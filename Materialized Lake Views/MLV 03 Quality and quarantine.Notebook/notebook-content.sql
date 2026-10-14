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

-- GOAL: retain valid facts and expose rejects for remediation.
-- PREREQUISITES: 01-02. Constraints evaluate projected output columns.
-- Explicit IS NOT NULL avoids relying on three-valued SQL null semantics.
CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.valid_orders (
 CONSTRAINT valid_quantity CHECK (quantity IS NOT NULL AND quantity > 0) ON MISMATCH DROP,
 CONSTRAINT valid_price CHECK (unit_price IS NOT NULL AND unit_price >= 0) ON MISMATCH DROP
)
TBLPROPERTIES ('delta.enableChangeDataFeed'='true')
AS SELECT order_id, customer_id, quantity, unit_price, order_ts, line_total
FROM mlv_learn.completed_orders;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- Quarantine is a separate materialization: DROP does not save rejected rows for you.
CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.rejected_orders AS
SELECT order_id, customer_id, quantity, unit_price,
 CASE WHEN quantity IS NULL THEN 'missing_quantity'
      WHEN quantity <= 0 THEN 'nonpositive_quantity' ELSE 'invalid_price' END AS reject_reason
FROM mlv_learn.completed_orders
WHERE quantity IS NULL OR quantity <= 0 OR unit_price IS NULL OR unit_price < 0;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT: 4 valid, 2 rejected (103 and 107). Customer 999 still needs a join check.
SELECT * FROM mlv_learn.rejected_orders ORDER BY order_id;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- OPTIONAL FAILURE EXERCISE: copy the commented statement into its own cell.
-- Expected: creation/refresh fails because orders 103 and 107 violate the rule.
-- Do not include this intentional failure in Run all or a production schedule.
-- CREATE MATERIALIZED LAKE VIEW mlv_learn.strict_orders (
--  CONSTRAINT qty_required CHECK (quantity IS NOT NULL AND quantity > 0) ON MISMATCH FAIL
-- ) AS SELECT order_id, quantity FROM mlv_learn.completed_orders;
-- Recover by fixing source data, or removing this optional test view if it was created.
-- EXERCISE: when should an invalid financial row fail the entire refresh instead of drop?

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }
