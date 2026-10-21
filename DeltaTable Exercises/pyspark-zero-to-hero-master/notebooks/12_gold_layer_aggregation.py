# Databricks notebook source
# MAGIC %md
# MAGIC # 12 - Gold Layer Aggregation
# MAGIC Gold tables expose stable, business-ready metrics.

# COMMAND ----------

from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")

if not spark.catalog.tableExists("learning_de.silver_sales"):
    raise RuntimeError("Run 11_data_quality_checks.py before this notebook.")

sales = spark.table("learning_de.silver_sales")

# The DQ notebook does not carry names, so this small dimension enriches the facts.
customers = spark.createDataFrame([
    (101, "Aroha"),
    (102, "Ben"),
    (103, "Chen"),
    (105, "Eli"),
], ["customer_id", "customer_name"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Customer sales summary

# COMMAND ----------

customer_summary = (
    sales.join(customers, "customer_id", "left")
    .groupBy("customer_id", "customer_name")
    .agg(
        F.countDistinct("sale_id").alias("sale_count"),
        F.round(F.sum("amount"), 2).alias("total_sales"),
        F.round(F.avg("amount"), 2).alias("average_sale"),
    )
)

spark.sql("DROP TABLE IF EXISTS learning_de.gold_customer_summary")
customer_summary.write.format("delta").saveAsTable(
    "learning_de.gold_customer_summary"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Daily sales summary

# COMMAND ----------

daily_summary = sales.groupBy("sale_date").agg(
    F.countDistinct("sale_id").alias("sale_count"),
    F.round(F.sum("amount"), 2).alias("total_sales"),
)

spark.sql("DROP TABLE IF EXISTS learning_de.gold_daily_sales")
daily_summary.write.format("delta").saveAsTable("learning_de.gold_daily_sales")

spark.table("learning_de.gold_customer_summary").show()
spark.table("learning_de.gold_daily_sales").show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC Gold models translate technical records into reusable business definitions.
# MAGIC Their grain, dimensions, measures, refresh schedule, and owners should be clear.
