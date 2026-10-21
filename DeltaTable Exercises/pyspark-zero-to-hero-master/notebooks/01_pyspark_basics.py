# Databricks notebook source

# MAGIC %md
# MAGIC # 01 - PySpark Basics
# MAGIC Learn how Spark creates distributed DataFrames and applies transformations.

# COMMAND ----------

# MAGIC %md
# MAGIC ## SparkSession
# MAGIC `spark` is created automatically by Databricks. It is the entry point for
# MAGIC DataFrame, SQL, catalog, and streaming operations.

# COMMAND ----------

spark.sql("""
    SELECT
        current_user() AS databricks_user,
        current_catalog() AS current_catalog,
        current_schema() AS current_schema
""").show(truncate=False)

# COMMAND ----------

a=1+2

# COMMAND ----------

spark

# COMMAND ----------

print(f"Spark version: {spark.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create a DataFrame with an explicit schema
# MAGIC Production pipelines prefer explicit schemas because inference can be slow
# MAGIC and inconsistent.

# COMMAND ----------

# Benifits of declaring explicit schema:
# 1. Performance: Spark can optimize query execution when it knows the schema in advance.
# 2. Data Quality: It helps in ensuring data quality by enforcing data types and constraints



from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

customer_schema = StructType([
    StructField("customer_id", IntegerType(), False),
    StructField("name", StringType(), False),
    StructField("country", StringType(), True),
    StructField("age", IntegerType(), True),
    StructField("lifetime_value", DoubleType(), True),
])

customer_data = [
    (1, "Aroha", "NZ", 29, 1250.50),
    (2, "Ben", "AU", 41, 820.00),
    (3, "Chen", "NZ", 35, 2100.75),
    (4, "Devi", None, 24, 300.00),
]

#Improve below code latest databrics version

customers_df = spark.createDataFrame(customer_data, schema=customer_schema)
customers_df.show()
customers_df.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Select and filter
# MAGIC Transformations are lazy: Spark builds a plan and executes it only when an
# MAGIC action such as `show`, `count`, or `write` is called.

# COMMAND ----------

selected_df = customers_df.select("customer_id", "name", "country")
selected_df.show()

filtered_df = customers_df.filter((F.col("country") == "NZ") & (F.col("age") >= 30))
filtered_df.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add, replace, drop, and rename columns

# COMMAND ----------

enriched_df = (
    customers_df
    .withColumn("value_band", F.when(F.col("lifetime_value") >= 1000, "high").otherwise("standard"))
    # alias not work because withColumn does not support aliasing directly. Instead, we can use the withColumn to create a new column and then select it with an alias if needed.
    .withColumn("name_upper", F.upper(F.col("name")))

    # Rename 'lifetime_value' to 'customer_value' for better clarity in downstream analysis and reporting. This makes it more intuitive to understand that this column represents the value associated with the customer.
    .withColumnRenamed("lifetime_value", "customer_value")
    .drop("age")
    # Handle missing values in 'country' column by replacing nulls with 'Unknown'
    # This ensures that we have a consistent value for missing countries, which can be useful for analysis and reporting.
    # The coalesce function is used to return the first non-null value among its arguments. If 'country' is null, it will return 'Unknown'.
    # Lit means literal value, which is used here to provide a default value for missing countries.
    .withColumn("country", F.coalesce(F.col("country"), F.lit("Unknown")))
)
enriched_df.show()
enriched_df.printSchema()

# COMMAND ----------

# assing new columns all with aliases from enriched_df
final_df = enriched_df.select(
    F.col("customer_id").alias("id"),
    F.col("name_upper").alias("name"),
    F.col("country").alias("country"),
    F.col("customer_value").alias("value"),
    F.col("value_band").alias("value band")
).show()


# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC - DataFrames are immutable; every transformation returns a new DataFrame.
# MAGIC - Transformations are lazy, while actions trigger execution.
# MAGIC - A schema contains column names, data types, and nullability.
# MAGIC - Use `col()` expressions instead of Python logic for distributed execution.
