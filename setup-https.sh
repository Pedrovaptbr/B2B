#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Setup HTTPS na VPS — useb2bzap.com.br
# Roda esse script UMA vez na VPS (como root) depois de:
#   1. DNS já estar apontando useb2bzap.com.br → IP da VPS (testa com: dig +short useb2bzap.com.br)
#   2. .env já estar atualizado (DEBUG=False, SITE_URL=https://..., ALLOWED_HOSTS=...)
#   3. nginx/nginx.conf já estar com seu domínio real (já está: useb2bzap.com.br)
# ──────────────────────────────────────────────────────────────────────────────
set -e

DOMINIO="useb2bzap.com.br"
EMAIL="ogrupocastle@gmail.com"   # usado pelo Let's Encrypt para avisos de renovação

echo "==> 1/6: Conferindo se DNS resolve pra essa máquina..."
IP_VPS=$(curl -s ifconfig.me)
IP_DNS=$(dig +short $DOMINIO | tail -n1)
echo "    IP da VPS: $IP_VPS"
echo "    IP do DNS: $IP_DNS"
if [ "$IP_VPS" != "$IP_DNS" ]; then
    echo "❌  DNS ainda não aponta pra essa VPS. Aguarde propagação e rode de novo."
    exit 1
fi
echo "✅  DNS OK"

echo ""
echo "==> 2/6: Instalando nginx e certbot..."
apt update -qq
apt install -y nginx certbot python3-certbot-nginx

echo ""
echo "==> 3/6: Copiando nginx.conf do projeto..."
cp /opt/b2bzap/nginx/nginx.conf /etc/nginx/sites-available/b2bzap
ln -sf /etc/nginx/sites-available/b2bzap /etc/nginx/sites-enabled/b2bzap
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/certbot

# Antes do SSL existir, comenta o bloco HTTPS pra nginx subir sem erro
sed -i '/listen 443 ssl/,$ s/^/#/' /etc/nginx/sites-available/b2bzap

nginx -t
systemctl reload nginx

echo ""
echo "==> 4/6: Gerando certificado SSL com Let's Encrypt..."
certbot certonly --webroot -w /var/www/certbot \
    -d $DOMINIO -d www.$DOMINIO \
    --email $EMAIL --agree-tos --non-interactive

echo ""
echo "==> 5/6: Restaurando nginx.conf com HTTPS ativo..."
cp /opt/b2bzap/nginx/nginx.conf /etc/nginx/sites-available/b2bzap
nginx -t
systemctl reload nginx

echo ""
echo "==> 6/6: Subindo o Docker Compose (já com .env atualizado)..."
cd /opt/b2bzap
docker compose down
docker compose up -d --build

echo ""
echo "✅  Pronto! Testa: https://$DOMINIO"
echo "    Renovação SSL automática (cron do certbot)."
