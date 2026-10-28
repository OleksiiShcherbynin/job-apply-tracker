from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from tracker.closing import CLOSED_EVENT_TEXT
from tracker.models import Application, ApplicationEvent, Company, Vacancy

DEMO_USERNAME = "demo"
# Shown in the README: the demo account only ever exists on a local machine.
DEMO_PASSWORD = "tracker-demo"  # noqa: S105  # nosec B105

Status = Application.Status

# Invented companies in Bratislava; the names are fictional on purpose.
COMPANIES = [
    "Danubia Data s.r.o.",
    "Dunajská Analytika s.r.o.",
    "Karpaty Cloud s.r.o.",
    "Petržalka Labs s.r.o.",
    "Tatrify a.s.",
    "Modrý Most Software s.r.o.",
]

# Vacancies still waiting for a decision (or dismissed). days = how long ago
# job-ai-assist first saw them; the default inbox shows the last 5 days.
INBOX = [
    {
        "company": "Danubia Data s.r.o.",
        "title": "Junior Python Developer",
        "salary": "1 600 – 2 100 EUR/month",
        "location": "Bratislava (hybrid)",
        "score": 86,
        "reasons": (
            "Python and Django are the core of the stack\nJunior level, mentoring promised",
            "Python и Django — основа стека\nУровень junior, обещают наставника",
        ),
        "days": 1,
    },
    {
        "company": "Dunajská Analytika s.r.o.",
        "title": "Junior Data Analyst",
        "salary": "1 400 – 1 800 EUR/month",
        "location": "Bratislava",
        "score": 78,
        "reasons": (
            "SQL and pandas match the resume\nPower BI is a plus, not required",
            "SQL и pandas совпадают с резюме\nPower BI — плюс, но не обязателен",
        ),
        "days": 2,
    },
    {
        "company": "Karpaty Cloud s.r.o.",
        "title": "Junior Django Developer",
        "salary": "1 700 EUR/month",
        "location": "Bratislava, home office",
        "score": 72,
        "stage": Vacancy.ScoreStage.ROUGH,
        "reasons": (
            "Django REST API work\nRough score: the full text is not judged yet",
            "Работа с Django REST API\nЧерновая оценка: полный текст ещё не оценён",
        ),
        "days": 0,
    },
    {
        "company": "Petržalka Labs s.r.o.",
        "title": "AI Engineer Intern",
        "salary": "9 EUR/hour",
        "location": "Bratislava",
        "score": 64,
        "reasons": (
            "LLM prototypes in Python\nPart-time, fits studies",
            "Прототипы на LLM в Python\nНеполный день, совместимо с учёбой",
        ),
        "days": 3,
    },
    {
        "company": "Modrý Most Software s.r.o.",
        "title": "Junior Backend Developer",
        "salary": "",
        "location": "Bratislava",
        "manual": True,
        "days": 1,
    },
    {
        "company": "Tatrify a.s.",
        "title": "Senior Java Architect",
        "salary": "4 500 EUR/month",
        "location": "Bratislava",
        "score": 18,
        "reasons": (
            "Senior role, 8+ years of Java\nNo Python",
            "Senior-позиция, 8+ лет Java\nPython не нужен",
        ),
        "days": 2,
    },
    {
        "company": "Tatrify a.s.",
        "title": "Junior Data Engineer",
        "salary": "1 900 EUR/month",
        "location": "Žilina",
        "score": 55,
        "reasons": (
            "Airflow and Spark\nOffice in Žilina only",
            "Airflow и Spark\nОфис только в Жилине",
        ),
        "days": 4,
        "dismissed": "Office in Žilina, too far",
    },
]

# Applications: (days ago, status it moved to, comment) after the first
# "→ Applied" event; the last step is the current status.
APPLICATIONS = [
    {
        "company": "Danubia Data s.r.o.",
        "title": "Python Developer (Junior)",
        "salary": "1 800 EUR/month",
        "applied": 12,  # silent for longer than follow_up_days: needs attention
        "steps": [],
    },
    {
        "company": "Karpaty Cloud s.r.o.",
        "title": "Data Analyst Intern",
        "salary": "8 EUR/hour",
        "applied": 2,
        "steps": [],
    },
    {
        "company": "Petržalka Labs s.r.o.",
        "title": "Junior Software Developer",
        "salary": "1 500 – 1 900 EUR/month",
        "applied": 20,
        "steps": [(6, Status.REPLIED, "HR asked for a short call")],
        "events": [(3, ApplicationEvent.EventType.CALL, "15 min with HR, next: tech interview")],
    },
    {
        "company": "Dunajská Analytika s.r.o.",
        "title": "BI Analyst (Junior)",
        "salary": "1 600 EUR/month",
        "applied": 25,
        "steps": [
            (15, Status.REPLIED, "Test task received"),
            (4, Status.INTERVIEW, "Technical interview on site"),
        ],
    },
    {
        "company": "Tatrify a.s.",
        "title": "Junior Developer",
        "salary": "1 700 EUR/month",
        "applied": 30,
        "steps": [(10, Status.REJECTED, "They chose a candidate with more experience")],
    },
    {
        "company": "Modrý Most Software s.r.o.",
        "title": "Data Analyst",
        "salary": "1 500 EUR/month",
        "applied": 35,
        "closed": 3,  # the posting closed on Profesia without an answer
        "steps": [],
    },
]


