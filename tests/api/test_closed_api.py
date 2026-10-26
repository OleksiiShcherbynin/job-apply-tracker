import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, VacancyFactory
from tracker.models import Application, ApplicationEvent, Vacancy

pytestmark = pytest.mark.django_db

URL = reverse("api:vacancy-closed")
SEEN = "2026-10-27T08:20:00+00:00"


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def api(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


def applied(owner, external_id="O1"):
    vacancy = VacancyFactory(
        company__owner=owner, external_id=external_id, state=Vacancy.State.APPLIED
    )
    return ApplicationFactory(vacancy=vacancy)


def item(external_id="O1", seen_at=SEEN):
    return {"external_id": external_id, "seen_at": seen_at}


def statuses(response):
    return [result["status"] for result in response.json()["results"]]


def test_requires_token():
    assert APIClient().post(URL, {"closed": []}, format="json").status_code == 401


def test_results_per_item(api, user):
    application = applied(user)
    response = api.post(URL, {"closed": [item("O1"), item("O404"), "oops"]}, format="json")
    assert response.status_code == 200
    assert statuses(response) == ["closed", "unknown", "invalid"]
    application.refresh_from_db()
    assert application.status == Application.Status.NO_RESPONSE


def test_same_offer_twice_in_one_report(api, user):
    application = applied(user)
    response = api.post(URL, {"closed": [item(), item()]}, format="json")
    assert statuses(response) == ["closed", "unchanged"]
    closing = application.events.filter(type=ApplicationEvent.EventType.STATUS_CHANGE)
    assert closing.count() == 1


def test_bad_seen_at_is_invalid(api, user):
    applied(user)
    (result,) = api.post(URL, {"closed": [item(seen_at="yesterday")]}, format="json").json()[
        "results"
    ]
    assert result["status"] == "invalid"
    assert result["external_id"] == "O1"
    assert "seen_at" in result["errors"]


def test_closed_must_be_a_list(api):
    assert api.post(URL, {"closed": "x"}, format="json").status_code == 400


def test_batch_limit(api):
    too_many = [item(f"O{n}") for n in range(201)]
    assert api.post(URL, {"closed": too_many}, format="json").status_code == 400
    assert api.post(URL, {"closed": too_many[:200]}, format="json").status_code == 200
