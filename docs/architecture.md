# Architecture

How job-apply-tracker is actually built as of `v0.1.0` (Stage 0 + MVP).
What it should become is in the [design spec](superpowers/specs/2026-10-14-job-apply-tracker-design.md);
this document describes the code that exists. Russian translation: [architecture.ru.md](architecture.ru.md).

## Apps

| App | Owns |
|---|---|
| `config/` | settings (`base` / `dev` / `prod`), root URLs, WSGI/ASGI |
| `accounts/` | custom `User` (adds `follow_up_days`, default 7) |
| `tracker/` | the whole domain: models, querysets, forms, views, templates |

Plain layered Django on purpose — fat models and querysets, thin views. Stage 2 adds an `api/` app (DRF).

## Data model

```mermaid
erDiagram
    User ||--o{ Company : owns
    User ||--o{ Vacancy : owns
    User ||--o{ Application : owns
    Company ||--o{ Vacancy : "PROTECT"
    Vacancy ||--o| Application : "OneToOne, PROTECT"
    Application ||--o{ ApplicationEvent : "timeline"
    Application ||--o{ Attachment : "files"
```

- **Vacancy** lives in `inbox` until the user acts on it: `applied` or `dismissed` (with a reason).
  `external_id` (Profesia offer id) is unique per owner when present — the hook for idempotent pushes in Stage 2.
- **Application** exists only once the user really applied; one per vacancy.
  Status: `applied → replied → interview → offer / rejected / no_response / withdrawn`.
- **ApplicationEvent** is the timeline. A status change always writes a `status_change` event.
- **Attachment** — the file that was actually sent (CV version, cover letter).
- Every model has `created_at` / `updated_at` (`TimeStampedModel`).

## A request, end to end

1. **Middleware** loads the session, sets `request.user`, checks the CSRF token on every POST.
2. **URLs** (`config/urls.py` → `tracker/urls.py`, namespace `tracker`) pick a class-based view.
3. **View** gets data through an owner-filtered queryset, renders a template that extends `templates/base.html`.
4. Every state change is a **POST** and ends in a **redirect** (POST/redirect/GET). Invalid forms re-render
   the same page with errors next to the field.

## Owner isolation

Multi-user from day one, no open registration (accounts are created by admin or `createsuperuser`).

- `OwnerQuerySetMixin` (`tracker/mixins.py`) filters every view's queryset by `owner=request.user`
  and requires login. Detail/update/delete views look objects up *inside* that queryset, so another
  user's pk is simply not found → **404**.
- `OwnedModelForm` receives `owner` from the view (`OwnerFormMixin`) and sets `instance.owner`.
  `owner` is never a form field, so the user cannot pick it — and so Django skips `(owner, …)`
  constraints during form validation. Owner-aware checks therefore live in the form:
  `CompanyForm.clean_name` (case-insensitive duplicate), `VacancyForm` limits the company dropdown
  to the owner's companies (a tampered foreign id fails validation).
- Child rows (`ApplicationEvent`, `Attachment`) inherit ownership through `application`.
- Uploaded files are private: no public `/media/` route; `attachment_download` serves a file only
  to its owner.

## Key flows

- **"I applied"** — `Vacancy.mark_applied()` creates the Application, its first `status_change` event
  and flips the vacancy to `applied` in one transaction; an optional file becomes an Attachment in the
  same transaction. The first event is dated on the entered `applied_at`, so an application entered
  late still ages correctly. A second "I applied" redirects to the existing application.
- **Status change** — `Application.change_status()` updates the status and writes the event in one
  transaction. "Changing" to the current status is a form error.
- **Needs attention** — `ApplicationQuerySet.needs_attention(owner)`: active statuses (`applied`,
  `replied`) whose latest event is older than `owner.follow_up_days`; applications with no events
  fall back to `applied_at`. Computed with `annotate(Max(...))`, nothing stored.

## Query budget

Every list and the dashboard have a fixed number of queries regardless of data size, pinned by
`django_assert_num_queries` tests: `select_related` for the "one" side (vacancy → company),
`prefetch_related` for the "many" side (application → events, attachments).

| Page | Queries |
|---|---|
| companies, inbox, vacancies, applications | 3 |
| application detail | 5 |
| dashboard | 6 |

(Two of them are always the session and the user.)

## Testing and CI

pytest-django + factory_boy, real PostgreSQL in tests, coverage gate 85% (currently ~99%).
GitHub Actions: ruff (lint + format), tests with coverage, bandit, pip-audit, gitleaks over full history.

## Decisions

One entry per decision: context → decision → consequence.

1. **Layered Django, not ports & adapters.** The goal is idiomatic Django; admin, forms and the ORM
   are built around models. → Logic lives in model methods and querysets, views stay thin.
2. **Custom `User` before the first migration.** Swapping the user model later means rewriting FKs
   in every table. → `accounts.User` from commit one, carrying per-user settings.
3. **Computed "needs attention", not a stored `last_activity`.** A denormalized field can drift from
   the timeline. → One `annotate(Max)` query; revisit only if it gets slow.
4. **Model methods, not signals, for multi-step writes.** Signals hide side effects. →
   `mark_applied()` and `change_status()` are the only entry points and run in `transaction.atomic()`.
5. **Owner-aware validation in forms.** Owner is not a form field, so DB constraints on
   `(owner, …)` are not checked by the form and a duplicate would surface as a 500. →
   `OwnedModelForm` + `clean_<field>`; the DB constraint stays as the safety net.
6. **`PROTECT` on company → vacancy → application, with friendly errors.** Deleting a company must not
   silently erase applications and their history. → Delete views catch `ProtectedError` and show a message.
7. **First event dated on `applied_at`.** Otherwise an application entered a few days late looks fresh
   and drops out of needs attention.
8. **One application per vacancy; double "I applied" redirects.** Matches reality, keeps forms simple;
   a re-application months later is a new vacancy.
9. **`status_change` events only through `change_status`.** The event-type dropdown excludes it, and a
   no-op change is rejected, so status and timeline cannot disagree and the follow-up clock is not
   reset by accident.
10. **Private attachments.** CVs are personal data. → No public media route even in DEBUG; files are
    served by an owner-checked view. Stage 4 only has to keep `media/` off the web server's static paths.
11. **Upload checks: extension + 5 MB, not file content.** Each user uploads into their own tracker and
    gets files back only as their owner. Default label = file name, cut to 100 characters.
12. **Ownership of child rows via `application`.** Spec says every model has an owner; events and
    attachments get it through their application — one source of truth.
13. **Application page = one detail view + three small POST-only views** sharing `ApplicationPageMixin`.
    Invalid input re-renders the page with the error next to its field instead of a flash message.
14. **Site-wide templates in `templates/`** (`base.html`, `registration/login.html`); app pages in
    `tracker/templates/tracker/`. Logout is POST-only and redirects to login.
15. **Environment pins.** `psycopg[binary]==3.2.9` (newer Windows wheels are blocked by Smart App Control
    on the dev machine); compose Postgres on host port **5433** (5432 is taken by a local PostgreSQL).
16. **Deferred to later stages:** security headers / HTTPS (Stage 4), pagination (not needed at one
    user's volume), UI for editing notes or deleting events/attachments (admin covers it), cleaning up
    files of deleted attachments.
