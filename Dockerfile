# Fusion-Bench Docker image.
# Importers/callers: docker-compose.yml; CI pipeline `docker build`.
# Affected API: no API changes; containerization only.
# Data schema: N/A.
# User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-14 containerization).

FROM python:3.11-slim

LABEL maintainer="fusion-bench"
LABEL description="Fusion-Bench: MLX model benchmarking and auto-tuning workbench"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY fusion_bench/ ./fusion_bench/

RUN pip install --no-cache-dir -e ".[test]"

EXPOSE 8000

VOLUME ["/root/.fusion-bench", "/root/bench"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["fusion-bench"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
