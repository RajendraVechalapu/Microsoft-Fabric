# Databricks notebook source
# MAGIC %md
# MAGIC # 16 - Delta Time Travel and Restore
# MAGIC The Delta transaction log makes previous consistent table versions queryable.

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")
spark.sql("DROP TABLE IF EXISTS learning_de.time_travel_demo")

spark.createDataFrame([
    (1, "original"),
    (2, "original"),
], ["id", "value"]).write.format("delta").saveAsTable(
    "learning_de.time_travel_demo"
)

spark.sql("UPDATE learning_de.time_travel_demo SET value = 'updated' WHERE id = 1")
spark.sql("INSERT INTO learning_de.time_travel_demo VALUES (3, 'new')")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Inspect history and query a previous version

# COMMAND ----------

history = spark.sql("DESCRIBE HISTORY learning_de.time_travel_demo")
history.select("version", "timestamp", "operation").show(truncate=False)

print("Current version")
spark.table("learning_de.time_travel_demo").orderBy("id").show()

print("Version 0")
spark.read.format("delta").option("versionAsOf", 0).table(
    "learning_de.time_travel_demo"
).orderBy("id").show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Restore
# MAGIC RESTORE creates a new version whose contents match the chosen old version.

# COMMAND ----------

try:
    spark.sql("RESTORE TABLE learning_de.time_travel_demo TO VERSION AS OF 0").show()
    spark.table("learning_de.time_travel_demo").orderBy("id").show()
except Exception as error:
    print(f"RESTORE was not available in this environment: {error}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC Time travel supports debugging, reproducibility, rollback, and audit analysis.
# MAGIC Old versions depend on retained files; VACUUM can remove files needed by
# MAGIC versions outside the configured retention period.
