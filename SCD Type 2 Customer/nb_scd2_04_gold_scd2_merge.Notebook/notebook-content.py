# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 04 - Gold: apply one batch to `dim_customer` (SCD Type 2)
# This is the heart of the solution. It uses **one atomic Delta `MERGE`** (the "merge-key / NULL-key" staging pattern),
# so a failure can never leave a customer with its old row closed but no new row inserted.
# # ### Classifying each incoming row against the current dimension row
# | Action | Rule (evaluated in this order) | Effect |
# |---|---|---|
# | `IGNORE_DELETE` | delete for a key with no current row | nothing |
# | `INSERT_NEW` | key has no current row | insert version 1 (or next version if it was deleted earlier) |
# | `NO_CHANGE` | both hashes equal | nothing - **this is what makes reruns idempotent** |
# | `LATE_ARRIVAL` | source change is older than the current version | logged to `dim_customer_late_arrivals`, not applied |
# | `DELETE` | `op = 'D'` | close current row, `is_deleted = true` |
# | `SCD2_CHANGE` | Type 2 hash differs | close current row **and** insert a new current version |
# | `SCD1_UPDATE` | only Type 1 hash differs | overwrite Type 1 columns on the current row |
# # ### The single-MERGE trick
# A changed customer needs two actions on the target (UPDATE old row + INSERT new row), but MERGE does one action per source row.
# So the staged source contains the changed customer **twice**:
# - once with `merge_key = customer_id` -> matches the current row -> **UPDATE** (close it)
# - once with `merge_key = NULL` -> can never match -> **INSERT** (new version)
# # Effective dating is **half-open** `[effective_from, effective_to)`: the closed row's `effective_to` equals the new row's `effective_from`.
# # **Concurrency:** surrogate keys are `max(customer_sk) + row_number()`. Run one writer per dimension at a time (the orchestrator does).

# PARAMETERS CELL ********************

# Batch to apply. Empty = the most recent silver batch.
batch_id = ""

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

# CELL ********************

started_at = utc_now()
if not batch_id:
    latest = read_table("silver", "customer_clean").select(F.max("_batch_id")).first()[0]
    if latest is None:
        raise ValueError("No silver batch found. Run nb_scd2_03_silver_cleanse first.")
    batch_id = latest
print("applying batch:", batch_id)

src = read_table("silver", "customer_clean").where(F.col("_batch_id") == batch_id)
dim = read_table("gold", "dim_customer")

