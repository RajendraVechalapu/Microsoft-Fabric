# Databricks notebook source
# MAGIC %md
# MAGIC # 04 - Bronze Layer Ingestion
# MAGIC Bronze preserves source records and adds operational metadata.

# COMMAND ----------

from datetime import datetime
from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")

# A new batch_id makes every rerun look like a new ingestion batch.
batch_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")

raw_customers = spark.createDataFrame([
    ("1", " Aroha ", "aroha@example.com", "NZ", "2026-01-01 10:00:00"),
    ("2", "Ben", "BEN@example.com", "AU", "2026-01-01 10:05:00"),
    ("2", "Ben", "BEN@example.com", "AU", "2026-01-01 10:05:00"),
    ("3", None, "chen@example.com", "NZ", "bad-timestamp"),
], ["customer_id", "customer_name", "email", "country", "source_updated_at"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add ingestion metadata

# COMMAND ----------

bronze_batch = (
    raw_customers
    .withColumn("ingestion_timestamp", F.current_timestamp())
    .withColumn("source_system", F.lit("demo_crm"))
    .withColumn("batch_id", F.lit(batch_id))
)

bronze_batch.write.format("delta").mode("append").saveAsTable(
    "learning_de.bronze_customers"
)

spark.table("learning_de.bronze_customers").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Why Bronze is append-only
# MAGIC - It preserves evidence of exactly what arrived.
# MAGIC - Bad data can be repaired downstream without asking the source to resend.
# MAGIC - Metadata supports replay, auditing, and incident investigation.
# MAGIC - Production ingestion should use an idempotency strategy so retrying the
# MAGIC   same batch does not duplicate data accidentally.
