# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # SCD2 06 - Orchestrator (run this to process everything end to end)
# Processes batches **strictly in order**: bronze -> silver -> gold merge -> quality checks, one batch at a time.
#
# **Restartable by design.** Before picking up new files it first finishes any batch that is already in bronze but has
# not completed the gold merge (e.g. the previous run failed in silver). A failed batch stops the run, so a newer batch is
# never applied on top of a broken one - fix the cause and simply rerun this notebook.
#
# **Scheduling:** schedule this notebook directly, or call it from a Fabric Data Pipeline *Notebook* activity.
# Set the pipeline/schedule so only **one run at a time** is active (single writer per dimension).
#
# Child notebooks are run with `notebookutils.notebook.run`, so each one gets its own run snapshot in the monitoring hub.

# PARAMETERS CELL ********************

max_batches = 50            # safety valve per run
child_timeout_sec = 1800

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %run nb_scd2_00_common

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def run_child(notebook, params=None):
    print(f"  -> {notebook} {params or ''}")
    out = notebookutils.notebook.run(notebook, child_timeout_sec, params or {})
    return json.loads(out) if out else {}


def unfinished_batches():
    """Batches loaded into bronze that have not completed the gold merge yet, oldest first."""
    loaded = [r["batch_id"] for r in read_table("bronze", "file_manifest")
              .where("status = 'LOADED'").orderBy("batch_id").collect()]
    done = completed_batches("gold_scd2_merge")
    return [b for b in loaded if b not in done]


def process_batch(batch):
    run_child("nb_scd2_03_silver_cleanse", {"batch_id": batch})
    gold = run_child("nb_scd2_04_gold_scd2_merge", {"batch_id": batch})
    run_child("nb_scd2_05_quality_checks", {"batch_id": batch})
    return gold


run_started = utc_now()
summary = []
try:
    # 1) Recovery: finish batches a previous run left half-done
    for batch in unfinished_batches():
        print(f"[resume] {batch}")
        summary.append((batch, "resumed", json.dumps(process_batch(batch).get("actions", {}))))

    # 2) New files: ingest one, process it fully, repeat
    for _ in range(max_batches):
        bronze = run_child("nb_scd2_02_bronze_ingest")
        if bronze.get("status") == "NO_FILES":
            print("[done] no more files in landing")
            break
        batch = bronze["batch_id"]
        print(f"[batch] {batch}")
        summary.append((batch, "processed", json.dumps(process_batch(batch).get("actions", {}))))
except Exception as e:
    log_run(None, "orchestrator", "FAILED", run_started, {"batches": [s[0] for s in summary]}, str(e))
    raise

log_run(None, "orchestrator", "SUCCEEDED", run_started, {"batches": [s[0] for s in summary]})
display(spark.createDataFrame(summary or [("-", "nothing to do", "{}")], "batch_id string, mode string, actions string"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Result
# With the three sample files you should end with **12 rows** in `dim_customer` (including the unknown member)
# and **6 current customers**: C001, C002 (v3), C003 (v2), C004 (v2), C006, C007. C005 is closed as deleted.

# CELL ********************

display(read_table("gold", "dim_customer").orderBy("customer_id", "version_number"))
display(read_table("gold", "etl_run_log").orderBy(F.desc("started_at")).limit(30))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
