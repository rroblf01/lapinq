# Stage 1: Build Rust worker and Python wheel
FROM rust:1.95-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src/ src/
COPY pyproject.toml README.md ./
COPY python/ python/
RUN cargo build --release
RUN pip3 install maturin && maturin build --release --out /build/dist

# Stage 2: Python runtime
FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/release/lapinq-worker /usr/local/bin/lapinq-worker
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

EXPOSE 8001

CMD ["python", "-m", "lapinq", "server", "--host", "0.0.0.0", "--port", "8001"]
