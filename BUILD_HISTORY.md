# Build history

This document records how the OpenTelemetry homelab was built and what each
step demonstrated. It is an interview study source as well as a project log.

## 1. Establish the baseline API

The project began as a small FastAPI application running locally with Python
3.12. It exposed three routes:

- `GET /health` returned `{"status":"ok"}`.
- `GET /hello` returned a greeting.
- `GET /items/{id}` returned a generated item and required an integer ID.

The API was tested with `curl`, including the expected `422` response for an
invalid item ID and `404` for an unknown route.

The purpose of this step was to establish a working application before adding
containers or telemetry.

## 2. Create a reproducible Python environment

A Python 3.12 virtual environment was created in `.venv/`. Dependencies were
installed from `requirements.txt`, then pinned to exact versions. `pip check`
confirmed that the installed packages had no broken requirements.

The virtual environment is development-only and is excluded from Git and
Docker build contexts.

## 3. Add Git tracking

The repository was initialized on the `main` branch. `.gitignore` excludes
the virtual environment, Python caches, environment files, and macOS metadata.
Commits were made throughout the build so every milestone could be inspected
or reverted.

## 4. Package the API with Docker

The Dockerfile uses `python:3.12-slim`, sets `/app` as the working directory,
installs the pinned requirements, copies the application, exposes port 8000,
and starts Uvicorn on `0.0.0.0:8000`.

`.dockerignore` keeps `.venv/`, `.git/`, caches, and environment files out of
the image.

The image was built as `otel-homelab:level1`. The container maps
`127.0.0.1:8000` on the Mac to port `8000` in the container, so the API is
reachable locally without publishing it on every host interface.

## 5. Create the Docker network

A user-defined bridge network named `otel-net` was created. The API and
Collector use this network so containers can resolve each other by name.

The important distinction is:

- `127.0.0.1:8000:8000` is host-to-container access for the API.
- `otel-collector:4318` is container-to-container access on `otel-net`.

The Collector's OTLP port does not need to be published to the Mac.

## 6. Add and validate the Collector

The Collector configuration in `config/otel-collector.yaml` contains:

- An OTLP receiver using HTTP on `0.0.0.0:4318`.
- A `batch` processor.
- A `debug` exporter with detailed verbosity.
- Traces, metrics, and logs pipelines using those components.

The configuration was bind-mounted read-only into
`otel/opentelemetry-collector:0.160.0`. The Collector's `validate` command
returned exit code `0`, and startup logs reported that the receiver was ready.

At this stage the debug exporter printed telemetry to Collector logs. It did
not provide persistent storage or a dashboard.

## 7. Instrument traces

`app/telemetry.py` created a shared OpenTelemetry `Resource` and
`TracerProvider`. A `BatchSpanProcessor` sent spans through
`OTLPSpanExporter` to the Collector. `FastAPIInstrumentor` created server and
ASGI spans automatically.

The API container received these environment variables:

