# Materialized lake views: hands-on Fabric course

Ten native Fabric notebooks take you from a stored query result to an operated analytics pipeline. Use Spark SQL in Fabric notebooks, not the lakehouse SQL analytics endpoint. The original notebooks and lakehouse metadata have been preserved.

## Setup and Git workflow

1. Commit and push the new `MLV *.Notebook` folders and this guide to the branch connected to your Fabric workspace. Each notebook needs both `.platform` and `notebook-content.sql`; keep its logical ID stable in later commits.
2. In Fabric, open workspace Source control, review the incoming changes, and update from Git. Cloning a repo locally does not execute or deploy its notebooks by itself.
3. Open `MLV 00 Start here`. Verify its default lakehouse is **LH_BRONZE_LAYER**, that lakehouse schemas are enabled, and the workspace has a Fabric capacity and a supported Spark runtime. Microsoft's quickstart specifies Runtime 1.3. You need permissions to create tables/views and run refreshes.
4. The notebook attachment metadata follows your existing notebook. When importing into a different workspace or lakehouse, reattach every lesson to the intended training lakehouse in Fabric; identifiers are workspace-specific. If Git sync does not resolve an attachment, select it manually and save the notebook.
5. Run the notebooks below in order, **cell by cell**. Pause at the UI instructions in lessons 05 and 08. Do not blindly Run all through those pauses. Learning comments appear directly in each SQL cell.

The course creates only objects in `mlv_learn`. It does not reset your existing `mlv_demo` tables. Use a separate training lakehouse if you prefer isolation, and update the notebook attachments first. Source and refresh execution use your Fabric capacity.

## Course map

| Notebook | What you practice | Prerequisite |
|---|---|---|
| [00 Start here](MLV%2000%20Start%20here.Notebook/notebook-content.sql) | Concepts, prerequisites, lakehouse attachment | None |
| [01 Bronze sample data](MLV%2001%20Bronze%20sample%20data.Notebook/notebook-content.sql) | Delta tables, CDF, replayable seed data | 00 |
| [02 First materialized lake view](MLV%2002%20First%20materialized%20lake%20view.Notebook/notebook-content.sql) | Create, query, list, inspect a definition | 01 |
| [03 Quality and quarantine](MLV%2003%20Quality%20and%20quarantine.Notebook/notebook-content.sql) | DROP/FAIL, explicit null checks, rejected rows | 02 |
| [04 Silver gold and lineage](MLV%2004%20Silver%20gold%20and%20lineage.Notebook/notebook-content.sql) | Joins, orphans, aggregates, dependency graph | 03 |
| [05 Refresh and source changes](MLV%2005%20Refresh%20and%20source%20changes.Notebook/notebook-content.sql) | Staleness, inserts, corrections, managed refresh | 04 |
| [06 Advanced modeling and performance](MLV%2006%20Advanced%20modeling%20and%20performance.Notebook/notebook-content.sql) | Replace definitions, partitioning, ranking, history | 05 |
| [07 Operations and troubleshooting](MLV%2007%20Operations%20and%20troubleshooting.Notebook/notebook-content.sql) | Reconciliation, monitoring, failures, CDF checks | 06 |
| [08 Near real time events](MLV%2008%20Near%20real%20time%20events.Notebook/notebook-content.sql) | Micro-batches, late events, optional live Eventstream | 01; read 05 first |
| [09 Capstone and safe reset](MLV%2009%20Capstone%20and%20safe%20reset.Notebook/notebook-content.sql) | Independent project, acceptance checks, optional cleanup | 01–08 |

Allow approximately 20–40 minutes per lesson plus Spark startup and refresh time. The advanced performance sample teaches query-plan inspection; seven source rows cannot establish a useful performance benchmark.

## Refresh practice

In the lakehouse, select **Materialized lake views > Manage > Manage schedules**. Create a practice schedule with a selected scope containing **all course views in the chain**. Inspect the scope before saving so unrelated views are excluded. Use **Run** on that schedule for an immediate managed refresh, and wait for successful completion before running the next verification cell. Single-view Run does not refresh all its upstream materializations.

For the sales chain, include `completed_orders`, `valid_orders`, `rejected_orders`, `silver_sales`, `orphan_orders`, and `gold_daily_sales`. Add `sales_by_date`, `customer_rank`, and any capstone views after creating them. The events chain independently includes `valid_events` and `device_minute`. Choose a time-based practice cadence of at least five minutes if you enable recurrence; pause it when finished.

