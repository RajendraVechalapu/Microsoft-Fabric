# Microsoft Fabric Delta Lake: end-to-end lab

Fifteen native Fabric PySpark notebooks teach initial ingestion, Delta storage, incremental extraction, MERGE, quality, deletes, late arrivals, CDF, recovery, orchestration and Power BI. Code cells include comments explaining what happens and why. Each lesson includes prerequisites, expected results and an exercise.

## Start in Fabric

1. Commit and push the `DELTA *.Notebook` folders to the branch connected to your Fabric workspace, then review and update from Git in Fabric Source control. Local file creation does not deploy or execute anything.
2. Create a dedicated schema-enabled Lakehouse, for example `LH_DELTA_LAB`, on a workspace with Fabric capacity. Attach **every** DELTA notebook to this same Lakehouse and save. The notebooks deliberately contain no workspace-specific attachment IDs.
3. Run lessons 00 through 14 **cell by cell**, in order. Use PySpark/Spark in Fabric, not the Lakehouse SQL analytics endpoint. Lesson 09 contains an expected exception: continue manually with its recovery cell.
4. Pause at the UI instructions in 11 and 12. They explain how to create your pipeline, semantic model and report; repository files do not provision those resources automatically.
5. Run only one batch writer at a time. Concurrent runs require a locking or transactional coordination design beyond this lab.

All training objects use `delta_lab_source`, `delta_lab_bronze`, `delta_lab_silver`, `delta_lab_gold` and `delta_lab_ops`. Landing files use `Files/delta_lab`. Existing MLV course objects are separate. Allow about 45–90 minutes per lesson, with additional time for UI setup.

## Course sequence

| Notebook | Learning outcome |
|---|---|
| [00 Start here](DELTA%2000%20Start%20here.Notebook/notebook-content.py) | Fabric setup, schemas, terminology and isolation |
| [01 Source and control tables](DELTA%2001%20Source%20and%20control%20tables.Notebook/notebook-content.py) | Reproducible source, keys, money types, UTC, durable controls |
| [02 Delta anatomy and time travel](DELTA%2002%20Delta%20anatomy%20and%20time%20travel.Notebook/notebook-content.py) | Transaction log, data files, history, versions and query plans |
| [03 Initial full extraction](DELTA%2003%20Initial%20full%20extraction.Notebook/notebook-content.py) | Fixed source snapshot, bounded extraction, immutable landing |
| [04 Bronze silver and quality](DELTA%2004%20Bronze%20silver%20and%20quality.Notebook/notebook-content.py) | Raw snapshots, validations, quarantine, deduplication and MERGE |
| [05 Gold star schema and reconciliation](DELTA%2005%20Gold%20star%20schema%20and%20reconciliation.Notebook/notebook-content.py) | Fact grain, customer/date dimensions, daily sales, checkpoint commit |
| [06 Incremental insert and bounded extraction](DELTA%2006%20Incremental%20insert%20and%20bounded%20extraction.Notebook/notebook-content.py) | Watermarks, an insert, source ordering assumptions |
| [07 Corrections deletes late arrivals and replay](DELTA%2007%20Corrections%20deletes%20late%20arrivals%20and%20replay.Notebook/notebook-content.py) | Updates, soft deletes, old business dates and actual batch replay |
| [08 Change data feed and version checkpoints](DELTA%2008%20Change%20data%20feed%20and%20version%20checkpoints.Notebook/notebook-content.py) | Bounded CDF reads, update images, hard deletes and consumer progress |
| [09 Failure recovery and idempotency](DELTA%2009%20Failure%20recovery%20and%20idempotency.Notebook/notebook-content.py) | Intentional partial failure and recovery with saved bounds/files |
| [10 Pipeline batch runner](DELTA%2010%20Pipeline%20batch%20runner.Notebook/notebook-content.py) | Self-contained parameterized runner, audit, failed activity propagation |
| [11 Fabric Data Factory orchestration](DELTA%2011%20Fabric%20Data%20Factory%20orchestration.Notebook/notebook-content.py) | Pipeline UI steps, retries, schedules and real-source extension |
| [12 SQL endpoint semantic model and Power BI](DELTA%2012%20SQL%20endpoint%20semantic%20model%20and%20Power%20BI.Notebook/notebook-content.py) | Read-only T-SQL, Direct Lake, relationships, DAX and reports |
| [13 Operations maintenance and MLV extension](DELTA%2013%20Operations%20maintenance%20and%20MLV%20extension.Notebook/notebook-content.py) | History, audit, OPTIMIZE, VACUUM dry run and existing MLV course integration |
| [14 Capstone acceptance and safe reset](DELTA%2014%20Capstone%20acceptance%20and%20safe%20reset.Notebook/notebook-content.py) | End-to-end acceptance, independent challenge and disabled cleanup |

## Expected checkpoints

These results assume a fresh lab and no optional mutations.

