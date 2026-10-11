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

-- GOAL: independently build a small sales analytics pipeline and prove correctness.
-- PREREQUISITES: 01-08. After 05, expected silver revenue is 375.
-- TASK A: define a NEW customer summary MLV with count, revenue and last order date.
-- TASK B: add a source order 109 for customer 3, quantity 2, price 25, completed Oct 3.
-- Use MERGE by order_id so replay does not duplicate it.
-- TASK C: include your new view and upstream views in the managed refresh scope.
-- TASK D: reconcile detail and gold. EXPECT total revenue 425; Priya total 125.
-- TASK E: cancel 109, refresh, prove revenue returns to 375.
-- TASK F: repair orphan 106 by adding customer 999; refresh. EXPECT revenue 455.
-- TASK G: document freshness target, quality policy, duplicate strategy and run cost.
-- Do tasks one at a time; expectations depend on completing prior steps exactly.
SELECT SUM(line_total) AS starting_revenue FROM mlv_learn.silver_sales;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- OPTIONAL RESET: first stop event sources and disable/delete ALL course schedules.
-- Export any work you want to keep. These statements DELETE only named course objects.
-- They are COMMENTS intentionally: copy needed statements into individual cells yourself.
-- Drop your custom capstone/live views first, then known downstream views before sources.
-- DROP MATERIALIZED LAKE VIEW mlv_learn.device_minute;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.valid_events;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.customer_rank;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.sales_by_date;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.gold_daily_sales;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.orphan_orders;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.silver_sales;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.rejected_orders;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.valid_orders;
-- DROP MATERIALIZED LAKE VIEW mlv_learn.completed_orders;
-- DROP TABLE mlv_learn.device_events;
-- DROP TABLE mlv_learn.orders;
-- DROP TABLE mlv_learn.customers;
-- If strict_orders exists from the optional FAIL exercise, drop it before completed_orders.
-- Missing objects: skip their statements. Do not use a broad DROP SCHEMA CASCADE.
-- Keep mlv_learn schema. Run 01 onward again to rebuild baseline data.
-- Git stores definitions and notebook text, not lakehouse rows or live Eventstream messages.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

