import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from accounts.factories import UserFactory
from tracker.factories import CompanyFactory, VacancyFactory
from tracker.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


# --- Список (пишет Алексей) ---


def test_anonymous_redirected_to_login(client):
    response = client.get(reverse("tracker:company_list"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_list_shows_only_own_companies(client, user):
    CompanyFactory(owner=user, name="ESET")
    CompanyFactory(name="Someone Else Inc")  # чужая компания
    response = client.get(reverse("tracker:company_list"))
    assertContains(response, "ESET")
    assertNotContains(response, "Someone Else Inc")


def test_company_list_num_queries(client, user, django_assert_num_queries):
    CompanyFactory.create_batch(5, owner=user)
    # Сессия + пользователь + список компаний. Число не должно расти
    # вместе с количеством компаний.
    with django_assert_num_queries(3):
        client.get(reverse("tracker:company_list"))


# --- Создание, редактирование, удаление (пишет Claude) ---


def test_create_sets_owner(client, user):
    response = client.post(reverse("tracker:company_add"), {"name": "Pantheon"})
    assert response.status_code == 302
    assert Company.objects.get(name="Pantheon").owner == user


def test_create_duplicate_name_shows_error_not_crash(client, user):
    CompanyFactory(owner=user, name="ESET")
    response = client.post(reverse("tracker:company_add"), {"name": "ESET"})
    assert response.status_code == 200  # форма с ошибкой, а не 500
    assert Company.objects.filter(owner=user, name="ESET").count() == 1


def test_edit_own_company(client, user):
    company = CompanyFactory(owner=user, name="Old name")
    response = client.post(reverse("tracker:company_edit", args=[company.pk]), {"name": "New name"})
    assert response.status_code == 302
    company.refresh_from_db()
    assert company.name == "New name"


def test_foreign_company_edit_404(client, user):
    foreign = CompanyFactory()
    response = client.get(reverse("tracker:company_edit", args=[foreign.pk]))
    assert response.status_code == 404


def test_foreign_company_delete_404(client, user):
    foreign = CompanyFactory()
    response = client.post(reverse("tracker:company_delete", args=[foreign.pk]))
    assert response.status_code == 404
    assert Company.objects.filter(pk=foreign.pk).exists()


def test_delete_own_company(client, user):
    company = CompanyFactory(owner=user)
    response = client.post(reverse("tracker:company_delete", args=[company.pk]))
    assert response.status_code == 302
    assert not Company.objects.filter(pk=company.pk).exists()


def test_delete_company_with_vacancies_shows_error(client, user):
    vacancy = VacancyFactory(company__owner=user)
    response = client.post(
        reverse("tracker:company_delete", args=[vacancy.company.pk]), follow=True
    )
    assert Company.objects.filter(pk=vacancy.company.pk).exists()
    assertContains(response, "has vacancies")
