# OpenTelemetry Homelab
A small FastAPI application for learning Docker and OpenTelemetry.


## Level 2.2.4–2.2.5 — Persistence and storage checkpoint

  Verified historical telemetry before and after:
  - docker compose down --timeout 60
  - docker compose up -d

  All three backends retained the test data:
  - Prometheus: failed /simulate request count remained 4 when queried
    at the fixed timestamp 1789573980.
  - Tempo: trace 55556666777788889999aaaabbbbcccc remained retrievable,
    with HTTP 503 and approximately 322 ms server-span duration.
  - Loki: the original "Simulated failure after 300 ms" log remained
    retrievable with its matching trace ID.

  Named volumes survive docker compose down.
  docker compose down -v deletes the named volumes and their stored data.
  The destructive -v option was not tested.

  The API's in-memory counters reset on recreation; Prometheus retains
  previously collected historical samples independently.

## Level 2.2.3 — Loki

  Loki receives application logs through the Collector:

  API → OTLP/HTTP → Collector → Loki /otlp/v1/logs

  The Collector uses the otlp_http/loki exporter and continues sending
  logs to its debug exporter.

  Loki's HTTP API is available at localhost:3100. Local storage is
  configured under /loki using the loki-data named volume.
  Persistence across container recreation verified for Prometheus, Tempo and Loki.

  Verified:
  - A /hello request produced a queryable INFO log.
  - A controlled /simulate failure produced a queryable WARN log.
  - Filtering by trace_id retrieved the specific failed request's log.
  - Trace and span IDs were preserved for correlation with Tempo.

  The service.name resource attribute becomes the service_name index
  label. Trace IDs remain structured metadata, not index labels.
  This pipeline collects application OTLP logs, not all container stdout.

## Level 2.2.2 — Tempo

  Tempo stores traces forwarded by the Collector:

  API → OTLP/HTTP :4318 → Collector → OTLP/HTTP :4318 → Tempo

  Tempo exposes its query API on `localhost:3200`. Trace data is stored under
  `/var/tempo` in the `tempo-data` Docker volume.

  Verified with Tempo's trace-by-ID API:

  - A controlled failed request returned HTTP 503 and was retrieved successfully.
  - A healthy `/simulate` request returned HTTP 200 and was retrieved successfully.
  - A slow `/simulate?delay_ms=750` request returned HTTP 200 and showed roughly
    750 ms span duration.
  - Server spans and their child response spans were present.
  - Trace IDs linked all spans belonging to one request.

  The Collector continues to print all signals through its debug exporter, while
  traces are also sent to Tempo through the `otlp_http/tempo` exporter.

## Level 2.2.1 — Prometheus

  Prometheus stores application metrics received through the Collector:

  API → OTLP/HTTP :4318 → Collector → /metrics :8889 ← Prometheus scrape

  The API exports metrics every five seconds. Prometheus scrapes the
  Collector every 15 seconds and stores samples in the prometheus-data
  named volume, mounted at /prometheus.

  Open http://localhost:9090 to query metrics.
  The target at http://localhost:9090/targets should show UP.

  Verified:
  - Successful /hello requests and intentional /simulate HTTP 503 failures.
  - Request counts labelled by http_target and http_status_code.
  - Request rates calculated with rate().
  - Existing duration histograms are available for latency queries.

  Request rate by route and status, excluding health probes:

  ```promql
  sum by (http_target, http_status_code) (
    rate(http_server_duration_milliseconds_count{
      job="otel-collector",
      exported_job="otel-homelab-api",
      http_target!="/health"
    }[2m])
  )
  ```

  A zero rate means no increase during the window; it does not mean
  the cumulative request count is zero.

  Traces and logs still use the Collector debug exporter.


## Level 2.1 — Docker Compose

  The API and OpenTelemetry Collector are now managed through `compose.yaml`.
  Use the Compose commands below for the current deployment. The manual Docker
  instructions later in this document describe the Level 1 setup.

  Run from the project directory:

  ```bash
  docker compose up -d
  docker compose ps
  curl -i http://localhost:8000/health
  curl -i http://localhost:8000/hello
  docker compose logs --since 2m otel-collector
  ```

  Expected results: the API reports healthy, the Collector reports running,
  both endpoints return HTTP 200, and traces, metrics, and application logs
  appear in Collector output.

  Compose creates a shared network. The API exports OTLP/HTTP telemetry to
  http://otel-collector:4318 using service-name discovery. Only API port 8000
  is published to the Mac, on 127.0.0.1.

  The API health check calls /health inside its container every 30 seconds.
  It checks API responsiveness, not telemetry delivery, and does not
  automatically restart an unhealthy container.

  The Collector still uses the detailed debug exporter. Metrics are now stored in Prometheus.
  Traces and logs are next. The original Level 1 containers remain stopped;
  do not start the old API alongside Compose because both use host port 8000.



