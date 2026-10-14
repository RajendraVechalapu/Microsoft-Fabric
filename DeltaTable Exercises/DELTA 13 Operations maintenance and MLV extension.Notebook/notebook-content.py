# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Inspect health and learn maintenance without deleting history
# Prerequisites: 09-12. Tiny data teaches mechanics, not performance benchmarks.
# OPTIMIZE compacts small files; a larger table and measured baseline are needed to prove a speedup.
# Avoid high-cardinality partition columns. Do not partition this handful of orders.
# VACUUM deletes obsolete files: it can break old time travel and CDF readers beyond retention.
# We show DRY RUN only. Do not disable retention checks or use zero retention in this course.
# 
# **MLV extension:** use your existing MLV course with delta_lab_silver.orders as a NEW source.
# Create an isolated active-orders view and daily aggregate, exclude is_deleted, and add both to a
# managed refresh schedule. Verify their refresh results after a correction. Use distinct names and
# do not replace existing MLV course objects. Compare engine-reported refresh strategy with the explicit
# notebook pipeline; CDF enablement does not promise every definition/change is incrementally refreshed.
# 
# Exercise: describe the retention period needed for your slowest downstream consumer and recovery window.
# Stop schedules when finished; maintenance and refresh consume Fabric capacity.

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
show('DESCRIBE DETAIL delta_lab_bronze.orders')
show('DESCRIBE HISTORY delta_lab_silver.orders')
show('SELECT * FROM delta_lab_ops.run_audit ORDER BY started_at DESC')
show('SELECT * FROM delta_lab_ops.quarantine')
show('EXPLAIN FORMATTED SELECT order_date, SUM(amount) FROM delta_lab_gold.fact_order GROUP BY order_date')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# WHAT: compact this dedicated training table. WHY: reduce many tiny file reads.
sql('OPTIMIZE delta_lab_bronze.orders')
show('DESCRIBE DETAIL delta_lab_bronze.orders')
# DRY RUN lists candidates and does not remove files.
show('VACUUM delta_lab_bronze.orders RETAIN 168 HOURS DRY RUN')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
