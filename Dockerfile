FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /requirements.txt

WORKDIR /app
COPY . /app

CMD ["python3", "bot.py"]
