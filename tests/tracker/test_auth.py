import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains

from accounts.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_login_page_renders(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    assertContains(response, "csrfmiddlewaretoken")  # форма защищена CSRF-токеном


def test_login_redirects_to_dashboard(client):
    user = UserFactory()
    response = client.post(reverse("login"), {"username": user.username, "password": "pass"})
    assert response.status_code == 302
    assert response.url == reverse("tracker:dashboard")


def test_logout_requires_post(client):
    client.force_login(UserFactory())
    assert client.get(reverse("logout")).status_code == 405  # GET запрещён
    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert response.url == reverse("login")


def test_dashboard_requires_login(client):
    response = client.get(reverse("tracker:dashboard"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_dashboard_shows_user_and_logout_button(client):
    user = UserFactory(username="alexei")
    client.force_login(user)
    response = client.get(reverse("tracker:dashboard"))
    assertContains(response, "alexei")
    assertContains(response, f'action="{reverse("logout")}"')
