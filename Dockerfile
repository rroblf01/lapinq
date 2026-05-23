# Stage 1: Build Rust worker
FROM rust:1.95-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src/ src/
RUN cargo build --release

# Stage 2: Python runtime
FROM python:3.14-slim-bookworm

WORKDIR /app

# Install system deps for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Rust binary
COPY --from=builder /build/target/release/lapinq-worker /usr/local/bin/lapinq-worker

# Install Python package
COPY pyproject.toml Cargo.toml README.md ./
COPY python/ python/
COPY src/ src/
RUN pip install --no-cache-dir maturin && maturin develop --release

EXPOSE 8001

CMD ["python", "-m", "lapinq", "server", "--host", "0.0.0.0", "--port", "8001"]
