import factory

from accounts.factories import UserFactory

from .models import Company


class CompanyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Company

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Company {n}")
