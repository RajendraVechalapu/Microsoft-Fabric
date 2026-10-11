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

-- GOAL: compare an on-demand query with its stored MLV result.
-- PREREQUISITE: 01. IF NOT EXISTS does NOT update an existing definition.
-- Explicit output columns form a stable contract; avoid SELECT * in production definitions.
CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.completed_orders
COMMENT 'Learning: completed orders before quality checks'
TBLPROPERTIES ('delta.enableChangeDataFeed'='true')
AS SELECT order_id, customer_id, quantity, unit_price, order_ts,
          quantity * unit_price AS line_total
FROM mlv_learn.orders WHERE status='COMPLETED';

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT: 6 rows, including invalid and orphan rows. Filtering is not validation.
SELECT * FROM mlv_learn.completed_orders ORDER BY order_id;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

SHOW MATERIALIZED LAKE VIEWS IN mlv_learn;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

SHOW CREATE MATERIALIZED LAKE VIEW mlv_learn.completed_orders;
-- EXERCISE: sketch orders -> completed_orders in the lakehouse lineage Manage view.
-- A temporary view may help query experimentation, but cannot be an MLV source.
-- Never INSERT/UPDATE/DELETE an MLV: change its source or replace its definition.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

