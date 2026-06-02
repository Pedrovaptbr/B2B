import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DEBUG = os.getenv('DEBUG', 'False') == 'True'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'mudar-na-producao-123')

# Lê do .env: ALLOWED_HOSTS=b2bzap.com.br,www.b2bzap.com.br,localhost
_allowed_hosts_env = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(',') if h.strip()]

# Chaves de API externas
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
EVOLUTION_API_URL = os.getenv('EVOLUTION_API_URL')
EVOLUTION_API_KEY = os.getenv('EVOLUTION_API_KEY')

# ── Stripe ────────────────────────────────────────────────────────────────────
STRIPE_PUBLIC_KEY  = os.getenv('STRIPE_PUBLIC_KEY', '')   # pk_live_... ou pk_test_...
STRIPE_SECRET_KEY  = os.getenv('STRIPE_SECRET_KEY', '')   # sk_live_... ou sk_test_...
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')  # whsec_...
STRIPE_PRICE_ID    = os.getenv('STRIPE_PRICE_ID', '')     # price_... (plano mensal no dashboard)

# Créditos avulsos — preços normais
STRIPE_CREDITS_20_PRICE_ID  = os.getenv('STRIPE_CREDITS_20_PRICE_ID', '')   # R$9,90
STRIPE_CREDITS_50_PRICE_ID  = os.getenv('STRIPE_CREDITS_50_PRICE_ID', '')   # R$22,90
STRIPE_CREDITS_100_PRICE_ID = os.getenv('STRIPE_CREDITS_100_PRICE_ID', '')  # R$39,90

# Créditos avulsos — preços Pro (com desconto)
STRIPE_CREDITS_20_PRO_PRICE_ID  = os.getenv('STRIPE_CREDITS_20_PRO_PRICE_ID', '')   # R$7,90
STRIPE_CREDITS_50_PRO_PRICE_ID  = os.getenv('STRIPE_CREDITS_50_PRO_PRICE_ID', '')   # R$18,90
STRIPE_CREDITS_100_PRO_PRICE_ID = os.getenv('STRIPE_CREDITS_100_PRO_PRICE_ID', '')  # R$33,90

# URL base do seu site — usada para montar success_url e cancel_url no Checkout
SITE_URL = os.getenv('SITE_URL', 'http://localhost:8000')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'leads.apps.LeadsConfig',
    'accounts.apps.AccountsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'B2BZap.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'B2BZap.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # DB_PATH permite colocar o banco em volume Docker (/data/db.sqlite3)
        # sem sobrescrever o código da aplicação
        'NAME': Path(os.getenv('DB_PATH', str(BASE_DIR / 'db.sqlite3'))),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

CSRF_TRUSTED_ORIGINS = [os.getenv('SITE_URL', 'http://localhost:8000')]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'media')))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'leads:campaign_list'
LOGIN_URL = 'accounts:login'
LOGOUT_REDIRECT_URL = 'landing_page'

# ── Segurança para produção (nginx termina SSL e passa X-Forwarded-Proto) ─────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = False        # nginx faz o redirect HTTP→HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
    },
}
