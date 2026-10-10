FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.17
COPY pyproject.toml uv.lock .python-version README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "pace.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
