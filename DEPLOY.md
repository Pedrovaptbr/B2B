# Deploy B2BZap na VPS

Guia completo do zero para colocar o B2BZap em produção com Docker, nginx e SSL.

---

## Pré-requisitos

- VPS com Ubuntu 22.04 (recomendado mínimo 1 vCPU / 1 GB RAM)
- Domínio apontando para o IP da VPS (registro A: `seudominio.com.br` → IP da VPS)
- Acesso SSH como root ou usuário com sudo

---

## 1. Preparar a VPS

```bash
# Atualiza o sistema
apt update && apt upgrade -y

# Instala Docker e Docker Compose
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# Verifica instalação
docker --version
docker compose version
```

---

## 2. Instalar o nginx e Certbot

```bash
apt install -y nginx certbot python3-certbot-nginx
```

---

## 3. Clonar o repositório

```bash
cd /opt
git clone https://github.com/SEU_USUARIO/b2bzap.git
cd b2bzap
```

---

## 4. Configurar o arquivo .env

```bash
cp .env.example .env
nano .env
```

Preencha **todos** os campos. Os mais importantes:

| Variável | O que colocar |
|---|---|
| `DJANGO_SECRET_KEY` | Gere com: `python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `ALLOWED_HOSTS` | `seudominio.com.br,www.seudominio.com.br` |
| `SITE_URL` | `https://seudominio.com.br` |
| `GOOGLE_API_KEY` | Sua chave do Google Maps |
| `EVOLUTION_API_KEY` | Uma senha forte (ex: `minhachavesecreta123`) |
| `EVOLUTION_API_URL` | `http://evolution:8080` (nome do container Docker) |
| `STRIPE_PUBLIC_KEY` | `pk_live_...` do Dashboard Stripe |
| `STRIPE_SECRET_KEY` | `sk_live_...` do Dashboard Stripe |
| `STRIPE_WEBHOOK_SECRET` | Ver Passo 8 abaixo |
| Todos os `STRIPE_*_PRICE_ID` | IDs do Dashboard Stripe → Products |

---

## 5. Configurar o nginx

```bash
# Copia o arquivo de configuração
cp nginx/nginx.conf /etc/nginx/sites-available/b2bzap

# Substitui o domínio (troque seudominio.com.br pelo seu domínio real)
sed -i 's/seudominio.com.br/SEU_DOMINIO_AQUI/g' /etc/nginx/sites-available/b2bzap

# Ativa o site
ln -s /etc/nginx/sites-available/b2bzap /etc/nginx/sites-enabled/b2bzap

# Remove o default se existir
rm -f /etc/nginx/sites-enabled/default

# Testa a configuração
nginx -t

# Recarrega o nginx
systemctl reload nginx
```

---

## 6. Gerar certificado SSL

```bash
# Substitua pelo seu domínio real
certbot --nginx -d seudominio.com.br -d www.seudominio.com.br

# Aceita os termos, informe seu email
# Certbot atualiza o nginx.conf automaticamente com os caminhos do certificado
```

O Certbot configura renovação automática. Para verificar:
```bash
systemctl status certbot.timer
```

---

## 7. Subir a aplicação com Docker Compose

```bash
cd /opt/b2bzap

# Builda e sobe em background
docker compose up -d --build

# Acompanha os logs
docker compose logs -f web
docker compose logs -f evolution
```

O Django roda na porta `127.0.0.1:8000` (só acessível pelo nginx).
A Evolution API roda na porta `127.0.0.1:8081` (só acessível internamente).

---

## 8. Configurar o Webhook do Stripe

1. Acesse [dashboard.stripe.com](https://dashboard.stripe.com) → **Developers → Webhooks**
2. Clique em **"Add endpoint"**
3. URL do endpoint: `https://seudominio.com.br/accounts/webhook/stripe/`
4. Eventos para escutar:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
   - `checkout.session.completed`
5. Copie o **Signing secret** (`whsec_...`)
6. Adicione ao `.env`: `STRIPE_WEBHOOK_SECRET=whsec_...`
7. Reinicie o container:

```bash
docker compose restart web
```

---

## 9. Criar o superusuário do Django (admin)

```bash
docker compose exec web python manage.py createsuperuser
```

Acesse o painel admin em: `https://seudominio.com.br/admin/`

---

## 10. Criar os planos no banco (comando personalizado)

```bash
docker compose exec web python manage.py criar_planos
```

---

## Comandos úteis do dia a dia

```bash
# Ver logs em tempo real
docker compose logs -f

# Reiniciar tudo
docker compose restart

# Atualizar após git pull
git pull
docker compose up -d --build

# Acessar o shell do Django
docker compose exec web python manage.py shell

# Fazer backup do banco
docker compose exec web cp /data/db.sqlite3 /data/db_backup_$(date +%Y%m%d).sqlite3
```

---

## Estrutura dos containers

```
nginx (host) :443 / :80
    ↓ proxy
b2bzap_app (Docker) :8000
    ↓ HTTP
b2bzap_evolution (Docker) :8080
```

Dados persistentes ficam em volumes Docker:
- `sqlite_data` → banco de dados (`/data/db.sqlite3`)
- `evolution_store` → sessões WhatsApp (`/evolution/store`)

---

## Solução de problemas comuns

**App não sobe / erro 502:**
```bash
docker compose logs web
```

**Evolution API não conecta:**
```bash
docker compose logs evolution
# Verifique que EVOLUTION_API_URL=http://evolution:8080 no .env
# Verifique que EVOLUTION_API_KEY bate com AUTHENTICATION_API_KEY no compose
```

**Certificado SSL não renova:**
```bash
certbot renew --dry-run
```

**Erro de CSRF (403 Forbidden em formulários):**
- Verifique que `SITE_URL=https://seudominio.com.br` no `.env` (com https)
- Verifique que `ALLOWED_HOSTS` inclui seu domínio
