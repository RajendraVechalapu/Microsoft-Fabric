# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 01 - Set up bronze, silver and gold lakehouses
# Run this notebook **once** (it is safe to rerun - every step is idempotent).
#
# What it does:
# 1. Creates three lakehouses in the current workspace if they do not exist:
#    `LH_SCD2_BRONZE`, `LH_SCD2_SILVER`, `LH_SCD2_GOLD`
# 2. Creates the folder layout in bronze: `samples`, `landing`, `archive`, `rejected`
# 3. Writes three daily sample CSV extracts for the customer source system
# 4. Lands the sample files in `Files/landing/customer` (all three, or only day 1)
# 5. Creates every Delta table with an explicit schema and seeds the dimension's **unknown member** (`customer_sk = -1`)
#
# No default lakehouse needs to be attached to this notebook.
#
# | Layer | Lakehouse | Tables |
# |---|---|---|
# | Bronze | LH_SCD2_BRONZE | `customer_raw`, `file_manifest` |
# | Silver | LH_SCD2_SILVER | `customer_clean`, `customer_quarantine` |
# | Gold | LH_SCD2_GOLD | `dim_customer` (SCD2), `dim_customer_late_arrivals`, `etl_run_log` |

# PARAMETERS CELL ********************

# "all"  -> land day 1, 2 and 3 (the orchestrator then processes them in order)
# "day1" -> land only day 1; land later days yourself with land_sample_file() below
# "none" -> only write the samples, land nothing
LAND_SAMPLE_FILES = "all"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %run nb_scd2_00_common

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Create the three lakehouses (idempotent)
# `notebookutils.lakehouse.create` provisions a lakehouse plus its SQL analytics endpoint.
# Provisioning is asynchronous, so we poll until the OneLake ABFSS path is available.

# CELL ********************

def ensure_lakehouse(name, description, timeout_sec=300):
    try:
        lh = notebookutils.lakehouse.get(name)
        if _prop(_prop(lh, "properties", {}), "abfsPath"):
            print(f"[exists ] {name}")
            return lh
    except Exception:
        print(f"[create ] {name}")
        notebookutils.lakehouse.create(name=name, description=description)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            lh = notebookutils.lakehouse.get(name)
            if _prop(_prop(lh, "properties", {}), "abfsPath"):
                print(f"[ready  ] {name}")
                return lh
        except Exception:
            pass
        time.sleep(10)
    raise TimeoutError(f"Lakehouse {name} was not provisioned within {timeout_sec}s")


descriptions = {
    "bronze": "SCD2 lab - raw customer CSV files and raw Delta table (append-only, as received)",
    "silver": "SCD2 lab - validated, standardised, de-duplicated customer changes",
    "gold": "SCD2 lab - conformed dim_customer (SCD Type 2) and pipeline audit",
}
for layer, name in CFG["lakehouses"].items():
    ensure_lakehouse(name, descriptions[layer])

