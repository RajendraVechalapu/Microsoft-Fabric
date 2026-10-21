# Databricks notebook source
# MAGIC %md
# MAGIC # 07 - Delta Table Creation
# MAGIC Delta Lake adds ACID transactions, schema enforcement, and history to Parquet.

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS learning_de")

employees = spark.createDataFrame([
    (1, "Ana", "Engineering"),
    (2, "Blake", "Finance"),
], ["employee_id", "employee_name", "department"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Managed table with `saveAsTable`
# MAGIC Databricks manages both metadata and data location.

# COMMAND ----------

spark.sql("DROP TABLE IF EXISTS learning_de.delta_managed_employees")
employees.write.format("delta").mode("overwrite").saveAsTable(
    "learning_de.delta_managed_employees"
)

spark.sql("DESCRIBE DETAIL learning_de.delta_managed_employees").show(truncate=False)
spark.sql("DESCRIBE HISTORY learning_de.delta_managed_employees").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Path-based external table
# MAGIC The table metadata points at a location chosen by the data engineer.

# COMMAND ----------

external_path = "dbfs:/tmp/learning_de/delta_external_employees"
spark.sql("DROP TABLE IF EXISTS learning_de.delta_external_employees")
dbutils.fs.rm(external_path, True)

employees.write.format("delta").mode("overwrite").save(external_path)
spark.sql(f"""
    CREATE TABLE learning_de.delta_external_employees
    USING DELTA
    LOCATION '{external_path}'
""")

spark.sql("DESCRIBE DETAIL learning_de.delta_external_employees").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Managed versus external
# MAGIC - Managed tables are the default for most Databricks workloads.
# MAGIC - Dropping a managed table normally removes its managed data.
# MAGIC - Dropping an external table removes metadata but leaves files at the path.
# MAGIC - Unity Catalog external locations should be governed; the DBFS path here is
# MAGIC   only for a compact learning example.
