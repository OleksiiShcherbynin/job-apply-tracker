import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from tracker.factories import CompanyFactory, VacancyFactory
from tracker.models import Company, Vacancy


@pytest.mark.django_db
def test_company_str():
    company = CompanyFactory(name="ESET")
    assert str(company) == "ESET"


@pytest.mark.django_db
def test_company_unique_per_owner():
    first = CompanyFactory(name="ESET")
    CompanyFactory(name="ESET")  # другой владелец, то же имя — можно
    with pytest.raises(IntegrityError):
        Company.objects.create(owner=first.owner, name="ESET")


@pytest.mark.django_db
def test_vacancy_defaults():
    vacancy = VacancyFactory()
    assert vacancy.state == Vacancy.State.INBOX
    assert vacancy.source == Vacancy.Source.MANUAL
    assert vacancy.owner == vacancy.company.owner


@pytest.mark.django_db
def test_external_id_unique_per_owner_when_set():
    first = VacancyFactory(external_id="O123")
    # Два NULL не конфликтуют: ручных вакансий без external_id сколько угодно.
    VacancyFactory(company=first.company, external_id=None)
    VacancyFactory(company=first.company, external_id=None)
    with pytest.raises(IntegrityError):
        VacancyFactory(company=first.company, external_id="O123")


@pytest.mark.django_db
def test_company_protected():
    vacancy = VacancyFactory()
    with pytest.raises(ProtectedError):
        vacancy.company.delete()
