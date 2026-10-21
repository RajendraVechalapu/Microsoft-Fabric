# Databricks notebook source
# MAGIC %md
# MAGIC # 13 - Incremental Load with a Watermark
# MAGIC Incremental loads process only records newer than the last successful point.

# COMMAND ----------

from delta.tables import DeltaTable
from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")
spark.sql("DROP TABLE IF EXISTS learning_de.incremental_customer_source")
spark.sql("DROP TABLE IF EXISTS learning_de.incremental_customer_target")
spark.sql("DROP TABLE IF EXISTS learning_de.pipeline_watermark")

source = spark.createDataFrame([
    (1, "Aroha", "2026-01-01 09:00:00"),
    (2, "Ben", "2026-01-01 10:00:00"),
    (1, "Aroha Updated", "2026-01-02 08:00:00"),
    (3, "Chen", "2026-01-02 11:00:00"),
], ["customer_id", "customer_name", "last_modified_raw"]).withColumn(
    "last_modified_date", F.to_timestamp("last_modified_raw")
).drop("last_modified_raw")

source.write.format("delta").saveAsTable("learning_de.incremental_customer_source")

watermark = spark.createDataFrame([
    ("customer_pipeline", "1900-01-01 00:00:00"),
], ["pipeline_name", "watermark_raw"]).withColumn(
    "last_successful_watermark", F.to_timestamp("watermark_raw")
).drop("watermark_raw")
watermark.write.format("delta").saveAsTable("learning_de.pipeline_watermark")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Full load versus incremental load
# MAGIC A full load reads everything. An incremental load filters on a reliable
# MAGIC change-tracking column and advances the watermark only after success.

# COMMAND ----------

last_watermark = (
    spark.table("learning_de.pipeline_watermark")
    .filter(F.col("pipeline_name") == "customer_pipeline")
    .select("last_successful_watermark")
    .first()[0]
)

incremental = (
    spark.table("learning_de.incremental_customer_source")
    .filter(F.col("last_modified_date") > F.lit(last_watermark))
)

# Keep the latest source row per key inside this batch.
from pyspark.sql.window import Window
latest = Window.partitionBy("customer_id").orderBy(F.col("last_modified_date").desc())
incremental = incremental.withColumn("rn", F.row_number().over(latest)).filter("rn = 1").drop("rn")

incremental.write.format("delta").saveAsTable("learning_de.incremental_customer_target")

new_watermark = incremental.agg(F.max("last_modified_date")).first()[0]
spark.sql(f"""
    UPDATE learning_de.pipeline_watermark
    SET last_successful_watermark = TIMESTAMP '{new_watermark}'
    WHERE pipeline_name = 'customer_pipeline'
""")

spark.table("learning_de.incremental_customer_target").show()
spark.table("learning_de.pipeline_watermark").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Control table concept
# MAGIC The control table records progress separately from business data. Production
# MAGIC pipelines often use an overlap window and deduplication to handle late data.
