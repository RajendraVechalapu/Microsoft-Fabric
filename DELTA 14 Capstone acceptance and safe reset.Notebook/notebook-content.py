# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Prove the end-to-end learning outcomes
# Prerequisites: all core lessons through 13. Expected after 09: active orders 5, revenue 500,
# silver rows 6 (including deleted 103), bronze snapshots 8, empty pending, Jan 6 watermark.
# Checks assume no optional quality experiments or additional pipeline mutations.
# 
# Capstone: add two new orders, update an existing order onto a different business date, and soft-delete
# another. Predict counts/revenue BEFORE execution, run the pipeline, and reconcile Power BI.
# Then inject a post-silver failure and recover from the SAME pending batch.
# Explain extraction ordering, idempotent MERGE, tombstones, CDF retention and reporting freshness.
# 
# **Safe reset is optional and disabled.** Pause pipelines/MLV schedules, remove optional dependent views,
# and ensure no consumers are running. Reset removes only the dedicated delta_lab_* schemas.
# Landing files are retained. After reset run 00 onward; fixed batch folders will be overwritten on extract.
# No existing mlv_learn or business tables are included.

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
assert sql('SELECT COUNT(*) FROM delta_lab_gold.fact_order').first()[0] == 5
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('500.00')
assert sql('SELECT COUNT(*) FROM delta_lab_silver.orders').first()[0] == 6
assert sql('SELECT COUNT(*) FROM delta_lab_bronze.orders').first()[0] == 8
assert sql('SELECT COUNT(*) FROM delta_lab_ops.pending').first()[0] == 0
assert sql('SELECT order_id FROM delta_lab_silver.orders GROUP BY order_id HAVING COUNT(*)>1').count() == 0
assert sql("SELECT watermark = TIMESTAMP '2026-01-06 10:00:00' FROM delta_lab_ops.watermarks WHERE entity='orders'").first()[0]
assert sql('SELECT SUM(revenue) FROM delta_lab_gold.daily_sales').first()[0] == Decimal('500.00')
assert sql("""SELECT COUNT(*) FROM delta_lab_silver.orders s
 LEFT ANTI JOIN delta_lab_source.customers c ON c.customer_id=s.customer_id""").first()[0] == 0
show('SELECT * FROM delta_lab_ops.watermarks')
print('Core lab acceptance checks passed')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Explicit opt-in only. Run all keeps cleanup disabled.
RESET_TRAINING_SCHEMAS = False
if RESET_TRAINING_SCHEMAS:
    for schema in ['gold','silver','bronze','ops','source']:
        sql('DROP SCHEMA IF EXISTS delta_lab_' + schema + ' CASCADE')
    print('Training tables reset; rerun 00 onward. Landing files retained.')
else:
    print('Reset disabled; no tables removed')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
