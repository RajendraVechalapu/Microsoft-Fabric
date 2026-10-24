# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 07 - Explore history, consume the dimension, maintain the tables
# Run after the orchestrator. Every cell is read-only except **Maintenance** and the opt-in **Reset**.
#
# 1. Current view, full history of one customer
# 2. Point-in-time ("as was") lookup and a fact join on `[effective_from, effective_to)`
# 3. Delta time travel vs SCD2 history - they answer different questions
# 4. Change Data Feed: what changed in the dimension in the last batch
# 5. Pipeline observability: run log, quarantine, late arrivals
# 6. Maintenance: OPTIMIZE / Z-ORDER / VACUUM
# 7. Reset (opt-in) to practise again from scratch

# PARAMETERS CELL ********************

as_of_ts = "2026-01-02 12:00:00"   # point-in-time to inspect
customer_to_trace = "C002"
RESET_CONFIRM = ""                 # type RESET to wipe all lab tables and files (lakehouses are kept)

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

# CELL ********************

# Register temp views so the rest of the notebook can be plain SQL.
for layer, tables in TABLES.items():
    for t in tables:
        read_table(layer, t).createOrReplaceTempView(t)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Current state and the full history of one customer

# CELL ********************

display(spark.sql("""
SELECT customer_sk, customer_id, first_name, last_name, email, city, segment, version_number, effective_from
FROM dim_customer WHERE is_current ORDER BY customer_id"""))

display(spark.sql(f"""
SELECT customer_sk, version_number, city, state, segment, email, phone,
       effective_from, effective_to, is_current, is_deleted, inserted_batch_id, updated_batch_id
FROM dim_customer WHERE customer_id = '{customer_to_trace}' ORDER BY version_number"""))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Point-in-time lookup and the fact-join pattern
# A fact row picks the dimension version that was valid **when the event happened**:
# `fact.event_ts >= dim.effective_from AND fact.event_ts < dim.effective_to` (half-open interval => exactly one match).
# Unmatched facts fall back to the unknown member `-1`.

# CELL ********************

display(spark.sql(f"""
SELECT customer_id, customer_sk, city, segment, effective_from, effective_to
FROM dim_customer
WHERE effective_from <= TIMESTAMP'{as_of_ts}' AND TIMESTAMP'{as_of_ts}' < effective_to
  AND customer_sk <> {CFG['unknown_sk']}
ORDER BY customer_id"""))

spark.createDataFrame([
    ("S1", "C002", "2026-01-01 12:00:00", 100.0),   # Wellington version
    ("S2", "C002", "2026-01-02 15:00:00", 250.0),   # Hamilton / Retail version
    ("S3", "C002", "2026-01-04 09:00:00", 75.0),    # Hamilton / SMB version
    ("S4", "C005", "2026-01-04 09:00:00", 40.0),    # after delete -> unknown member
    ("S5", "C888", "2026-01-02 09:00:00", 10.0),    # never existed -> unknown member
], "sale_id string, customer_id string, sale_ts string, amount double") \
    .withColumn("sale_ts", F.to_timestamp("sale_ts")).createOrReplaceTempView("sales")

display(spark.sql(f"""
SELECT s.sale_id, s.customer_id, s.sale_ts, s.amount,
       COALESCE(d.customer_sk, {CFG['unknown_sk']}) AS customer_sk, d.city, d.segment
FROM sales s
LEFT JOIN dim_customer d
  ON d.customer_id = s.customer_id
 AND s.sale_ts >= d.effective_from AND s.sale_ts < d.effective_to
ORDER BY s.sale_id"""))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Delta time travel vs SCD2
# - **SCD2** = business history: *what was true in the real world* at a business time (`effective_from/to`).
# - **Delta time travel** = technical history: *what the table looked like* after a given commit. Limited by VACUUM retention,
#   so it is for audit/debug/rollback, **never** a replacement for SCD2.

# CELL ********************

dim_dt = delta_table("gold", "dim_customer")
display(dim_dt.history().select("version", "timestamp", "operation", "operationMetrics").orderBy("version"))

# MERGE #1 is the setup notebook seeding the unknown member; MERGE #2 is the first batch.
merges = [r["version"] for r in dim_dt.history().where("operation = 'MERGE'").orderBy("version").collect()]
if len(merges) > 1:
    print(f"dim_customer as of Delta version {merges[1]} (right after the first batch):")
    display(spark.read.format("delta").option("versionAsOf", merges[1])
            .load(table_path("gold", "dim_customer")).orderBy("customer_id", "version_number"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Change Data Feed - incremental consumption of the dimension
# Downstream consumers (fact builds, exports) read only the rows changed by the last merge instead of the whole table.

# CELL ********************

# Last MERGE commit (OPTIMIZE/VACUUM commits carry no data changes)
latest_merge = dim_dt.history().where("operation = 'MERGE'").agg(F.max("version")).first()[0]
display(spark.read.format("delta").option("readChangeFeed", "true")
        .option("startingVersion", latest_merge).option("endingVersion", latest_merge)
        .load(table_path("gold", "dim_customer"))
        .select("_change_type", "_commit_version", "customer_sk", "customer_id", "version_number",
                "city", "segment", "is_current", "effective_to")
        .orderBy("customer_id", "_change_type"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 5. Observability: run log, file manifest, quarantine, late arrivals

# CELL ********************

display(spark.sql("SELECT batch_id, stage, status, started_at, duration_sec, metrics, message FROM etl_run_log ORDER BY started_at"))
display(spark.sql("SELECT * FROM file_manifest ORDER BY file_name"))
display(spark.sql("SELECT _batch_id, _source_row, customer_id, email, dq_errors FROM customer_quarantine ORDER BY _batch_id, _source_row"))
display(spark.sql("SELECT * FROM dim_customer_late_arrivals"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 6. Maintenance (schedule weekly / in a quiet window, never concurrently with a merge)
# - `OPTIMIZE ... ZORDER BY (customer_id)` compacts small files from frequent merges and co-locates the merge key
# - `VACUUM` removes files no longer referenced; 168 h (7 days) keeps time travel for a week

# CELL ********************

dim_dt.optimize().executeZOrderBy("customer_id")
dim_dt.vacuum(168)
for layer, t in [("bronze", "customer_raw"), ("silver", "customer_clean"), ("gold", "etl_run_log")]:
    delta_table(layer, t).optimize().executeCompaction()
print("maintenance done")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 7. Reset (opt-in)
# Set `RESET_CONFIRM = "RESET"` and run this cell to delete every lab table and file. The three lakehouses are kept.
# Afterwards run **nb_scd2_01_setup_lakehouses** again.

# CELL ********************

if RESET_CONFIRM == "RESET":
    for layer, tables in TABLES.items():
        for t in tables:
            notebookutils.fs.rm(table_path(layer, t), True)
            print("dropped", CFG["lakehouses"][layer], t)
    for key in ["samples_dir", "landing_dir", "archive_dir", "rejected_dir"]:
        notebookutils.fs.rm(file_path("bronze", CFG[key]), True)
        print("removed", CFG[key])
    print("Reset complete. Run nb_scd2_01_setup_lakehouses next.")
else:
    print("Reset skipped (set RESET_CONFIRM = 'RESET' to enable).")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
