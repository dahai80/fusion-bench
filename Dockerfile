# Fusion-Bench Docker image — Apple Silicon MLX workbench.
# Importers/callers: docker-compose.yml; CI pipeline `docker build`.
# Affected API: no API changes; containerization only.
# Data schema: N/A.

FROM python:3.12-slim

LABEL maintainer="fusion-bench"
LABEL description="Fusion-Bench: MLX model benchmarking and auto-tuning workbench"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY fusion_bench/ ./fusion_bench/

RUN pip install --no-cache-dir -e ".[test]"

# Non-root user for production safety.
RUN useradd -m -r fusion && chown -R fusion:fusion /app
USER fusion

# Default serve port (cli.py `serve` default = 11450).
ENV FUSION_BENCH_PORT=11450
EXPOSE 11450

VOLUME ["/home/fusion/.fusion-bench", "/home/fusion/bench"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:11450/api/v1/system/health || exit 1

ENTRYPOINT ["fusion-bench"]
CMD ["serve", "--host", "0.0.0.0", "--port", "11450"]
