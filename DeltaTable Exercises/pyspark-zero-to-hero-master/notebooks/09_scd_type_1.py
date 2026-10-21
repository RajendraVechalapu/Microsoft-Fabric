# Databricks notebook source
# MAGIC %md
# MAGIC # 09 - Slowly Changing Dimension Type 1
# MAGIC SCD1 stores only the latest state and overwrites old attribute values.

# COMMAND ----------

from delta.tables import DeltaTable
from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")
spark.sql("DROP TABLE IF EXISTS learning_de.dim_customer_scd1")

initial = spark.createDataFrame([
    (1, "Aroha", "old@example.com", "Auckland"),
    (2, "Ben", "ben@example.com", "Sydney"),
], ["customer_id", "customer_name", "email", "address"])

(
    initial.withColumn("updated_at", F.current_timestamp())
    .write.format("delta")
    .saveAsTable("learning_de.dim_customer_scd1")
)

changes = spark.createDataFrame([
    (1, "Aroha", "new@example.com", "Wellington"),
    (3, "Chen", "chen@example.com", "Christchurch"),
], ["customer_id", "customer_name", "email", "address"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Apply SCD1

# COMMAND ----------

target = DeltaTable.forName(spark, "learning_de.dim_customer_scd1")
(
    target.alias("t")
    .merge(changes.alias("s"), "t.customer_id = s.customer_id")
    .whenMatchedUpdate(set={
        "customer_name": "s.customer_name",
        "email": "s.email",
        "address": "s.address",
        "updated_at": "current_timestamp()",
    })
    .whenNotMatchedInsert(values={
        "customer_id": "s.customer_id",
        "customer_name": "s.customer_name",
        "email": "s.email",
        "address": "s.address",
        "updated_at": "current_timestamp()",
    })
    .execute()
)

spark.table("learning_de.dim_customer_scd1").orderBy("customer_id").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## When to use SCD1
# MAGIC Use SCD1 when only current values matter, corrections should replace bad
# MAGIC values, and historical attribute analysis is not required.
