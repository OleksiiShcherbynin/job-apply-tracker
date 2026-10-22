"""Smoke test: the whole chain Python -> Django -> psycopg -> Postgres works."""

import pytest
from django.db import connection


@pytest.mark.django_db
def test_db_connection():
    connection.ensure_connection()
    assert connection.is_usable()
