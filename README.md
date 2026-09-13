# OpenTelemetry Homelab

A small FastAPI application for learning Docker and OpenTelemetry.

## Current state

The API runs locally with Python 3.12.
Docker packaging and OpenTelemetry instrumentation are planned.

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
