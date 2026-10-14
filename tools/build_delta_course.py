"""Generate native Fabric learning notebooks; run from the repository root."""
from pathlib import Path
import ast
import json
import uuid

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'DELTA'
BOOT = '''from pyspark.sql import functions as F
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
'''

ENGINE = """# WHAT: these functions implement one bounded, restartable batch.
# WHY: extraction, target application, and checkpoint advancement are different operations.
# Delta commits are atomic PER TABLE; this whole workflow is not one cross-table transaction.
# Run one writer at a time. Pipeline concurrency must be 1 for this learning implementation.
def prepare_batch(batch_id):
    # A pending batch keeps its original bounds and files across retries.
    pending = sql("SELECT * FROM delta_lab_ops.pending WHERE entity = 'orders'").collect()
    if pending:
        return pending[0].asDict()
    old = sql("SELECT watermark FROM delta_lab_ops.watermarks WHERE entity='orders'").first()[0]
    version = sql("DESCRIBE HISTORY delta_lab_source.orders").first()['version']
    # Pin a Delta snapshot: later source writes cannot change this batch's extract.
    source = spark.read.format('delta').option('versionAsOf', version).table('delta_lab_source.orders')
    upper = source.agg(F.max('modified_at')).first()[0]
    if upper is None or upper <= old:
        return None
    path = 'Files/delta_lab/landing/orders/' + batch_id
    changed = source.where((F.col('modified_at') > F.lit(old)) & (F.col('modified_at') <= F.lit(upper)))
    # A directory of Parquet files is an immutable batch landing area, not yet a Delta table.
    changed.write.mode('overwrite').parquet(path)
    spark.createDataFrame([('orders', batch_id, old, upper, path)],
        'entity string, batch_id string, old_watermark timestamp, upper_watermark timestamp, path string'
    ).createOrReplaceTempView('new_pending')
    sql("INSERT INTO delta_lab_ops.pending SELECT * FROM new_pending")
    return sql("SELECT * FROM delta_lab_ops.pending WHERE entity='orders'").first().asDict()

def apply_batch(batch):
    incoming = spark.read.parquet(batch['path'])
    incoming = incoming.withColumn('batch_id', F.lit(batch['batch_id'])).withColumn('ingested_at', F.current_timestamp())
    incoming.createOrReplaceTempView('incoming_orders')
    # Bronze retains every extracted source state. Retry of the SAME batch adds no duplicates.
    sql('''MERGE INTO delta_lab_bronze.orders t USING incoming_orders s
        ON t.batch_id=s.batch_id AND t.order_id=s.order_id
        WHEN NOT MATCHED THEN INSERT *''')
    # Validate foreign keys as well as required values. Never silently discard rejected data.
    checked = incoming.join(sql('SELECT customer_id FROM delta_lab_source.customers'), 'customer_id', 'left_semi')
    checked = checked.withColumn('reason', F.when(F.col('order_id').isNull(), 'missing key')
        .when(F.col('modified_at').isNull(), 'missing change timestamp')
        .when(F.col('order_date').isNull(), 'missing order date')
        .when(F.col('amount').isNull() | (F.col('amount') < 0), 'invalid amount')
        .when(F.col('is_deleted').isNull(), 'missing delete flag'))
    orphans = incoming.join(sql('SELECT customer_id FROM delta_lab_source.customers'), 'customer_id', 'left_anti').withColumn('reason', F.lit('unknown customer'))
    rejected = checked.where('reason IS NOT NULL').unionByName(orphans)
    rejected.createOrReplaceTempView('rejected_orders')
    sql('''MERGE INTO delta_lab_ops.quarantine t USING rejected_orders s
        ON t.batch_id=s.batch_id AND t.order_id <=> s.order_id
        WHEN NOT MATCHED THEN INSERT *''')
    # Fail the batch after retaining evidence. Checkpoint remains unchanged for correction/retry.
    if rejected.count():
        raise ValueError('Rejected rows recorded in delta_lab_ops.quarantine; resolve before committing')
    # One winner per business key avoids ambiguous MERGE matches.
    # This source has unique keys. Real CDC needs a source sequence to break timestamp ties.
    ranked = checked.where('reason IS NULL').drop('reason').withColumn('rn',
        F.row_number().over(Window.partitionBy('order_id').orderBy(F.col('modified_at').desc())))
    ranked.where('rn=1').drop('rn','batch_id','ingested_at').createOrReplaceTempView('valid_orders')
    # Keep tombstones in silver: an older replay must not resurrect a deleted order.
    # The >= guard permits retry but prevents older source states overwriting newer states.
    sql('''MERGE INTO delta_lab_silver.orders t USING valid_orders s ON t.order_id=s.order_id
        WHEN MATCHED AND s.modified_at >= t.modified_at THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *''')

def build_gold():
    # Full gold rebuild is deliberate for this tiny lab. It handles corrections to old dates.
    # At scale, capture BOTH old and new affected dates before MERGE and replace those groups.
    sql('''CREATE OR REPLACE TABLE delta_lab_gold.dim_customer USING DELTA AS
        SELECT customer_id, customer_name, city FROM delta_lab_source.customers''')
    sql('''CREATE OR REPLACE TABLE delta_lab_gold.fact_order USING DELTA AS
        SELECT order_id, customer_id, order_date, amount FROM delta_lab_silver.orders
        WHERE NOT is_deleted''')
    sql('''CREATE OR REPLACE TABLE delta_lab_gold.dim_date USING DELTA AS
        SELECT d AS order_date, year(d) AS year, month(d) AS month, day(d) AS day
        FROM (SELECT explode(sequence(DATE '2026-01-01', DATE '2026-12-31', INTERVAL 1 DAY)) AS d)''')
    sql('''CREATE OR REPLACE TABLE delta_lab_gold.daily_sales USING DELTA AS
        SELECT order_date, COUNT(*) AS order_count, SUM(amount) AS revenue
        FROM delta_lab_gold.fact_order GROUP BY order_date''')
    silver = sql('SELECT COALESCE(SUM(amount),0) FROM delta_lab_silver.orders WHERE NOT is_deleted').first()[0]
    gold = sql('SELECT COALESCE(SUM(revenue),0) FROM delta_lab_gold.daily_sales').first()[0]
    assert silver == gold, 'Gold reconciliation failed'

def commit_batch(batch):
    # Commit only AFTER silver, gold and checks succeed. A crash before this replays safely.
    spark.createDataFrame([('orders', batch['upper_watermark'])],
        'entity string, watermark timestamp').createOrReplaceTempView('next_watermark')
    sql('''MERGE INTO delta_lab_ops.watermarks t USING next_watermark s ON t.entity=s.entity
        WHEN MATCHED AND s.watermark > t.watermark THEN UPDATE SET watermark=s.watermark''')
    # This delete is housekeeping. A crash after watermark commit but before delete replays
    # the same pending batch, then removes it; the watermark never moves backwards.
    sql("DELETE FROM delta_lab_ops.pending WHERE entity='orders'")

def run_batch(batch_id, fail_after_silver=False):
    batch = prepare_batch(batch_id)
    if batch is None:
        print('No new changes; checkpoint unchanged')
        return
    apply_batch(batch)
    if fail_after_silver:
        raise RuntimeError('Intentional lab failure: silver committed, watermark has NOT advanced')
    build_gold()
    commit_batch(batch)
    print('Completed batch', batch['batch_id'])
"""

