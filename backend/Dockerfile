FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system revayato \
    && useradd --system --gid revayato --home-dir /app --shell /usr/sbin/nologin revayato

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY --chown=revayato:revayato . .
RUN mkdir -p /app/staticfiles /app/media \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R revayato:revayato /app/staticfiles /app/media

USER revayato

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
