#!/bin/sh
# Regenerates the translation catalogs (locale/*/LC_MESSAGES/django.po) and
# compiles them to .mo. makemessages/compilemessages need GNU gettext, which
# the dev machine does not have, so this runs in a throwaway container:
#
#   docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh docker/i18n.sh
#
# Both .po and .mo are committed, so tests and runserver work without gettext.
set -eu

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends gettext > /dev/null
pip install -q --root-user-action=ignore -r requirements/base.txt

# Dev settings need no environment; extraction never touches the database.
export DJANGO_SETTINGS_MODULE=config.settings.dev

python manage.py makemessages -l sk -l ru --no-obsolete \
    --ignore "tests/*" --ignore "docs/*" --ignore "staticfiles/*" \
    --ignore "media/*" --ignore ".superpowers/*"
python manage.py compilemessages --ignore "staticfiles/*"
