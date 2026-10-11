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

-- GOAL: build reusable enriched facts and chained reporting aggregates.
-- PREREQUISITES: 01-03. Customers must have one row per key to prevent join fan-out.
SELECT customer_id, COUNT(*) AS copies FROM mlv_learn.customers
GROUP BY customer_id HAVING COUNT(*) > 1;
-- EXPECT: no rows. A CHECK constraint does not enforce uniqueness across rows.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.silver_sales
TBLPROPERTIES ('delta.enableChangeDataFeed'='true') AS
SELECT o.order_id, o.customer_id, c.customer_name, c.city,
 o.quantity, o.unit_price, o.line_total, CAST(o.order_ts AS DATE) AS order_date
FROM mlv_learn.valid_orders o
INNER JOIN mlv_learn.customers c ON o.customer_id=c.customer_id;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- Orphans excluded by the inner join are made visible separately.
CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.orphan_orders AS
SELECT o.order_id, o.customer_id FROM mlv_learn.valid_orders o
LEFT JOIN mlv_learn.customers c ON o.customer_id=c.customer_id
WHERE c.customer_id IS NULL;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.gold_daily_sales AS
SELECT order_date, city, COUNT(*) AS order_count,
 SUM(quantity) AS units, SUM(line_total) AS revenue
FROM mlv_learn.silver_sales GROUP BY order_date, city;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT: 3 silver rows; total revenue 575.00.
-- Gold: Oct 1 Auckland 200, Wellington 300; Oct 2 Hamilton 75.
SELECT * FROM mlv_learn.gold_daily_sales ORDER BY order_date, city;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT: 106 is the single orphan. Account for every completed order:
-- 6 completed = 2 rejected + 1 orphan + 3 silver.
SELECT * FROM mlv_learn.orphan_orders;
-- UI: Lakehouse > Materialized lake views > Manage. Follow bronze -> gold dependencies.
-- EXERCISE: add a gold_customer_sales MLV grouped by customer_id and customer_name.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

