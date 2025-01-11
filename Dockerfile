# syntax=docker/dockerfile:1.12.1@sha256:93bfd3b68c109427185cd78b4779fc82b484b0b7618e36d0f104d4d801e66d25
FROM python:3.13.1-slim-bookworm@sha256:1127090f9fff0b8e7c3a1367855ef8a3299472d2c9ed122948a576c39addeaf1
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
COPY --from=docker.io/chromedp/headless-shell:stable@sha256:ec3c8e860f7659a2dc0c65d33b37f0226191a424c154bbe77c27dbd7f76e28dc \
    /headless-shell/ \
    /headless-shell/

# Create a virtualenv with dependencies and project
RUN --mount=from=ghcr.io/astral-sh/uv:0.5.18@sha256:e2101b9e627153b8fe4e8a1249cc4194f1b38ece7f28a5a9b8f958e3b560e69c,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=src/,target=src/ \
    uv sync --no-group dev --no-editable

ENTRYPOINT [ "/action/.venv/bin/action" ]
