# OpenTelemetry Homelab

A small FastAPI application for learning Docker and OpenTelemetry.

## Current state

The API runs locally with Python 3.12 or inside a Docker container.
OpenTelemetry instrumentation and the Collector are planned.

## Run locally

From the project directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If the virtual environment already exists, skip its creation.

## Endpoints

- GET /health — returns application health.
- GET /hello — returns a greeting.
- GET /items/{id} — returns a generated item; id must be an integer.

## Example request

In a second terminal:

```bash
curl -i http://127.0.0.1:8000/items/42
```

Expected status: 200 OK.

An invalid integer such as /items/banana returns 422.
An unknown route such as /missing returns 404.

## Stop the server

Press Control + C in the terminal running Uvicorn.

## Run with Docker

Requires Docker Desktop to be running.
Run these commands from the project directory.

Build the image:

```bash
docker build -t otel-homelab:level1 .
```

Create the shared network once; skip if it already exists:

```bash
docker network create otel-net
```

Create and start the API container:

```bash
docker run -d --name otel-api --network otel-net -p 127.0.0.1:8000:8000 otel-homelab:level1
```

Mac port 8000 must be available. Stop any local Uvicorn server first.
If otel-api already exists, use docker start otel-api instead.

Test the API:

```bash
curl -i http://127.0.0.1:8000/health
```

View logs and manage the container:

```bash
docker logs otel-api
docker stop otel-api
docker start otel-api
```






