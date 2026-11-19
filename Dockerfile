FROM node:22-bookworm-slim AS node-runtime

FROM python:3.12-slim-bookworm
ARG MG_VERSION=development
LABEL org.opencontainers.image.version=$MG_VERSION org.opencontainers.image.licenses="GPL-3.0-or-later" org.opencontainers.image.source="https://github.com/petrjones/MediaGrabber-NAS"
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ffmpeg tini ca-certificates tzdata libstdc++6 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/LICENSE /usr/local/share/doc/node/LICENSE
WORKDIR /app
COPY requirements-linux.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: --report /app/python-install-report.json -r requirements-linux.lock \
    && pip freeze > /app/installed-dependencies.txt \
    && node --version && yt-dlp --version && ffmpeg -version >/dev/null
COPY mg_nas ./mg_nas
COPY THIRD-PARTY-NOTICES.md ./THIRD-PARTY-NOTICES.md
COPY LICENSE COPYRIGHT PRIVACY.md SOURCE.tar.gz ./
COPY LICENSES ./LICENSES
COPY tools/runtime_inventory.py ./runtime_inventory.py
RUN python runtime_inventory.py > /app/runtime-inventory.json
RUN groupadd --gid 1000 mediagrabber && useradd --uid 1000 --gid 1000 --no-create-home mediagrabber \
    && mkdir /data /downloads && chown 1000:1000 /data /downloads
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    MG_DATA=/data MG_DOWNLOADS=/downloads MG_FFMPEG=/usr/bin/ffmpeg \
    MG_PASSWORD_FILE=/run/secrets/admin_password
USER 1000:1000
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=4).read()"
ENTRYPOINT ["/usr/bin/tini", "--"]
# One process owns the queue. Do not add workers or --preload.
CMD ["gunicorn", "mg_nas.app:create_app()", "--bind", "0.0.0.0:8787", "--workers", "1", "--worker-class", "gthread", "--threads", "8", "--timeout", "1200", "--graceful-timeout", "25", "--worker-tmp-dir", "/tmp", "--access-logfile", "-", "--error-logfile", "-"]
