# syntax=docker/dockerfile:1.13.0@sha256:426b85b823c113372f766a963f68cfd9cd4878e1bcc0fda58779127ee98a28eb
FROM python:3.13.1-slim-bookworm@sha256:031ebf3cde9f3719d2db385233bcb18df5162038e9cda20e64e08f49f4b47a2f
ARG VERSION=0.1.0dev0

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    FORCE_COLOR=1 \
    BROWSER_PATH=/headless-shell/headless-shell \
    VERSION="${VERSION}"

WORKDIR /action

# renovate: release=bookworm depName=libnspr4
ENV LIBNSPR4_VERSION="2:4.35-1"
# renovate: release=bookworm depName=libnss3
ENV LIBNSS3_VERSION="2:3.87.1-1+deb12u1"
# renovate: release=bookworm depName=libexpat1
ENV LIBEXPAT1_VERSION="2.5.0-1+deb12u1"
# renovate: release=bookworm depName=libfontconfig1
ENV LIBFONTCONFIG1_VERSION="2.14.1-4"
# renovate: release=bookworm depName=libuuid1
ENV LIBUUID1_VERSION="2.38.1-5+deb12u3"

# Headless chrome, used to convert graphs to static images
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
        libnspr4=${LIBNSPR4_VERSION} \
        libnss3=${LIBNSS3_VERSION} \
        libexpat1=${LIBEXPAT1_VERSION} \
        libfontconfig1=${LIBFONTCONFIG1_VERSION} \
        libuuid1=${LIBUUID1_VERSION} \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
COPY --from=docker.io/chromedp/headless-shell:stable@sha256:7fc3f7ede786598da4fad64cb57201ac6e78e6e4ba4e7318908a51fe06585093 \
    /headless-shell/ \
    /headless-shell/

# Create a virtualenv with dependencies and project
RUN --mount=from=ghcr.io/astral-sh/uv:0.5.29@sha256:88d7b48fc9f17462c82b5482e497af250d337f3f14e1ac97c16e68eba49b651e,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=src/,target=src/ \
    uv sync --no-group dev --no-editable

ENTRYPOINT [ "/action/.venv/bin/action" ]
