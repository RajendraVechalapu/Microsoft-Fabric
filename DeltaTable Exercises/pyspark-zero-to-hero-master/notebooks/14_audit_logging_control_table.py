# Databricks notebook source
# MAGIC %md
# MAGIC # 14 - Audit Logging and Control Tables
# MAGIC Audit rows answer what ran, when, how much data moved, and whether it failed.

# COMMAND ----------

from datetime import datetime
from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")
spark.sql("""
    CREATE TABLE IF NOT EXISTS learning_de.pipeline_audit (
        pipeline_name STRING,
        batch_id STRING,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        status STRING,
        rows_read BIGINT,
        rows_written BIGINT,
        error_message STRING
    ) USING DELTA
""")

pipeline_name = "customer_demo_pipeline"
batch_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
start_time = datetime.utcnow()
rows_read = 0
rows_written = 0

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run work inside try/except and always write an audit row

# COMMAND ----------

try:
    source = spark.range(1, 11).withColumnRenamed("id", "record_id")
    rows_read = source.count()

    spark.sql("DROP TABLE IF EXISTS learning_de.audit_demo_output")
    source.withColumn("processed_at", F.current_timestamp()).write.format(
        "delta"
    ).saveAsTable("learning_de.audit_demo_output")

    rows_written = spark.table("learning_de.audit_demo_output").count()
    status = "SUCCESS"
    error_message = None
except Exception as error:
    status = "FAILED"
    error_message = str(error)[:4000]
    raise
finally:
    end_time = datetime.utcnow()
    audit_row = spark.createDataFrame([(
        pipeline_name,
        batch_id,
        start_time,
        end_time,
        status,
        rows_read,
        rows_written,
        error_message,
    )], """
        pipeline_name string, batch_id string, start_time timestamp,
        end_time timestamp, status string, rows_read long,
        rows_written long, error_message string
    """)
    audit_row.write.format("delta").mode("append").saveAsTable(
        "learning_de.pipeline_audit"
    )

spark.table("learning_de.pipeline_audit").orderBy(F.col("start_time").desc()).show(
    truncate=False
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Production monitoring
# MAGIC Emit one audit row per attempt, use a unique batch ID, retain failure text,
# MAGIC monitor duration and row-count anomalies, and alert on failed or stale runs.