def _url(title):
    slug = "-".join(title.lower().replace("(", "").replace(")", "").split())
    return f"https://example.com/jobs/{slug}"


class Command(BaseCommand):
    help = "Create (or recreate) the demo account with invented data, for screenshots and demos."

    def handle(self, *args, **options):
        with transaction.atomic():
            demo = self._demo_user()
            self._wipe(demo)
            companies = {
                name: Company.objects.create(
                    owner=demo, name=name, website=_url(name).replace("/jobs/", "/")
                )
                for name in COMPANIES
            }
            now = timezone.now()
            for spec in INBOX:
                self._inbox_vacancy(demo, companies[spec["company"]], spec, now)
            for spec in APPLICATIONS:
                self._application(demo, companies[spec["company"]], spec, now)

        self.stdout.write(
            f"Demo account ready: log in as {DEMO_USERNAME} / {DEMO_PASSWORD} "
            f"({len(INBOX) + len(APPLICATIONS)} vacancies, {len(APPLICATIONS)} applications)."
        )

    def _demo_user(self):
        user = get_user_model().objects.filter(username=DEMO_USERNAME).first()
        if user is None:
            return get_user_model().objects.create_user(DEMO_USERNAME, password=DEMO_PASSWORD)
        # Never take over a real account that happens to be called "demo".
        if user.is_staff or user.is_superuser or Token.objects.filter(user=user).exists():
            raise CommandError(
                f"User {DEMO_USERNAME!r} is staff, a superuser or has an API token: "
                "it looks like a real account, so it is left alone."
            )
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])
        return user

    def _wipe(self, demo):
        # Applications first: a vacancy with an application is protected.
        Application.objects.filter(owner=demo).delete()
        Vacancy.objects.filter(owner=demo).delete()
        Company.objects.filter(owner=demo).delete()

    def _inbox_vacancy(self, demo, company, spec, now):
        en, ru = spec.get("reasons", ("", ""))
        manual = spec.get("manual", False)
        Vacancy.objects.create(
            owner=demo,
            company=company,
            title=spec["title"],
            url=_url(spec["title"]),
            source=Vacancy.Source.MANUAL if manual else Vacancy.Source.JOB_AI_ASSIST,
            score=spec.get("score"),
            score_stage=spec.get("stage", "" if manual else Vacancy.ScoreStage.FINAL),
            score_reasons=en,
            score_reasons_ru=ru,
            salary=spec["salary"],
            location=spec["location"],
            first_seen_at=None if manual else now - timedelta(days=spec["days"]),
            state=Vacancy.State.DISMISSED if "dismissed" in spec else Vacancy.State.INBOX,
            dismiss_reason=spec.get("dismissed", ""),
        )

    def _application(self, demo, company, spec, now):
        vacancy = Vacancy.objects.create(
            owner=demo,
            company=company,
            title=spec["title"],
            url=_url(spec["title"]),
            source=Vacancy.Source.JOB_AI_ASSIST,
            score=70,
            score_stage=Vacancy.ScoreStage.FINAL,
            salary=spec["salary"],
            location="Bratislava",
            first_seen_at=now - timedelta(days=spec["applied"] + 1),
        )
        application = vacancy.mark_applied((now - timedelta(days=spec["applied"])).date())
        for days, status, comment in spec["steps"]:
            application.change_status(status, comment=comment, when=now - timedelta(days=days))
        for days, kind, text in spec.get("events", []):
            ApplicationEvent.objects.create(
                application=application,
                type=kind,
                happened_at=now - timedelta(days=days),
                text=text,
            )
        if "closed" in spec:
            closed_at = now - timedelta(days=spec["closed"])
            vacancy.closed_at = closed_at
            vacancy.save(update_fields=["closed_at", "updated_at"])
            application.change_status(Status.NO_RESPONSE, comment=CLOSED_EVENT_TEXT, when=closed_at)
