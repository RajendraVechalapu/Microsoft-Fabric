# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Delta is a transaction log plus data files
# Prerequisite: 01. Parquet stores columnar data; Delta tracks which files form a committed snapshot.
# Table history shows operations, versions and metrics. A version is local to ONE table.
# Time travel reads an earlier snapshot, but requires its files to remain retained.
# Reading raw Parquet files from a Delta directory bypasses the log and can return obsolete rows.
# Exercise: locate `_delta_log` in the table's OneLake folder using Lakehouse Explorer.
# No table mutations are needed for this lesson.

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
show('DESCRIBE DETAIL delta_lab_source.orders')
show('DESCRIBE HISTORY delta_lab_source.orders')
first_version = sql('DESCRIBE HISTORY delta_lab_source.orders').agg(F.min('version')).first()[0]
display(spark.read.format('delta').option('versionAsOf', first_version).table('delta_lab_source.orders'))
# Version 0 can be the empty CREATE TABLE commit. Compare with the later seed MERGE version.
show('EXPLAIN FORMATTED SELECT * FROM delta_lab_source.orders WHERE order_id=101')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
