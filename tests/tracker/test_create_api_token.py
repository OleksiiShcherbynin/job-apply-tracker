from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from rest_framework.authtoken.models import Token

from accounts.factories import UserFactory

pytestmark = pytest.mark.django_db


def run(*args):
    out = StringIO()
    call_command("create_api_token", *args, stdout=out)
    return out.getvalue()


def test_create_api_token_prints_key():
    user = UserFactory(username="alexei")
    out = run("alexei")
    assert Token.objects.get(user=user).key in out


def test_existing_token_requires_rotate():
    user = UserFactory(username="alexei")
    first = run("alexei")
    with pytest.raises(CommandError, match="--rotate"):
        run("alexei")
    second = run("alexei", "--rotate")
    assert Token.objects.get(user=user).key in second
    assert second.strip() != first.strip()


def test_unknown_user_is_an_error():
    with pytest.raises(CommandError):
        run("nobody")
