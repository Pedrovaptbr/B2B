#!/bin/bash

# Aplica as migrações
echo "Applying database migrations..."
python manage.py migrate --noinput

# Coleta os estáticos
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Inicia o servidor
echo "Starting Gunicorn..."
gunicorn B2BZap.wsgi:application --bind 0.0.0.0:8000