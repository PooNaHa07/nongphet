#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "🔐 Generating 10-year SSL Certificate for Nong Phet AI Guide..."
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 3650 \
  -subj "/CN=raspberrypi.local" \
  -addext "subjectAltName=DNS:raspberrypi.local,DNS:raspberrypi,DNS:localhost,IP:192.168.1.162,IP:127.0.0.1"

chmod 600 key.pem
chmod 644 cert.pem

echo "✅ SSL Certificate generated successfully!"
echo "🔄 Restarting nongphet service..."
echo nongphet999 | sudo -S systemctl restart nongphet
echo "🎉 Done! Nong Phet is now permanently running with HTTPS on https://192.168.1.162:5000"