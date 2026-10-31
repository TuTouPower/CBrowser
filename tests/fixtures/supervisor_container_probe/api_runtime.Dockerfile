FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src/backend
RUN pip install --no-cache-dir "fastapi>=0.115.0" "uvicorn>=0.34.0" \
    "pydantic>=2.0" "httpx>=0.27.0" "sqlalchemy[asyncio]>=2.0.0" \
    "alembic>=1.13.0" "aiosqlite>=0.20.0" "argon2-cffi>=23.1.0"
COPY src/backend/cbrowser/api /app/src/backend/cbrowser/api
COPY src/backend/cbrowser/auth /app/src/backend/cbrowser/auth
COPY src/backend/cbrowser/domain /app/src/backend/cbrowser/domain
COPY src/backend/cbrowser/services /app/src/backend/cbrowser/services
COPY src/backend/cbrowser/adapters /app/src/backend/cbrowser/adapters
COPY src/backend/diagnostics.py /app/src/backend/diagnostics.py
COPY src/backend/migrations /app/src/backend/migrations
ENTRYPOINT ["python3", "-m", "uvicorn", "cbrowser.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
