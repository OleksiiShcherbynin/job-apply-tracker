import factory

from accounts.factories import UserFactory

from .models import Application, ApplicationEvent, Company, Vacancy


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


class ApplicationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Application

    vacancy = factory.SubFactory(VacancyFactory)
    owner = factory.SelfAttribute("vacancy.owner")


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ApplicationEvent

    application = factory.SubFactory(ApplicationFactory)
    type = ApplicationEvent.EventType.NOTE
