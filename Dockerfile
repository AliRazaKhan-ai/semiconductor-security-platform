# Purpose: Container image for the SemiSecure platform.
#
# Base is python:3.12-slim-trixie for two reasons. requirements.txt marks
# tensorflow as python_version < "3.13", so the image must be 3.12. And Debian
# trixie carries Yosys 0.52 and Verilator 5.032, the versions this project's
# evidence was measured with; Ubuntu 24.04 ships Yosys 0.33, which produces
# different cell counts and would silently contradict
# evidence/hardware/yosys_structural_delta_evidence.json.
#
# The build asserts both versions and fails if they differ, so the image either
# reproduces the recorded measurements or refuses to exist.

FROM python:3.12-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        yosys verilator build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN yosys -V && verilator --version \
    && yosys -V | grep -q "Yosys 0.52" \
    && verilator --version | grep -q "Verilator 5.032"

WORKDIR /app

# CPU-only PyTorch first: requirements.txt says torch>=2.4,<3, which otherwise
# resolves to the CUDA build and roughly 2.5 GB of libraries with no GPU present.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

COPY app ./app
COPY terminal ./terminal
COPY scripts ./scripts
COPY configs ./configs
COPY models ./models
COPY hardware_lab ./hardware_lab
COPY blockchain ./blockchain
COPY manage.py wsgi.py run.py gunicorn.conf.py VERSION ./

RUN mkdir -p data runtime evidence backups

# Runs unprivileged: the OS account is the trust anchor in the threat model, so
# the container must not add root where the host does not have it.
RUN useradd --create-home --uid 10001 semisecure \
    && chown -R semisecure:semisecure /app
USER semisecure

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/health/ready || exit 1

# One worker: the rate limiter keeps its counters in process memory, so a second
# worker would silently multiply the effective limit. See RISK-06.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", \
     "--worker-class", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", \
     "--timeout", "120", "--graceful-timeout", "30", "--keep-alive", "5", \
     "--access-logfile", "-", "--error-logfile", "-", "--capture-output", \
     "wsgi:app"]
