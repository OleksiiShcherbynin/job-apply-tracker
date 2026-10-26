from datetime import UTC, datetime

import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, VacancyFactory
from tracker.models import Application, Vacancy

pytestmark = pytest.mark.django_db

URL = reverse("api:vacancy-to-check")


@pytest.fixture
def user():
    return UserFactory()  # inbox_min_score defaults to 40


@pytest.fixture
def api(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


def offer(owner, external_id="O1", **kwargs):
    return VacancyFactory(
        company__owner=owner,
        external_id=external_id,
        url=f"https://www.profesia.sk/praca/softec/{external_id}",
        **kwargs,
    )


def listed(api):
    return [item["external_id"] for item in api.get(URL).json()["vacancies"]]


def applied(owner, status=Application.Status.APPLIED, **vacancy_kwargs):
    vacancy = offer(owner, state=Vacancy.State.APPLIED, **vacancy_kwargs)
    return ApplicationFactory(vacancy=vacancy, status=status)


def test_applied_application_is_listed(api, user):
    applied(user, score=10)  # score does not matter once he applied
    assert listed(api) == ["O1"]


def test_replied_application_is_not_listed(api, user):
    applied(user, status=Application.Status.REPLIED)
    assert listed(api) == []


def test_inbox_vacancy_at_threshold_is_listed(api, user):
    offer(user, score=40)
    assert listed(api) == ["O1"]


def test_unscored_inbox_vacancy_is_listed(api, user):
    offer(user)
    assert listed(api) == ["O1"]


def test_inbox_vacancy_below_threshold_is_not_listed(api, user):
    offer(user, score=39)
    assert listed(api) == []


def test_dismissed_vacancy_is_not_listed(api, user):
    offer(user, score=90, state=Vacancy.State.DISMISSED)
    assert listed(api) == []


def test_already_closed_is_not_listed(api, user):
    offer(user, score=90, closed_at=datetime(2026, 10, 27, tzinfo=UTC))
    assert listed(api) == []


def test_vacancy_without_external_id_is_not_listed(api, user):
    VacancyFactory(company__owner=user, url="https://jobs.example.com/python", score=90)
    assert listed(api) == []


def test_other_owners_vacancy_is_not_listed(api):
    offer(UserFactory(), score=90)
    assert listed(api) == []


def test_response_shape(api, user):
    offer(user, score=90)
    assert api.get(URL).json() == {
        "vacancies": [{"external_id": "O1", "url": "https://www.profesia.sk/praca/softec/O1"}]
    }


def test_requires_token():
    anonymous = APIClient()
    assert anonymous.get(URL).status_code == 401
    anonymous.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    assert anonymous.get(URL).status_code == 401


def test_to_check_num_queries(api, user, django_assert_num_queries):
    for n in range(5):
        offer(user, external_id=f"O{n}", score=90)
    # Token lookup + the list.
    with django_assert_num_queries(2):
        assert len(api.get(URL).json()["vacancies"]) == 5