lessons = []
def add(name, intro, *cells):
    lessons.append((name, intro, cells))
def md(text): return ('md', text)
def code(text): return ('code', text)

add('00 Start here', '''# Fabric Delta Lake: end-to-end learning lab
**What you build:** a reproducible sales pipeline from source through bronze, silver, gold and Power BI.
**Why:** learning Delta syntax alone does not teach extraction, retries, deletes or serving.

Read DELTA-LEARNING.md first. Sync these items through workspace Git, then attach EVERY
notebook to the same schema-enabled training Lakehouse. No workspace identifiers are embedded.
Use Fabric Spark/PySpark, not the read-only Lakehouse SQL analytics endpoint.
Run 00-14 in order, cell by cell. Stop at UI instructions and intentional failure cells.
This course only writes delta_lab_* schemas and Files/delta_lab. Source is simulated locally;
lesson 11 explains replacement with a real Fabric Data Factory source connector.
Prerequisites: Fabric capacity, notebook/table write permission, schemas enabled, Power BI permissions.
Exercise: explain source change time, business event time, ingestion time and report refresh time.''',
code(BOOT + '''show('SELECT current_database() AS attached_database, current_timestamp() AS session_time')
for schema in ['source','bronze','silver','gold','ops']:
    sql('CREATE SCHEMA IF NOT EXISTS delta_lab_' + schema)
show('SHOW SCHEMAS')
'''))

