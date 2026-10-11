-- Fabric notebook source

-- METADATA ********************

-- META {
-- META   "kernel_info": {
-- META     "name": "synapse_pyspark"
-- META   },
-- META   "dependencies": {
-- META     "lakehouse": {
-- META       "default_lakehouse": "575635c0-39a7-4c4a-b3b2-51947e31e4f6",
-- META       "default_lakehouse_name": "LH_BRONZE_LAYER",
-- META       "default_lakehouse_workspace_id": "5eb70860-7a4a-4770-86da-351148a2dddc",
-- META       "known_lakehouses": [
-- META         {
-- META           "id": "575635c0-39a7-4c4a-b3b2-51947e31e4f6"
-- META         }
-- META       ]
-- META     }
-- META   }
-- META }

-- CELL ********************

-- GOAL: observe stale results, then refresh a whole dependency graph.
-- PREREQUISITES: 01-04. Turn off course schedules while observing the stale state.
-- One new valid order; MERGE makes this exercise safe to replay without duplicate inserts.
MERGE INTO mlv_learn.orders t
USING (SELECT 108 AS order_id, 1 AS customer_id, 1 AS quantity,
 CAST(50 AS DECIMAL(12,2)) AS unit_price, 'COMPLETED' AS status,
 TIMESTAMP '2026-10-02 13:00:00' AS order_ts) s
ON t.order_id=s.order_id WHEN NOT MATCHED THEN INSERT *;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- Before refresh, source has 108 while gold usually still totals 575.
-- If already refreshed/replayed, gold may total 625. This is observation, not a race-safe assertion.
SELECT * FROM mlv_learn.orders WHERE order_id=108;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

SELECT SUM(revenue) AS stored_gold_revenue FROM mlv_learn.gold_daily_sales;
-- PAUSE HERE: create a lakehouse-managed schedule selecting ALL course views from 02-04.
-- Avoid Refresh all if your lakehouse has unrelated MLVs; inspect the highlighted scope.
-- Run the schedule on demand and wait for SUCCESS. Included dependencies run in order.
-- Select a five-minute-or-longer practice cadence if enabling recurring refresh.
-- A single-node Run refreshes only that node, so do not use gold-only Run for this chain.
-- Refresh type, interval, environment and Optimal refresh settings belong to that schedule.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- AFTER successful graph refresh EXPECT: 4 silver rows, gold revenue 625.
SELECT COUNT(*) AS silver_count, SUM(line_total) AS revenue FROM mlv_learn.silver_sales;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- GOAL: changes include corrections and cancellations, not just inserts.
UPDATE mlv_learn.orders SET quantity=2 WHERE order_id=108;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

UPDATE mlv_learn.orders SET status='CANCELLED' WHERE order_id=102;
-- PAUSE: run the same selected-scope schedule again; wait for success.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT after second graph refresh: 3 silver rows, revenue 375 (=200+75+100).
SELECT COUNT(*) AS silver_count, SUM(line_total) AS revenue FROM mlv_learn.silver_sales;
-- CDF + eligible SQL enables incremental refresh; it never guarantees incremental execution.
-- Updates/deletes may require full recomputation without supported row-identity hints.
-- Inspect actual strategy in refresh monitoring; do not infer it from small elapsed time.
-- For a one-off diagnostic, REFRESH MATERIALIZED LAKE VIEW mlv_learn.completed_orders;
-- refreshes one node only. It is not this course's ongoing orchestration mechanism.
-- EXERCISE: explain why refreshing gold before silver can report stale revenue.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

