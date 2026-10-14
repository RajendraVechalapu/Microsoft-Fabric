# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Consume committed Delta changes independently of source timestamps
# Prerequisite: 07. This isolated CDF probe demonstrates INSERT, UPDATE images and physical DELETE.
# CDF must be enabled BEFORE changes. Its retention is finite; it is not a permanent audit archive.
# Bound reads by versions and retain a next-version checkpoint only after consumer application succeeds.
# Update preimages describe OLD state; applying them as current state would corrupt the consumer.
# This current-state consumer keeps one last event per key, including deletes, then MERGEs it.
# Exercise: compare source CDC, Delta CDF, and timestamp extraction. They operate at different boundaries.

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
sql("""CREATE TABLE IF NOT EXISTS delta_lab_source.cdf_probe (id INT, value INT)
 USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true')""")
sql('CREATE TABLE IF NOT EXISTS delta_lab_silver.cdf_consumer (id INT, value INT) USING DELTA')
sql('CREATE TABLE IF NOT EXISTS delta_lab_ops.cdf_checkpoint (entity STRING, next_version BIGINT) USING DELTA')
sql("""MERGE INTO delta_lab_ops.cdf_checkpoint t USING (SELECT 'probe' entity, CAST(0 AS BIGINT) next_version) s
 ON t.entity=s.entity WHEN NOT MATCHED THEN INSERT *""")
sql('MERGE INTO delta_lab_source.cdf_probe t USING (SELECT 1 id,10 value UNION ALL SELECT 2,20) s ON t.id=s.id WHEN NOT MATCHED THEN INSERT *')
sql('UPDATE delta_lab_source.cdf_probe SET value=15 WHERE id=1 AND value=10')
sql('DELETE FROM delta_lab_source.cdf_probe WHERE id=2')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

start = sql("SELECT next_version FROM delta_lab_ops.cdf_checkpoint WHERE entity='probe'").first()[0]
end = sql('DESCRIBE HISTORY delta_lab_source.cdf_probe').first()['version']
if start <= end:
    changes = (spark.read.format('delta').option('readChangeFeed','true')
        .option('startingVersion',start).option('endingVersion',end).table('delta_lab_source.cdf_probe'))
    display(changes.orderBy('_commit_version','id','_change_type'))
    events = changes.where("_change_type IN ('insert','update_postimage','delete')")
    latest = events.withColumn('rn',F.row_number().over(Window.partitionBy('id').orderBy(F.col('_commit_version').desc())))
    latest.where('rn=1').createOrReplaceTempView('cdf_latest')
    sql("""MERGE INTO delta_lab_silver.cdf_consumer t USING cdf_latest s ON t.id=s.id
     WHEN MATCHED AND s._change_type='delete' THEN DELETE
     WHEN MATCHED THEN UPDATE SET t.value=s.value
     WHEN NOT MATCHED AND s._change_type <> 'delete' THEN INSERT (id,value) VALUES (s.id,s.value)""")
    # Sequential single consumer; retries replay the same bounded changes if commit fails.
    sql(f"UPDATE delta_lab_ops.cdf_checkpoint SET next_version={end+1} WHERE entity='probe'")
else:
    print('No unread versions')
show('SELECT * FROM delta_lab_silver.cdf_consumer')
assert sql('SELECT COUNT(*) FROM delta_lab_silver.cdf_consumer').first()[0] == 1
assert sql('SELECT value FROM delta_lab_silver.cdf_consumer WHERE id=1').first()[0] == 15

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
