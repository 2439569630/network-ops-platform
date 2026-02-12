FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8000

ENV FASTAPI_HOST=0.0.0.0 \
    FASTAPI_PORT=8000 \
    SUPERVISOR_LOG_MODE=stdout

ENTRYPOINT ["tini", "--"]
CMD ["python", "supervisor.py"]
