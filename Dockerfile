FROM --platform=$BUILDPLATFORM golang:1.27.3-bookworm AS tailscale-build

ARG TARGETOS
ARG TARGETARCH
ARG TAILSCALE_VERSION=v1.104.5

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${TAILSCALE_VERSION}" https://github.com/tailscale/tailscale.git /src
WORKDIR /src

# Build from the official Tailscale release source with the patched Go modules
# while upstream releases catch up with the fixed dependency versions.
RUN go get github.com/klauspost/compress@v1.20.2 golang.org/x/net@v0.62.0 \
    && test "$(go list -m -f '{{.Version}}' github.com/klauspost/compress)" = v1.20.2 \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/net)" = v0.62.0 \
    && mkdir -p /out \
    && GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" CGO_ENABLED=0 ./build_dist.sh -o /out/tailscaled tailscale.com/cmd/tailscaled \
    && GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" CGO_ENABLED=0 ./build_dist.sh -o /out/tailscale tailscale.com/cmd/tailscale

FROM python:3.11-slim

ARG APP_VERSION=v0.4.16
LABEL org.opencontainers.image.title="Synology Photo Tagger" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="Synology Photos AI tagging with scheduled work, trusted-device login, and automatic verified writes."

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates openssh-server util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tailscale-build /out/tailscaled /usr/sbin/tailscaled
COPY --from=tailscale-build /out/tailscale /usr/bin/tailscale

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
