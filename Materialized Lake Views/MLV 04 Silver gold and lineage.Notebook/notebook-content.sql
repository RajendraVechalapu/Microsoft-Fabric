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

-- Display Customers from FROM mlv_learn.customers
SELECT * FROM mlv_learn.customers;

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

CREATE TABLE IF NOT EXISTS mlv_learn.valid_orders (
    order_id INT,
    customer_id INT,
    quantity INT,
    unit_price DECIMAL(12,2),
    line_total DECIMAL(14,2),
    order_ts TIMESTAMP
)
USING DELTA
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- Insert sample orders only when their customer exists.
-- MERGE prevents duplicate order IDs when rerunning this cell.
MERGE INTO mlv_learn.valid_orders AS target
USING (
    SELECT
        v.order_id,
        c.customer_id,
        v.quantity,
        CAST(v.unit_price AS DECIMAL(12,2)) AS unit_price,
        CAST(v.quantity * v.unit_price AS DECIMAL(14,2)) AS line_total,
        v.order_ts
    FROM VALUES
        (101, 1, 2, 100.00, TIMESTAMP '2026-10-01 09:00:00'),
        (102, 2, 1, 300.00, TIMESTAMP '2026-10-01 10:00:00'),
        (105, 3, 3,  25.00, TIMESTAMP '2026-10-02 10:00:00')
    AS v(order_id, customer_id, quantity, unit_price, order_ts)
    INNER JOIN (
        SELECT DISTINCT customer_id
        FROM mlv_learn.customers
    ) c ON v.customer_id = c.customer_id
) AS source
ON target.order_id = source.order_id
WHEN NOT MATCHED THEN INSERT *;

-- Add the orphan order used by the notebook's orphan exercise.
-- Customer 999 should not exist in mlv_learn.customers.
MERGE INTO mlv_learn.valid_orders AS target
USING (
    SELECT
        106 AS order_id,
        999 AS customer_id,
        1 AS quantity,
        CAST(80.00 AS DECIMAL(12,2)) AS unit_price,
        CAST(80.00 AS DECIMAL(14,2)) AS line_total,
        TIMESTAMP '2026-10-02 11:00:00' AS order_ts
) AS source
ON target.order_id = source.order_id
WHEN NOT MATCHED THEN INSERT *;

SELECT * FROM mlv_learn.valid_orders ORDER BY order_id;

-- CELL ********************

-- Display customers
SELECT * FROM mlv_learn.customers order by customer_id;

-- CELL ********************

SELECT o.order_id, o.customer_id, c.customer_name, c.city,
 o.quantity, o.unit_price, o.line_total, CAST(o.order_ts AS DATE) AS order_date
FROM mlv_learn.valid_orders o
INNER JOIN mlv_learn.customers c ON o.customer_id=c.customer_id;

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

-- Display records from the silver_sales materialized lake view.
SELECT * FROM mlv_learn.silver_sales ORDER BY order_id;

-- CELL ********************

select * from mlv_learn.valid_orders

-- CELL ********************

-- To test materialized lake view lineage, we will add a record to the source table and verify that it is reflected in the materialized lake view.
INSERT INTO mlv_learn.valid_orders VALUES (107, 1, 5, 50.00, 250.00, TIMESTAMP '2026-10-03 09:00:00');

-- CELL ********************

SELECT o.order_id, o.customer_id, c.customer_name, c.city,
 o.quantity, o.unit_price, o.line_total, CAST(o.order_ts AS DATE) AS order_date
FROM mlv_learn.valid_orders o
INNER JOIN mlv_learn.customers c ON o.customer_id=c.customer_id;

-- CELL ********************

-- Display records from the silver_sales materialized lake view.
SELECT * FROM mlv_learn.silver_sales ORDER BY order_id;

-- CELL ********************

REFRESH MATERIALIZED LAKE VIEW mlv_learn.silver_sales FULL;

-- CELL ********************

-- DISPLAY records from the silver_sales materialized lake view.
SELECT * FROM mlv_learn.silver_sales ORDER BY order_id;

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