add('01 Source and control tables', '''# Build a deterministic source and durable control state
Prerequisite: 00. Source tables simulate an operational system; they are not bronze.
`order_id` is the business key, `order_date` is the business date, `modified_at` is extraction time.
Use DECIMAL for money and UTC timestamps to avoid rounding and timezone surprises.
Initial seed inserts missing keys only: rerunning does not undo later source changes.
Expected first run: 3 orders, revenue 600, watermark 1900-01-01.''', code(BOOT + '''sql("""CREATE TABLE IF NOT EXISTS delta_lab_source.orders (
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
'''))

add('02 Delta anatomy and time travel', '''# Delta is a transaction log plus data files
Prerequisite: 01. Parquet stores columnar data; Delta tracks which files form a committed snapshot.
Table history shows operations, versions and metrics. A version is local to ONE table.
Time travel reads an earlier snapshot, but requires its files to remain retained.
Reading raw Parquet files from a Delta directory bypasses the log and can return obsolete rows.
Exercise: locate `_delta_log` in the table's OneLake folder using Lakehouse Explorer.
No table mutations are needed for this lesson.''', code(BOOT + '''show('DESCRIBE DETAIL delta_lab_source.orders')
show('DESCRIBE HISTORY delta_lab_source.orders')
first_version = sql('DESCRIBE HISTORY delta_lab_source.orders').agg(F.min('version')).first()[0]
display(spark.read.format('delta').option('versionAsOf', first_version).table('delta_lab_source.orders'))
# Version 0 can be the empty CREATE TABLE commit. Compare with the later seed MERGE version.
show('EXPLAIN FORMATTED SELECT * FROM delta_lab_source.orders WHERE order_id=101')
'''))

add('03 Initial full extraction', '''# Initial load is the first bounded batch
Prerequisites: 00-02. A watermark earlier than all source rows makes the first extract a full load.
Capture a fixed upper bound, then materialize landing files. Do not use an unbounded query
while the source is changing. Our simulated Delta source also pins a table version.
This lesson intentionally DOES NOT advance the watermark: landing is not successful end-to-end processing.
Expected fresh run: 3 landed rows, pending bounds 1900-01-01 to 2026-01-01 10:00 UTC.
Exercise: inspect Files/delta_lab/landing/orders/initial_001 in the Lakehouse.''',
code(BOOT + ENGINE), code('''batch = prepare_batch('initial_001')
assert batch is not None, 'Initial batch already processed; inspect watermarks or use safe reset in 14'
display(spark.read.parquet(batch['path']))
show('SELECT * FROM delta_lab_ops.pending')
show('SELECT * FROM delta_lab_ops.watermarks')
'''))

add('04 Bronze silver and quality', '''# Apply raw changes, validate, and upsert clean state
Prerequisite: 03 with a pending batch. Bronze holds source snapshots by batch; silver holds latest state.
Why MERGE: append alone duplicates updated business keys. Why tombstones: preserve deletion ordering.
The helper comments explain rejection, deduplication and retry behavior line by line.
Quarantine is evidence, not permission to lose a bad record: rejected batches fail without advancing state.
Expected fresh run: bronze 3, silver 3, quarantine 0, active silver revenue 600.
Exercise: describe why a null/negative amount should fail a financial reconciliation.''',
code(BOOT + ENGINE), code('''batch = sql("SELECT * FROM delta_lab_ops.pending WHERE entity='orders'").first()
assert batch is not None, 'Run 03 first'
apply_batch(batch.asDict())
show('SELECT * FROM delta_lab_bronze.orders ORDER BY order_id')
show('SELECT * FROM delta_lab_silver.orders ORDER BY order_id')
assert sql('SELECT COUNT(*) FROM delta_lab_ops.quarantine').first()[0] == 0
# Checkpoint is still unchanged: gold has not yet been built.
show('SELECT * FROM delta_lab_ops.watermarks')
'''), md('''**Quality extension (manual exercise):** after completing 10, insert an order with amount -10
and a NEW modified_at. Run 10 and inspect quarantine and pending. Correct its source amount and
advance modified_at again. Because the pending files are immutable, source correction alone does not
repair that batch: inspect and explicitly abandon the failed pending batch, preserving quarantine,
then rerun from the unchanged watermark to re-extract. This lab fails on rejects; production can instead
commit accepted rows only with a separately durable rejected-row repair workflow. Do this extension
after the deterministic checkpoints, or reset before continuing them.'''))

