# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 00 - Common configuration and helpers
# This notebook is **not run on its own**. Every other notebook loads it with `%run nb_scd2_00_common`.
# It holds the single source of truth for:
# - lakehouse names (bronze / silver / gold) and how to resolve their OneLake paths
# - table schemas (DDL) for every table in the solution
# - SCD column lists (which attributes are Type 2 history vs Type 1 overwrite)
# - shared helpers: path resolution, idempotent table creation, run logging, Delta metrics
#
# All reads and writes use **ABFSS OneLake paths**, so no notebook needs a default lakehouse attached
# and the same code works for schema-enabled and non-schema lakehouses.

# CELL ********************

import json
import re
import time
import uuid
from datetime import datetime, timezone

from delta.tables import DeltaTable
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# WHY: all SCD effective dates are compared as timestamps; a fixed session time zone keeps them deterministic.
spark.conf.set("spark.sql.session.timeZone", "UTC")
# WHY: unparseable dates become NULL (and are quarantined) instead of failing the whole batch.
spark.conf.set("spark.sql.legacy.timeParserPolicy", "CORRECTED")

CFG = {
    "lakehouses": {
        "bronze": "LH_SCD2_BRONZE",
        "silver": "LH_SCD2_SILVER",
        "gold": "LH_SCD2_GOLD",
    },
    "entity": "customer",
    # Folders inside the BRONZE lakehouse Files area
    "samples_dir": "Files/samples/customer",
    "landing_dir": "Files/landing/customer",
    "archive_dir": "Files/archive/customer",
    "rejected_dir": "Files/rejected/customer",
    # Source contract: one file per extract day, e.g. customer_20260101.csv or customer_20260101_2.csv
    "file_pattern": r"^customer_(\d{8})(?:_(\d+))?\.csv$",
    "source_columns": ["customer_id", "first_name", "last_name", "email", "phone",
                       "city", "state", "country", "segment", "op", "updated_at"],
    "source_ts_format": "yyyy-MM-dd HH:mm:ss",
    # SCD design: Type 2 columns create a new version; Type 1 columns overwrite the current version.
    "scd2_columns": ["email", "city", "state", "country", "segment"],
    "scd1_columns": ["first_name", "last_name", "phone"],
    "high_date": "9999-12-31 23:59:59",
    "unknown_sk": -1,
    # Data quality: fail the batch if more than this fraction of rows is quarantined.
    "max_reject_ratio": 0.30,
}

# ---------------------------------------------------------------------------
# Table schemas. Keeping DDL here means setup, writers and tests never drift apart.
# ---------------------------------------------------------------------------
BRONZE_RAW_DDL = """
customer_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING,
city STRING, state STRING, country STRING, segment STRING, op STRING, updated_at STRING,
_corrupt_record STRING, _source_file STRING, _source_row BIGINT, _batch_id STRING, _ingested_at TIMESTAMP
"""

FILE_MANIFEST_DDL = """
file_name STRING, file_path STRING, file_size BIGINT, batch_id STRING, row_count BIGINT,
status STRING, message STRING, loaded_at TIMESTAMP
"""

SILVER_CLEAN_DDL = """
customer_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING,
city STRING, state STRING, country STRING, segment STRING, op STRING, source_updated_at TIMESTAMP,
scd1_hash STRING, scd2_hash STRING, _batch_id STRING, _source_file STRING, _source_row BIGINT,
_processed_at TIMESTAMP
"""

SILVER_QUARANTINE_DDL = """
customer_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING,
city STRING, state STRING, country STRING, segment STRING, op STRING, updated_at STRING,
_corrupt_record STRING, _source_file STRING, _source_row BIGINT, _batch_id STRING,
dq_errors ARRAY<STRING>, _quarantined_at TIMESTAMP
"""

DIM_CUSTOMER_DDL = """
customer_sk BIGINT, customer_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING,
city STRING, state STRING, country STRING, segment STRING, scd1_hash STRING, scd2_hash STRING,
version_number INT, effective_from TIMESTAMP, effective_to TIMESTAMP, is_current BOOLEAN, is_deleted BOOLEAN,
inserted_batch_id STRING, updated_batch_id STRING, inserted_at TIMESTAMP, updated_at TIMESTAMP
"""

LATE_ARRIVALS_DDL = """
customer_id STRING, source_updated_at TIMESTAMP, current_effective_from TIMESTAMP, op STRING,
scd2_hash STRING, scd1_hash STRING, _batch_id STRING, reason STRING, logged_at TIMESTAMP
"""

RUN_LOG_DDL = """
run_id STRING, batch_id STRING, stage STRING, status STRING, started_at TIMESTAMP, ended_at TIMESTAMP,
duration_sec DOUBLE, metrics STRING, message STRING
"""

