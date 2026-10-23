#!/bin/bash
set -euo pipefail

# ==============================================================================
# Let's Encrypt SSL Initialization Script for Live Chat Platform
# Issue: Backend #5 (Observability & SSL)
# Run this on the EC2 production host (/opt/livechat-server)
# ==============================================================================

if [ ! -f .env ]; then
  echo "Error: .env file not found. Copy .env.production.example to .env and configure DOMAIN_NAME."
  exit 1
fi

set -a
. ./.env
set +a

if [ -z "${DOMAIN_NAME:-}" ] || [ "${DOMAIN_NAME}" = "livechat.example.com" ]; then
  echo "Error: Please set a valid DOMAIN_NAME in .env before requesting SSL certificate."
  exit 1
fi

if [ -z "${CERTBOT_EMAIL:-}" ] || [ "${CERTBOT_EMAIL}" = "admin@example.com" ]; then
  echo "Error: Please set a valid CERTBOT_EMAIL in .env."
  exit 1
fi

echo "==> Starting Nginx in HTTP mode for ACME Challenge validation..."
docker compose up -d nginx

echo "==> Requesting Let's Encrypt SSL Certificate for ${DOMAIN_NAME}..."
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "${CERTBOT_EMAIL}" \
  --agree-tos \
  --no-eff-email \
  --cert-name livechat \
  -d "${DOMAIN_NAME}"

echo "==> Activating HTTPS Nginx configuration..."
cp ./nginx/ssl.conf ./nginx/default.conf

echo "==> Reloading Nginx with TLS enabled..."
docker compose restart nginx

echo "==> SSL Certificate installed successfully!"
echo "    Access your application at: https://${DOMAIN_NAME}"
echo "    Grafana Dashboard at:        https://${DOMAIN_NAME}/grafana"
