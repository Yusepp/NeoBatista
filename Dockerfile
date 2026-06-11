FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md LICENSE neo_batista.py ./
COPY neobatista ./neobatista
RUN python -m pip install --prefix=/install .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg nodejs ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 neobatista

COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=neobatista:neobatista neo_batista.py ./
COPY --chown=neobatista:neobatista neobatista ./neobatista
COPY --chown=neobatista:neobatista scripts ./scripts

USER neobatista
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "scripts/healthcheck.py"]

CMD ["python", "neo_batista.py"]
