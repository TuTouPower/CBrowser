FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/sh -m appuser

COPY config/docker/api_runtime/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY src/backend /app

RUN chown -R appuser:appgroup /app

USER 1000:1000

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "cbrowser.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