| After | Active orders | Revenue | Other check |
|---|---:|---:|---|
| 01 | Source has 3 | Source 600 | Watermark remains 1900-01-01 |
| 03 | No silver yet | — | 3 landed rows; pending batch exists |
| 04 | 3 silver | 600 | No checkpoint advance yet |
| 05 | 3 gold | 600 | Initial watermark Jan 1, 2026 at 10:00 UTC |
| 06 | 4 | 650 | Insert 104 |
| 07 correction | 4 | 700 | Order 102 becomes 250 |
| 07 deletion | 3 | 400 | Order 103 retained as silver tombstone |
| 07 late arrival/replay | 4 | 475 | Order 105; replay leaves bronze count unchanged |
| 09 intentional failure | Silver 5; gold 4 | Silver 500; gold 475 | Pending retained, watermark still Jan 5 |
| 09 recovery | 5 | 500 | Silver 6; bronze 8; pending empty; watermark Jan 6 |
| 10 no-change run | 5 | 500 | Audit status NO_CHANGES |

Rerunning a seed or MERGE does not restore the original dataset. Earlier stage assertions can fail after later lessons legitimately change the state. To repeat the complete sequence, use the explicit reset option in 14 after stopping consumers, then rerun from 00. Do not set reset to true during normal course execution.

## What is incremental here?

The first extract is a full load. Later extraction reads only rows in a saved timestamp interval. Bronze preserves extracted states by batch; silver MERGEs current business state. Gold is deliberately rebuilt in full because the dataset is tiny: a scalable incremental gold extension must retain both old and new affected dates, including dates with zero remaining rows.

The simulated operational source is itself a Delta table so the extraction can pin its version. It needs no external credentials. Lesson 11 describes replacing it with a connected SQL/Fabric Warehouse source; that extension requires adapting the extraction helper to the external landing path.

Watermark extraction assumes reliable change timestamps and visibility ordering. It cannot detect source hard deletes and can miss delayed commits behind the watermark. Soft-delete flags address deletes in the core course; overlap/deduplication or source CDC addresses more demanding source contracts. The separate CDF exercise demonstrates physical deletes in a committed Delta source.

The checkpoints and targets are separate Delta tables. There is no cross-table atomic transaction. Saved pending batches and idempotent application make the demonstrated retry recoverable; this is a learning implementation with one writer, not a production concurrency framework. Landing files and pending state must remain available until processing completes.

## Troubleshooting

- **Schema/table not found:** verify notebook default Lakehouse, schema support, and completion of 00/01. Do not attach different lessons to different Lakehouses.
- **Expected failure in 09:** run the next inspection/recovery cell; do not advance the watermark by hand.
- **Rejected batch:** inspect quarantine. Its fixed landing files remain unchanged even if the source is corrected. Preserve the evidence and explicitly abandon the failed pending row only when ready to re-extract from the unchanged watermark. Production needs a defined repair workflow.
- **No new changes:** confirm the source modification has a timestamp greater than the committed watermark; changing only order_date is insufficient.
- **SQL endpoint missing a table:** check metadata synchronization and ensure the table is registered Delta under the Lakehouse Tables area.
- **Report is stale:** check source commit, pipeline outcome, gold reconciliation, semantic model refresh/frame and report visual refresh separately.
- **Pipeline parameters ignored:** mark lesson 10's first cell as Parameters in Fabric and configure matching base parameter names/types on the Notebook activity.
- **CDF version unavailable:** retention may have removed the required history. Rebaseline the consumer using a consistent snapshot and a corresponding version, then resume from the next version.

## Local validation and references

Run `python tools/validate_delta_course.py` to check Python cell syntax, Fabric metadata, unique logical IDs, isolation declarations and the sample arithmetic/retry model. Run `python tools/build_delta_course.py` to regenerate notebooks; logical IDs remain stable. Edit that generator when maintaining course content so regeneration preserves your edits.

Local checks do not execute Spark or certify Fabric Git import, SQL compatibility, capacity/runtime configuration, pipeline activities or report refresh. Execute notebook assertions in Fabric to validate those behaviors.

Microsoft references reviewed for this course on 14 October 2026:

- [Fabric notebook definitions and source formats](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/notebook-definition)
- [Medallion Lakehouse architecture](https://learn.microsoft.com/en-us/fabric/onelake/onelake-medallion-lakehouse-architecture)
- [Warehouse-to-Lakehouse incremental pipeline tutorial](https://learn.microsoft.com/en-us/fabric/data-factory/tutorial-incremental-copy-data-warehouse-lakehouse)
- [Delta Change Data Feed in Fabric](https://learn.microsoft.com/en-us/fabric/data-engineering/delta-lake-change-data-feed)
- [Lakehouse SQL analytics endpoint](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-sql-analytics-endpoint)
- [Develop Direct Lake semantic models](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-develop)

See [MLV-LEARNING.md](MLV-LEARNING.md) for the existing materialized lake view course.
