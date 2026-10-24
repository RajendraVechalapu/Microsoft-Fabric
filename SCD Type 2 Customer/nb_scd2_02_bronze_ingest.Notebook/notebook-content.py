# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 02 - Bronze: ingest one customer CSV file
# **One file = one batch.** SCD2 history is order-sensitive, so files are processed strictly oldest-first,
# one at a time. `batch_id` is derived from the file name (e.g. `customer_20260102`), which makes reruns deterministic.
# # Production controls in this notebook:
# - **File contract check**: header must match the expected columns exactly, otherwise the file moves to `rejected/`
# - **Raw fidelity**: every column lands as STRING, plus lineage columns (`_source_file`, `_source_row`, `_batch_id`, `_ingested_at`)
# - **Malformed rows are kept**, captured in `_corrupt_record` and quarantined later in silver
# - **Idempotency**: `replaceWhere _batch_id = ...` overwrites only this batch; `file_manifest` prevents double loads
# - **Archive** after success so landing only ever contains unprocessed files
# # Returns (via `notebookutils.notebook.exit`) JSON: `{"status": "LOADED"|"NO_FILES", "batch_id": ..., ...}`

# PARAMETERS CELL ********************

# Optional: a specific file name in landing. Empty = oldest pending file.
source_file = ""

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

%run nb_scd2_00_common%run nb_scd2_00_common

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Find the next file to load
# Files already marked `LOADED` in the manifest but still sitting in landing (e.g. the archive move failed last time)
# are archived now and skipped - this is what makes the notebook safe to rerun after a failure at any step.

# CELL ********************

started_at = utc_now()
pattern = re.compile(CFG["file_pattern"])
landing = file_path("bronze", CFG["landing_dir"])
archive_root = file_path("bronze", CFG["archive_dir"])

loaded = {r["file_name"] for r in read_table("bronze", "file_manifest").where("status = 'LOADED'").collect()}
landed = sorted([f for f in notebookutils.fs.ls(landing) if not f.isDir], key=lambda f: f.name)

pending = []
for f in landed:
    if not pattern.match(f.name):
        print(f"WARNING: ignoring file that does not match the naming contract: {f.name}")
    elif f.name in loaded:
        print(f"already loaded, archiving leftover: {f.name}")
        notebookutils.fs.mv(f.path, f"{archive_root}/{f.name}", True, True)
    else:
        pending.append(f)

if source_file:
    pending = [f for f in pending if f.name == source_file]
    if not pending:
        raise ValueError(f"{source_file} is not a pending file in {CFG['landing_dir']}")

print("pending files:", [f.name for f in pending])
if not pending:
    exit_json({"status": "NO_FILES"})

src = pending[0]
batch_id = src.name.rsplit(".", 1)[0]
print(f"loading {src.name} as batch {batch_id}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. File contract check (header)

# CELL ********************

def record_manifest(status, row_count=None, message=None):
    m = spark.createDataFrame(
        [(src.name, src.path, int(src.size), batch_id, row_count, status, message, utc_now())],
        schema_of(FILE_MANIFEST_DDL))
    (delta_table("bronze", "file_manifest").alias("t")
        .merge(m.alias("s"), "t.file_name = s.file_name")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute())


header = spark.read.text(src.path).first()
actual_cols = [c.strip().lower() for c in (header[0] if header else "").lstrip("﻿").split(",")]
if actual_cols != CFG["source_columns"]:
    msg = f"Header mismatch. expected={CFG['source_columns']} actual={actual_cols}"
    notebookutils.fs.mv(src.path, f"{file_path('bronze', CFG['rejected_dir'])}/{src.name}", True, True)
    record_manifest("REJECTED", 0, msg)
    log_run(batch_id, "bronze_ingest", "FAILED", started_at, message=msg)
    raise ValueError(msg)
print("header OK")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Read as raw strings and write to bronze (`customer_raw`)

# CELL ********************

raw_schema = schema_of(", ".join(f"{c} STRING" for c in CFG["source_columns"]) + ", _corrupt_record STRING")

raw = (spark.read
       .option("header", True)
       .option("mode", "PERMISSIVE")
       .option("columnNameOfCorruptRecord", "_corrupt_record")
       .option("multiLine", False)
       .option("encoding", "UTF-8")
       .schema(raw_schema)
       .csv(src.path)
       .cache())  # cache is required by Spark when _corrupt_record is used in later expressions

bronze_df = (raw
    .withColumn("_source_file", F.lit(src.name))
    # single small file => one partition => monotonically_increasing_id follows file order
    .withColumn("_source_row", F.monotonically_increasing_id() + 1)
    .withColumn("_batch_id", F.lit(batch_id))
    .withColumn("_ingested_at", F.current_timestamp())
    .select(*schema_of(BRONZE_RAW_DDL).fieldNames()))

row_count = bronze_df.count()
if row_count == 0:
    print("WARNING: file has a header but no data rows")

overwrite_batch(bronze_df, "bronze", "customer_raw", "_batch_id", batch_id)
corrupt = raw.where(F.col("_corrupt_record").isNotNull()).count()
raw.unpersist()
print(f"bronze rows written: {row_count} (malformed: {corrupt})")
display(read_table("bronze", "customer_raw").where(F.col("_batch_id") == batch_id).orderBy("_source_row"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Mark loaded, archive the file, log the run
# Order matters: data first, then manifest, then move. A failure between steps is recovered by a simple rerun.

# CELL ********************

record_manifest("LOADED", row_count)
notebookutils.fs.mv(src.path, f"{archive_root}/{src.name}", True, True)

metrics = {"file": src.name, "rows": row_count, "malformed_rows": corrupt}
log_run(batch_id, "bronze_ingest", "SUCCEEDED", started_at, metrics)
exit_json({"status": "LOADED", "batch_id": batch_id, **metrics})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
