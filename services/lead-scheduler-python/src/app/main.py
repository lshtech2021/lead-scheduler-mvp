from fastapi import FastAPI
from .routes import webhook
from .db import init_db
from loguru import logger
import os

app = FastAPI(title="Scheduling Automation API")

app.include_router(webhook.router, prefix="/webhook")

@app.on_event("startup")
async def startup():
    logger.info("Initializing DB")
    init_db()

@app.get("/")
async def root():
    return {"ok": True}