## Current state

The containerised FastAPI API exports traces, metrics, and logs over
OTLP HTTP to an OpenTelemetry Collector.

Application logs include trace and span IDs in their OTLP records.
Application messages and exporter diagnostics are also visible locally
through docker logs otel-api.

The /simulate endpoint generates controlled latency and HTTP 503 failures.
Collector outage testing confirmed that the API continues serving requests,
exporter failures appear in local logs, and fresh telemetry resumes after
the Collector restarts.

The Collector uses a debug exporter for terminal inspection.
No searchable telemetry storage or dashboard is configured.


## Architecture

Client on Mac
    → localhost:8000
    → Docker port mapping
    → FastAPI application in otel-api
    → OTLP HTTP over otel-net
    → otel-collector:4318
    → Collector debug output

The API returns HTTP responses directly to the client.
Telemetry export is a separate flow.

## Requirements

- Docker Desktop running
- Python 3.12 for local development
- Git
- curl

Run setup and build commands from the project directory.

## Endpoints

- GET /health — returns application health.
- GET /hello — returns a greeting.
- GET /items/{id} — returns a generated item; id must be an integer.

There is no database.

## Local Python setup

Create the virtual environment once:

```bash
python3.12 -m venv .venv
```

Activate it and install dependencies:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The Docker instructions below run the complete tracing pipeline.
The local server command starts only the API:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Without exporter configuration, the local API attempts to send traces
to localhost:4318. The Collector setup below does not publish that
port to the Mac, so local trace export will fail with this setup.
Use the containerised API to follow the complete pipeline.

Press Control + C to stop the local server before using Mac port 8000
for the API container.

## Build the API image

```bash
docker build -t otel-homelab:level1 .
```

The image installs its own Python dependencies.
The Mac's .venv is excluded through .dockerignore.

Rebuilding an image does not update an existing container.

## Create the shared Docker network

Run once; skip if otel-net already exists:

```bash
docker network create otel-net
```

Containers on this network can reach each other by name.

## Start the Collector

```bash
docker run -d \
--name otel-collector \
--network otel-net \
--mount "type=bind,source=$(pwd)/config/otel-collector.yaml,target=/etc/otelcol/config.yaml,readonly" \
otel/opentelemetry-collector:0.160.0 \
--config=/etc/otelcol/config.yaml
```

The bind mount makes the local configuration available inside the
container as a read-only file.

If the Collector container already exists and is stopped:

```bash
docker start otel-collector
```

If it is already running, leave it running.

Check startup:

```bash
docker logs otel-collector
```

Expect a message indicating the Collector is ready.

The traces pipeline is:

OTLP receiver → batch processor → debug exporter

Port 4318 is reachable through the Docker network.
It is not published to the Mac.

## Start the API container

Mac port 8000 must be available. Stop any local Uvicorn server first.

```bash
docker run -d \
--name otel-api \
--network otel-net \
-p 127.0.0.1:8000:8000 \
-e OTEL_SERVICE_NAME=otel-homelab-api \
-e OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
otel-homelab:level1
```

- OTEL_SERVICE_NAME identifies the application in telemetry.
- OTEL_EXPORTER_OTLP_ENDPOINT sets the Collector's base URL.
- The HTTP trace exporter sends spans to /v1/traces.
- The port mapping forwards Mac port 8000 to container port 8000.

If otel-api already exists and is stopped:

```bash
docker start otel-api
```

Starting an existing container preserves its original image and
environment settings. To use a rebuilt image or new settings, stop
and remove the old API container, then run the creation command again:

```bash
docker stop otel-api
docker rm otel-api
```

