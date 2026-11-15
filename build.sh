#!/usr/bin/env bash
# Script de construcción para Render: se ejecuta en cada despliegue.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py crear_datos_iniciales      # idempotente: crea el 1er Administrador y tarifas de ejemplo si faltan
