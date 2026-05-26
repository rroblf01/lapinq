FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build
COPY . .
RUN uv pip install --system --no-cache-dir maturin && \
    maturin build --release --out /wheels && \
    uv pip install --system --no-cache-dir /wheels/*.whl && \
    uv pip install --system --no-cache-dir -r /build/example/app/requirements.txt

RUN mkdir -p /workspace && cp -r /build/example /workspace/example && \
    rm -rf /build /wheels /root/.cargo /root/.rustup

WORKDIR /workspace/example
