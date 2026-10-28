from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from rest_framework.authtoken.models import Token

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, CompanyFactory, EventFactory, VacancyFactory
from tracker.management.commands.seed_demo import DEMO_PASSWORD, DEMO_USERNAME
from tracker.models import Application, ApplicationEvent, Company, Vacancy

pytestmark = pytest.mark.django_db


def seed():
    out = StringIO()
    call_command("seed_demo", stdout=out)
    return out.getvalue()


def demo_user():
    return get_user_model().objects.get(username=DEMO_USERNAME)


def counts(owner):
    return (
        Company.objects.filter(owner=owner).count(),
        Vacancy.objects.filter(owner=owner).count(),
        Application.objects.filter(owner=owner).count(),
        ApplicationEvent.objects.filter(application__owner=owner).count(),
    )


def test_creates_a_believable_demo_account():
    out = seed()

    demo = demo_user()
    assert (DEMO_USERNAME, DEMO_PASSWORD) == ("demo", "tracker-demo")
    assert demo.check_password(DEMO_PASSWORD)
    assert not demo.is_staff and not demo.is_superuser
    companies, vacancies, _, _ = counts(demo)
    assert companies >= 5
    assert vacancies >= 10
    statuses = set(Application.objects.filter(owner=demo).values_list("status", flat=True))
    assert {"applied", "replied", "interview", "rejected", "no_response"} <= statuses
    mine = Vacancy.objects.filter(owner=demo)
    assert mine.filter(closed_at__isnull=False).exists()
    assert (
        mine.filter(state=Vacancy.State.INBOX)
        .exclude(score_reasons="")
        .exclude(score_reasons_ru="")
    )
    assert mine.filter(state=Vacancy.State.DISMISSED).exists()
    assert DEMO_PASSWORD in out


def test_dashboard_has_something_to_show():
    seed()

    demo = demo_user()
    assert Application.objects.needs_attention(demo).exists()
    assert Vacancy.objects.for_inbox_view(demo).exists()


def test_running_twice_gives_the_same_result():
    seed()
    first = counts(demo_user())

    seed()

    assert counts(demo_user()) == first


def test_other_users_rows_are_untouched():
    seed()
    demo_company_name = Company.objects.filter(owner=demo_user()).first().name
    author = UserFactory(username="a")
    company = CompanyFactory(owner=author, name=demo_company_name)
    VacancyFactory(company=company, title="Author's inbox vacancy")
    application = ApplicationFactory(vacancy__company=company)
    EventFactory(application=application, text="author's note")

    def snapshot():
        return (
            list(Company.objects.filter(owner=author).values()),
            list(Vacancy.objects.filter(owner=author).values()),
            list(Application.objects.filter(owner=author).values()),
            list(ApplicationEvent.objects.filter(application__owner=author).values()),
        )

    before = snapshot()
    seed()

    assert snapshot() == before


@pytest.mark.parametrize("kind", ["staff", "superuser", "token"])
def test_refuses_a_real_demo_account(kind):
    user = UserFactory(
        username=DEMO_USERNAME, is_staff=kind == "staff", is_superuser=kind == "superuser"
    )
    if kind == "token":
        Token.objects.create(user=user)
    company = CompanyFactory(owner=user, name="Real company")

    with pytest.raises(CommandError):
        seed()

    assert list(Company.objects.filter(owner=user)) == [company]
    user.refresh_from_db()
    assert user.check_password("pass")


def test_demo_urls_never_point_to_profesia():
    seed()

    for vacancy in Vacancy.objects.filter(owner=demo_user()):
        assert vacancy.url.startswith("https://example.com/")
        assert vacancy.external_id is None