add('05 Gold star schema and reconciliation', '''# Turn clean state into business analytics
Prerequisite: 04. Fact grain is one active order; customer and date dimensions are unique by key.
Soft-deleted rows stay in silver but are excluded from the fact and revenue.
For the small lab, rebuild gold each batch. This is intentionally NOT incremental gold processing.
Why: updating an old order changes an old aggregate, and moving its date affects TWO dates.
Expected: 3 fact rows, revenue 600; initial watermark committed only after reconciliation.
Exercise: explain why adding the new amount to yesterday's total is wrong for an update.''',
code(BOOT + ENGINE), code('''build_gold()
batch = sql("SELECT * FROM delta_lab_ops.pending WHERE entity='orders'").first()
if batch is not None:
    commit_batch(batch.asDict())
show('SELECT * FROM delta_lab_gold.daily_sales ORDER BY order_date')
show('SELECT * FROM delta_lab_ops.watermarks')
assert sql('SELECT COUNT(*) FROM delta_lab_gold.fact_order').first()[0] == 3
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('600.00')
'''))

add('06 Incremental insert and bounded extraction', '''# Extract only changes since successful processing
Prerequisite: 05. Add order 104 for 50 with a newer modified_at.
The filter is old < modified_at <= upper. Bounds are saved before downstream processing.
Source contract: every change updates modified_at, and newly visible changes must not arrive behind
the committed timestamp. Delayed commits can violate this; use overlap plus dedup or source CDC.
Timestamp ties require a reliable source sequence for ordering when the source emits multiple states.
Expected: 1 landed row; after apply and commit, active orders 4 and revenue 650.''',
code(BOOT + ENGINE), code('''sql("""MERGE INTO delta_lab_source.orders t USING (
 SELECT 104 order_id,2 customer_id,DATE '2026-01-03' order_date,
 CAST(50 AS DECIMAL(12,2)) amount,TIMESTAMP '2026-01-02 10:00:00' modified_at,false is_deleted
) s ON t.order_id=s.order_id WHEN NOT MATCHED THEN INSERT *""")
batch = prepare_batch('insert_001')
if batch is not None:
    display(spark.read.parquet(batch['path']))
    apply_batch(batch)
    build_gold()
    commit_batch(batch)
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('650.00')
'''))

add('07 Corrections deletes late arrivals and replay', '''# Incremental means changes, not just inserts
Prerequisite: 06. Run cells in sequence: correction -> soft delete -> late business event -> replay.
Correction changes order 102 to 250. Soft deletion removes order 103 from active analytics.
Late order 105 has an OLD order_date but NEW modified_at: extraction must use modified_at.
Do not hard-delete source rows in a timestamp-only pipeline: deleted rows cannot be selected.
Expected revenues: 700 -> 400 -> 475 -> 475. Final active count 4; silver count 5 including tombstone.
Each source mutation has a guard so lesson replay does not move source timestamps backwards.''',
code(BOOT + ENGINE), code('''sql("""UPDATE delta_lab_source.orders SET amount=250, modified_at=TIMESTAMP '2026-01-03 10:00:00'
 WHERE order_id=102 AND modified_at < TIMESTAMP '2026-01-03 10:00:00'""")
run_batch('correction_001')
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('700.00')
'''), code('''sql("""UPDATE delta_lab_source.orders SET is_deleted=true, modified_at=TIMESTAMP '2026-01-04 10:00:00'
 WHERE order_id=103 AND modified_at < TIMESTAMP '2026-01-04 10:00:00'""")
run_batch('delete_001')
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('400.00')
'''), code('''sql("""MERGE INTO delta_lab_source.orders t USING (
 SELECT 105 order_id,1 customer_id,DATE '2026-01-01' order_date,
 CAST(75 AS DECIMAL(12,2)) amount,TIMESTAMP '2026-01-05 10:00:00' modified_at,false is_deleted
) s ON t.order_id=s.order_id WHEN NOT MATCHED THEN INSERT *""")
run_batch('late_001')
assert sql('SELECT COUNT(*) FROM delta_lab_gold.fact_order').first()[0] == 4
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('475.00')
'''), code('''# Actual target replay uses saved files even though the watermark has advanced.
before = sql('SELECT COUNT(*) FROM delta_lab_bronze.orders').first()[0]
apply_batch({'batch_id':'late_001', 'path':'Files/delta_lab/landing/orders/late_001'})
build_gold()
assert sql('SELECT COUNT(*) FROM delta_lab_bronze.orders').first()[0] == before
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('475.00')
show('SELECT * FROM delta_lab_silver.orders ORDER BY order_id')
'''))

