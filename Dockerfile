FROM node:22-bookworm AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NTERM_DATA_DIR=/data \
    NTERM_BENCH_URL=https://nterm.ai/bench-feed.json

# A network engineer's terminal whose own shell has no network tools is not a
# network tool. The base image ships ssh and nothing else — no ip, ping, dig,
# curl, traceroute or even an editor — so the Local Shell session was useless.
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-client \
      iproute2 \
      iputils-ping \
      iputils-tracepath \
      traceroute \
      dnsutils \
      netcat-openbsd \
      net-tools \
      curl \
      wget \
      telnet \
      socat \
      mtr-tiny \
      tcpdump \
      nano \
      vim-tiny \
      less \
      procps \
      ca-certificates \
    && ln -sf /usr/bin/vim.tiny /usr/bin/vi \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG GIT_SHA=dev
ENV NTERM_BUILD_SHA=${GIT_SHA}

LABEL org.opencontainers.image.title="NTerm" \
      org.opencontainers.image.vendor="ValeronLabs LLC" \
      org.opencontainers.image.source="https://github.com/devnexthop/nterm.ai" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY VERSION ./VERSION
COPY backend/app ./app
COPY --from=frontend /src/dist ./app/static

VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=8 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
