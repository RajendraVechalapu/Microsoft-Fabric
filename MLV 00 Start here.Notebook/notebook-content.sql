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

-- GOAL: understand what a materialized lake view (MLV) is before creating one.
-- A regular view stores a query; an MLV stores the query result as managed Delta data.
-- Source changes require a refresh. Creation is not a continuous streaming subscription.
-- Use MLVs for reusable transformations, quality rules, and reporting aggregates.
-- Use Eventhouse/KQL for low-latency event exploration; lesson 08 explains the boundary.
-- PREREQUISITES: a Fabric capacity, write permissions, a schema-enabled lakehouse,
-- and a supported Fabric Spark runtime (Microsoft quickstart specifies Runtime 1.3).
-- This series defaults to LH_BRONZE_LAYER. Verify that attachment in Fabric before running.
-- If practicing in another workspace, reattach EVERY notebook to your training lakehouse.
-- All training objects use mlv_learn. Existing mlv_demo and business tables are untouched.
-- Run 01 through 09 in order, CELL BY CELL: several lessons pause for UI actions.
-- Do not schedule these lesson notebooks: use lakehouse-managed MLV schedules.
SELECT current_database() AS attached_database, current_timestamp() AS session_time;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- CHECK: confirm the lakehouse explorer has schemas and the MLV Manage ribbon.
-- If not, resolve prerequisites before proceeding; do not run this in the SQL endpoint.
SHOW SCHEMAS;
-- EXERCISE: explain storage cost vs query cost vs freshness in your own words.
-- Read the course README for setup, expected results, replay, and references.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

