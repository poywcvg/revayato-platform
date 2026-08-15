FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system revayato \
    && useradd --system --gid revayato --home-dir /app --shell /usr/sbin/nologin revayato \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

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
# Multiple ASGI workers share Redis channel layers; tune with WEB_CONCURRENCY.
# Trust proxy headers only from Cloudflare's published edge ranges and the
# private Docker reverse-proxy network. --forwarded-allow-ips='*' would let any
# client inject X-Forwarded-For and override REMOTE_ADDR (spoofed client IP,
# throttle evasion); CF ranges refresh from https://api.cloudflare.com/client/v4/ips.
CMD ["sh", "-c", "exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-3} --proxy-headers --forwarded-allow-ips='127.0.0.1,172.16.0.0/12,10.0.0.0/8,173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,2400:cb00::/32,2606:4700::/32,2803:f800::/32,2405:b500::/32,2405:8100::/32,2a06:98c0::/29,2c0f:f248::/32' --timeout-keep-alive ${WEB_KEEPALIVE_SECONDS:-15} --limit-concurrency ${WEB_LIMIT_CONCURRENCY:-80} --limit-max-requests ${WEB_MAX_REQUESTS:-1500} --limit-max-requests-jitter ${WEB_MAX_REQUESTS_JITTER:-150}"]
