FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so code edits don't bust the layer cache. Runtime
# requirements only — pytest and its tree have no business in an image that
# faces the internet, and every package that ships is attack surface.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Uploaded media lives on a volume; create the mount point up front.
RUN mkdir -p /app/media && \
    adduser --disabled-password --gecos "" --uid 1000 app && \
    chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# The suite runs against the same layers the runtime image is built from, with
# the test tooling added on top:
#     docker build --target test -t parking-api-test ./backend
FROM base AS test
USER root
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
USER app
CMD ["pytest", "-q"]


# Last stage is what `docker build` produces by default, so the plain build
# stays the lean runtime image.
FROM base AS runtime
