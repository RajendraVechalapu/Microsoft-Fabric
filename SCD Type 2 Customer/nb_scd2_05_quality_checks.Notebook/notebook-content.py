# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 05 - Quality checks and reconciliation for `dim_customer`
# Run after every batch (the orchestrator does). Any failed check fails the notebook, which stops the pipeline
# **before** a later batch is applied on top of bad history.
#
# | Check | Why it matters |
# |---|---|
# | one current row per customer | the defining SCD2 invariant; fact lookups would duplicate otherwise |
# | unique surrogate keys | facts join on `customer_sk` |
# | `effective_from < effective_to` | no zero/negative length versions |
# | no overlapping versions per customer | point-in-time joins must return exactly one row |
# | current rows end at the high date, closed rows do not | `is_current` and dates must agree |
# | version numbers 1..n with no gaps | proves no version was lost |
# | reconciliation with silver | the current gold state equals the latest accepted silver state per customer |

# PARAMETERS CELL ********************

batch_id = ""          # only used for logging
fail_on_error = True

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
high = F.to_timestamp(F.lit(CFG["high_date"]))
dim = read_table("gold", "dim_customer").where(F.col("customer_sk") != CFG["unknown_sk"]).cache()

by_key = Window.partitionBy("customer_id").orderBy("effective_from")
ordered = (dim.withColumn("next_from", F.lead("effective_from").over(by_key))
              .withColumn("expected_version", F.row_number().over(by_key)))

checks = {
    "one_current_row_per_customer":
        dim.where("is_current").groupBy("customer_id").count().where("count > 1"),
    "unique_surrogate_key":
        read_table("gold", "dim_customer").groupBy("customer_sk").count().where("count > 1"),
    "effective_from_before_effective_to":
        dim.where(F.col("effective_from") >= F.col("effective_to")),
    "no_overlapping_versions":
        ordered.where(F.col("next_from").isNotNull() & (F.col("next_from") < F.col("effective_to"))),
    "current_rows_end_at_high_date":
        dim.where(F.col("is_current") & (F.col("effective_to") != high)),
    "closed_rows_end_before_high_date":
        dim.where(~F.col("is_current") & (F.col("effective_to") >= high)),
    "current_rows_not_deleted":
        dim.where("is_current AND is_deleted"),
    "version_numbers_contiguous":
        ordered.where(F.col("version_number") != F.col("expected_version")),
}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Reconciliation with silver
# Expected current state = for each customer, the newest silver row (by `source_updated_at`) across all batches.
# If that newest row is a delete, the customer must have no current row. Late arrivals are older by definition,
# so they never become "newest" and are correctly ignored.

# CELL ********************

newest = Window.partitionBy("customer_id").orderBy(F.desc("source_updated_at"), F.desc("_batch_id"))
expected = (read_table("silver", "customer_clean")
            .withColumn("_rn", F.row_number().over(newest)).where("_rn = 1")
            .where("op <> 'D'")
            .select("customer_id", F.col("scd2_hash").alias("exp_scd2"), F.col("scd1_hash").alias("exp_scd1")))
actual = dim.where("is_current").select("customer_id", F.col("scd2_hash").alias("act_scd2"),
                                        F.col("scd1_hash").alias("act_scd1"))
checks["reconciles_with_silver"] = (expected.join(actual, "customer_id", "full_outer")
    .where(F.col("exp_scd2").isNull() | F.col("act_scd2").isNull()
           | (F.col("exp_scd2") != F.col("act_scd2")) | (F.col("exp_scd1") != F.col("act_scd1"))))

results = []
for name, failing in checks.items():
    n = failing.count()
    results.append((name, "PASS" if n == 0 else "FAIL", n))
    if n:
        print(f"FAILED {name}: sample rows")
        display(failing.limit(20))

results_df = spark.createDataFrame(results, "check string, result string, failing_rows long")
display(results_df)
dim.unpersist()

failed = [r[0] for r in results if r[1] == "FAIL"]
summary = {"checks": len(results), "failed": failed,
           "current_customers": read_table("gold", "dim_customer").where(f"is_current AND customer_sk <> {CFG['unknown_sk']}").count(),
           "total_rows": read_table("gold", "dim_customer").count()}
log_run(batch_id or None, "quality_checks", "FAILED" if failed else "SUCCEEDED", started_at, summary)
if failed and fail_on_error:
    raise AssertionError(f"SCD2 quality checks failed: {failed}")
exit_json({"status": "FAILED" if failed else "SUCCEEDED", "batch_id": batch_id, **summary})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