# layer -> table -> (ddl, table properties)
TABLES = {
    "bronze": {
        "customer_raw": (BRONZE_RAW_DDL, {}),
        "file_manifest": (FILE_MANIFEST_DDL, {}),
    },
    "silver": {
        "customer_clean": (SILVER_CLEAN_DDL, {}),
        "customer_quarantine": (SILVER_QUARANTINE_DDL, {}),
    },
    "gold": {
        # CDF lets downstream facts/semantic models consume only changed dimension rows.
        "dim_customer": (DIM_CUSTOMER_DDL, {"delta.enableChangeDataFeed": "true"}),
        "dim_customer_late_arrivals": (LATE_ARRIVALS_DDL, {}),
        "etl_run_log": (RUN_LOG_DDL, {}),
    },
}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------------------
# Lakehouse and path resolution
# ---------------------------------------------------------------------------
_LH_CACHE = {}


def _prop(obj, key, default=None):
    """notebookutils returns dict-like objects; support both dict and attribute access."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except Exception:
        return getattr(obj, key, default)


def lakehouse_info(layer):
    """Resolve a layer ('bronze'|'silver'|'gold') to its id, ABFSS root and default schema."""
    name = CFG["lakehouses"][layer]
    if name in _LH_CACHE:
        return _LH_CACHE[name]
    try:
        lh = notebookutils.lakehouse.getWithProperties(name)
    except Exception:
        lh = notebookutils.lakehouse.get(name)
    props = _prop(lh, "properties", {}) or {}
    abfs = _prop(props, "abfsPath")
    if not abfs:
        raise RuntimeError(f"Lakehouse {name} has no abfsPath yet. Run nb_scd2_01_setup_lakehouses first.")
    info = {
        "name": name,
        "id": _prop(lh, "id"),
        "abfs": abfs.rstrip("/"),
        # Schema-enabled lakehouses store tables under Tables/<schema>/<table>
        "schema": _prop(props, "defaultSchema"),
    }
    _LH_CACHE[name] = info
    return info


def table_path(layer, table):
    info = lakehouse_info(layer)
    if info["schema"]:
        return f"{info['abfs']}/Tables/{info['schema']}/{table}"
    return f"{info['abfs']}/Tables/{table}"


def file_path(layer, relative):
    return f"{lakehouse_info(layer)['abfs']}/{relative.strip('/')}"


def schema_of(ddl):
    return spark.createDataFrame([], ddl).schema


def read_table(layer, table):
    return spark.read.format("delta").load(table_path(layer, table))


def delta_table(layer, table):
    return DeltaTable.forPath(spark, table_path(layer, table))


def ensure_table(layer, table):
    """Create an empty Delta table at its OneLake path if it does not exist (idempotent)."""
    ddl, props = TABLES[layer][table]
    tblprops = ", ".join(f"'{k}' = '{v}'" for k, v in props.items())
    spark.sql(f"CREATE TABLE IF NOT EXISTS delta.`{table_path(layer, table)}` ({ddl.strip()}) USING DELTA"
              + (f" TBLPROPERTIES ({tblprops})" if tblprops else ""))


def overwrite_batch(df, layer, table, batch_col, batch_id):
    """Replace only one batch's rows. Rerunning a batch therefore never duplicates data."""
    (df.write.format("delta").mode("overwrite")
       .option("replaceWhere", f"{batch_col} = '{batch_id}'")
       .save(table_path(layer, table)))


def last_operation_metrics(layer, table):
    row = delta_table(layer, table).history(1).select("version", "operation", "operationMetrics").first()
    return {"version": row["version"], "operation": row["operation"], **(row["operationMetrics"] or {})}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------------------
# Run logging (gold.etl_run_log) and notebook exit helpers
# ---------------------------------------------------------------------------
def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def log_run(batch_id, stage, status, started_at, metrics=None, message=None):
    ended_at = utc_now()
    row = [(str(uuid.uuid4()), batch_id, stage, status, started_at, ended_at,
            float((ended_at - started_at).total_seconds()),
            json.dumps(metrics or {}, default=str), (message or "")[:4000])]
    (spark.createDataFrame(row, schema_of(RUN_LOG_DDL))
          .write.format("delta").mode("append").save(table_path("gold", "etl_run_log")))


def completed_batches(stage):
    """Batches whose given stage finished successfully at least once."""
    return {r["batch_id"] for r in read_table("gold", "etl_run_log")
            .where((F.col("stage") == stage) & (F.col("status") == "SUCCEEDED"))
            .select("batch_id").distinct().collect()}


def row_hash(cols):
    """SHA-256 of the given columns. NULLs get a sentinel so (NULL,'a') and ('a',NULL) differ."""
    return F.sha2(F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("<NULL>")) for c in cols]), 256)


def exit_json(payload):
    """Return a JSON string to a calling notebook / pipeline (notebookutils.notebook.exit)."""
    print(json.dumps(payload, default=str, indent=2))
    notebookutils.notebook.exit(json.dumps(payload, default=str))


print("SCD2 common config loaded:", CFG["lakehouses"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
