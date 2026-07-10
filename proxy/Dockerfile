# The `proxy` service: terminates TLS in front of `web` and `api` (AC4, NFR-06).
FROM nginx:1.29-alpine

# `openssl` is not guaranteed present in the nginx alpine image, and the entrypoint
# needs it to mint a development certificate on first start.
RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 443

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
