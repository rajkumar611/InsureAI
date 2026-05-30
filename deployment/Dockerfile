FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./backend/
COPY database/ ./database/

ENV PYTHONPATH=/app/backend:/app

EXPOSE 8000

CMD ["uv", "run", "python", "backend/run.py"]
