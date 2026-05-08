# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -r requirements.txt

COPY bot.py config.py link_mirror.py tiktok_downloader.py tiktok_urls.py ./

# Railway / platforms pass PORT for the Flask health endpoint
ENV PORT=8000
EXPOSE 8000

CMD ["python", "bot.py"]