CDF enables eligible incremental processing; actual strategy also depends on the definition, change pattern and engine decision. Updates/deletes can fall back to a full refresh. Observe the reported strategy rather than assuming incremental processing. Optional preview features may vary by workspace; the core course uses table-based Spark SQL definitions and managed time-based refresh.

## Expected checkpoints

These checkpoints assume a fresh course and no extra exercise mutations.

| Stage | Expected result |
|---|---|
| 01 | 7 source orders, 3 customers |
| 02 | 6 completed rows |
| 03 | 4 valid rows, 2 rejects (103 and 107) |
| 04 | 3 silver rows; revenue 575; orphan 106 |
| 05 first graph refresh | 4 silver rows; revenue 625 |
| 05 correction/cancellation refresh | 3 silver rows; revenue 375 |
| 06 customer ranking | Aroha 300, Priya 75 |
| 07 reconciliation | Zero difference rows while ingestion is paused |
| 08 initial / late-arrival refresh | Sensor count 2 / 3; average 25 / 30 |

Seed MERGEs prevent duplicate inserts on replay but do not undo later changes. `IF NOT EXISTS` preserves an existing MLV definition, so edits require `CREATE OR REPLACE` and a downstream refresh. To return to the starting dataset, use the commented cleanup in 09, then rerun from 01. Cleanup is deliberately never executed by Run all. Drop optional/custom dependent views before their sources, and stop ingestion and schedules first.

## Optional real Eventstream integration

Lesson 08 runs immediately with simulated micro-batches. To turn it into a live exercise, create an Eventstream source and a **new dedicated Lakehouse destination table**, using the linked Microsoft tutorial. That external resource setup is manual; this repo does not provision Eventstreams or store credentials.

Example custom-source message:

```json
{"event_id":"live-001","device_id":"sensor-a","event_ts":"2026-10-11T08:00:10Z","ingested_at":"2026-10-11T08:00:12Z","temperature":24.5}
```

Use current UTC timestamps when generating live events and establish a consistent UTC interpretation in your mappings. Map strings/timestamps/numbers explicitly in Eventstream, inspect the resulting table schema, and copy lesson 08's definitions into `live_valid_events` and `live_device_minute` using that table's actual namespace. Add source CDF where supported. Select both views in their managed schedule and verify a lakehouse commit followed by a successful refresh. For production, stamp ingestion time at ingestion rather than trusting the sender's clock. Transport and sink retries can produce duplicates: stable IDs alone do not remove them from an append-only table.

Time-based MLV refresh currently has a minimum effective interval of five minutes. Event-triggered refresh is a preview option using supported ingestion or job events; it still runs refresh jobs. Measure source-to-report latency across sink commits, waiting, computation and serving. Use Eventhouse/KQL when the goal is low-latency event exploration. Stop your sender/Eventstream and pause refresh after practice.

## Reference and validation

Reviewed against Microsoft documentation on 11 October 2026:

- [MLV concepts](https://learn.microsoft.com/en-us/fabric/data-engineering/materialized-lake-views/overview-materialized-lake-view)
- [Prerequisites and quickstart](https://learn.microsoft.com/en-us/fabric/data-engineering/materialized-lake-views/get-started-with-materialized-lake-views)
- [Spark SQL syntax and limitations](https://learn.microsoft.com/en-us/fabric/data-engineering/materialized-lake-views/create-materialized-lake-view)
- [Quality constraints](https://learn.microsoft.com/en-us/fabric/data-engineering/materialized-lake-views/data-quality)
- [Refresh optimization](https://learn.microsoft.com/en-us/fabric/data-engineering/materialized-lake-views/refresh-materialized-lake-view)
- [Scheduling and event-triggered preview](https://learn.microsoft.com/en-us/fabric/data-engineering/materialized-lake-views/schedule-lineage-run)
- [Eventstream to Lakehouse tutorial](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/event-streams/transform-and-stream-real-time-events-to-lakehouse)

Local validation checks notebook structure, JSON metadata, unique logical IDs and sample arithmetic. Fabric-only SQL creation, Git sync, refresh strategy, schedules and live ingestion require execution in your workspace. Git stores notebook definitions, not source rows, refresh schedules or live messages.
