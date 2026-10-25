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


@pytest.mark.django_db
def test_company_rename_recomputes_vacancy_fingerprints():
    # Found in final review: a fixed company typo left stale fingerprints,
    # so adoption and repost markers silently stopped matching.
    from tracker.ingest import ingest_vacancy

    vacancy = VacancyFactory(company__name="Sotfec", title="Junior Dev")
    company = vacancy.company
    company.name = "Softec"
    company.save()
    vacancy.refresh_from_db()
    assert vacancy.fingerprint == "softec|junior dev"

    data = {
        "external_id": "O9",
        "title": "Junior Dev",
        "company": "Softec",
        "url": "https://example.com/O9",
        "score": 70,
        "score_stage": "final",
    }
    adopted, status = ingest_vacancy(company.owner, data)
    assert (adopted.pk, status) == (vacancy.pk, "updated")
