# Databricks notebook source
# MAGIC %md
# MAGIC # 08 - Delta MERGE Upsert
# MAGIC MERGE atomically updates matched rows and inserts unmatched rows.

# COMMAND ----------

from delta.tables import DeltaTable
from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")
spark.sql("DROP TABLE IF EXISTS learning_de.customer_merge_target")

target = spark.createDataFrame([
    (1, "Aroha", "aroha@old.example", "NZ"),
    (2, "Ben", "ben@example.com", "AU"),
], ["customer_id", "customer_name", "email", "country"])

target.write.format("delta").saveAsTable("learning_de.customer_merge_target")

# Customer 1 changed email; customer 3 is new.
updates = spark.createDataFrame([
    (1, "Aroha", "aroha@new.example", "NZ"),
    (3, "Chen", "chen@example.com", "NZ"),
], ["customer_id", "customer_name", "email", "country"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Perform the upsert

# COMMAND ----------

delta_target = DeltaTable.forName(spark, "learning_de.customer_merge_target")

(
    delta_target.alias("target")
    .merge(updates.alias("source"), "target.customer_id = source.customer_id")
    .whenMatchedUpdate(set={
        "customer_name": "source.customer_name",
        "email": "source.email",
        "country": "source.country",
    })
    .whenNotMatchedInsertAll()
    .execute()
)

spark.table("learning_de.customer_merge_target").orderBy("customer_id").show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC - The merge condition identifies the business key.
# MAGIC - Matched clauses update or delete existing rows.
# MAGIC - Not-matched clauses insert new rows.
# MAGIC - Deduplicate source keys before MERGE; multiple source rows matching one
# MAGIC   target row can make the operation ambiguous.
