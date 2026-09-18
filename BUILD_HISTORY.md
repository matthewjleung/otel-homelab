# Build history

This document records how the OpenTelemetry homelab was built and what each
step demonstrated. It is an interview study source as well as a project log.

Sections 1–14 and their architecture/limitations describe the Level 1 snapshot.
The Level 2 completion record is appended below; it supersedes those historical
limitations without removing the original learning record.

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

## Level 2 — Completed 18 September 2026

Level 2 extended the existing application into a six-container observability
platform. Work proceeded in tutor mode: the learner edited configurations,
ran commands, interpreted evidence and committed checkpoints. No application
redesign, Kubernetes, additional microservices or custom metrics were required.
The 12–16 focused-hour budget guided scope, but focused hours were not tracked.

### 2.1 — Declarative container management

Replaced manual management with Compose services for the API and Collector.
Service-name discovery preserved OTLP/HTTP delivery over the Compose network.
A Python-based API health check verified responsiveness inside the container.
It did not test telemetry delivery or automatically restart unhealthy containers.
Existing traces, metrics and correlated application logs were validated after
the migration; the original Level 1 containers were left stopped.

### 2.2 — Queryable storage, one signal at a time

- Prometheus scraped the Collector's application metrics endpoint on port 8889
  every 15 seconds. The API continued pushing OTLP metrics to the Collector
  every five seconds. Request counts and rates were queried with route/status
  labels using existing instrumentation.
- Tempo received traces through `otlp_http/tempo` on port 4318. Its query API on
  port 3200 retrieved healthy, slow and failed requests by trace ID.
- Loki received existing application OTLP logs through `otlp_http/loki`, whose
  base endpoint is `http://loki:3100/otlp`. Normal and failed logs were queried
  through its API. `service.name` became the indexed `service_name` label;
  trace IDs remained structured metadata rather than high-cardinality labels.
- The detailed debug exporter remained available for diagnosis. No separate
  container-log collection agent was added.

Named volumes were added for all three backends. Historical data was queried,
all five then-existing Compose containers were removed with
`docker compose down --timeout 60`, and replacements were started. Volumes were
not deleted. Prometheus retained count 4 at timestamp 1789573980; Tempo and Loki
retained trace/log evidence for `55556666777788889999aaaabbbbcccc`.
This demonstrated container-replacement persistence, not backup or lossless
telemetry handling under every failure. Startup readiness briefly returned 503
for Tempo/Loki, then succeeded without configuration changes.

### 2.3 — Grafana, RED and cross-signal investigation

Grafana became the sixth service, with `grafana-data` mounted at
`/var/lib/grafana`. Data sources were configured manually against Compose
service query addresses and tested with actual telemetry in Explore. The volume
preserves Grafana state by design; a separate Grafana recreation test was not run.

Built exactly one dashboard, Homelab RED, with three panels:

- Request rate, in requests per second.
- HTTP 5xx error percentage.
- Estimated P95 latency, in milliseconds.

All panels excluded `/health` and used two-minute rate windows. Simple curl
loops exercised healthy, failed, slow and slow-failed traffic. Histogram bucket
interpolation explained an approximately 988 ms P95 estimate for requests with
a 750 ms injected delay. It was not evidence that every trace lasted 988 ms.
No traffic produced undefined ratios/percentiles, distinct from a healthy zero.

Investigation followed dashboard degradation to trace
`9dfc2ae775afec75b2ddc7c973b1da99`: HTTP 503, 762.3 ms, and a correlated WARN log
`Simulated failure after 750 ms`. Navigation was manual through time windows
and trace IDs, not automatic metric exemplars or configured cross-signal links.

The tested dashboard was exported as portable Classic JSON to
`dashboards/homelab-red.json`, with a Prometheus data-source input for import.
The initial V2 export had local data-source references; re-exporting corrected
portability without changing the live dashboard or adding provisioning.

### 2.4 — One SLI, one SLO, one alert, one incident

Defined request-based availability as recorded HTTP 200–499 responses divided
by total recorded application responses, excluding `/health`, over two minutes.
4xx responses were accepted for this server-availability definition, not as
proof of business success. No traffic was undefined. Requests that never reach
the application are outside this measurement's coverage.

The demonstration SLO was at least 99% availability over that same rolling
two-minute window. This was intentionally short for testing, not a production
SLO or external SLA. The SLI query was tested in Explore without adding a panel.

Created one Grafana-managed rule, High HTTP 5xx error rate:

- Instant query for 5xx percentage using the existing metrics and 2m window.
- Threshold strictly above 1%, evaluated every 30s, pending for 1m.
- No additional recovery hold; no data mapped to Normal, query errors to Error.
- Rule active in Homelab / homelab-alerts.
- Default routing preview selected an empty contact point; no external
  notification integration was configured or tested.

The planned 15s evaluation interval was changed to 30s during setup. Collection
interval, query window, dashboard refresh, evaluation interval and pending
period were explained as separate concepts. A NaN preview from idle traffic was
distinguished from a numeric 0% error result after healthy requests.

The controlled incident on 18 September 2026 demonstrated:

1. Healthy HTTP 200 traffic, 0% error rate and Normal/OK alert state.
2. Sustained intentional HTTP 503 traffic and an observed Firing alert.
3. Investigation of trace `68eda52dfdd2f9872e2889adf70b1293`, starting at
   12:53:15.360 Australia/Sydney: `/simulate`, HTTP 503, duration 3.71 ms.
4. Loki returned the matching WARN message `Simulated failure after 0 ms`.
5. Failure injection stopped; healthy traffic returned HTTP 200, the measured
   error percentage reached 0%, and the alert returned to Normal/OK.

For this 200/503 traffic, availability was the complement of error percentage:
the failures violated the 99% demonstration target and successful traffic
restored it as failures aged out. Normal from absent traffic alone was not
accepted as recovery. Exact alert firing/resolution timestamps were not recorded.

Exported the actual rule to `alerts/high-http-5xx.yaml` for version control.
This file-provisioning export is not loaded by Compose and still references the
original Prometheus data-source UID. A fresh deployment needs that reference
mapped or the rule recreated through the UI. Export restoration was not tested.

### Troubleshooting and engineering habits

- YAML nesting errors were diagnosed from Compose validation and numbered file
  output. Cosmetic trailing spaces were subsequently deprioritised.
- Empty shell URL variables caused curl errors before any API request was sent;
  printing the variable and testing one request isolated the cause.
- Copied shell `>` prompts and broken multiline quoting caused shell/PromQL
  errors. Control+C cancelled unfinished commands; shorter commands reduced
  copy/paste mistakes. These were not failures of the telemetry backends.
- Grafana state, health, and query value were distinguished: a firing alert can
  have OK health, while Normal alone can result from no traffic.
- Git checkpoints used scoped staging and review. An earlier rejected push was
  resolved by fetching, inspecting divergence, preserving local edits in a
  scoped stash, and rebasing before a normal push. No force push was needed.
- UI-created settings live in Grafana's volume, not automatically in Git.
  Exported configuration preserves definitions, not historical telemetry data.

### Finish condition and remaining limits

All Level 2 functional criteria were demonstrated: Compose, three stored and
queryable signals, Grafana, RED, one SLI/SLO, one firing/resolving alert, controlled
failure injection and cross-signal investigation. README and this history were
updated at the final checkpoint.

This remains a single-host learning platform. It has no production HA, backup
strategy, TLS architecture, notification delivery, end-to-end uptime guarantee
or advanced error-budget tooling. One dashboard and one alert were sufficient.
Level 2 stops here. Kubernetes is explicitly deferred to Level 3; it has not
been started automatically.