add('08 Change data feed and version checkpoints', '''# Consume committed Delta changes independently of source timestamps
Prerequisite: 07. This isolated CDF probe demonstrates INSERT, UPDATE images and physical DELETE.
CDF must be enabled BEFORE changes. Its retention is finite; it is not a permanent audit archive.
Bound reads by versions and retain a next-version checkpoint only after consumer application succeeds.
Update preimages describe OLD state; applying them as current state would corrupt the consumer.
This current-state consumer keeps one last event per key, including deletes, then MERGEs it.
Exercise: compare source CDC, Delta CDF, and timestamp extraction. They operate at different boundaries.''',
code(BOOT + '''sql("""CREATE TABLE IF NOT EXISTS delta_lab_source.cdf_probe (id INT, value INT)
 USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true')""")
sql('CREATE TABLE IF NOT EXISTS delta_lab_silver.cdf_consumer (id INT, value INT) USING DELTA')
sql('CREATE TABLE IF NOT EXISTS delta_lab_ops.cdf_checkpoint (entity STRING, next_version BIGINT) USING DELTA')
sql("""MERGE INTO delta_lab_ops.cdf_checkpoint t USING (SELECT 'probe' entity, CAST(0 AS BIGINT) next_version) s
 ON t.entity=s.entity WHEN NOT MATCHED THEN INSERT *""")
sql('MERGE INTO delta_lab_source.cdf_probe t USING (SELECT 1 id,10 value UNION ALL SELECT 2,20) s ON t.id=s.id WHEN NOT MATCHED THEN INSERT *')
sql('UPDATE delta_lab_source.cdf_probe SET value=15 WHERE id=1 AND value=10')
sql('DELETE FROM delta_lab_source.cdf_probe WHERE id=2')
'''), code('''start = sql("SELECT next_version FROM delta_lab_ops.cdf_checkpoint WHERE entity='probe'").first()[0]
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
'''))

add('09 Failure recovery and idempotency', '''# Prove recovery after a partial workflow commit
Prerequisite: 07 (08 is independent). Add order 106 for 25, then intentionally fail after silver.
Why this matters: Delta guarantees table commits; it does not roll back bronze and silver when gold fails.
STOP after the failure cell, inspect pending/watermark, then run the recovery cell manually.
Expected before recovery: silver active revenue 500, gold 475, watermark still Jan 5.
Expected after recovery: silver/gold 500, active count 5, pending empty, watermark Jan 6.
Never configure a pipeline to advance watermark on a failure dependency.''',
code(BOOT + ENGINE), code('''sql("""MERGE INTO delta_lab_source.orders t USING (
 SELECT 106 order_id,2 customer_id,DATE '2026-01-04' order_date,
 CAST(25 AS DECIMAL(12,2)) amount,TIMESTAMP '2026-01-06 10:00:00' modified_at,false is_deleted
) s ON t.order_id=s.order_id WHEN NOT MATCHED THEN INSERT *""")
# EXPECTED ERROR. Run this cell once, then continue manually with the next cell.
run_batch('recovery_001', fail_after_silver=True)
'''), code('''show('SELECT * FROM delta_lab_ops.pending')
show('SELECT * FROM delta_lab_ops.watermarks')
show('SELECT SUM(amount) AS silver_revenue FROM delta_lab_silver.orders WHERE NOT is_deleted')
show('SELECT SUM(amount) AS gold_revenue FROM delta_lab_gold.fact_order')
run_batch('recovery_001')
assert sql('SELECT SUM(amount) FROM delta_lab_gold.fact_order').first()[0] == Decimal('500.00')
assert sql('SELECT COUNT(*) FROM delta_lab_ops.pending').first()[0] == 0
'''))

