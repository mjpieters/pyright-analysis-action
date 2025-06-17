# syntax=docker/dockerfile:1.17.0@sha256:e63addfe27b10e394a5f9f1e866961adc70d08573f1cb80f8d1a0999347b3553
FROM python:3.13.5-slim-bookworm@sha256:f2fdaec50160418e0c2867ba3e254755edd067171725886d5d303fd7057bbf81
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
COPY --from=docker.io/chromedp/headless-shell:stable@sha256:27573b0b3ebf5156df95858ab88a017fc60f1907bf6899a618885169d0881dc0 \
    /headless-shell/ \
    /headless-shell/

# Create a virtualenv with dependencies and project
RUN --mount=from=ghcr.io/astral-sh/uv:0.7.13@sha256:6c1e19020ec221986a210027040044a5df8de762eb36d5240e382bc41d7a9043,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=src/,target=src/ \
    uv sync --no-group dev --no-editable

ENTRYPOINT [ "/action/.venv/bin/action" ]
