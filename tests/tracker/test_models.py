import pytest
from django.db import IntegrityError

from tracker.factories import CompanyFactory
from tracker.models import Company


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
