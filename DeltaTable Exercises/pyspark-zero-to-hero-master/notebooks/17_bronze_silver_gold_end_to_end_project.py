# Databricks notebook source
# MAGIC %md
# MAGIC # 17 - End-to-End Bronze, Silver, Gold Project
# MAGIC This standalone mini pipeline ingests orders, validates schema, applies DQ,
# MAGIC produces customer metrics, and writes an audit record.

# COMMAND ----------

from datetime import datetime
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType
from pyspark.sql.window import Window

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")

for table_name in [
    "e2e_bronze_orders",
    "e2e_silver_orders",
    "e2e_error_orders",
    "e2e_gold_customer_sales",
]:
    spark.sql(f"DROP TABLE IF EXISTS learning_de.{table_name}")

spark.sql("""
    CREATE TABLE IF NOT EXISTS learning_de.pipeline_audit (
        pipeline_name STRING, batch_id STRING, start_time TIMESTAMP,
        end_time TIMESTAMP, status STRING, rows_read BIGINT,
        rows_written BIGINT, error_message STRING
    ) USING DELTA
""")

pipeline_name = "e2e_orders_pipeline"
batch_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
start_time = datetime.utcnow()
rows_read = 0
rows_written = 0

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Source to Bronze

# COMMAND ----------

raw_schema = StructType([
    StructField("order_id", StringType(), True),
    StructField("customer_id", StringType(), True),
    StructField("customer_name", StringType(), True),
    StructField("order_date", StringType(), True),
    StructField("amount", StringType(), True),
])

raw_orders = spark.createDataFrame([
    ("1001", "1", " Aroha ", "2026-03-01", "120.50"),
    ("1002", "1", "Aroha", "2026-03-02", "80.00"),
    ("1002", "1", "Aroha", "2026-03-02", "80.00"),
    ("1003", "2", "Ben", "bad-date", "45.00"),
    ("1004", "3", None, "2026-03-03", "-5.00"),
    ("1005", "3", "Chen", "2026-03-03", "210.00"),
], raw_schema)

bronze = (
    raw_orders
    .withColumn("ingestion_timestamp", F.current_timestamp())
    .withColumn("source_system", F.lit("demo_order_api"))
    .withColumn("batch_id", F.lit(batch_id))
)
bronze.write.format("delta").saveAsTable("learning_de.e2e_bronze_orders")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Schema validation

# COMMAND ----------

expected_columns = {
    "order_id": "string",
    "customer_id": "string",
    "customer_name": "string",
    "order_date": "string",
    "amount": "string",
}
actual_columns = {
    field.name: field.dataType.simpleString()
    for field in raw_orders.schema
}
if actual_columns != expected_columns:
    raise ValueError(
        f"Source schema mismatch. Expected {expected_columns}; got {actual_columns}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Bronze to typed Silver candidates
# MAGIC The same guarded pipeline block also builds Gold and records audit status.

# COMMAND ----------

try:
    rows_read = bronze.count()

    typed = (
        bronze
        .withColumn("order_id", F.col("order_id").cast("long"))
        .withColumn("customer_id", F.col("customer_id").cast("long"))
        .withColumn("customer_name", F.trim("customer_name"))
        .withColumn("order_date", F.to_date("order_date"))
        .withColumn("amount", F.col("amount").cast("double"))
    )

    # Remove exact source duplicates before evaluating uniqueness.
    dedupe_window = Window.partitionBy("order_id").orderBy(
        F.col("ingestion_timestamp").desc()
    )
    typed = typed.withColumn("row_number", F.row_number().over(dedupe_window))

    checked = typed.withColumn(
        "error_reasons",
        F.array_compact(F.array(
            F.when(F.col("order_id").isNull(), F.lit("invalid order_id")),
            F.when(F.col("customer_id").isNull(), F.lit("invalid customer_id")),
            F.when(F.col("customer_name").isNull(), F.lit("missing customer_name")),
            F.when(F.col("order_date").isNull(), F.lit("invalid order_date")),
            F.when(F.col("amount").isNull() | (F.col("amount") <= 0), F.lit("invalid amount")),
            F.when(F.col("row_number") > 1, F.lit("duplicate order_id")),
        )),
    )

    good = checked.filter(F.size("error_reasons") == 0).drop(
        "row_number", "error_reasons"
    )
    bad = checked.filter(F.size("error_reasons") > 0).drop("row_number")

    good.write.format("delta").saveAsTable("learning_de.e2e_silver_orders")
    bad.write.format("delta").saveAsTable("learning_de.e2e_error_orders")

    # Aggregate trusted Silver records into a customer-grain Gold table.
    gold = (
        good.groupBy("customer_id", "customer_name")
        .agg(
            F.countDistinct("order_id").alias("order_count"),
            F.round(F.sum("amount"), 2).alias("total_sales"),
            F.max("order_date").alias("latest_order_date"),
        )
    )
    gold.write.format("delta").saveAsTable(
        "learning_de.e2e_gold_customer_sales"
    )
    rows_written = good.count()
    status = "SUCCESS"
    error_message = None
except Exception as error:
    status = "FAILED"
    error_message = str(error)[:4000]
    raise
finally:
    audit = spark.createDataFrame([(
        pipeline_name, batch_id, start_time, datetime.utcnow(), status,
        rows_read, rows_written, error_message,
    )], """
        pipeline_name string, batch_id string, start_time timestamp,
        end_time timestamp, status string, rows_read long,
        rows_written long, error_message string
    """)
    audit.write.format("delta").mode("append").saveAsTable(
        "learning_de.pipeline_audit"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Inspect pipeline outputs

# COMMAND ----------

print("Bronze")
spark.table("learning_de.e2e_bronze_orders").show(truncate=False)
print("Silver")
spark.table("learning_de.e2e_silver_orders").show(truncate=False)
print("Quarantine")
spark.table("learning_de.e2e_error_orders").show(truncate=False)
print("Gold")
spark.table("learning_de.e2e_gold_customer_sales").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview-ready summary
# MAGIC Bronze preserves raw input and metadata. Schema validation protects the
# MAGIC contract. Silver standardizes types, deduplicates, and separates invalid
# MAGIC data. Gold publishes business metrics. Audit logging records operational
# MAGIC outcomes. In production, orchestrate these stages as separate dependent tasks.
