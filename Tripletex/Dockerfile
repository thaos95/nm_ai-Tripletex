FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY setup.py pyproject.toml README.md /app/
COPY app /app/app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
