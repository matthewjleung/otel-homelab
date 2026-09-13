# OpenTelemetry Homelab

A small FastAPI application for learning Docker and OpenTelemetry.

## Current state

The containerised API exports traces over OTLP HTTP to an OpenTelemetry
Collector. The Collector prints received spans using its debug exporter.

Metrics and log export are planned.

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

