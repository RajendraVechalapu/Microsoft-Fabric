# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Serve gold through a semantic model
# Prerequisites: 09-11. Spark writes gold; the Lakehouse SQL analytics endpoint reads Delta tables.
# Endpoint metadata synchronization may lag table creation. Check table discovery before proceeding.
# 
# 1. Open the Lakehouse SQL analytics endpoint. Run T-SQL `SELECT SUM(amount) FROM delta_lab_gold.fact_order;`.
#    Expected after 09: 500. Do not execute Spark MERGE in this endpoint.
# 2. From the Lakehouse choose **New semantic model**, selecting gold fact_order, dim_customer and dim_date.
#    Use a supported Direct Lake creation path in your workspace. Do not assume a default model exists.
# 3. Create one-to-many relationships dim_customer.customer_id -> fact_order.customer_id and
#    dim_date.order_date -> fact_order.order_date; use single-direction filtering from dimensions.
# 4. Add measures: `Revenue = SUM(fact_order[amount])` and `Orders = COUNTROWS(fact_order)`.
#    Table names in DAX must match the actual semantic-model names.
# 5. Build report cards for Revenue/Orders, a date revenue chart and a customer revenue table.
# 6. Verify Revenue=500 and Orders=5. Check customer/date filtering against notebook SQL.
# 7. Change source data, run PL_DELTA_LAB, then refresh/reframe the semantic model as appropriate
#    for its Direct Lake configuration and reload report visuals. Measure each latency boundary.
# 8. Optional security exercise: add a test role in the model and use Test as role before sharing.
# 
# Why star schema: dimensions filter facts consistently; duplicate dimension keys break the one side.
# Why semantic refresh still matters: new Delta commits and model metadata/frames are different states.
# Direct Lake, Import refresh, source ingestion and MLV refresh are distinct operations.
# This notebook does not publish reports or change permissions automatically.

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from decimal import Decimal
import uuid
spark.conf.set("spark.sql.session.timeZone", "UTC")
# WHAT: all tables use dedicated training schemas in the attached default Lakehouse.
# WHY: isolation makes it possible to experiment without changing your MLV course.
def sql(query):
    return spark.sql(query)
def show(query):
    display(sql(query))
show('SELECT COUNT(*) AS active_orders, SUM(amount) AS revenue FROM delta_lab_gold.fact_order')
show("""SELECT c.customer_name, SUM(f.amount) AS revenue FROM delta_lab_gold.fact_order f
 JOIN delta_lab_gold.dim_customer c ON c.customer_id=f.customer_id GROUP BY c.customer_name""")
assert sql('SELECT customer_id FROM delta_lab_gold.dim_customer GROUP BY customer_id HAVING COUNT(*)>1').count()==0
assert sql('SELECT order_date FROM delta_lab_gold.dim_date GROUP BY order_date HAVING COUNT(*)>1').count()==0

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
