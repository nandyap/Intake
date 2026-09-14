# syntax=docker/dockerfile:1
#
# Backend — FastAPI + Microsoft Agent Framework.
# Runs as a non-root user; no secrets baked in (managed identity at runtime).

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so the layer caches across code changes.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Governed artifacts ship with the image so retrieval can fail closed on a
# known-good manifest. Replacing a seed with a governed artifact is a
# manifest version bump and a redeploy.
COPY artifacts/ /artifacts/
ENV ARTIFACT_ROOT=/artifacts

RUN useradd --create-home --uid 1001 appuser \
    && chown -R appuser:appuser /app /artifacts
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
