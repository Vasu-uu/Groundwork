# Groundwork API. Build from the repository root (the sample sets live there):
#   docker build -f backend/Dockerfile -t groundwork-api .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# Dependencies first, so code changes do not reinstall them.
COPY backend/pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install . \
    && pip uninstall -y groundwork-backend

COPY backend/ ./
COPY samples/ /app/samples/

RUN useradd --create-home groundwork && mkdir -p data && chown groundwork data
USER groundwork

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
