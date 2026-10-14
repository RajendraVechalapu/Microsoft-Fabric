# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Initial load is the first bounded batch
# Prerequisites: 00-02. A watermark earlier than all source rows makes the first extract a full load.
# Capture a fixed upper bound, then materialize landing files. Do not use an unbounded query
# while the source is changing. Our simulated Delta source also pins a table version.
# This lesson intentionally DOES NOT advance the watermark: landing is not successful end-to-end processing.
# Expected fresh run: 3 landed rows, pending bounds 1900-01-01 to 2026-01-01 10:00 UTC.
# Exercise: inspect Files/delta_lab/landing/orders/initial_001 in the Lakehouse.

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

batch = prepare_batch('initial_001')
assert batch is not None, 'Initial batch already processed; inspect watermarks or use safe reset in 14'
display(spark.read.parquet(batch['path']))
show('SELECT * FROM delta_lab_ops.pending')
show('SELECT * FROM delta_lab_ops.watermarks')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
