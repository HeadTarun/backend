FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --extra ui

COPY . .
EXPOSE 8000 8501
CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port 8000 & uv run streamlit run UI/streamlit_app.py --server.address 0.0.0.0 --server.port 8501"]
