#!/bin/sh
set -e
# Rebuild the live container only from main: this applies whatever migrations
# the image carries to the live database.
python manage.py migrate --noinput
exec gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 2 --access-logfile -
