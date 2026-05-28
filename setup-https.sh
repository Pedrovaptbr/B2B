#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Setup HTTPS na VPS — useb2bzap.com.br
#
# Pré-requisitos:
#   1. DNS apontando useb2bzap.com.br → IP da VPS (testa: dig +short useb2bzap.com.br)
#   2. .env atualizado (DEBUG=False, SITE_URL=https://..., ALLOWED_HOSTS=...)
#
# Como rodar (na VPS, como root):
#   cd /opt/b2bzap
#   chmod +x setup-https.sh
#   ./setup-https.sh
# ──────────────────────────────────────────────────────────────────────────────
set -e

DOMINIO="useb2bzap.com.br"
EMAIL="ogrupocastle@gmail.com"   # usado pelo Let's Encrypt para avisos de renovação

echo "==> 1/5: Conferindo se DNS resolve pra essa máquina..."
IP_VPS=$(curl -4 -s ifconfig.me)
IP_DNS=$(dig +short "$DOMINIO" | tail -n1)
echo "    IP da VPS: $IP_VPS"
echo "    IP do DNS: $IP_DNS"
if [ "$IP_VPS" != "$IP_DNS" ]; then
    echo "❌  DNS ainda não aponta pra essa VPS. Aguarde propagação e rode de novo."
    exit 1
fi
echo "✅  DNS OK"
echo ""

echo "==> 2/5: Instalando nginx e certbot..."
apt update -qq
apt install -y nginx certbot python3-certbot-nginx
echo ""

echo "==> 3/5: Copiando nginx.conf do projeto..."
cp /opt/b2bzap/nginx/nginx.conf /etc/nginx/sites-available/b2bzap
ln -sf /etc/nginx/sites-available/b2bzap /etc/nginx/sites-enabled/b2bzap
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/certbot
nginx -t
systemctl reload nginx
echo ""

echo "==> 4/5: Gerando certificado SSL com Let's Encrypt..."
# O plugin --nginx adiciona automaticamente o bloco HTTPS + redirect HTTP→HTTPS
certbot --nginx -d "$DOMINIO" -d "www.$DOMINIO" \
    --email "$EMAIL" --agree-tos --non-interactive --redirect
echo ""

echo "==> 5/5: Subindo Docker Compose (force-recreate pra carregar .env atualizado)..."
cd /opt/b2bzap
docker compose up -d --force-recreate
echo ""

echo "✅  Pronto! Testa: https://$DOMINIO"
echo "    Renovação SSL automática via cron do certbot."
