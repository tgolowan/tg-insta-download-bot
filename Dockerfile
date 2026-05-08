# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bot.py config.py link_mirror.py ./

# Railway / platforms pass PORT for the Flask health endpoint
ENV PORT=8000
EXPOSE 8000

CMD ["python", "bot.py"]
