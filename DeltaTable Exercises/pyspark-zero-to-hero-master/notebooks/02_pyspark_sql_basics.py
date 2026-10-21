# Databricks notebook source

# MAGIC %md
# MAGIC # 02 - PySpark SQL Basics
# MAGIC The DataFrame API and Spark SQL use the same Catalyst optimizer.

# COMMAND ----------

1+2

# COMMAND ----------

# test if it is connected to databricks serverless or not
print("Connected to Databricks Serverless!")
def test_connection():
    try:
        # Try to access a Spark property to confirm the connection
        spark_version = spark.version
        print(f"Spark version: {spark_version}")
        return True
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False

test_connection()

# COMMAND ----------

# read catelogue and list tables
catalogs = spark.catalog.listCatalogs()
for catalog in catalogs:
    print(f"Catalog: {catalog.name}")
    databases = spark.catalog.listDatabases(catalog.name)
    for database in databases:
        print(f"  Database: {database.name}")
        tables = spark.catalog.listTables(database.name)
        for table in tables:
            print(f"    Table: {table.name}")

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

# Create struct type first and then use it to create DataFrame


customer_schema = StructType([
    StructField("customer_id", IntegerType(), True),
    StructField("customer_name", StringType(), True),
    StructField("country", StringType(), True)
])

customers = spark.createDataFrame([
    (1, "Aroha", "NZ"),
    (2, "Ben", "AU"),
    (3, "Chen", "NZ"),
], customer_schema)

# Create stuct type first and then use it to create DataFrame

orders_schema = StructType([
    StructField("order_id", IntegerType(), True),
    StructField("customer_id", IntegerType(), True),
    StructField("amount", DoubleType(), True)
])

orders = spark.createDataFrame([
    (101, 1, 120.0),
    (102, 1, 80.0),
    (103, 2, 200.0),
    (104, 3, 50.0),
], orders_schema)

# COMMAND ----------

customers.show()
orders.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Temporary views
# MAGIC A temp view exists only for the current Spark session.

# COMMAND ----------

#Temp views are session-scoped and will disappear if the session that creates it terminates. Global temporary views are cross-session and remain until the Spark application terminates. They are stored in the system database `global_temp`. To reference a global temporary view, you must use the qualified name `global_temp.view_name`.
# In this case, we are creating temporary views for both `customers` and `orders` DataFrames, which allows us to run SQL queries against them using Spark SQL.
# By creating temporary views, we can leverage the power of SQL to perform complex queries, joins, aggregations, and other operations on our DataFrames as if they were tables in a traditional relational database.
# For example, after creating the temporary views, we can run a SQL query to select all customers from New Zealand (NZ) using the `customers_temp` view. This demonstrates how we can seamlessly integrate SQL queries with our Spark DataFrames for data analysis and manipulation.
# Note: If you want to create a global temporary view, you can use `createGlobalTempView` instead of `createOrReplaceTempView`. Global temporary views are accessible across different sessions and are stored in the `global_temp` database. You would reference them in SQL queries using `global_temp.view_name`.
# it stores data in memory and is faster than creating a new DataFrame for each query. It also allows us to reuse the same view across multiple queries without having to recreate it each time.

customers.createOrReplaceTempView("customers_temp")
orders.createOrReplaceTempView("orders_temp")

spark.sql("SELECT * FROM customers_temp WHERE country = 'NZ'").show()

# i want to save back into a new dataframe the result of the sql query, so i can do further transformations on it
nz_customers_df = spark.sql("SELECT * FROM customers_temp WHERE country = 'NZ'")
nz_customers_df.show()

# i want to update customer name Aroha with Rajendra
nz_customers_df = nz_customers_df.withColumn("customer_name", F.when(F.col("customer_name") == "Aroha", "Rajendra").otherwise(F.col("customer_name")))
nz_customers_df.show()



# COMMAND ----------

# MAGIC %md
# MAGIC ## DataFrame API versus SQL

# COMMAND ----------

df_result = (
    customers.join(orders, "customer_id", "inner")
    .groupBy("customer_id", "customer_name")
    .agg(
        F.count("order_id").alias("order_count"),
        F.sum("amount").alias("total_amount"),
    )
    .orderBy("customer_id")
)
df_result.show()

sql_result = spark.sql("""
    SELECT
        c.customer_id,
        c.customer_name,
        COUNT(o.order_id) AS order_count,
        SUM(o.amount) AS total_amount
    FROM customers_temp c
    INNER JOIN orders_temp o
        ON c.customer_id = o.customer_id
    GROUP BY c.customer_id, c.customer_name
    ORDER BY c.customer_id
""")
sql_result.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Explain the physical plan

# COMMAND ----------

df_result.explain(mode="formatted")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC - Temp views bridge Python transformations and SQL.
# MAGIC - Inner joins keep matching rows; left joins retain every left-side row.
# MAGIC - Grouping changes row granularity, so every selected non-aggregate column
# MAGIC   must be part of the grouping key.
# MAGIC - SQL and DataFrame code normally produce equivalent optimized plans.
