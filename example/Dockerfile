FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir maturin && \
    maturin build --release --out /wheels && \
    pip install --no-cache-dir /wheels/*.whl && \
    pip install --no-cache-dir -r /build/example/app/requirements.txt

RUN mkdir -p /workspace && cp -r /build/example /workspace/example && \
    rm -rf /build /wheels /root/.cargo /root/.rustup

WORKDIR /workspace/example
