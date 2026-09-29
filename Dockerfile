FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_PATH=/app/data/bot.db

WORKDIR /app

COPY requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 bot \
    && useradd --uid 10001 --gid bot --create-home --shell /usr/sbin/nologin bot \
    && mkdir -p /app/data \
    && chown -R bot:bot /app

COPY --chown=bot:bot app ./app

USER 10001:10001

CMD ["python", "-m", "app.main"]
