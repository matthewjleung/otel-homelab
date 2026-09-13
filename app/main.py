import logging
from fastapi import FastAPI
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

