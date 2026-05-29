FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/src/ ./backend/src/
COPY backend/main.py ./backend/
COPY backend/alembic/ ./backend/alembic/
COPY backend/alembic.ini ./backend/

ENV PYTHONPATH=/app/backend/src

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