# Guard: silver must be unique per key, otherwise MERGE would fail (or worse, be ambiguous).
dupes = src.groupBy("customer_id").count().where("count > 1").count()
if dupes:
    raise ValueError(f"{dupes} duplicate customer_id values in silver batch {batch_id}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Classify every incoming row

# CELL ********************

current = (dim.where("is_current AND customer_sk <> {}".format(CFG["unknown_sk"]))
              .select("customer_id",
                      F.col("customer_sk").alias("cur_sk"),
                      F.col("scd2_hash").alias("cur_scd2_hash"),
                      F.col("scd1_hash").alias("cur_scd1_hash"),
                      F.col("effective_from").alias("cur_effective_from"),
                      F.col("version_number").alias("cur_version")))
# Highest version ever issued per key (a deleted-then-returning customer continues numbering).
max_version = dim.groupBy("customer_id").agg(F.max("version_number").alias("max_version"))

classified = (src.join(current, "customer_id", "left")
                 .join(max_version, "customer_id", "left")
                 .withColumn("action",
                     F.when(F.col("cur_sk").isNull() & (F.col("op") == "D"), "IGNORE_DELETE")
                      .when(F.col("cur_sk").isNull(), "INSERT_NEW")
                      .when((F.col("op") != "D") & (F.col("scd2_hash") == F.col("cur_scd2_hash"))
                            & (F.col("scd1_hash") == F.col("cur_scd1_hash")), "NO_CHANGE")
                      .when(F.col("source_updated_at") <= F.col("cur_effective_from"), "LATE_ARRIVAL")
                      .when(F.col("op") == "D", "DELETE")
                      .when(F.col("scd2_hash") != F.col("cur_scd2_hash"), "SCD2_CHANGE")
                      .otherwise("SCD1_UPDATE"))
                 # WHY: materialise now. `classified` is derived from the target table; it must not be
                 # recomputed against the post-MERGE snapshot when used again further down.
                 .localCheckpoint())

action_counts = {r["action"]: r["count"] for r in classified.groupBy("action").count().collect()}
print("actions:", action_counts)
display(classified.select("customer_id", "op", "source_updated_at", "cur_effective_from", "cur_version", "action")
                  .orderBy("customer_id"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Build the staged MERGE source

# CELL ********************

load_ts = F.current_timestamp()
attr_cols = CFG["scd1_columns"] + CFG["scd2_columns"]

# (a) rows that UPDATE the current target row: close it (SCD2/DELETE) or overwrite Type 1 columns
updates = (classified.where(F.col("action").isin("SCD2_CHANGE", "DELETE", "SCD1_UPDATE"))
                     .withColumn("merge_key", F.col("customer_id"))
                     .withColumn("new_sk", F.lit(None).cast("bigint"))
                     .withColumn("new_version", F.lit(None).cast("int")))

# (b) rows that INSERT a new current version: brand-new keys and the new side of SCD2 changes
max_sk = dim.select(F.coalesce(F.max("customer_sk"), F.lit(0))).first()[0]
max_sk = max(max_sk, 0)
inserts = (classified.where(F.col("action").isin("INSERT_NEW", "SCD2_CHANGE"))
                     .withColumn("merge_key", F.lit(None).cast("string"))
                     .withColumn("new_sk", F.lit(max_sk) + F.row_number().over(Window.orderBy("customer_id")))
                     .withColumn("new_version", F.coalesce(F.col("max_version"), F.lit(0)) + 1))

staged = (updates.unionByName(inserts)
                 .withColumn("load_ts", load_ts)
                 .select("merge_key", "action", "customer_id", *attr_cols, "scd1_hash", "scd2_hash",
                         "source_updated_at", "new_sk", "new_version", "_batch_id", "load_ts"))
display(staged.orderBy("customer_id", F.col("merge_key").asc_nulls_last()))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. One atomic MERGE
# Equivalent Spark SQL, for reference:
# ```sql
# MERGE INTO dim_customer t
# USING staged s
#   ON t.customer_id = s.merge_key AND t.is_current = true
# WHEN MATCHED AND s.action IN ('SCD2_CHANGE','DELETE') THEN
#   UPDATE SET t.effective_to = s.source_updated_at, t.is_current = false, t.is_deleted = (s.action = 'DELETE'), ...
# WHEN MATCHED AND s.action = 'SCD1_UPDATE' THEN
#   UPDATE SET t.first_name = s.first_name, t.last_name = s.last_name, t.phone = s.phone, t.scd1_hash = s.scd1_hash, ...
# WHEN NOT MATCHED AND s.merge_key IS NULL THEN
#   INSERT (...) VALUES (s.new_sk, s.customer_id, ..., s.source_updated_at, TIMESTAMP '9999-12-31 23:59:59', true, false, ...)
# ```

# CELL ********************

audit_update = {"updated_batch_id": "s._batch_id", "updated_at": "s.load_ts"}
close_set = {"effective_to": "s.source_updated_at", "is_current": "false",
             "is_deleted": "s.action = 'DELETE'", **audit_update}
scd1_set = {**{c: f"s.{c}" for c in CFG["scd1_columns"]}, "scd1_hash": "s.scd1_hash", **audit_update}
insert_values = {
    "customer_sk": "s.new_sk", "customer_id": "s.customer_id",
    **{c: f"s.{c}" for c in attr_cols},
    "scd1_hash": "s.scd1_hash", "scd2_hash": "s.scd2_hash", "version_number": "s.new_version",
    "effective_from": "s.source_updated_at", "effective_to": f"TIMESTAMP'{CFG['high_date']}'",
    "is_current": "true", "is_deleted": "false",
    "inserted_batch_id": "s._batch_id", "updated_batch_id": "s._batch_id",
    "inserted_at": "s.load_ts", "updated_at": "s.load_ts",
}

(delta_table("gold", "dim_customer").alias("t")
    .merge(staged.alias("s"), "t.customer_id = s.merge_key AND t.is_current = true")
    .whenMatchedUpdate(condition="s.action IN ('SCD2_CHANGE', 'DELETE')", set=close_set)
    .whenMatchedUpdate(condition="s.action = 'SCD1_UPDATE'", set=scd1_set)
    .whenNotMatchedInsert(condition="s.merge_key IS NULL", values=insert_values)
    .execute())

merge_metrics = last_operation_metrics("gold", "dim_customer")
print({k: merge_metrics.get(k) for k in ["version", "operation", "numTargetRowsInserted", "numTargetRowsUpdated",
                                         "numSourceRows"]})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Record late arrivals, fast integrity check, log
# Late arrivals are **not** silently dropped: they are written to `dim_customer_late_arrivals` for a data steward
# to decide whether history must be re-stated (see the PDF guide for the re-statement approach).

# CELL ********************

late_df = (classified.where("action = 'LATE_ARRIVAL'")
    .select("customer_id", "source_updated_at", F.col("cur_effective_from").alias("current_effective_from"), "op",
            "scd2_hash", "scd1_hash", "_batch_id",
            F.lit("source change is older than the current version").alias("reason"),
            F.current_timestamp().alias("logged_at")))
overwrite_batch(late_df, "gold", "dim_customer_late_arrivals", "_batch_id", batch_id)

# Fail fast if the merge broke the core SCD2 invariant (full checks run in nb_scd2_05).
multi_current = (read_table("gold", "dim_customer").where("is_current")
                 .groupBy("customer_id").count().where("count > 1").count())
if multi_current:
    msg = f"{multi_current} customers have more than one current row after batch {batch_id}"
    log_run(batch_id, "gold_scd2_merge", "FAILED", started_at, action_counts, msg)
    raise AssertionError(msg)

metrics = {"actions": action_counts,
           "rows_inserted": int(merge_metrics.get("numTargetRowsInserted", 0)),
           "rows_updated": int(merge_metrics.get("numTargetRowsUpdated", 0)),
           "delta_version": merge_metrics["version"]}
log_run(batch_id, "gold_scd2_merge", "SUCCEEDED", started_at, metrics)

display(read_table("gold", "dim_customer").orderBy("customer_id", "version_number"))
exit_json({"status": "SUCCEEDED", "batch_id": batch_id, **metrics})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
