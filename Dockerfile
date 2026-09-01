FROM python:3.12-slim

# flock (스케줄 잡 중복 방지), curl (supercronic 설치)
RUN apt-get update && apt-get install -y --no-install-recommends util-linux curl \
    && rm -rf /var/lib/apt/lists/*

# supercronic — 컨테이너 전용 cron (ARM64)
ARG SUPERCRONIC_VERSION=v0.2.33
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSLo /usr/local/bin/supercronic \
       "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${ARCH}" \
    && chmod +x /usr/local/bin/supercronic

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# 의존성 레이어 (소스 변경과 분리)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --all-extras --no-install-project

COPY . .
RUN uv sync --frozen --no-dev --all-extras

CMD ["supercronic", "-passthrough-logs", "/app/crontab"]
