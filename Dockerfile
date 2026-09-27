# syntax=docker/dockerfile:1.7
# PAI — image serveur unique (interface + API /v1 + worker). Chromium inclus pour le rendu PDF.
# Multi-architecture : amd64 et arm64 (Oracle Cloud Ampere A1).
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PAI_DATA_DIR=/app/data \
    ENVIRONMENT=production

WORKDIR /app

COPY requirements.txt .
# Autorité de certification optionnelle (proxy d'entreprise qui ré-chiffre le TLS) :
#   docker build --secret id=ca,src=/chemin/ca.crt .
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install -r requirements.txt

COPY . .
RUN python -m pai build-studio --server \
    && mkdir -p /app/data \
    && chown -R pwuser:pwuser /app/data \
    && chmod 0755 deploy/entrypoint.sh

USER pwuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["web"]