## Test the API

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/hello
curl -i http://127.0.0.1:8000/items/42
```

These requests should return HTTP 200 with JSON bodies.

Test invalid input and an unknown route:

```bash
curl -i http://127.0.0.1:8000/items/banana
curl -i http://127.0.0.1:8000/missing
```

Expected statuses:

- 422 for an item ID that cannot be parsed as an integer.
- 404 for a route that does not exist.

## Inspect traces

Send a request, then allow about 10 seconds for batch export:

```bash
curl -i http://127.0.0.1:8000/hello
```

Read recent Collector output:

```bash
docker logs --since 1m otel-collector
```

Look for service.name equal to otel-homelab-api and a GET /hello
server span. Framework operations may produce additional child spans.

Spans in the same trace share a trace ID.
Each span has its own span ID.
A child span's parent ID identifies its parent span.

The debug exporter prints telemetry; it is not a searchable
telemetry database.

## Demonstrate context propagation

Supply a demonstration upstream trace context:

```bash
curl -i \
-H "traceparent: 00-11111111111111111111111111111111-2222222222222222-01" \
http://127.0.0.1:8000/hello
```

After allowing time for export:

```bash
docker logs --since 1m otel-collector
```

The GET /hello server span should have:

- Trace ID: 11111111111111111111111111111111
- Parent ID: 2222222222222222
- A newly generated span ID

The upstream span is simulated; only its context was supplied.
Normally, instrumentation generates and propagates these IDs.

## Inspect and manage containers

List running containers:

```bash
docker ps
```

Read API logs:

```bash
docker logs otel-api
```

Stop the services:

```bash
docker stop otel-api
docker stop otel-collector
```

Start the existing services again:

```bash
docker start otel-collector
docker start otel-api
```

Stopping containers preserves them and their configuration.
Removing containers does not remove their images or project source files.

## Security

Keep credentials and secrets out of source code and Git.
.env files and the local virtual environment are excluded by
.gitignore and .dockerignore.

The current setup requires no credentials.

## Simulate latency and failures

GET /simulate accepts two optional query parameters:

- delay_ms: integer delay in milliseconds, default 0, clamped to 0–5000.
- fail: boolean, default false. When true, returns HTTP 503.

Measure a successful slow request:

```bash
curl -i \
-w '\nTotal time: %{time_total} seconds\n' \
"http://127.0.0.1:8000/simulate?delay_ms=750"
```

Expect HTTP 200 and approximately 0.75 seconds or longer.

Measure a slow failed request:

```bash
curl -i \
-w '\nTotal time: %{time_total} seconds\n' \
"http://127.0.0.1:8000/simulate?delay_ms=300&fail=true"
```

Expect HTTP 503 with {"detail":"simulated failure"}.
The URL is quoted because & has special meaning in the shell.

The failed request produces:

- A WARN log containing "Simulated failure after 300 ms".
- A server span with status Error and HTTP status 503.
- Duration and response-size histogram points labelled with status 503.

Inspect the warning and its trace context:

```bash
docker logs --since 2m otel-collector 2>&1 |
grep -F -B 10 -A 10 'Simulated failure after 300 ms'
```

Allow about 10 seconds after the request for export.
Use the log's trace and span IDs to find the corresponding request span.


## Troubleshoot a Collector outage

Stop the Collector, then request the API:

```bash
docker stop otel-collector
curl -i http://127.0.0.1:8000/hello
```

The API should still return HTTP 200 because telemetry export runs
in the background.

After about 10 seconds, inspect exporter diagnostics:

```bash
docker logs --tail 50 otel-api
```

During our test, exporters reported name-resolution failures for
otel-collector, retried, and eventually reported failed batches.

Restore the Collector:

```bash
docker start otel-collector
```

Send a fresh request:

```bash
curl -i http://127.0.0.1:8000/hello
```

After about 10 seconds, confirm the new log arrived:

```bash
docker logs --since 2m otel-collector 2>&1 |
grep -F -B 10 -A 10 'hello endpoint called'
```

Check the log timestamp against the new request.

Successful recovery proves fresh telemetry delivery resumes.
It does not prove all telemetry from the outage was retained.

Application logs go to both OTLP and the console.
Exporter diagnostics go to the console, so they remain accessible
when the Collector is unavailable.

## Architecture diagram

```mermaid
flowchart LR
client["Mac client / curl"]
port["Docker port mapping<br/>127.0.0.1:8000 -> 8000"]

subgraph network["Docker network: otel-net"]
api["otel-api<br/>FastAPI + Uvicorn"]
sdk["OpenTelemetry SDK<br/>FastAPI instrumentation"]
collector["otel-collector<br/>OTLP receiver :4318"]
batch["Batch processor"]
debug["Debug exporter<br/>Collector container logs"]
api --> sdk
sdk -->|OTLP HTTP /v1/traces| collector
sdk -->|OTLP HTTP /v1/metrics| collector
sdk -->|OTLP HTTP /v1/logs| collector
collector --> batch --> debug
end

client -->|HTTP request| port
port --> api
api -->|HTTP response| port
port --> client
api --> appLogs["Console handler<br/>API container logs"]

