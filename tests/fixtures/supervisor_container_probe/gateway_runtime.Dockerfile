FROM python:3.12-slim-bookworm
WORKDIR /probe
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
RUN pip install --no-cache-dir aiohttp==3.14.5 pydantic==2.14.1
COPY src/backend/cbrowser/supervisor/agent_credentials.py /app/cbrowser/supervisor/agent_credentials.py
COPY src/backend/cbrowser/supervisor/__init__.py /app/cbrowser/supervisor/__init__.py
COPY tests/fixtures/supervisor_recovery_probe/gateway_fixture.py /probe/gateway_fixture.py
COPY tests/fixtures/supervisor_container_probe/gateway_container.py /probe/gateway_container.py
USER 1000:1000
ENTRYPOINT ["python3", "/probe/gateway_container.py"]
