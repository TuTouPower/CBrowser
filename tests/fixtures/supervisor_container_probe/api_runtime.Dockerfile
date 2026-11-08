FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src/backend
RUN pip install --no-cache-dir "fastapi==0.162.0" "uvicorn==0.54.0" \
    "pydantic==2.14.1" "httpx==0.28.1" "sqlalchemy[asyncio]==2.1.8" \
    "alembic==1.20.1" "aiosqlite==0.22.1" "argon2-cffi==25.1.0" \
    "websockets==17.4"
COPY src/backend/cbrowser/__init__.py /app/src/backend/cbrowser/__init__.py
COPY src/backend/cbrowser/secret_files.py /app/src/backend/cbrowser/secret_files.py
COPY src/backend/cbrowser/launch_args.py /app/src/backend/cbrowser/launch_args.py
COPY src/backend/cbrowser/gateway /app/src/backend/cbrowser/gateway
COPY src/backend/cbrowser/api /app/src/backend/cbrowser/api
COPY src/backend/cbrowser/auth /app/src/backend/cbrowser/auth
COPY src/backend/cbrowser/domain /app/src/backend/cbrowser/domain
COPY src/backend/cbrowser/services /app/src/backend/cbrowser/services
COPY src/backend/cbrowser/adapters /app/src/backend/cbrowser/adapters
COPY src/backend/diagnostics.py /app/src/backend/diagnostics.py
COPY src/backend/migrations /app/src/backend/migrations
ENTRYPOINT ["python3", "-m", "uvicorn", "cbrowser.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
