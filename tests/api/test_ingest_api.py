import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from tracker.models import Vacancy

pytestmark = pytest.mark.django_db

URL = reverse("api:vacancy-ingest")


def payload(external_id="O1", **overrides):
    data = {
        "external_id": external_id,
        "title": "Junior Python Developer",
        "company": "Softec",
        "url": f"https://www.profesia.sk/praca/softec/{external_id}",
        "score": 78,
        "score_stage": "final",
    }
    data.update(overrides)
    return data


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def api(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


def test_requires_token():
    anonymous = APIClient()
    assert anonymous.post(URL, {"vacancies": []}, format="json").status_code == 401
    anonymous.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    assert anonymous.post(URL, {"vacancies": []}, format="json").status_code == 401


def test_created_and_updated_results(api, user):
    api.post(URL, {"vacancies": [payload("O2")]}, format="json")
    response = api.post(URL, {"vacancies": [payload("O1"), payload("O2")]}, format="json")
    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["external_id"] for r in results] == ["O1", "O2"]
    assert [r["status"] for r in results] == ["created", "updated"]
    assert results[0]["id"] == Vacancy.objects.get(owner=user, external_id="O1").pk


def test_invalid_item_does_not_block_others(api, user):
    response = api.post(
        URL, {"vacancies": [payload("O1", score=150), payload("O2")]}, format="json"
    )
    first, second = response.json()["results"]
    assert first["status"] == "invalid"
    assert first["external_id"] == "O1"
    assert "score" in first["errors"]
    assert second["status"] == "created"
    assert not Vacancy.objects.filter(external_id="O1").exists()


def test_non_object_item_is_invalid(api):
    # Review Focus #3: a stray string must not 500 or block the batch.
    response = api.post(URL, {"vacancies": ["oops", 42, payload("O3")]}, format="json")
    assert response.status_code == 200
    statuses = [r["status"] for r in response.json()["results"]]
    assert statuses == ["invalid", "invalid", "created"]


def test_same_external_id_twice_in_batch(api, user):
    # Review Focus #2.
    response = api.post(URL, {"vacancies": [payload("O1"), payload("O1", score=90)]}, format="json")
    assert [r["status"] for r in response.json()["results"]] == ["created", "updated"]
    assert Vacancy.objects.get(owner=user, external_id="O1").score == 90


def test_more_than_200_items_is_400(api):
    items = [payload(f"O{n}") for n in range(201)]
    assert api.post(URL, {"vacancies": items}, format="json").status_code == 400
    assert not Vacancy.objects.exists()


def test_missing_vacancies_key_is_400(api):
    assert api.post(URL, {"jobs": []}, format="json").status_code == 400


def test_body_that_is_a_list_is_400(api):
    assert api.post(URL, [payload()], format="json").status_code == 400


def test_schema_and_swagger_respond(client):
    assert client.get(reverse("api:schema")).status_code == 200
    assert client.get(reverse("api:swagger-ui")).status_code == 200


def test_blank_reason_lines_do_not_reject_the_item(api, user):
    # Found in final review: one empty string from the scorer would make the
    # vacancy "invalid" forever (the sender does not retry invalid items).
    item = payload("O7", reasons_en=["Python matches", ""], reasons_ru=["", "Подходит"])
    response = api.post(URL, {"vacancies": [item]}, format="json")
    assert response.json()["results"][0]["status"] == "created"
    vacancy = Vacancy.objects.get(owner=user, external_id="O7")
    assert vacancy.score_reasons == "Python matches"
    assert vacancy.score_reasons_ru == "Подходит"
