import importlib

import pytest
from django.apps import apps

from accounts.factories import UserFactory
from tracker.factories import VacancyFactory
from tracker.models import Vacancy
from tracker.profesia import profesia_offer_id

OFFER_URL = "https://www.profesia.sk/praca/builtmind/O5330945"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (OFFER_URL, "O5330945"),
        (OFFER_URL + "?search_id=abc", "O5330945"),
        (OFFER_URL + "/", "O5330945"),
        ("http://profesia.sk/praca/x/O12", "O12"),
        ("https://www.profesia.sk/praca/softec/", None),
        ("https://www.profesia.sk/praca/", None),
        ("https://example.com/jobs/O5330945", None),
        ("", None),
        ("not a url", None),
    ],
)
def test_offer_id_from_url(url, expected):
    assert profesia_offer_id(url) == expected


@pytest.mark.django_db
def test_manual_vacancy_gets_offer_id_from_url():
    assert VacancyFactory(url=OFFER_URL).external_id == "O5330945"


@pytest.mark.django_db
def test_offer_id_not_taken_twice():
    held = VacancyFactory(external_id="O5330945")
    newer = VacancyFactory(company__owner=held.owner, url=OFFER_URL)
    assert newer.external_id is None


@pytest.mark.django_db
def test_other_owner_does_not_block():
    VacancyFactory(external_id="O5330945")
    assert VacancyFactory(company__owner=UserFactory(), url=OFFER_URL).external_id == "O5330945"


@pytest.mark.django_db
def test_existing_external_id_is_kept():
    vacancy = VacancyFactory(external_id="O1", url="https://www.profesia.sk/praca/x/O2")
    assert vacancy.external_id == "O1"


@pytest.mark.django_db
def test_non_profesia_url_leaves_none():
    assert VacancyFactory(url="https://jobs.example.com/O5330945").external_id is None


@pytest.mark.django_db
def test_backfill_fills_existing_rows():
    # Rows saved before this rule existed: the data migration fills them once.
    migration = importlib.import_module("tracker.migrations.0009_backfill_profesia_external_id")
    first = VacancyFactory()
    second = VacancyFactory(company__owner=first.owner)
    Vacancy.objects.filter(pk__in=[first.pk, second.pk]).update(url=OFFER_URL, external_id=None)
    migration.backfill(apps, None)
    filled = Vacancy.objects.filter(pk__in=[first.pk, second.pk]).values_list(
        "external_id", flat=True
    )
    # Exactly one of the two gets the id; the unique constraint forbids both.
    assert sorted(filled, key=lambda value: value is None) == ["O5330945", None]
