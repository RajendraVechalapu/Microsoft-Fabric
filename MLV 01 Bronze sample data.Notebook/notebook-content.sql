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

-- GOAL: create deterministic source data. No external credentials are needed.
-- Bronze means raw source; silver means validated detail; gold means business aggregates.
-- IF NOT EXISTS preserves existing training data. Rerunning the seed MERGEs adds no duplicates.
-- A later lesson changes some rows: this notebook is not a destructive reset.
CREATE SCHEMA IF NOT EXISTS mlv_learn;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

CREATE TABLE IF NOT EXISTS mlv_learn.customers (
  customer_id INT, customer_name STRING, city STRING
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true');

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

CREATE TABLE IF NOT EXISTS mlv_learn.orders (
  order_id INT, customer_id INT, quantity INT, unit_price DECIMAL(12,2),
  status STRING, order_ts TIMESTAMP
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true');
-- CDF records changes AFTER enablement; it does not reconstruct older changes.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

MERGE INTO mlv_learn.customers t
USING (SELECT * FROM VALUES
 (1,'Aroha','Auckland'), (2,'Sam','Wellington'), (3,'Priya','Hamilton')
 AS v(customer_id,customer_name,city)) s
ON t.customer_id=s.customer_id
WHEN NOT MATCHED THEN INSERT *;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

MERGE INTO mlv_learn.orders t
USING (SELECT * FROM VALUES
 (101,1,2,CAST(100 AS DECIMAL(12,2)),'COMPLETED',TIMESTAMP '2026-10-01 09:00:00'),
 (102,2,1,CAST(300 AS DECIMAL(12,2)),'COMPLETED',TIMESTAMP '2026-10-01 10:00:00'),
 (103,1,-1,CAST(50 AS DECIMAL(12,2)),'COMPLETED',TIMESTAMP '2026-10-01 11:00:00'),
 (104,3,1,CAST(400 AS DECIMAL(12,2)),'CANCELLED',TIMESTAMP '2026-10-02 09:00:00'),
 (105,3,3,CAST(25 AS DECIMAL(12,2)),'COMPLETED',TIMESTAMP '2026-10-02 10:00:00'),
 (106,999,1,CAST(80 AS DECIMAL(12,2)),'COMPLETED',TIMESTAMP '2026-10-02 11:00:00'),
 (107,2,CAST(NULL AS INT),CAST(20 AS DECIMAL(12,2)),'COMPLETED',TIMESTAMP '2026-10-02 12:00:00')
 AS v(order_id,customer_id,quantity,unit_price,status,order_ts)) s
ON t.order_id=s.order_id
WHEN NOT MATCHED THEN INSERT *;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT on a fresh course: 7 orders, 3 customers. Bad rows are intentional.
SELECT * FROM mlv_learn.orders ORDER BY order_id;
-- EXERCISE: identify invalid quantity, missing quantity, orphan customer, cancelled order.
-- DECIMAL avoids binary floating-point surprises in financial totals.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

