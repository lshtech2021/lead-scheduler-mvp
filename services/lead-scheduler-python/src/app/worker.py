"""Simple entrypoint for RQ worker (not strictly necessary if using docker-compose command)."""
from rq import Worker, Queue, Connection
from redis import Redis
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)

if __name__ == "__main__":
    with Connection(redis_conn):
        qs = [Queue("followups"), Queue("leads")]
        worker = Worker(qs)
        worker.work()