```text
OTEL_SERVICE_NAME=otel-homelab-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

The service name identifies the application in telemetry. The HTTP exporter
uses the Collector base URL and sends traces to `/v1/traces`.

A request to `/hello` produced a server span plus ASGI response spans in the
Collector debug output.

## 8. Instrument metrics

The application added a `MeterProvider` with a
`PeriodicExportingMetricReader` set to export every five seconds through
`OTLPMetricExporter`. The FastAPI instrumentation used this meter provider.

Requests produced metrics such as:

- `http.server.active_requests`
- `http.server.duration`
- `http.server.response.size`

The duration and response-size metrics are histograms, so they can describe
request latency and payload size rather than only counting requests.

## 9. Instrument logs

The application added a `LoggerProvider`, `BatchLogRecordProcessor`, and
`OTLPLogExporter`. An OpenTelemetry `LoggingHandler` was attached to the
application logger so application records were exported to `/v1/logs`.

The `/hello` handler logs `hello endpoint called`. Collector output showed the
log body, severity, source file and line, trace ID, and span ID.

## 10. Logging visibility detour

The first log configuration exported records to the Collector but did not
make the application message visible in `docker logs otel-api`. The reason
was that `LoggingHandler` is an OTLP handler; it forwards records instead of
printing them to the container console.

The fix was to:

1. Attach the OTLP handler to the `app` logger.
2. Add a standard console `StreamHandler` to the root logger.
3. Set the root logger level to `INFO`.

After rebuilding and recreating the API container, local output included:

```text
INFO app.main: hello endpoint called
```

The same event continued to arrive at the Collector with trace correlation.

This demonstrated the difference between application log export and local
process diagnostics.

## 11. Add controlled latency and failures

The `/simulate` endpoint was added for repeatable observability tests:

- `delay_ms` adds a delay and is clamped to `0` through `5000` milliseconds.
- `fail=true` returns HTTP `503` after the delay.
- Successful requests log completion and return the delay.
- Failed requests log a warning and raise `HTTPException`.

Observed tests included:

- `delay_ms=750` returned HTTP `200` in approximately 0.75 seconds.
- `delay_ms=300&fail=true` returned HTTP `503` in approximately 0.3 seconds.

The failed request generated a warning log, an error-status server span, and
`503`-labelled duration and response-size metric points.

## 12. Test Collector outage recovery

The Collector was stopped while the API remained running. The API continued
to return HTTP responses because telemetry export runs in background processors
and is separate from request handling.

The API logs showed exporter retries and eventual failures for `/v1/traces`,
`/v1/metrics`, and `/v1/logs`, including DNS failures for `otel-collector`.

After the Collector was restarted, a new request produced fresh telemetry
again. This proves recovery for new data; it does not prove that every record
created during the outage was retained.

## 13. Verify W3C trace context propagation

The following header simulated an upstream trace:

```text
traceparent: 00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01
```

The Collector showed:

- Trace ID: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Parent ID: `bbbbbbbbbbbbbbbb`
- A newly generated server span ID
- `GET /simulate` with status `Error` and HTTP `503`

The warning log used the same trace ID and the server span ID. This confirmed
that traces and logs were correlated and that the application honored the
incoming W3C trace context.

## 14. Document and publish the project

The README was expanded to describe local execution, Docker networking,
Collector startup, telemetry inspection, failure simulation, outage recovery,
and the architecture diagram.

The repository was published as a public GitHub repository:

`https://github.com/matthewjleung/otel-homelab`

The local `main` branch tracks `origin/main`. GitHub HTTPS authentication used
a fine-grained personal access token; the token itself was never stored in the
repository.

## Current architecture

```text
Mac client
  -> 127.0.0.1:8000
  -> Docker port mapping
  -> otel-api (FastAPI + Uvicorn)
  -> OpenTelemetry SDK
  -> OTLP HTTP over otel-net
  -> otel-collector:4318
  -> batch processor
  -> debug exporter
  -> Collector container logs
```

Application logs also go to the API container console. The API response path
and telemetry path are separate.

## Known limitations and next steps

The current Collector only prints telemetry. It has no durable backend,
query interface, dashboard, alerting, authentication, TLS, or Kubernetes
deployment.

The next useful milestones are:

1. Deploy the API and Collector with Kubernetes manifests.
2. Add persistent trace, metric, and log backends.
3. Add Grafana dashboards and alerts.
4. Add health probes and a reproducible deployment workflow.

## Interview prompts

Practice answering these without looking at the implementation:

1. Why use a Collector instead of exporting directly to a backend?
2. How does Docker DNS let the API resolve `otel-collector`?
3. What is the difference between a trace, span, metric, and log?
4. How did you prove that logs and spans were correlated?
5. Why did the API remain available when the Collector was stopped?
6. Why did rebuilding the image require recreating the API container?
7. What did the console-handler detour teach you?
8. What would you add before calling this production-ready?