_LH_CACHE.clear()
display(spark.createDataFrame(
    [(layer, i["name"], i["id"], i["schema"] or "(no schemas)", i["abfs"])
     for layer, i in ((l, lakehouse_info(l)) for l in CFG["lakehouses"])],
    "layer string, lakehouse string, id string, default_schema string, abfs_path string"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Folder layout in the bronze lakehouse
# - `samples/` - our simulated source system "outbox" (only used for this lab)
# - `landing/` - where the source drops files; the ingest notebook reads from here
# - `archive/` - successfully loaded files are moved here (never re-read)
# - `rejected/` - files that break the file contract (wrong header) are moved here

# CELL ********************

for key in ["samples_dir", "landing_dir", "archive_dir", "rejected_dir"]:
    notebookutils.fs.mkdirs(file_path("bronze", CFG[key]))
    print("folder ready:", CFG[key])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Sample source extracts (3 days)
# Each file is a **delta extract**: only customers that changed that day, with `op` = I(nsert) / U(pdate) / D(elete)
# and the source change time `updated_at`.
#
# | Day | Scenario it exercises |
# |---|---|
# | 1 | Initial load of 5 customers |
# | 2 | C001 unchanged (no-op) - C002 moves city (**SCD2**) - C003 phone changes and messy name casing (**SCD1** only) - C004 appears **twice** (de-dup keeps latest, **SCD2**) - C006 **new** - 1 row without id and 1 bad email (**quarantine**) |
# | 3 | C002 changes segment (**3rd version**) - C003 moves city (**SCD2**) - C005 **deleted** - C006 **late-arriving** older change (logged, not applied) - C007 arrives with fixed email (**new**) - C999 delete for unknown key (ignored) |

# CELL ********************

HEADER = ",".join(CFG["source_columns"])
SAMPLES = {
    "customer_20260101.csv": [
        "C001,Aroha,Ngata,aroha.ngata@example.com,021-555-0101,Auckland,AUK,NZ,Retail,I,2026-01-01 08:00:00",
        "C002,Priya,Sharma,priya.sharma@example.com,021-555-0102,Wellington,WGN,NZ,Retail,I,2026-01-01 08:00:00",
        "C003,James,Lee,james.lee@example.com,021-555-0103,Christchurch,CAN,NZ,SMB,I,2026-01-01 08:00:00",
        "C004,Maria,Garcia,maria.garcia@example.com,02-5550-0104,Sydney,NSW,AU,Enterprise,I,2026-01-01 08:00:00",
        "C005,Wei,Chen,wei.chen@example.com,03-5550-0105,Melbourne,VIC,AU,SMB,I,2026-01-01 08:00:00",
    ],
    "customer_20260102.csv": [
        "C001,Aroha,Ngata,aroha.ngata@example.com,021-555-0101,Auckland,AUK,NZ,Retail,U,2026-01-02 07:30:00",
        "C002,Priya,Sharma,priya.sharma@example.com,021-555-0102,Hamilton,WKO,NZ,Retail,U,2026-01-02 09:00:00",
        "C003,  JAMES ,lee,James.Lee@Example.com,021-555-0199,Christchurch,can,nz,smb,U,2026-01-02 09:15:00",
        "C004,Maria,Garcia,maria.garcia@example.com,02-5550-0104,Sydney,NSW,AU,Strategic,U,2026-01-02 10:00:00",
        "C004,Maria,Garcia,maria.g@example.com,02-5550-0104,Sydney,NSW,AU,Strategic,U,2026-01-02 11:00:00",
        "C006,Tane,Walker,tane.walker@example.com,027-555-0106,Dunedin,OTA,NZ,Retail,I,2026-01-02 12:00:00",
        ",No,Id,no.id@example.com,000,Nowhere,XX,NZ,Retail,I,2026-01-02 12:30:00",
        "C007,Liam,Smith,not-an-email,021-555-0107,Napier,HKB,NZ,Retail,I,2026-01-02 13:00:00",
    ],
    "customer_20260103.csv": [
        "C002,Priya,Sharma,priya.sharma@example.com,021-555-0102,Hamilton,WKO,NZ,SMB,U,2026-01-03 09:00:00",
        "C003,James,Lee,james.lee@example.com,021-555-0199,Nelson,NSN,NZ,SMB,U,2026-01-03 09:30:00",
        "C005,Wei,Chen,wei.chen@example.com,03-5550-0105,Melbourne,VIC,AU,SMB,D,2026-01-03 10:00:00",
        "C006,Tane,Walker,tane.walker@example.com,027-555-0106,Queenstown,OTA,NZ,Retail,U,2026-01-01 23:00:00",
        "C007,Liam,Smith,liam.smith@example.com,021-555-0107,Napier,HKB,NZ,Retail,I,2026-01-03 11:00:00",
        "C999,Ghost,Customer,ghost@example.com,000,Nowhere,XX,NZ,Retail,D,2026-01-03 12:00:00",
    ],
}

for name, rows in SAMPLES.items():
    notebookutils.fs.put(file_path("bronze", f"{CFG['samples_dir']}/{name}"), "\n".join([HEADER, *rows]) + "\n", True)
    print(f"sample written: {name} ({len(rows)} rows)")


def land_sample_file(name):
    """Simulate the source system dropping a file into landing (copy from samples)."""
    notebookutils.fs.cp(file_path("bronze", f"{CFG['samples_dir']}/{name}"),
                        file_path("bronze", f"{CFG['landing_dir']}/{name}"))
    print("landed:", name)


already_loaded = set()
if DeltaTable.isDeltaTable(spark, table_path("bronze", "file_manifest")):
    already_loaded = {r["file_name"] for r in read_table("bronze", "file_manifest").collect()}

to_land = {"all": sorted(SAMPLES), "day1": ["customer_20260101.csv"], "none": []}[LAND_SAMPLE_FILES]
for name in to_land:
    if name in already_loaded:
        print("skip (already loaded in a previous run):", name)
    else:
        land_sample_file(name)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Create all Delta tables with explicit schemas
# Explicit schemas (instead of letting the first write infer them) are a production must:
# types never drift with the data, and every downstream notebook can rely on the contract.
#
# The dimension also gets an **unknown member** row (`customer_sk = -1`). Fact loads map
# missing/late customers to it instead of dropping the fact row.

# CELL ********************

for layer, tables in TABLES.items():
    for table in tables:
        ensure_table(layer, table)
        print(f"table ready: {CFG['lakehouses'][layer]}.{table}")

unknown = spark.sql(f"""
SELECT CAST({CFG['unknown_sk']} AS BIGINT) AS customer_sk, 'UNKNOWN' AS customer_id,
       'Unknown' AS first_name, 'Unknown' AS last_name, CAST(NULL AS STRING) AS email, CAST(NULL AS STRING) AS phone,
       'Unknown' AS city, 'Unknown' AS state, 'Unknown' AS country, 'Unknown' AS segment,
       CAST(NULL AS STRING) AS scd1_hash, CAST(NULL AS STRING) AS scd2_hash, 1 AS version_number,
       TIMESTAMP'1900-01-01 00:00:00' AS effective_from, TIMESTAMP'{CFG['high_date']}' AS effective_to,
       true AS is_current, false AS is_deleted, 'SETUP' AS inserted_batch_id, 'SETUP' AS updated_batch_id,
       current_timestamp() AS inserted_at, current_timestamp() AS updated_at
""")
(delta_table("gold", "dim_customer").alias("t")
    .merge(unknown.alias("s"), "t.customer_sk = s.customer_sk")
    .whenNotMatchedInsertAll()
    .execute())

display(read_table("gold", "dim_customer"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 5. What is in landing now?
# Next step: run **nb_scd2_06_orchestrator** (processes every landed file in order), or run
# 02 -> 03 -> 04 -> 05 by hand for one file at a time to see each layer.

# CELL ********************

display(spark.createDataFrame([(f.name, f.size) for f in notebookutils.fs.ls(file_path("bronze", CFG["landing_dir"]))],
                              "file_name string, size_bytes long"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
