# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Build a deterministic source and durable control state
# Prerequisite: 00. Source tables simulate an operational system; they are not bronze.
# `order_id` is the business key, `order_date` is the business date, `modified_at` is extraction time.
# Use DECIMAL for money and UTC timestamps to avoid rounding and timezone surprises.
# Initial seed inserts missing keys only: rerunning does not undo later source changes.
# Expected first run: 3 orders, revenue 600, watermark 1900-01-01.

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
sql("""CREATE TABLE IF NOT EXISTS delta_lab_source.orders (
 order_id INT, customer_id INT, order_date DATE, amount DECIMAL(12,2),
 modified_at TIMESTAMP, is_deleted BOOLEAN) USING DELTA
 TBLPROPERTIES ('delta.enableChangeDataFeed'='true')""")
sql("""MERGE INTO delta_lab_source.orders t USING (
 SELECT 101 order_id, 1 customer_id, DATE '2026-01-01' order_date,
 CAST(100 AS DECIMAL(12,2)) amount, TIMESTAMP '2026-01-01 10:00:00' modified_at, false is_deleted
 UNION ALL SELECT 102,2,DATE '2026-01-01',200,TIMESTAMP '2026-01-01 10:00:00',false
 UNION ALL SELECT 103,1,DATE '2026-01-02',300,TIMESTAMP '2026-01-01 10:00:00',false
) s ON t.order_id=s.order_id WHEN NOT MATCHED THEN INSERT *""")
sql("""CREATE TABLE IF NOT EXISTS delta_lab_source.customers
 (customer_id INT, customer_name STRING, city STRING) USING DELTA""")
sql("""MERGE INTO delta_lab_source.customers t USING (
 SELECT 1 customer_id, 'Aroha' customer_name, 'Auckland' city
 UNION ALL SELECT 2,'Priya','Wellington') s ON t.customer_id=s.customer_id
 WHEN NOT MATCHED THEN INSERT *""")
sql("""CREATE TABLE IF NOT EXISTS delta_lab_ops.watermarks
 (entity STRING, watermark TIMESTAMP) USING DELTA""")
sql("""MERGE INTO delta_lab_ops.watermarks t USING
 (SELECT 'orders' entity, TIMESTAMP '1900-01-01 00:00:00' watermark) s
 ON t.entity=s.entity WHEN NOT MATCHED THEN INSERT *""")
sql("""CREATE TABLE IF NOT EXISTS delta_lab_ops.pending
 (entity STRING, batch_id STRING, old_watermark TIMESTAMP, upper_watermark TIMESTAMP, path STRING) USING DELTA""")
sql("""CREATE TABLE IF NOT EXISTS delta_lab_bronze.orders
 (order_id INT, customer_id INT, order_date DATE, amount DECIMAL(12,2), modified_at TIMESTAMP,
 is_deleted BOOLEAN, batch_id STRING, ingested_at TIMESTAMP) USING DELTA""")
sql("""CREATE TABLE IF NOT EXISTS delta_lab_silver.orders
 (order_id INT, customer_id INT, order_date DATE, amount DECIMAL(12,2), modified_at TIMESTAMP,
 is_deleted BOOLEAN) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true')""")
sql("""CREATE TABLE IF NOT EXISTS delta_lab_ops.quarantine
 (customer_id INT, order_id INT, order_date DATE, amount DECIMAL(12,2), modified_at TIMESTAMP,
 is_deleted BOOLEAN, batch_id STRING, ingested_at TIMESTAMP, reason STRING) USING DELTA""")
show('SELECT * FROM delta_lab_source.orders ORDER BY order_id')
show('SELECT * FROM delta_lab_ops.watermarks')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
