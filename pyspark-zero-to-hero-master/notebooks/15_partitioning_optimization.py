# Databricks notebook source
# MAGIC %md
# MAGIC # 15 - Partitioning and Optimization
# MAGIC Good physical layout reduces files and data scanned; poor partitioning does
# MAGIC the opposite.

# COMMAND ----------

from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")
spark.sql("DROP TABLE IF EXISTS learning_de.partitioned_sales")

sales = (
    spark.range(1, 10001)
    .withColumnRenamed("id", "sale_id")
    .withColumn("sale_date", F.date_add(F.lit("2026-01-01"), (F.col("sale_id") % 30).cast("int")))
    .withColumn("customer_id", (F.col("sale_id") % 500).cast("long"))
    .withColumn("amount", F.round((F.rand(seed=42) * 500) + 1, 2))
)

sales.write.format("delta").mode("overwrite").partitionBy("sale_date").saveAsTable(
    "learning_de.partitioned_sales"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Partition pruning
# MAGIC A filter on the partition column lets Spark skip unrelated directories.

# COMMAND ----------

filtered = spark.table("learning_de.partitioned_sales").filter(
    F.col("sale_date") == F.lit("2026-01-15")
)
filtered.explain(mode="formatted")
filtered.show(5)

# COMMAND ----------

# MAGIC %md
# MAGIC ## OPTIMIZE and ZORDER
# MAGIC Availability and syntax can vary by Databricks edition and table features.

# COMMAND ----------

try:
    spark.sql("""
        OPTIMIZE learning_de.partitioned_sales
        ZORDER BY (customer_id)
    """)
    print("OPTIMIZE completed.")
except Exception as error:
    print(f"OPTIMIZE was not available in this environment: {error}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Performance tuning notes
# MAGIC - Partition low-to-medium cardinality columns commonly used in filters.
# MAGIC - Avoid tiny partitions and high-cardinality keys such as customer_id.
# MAGIC - Compact small files and use data clustering/ZORDER for selective filters.
# MAGIC - Measure query plans and scan metrics before and after tuning.
