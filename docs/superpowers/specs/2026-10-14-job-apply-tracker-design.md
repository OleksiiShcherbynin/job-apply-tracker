# job-apply-tracker — Design Spec

Date: 2026-10-14
Status: approved for planning
Author: Oleksii Shcherbynin (with Claude as mentor/pair)

## Purpose

A Django web application where the author tracks his real job applications.
Dual goal, in this priority order:

1. **Working tool** — used daily from the first MVP release, replacing ad-hoc
   tracking across email, Profesia.sk, and markdown reports.
2. **Portfolio** — demonstrates confident, idiomatic Django for junior-dev
   hiring (the author's portfolio currently has no web project).

The project is also a **learning vehicle**: the author is learning Django as
the project is built (see "Development & learning process").

### Pains this solves (in priority order)

1. **Forgotten follow-ups** — applications go silent and nobody pings the
   company. Solved by a dashboard section "needs attention": active
   applications with no event for ≥ N days (N is a per-user setting,
   default 7), computed by a custom QuerySet manager.
2. **Manual transfer from job-ai-assist** — the author's existing daily
   scraper/scorer ([job-ai-assist](https://github.com/OleksiiShcherbynin))
   produces scored vacancies that are currently copied by hand. Solved by a
   push API: job-ai-assist POSTs finalists to the tracker at the end of its
   daily run; they appear in the tracker's "inbox".
3. **Lost application materials** — which CV version went where, what was
   answered, when the interview happened. Solved by a per-application event
   timeline and file attachments.

### Success criteria

- The author enters all new applications in the tracker (and stops losing
  follow-ups) starting from the end of Stage 1.
- The repo demonstrates: custom User, CBVs + ModelForms, custom QuerySet
  managers, N+1 tests (`assertNumQueries`), configured admin, DRF API with
  token auth + OpenAPI schema, Celery + Redis, HTMX, PostgreSQL, i18n en/sk,
  pytest + factory_boy + coverage gate, security CI, live deploy with a demo
  account.
- Django goes on the resume only once the code is public.

## System boundary

| Concern | job-ai-assist (existing) | job-apply-tracker (this project) |
|---|---|---|
| Scraping Profesia.sk | yes | never |
| Scoring vacancies with LLM | yes | never |
| Delivering daily finalists | pushes via tracker API (new small connector, built later **in the job-ai-assist repo**) | receives via `POST /api/v1/vacancies/` |
| Tracking applications, statuses, events, files | no | yes |
| Manual vacancy entry (applications outside Profesia) | no | yes |

The tracker never reads job-ai-assist's SQLite or reports. The only coupling
is the JSON contract of the push endpoint.

## Users & auth

- **Multi-user data isolation**: every domain row belongs to a user (FK),
  all queries filter by owner. This is the architecturally correct shape and
  an interview talking point.
- **No open registration**: accounts (the author's + a demo account) are
  created via management command / admin. Login/logout use Django's built-in
  auth views with custom templates. No email verification, no password reset
  pages in scope.
- **Custom User** (`accounts.User`, extends `AbstractUser`) from day one,
  before the first migration. Carries per-user settings such as
  `follow_up_days` (default 7).

## Project structure

Three Django apps by domain (canonical layered Django — deliberately NOT
ports & adapters; the goal is idiomatic Django):

```
job-apply-tracker/
├── config/              # settings, root urls, wsgi/asgi
│   └── settings/        # base.py / dev.py / prod.py
├── accounts/            # custom User
├── tracker/             # domain: models, managers, views, forms, templates
├── api/                 # DRF (created in Stage 2)
├── manage.py
└── docker-compose.yml   # PostgreSQL (+ Redis in Stage 3)
```

## Data model

All domain models have `owner = FK(User)` and created/updated timestamps.

- **Company** — `name`, `website`, `notes`. Unique per owner by name.
- **Vacancy** — `company FK`, `title`, `url`, `source`
  (`manual` / `job_ai_assist`), `external_id` (Profesia offer id, used for
  idempotent pushes; nullable, unique per owner when set), `score` +
  `score_reasons` (from job-ai-assist; empty for manual entries), `salary`
  (text, as-is), `location`, `state`: `inbox` → `applied` / `dismissed`
  (dismissal stores a reason — feeds "how much inbox I reject" stats).
- **Application** — `OneToOneField(Vacancy)`. One application per vacancy:
  matches reality, keeps forms simple; a re-application months later is a new
  vacancy (a new push creates it). `status`: `applied` → `replied` →
  `interview` → terminal `offer` / `rejected` / `no_response` / `withdrawn`.
  Fields: `applied_at`, `notes`.
- **ApplicationEvent** — `application FK`, `type` (`status_change`, `note`,
  `call`, `interview`, `email`), `happened_at`, `text`. A status change on
  Application automatically writes a `status_change` event (model method, not
  signals).
- **Attachment** — `application FK`, `FileField`, `label`
  (e.g. "CV v3 EN"), `uploaded_at`. Stored on local media volume;
  file-type/size validation in the form.

**"Needs attention"** is computed, not denormalized: applications in active
statuses (`applied`, `replied`) whose latest event is older than the owner's
`follow_up_days`, via `annotate(Max("events__happened_at"))` in a custom
QuerySet. List views are covered by `assertNumQueries` tests to catch N+1.

## Screens (server-rendered Django templates; no JS build; HTMX in Stage 3)

- **Dashboard** — "needs attention" list, counts per status, recent events.
- **Inbox** — vacancies in `inbox` state sorted by score desc; actions:
  "Applied" (creates Application; asks date / attachments) and "Dismiss"
  (with reason).
- **Applications list** — filter by status/company, search.
- **Application detail** — status (change via form with comment → writes
  event), event timeline, attachments, notes.
- **Companies / vacancies CRUD** — manual entry for applications outside
  Profesia.
- **Admin** — configured `list_display`, filters, search, event inline on
  Application; the author's power-user entrance and a portfolio feature.
- **Auth** — login/logout.

Styling: a classless/light CSS framework (Pico.css or Bootstrap), decided at
implementation time; not a design project.

## API (Stage 2)

- `POST /api/v1/vacancies/` — bulk create/update of vacancies pushed by
  job-ai-assist. Idempotent on (`owner`, `external_id`): re-pushing the same
  offer updates instead of duplicating. Creates Company by name if missing.
- DRF TokenAuth (token per user, issued via management command), throttling,
  drf-spectacular with Swagger UI at `/api/schema/swagger-ui/`.
- The sending connector is a separate task in the job-ai-assist repo, out of
  scope here except for the JSON contract, which will be specified in
  Stage 2.

## Stages

- **Stage 0 — skeleton**: git repo, Django 5.2 LTS, split settings,
  custom User (before first migration), PostgreSQL via docker-compose,
  pytest-django + factory_boy + coverage threshold, GitHub Actions: ruff,
  pytest, coverage gate, bandit, pip-audit, gitleaks (same security bar as
  job-ai-assist). Branch + PR workflow, small commits, TDD from the start.
- **Stage 1 — MVP** (after this the author starts daily use): models +
  migrations + admin → auth → companies/vacancies CRUD → inbox → applications
  + events + attachments → "needs attention" dashboard.
- **Stage 2 — API for job-ai-assist**: DRF endpoint as above; then the
  connector in the job-ai-assist repo (separate project, separate plan).
- **Stage 3 — showcase features**: HTMX (inline status change, add event
  without reload), Celery + Redis (morning digest email of "needs
  attention"), i18n en/sk.
- **Stage 4 — deploy**: live instance + demo account with seeded data
  (management command), README with screenshots, security headers/HTTPS.
  Hosting provider chosen at Stage 4 (candidates: Fly.io, Railway, Hetzner).

Each stage lands through feature branches and PRs with CI green.

## Testing

- pytest-django + factory_boy; coverage threshold enforced in CI (exact
  percentage set in Stage 0, target ≥ 85–90%).
- TDD for domain logic (model methods, managers, forms, views).
- `assertNumQueries` on every list view (dashboard, inbox, applications).
- API tests for idempotency, auth, and validation in Stage 2.

## Development & learning process

The author is learning Django through this project:

- Before each block, the mentor (Claude) explains the concept (what a
  migration is, how CBVs dispatch, what `get_queryset` does, …).
- **Most code is written by Claude with explanations.** For the key concepts
  of each block (first model, custom manager, first CBV, first form, first
  DRF serializer, …) the author writes the code himself after the
  explanation; Claude helps when stuck and reviews.
- Small commits; commit messages state the "why".

## Out of scope (YAGNI)

- Open registration, email verification, password reset.
- Scraping or scoring anything in this project.
- Multiple applications per vacancy.
- Notifications beyond the Stage-3 email digest (no Telegram here;
  job-ai-assist has its own bot).
- Kanban drag-and-drop boards, charts/analytics dashboards (a simple counts
  block is enough for now).
- S3/object storage for media (local volume is fine at this scale).
