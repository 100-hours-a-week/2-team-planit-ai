FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md /app/
COPY app /app/app
COPY main.py /app/main.py

RUN pip install --upgrade pip && pip install .
RUN mkdir -p /var/log/planit

EXPOSE 8000

CMD ["sh", "-c", "python main.py 2>&1 | tee -a /var/log/planit/app.log"]
