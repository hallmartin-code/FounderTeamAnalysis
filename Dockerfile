# Railway builds this image. Everything the app needs is baked in; the API key is not.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Optional: uncomment to support legacy .ppt and image-only .pptx decks.
# This adds ~450 MB to the image; .pdf and text-bearing .pptx work without it.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libreoffice-impress fonts-dejavu-core \
#  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer first, so code edits do not reinstall the world.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[web]"

# Drop root before serving.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
ENV PORT=8000

# Railway injects $PORT. One worker: jobs live in this process's memory.
CMD ["sh", "-c", "uvicorn onepager.web.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]
