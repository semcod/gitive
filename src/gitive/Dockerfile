FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends git make age && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir litellm==1.83.7 numpy==2.2.6 python-dotenv==1.0.1
COPY src/gitive/vendor /opt/gitive-vendor
RUN python -c "import pathlib,json,hashlib; p=pathlib.Path('/opt/gitive-vendor'); m=json.loads((p/'manifest.json').read_text()); assert hashlib.sha256(next(p.glob('*.whl')).read_bytes()).hexdigest()==m['sha256']" && pip install --no-cache-dir /opt/gitive-vendor/*.whl
WORKDIR /app
COPY src/gitive /app/src/gitive
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
EXPOSE 8787
CMD ["python", "-m", "gitive.server"]
