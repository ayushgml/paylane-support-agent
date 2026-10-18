FROM ghcr.io/astral-sh/uv:0.9.10 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock /app/backend/
COPY backend/src /app/backend/src
RUN uv sync --project backend --locked --no-dev
COPY backend/prompts /app/backend/prompts
COPY backend/scenarios /app/backend/scenarios
COPY backend/reports /app/backend/reports
COPY backend/deployment.py /app/backend/deployment.py
ENV PYTHONUNBUFFERED=1 PAYLANE_DATA_DIR=/data
CMD ["sh", "-c", "exec /app/backend/.venv/bin/uvicorn deployment:create_hosted_app --factory --app-dir /app/backend --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
