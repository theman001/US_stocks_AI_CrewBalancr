FROM python:3.12-slim

# flock (스케줄 잡 중복 방지), curl (supercronic 설치), git (crewai 일부 의존성)
RUN apt-get update && apt-get install -y --no-install-recommends util-linux curl git \
    && rm -rf /var/lib/apt/lists/*

# supercronic — 컨테이너 전용 cron (Go 단일 바이너리, arm64/amd64)
ARG SUPERCRONIC_VERSION=v0.2.33
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSLo /usr/local/bin/supercronic \
       "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${ARCH}" \
    && chmod +x /usr/local/bin/supercronic

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# 의존성 레이어 (소스 변경과 분리 — 캐시 히트)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --all-extras --no-install-project

COPY . .
RUN uv sync --frozen --no-dev --all-extras

# bge-m3 가중치(~2.3GB)는 베이크 안 함 — 첫 RAG 배치(가동 후 수 주) 때 HF 에서 1회 다운로드,
# compose 의 hf-cache 명명 볼륨에 영구 보존 (컨테이너 교체·이미지 갱신에도 유지).
ENV HF_HOME=/app/hf-cache

# 스케줄은 deploy/crontab (COPY . . 로 이미 /app/deploy/crontab). 변경 시 push → 재빌드.
CMD ["supercronic", "-passthrough-logs", "/app/deploy/crontab"]
