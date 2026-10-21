# Databricks notebook source
# MAGIC %md
# MAGIC # 11 - Data Quality Checks
# MAGIC Keep valid records flowing while preserving invalid records for investigation.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")

sales = spark.createDataFrame([
    (1, 101, "2026-01-10", 120.00),
    (2, 102, "2026-01-11", -10.00),
    (2, 103, "2026-01-12", 50.00),
    (4, None, "not-a-date", 75.00),
    (5, 105, "2026-01-13", None),
], ["sale_id", "customer_id", "sale_date_raw", "amount"])

typed = sales.withColumn("sale_date", F.to_date("sale_date_raw"))

# Identify duplicate sale IDs with a window count.
duplicate_count = F.count("*").over(
    Window.partitionBy("sale_id")
)

checked = (
    typed
    .withColumn("duplicate_count", duplicate_count)
    .withColumn(
        "error_reasons",
        F.array_compact(F.array(
            F.when(F.col("sale_id").isNull(), F.lit("sale_id is null")),
            F.when(F.col("customer_id").isNull(), F.lit("customer_id is null")),
            F.when(F.col("duplicate_count") > 1, F.lit("sale_id is not unique")),
            F.when(F.col("sale_date").isNull(), F.lit("sale_date is invalid")),
            F.when(F.col("amount").isNull() | (F.col("amount") <= 0), F.lit("amount must be positive")),
        )),
    )
)

good_records = checked.filter(F.size("error_reasons") == 0).drop(
    "sale_date_raw", "duplicate_count", "error_reasons"
)
bad_records = checked.filter(F.size("error_reasons") > 0).drop("duplicate_count")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write trusted and quarantined data

# COMMAND ----------

spark.sql("DROP TABLE IF EXISTS learning_de.silver_sales")
spark.sql("DROP TABLE IF EXISTS learning_de.error_sales")

good_records.write.format("delta").saveAsTable("learning_de.silver_sales")
bad_records.write.format("delta").saveAsTable("learning_de.error_sales")

print("Good records")
spark.table("learning_de.silver_sales").show(truncate=False)
print("Quarantined records")
spark.table("learning_de.error_sales").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## DQ design
# MAGIC - Attach rule failures to each record instead of only returning a count.
# MAGIC - Quarantine supports debugging and later repair.
# MAGIC - Monitor rule pass rates and stop the pipeline when critical thresholds fail.