add('10 Pipeline batch runner', '''# A self-contained notebook activity for Fabric Data Factory
Prerequisites: 00-09. This notebook runs one batch and writes an attempt audit.
Mark the parameter cell in Fabric UI so a Notebook activity can override batch_id/fail_after_silver.
All helpers are included: pipeline sessions do not share another notebook's Python variables.
Audit records attempts, not exactly-once events. Repeated attempts may legitimately share batch_id.
Exceptions are re-raised so Fabric marks the activity Failed. There is no silent success on bad data.
Use sequential execution/concurrency 1. On a fresh run after 09, expect no new changes.''',
code('''# PARAMETERS: mark this cell as a parameter cell in Fabric.
batch_id = 'pipeline_' + 'manual_001'
fail_after_silver = False
'''), code(BOOT + ENGINE), code('''from datetime import datetime, timezone
import time
sql("""CREATE TABLE IF NOT EXISTS delta_lab_ops.run_audit
 (attempt_id STRING, requested_batch_id STRING, actual_batch_id STRING, status STRING,
 started_at TIMESTAMP, duration_seconds DOUBLE, source_rows BIGINT, bronze_rows BIGINT,
 silver_rows BIGINT, quarantine_rows BIGINT, watermark TIMESTAMP, error STRING) USING DELTA""")
attempt_id = str(uuid.uuid4())
started = datetime.now(timezone.utc).replace(tzinfo=None)
clock_start = time.monotonic()
actual = None
try:
    pending = prepare_batch(batch_id)
    actual = pending['batch_id'] if pending else None
    run_batch(batch_id, fail_after_silver)
    status, error = ('SUCCEEDED' if pending else 'NO_CHANGES'), None
except Exception as exc:
    status, error = 'FAILED', str(exc)[:2000]
    raise
finally:
    # In a production runner, preserve the original error if audit storage itself fails.
    try:
        counts = [sql('SELECT COUNT(*) FROM ' + t).first()[0] for t in
            ['delta_lab_source.orders','delta_lab_bronze.orders','delta_lab_silver.orders','delta_lab_ops.quarantine']]
        watermark = sql("SELECT watermark FROM delta_lab_ops.watermarks WHERE entity='orders'").first()[0]
        spark.createDataFrame([(attempt_id,batch_id,actual,status,started,time.monotonic()-clock_start,
            *counts,watermark,error)], sql('SELECT * FROM delta_lab_ops.run_audit').schema
        ).write.format('delta').mode('append').saveAsTable('delta_lab_ops.run_audit')
    except Exception as audit_error:
        print('Audit write failed:', str(audit_error))
show('SELECT * FROM delta_lab_ops.run_audit ORDER BY started_at DESC')
'''))

add('11 Fabric Data Factory orchestration', '''# Build the Fabric pipeline in the UI
Prerequisite: 10. This notebook is an instruction/checkpoint notebook; it does not provision a pipeline.

1. Create pipeline **PL_DELTA_LAB** in your Fabric workspace.
2. Add a Notebook activity pointing to **DELTA 10 Pipeline batch runner**; select the training Lakehouse.
3. In the notebook, mark its first code cell as Parameters. In the activity, set batch_id to a string
   based on `@pipeline().RunId`, and fail_after_silver to Boolean false.
4. Set notebook retries to 1 for transient failures. Ensure scheduled runs cannot overlap; use one writer.
5. Run manually; verify activity success and delta_lab_ops.run_audit. Run again with no changes.
6. Add a new source order with a NEW modified_at, then run pipeline and verify report-bound gold changes.
7. Schedule at a modest practice cadence; pause the schedule after the lab.

**Real source extension:** use a Fabric Warehouse or SQL database orders table with a reliable change
column. Read old watermark, capture source upper bound, then use Copy activity with
`modified_at > old AND modified_at <= upper` to a unique Files/delta_lab/external/<run_id> folder.
Use typed parameters/bound expressions supported by your connector. Preserve pending bounds/path before
downstream writes and reuse them on retry. Copy file format/schema must be mapped explicitly.
Adapt prepare_batch to consume that saved external path; the supplied runner reads the simulated source,
so adding Copy without adapting the runner would not process your external data.
For a real database use source-consistent reads/CDC or overlap/dedup to address delayed commits.
Put credentials in Fabric connections. Do not commit secrets into notebooks.

**Why a Notebook activity:** it owns MERGE, reconciliation and checkpoint commit. A Copy activity alone
does not implement the recovery contract. Git stores definitions, not the source rows or schedule state.
Exercise: fail the notebook activity intentionally and confirm the pipeline reports failure.''',
code(BOOT + '''show('SELECT * FROM delta_lab_ops.watermarks')
show('SELECT * FROM delta_lab_ops.pending')
show('SELECT * FROM delta_lab_ops.run_audit ORDER BY started_at DESC')
'''))

