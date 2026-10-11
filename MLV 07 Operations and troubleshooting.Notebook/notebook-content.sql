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

-- GOAL: reconcile source truth against stored results after a successful graph refresh.
-- PREREQUISITES: 01-06. Pause ingestion for this exact comparison.
-- A concurrent source commit can create a legitimate difference between snapshots.
WITH expected AS (
 SELECT o.order_id, o.customer_id, c.customer_name, c.city,
 o.quantity, o.unit_price, o.quantity*o.unit_price AS line_total,
 CAST(o.order_ts AS DATE) AS order_date
 FROM mlv_learn.orders o JOIN mlv_learn.customers c ON o.customer_id=c.customer_id
 WHERE o.status='COMPLETED' AND o.quantity IS NOT NULL AND o.quantity>0
 AND o.unit_price IS NOT NULL AND o.unit_price>=0
)
SELECT 'source_missing_in_mlv' AS issue, x.* FROM
 (SELECT * FROM expected EXCEPT ALL SELECT * FROM mlv_learn.silver_sales) x
UNION ALL
SELECT 'extra_in_mlv' AS issue, x.* FROM
 (SELECT * FROM mlv_learn.silver_sales EXCEPT ALL SELECT * FROM expected) x;
-- EXPECT: zero differences; EXCEPT ALL also catches multiplicity differences.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- Measure quality exclusions without hiding them in a headline total.
SELECT 'rejected' AS category, COUNT(*) AS row_count FROM mlv_learn.rejected_orders
UNION ALL SELECT 'orphan', COUNT(*) FROM mlv_learn.orphan_orders
UNION ALL SELECT 'silver', COUNT(*) FROM mlv_learn.silver_sales;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

SHOW TBLPROPERTIES mlv_learn.orders;
-- UI LAB: Manage > recent runs/details. Record run start, duration, status,
-- selected scope, per-view strategy and data-quality failures where available.
-- Run with no source changes; observe whether Fabric skips eligible views.
-- Troubleshooting: missing table -> attachment/schema; stale gold -> upstream scope;
-- unexpected counts -> duplicate keys, invalid facts or orphans; failure -> error detail.
-- If incremental is unavailable, check CDF on every directly referenced source,
-- supported expressions and Optimal refresh settings. Full refresh can be correct.
-- Check capacity throttling, permissions and schedule environment when runs fail.
-- Schema changes: review explicit columns and downstream contracts before OR REPLACE.
-- Failure recovery: fix source/definition, rerun graph, then rerun reconciliation.
-- EXERCISE: keep a run log before and after correction 108, including observed strategy.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }
