import time
import logging
from fastapi import FastAPI, HTTPException
from app.telemetry import configure_telemetry

app = FastAPI()
configure_telemetry(app)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/hello")
def hello():
    logger.info("hello endpoint called")
    return {"message": "Hello from my homelab"}


@app.get("/items/{id}")
def get_item(id: int):
    return {"id": id, "name": f"Item {id}"}

@app.get("/simulate")
def simulate(delay_ms: int = 0, fail: bool = False):
    delay_ms = min(max(delay_ms, 0), 5000)

    if delay_ms:
        time.sleep(delay_ms / 1000)

    if fail:
        logger.warning("Simulated failure after %s ms", delay_ms)
        raise HTTPException(
            status_code=503,
            detail="simulated failure",
        )

    logger.info("Simulation completed after %s ms", delay_ms)
    return {"delay_ms": delay_ms, "failed": False}

