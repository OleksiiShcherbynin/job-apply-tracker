import pytest

from accounts.factories import UserFactory
from tracker.factories import VacancyFactory
from tracker.fingerprints import fingerprint


def test_fingerprint_normalizes():
    # Must match job-ai-assist's app/store.py::fingerprint exactly.
    assert fingerprint("  Softec ", "Junior  PYTHON  Developer") == "softec|junior python developer"
    assert fingerprint("Príležitosť s.r.o.", "Študent") == "prilezitost s.r.o.|student"


@pytest.mark.django_db
def test_vacancy_save_sets_fingerprint():
    vacancy = VacancyFactory(company__name="ESET", title="Junior Dev")
    assert vacancy.fingerprint == "eset|junior dev"


@pytest.mark.django_db
def test_user_inbox_defaults():
    user = UserFactory()
    assert user.inbox_min_score == 40
    assert user.inbox_fresh_days == 5


@pytest.mark.django_db
def test_backfill_migration_fills_existing_rows():
    # Rows created before the field existed have fingerprint "" until the
    # data migration runs over the live database.
    import importlib

    from django.apps import apps

    from tracker.models import Vacancy

    migration = importlib.import_module("tracker.migrations.0006_backfill_vacancy_fingerprint")
    backfill = migration.backfill
    vacancy = VacancyFactory(company__name="Softec", title="Junior Python")
    Vacancy.objects.filter(pk=vacancy.pk).update(fingerprint="")
    backfill(apps, None)
    vacancy.refresh_from_db()
    assert vacancy.fingerprint == "softec|junior python"
