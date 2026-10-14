# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # A self-contained notebook activity for Fabric Data Factory
# Prerequisites: 00-09. This notebook runs one batch and writes an attempt audit.
# Mark the parameter cell in Fabric UI so a Notebook activity can override batch_id/fail_after_silver.
# All helpers are included: pipeline sessions do not share another notebook's Python variables.
# Audit records attempts, not exactly-once events. Repeated attempts may legitimately share batch_id.
# Exceptions are re-raised so Fabric marks the activity Failed. There is no silent success on bad data.
# Use sequential execution/concurrency 1. On a fresh run after 09, expect no new changes.

# CELL ********************

# PARAMETERS: mark this cell as a parameter cell in Fabric.
batch_id = 'pipeline_' + 'manual_001'
fail_after_silver = False

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

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
# WHAT: these functions implement one bounded, restartable batch.
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

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from datetime import datetime, timezone
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

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
