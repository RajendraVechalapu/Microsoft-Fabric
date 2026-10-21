# Databricks notebook source
# MAGIC %md
# MAGIC # 18 - Databricks Jobs and Workflow Notes
# MAGIC Use Databricks Workflows to schedule, order, observe, and retry notebook tasks.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Core concepts
# MAGIC - **Job**: the deployable workflow definition.
# MAGIC - **Run**: one execution of a job.
# MAGIC - **Task**: one unit of work, such as a notebook, Python wheel, SQL task, or pipeline.
# MAGIC - **Dependency**: a rule that a task starts only after upstream tasks meet a run condition.
# MAGIC - **Job compute**: compute created for a run and terminated afterward.
# MAGIC - **All-purpose compute**: interactive compute, useful for learning but usually not ideal for production jobs.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Suggested task graph
# MAGIC
# MAGIC 1. `bronze_ingestion` -> notebook 04
# MAGIC 2. `schema_validation` -> notebook 05, depends on Bronze
# MAGIC 3. `silver_cleaning` -> notebook 06, depends on validation
# MAGIC 4. `data_quality` -> notebook 11, depends on Silver
# MAGIC 5. `gold_aggregation` -> notebook 12, depends on DQ
# MAGIC 6. `audit_or_notification` -> runs after success or failure as configured

# COMMAND ----------

# MAGIC %md
# MAGIC ## Compute choices
# MAGIC Choose a supported Databricks Runtime with Delta Lake. Prefer job compute or
# MAGIC serverless jobs for repeatable production runs. Configure autoscaling and
# MAGIC worker types based on measured workload needs, not maximum guesses.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Retries, timeouts, and concurrency
# MAGIC - Retry transient failures, but make writes idempotent first.
# MAGIC - Set a timeout so stalled work does not run forever.
# MAGIC - Limit concurrent runs when tasks update the same tables or control rows.
# MAGIC - Pass values such as `batch_id` and processing date through job parameters.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Alerting and monitoring
# MAGIC Configure notifications for failed, timed-out, or long-running jobs. Monitor
# MAGIC task duration, cluster startup, rows read/written, DQ failure rates, and data
# MAGIC freshness. Link job run IDs to records in `learning_de.pipeline_audit`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Production checklist
# MAGIC - Store code in Git and deploy with Databricks Asset Bundles.
# MAGIC - Use service principals instead of personal identities.
# MAGIC - Use Unity Catalog grants and least privilege.
# MAGIC - Separate development, test, and production catalogs or schemas.
# MAGIC - Test schema changes and backfills before production.
# MAGIC - Define ownership, alerts, runbooks, and recovery procedures.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interview notes
# MAGIC A reliable pipeline is not only transformation code. It also needs deterministic
# MAGIC inputs, idempotent outputs, dependency management, observability, retry policy,
# MAGIC access control, cost controls, and a tested recovery process.
