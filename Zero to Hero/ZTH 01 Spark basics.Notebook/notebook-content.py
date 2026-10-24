# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # PySpark zero to hero: 01 Spark basics
# **What you learn:** create a DataFrame, inspect its schema, filter, add columns and aggregate.
# **Why:** every later lesson builds on these DataFrame operations.
#
# This notebook uses in-memory sample data only, so no Lakehouse needs to be attached.
# Run the cells in order.

# CELL ********************

from pyspark.sql import functions as F
# WHAT: confirm the Spark session that Fabric provides is ready.
print("Spark version:", spark.version)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Create a DataFrame
# A DataFrame is a distributed table with named, typed columns.

# CELL ********************

data = [
    (1, "Alice", "Sales", 5200),
    (2, "Bob", "Sales", 4800),
    (3, "Chitra", "Engineering", 7300),
    (4, "Dev", "Engineering", 6900),
    (5, "Elena", "Marketing", 4500),
]
df = spark.createDataFrame(data, ["emp_id", "name", "department", "salary"])
df.printSchema()
display(df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Filter and add columns
# Transformations are lazy: Spark only runs them when an action such as display() is called.

# CELL ********************

high_earners = (
    df.filter(F.col("salary") > 5000)
      .withColumn("bonus", F.round(F.col("salary") * 0.10, 2))
)
display(high_earners)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Aggregate
# Group rows by department and compute summary statistics.

# CELL ********************

by_dept = (
    df.groupBy("department")
      .agg(F.count("*").alias("headcount"), F.avg("salary").alias("avg_salary"))
      .orderBy(F.desc("avg_salary"))
)
display(by_dept)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Spark SQL
# Register the DataFrame as a temporary view to query it with SQL.

# CELL ********************

df.createOrReplaceTempView("employees")
display(spark.sql("SELECT department, MAX(salary) AS max_salary FROM employees GROUP BY department"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# **Exercise:** add a column `salary_band` that is "High" when salary >= 6000 and "Standard" otherwise,
# then count employees per band.
