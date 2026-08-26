# Fusion-Bench Docker image — Apple Silicon MLX workbench.
# Importers/callers: docker-compose.yml; CI pipeline `docker build`.
# Affected API: no API changes; containerization only.
# Data schema: N/A.

FROM python:3.12-slim

LABEL maintainer="fusion-bench"
LABEL description="Fusion-Bench: MLX model benchmarking and auto-tuning workbench"

WORKDIR /app

# No apt layer: all deps (pyjwt[crypto]→cryptography, matplotlib, pydantic-core)
# ship prebuilt linux/arm64 wheels — no C compilation, no system packages.
# git/curl unused at runtime (no git subprocess calls; HEALTHCHECK uses
# Python urllib from the base image). Skipping apt also sidesteps slow
# Debian mirror fetches inside the build VM.

COPY pyproject.toml ./
COPY fusion_bench/ ./fusion_bench/

# Use Aliyun PyPI mirror: direct PyPI is throttled/unreachable inside the
# build VM (~17 kB/s vs mirror's ~4 MB/s). Same mirror used for uv pip
# compile (see root CLAUDE.md). Override at build time with --build-arg
# PIP_INDEX_URL=... for environments with direct PyPI access.
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN pip install --no-cache-dir -e ".[test]"

# Non-root user for production safety. Pre-create the data dirs the app
# writes to (~/.fusion-bench for sqlite DBs, ~/bench for task output) and
# chown them to the fusion user — named volumes inherit ownership from the
# image path on first mount, so without this the volume is root-owned and
# the non-root process hits "unable to open database file" at startup.
RUN useradd -m -r fusion && \
    mkdir -p /home/fusion/.fusion-bench /home/fusion/bench && \
    chown -R fusion:fusion /app /home/fusion/.fusion-bench /home/fusion/bench
USER fusion

# Default serve port (cli.py `serve` default = 11450).
ENV FUSION_BENCH_PORT=11450
EXPOSE 11450

VOLUME ["/home/fusion/.fusion-bench", "/home/fusion/bench"]

# HEALTHCHECK uses Python urllib (present in base image) — no curl needed.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:11450/api/v1/system/health', timeout=4).status==200 else 1)" || exit 1

ENTRYPOINT ["fusion-bench"]
CMD ["serve", "--host", "0.0.0.0", "--port", "11450"]
