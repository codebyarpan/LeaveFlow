# The `api` service: FastAPI + uvicorn (AC4, AC7).
#
# python:3.13-slim, not 3.14. The spine pins 3.13 deliberately, for library
# compatibility. A later story must not upgrade it.
FROM python:3.13-slim

# libpq5 is the PostgreSQL client library that psycopg 3 loads at runtime.
#
# We install it from the distribution rather than depending on `psycopg[binary]`,
# whose bundled libpq does not track system security updates. That is the story's
# stated preference for a deployed environment, and this image is one.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# NOTE on layer caching: `pip install .` needs the package source, so the install
# runs after every COPY and any source edit re-resolves the dependencies. That is
# a deliberate simplicity trade — this image is rebuilt rarely, and a deps-only
# install layer would mean maintaining a second dependency listing. Revisit only
# if rebuild time actually starts to hurt.
COPY pyproject.toml ./
COPY app ./app
COPY seed ./seed
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .

# Run unprivileged. Nothing in the api service needs root once the image is built.
RUN useradd --system --create-home --uid 10001 leaveflow

# Story 4.1 (AD-15): the `documents` named volume mounts at /srv/documents. Pre-create it
# OWNED BY the runtime user: a named volume initializes its ownership from the image's
# directory on FIRST use, and without this it arrives root-owned — every upload then dies
# as a PermissionError 500 in the deployed stack while the whole host-side test suite stays
# green (found live through the :8443 proxy check, not guessed).
RUN mkdir -p /srv/documents && chown leaveflow:leaveflow /srv/documents

USER leaveflow

EXPOSE 8000

# No --reload, no --workers here. AD-7: the rollover is a cron-invoked CLI job, not an
# in-process scheduler, precisely so that the worker count is free to change without
# firing the job once per worker.
#
# --forwarded-allow-ips=*: uvicorn honours X-Forwarded-Proto only from IPs it
# trusts, and the default is loopback — which the nginx proxy, connecting over the
# compose network, is not. Without this, every server-generated absolute URL (a
# trailing-slash 307, the docs redirect) says `http://` and dead-ends, because no
# plaintext port exists (NFR-06). Trusting every peer is safe HERE because compose
# publishes no host port for this service: the proxy is the only possible client.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
