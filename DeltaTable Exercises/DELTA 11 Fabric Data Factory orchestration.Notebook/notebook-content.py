# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Build the Fabric pipeline in the UI
# Prerequisite: 10. This notebook is an instruction/checkpoint notebook; it does not provision a pipeline.
# 
# 1. Create pipeline **PL_DELTA_LAB** in your Fabric workspace.
# 2. Add a Notebook activity pointing to **DELTA 10 Pipeline batch runner**; select the training Lakehouse.
# 3. In the notebook, mark its first code cell as Parameters. In the activity, set batch_id to a string
#    based on `@pipeline().RunId`, and fail_after_silver to Boolean false.
# 4. Set notebook retries to 1 for transient failures. Ensure scheduled runs cannot overlap; use one writer.
# 5. Run manually; verify activity success and delta_lab_ops.run_audit. Run again with no changes.
# 6. Add a new source order with a NEW modified_at, then run pipeline and verify report-bound gold changes.
# 7. Schedule at a modest practice cadence; pause the schedule after the lab.
# 
# **Real source extension:** use a Fabric Warehouse or SQL database orders table with a reliable change
# column. Read old watermark, capture source upper bound, then use Copy activity with
# `modified_at > old AND modified_at <= upper` to a unique Files/delta_lab/external/<run_id> folder.
# Use typed parameters/bound expressions supported by your connector. Preserve pending bounds/path before
# downstream writes and reuse them on retry. Copy file format/schema must be mapped explicitly.
# Adapt prepare_batch to consume that saved external path; the supplied runner reads the simulated source,
# so adding Copy without adapting the runner would not process your external data.
# For a real database use source-consistent reads/CDC or overlap/dedup to address delayed commits.
# Put credentials in Fabric connections. Do not commit secrets into notebooks.
# 
# **Why a Notebook activity:** it owns MERGE, reconciliation and checkpoint commit. A Copy activity alone
# does not implement the recovery contract. Git stores definitions, not the source rows or schedule state.
# Exercise: fail the notebook activity intentionally and confirm the pipeline reports failure.

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
show('SELECT * FROM delta_lab_ops.watermarks')
show('SELECT * FROM delta_lab_ops.pending')
show('SELECT * FROM delta_lab_ops.run_audit ORDER BY started_at DESC')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