add('12 SQL endpoint semantic model and Power BI', '''# Serve gold through a semantic model
Prerequisites: 09-11. Spark writes gold; the Lakehouse SQL analytics endpoint reads Delta tables.
Endpoint metadata synchronization may lag table creation. Check table discovery before proceeding.

1. Open the Lakehouse SQL analytics endpoint. Run T-SQL `SELECT SUM(amount) FROM delta_lab_gold.fact_order;`.
   Expected after 09: 500. Do not execute Spark MERGE in this endpoint.
2. From the Lakehouse choose **New semantic model**, selecting gold fact_order, dim_customer and dim_date.
   Use a supported Direct Lake creation path in your workspace. Do not assume a default model exists.
3. Create one-to-many relationships dim_customer.customer_id -> fact_order.customer_id and
   dim_date.order_date -> fact_order.order_date; use single-direction filtering from dimensions.
4. Add measures: `Revenue = SUM(fact_order[amount])` and `Orders = COUNTROWS(fact_order)`.
   Table names in DAX must match the actual semantic-model names.
5. Build report cards for Revenue/Orders, a date revenue chart and a customer revenue table.
6. Verify Revenue=500 and Orders=5. Check customer/date filtering against notebook SQL.
7. Change source data, run PL_DELTA_LAB, then refresh/reframe the semantic model as appropriate
   for its Direct Lake configuration and reload report visuals. Measure each latency boundary.
8. Optional security exercise: add a test role in the model and use Test as role before sharing.

Why star schema: dimensions filter facts consistently; duplicate dimension keys break the one side.
Why semantic refresh still matters: new Delta commits and model metadata/frames are different states.
Direct Lake, Import refresh, source ingestion and MLV refresh are distinct operations.
This notebook does not publish reports or change permissions automatically.''',
code(BOOT + '''show('SELECT COUNT(*) AS active_orders, SUM(amount) AS revenue FROM delta_lab_gold.fact_order')
show("""SELECT c.customer_name, SUM(f.amount) AS revenue FROM delta_lab_gold.fact_order f
 JOIN delta_lab_gold.dim_customer c ON c.customer_id=f.customer_id GROUP BY c.customer_name""")
assert sql('SELECT customer_id FROM delta_lab_gold.dim_customer GROUP BY customer_id HAVING COUNT(*)>1').count()==0
assert sql('SELECT order_date FROM delta_lab_gold.dim_date GROUP BY order_date HAVING COUNT(*)>1').count()==0
'''))

