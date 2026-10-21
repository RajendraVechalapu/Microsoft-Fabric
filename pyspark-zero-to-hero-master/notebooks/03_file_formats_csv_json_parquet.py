# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - CSV, JSON, and Parquet
# MAGIC Compare row-oriented text formats with a typed columnar format.

# COMMAND ----------

from pyspark.sql.types import IntegerType, StringType, StructField, StructType

schema = StructType([
    StructField("product_id", IntegerType(), False),
    StructField("product_name", StringType(), False),
    StructField("category", StringType(), True),
])
products = spark.createDataFrame([
    (1, "Keyboard", "hardware"),
    (2, "Monitor", "hardware"),
    (3, "Notebook", "stationery"),
], schema)

base_path = "dbfs:/tmp/learning_de/file_formats"
dbutils.fs.rm(base_path, True)

# COMMAND ----------

# MAGIC %md
# MAGIC ## CSV
# MAGIC CSV is human-readable but has no native types and needs careful delimiter,
# MAGIC quoting, header, and null handling.

# COMMAND ----------

csv_path = f"{base_path}/csv"
products.write.mode("overwrite").option("header", True).csv(csv_path)
spark.read.schema(schema).option("header", True).csv(csv_path).show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## JSON
# MAGIC JSON supports nested structures but is verbose and expensive to parse.

# COMMAND ----------

json_path = f"{base_path}/json"
products.write.mode("overwrite").json(json_path)
spark.read.schema(schema).json(json_path).show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parquet
# MAGIC Parquet stores schema and statistics, compresses well, and reads only the
# MAGIC columns required by a query.

# COMMAND ----------

parquet_path = f"{base_path}/parquet"
products.write.mode("overwrite").parquet(parquet_path)
parquet_df = spark.read.parquet(parquet_path)
parquet_df.show()
parquet_df.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Why data engineers prefer Parquet
# MAGIC - Column pruning reduces I/O.
# MAGIC - Predicate pushdown can skip irrelevant data.
# MAGIC - Encodings and compression reduce storage.
# MAGIC - Types travel with the data.
# MAGIC - Delta Lake uses Parquet data files plus a transaction log.
