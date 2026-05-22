FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY configs ./configs
COPY db ./db

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["uvicorn", "nutmeg.main:app", "--host", "0.0.0.0", "--port", "8000"]
