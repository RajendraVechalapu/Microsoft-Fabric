# Databricks notebook source
# MAGIC %md
# MAGIC # 06 - Silver Layer Cleaning
# MAGIC Silver converts raw records into typed, deduplicated, trusted data.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")

if not spark.catalog.tableExists("learning_de.bronze_customers"):
    raise RuntimeError("Run 04_bronze_layer_ingestion.py before this notebook.")

bronze = spark.table("learning_de.bronze_customers")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Standardize values and types

# COMMAND ----------

standardized = (
    bronze
    .withColumn("customer_id", F.col("customer_id").cast("long"))
    .withColumn("customer_name", F.trim("customer_name"))
    .withColumn("email", F.lower(F.trim("email")))
    .withColumn("country", F.upper(F.trim("country")))
    .withColumn("source_updated_at", F.to_timestamp("source_updated_at"))
    .filter(F.col("customer_id").isNotNull())
    .filter(F.col("customer_name").isNotNull())
)

# Keep the latest record for each customer.
latest_first = Window.partitionBy("customer_id").orderBy(
    F.col("source_updated_at").desc_nulls_last(),
    F.col("ingestion_timestamp").desc(),
)

silver = (
    standardized
    .withColumn("row_number", F.row_number().over(latest_first))
    .filter(F.col("row_number") == 1)
    .drop("row_number")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the clean Silver table

# COMMAND ----------

spark.sql("DROP TABLE IF EXISTS learning_de.silver_customers")
silver.write.format("delta").mode("overwrite").saveAsTable(
    "learning_de.silver_customers"
)

spark.table("learning_de.silver_customers").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transformation logic
# MAGIC - Cast identifiers and timestamps into stable types.
# MAGIC - Trim and normalize text for reliable matching.
# MAGIC - Reject records without required business keys or names.
# MAGIC - Use a window to retain one latest record per customer.
