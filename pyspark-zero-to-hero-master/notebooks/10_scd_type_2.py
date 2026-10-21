# Databricks notebook source
# MAGIC %md
# MAGIC # 10 - Slowly Changing Dimension Type 2
# MAGIC SCD2 preserves old versions and marks exactly one row as current.

# COMMAND ----------

from datetime import date
from delta.tables import DeltaTable
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DateType, IntegerType, StringType, StructField, StructType

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")
spark.sql("DROP TABLE IF EXISTS learning_de.dim_customer_scd2")

scd2_schema = StructType([
    StructField("customer_id", IntegerType(), False),
    StructField("customer_name", StringType(), False),
    StructField("email", StringType(), True),
    StructField("address", StringType(), True),
    StructField("effective_from", DateType(), False),
    StructField("effective_to", DateType(), True),
    StructField("is_current", BooleanType(), False),
])

initial = spark.createDataFrame([
    (1, "Aroha", "old@example.com", "Auckland", date(2026, 1, 1), None, True),
], scd2_schema)
initial.write.format("delta").saveAsTable("learning_de.dim_customer_scd2")

changes = spark.createDataFrame([
    (1, "Aroha", "new@example.com", "Wellington", "2026-02-01"),
    (2, "Ben", "ben@example.com", "Sydney", "2026-02-01"),
], ["customer_id", "customer_name", "email", "address", "change_date"]).withColumn(
    "change_date", F.to_date("change_date")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Identify changed current records

# COMMAND ----------

current = spark.table("learning_de.dim_customer_scd2").filter("is_current = true")
changed = (
    changes.alias("s")
    .join(current.alias("t"), "customer_id", "left")
    .filter(
        F.col("t.customer_id").isNull()
        | (F.coalesce(F.col("s.email"), F.lit("")) != F.coalesce(F.col("t.email"), F.lit("")))
        | (F.coalesce(F.col("s.address"), F.lit("")) != F.coalesce(F.col("t.address"), F.lit("")))
    )
    .select("s.*")
)

# Close old current versions one day before the new version starts.
delta_target = DeltaTable.forName(spark, "learning_de.dim_customer_scd2")
(
    delta_target.alias("t")
    .merge(changed.alias("s"), "t.customer_id = s.customer_id AND t.is_current = true")
    .whenMatchedUpdate(set={
        "effective_to": "date_sub(s.change_date, 1)",
        "is_current": "false",
    })
    .execute()
)

# Insert a new current version for changed and new customers.
new_versions = changed.select(
    "customer_id",
    "customer_name",
    "email",
    "address",
    F.col("change_date").alias("effective_from"),
    F.lit(None).cast("date").alias("effective_to"),
    F.lit(True).alias("is_current"),
)
new_versions.write.format("delta").mode("append").saveAsTable(
    "learning_de.dim_customer_scd2"
)

spark.table("learning_de.dim_customer_scd2").orderBy(
    "customer_id", "effective_from"
).show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC - SCD2 adds a new row instead of overwriting history.
# MAGIC - `effective_from` and `effective_to` define validity.
# MAGIC - `is_current` makes current-state queries simple.
# MAGIC - Production designs also consider late-arriving changes and surrogate keys.