add('13 Operations maintenance and MLV extension', '''# Inspect health and learn maintenance without deleting history
Prerequisites: 09-12. Tiny data teaches mechanics, not performance benchmarks.
OPTIMIZE compacts small files; a larger table and measured baseline are needed to prove a speedup.
Avoid high-cardinality partition columns. Do not partition this handful of orders.
VACUUM deletes obsolete files: it can break old time travel and CDF readers beyond retention.
We show DRY RUN only. Do not disable retention checks or use zero retention in this course.

**MLV extension:** use your existing MLV course with delta_lab_silver.orders as a NEW source.
Create an isolated active-orders view and daily aggregate, exclude is_deleted, and add both to a
managed refresh schedule. Verify their refresh results after a correction. Use distinct names and
do not replace existing MLV course objects. Compare engine-reported refresh strategy with the explicit
notebook pipeline; CDF enablement does not promise every definition/change is incrementally refreshed.

Exercise: describe the retention period needed for your slowest downstream consumer and recovery window.
Stop schedules when finished; maintenance and refresh consume Fabric capacity.''',
code(BOOT + '''show('DESCRIBE DETAIL delta_lab_bronze.orders')
show('DESCRIBE HISTORY delta_lab_silver.orders')
show('SELECT * FROM delta_lab_ops.run_audit ORDER BY started_at DESC')
show('SELECT * FROM delta_lab_ops.quarantine')
show('EXPLAIN FORMATTED SELECT order_date, SUM(amount) FROM delta_lab_gold.fact_order GROUP BY order_date')
'''), code('''# WHAT: compact this dedicated training table. WHY: reduce many tiny file reads.
sql('OPTIMIZE delta_lab_bronze.orders')
show('DESCRIBE DETAIL delta_lab_bronze.orders')
# DRY RUN lists candidates and does not remove files.
show('VACUUM delta_lab_bronze.orders RETAIN 168 HOURS DRY RUN')
'''))

add('14 Capstone acceptance and safe reset', '''# Prove the end-to-end learning outcomes
Prerequisites: all core lessons through 13. Expected after 09: active orders 5, revenue 500,
silver rows 6 (including deleted 103), bronze snapshots 8, empty pending, Jan 6 watermark.
Checks assume no optional quality experiments or additional pipeline mutations.

Capstone: add two new orders, update an existing order onto a different business date, and soft-delete
another. Predict counts/revenue BEFORE execution, run the pipeline, and reconcile Power BI.
Then inject a post-silver failure and recover from the SAME pending batch.
Explain extraction ordering, idempotent MERGE, tombstones, CDF retention and reporting freshness.

**Safe reset is optional and disabled.** Pause pipelines/MLV schedules, remove optional dependent views,
and ensure no consumers are running. Reset removes only the dedicated delta_lab_* schemas.
Landing files are retained. After reset run 00 onward; fixed batch folders will be overwritten on extract.
No existing mlv_learn or business tables are included.''',
code(BOOT + '''assert sql('SELECT COUNT(*) FROM delta_lab_gold.fact_order').first()[0] == 5
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
'''), code('''# Explicit opt-in only. Run all keeps cleanup disabled.
RESET_TRAINING_SCHEMAS = False
if RESET_TRAINING_SCHEMAS:
    for schema in ['gold','silver','bronze','ops','source']:
        sql('DROP SCHEMA IF EXISTS delta_lab_' + schema + ' CASCADE')
    print('Training tables reset; rerun 00 onward. Landing files retained.')
else:
    print('Reset disabled; no tables removed')
'''))

def render(name, intro, cells):
    parts = ['# Fabric notebook source', '', '# METADATA ********************', '',
        '# META ' + json.dumps({'kernel_info': {'name':'synapse_pyspark'}}, indent=2).replace('\n','\n# META '), '']
    for kind, body in [('md', intro), *cells]:
        if kind == 'md':
            parts += ['# MARKDOWN ********************','', '\n'.join('# ' + line for line in body.strip().splitlines()), '']
        else:
            ast.parse(body)
            parts += ['# CELL ********************','', body.strip(), '', '# METADATA ********************','',
                '# META ' + json.dumps({'language':'python','language_group':'synapse_pyspark'},indent=2).replace('\n','\n# META '),'']
    return '\n'.join(parts)

for name, intro, cells in lessons:
    folder = ROOT / (PREFIX + ' ' + name + '.Notebook')
    folder.mkdir(exist_ok=True)
    platform_path = folder / '.platform'
    logical_id = json.loads(platform_path.read_text())['config']['logicalId'] if platform_path.exists() else str(uuid.uuid4())
    platform = {'$schema':'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json',
        'metadata':{'type':'Notebook','displayName':PREFIX+' '+name,'description':'Fabric Delta Lake end-to-end lab: '+name},
        'config':{'version':'2.0','logicalId':logical_id}}
    platform_path.write_text(json.dumps(platform,indent=2)+'\n',encoding='utf-8')
    (folder/'notebook-content.py').write_text(render(name,intro,cells),encoding='utf-8')
print(f'Generated and syntax-checked {len(lessons)} Fabric notebooks')
