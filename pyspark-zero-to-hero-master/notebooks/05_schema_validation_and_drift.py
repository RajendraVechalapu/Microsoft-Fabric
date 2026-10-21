# Databricks notebook source
# MAGIC %md
# MAGIC # 05 - Schema Validation and Drift
# MAGIC A schema contract prevents silent corruption when a source changes.

# COMMAND ----------

from pyspark.sql.types import IntegerType, StringType, StructField, StructType

expected_schema = StructType([
    StructField("customer_id", IntegerType(), False),
    StructField("customer_name", StringType(), True),
    StructField("email", StringType(), True),
    StructField("country", StringType(), True),
])

# This incoming example contains an extra column and changes customer_id to string.
incoming = spark.createDataFrame([
    ("1", "Aroha", "aroha@example.com", "NZ", "unexpected"),
], ["customer_id", "customer_name", "email", "country", "new_source_column"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Compare actual and expected schemas

# COMMAND ----------

def validate_schema(actual_schema, required_schema):
    actual = {field.name: field.dataType.simpleString() for field in actual_schema}
    expected = {field.name: field.dataType.simpleString() for field in required_schema}

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(
        f"{name}: expected {expected[name]}, got {actual[name]}"
        for name in set(actual).intersection(expected)
        if actual[name] != expected[name]
    )

    problems = []
    if missing:
        problems.append(f"missing columns={missing}")
    if extra:
        problems.append(f"extra columns={extra}")
    if changed:
        problems.append(f"changed types={changed}")

    if problems:
        raise ValueError("Schema validation failed: " + "; ".join(problems))


try:
    validate_schema(incoming.schema, expected_schema)
except ValueError as error:
    print(error)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validate a correct DataFrame

# COMMAND ----------

valid_incoming = spark.createDataFrame([
    (1, "Aroha", "aroha@example.com", "NZ"),
], expected_schema)
validate_schema(valid_incoming.schema, expected_schema)
print("Schema validation passed.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC - Missing columns break downstream logic.
# MAGIC - Extra or renamed columns may signal an unapproved source change.
# MAGIC - Type changes can create nulls during casts or alter business meaning.
# MAGIC - Failing loudly at the boundary is usually safer than silently accepting drift.
