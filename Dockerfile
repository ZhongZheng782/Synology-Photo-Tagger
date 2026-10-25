FROM python:3.11-slim

ARG APP_VERSION=v0.3.1
LABEL org.opencontainers.image.title="Synology Photo Tagger" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="Synology Photos browser with read-only local MLX photo analysis suggestions."

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl openssh-server \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000 \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY templates ./templates
COPY static ./static
COPY entrypoint.sh ./
RUN chmod 755 /app/entrypoint.sh

EXPOSE 5000 22

CMD ["/app/entrypoint.sh"]
