# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 03 - Silver: validate, standardise, de-duplicate, hash
# Input: one bronze batch. Output: exactly **one clean row per `customer_id`** for that batch, ready for the SCD2 merge.
#
# 1. **Validate** with explicit data-quality rules -> failing rows go to `customer_quarantine` with the reasons (never silently dropped)
# 2. **Standardise** (trim, casing, phone digits) so cosmetic differences do not create fake SCD2 versions
# 3. **De-duplicate** to the latest change per key - Delta `MERGE` fails if two source rows match one target row
# 4. **Hash** the Type 2 and Type 1 attribute groups separately (`scd2_hash`, `scd1_hash`) for cheap change detection
# 5. **Quality gate**: the batch fails if more than `max_reject_ratio` of its rows are quarantined

# PARAMETERS CELL ********************

# Batch to process. Empty = the most recently ingested bronze batch (handy when running by hand).
batch_id = ""

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

started_at = utc_now()
if not batch_id:
    latest = read_table("bronze", "file_manifest").where("status = 'LOADED'").orderBy(F.desc("batch_id")).first()
    if latest is None:
        raise ValueError("No loaded bronze batch found. Run nb_scd2_02_bronze_ingest first.")
    batch_id = latest["batch_id"]
print("processing batch:", batch_id)

bronze = read_table("bronze", "customer_raw").where(F.col("_batch_id") == batch_id).cache()
input_rows = bronze.count()
print("bronze rows:", input_rows)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Data-quality rules
# Each rule produces an error code or NULL; the non-null codes are collected into `dq_errors`.

# CELL ********************

def clean_str(c):
    """Trim and turn empty strings into NULL."""
    return F.when(F.trim(F.col(c)) == "", None).otherwise(F.trim(F.col(c)))


typed = bronze
for c in CFG["source_columns"]:
    typed = typed.withColumn(c, clean_str(c))
typed = typed.withColumn("source_updated_at", F.to_timestamp("updated_at", CFG["source_ts_format"]))

EMAIL_RE = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
rules = [
    F.when(F.col("_corrupt_record").isNotNull(), F.lit("MALFORMED_ROW")),
    F.when(F.col("customer_id").isNull(), F.lit("MISSING_CUSTOMER_ID")),
    F.when(F.col("customer_id").isNotNull() & ~F.upper("customer_id").rlike(r"^C[0-9]{3,}$"), F.lit("INVALID_CUSTOMER_ID")),
    F.when(F.col("source_updated_at").isNull(), F.lit("INVALID_UPDATED_AT")),
    F.when(F.col("source_updated_at") > F.current_timestamp() + F.expr("INTERVAL 1 DAY"), F.lit("FUTURE_UPDATED_AT")),
    F.when(F.col("op").isNull() | ~F.upper("op").isin("I", "U", "D"), F.lit("INVALID_OP")),
    # Deletes only need a key; inserts/updates need a valid email
    F.when((F.upper("op") != "D") & (F.col("email").isNull() | ~F.col("email").rlike(EMAIL_RE)), F.lit("INVALID_EMAIL")),
]
checked = typed.withColumn("dq_errors", F.filter(F.array(*rules), lambda x: x.isNotNull()))

valid = checked.where(F.size("dq_errors") == 0)
invalid = checked.where(F.size("dq_errors") > 0)

quarantine_df = (bronze.join(invalid.select("_source_row", "dq_errors"), "_source_row")
                 .withColumn("_quarantined_at", F.current_timestamp())
                 .select(*schema_of(SILVER_QUARANTINE_DDL).fieldNames()))
display(quarantine_df.select("_source_row", "customer_id", "email", "op", "updated_at", "dq_errors"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Standardise, de-duplicate, hash
# Without standardisation `"  JAMES "` vs `"James"` would look like a change and create a bogus version.

# CELL ********************

standardised = (valid
    .withColumn("customer_id", F.upper("customer_id"))
    .withColumn("op", F.upper("op"))
    .withColumn("first_name", F.initcap("first_name"))
    .withColumn("last_name", F.initcap("last_name"))
    .withColumn("email", F.lower("email"))
    .withColumn("phone", F.regexp_replace("phone", r"[^0-9+]", ""))
    .withColumn("city", F.initcap("city"))
    .withColumn("state", F.upper("state"))
    .withColumn("country", F.upper("country"))
    .withColumn("segment", F.initcap("segment")))

# Latest change per key wins; file row order breaks ties on identical timestamps.
latest_first = Window.partitionBy("customer_id").orderBy(F.desc("source_updated_at"), F.desc("_source_row"))
deduped = (standardised
    .withColumn("_rn", F.row_number().over(latest_first))
    .where("_rn = 1")
    .drop("_rn"))

clean_df = (deduped
    .withColumn("scd2_hash", row_hash(CFG["scd2_columns"]))
    .withColumn("scd1_hash", row_hash(CFG["scd1_columns"]))
    .withColumn("_processed_at", F.current_timestamp())
    .select(*schema_of(SILVER_CLEAN_DDL).fieldNames()))

valid_rows = valid.count()
quarantined_rows = input_rows - valid_rows
clean_rows = clean_df.count()
print(f"valid={valid_rows} quarantined={quarantined_rows} duplicates_removed={valid_rows - clean_rows} clean={clean_rows}")
display(clean_df.orderBy("customer_id"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Write (idempotent per batch) and apply the quality gate

# CELL ********************

overwrite_batch(quarantine_df, "silver", "customer_quarantine", "_batch_id", batch_id)
overwrite_batch(clean_df, "silver", "customer_clean", "_batch_id", batch_id)
bronze.unpersist()

metrics = {"input_rows": input_rows, "valid_rows": valid_rows, "quarantined_rows": quarantined_rows,
           "duplicates_removed": valid_rows - clean_rows, "clean_rows": clean_rows}
reject_ratio = quarantined_rows / input_rows if input_rows else 0.0
if reject_ratio > CFG["max_reject_ratio"]:
    msg = f"Quality gate failed: {reject_ratio:.0%} of rows quarantined (limit {CFG['max_reject_ratio']:.0%})"
    log_run(batch_id, "silver_cleanse", "FAILED", started_at, metrics, msg)
    raise ValueError(msg)

log_run(batch_id, "silver_cleanse", "SUCCEEDED", started_at, metrics)
exit_json({"status": "SUCCEEDED", "batch_id": batch_id, **metrics})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
