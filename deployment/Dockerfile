FROM python:3.12-slim as builder
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY --from=builder /app/.venv /app/.venv
COPY backend/ ./backend/
COPY database/ ./database/
COPY frontend/ ./frontend/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend:/app

EXPOSE 8081
CMD ["python", "backend/run.py"]
