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

-- GOAL: demonstrate event-time analytics and late arrivals with replayable micro-batches.
-- PREREQUISITE: 01 (schema). Independent event chain; sales lessons are not changed.
-- These SQL inserts SIMULATE ingestion; they are not a live streaming connection.
-- Actual live integration instructions are in the final cells and README.
CREATE TABLE IF NOT EXISTS mlv_learn.device_events (
 event_id STRING, device_id STRING, event_ts TIMESTAMP,
 ingested_at TIMESTAMP, temperature DECIMAL(5,2)
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true');

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

MERGE INTO mlv_learn.device_events t
USING (SELECT * FROM VALUES
 ('e1','sensor-a',TIMESTAMP '2026-10-03 10:00:10',TIMESTAMP '2026-10-03 10:00:12',CAST(20 AS DECIMAL(5,2))),
 ('e2','sensor-a',TIMESTAMP '2026-10-03 10:00:40',TIMESTAMP '2026-10-03 10:00:42',CAST(30 AS DECIMAL(5,2)))
 AS v(event_id,device_id,event_ts,ingested_at,temperature)) s
ON t.event_id=s.event_id WHEN NOT MATCHED THEN INSERT *;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.valid_events (
 CONSTRAINT valid_event CHECK (event_id IS NOT NULL AND device_id IS NOT NULL
 AND event_ts IS NOT NULL AND temperature IS NOT NULL
 AND temperature >= -50 AND temperature <= 150) ON MISMATCH DROP
)
TBLPROPERTIES ('delta.enableChangeDataFeed'='true') AS
SELECT event_id, device_id, event_ts, ingested_at, temperature FROM mlv_learn.device_events;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mlv_learn.device_minute AS
SELECT device_id, date_trunc('MINUTE',event_ts) AS event_minute,
 COUNT(*) AS event_count, AVG(temperature) AS avg_temperature,
 MAX(ingested_at) AS latest_ingestion
FROM mlv_learn.valid_events GROUP BY device_id, date_trunc('MINUTE',event_ts);

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT initial bucket: 10:00, count 2, average 25.
SELECT * FROM mlv_learn.device_minute;

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- Late arrival: event happened in the OLD minute but landed later.
-- Stable event_id + MERGE deduplicates this simulated batch. MLV constraints do not deduplicate.
MERGE INTO mlv_learn.device_events t
USING (SELECT 'e3' AS event_id, 'sensor-a' AS device_id,
 TIMESTAMP '2026-10-03 10:00:20' AS event_ts,
 TIMESTAMP '2026-10-03 10:07:00' AS ingested_at,
 CAST(40 AS DECIMAL(5,2)) AS temperature) s
ON t.event_id=s.event_id WHEN NOT MATCHED THEN INSERT *;
-- PAUSE: create/run a schedule selecting valid_events AND device_minute. Wait for success.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- EXPECT after refresh: old 10:00 bucket changes to count 3 and average 30.
SELECT * FROM mlv_learn.device_minute;
-- Event time controls grouping; ingestion time helps measure arrival lag.
-- Unlike a stateful stream with a watermark, this query does not discard old arrivals.
-- Replay e3: event count should remain 3. A live append sink can still introduce duplicates.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

-- CELL ********************

-- OPTIONAL LIVE FABRIC LAB (requires Eventstream resources; do not Run all to deploy):
-- 1. Create an Eventstream with a custom endpoint or an available event source.
-- 2. Send the JSON sample in README. Map event_id/device_id to strings,
--    event_ts/ingested_at to timestamps and temperature to a numeric type.
-- 3. Add a Lakehouse destination to a NEW dedicated table; inspect its schema and namespace.
--    Do not assume the sink enforces event_id uniqueness or exactly-once delivery.
-- 4. Copy valid_events/device_minute definitions using NEW live_* object names and
--    the actual destination table. Enable CDF on that source where supported.
-- 5. Select both live views in a time-based schedule. Start with >=5 minutes.
--    Where available, try Event-triggered refresh (Preview) with a supported OneLake
--    ingestion event; inspect the generated resources and actual refresh behavior.
-- 6. Publish/start the Eventstream, send events, wait for lakehouse commits then refresh.
--    Measure end-to-end freshness: arrival + sink commit + refresh wait + compute + serving.
-- 7. Stop the source/Eventstream and pause schedules after practice.
-- Scheduled MLV refresh has a minimum effective interval of five minutes today.
-- Event-triggered preview is also refresh-based, not per-event continuous computation.
-- For subsecond operational exploration, route events to Eventhouse and use KQL.
-- EXERCISE: send e3 twice, detect duplicates, design a deduplication stage before aggregation.

-- METADATA ********************

-- META {
-- META   "language": "sparksql",
-- META   "language_group": "synapse_pyspark"
-- META }

