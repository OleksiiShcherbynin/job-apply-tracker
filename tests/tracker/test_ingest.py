from datetime import UTC, datetime, timedelta

import pytest

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, CompanyFactory, VacancyFactory
from tracker.ingest import UNKNOWN_COMPANY, ingest_vacancy
from tracker.models import Company, Vacancy

pytestmark = pytest.mark.django_db

SEEN = datetime(2026, 10, 20, 8, 14, tzinfo=UTC)


def item(**overrides):
    data = {
        "external_id": "O5350242",
        "title": "Junior Python Developer",
        "company": "Softec",
        "url": "https://www.profesia.sk/praca/softec/O5350242",
        "location": "Bratislava",
        "salary": "1 800 - 2 200 EUR/month",
        "score": 78,
        "score_stage": "final",
        "reasons_en": ["Python matches", "Junior-friendly"],
        "reasons_ru": ["Совпадает Python", "Подходит джуниору"],
        "first_seen_at": SEEN,
    }
    data.update(overrides)
    return data


def test_creates_inbox_vacancy_with_job_ai_assist_source():
    owner = UserFactory()
    vacancy, status = ingest_vacancy(owner, item())
    assert status == "created"
    assert vacancy.owner == owner
    assert vacancy.source == Vacancy.Source.JOB_AI_ASSIST
    assert vacancy.state == Vacancy.State.INBOX
    assert vacancy.company.name == "Softec"
    assert vacancy.score == 78
    assert vacancy.score_stage == Vacancy.ScoreStage.FINAL
    assert vacancy.score_reasons == "Python matches\nJunior-friendly"
    assert vacancy.score_reasons_ru == "Совпадает Python\nПодходит джуниору"
    assert vacancy.first_seen_at == SEEN


def test_repush_updates_score_and_keeps_state():
    owner = UserFactory()
    dismissed, _ = ingest_vacancy(owner, item(external_id="O1"))
    dismissed.state = Vacancy.State.DISMISSED
    dismissed.dismiss_reason = "Senior only"
    dismissed.save()
    applied, _ = ingest_vacancy(owner, item(external_id="O2"))
    applied.mark_applied(SEEN.date())

    _, status1 = ingest_vacancy(owner, item(external_id="O1", score=55, score_stage="rough"))
    _, status2 = ingest_vacancy(owner, item(external_id="O2", score=91))

    assert (status1, status2) == ("updated", "updated")
    dismissed.refresh_from_db()
    applied.refresh_from_db()
    assert dismissed.score == 55
    assert dismissed.state == Vacancy.State.DISMISSED
    assert dismissed.dismiss_reason == "Senior only"
    assert applied.score == 91
    assert applied.state == Vacancy.State.APPLIED
    assert Vacancy.objects.count() == 2


def test_repush_does_not_move_first_seen_at():
    owner = UserFactory()
    ingest_vacancy(owner, item())
    vacancy, _ = ingest_vacancy(owner, item(first_seen_at=SEEN + timedelta(days=3)))
    assert vacancy.first_seen_at == SEEN


def test_repush_keeps_reasons_when_omitted():
    owner = UserFactory()
    ingest_vacancy(owner, item())
    data = item(score=80)
    del data["reasons_en"], data["reasons_ru"]
    vacancy, _ = ingest_vacancy(owner, data)
    assert vacancy.score_reasons == "Python matches\nJunior-friendly"
    assert vacancy.score_reasons_ru == "Совпадает Python\nПодходит джуниору"


def test_repush_title_change_updates_fingerprint():
    # Review Focus #5: repost matching must follow the current title.
    owner = UserFactory()
    ingest_vacancy(owner, item())
    vacancy, _ = ingest_vacancy(owner, item(title="Junior Data Engineer"))
    assert vacancy.fingerprint == "softec|junior data engineer"


def test_company_reused_ignoring_case_and_spaces():
    # Review Focus #1.
    owner = UserFactory()
    existing = CompanyFactory(owner=owner, name="Softec")
    vacancy, _ = ingest_vacancy(owner, item(company="  softec "))
    assert vacancy.company == existing
    assert Company.objects.filter(owner=owner).count() == 1


@pytest.mark.parametrize("company", ["", "   "])
def test_blank_company_becomes_unknown_company(company):
    owner = UserFactory()
    vacancy, _ = ingest_vacancy(owner, item(company=company))
    assert vacancy.company.name == UNKNOWN_COMPANY == "Unknown company"


def test_missing_company_becomes_unknown_company():
    owner = UserFactory()
    data = item()
    del data["company"]
    vacancy, _ = ingest_vacancy(owner, data)
    assert vacancy.company.name == UNKNOWN_COMPANY


def test_adopts_manual_vacancy_with_same_fingerprint():
    owner = UserFactory()
    application = ApplicationFactory(
        vacancy__company__owner=owner,
        vacancy__company__name="SOFTEC",
        vacancy__title="Junior  python developer",
        vacancy__location="Bratislava – centrum",
        vacancy__state=Vacancy.State.APPLIED,
    )
    manual = application.vacancy

    vacancy, status = ingest_vacancy(owner, item())

    assert status == "updated"
    assert vacancy.pk == manual.pk
    assert Vacancy.objects.filter(owner=owner).count() == 1
    assert vacancy.external_id == "O5350242"
    assert vacancy.score == 78
    assert vacancy.first_seen_at == SEEN
    assert vacancy.state == Vacancy.State.APPLIED
    assert vacancy.source == Vacancy.Source.MANUAL
    assert vacancy.location == "Bratislava – centrum"  # filled only where empty
    assert vacancy.application == application


def test_does_not_adopt_vacancy_that_already_has_external_id():
    owner = UserFactory()
    other = VacancyFactory(
        company__owner=owner,
        company__name="Softec",
        title="Junior Python Developer",
        external_id="O5321098",
    )
    vacancy, status = ingest_vacancy(owner, item())
    assert status == "created"
    assert vacancy.pk != other.pk


def test_ingest_is_owner_scoped():
    first, second = UserFactory(), UserFactory()
    ingest_vacancy(first, item())
    _, status = ingest_vacancy(second, item())
    assert status == "created"
    assert Vacancy.objects.filter(external_id="O5350242").count() == 2
