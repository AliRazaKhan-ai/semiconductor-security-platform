"""Purpose: Production Gunicorn settings for Flask-SocketIO threaded deployment.
Directory: project root.
Dependencies: gunicorn and environment variables.
Connection: Loads app.factory:create_app through the wsgi module.
"""

from __future__ import annotations

import multiprocessing
import os

bind = os.getenv("SEMISURE_GUNICORN_BIND", "0.0.0.0:5000")
workers = 1
worker_class = "gthread"
threads = int(os.getenv("SEMISURE_GUNICORN_THREADS", "32"))
timeout = int(os.getenv("SEMISURE_GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("SEMISURE_GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("SEMISURE_GUNICORN_KEEPALIVE", "5"))
backlog = int(os.getenv("SEMISURE_GUNICORN_BACKLOG", "2048"))
max_requests = int(os.getenv("SEMISURE_GUNICORN_MAX_REQUESTS", "5000"))
max_requests_jitter = int(os.getenv("SEMISURE_GUNICORN_MAX_REQUESTS_JITTER", "500"))
preload_app = False
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("SEMISURE_LOG_LEVEL", "INFO").lower()
capture_output = True
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None
proc_name = "semisecure-backend"


def when_ready(server: object) -> None:
    server.log.info("SemiSecure backend is ready")


def on_exit(server: object) -> None:
    server.log.info("SemiSecure backend stopped")

