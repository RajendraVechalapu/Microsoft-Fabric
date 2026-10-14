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

-- STEP 1: Create a demo schema + BRONZE source tables (raw data, with some bad rows on purpose).
-- Change Data Feed is enabled so MLVs can refresh incrementally.
CREATE SCHEMA IF NOT EXISTS mlv_demo;
CREATE TABLE IF NOT EXISTS mlv_demo.bronze_customers (customer_id INT, customer_name STRING, city STRING, segment STRING) USING DELTA TBLPROPERTIES (delta.enableChangeDataFeed = true);
CREATE TABLE IF NOT EXISTS mlv_demo.bronze_orders (order_id INT, customer_id INT, product STRING, quantity INT, unit_price DOUBLE, order_status STRING, order_ts TIMESTAMP) USING DELTA TBLPROPERTIES (delta.enableChangeDataFeed = true);
INSERT INTO mlv_demo.bronze_customers VALUES (1,'John Smith','Auckland','Retail'), (2,'Sarah Lee','Wellington','Corporate'), (3,'Mike Brown','Christchurch','Retail'), (4,'Priya Nair','Auckland','Corporate');
INSERT INTO mlv_demo.bronze_orders VALUES (101,1,'Laptop',1,1500.0,'COMPLETED',TIMESTAMP'2026-10-01 09:15:00'), (102,2,'Monitor',2,300.0,'COMPLETED',TIMESTAMP'2026-10-01 11:20:00'), (103,3,'Mouse',5,25.0,'COMPLETED',TIMESTAMP'2026-10-02 14:05:00'), (104,1,'Keyboard',-2,80.0,'COMPLETED',TIMESTAMP'2026-10-02 16:40:00'), (105,4,'Laptop',2,1450.0,'CANCELLED',TIMESTAMP'2026-10-03 10:00:00'), (106,2,'Headset',3,120.0,'COMPLETED',TIMESTAMP'2026-10-03 13:30:00'), (107,4,'Monitor',1,320.0,'COMPLETED',TIMESTAMP'2026-10-03 17:45:00');
SELECT * FROM mlv_demo.bronze_orders ORDER BY order_id;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- STEP 2: SILVER materialized lake view = cleaned + joined data, stored physically and kept up to date by Fabric.
-- CONSTRAINT ... ON MISMATCH DROP silently removes bad rows (quantity <= 0). Use FAIL instead to stop the refresh.
CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_demo.silver_orders (CONSTRAINT valid_quantity CHECK (quantity > 0) ON MISMATCH DROP) COMMENT 'Cleaned completed orders enriched with customer details' AS SELECT o.order_id, o.customer_id, c.customer_name, c.city, c.segment, o.product, o.quantity, o.unit_price, o.quantity * o.unit_price AS line_total, CAST(o.order_ts AS DATE) AS order_date FROM mlv_demo.bronze_orders o INNER JOIN mlv_demo.bronze_customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'COMPLETED';
SELECT * FROM mlv_demo.silver_orders ORDER BY order_id;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- STEP 3: GOLD materialized lake views built ON TOP OF the silver MLV (MLV -> MLV chaining creates a lineage DAG).
-- Business-ready aggregates for reports: sales per city per day, and a customer summary.
CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_demo.gold_daily_sales_by_city COMMENT 'Daily revenue per city' AS SELECT order_date, city, COUNT(order_id) AS total_orders, SUM(quantity) AS total_units, ROUND(SUM(line_total), 2) AS total_revenue FROM mlv_demo.silver_orders GROUP BY order_date, city;
CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_demo.gold_customer_summary COMMENT 'Lifetime value per customer' AS SELECT customer_id, customer_name, segment, COUNT(order_id) AS orders_count, ROUND(SUM(line_total), 2) AS lifetime_value, MAX(order_date) AS last_order_date FROM mlv_demo.silver_orders GROUP BY customer_id, customer_name, segment;
SELECT * FROM mlv_demo.gold_daily_sales_by_city ORDER BY order_date, city;
SELECT * FROM mlv_demo.gold_customer_summary ORDER BY lifetime_value DESC;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- STEP 4: New raw data lands in BRONZE (a new day of orders + a new customer + one bad row).
-- MLVs do not change by themselves after an insert: you REFRESH them (manually here, or on a schedule from the lakehouse UI).
-- Refresh order matters: upstream (silver) first, then downstream (gold). The scheduled refresh does this automatically via lineage.
INSERT INTO mlv_demo.bronze_customers VALUES (5,'Aroha Wiremu','Hamilton','Retail');
INSERT INTO mlv_demo.bronze_orders VALUES (108,5,'Laptop',1,1550.0,'COMPLETED',TIMESTAMP'2026-10-04 09:00:00'), (109,3,'Monitor',2,310.0,'COMPLETED',TIMESTAMP'2026-10-04 12:10:00'), (110,2,'Mouse',0,25.0,'COMPLETED',TIMESTAMP'2026-10-04 15:30:00');
REFRESH MATERIALIZED LAKE VIEW mlv_demo.silver_orders;
REFRESH MATERIALIZED LAKE VIEW mlv_demo.gold_daily_sales_by_city;
REFRESH MATERIALIZED LAKE VIEW mlv_demo.gold_customer_summary;
SELECT * FROM mlv_demo.gold_customer_summary ORDER BY lifetime_value DESC;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }
