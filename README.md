# Job Apply Tracker

[Русская версия](README.ru.md)

**Job Apply Tracker** — my personal job-search tracker in Django, used daily.
My other project, [job-ai-assist](https://github.com/OleksiiShcherbynin/job-ai-assist), scrapes
Profesia.sk and scores every posting with an LLM; the good ones land here automatically. Here I act
on them: apply, dismiss, follow statuses and the timeline of each application. Nothing gets lost:
stale applications surface on the dashboard, and postings that close on Profesia close themselves.

![Dashboard](docs/screenshots/dashboard.png)

| Inbox: scored vacancies, best first | One application and its timeline |
|---|---|
| ![Inbox](docs/screenshots/inbox.png) | ![Application](docs/screenshots/application.png) |
| **All applications, with search and archive** | **The same inbox in Slovak** |
| ![Applications](docs/screenshots/applications.png) | ![Inbox in Slovak](docs/screenshots/inbox-sk.png) |

The screenshots show the demo account; every company and vacancy in it is invented.

## What the code shows

- **Owner isolation** — every row belongs to a user; querysets filter by owner, and other users'
  objects are a 404, never a 403.
- **Custom querysets, fixed query budgets** — "needs attention" and the inbox views are computed with
  annotations and subqueries; tests pin the number of SQL queries per page, so N+1 cannot creep in.
- **A token API for another program** — Django REST Framework with token auth, deny by default,
  OpenAPI schema; batch pushes get a result per item instead of all-or-nothing.
- **Idempotent ingest** — a re-pushed offer updates instead of duplicating; reposts of the same job
  under a new offer id are recognised and linked to the earlier application.
- **Domain rules outside the views** — what a closed posting means (silence → "No response", inbox →
  dismissed) lives in plain Python (`tracker/closing.py`), the API only validates and loops.
- **i18n done properly** — English, Slovak and Russian; the language comes only from the switch;
  texts the code stores stay English in the database and are translated when shown.
- **Tests and CI** — pytest + factory_boy on real PostgreSQL, ~99% coverage with an 85% gate;
  GitHub Actions run ruff, tests, bandit, pip-audit and gitleaks over the full history.
- **Docker** — Postgres + gunicorn (gthread workers) + WhiteNoise, migrations on start, private
  uploads served only to their owner.

The decisions behind all of this, with their reasons: [docs/architecture.md](docs/architecture.md).

## Run it locally

You need Docker.

```bash
cp .env.example .env            # local settings; fine as they are for a try-out
docker compose up -d --build    # Postgres + the app on http://localhost:8000
docker compose exec web python manage.py seed_demo
```

Open http://localhost:8000 and log in as **demo** / **tracker-demo**. The language switch is in the
top right corner.

`seed_demo` can be run again at any time: it rebuilds the demo account's data and touches nothing
else.

## Stack

Python 3.12 · Django 5.2 · Django REST Framework · drf-spectacular · PostgreSQL 17 · Pico.css ·
pytest-django · factory_boy · Docker Compose · GitHub Actions
