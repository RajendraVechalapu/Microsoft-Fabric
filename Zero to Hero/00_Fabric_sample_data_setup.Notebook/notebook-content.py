# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "c5416f9f-9901-4acf-b668-7852eb4d2ca2",
# META       "default_lakehouse_name": "lh_RV_Fabric_2026",
# META       "default_lakehouse_workspace_id": "ad71507f-ecc6-4358-ae9a-07bcdcecb051"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Fabric Sample Data Setup
# 
# Run this notebook once before the file-based lessons. It creates small synthetic CSV, JSON, Parquet, and ORC practice data in the attached Lakehouse under `Files/data/input/`. Running it again replaces only those sample paths.
# 
# The data is intentionally small for learning and is not suitable for performance benchmarking.


# CELL ********************

import csv
import io
import json

from pyspark.sql import Row


def _csv_text(headers, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def _put_text(path, text):
    parent = path.rsplit("/", 1)[0]
    notebookutils.fs.mkdirs(parent)
    notebookutils.fs.put(path, text, True)


employees = [
    (1, 10, "Ava Chen", 29, "F", 82000.0, "2021-03-15"),
    (2, 20, "Noah Patel", 35, "M", 91000.0, "2019-07-01"),
    (3, 10, "Mia Wilson", 31, "F", 87000.0, "2020-11-20"),
    (4, 30, "Liam Jones", 42, "M", 105000.0, "2017-02-10"),
    (5, 20, "Zoe Singh", 26, "F", 76000.0, "2022-06-05"),
]
employee_headers = ["employee_id", "department_id", "name", "age", "gender", "salary", "hire_date"]
_put_text("Files/data/input/emp.csv", _csv_text(employee_headers, employees))
_put_text("Files/data/input/emp_new.csv", _csv_text(employee_headers, employees + [
    (6, 10, "Bad Row", "not-an-age", "X", "not-a-salary", "2024-01-01")
]))

record_headers = ["first_name", "last_name", "job_title", "dob", "email", "phone", "salary", "department_id"]
records = [
    ("Ava", "Chen", "Engineer", "1995-04-12", "ava@example.com", "555-0101", 82000.0, 10),
    ("Noah", "Patel", "Analyst", "1990-09-03", "noah@example.com", "555-0102", 91000.0, 20),
    ("Mia", "Wilson", "Engineer", "1993-01-22", "mia@example.com", "555-0103", 87000.0, 10),
    ("Liam", "Jones", "Manager", "1982-12-08", "liam@example.com", "555-0104", 105000.0, 30),
    ("Zoe", "Singh", "Analyst", "1998-07-17", "zoe@example.com", "555-0105", 76000.0, 20),
    ("Ethan", "Brown", "Engineer", "1988-03-30", "ethan@example.com", "555-0106", 99000.0, 10),
]
skewed_records = [(a, b, c, d, e, f, g, 10 if i < 5 else h) for i, (a, b, c, d, e, f, g, h) in enumerate(records)]

_dept_rows = [
    (10, "Engineering", "Builds products", "Auckland", "AUK", "New Zealand"),
    (20, "Analytics", "Analyzes data", "Sydney", "NSW", "Australia"),
    (30, "Operations", "Runs services", "Mumbai", "MH", "India"),
]
_dept_headers = ["department_id", "department_name", "description", "city", "state", "country"]
_city_headers = ["city_id", "city", "state", "state_abv", "country"]
_cities = [
    ("C1", "Auckland", "Auckland", "AUK", "New Zealand"),
    ("C2", "Sydney", "New South Wales", "NSW", "Australia"),
    ("C3", "Mumbai", "Maharashtra", "MH", "India"),
    ("C4", "Accra", "Greater Accra", "GA", "Ghana"),
    ("C5", "Tehran", "Tehran", "THR", "Iran"),
]
_sales_headers = ["transacted_at", "trx_id", "retailer_id", "description", "amount", "city_id"]
_sales_rows = [
    ("2024-01-01 10:00:00", "1734117021", "R1", "Book", 25.5, "C1"),
    ("2024-01-02 11:30:00", "1734117022", "R2", "Keyboard", 79.0, "C2"),
    ("2024-01-03 12:15:00", "1734117023", "R1", "Mouse", 19.5, "C3"),
    ("2024-01-04 09:45:00", "1734117024", "R3", "Monitor", 199.0, "C4"),
    ("2024-01-05 14:20:00", "1734117025", "R2", "Cable", 12.0, "C5"),
]

for path, headers, rows in [
    ("Files/data/input/employee_records.csv", record_headers, records),
    ("Files/data/input/employee_records_skewed.csv", record_headers, skewed_records),
    ("Files/data/input/datasets/employee_records.csv", record_headers, records),
    ("Files/data/input/datasets/employee_records_skewed.csv", record_headers, skewed_records),
    ("Files/data/input/department_data.csv", _dept_headers, _dept_rows),
    ("Files/data/input/datasets/department_data.csv", _dept_headers, _dept_rows),
    ("Files/data/input/cities.csv", _city_headers, _cities),
    ("Files/data/input/datasets/cities.csv", _city_headers, _cities),
    ("Files/data/input/new_sales.csv", _sales_headers, _sales_rows),
    ("Files/data/input/datasets/new_sales.csv", _sales_headers, _sales_rows),
]:
    _put_text(path, _csv_text(headers, rows))

retail_headers = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country"]
retail_rows = [
    ("576394", "A100", "Notebook", 2, "2024-01-01 09:00:00", 4.5, "C100", "Australia"),
    ("576395", "A101", "Pen", 5, "2024-01-02 10:00:00", 1.2, "C101", "Australia"),
    ("576396", "B200", "Mug", 1, "2024-01-03 11:00:00", 8.0, "C102", "New Zealand"),
    ("576397", "B201", "Folder", 3, "2024-01-04 12:00:00", 2.0, "C103", "India"),
]
_put_text("Files/data/input/sales/sales.csv", _csv_text(retail_headers, retail_rows))

single_line_orders = [
    {"customer_id": "C001", "order_id": "O001", "contact": [6421000001, 6421000002], "order_line_items": [{"item_id": "I100", "amount": 25.5, "qty": 1}]},
    {"customer_id": "C002", "order_id": "O002", "contact": [6421000003], "order_line_items": [{"item_id": "I101", "amount": 12.0, "qty": 2}]},
]
_put_text("Files/data/input/order_singleline.json", "\n".join(json.dumps(row) for row in single_line_orders) + "\n")
_put_text("Files/data/input/order_multiline.json", json.dumps(single_line_orders, indent=2) + "\n")
_put_text("Files/data/input/oom_example/words.txt", "small sample for safe memory practice\n" * 20)

sales_df = spark.createDataFrame([
    Row(trx_id=row[1], amount=float(row[4]), retailer_id=row[2], description=row[3], city_id=row[5])
    for row in _sales_rows
])
for path, writer in [
    ("Files/data/input/sales_data.parquet", "parquet"),
    ("Files/data/input/sales_total_parquet", "parquet"),
    ("Files/data/input/sales_recursive/sales_1/1.parquet", "parquet"),
    ("Files/data/input/sales_recursive/sales_1/sales_2/2.parquet", "parquet"),
    ("Files/data/input/sales_data.orc", "orc"),
    ("Files/data/input/sales_total_orc", "orc"),
    ("Files/data/input/nyctaxi/parquet", "parquet"),
]:
    frame = sales_df
    if "nyctaxi" in path:
        frame = spark.createDataFrame([
            Row(vendor_id="VTS", trip_distance=2.4, passenger_count=1),
            Row(vendor_id="VTS", trip_distance=0.8, passenger_count=2),
            Row(vendor_id="CMT", trip_distance=3.1, passenger_count=1),
            Row(vendor_id="VTS", trip_distance=5.0, passenger_count=3),
        ])
    getattr(frame.write.mode("overwrite"), writer)(path)

print("Synthetic Fabric practice files are ready under Files/data/input.")
print("These samples are intentionally small; use the Spark UI for execution plans, not benchmarking.")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
