# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Fabric Delta Lake: end-to-end learning lab
# **What you build:** a reproducible sales pipeline from source through bronze, silver, gold and Power BI.
# **Why:** learning Delta syntax alone does not teach extraction, retries, deletes or serving.
# 
# Read DELTA-LEARNING.md first. Sync these items through workspace Git, then attach EVERY
# notebook to the same schema-enabled training Lakehouse. No workspace identifiers are embedded.
# Use Fabric Spark/PySpark, not the read-only Lakehouse SQL analytics endpoint.
# Run 00-14 in order, cell by cell. Stop at UI instructions and intentional failure cells.
# This course only writes delta_lab_* schemas and Files/delta_lab. Source is simulated locally;
# lesson 11 explains replacement with a real Fabric Data Factory source connector.
# Prerequisites: Fabric capacity, notebook/table write permission, schemas enabled, Power BI permissions.
# Exercise: explain source change time, business event time, ingestion time and report refresh time.

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from decimal import Decimal
import uuid
spark.conf.set("spark.sql.session.timeZone", "UTC")
# WHAT: all tables use dedicated training schemas in the attached default Lakehouse.
# WHY: isolation makes it possible to experiment without changing your MLV course.
def sql(query):
    return spark.sql(query)
def show(query):
    display(sql(query))
show('SELECT current_database() AS attached_database, current_timestamp() AS session_time')
for schema in ['source','bronze','silver','gold','ops']:
    sql('CREATE SCHEMA IF NOT EXISTS delta_lab_' + schema)
show('SHOW SCHEMAS')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
