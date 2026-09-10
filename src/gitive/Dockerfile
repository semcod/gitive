FROM python:3.12-slim-bookworm AS gitbuild
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libssl-dev libcurl4-gnutls-dev libexpat1-dev zlib1g-dev gettext xz-utils ca-certificates
ADD --checksum=sha256:60a7c2251cc2e588d5cd87bae567260617c6de0c22dca9cdbfc4c7d2b8990b62 https://www.kernel.org/pub/software/scm/git/git-2.51.0.tar.xz /tmp/git.tar.xz
RUN tar -xf /tmp/git.tar.xz -C /tmp && cd /tmp/git-2.51.0 && make -j4 prefix=/usr/local NO_TCLTK=YesPlease all && make prefix=/usr/local NO_TCLTK=YesPlease install
FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends git make age && rm -rf /var/lib/apt/lists/*
COPY --from=gitbuild /usr/local/bin/git /usr/local/bin/git
COPY --from=gitbuild /usr/local/libexec/git-core /usr/local/libexec/git-core
RUN git --version
RUN pip install --no-cache-dir litellm==1.83.7 numpy==2.2.6 python-dotenv==1.0.1
COPY src/gitive/vendor /opt/gitive-vendor
RUN python -c "import pathlib,json,hashlib; p=pathlib.Path('/opt/gitive-vendor'); m=json.loads((p/'manifest.json').read_text()); assert hashlib.sha256(next(p.glob('llm_account_inventory*.whl')).read_bytes()).hexdigest()==m['sha256']" && python -c "import pathlib,json,hashlib; p=pathlib.Path('/opt/gitive-vendor'); m=json.loads((p/'planfile-manifest.json').read_text()); assert hashlib.sha256((p/m['file']).read_bytes()).hexdigest()==m['sha256']" && pip install --no-cache-dir /opt/gitive-vendor/*.whl
COPY --from=gitbuild /usr/local/share/git-core /usr/local/share/git-core
WORKDIR /app
COPY src/gitive /app/src/gitive
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
EXPOSE 8787
CMD ["python", "-m", "gitive.server"]
