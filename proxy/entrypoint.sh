#!/bin/sh
# Generate a self-signed TLS certificate on first start, then run nginx.
#
# Implements: AC4 (the proxy terminates TLS), AC5 (no secret is committed),
# NFR-06 (credentials and tokens travel over TLS in any deployed environment).
#
# Why generated rather than committed: a TLS private key is a secret. Committing one —
# even a "development only" one — puts a private key in version control, which AC5
# forbids without qualification, and trains everyone reading the repository that it is
# an acceptable thing to do.
#
# Why at container start rather than as a fourth setup command: AC1 fixes setup at
# exactly three operator commands. A `make certs` step before `docker compose up` would
# be a fourth, and NFR-21's reproducibility claim would quietly stop being true.
#
# Idempotent: an existing certificate in the mounted volume is left alone, so restarting
# the proxy does not invalidate a certificate the browser has already been told to trust.
#
# A DEPLOYED environment must mount a real certificate over this volume. Self-signed is
# acceptable locally; it is not acceptable in front of real credentials.

set -eu

CERT_DIR=/etc/nginx/certs
CERT="$CERT_DIR/leaveflow.crt"
KEY="$CERT_DIR/leaveflow.key"

# Regenerate when the certificate is missing OR expired. Without the expiry check,
# a `proxy_certs` volume older than the cert's validity serves an expired
# certificate forever, and the only "fix" an operator would find is guessing to
# delete the volume.
if [ ! -f "$CERT" ] || [ ! -f "$KEY" ] || ! openssl x509 -checkend 0 -noout -in "$CERT" >/dev/null; then
    echo "proxy: no valid certificate found, generating a self-signed one for local development"
    mkdir -p "$CERT_DIR"

    # subjectAltName, not just CN: every current browser and `curl` ignores CN for
    # hostname verification and requires a SAN.
    #
    # stderr is NOT silenced: under `set -e` a generation failure (read-only
    # volume, full disk) ends the container, and its last words should say why.
    openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
        -keyout "$KEY" -out "$CERT" \
        -subj "/CN=localhost/O=LeaveFlow local development" \
        -addext "subjectAltName=DNS:localhost,DNS:proxy,IP:127.0.0.1"

    chmod 600 "$KEY"
    echo "proxy: certificate generated at $CERT"
else
    echo "proxy: reusing the existing certificate at $CERT"
fi

exec nginx -g 'daemon off;'
