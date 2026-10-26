#!/bin/sh
set -e
# Rebuild the live container only from main: this applies whatever migrations
# the image carries to the live database.
python manage.py migrate --noinput
# gthread, not the default sync worker: browsers talk to gunicorn directly here
# (no nginx in front) and open idle speculative connections. A sync worker
# blocks on such a socket until its 30 s timeout, gets killed, and writes
# "500 Internal Server Error" into it — which the browser then shows on the
# next click.
exec gunicorn config.wsgi --bind 0.0.0.0:8000 \
    --workers 2 --worker-class gthread --threads 4 \
    --access-logfile -
