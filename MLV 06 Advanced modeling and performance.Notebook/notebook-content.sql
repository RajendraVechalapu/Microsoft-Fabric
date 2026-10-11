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

-- GOAL: learn definition evolution, partition tradeoffs, and window semantics.
-- PREREQUISITES: 01-05. OR REPLACE updates an existing definition; IF NOT EXISTS does not.
-- Separate advanced objects keep the earlier lesson contracts stable.
CREATE OR REPLACE MATERIALIZED LAKE VIEW mlv_learn.sales_by_date
PARTITIONED BY (order_date)
COMMENT 'Learning partition pruning; tiny sample is not a performance benchmark'
AS SELECT order_id, customer_id, city, order_date, line_total
FROM mlv_learn.silver_sales;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

EXPLAIN FORMATTED SELECT * FROM mlv_learn.sales_by_date
WHERE order_date=DATE '2026-10-02';
-- Inspect partition filters in the plan. Many tiny date partitions can hurt small workloads.
-- Do not partition by unique order_id. Benchmark representative volume before tuning.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

CREATE OR REPLACE MATERIALIZED LAKE VIEW mlv_learn.customer_rank AS
SELECT customer_id, customer_name, SUM(line_total) AS revenue,
 DENSE_RANK() OVER (ORDER BY SUM(line_total) DESC) AS revenue_rank
FROM mlv_learn.silver_sales GROUP BY customer_id, customer_name;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT after 05: Aroha 300 rank 1, Priya 75 rank 2.
SELECT * FROM mlv_learn.customer_rank ORDER BY revenue_rank, customer_id;
-- Window queries may require full refresh. Check the current supported-SQL reference.
-- An MLV holds the CURRENT derived state, not an SCD Type 2 history automatically.
-- For history, build a separately designed versioned source with validity intervals.
-- Avoid current_timestamp() in business definitions if a reproducible snapshot is needed.
-- EXERCISE: extend gold_daily_sales with AVG(line_total) in a NEW view and compare contracts.
-- OPTIONAL cross-lakehouse lab: use workspace.lakehouse.schema.table source names.
-- Verify permissions and enable Extended lineage in Manage before scheduling that chain.
-- Keep this base course in one lakehouse so it works without modifying existing shortcuts.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }
