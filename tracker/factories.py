import factory

from accounts.factories import UserFactory

from .models import Company, Vacancy


class CompanyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Company

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Company {n}")


class VacancyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vacancy

    company = factory.SubFactory(CompanyFactory)
    # Owner always matches the company's owner (cross-owner data is a bug).
    owner = factory.SelfAttribute("company.owner")
    title = factory.Sequence(lambda n: f"Vacancy {n}")
