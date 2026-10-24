# Stage 2 Part A — tracker side of the job-ai-assist push — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The tracker runs permanently in Docker, accepts batches of scored vacancies over a token-authenticated REST API, and turns them into a clean inbox with "Unprocessed" / "below threshold" toggles, an applications archive and repost-aware repeat applications.

**Architecture:** Ingest logic lives in the domain app (`tracker/ingest.py`), HTTP in a new `api/` app (DRF + authtoken + drf-spectacular). Inbox views are pure queryset composition on `VacancyQuerySet` (annotations, no stored flags). Live data stays in the existing `tracker` database served by a gunicorn container; development moves to a separate `tracker_dev` database.

**Tech Stack:** Django 5.2, PostgreSQL 17, djangorestframework, drf-spectacular, gunicorn, whitenoise, Docker Compose. Python via `py -3.12`.

**Spec:** `docs/superpowers/specs/2026-10-24-stage2-push-api-design.md` (RU twin alongside; EN canonical). As-built context: `docs/architecture.md`.

## Global Constraints

- Python commands: `py -3.12 ...`. New packages: `py -3.12 -m pip install -r requirements/dev.txt`. If an import fails with "DLL load failed … Политика управления приложениями" (Smart App Control), install the previous minor version of that package and pin it with a comment, as done for psycopg.
- Ingest batch limit **200** items; `score` integer **0–100**; `score_stage` ∈ {`rough`, `final`}; missing/empty company → **`Unknown company`**.
- User settings defaults: `inbox_min_score` **40**, `inbox_fresh_days` **5**.
- Closed application statuses: exactly **Rejected, No response, Withdrawn**.
- Fingerprint = `f"{norm(company)}|{norm(title)}"` where `norm` = lowercase, strip accents via NFKD + drop combining chars, collapse whitespace — identical to job-ai-assist `app/store.py::fingerprint`.
- Every write path keeps owner isolation (`OwnerQuerySetMixin` / `request.user`); every state change is POST-only and redirects.
- Query budgets stay pinned: inbox **3**, applications list **3**, vacancy list **3**, dashboard **6**.
- Never run `create_api_token` from Claude's shell (its output is the secret, the audit log records commands and Claude sees output); the user runs it himself.
- After this branch merges, the live container is rebuilt **from `main` only** (`docker compose up -d --build web`); never build the live container from a feature branch that carries new migrations.
- Coverage gate 85%; ruff, bandit clean. Branch `feature/stage2-api`, one PR at the end.
- Work format: before each task the user gets a short simple-language lesson (what and why, interview angle); Claude writes all code.

## Review Focus

1. Company names differing only by case or surrounding spaces ("Softec " vs "softec") reuse one Company — Task 3.
2. The same `external_id` twice in one batch → second item `updated`, no IntegrityError — Task 3.
3. A batch item that is not a JSON object (string, number) → that item `invalid`, the rest processed, no 500 — Task 3.
4. Boundaries: score exactly 40 and age exactly `inbox_fresh_days` count as default inbox — Task 4.
5. A re-push that changes the title recomputes the fingerprint (repost matching follows the current title) — Task 3.

---

### Task 1: Always-on Docker container, live/dev databases split

**Lesson first:** what a Docker image vs container is; gunicorn vs runserver; why live and dev data must not share a database; what WhiteNoise does.

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`, `docker/postgres-init/01-dev-db.sql`, `.env.example`, `tests/test_settings.py`
- Modify: `requirements/base.txt` (+ `gunicorn`, `whitenoise`), `config/settings/base.py` (WhiteNoise middleware right after SecurityMiddleware, `STATIC_ROOT = BASE_DIR / "staticfiles"`), `config/settings/dev.py` (DB `NAME` = `"tracker_dev"`), `config/settings/prod.py`, `docker-compose.yml`, `.github/workflows/ci.yml` (`POSTGRES_DB: tracker_dev`)

**Interfaces (produces):**
- `config.settings.prod` reads env: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (comma list), `POSTGRES_DB/USER/PASSWORD/HOST/PORT`, `DJANGO_MEDIA_ROOT` (default `/data/media`), `DJANGO_HTTPS` (`"1"` default; `"0"` turns off `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS).
- Compose service `web`: build `.`, `env_file: .env`, `DJANGO_SETTINGS_MODULE=config.settings.prod`, `POSTGRES_HOST=db`, `POSTGRES_DB=tracker`, `ports: "127.0.0.1:8000:8000"`, volume `media:/data/media`, `restart: unless-stopped`, `depends_on: db (service_healthy)`, networks `default` and `jobnet` with alias **`job-apply-tracker`**. Top-level `networks: jobnet: name: job-net` (fixed name, not external). `db` gets a `pg_isready` healthcheck and mounts `./docker/postgres-init` to `/docker-entrypoint-initdb.d` (creates `tracker_dev` on a fresh volume).
- Container entrypoint: `python manage.py migrate --noinput` then `gunicorn config.wsgi -b 0.0.0.0:8000 --workers 2`. Image: `python:3.12-slim`, non-root user `app` (uid 10001), `collectstatic` at build with a dummy secret.
- `.env.example`: `DJANGO_SECRET_KEY=change-me`, `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,job-apply-tracker`, `DJANGO_HTTPS=0`, `POSTGRES_USER=tracker`, `POSTGRES_PASSWORD=devpass`.

- [ ] **Step 1: Failing tests** in `tests/test_settings.py`:
  - `test_dev_settings_use_dev_database`: `settings.DATABASES["default"]["NAME"].endswith("tracker_dev")` (the test runner prefixes `test_`).
  - `test_prod_https_flags_follow_env(monkeypatch)`: with required env set and `DJANGO_HTTPS="0"`, `importlib.reload(config.settings.prod)` → `SESSION_COOKIE_SECURE is False` and `SECURE_SSL_REDIRECT is False`; with `"1"` → both `True`.
  - `test_prod_uses_whitenoise`: `"whitenoise.middleware.WhiteNoiseMiddleware"` in reloaded prod `MIDDLEWARE`.
- [ ] **Step 2:** `py -3.12 -m pytest tests/test_settings.py -v` → FAIL.
- [ ] **Step 3:** Implement the files above. Install deps.
- [ ] **Step 4:** `py -3.12 -m pytest -q` → all pass (suite now runs against `test_tracker_dev`).
- [ ] **Step 5: Manual, with the user** (Claude runs only the non-secret commands):
  1. User copies `.env.example` → `.env` and puts a real random `DJANGO_SECRET_KEY` there himself.
  2. `docker compose exec db createdb -U tracker tracker_dev` (existing volume; the init script only runs on fresh ones), then `py -3.12 manage.py migrate` → dev DB ready, live `tracker` untouched.
  3. `docker compose up -d --build web` → http://localhost:8000 shows the user's existing data.
     (Building from the branch is safe only here: at this commit the branch has no new migrations,
     so the entrypoint's `migrate` changes nothing in the live `tracker` database.)
  4. Copy existing uploads once: `docker compose cp media/. web:/data/media/` then `docker compose exec -u root web chown -R app:app /data/media`; an old attachment downloads.
  5. `docker network inspect job-net` shows the `web` container with alias `job-apply-tracker`.
- [ ] **Step 6:** Commit `feat: always-on docker container, separate dev database`.

### Task 2: Vacancy and user model additions

**Lesson first:** migrations that add fields vs data migrations; why a stored, indexed fingerprint beats computing it per query.

**Files:**
- Create: `tracker/fingerprints.py`, `tests/tracker/test_fingerprints.py`
- Modify: `tracker/models.py`, `accounts/models.py`, `accounts/admin.py`, `tracker/admin.py`, migrations (schema + one `RunPython` backfilling `fingerprint` for existing vacancies)

**Interfaces (produces):**
- `tracker.fingerprints.fingerprint(company: str, title: str) -> str` (rule in Global Constraints).
- `Vacancy` new/changed fields: `score_stage = CharField(5, choices ScoreStage: ROUGH="rough", FINAL="final", blank=True)`; `score_reasons` stays (English); new `score_reasons_ru = TextField(blank=True)`; `first_seen_at = DateTimeField(null=True, blank=True)`; `fingerprint = CharField(max_length=500, db_index=True, editable=False)`; widen `url` to `max_length=500`, `salary` to 200, `location` to 200.
- `Vacancy.save()` sets `self.fingerprint = fingerprint(self.company.name, self.title)` before saving.
- `accounts.User`: `inbox_min_score = PositiveSmallIntegerField(default=40, validators=[MaxValueValidator(100)])`, `inbox_fresh_days = PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1)])`; both shown in the admin "Tracker" fieldset next to `follow_up_days`.

- [ ] **Step 1: Failing tests:**
  - `test_fingerprint_normalizes`: `fingerprint("  Softec ", "Junior  PYTHON  Developer") == "softec|junior python developer"`; `fingerprint("Príležitosť s.r.o.", "Študent") == "prilezitost s.r.o.|student"`.
  - `test_vacancy_save_sets_fingerprint` (model test, `VacancyFactory(company__name="ESET", title="Junior Dev")` → `"eset|junior dev"`).
  - `test_user_inbox_defaults`: `UserFactory().inbox_min_score == 40`, `.inbox_fresh_days == 5`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement + `makemigrations` (backfill via `RunPython` iterating vacancies with `select_related("company")`). **Step 4:** `py -3.12 -m pytest -q` → PASS; `makemigrations --check` clean.
- [ ] **Step 5:** Commit `feat: vacancy fingerprint, score stage, bilingual reasons, inbox settings`.

### Task 3: Ingest API

**Lesson first:** REST, JSON, what a serializer is, token auth vs sessions, idempotency, why per-item results.

**Files:**
- Create: `api/__init__.py`, `api/apps.py`, `api/serializers.py`, `api/views.py`, `api/urls.py`, `tracker/ingest.py`, `tracker/management/__init__.py`, `tracker/management/commands/__init__.py`, `tracker/management/commands/create_api_token.py`, `tests/api/__init__.py`, `tests/api/test_ingest_api.py`, `tests/tracker/test_ingest.py`, `tests/tracker/test_create_api_token.py`
- Modify: `requirements/base.txt` (+ `djangorestframework`, `drf-spectacular`), `config/settings/base.py` (`INSTALLED_APPS` + `rest_framework`, `rest_framework.authtoken`, `drf_spectacular`, `api`; `REST_FRAMEWORK` with `DEFAULT_SCHEMA_CLASS` spectacular and `DEFAULT_THROTTLE_RATES = {"user": "60/hour"}`), `config/urls.py` (`path("api/", include("api.urls"))`), `.github/workflows/ci.yml` (`--cov=api`, bandit `-r accounts tracker api config`)

**Interfaces (produces):**
- `tracker.ingest.ingest_vacancy(owner, data: dict) -> tuple[Vacancy, str]` — `data` is a validated item dict; returns `(vacancy, "created" | "updated")`; runs in `transaction.atomic()`. Rules exactly as spec A1 "Ingest rules": lookup by `(owner, external_id)` → update job-ai-assist-owned fields only; else adopt the most recent owner vacancy with `external_id IS NULL` and same fingerprint (fill score / stage / reasons / `first_seen_at`, location & salary only if empty; status `"updated"`); else create with `source=job_ai_assist`, `state=inbox`. Company: `Company.objects.filter(owner=owner, name__iexact=name.strip()).first()` or create; blank → `Unknown company`. `first_seen_at` written on create/adopt only. Reasons lists stored as `"\n".join(...)`; omitted key leaves stored reasons as they are.
- `api.serializers.VacancyItemSerializer` (fields + rules from the spec table); `VacancyBatchSerializer` (`vacancies = ListField(child=JSONField(), max_length=200, allow_empty=True)`).
- `api.views.VacancyIngestView(APIView)`: `authentication_classes=[TokenAuthentication]`, `permission_classes=[IsAuthenticated]`, `throttle_classes=[UserRateThrottle]`, `post()` → 400 on batch errors; else per item: not a dict or invalid → `{"external_id": <given or "">, "status": "invalid", "errors": ...}`; valid → `ingest_vacancy` → `{"external_id", "status", "id"}`. Response `{"results": [...]}`, 200. Annotated with `extend_schema` (request/response serializers) so Swagger shows the contract.
- `api/urls.py`: `v1/vacancies/` (name `api:vacancy-ingest`), `schema/` (`SpectacularAPIView`, name `api:schema`), `schema/swagger-ui/` (`SpectacularSwaggerView`).
- `create_api_token <username> [--rotate]`: prints the key; if a token exists and no `--rotate` → error "token exists, use --rotate".

- [ ] **Step 1: Failing domain tests** (`tests/tracker/test_ingest.py`): `test_creates_inbox_vacancy_with_job_ai_assist_source`; `test_repush_updates_score_and_keeps_state` (dismissed vacancy stays dismissed with its reason; applied stays applied); `test_repush_does_not_move_first_seen_at`; `test_repush_keeps_reasons_when_omitted`; **(RF #5)** `test_repush_title_change_updates_fingerprint`; **(RF #1)** `test_company_reused_ignoring_case_and_spaces` (`" softec "` → existing `Softec`, `Company.objects.count()` unchanged); `test_blank_company_becomes_unknown_company`; `test_adopts_manual_vacancy_with_same_fingerprint` (manual applied vacancy gets `external_id`, keeps state/application/source; no new row); `test_does_not_adopt_vacancy_that_already_has_external_id`; `test_ingest_is_owner_scoped` (same `external_id` for two users → two rows).
- [ ] **Step 2: Failing API tests** (`tests/api/test_ingest_api.py`, `APIClient` + `Token`): `test_requires_token` (401 without / with bad token); `test_created_and_updated_results` (status values, ids, order); `test_invalid_item_does_not_block_others` (bad score 150 → `invalid` with `errors["score"]`, sibling `created`); **(RF #3)** `test_non_object_item_is_invalid`; **(RF #2)** `test_same_external_id_twice_in_batch` (`["created", "updated"]`, one row); `test_more_than_200_items_is_400`; `test_missing_vacancies_key_is_400`; `test_schema_and_swagger_respond` (GET `api:schema` 200). Command tests: `test_create_api_token_prints_key` (capture stdout, `Token.objects.get(user=...).key in out`), `test_existing_token_requires_rotate`.
- [ ] **Step 3:** Run → FAIL. **Step 4:** Implement. **Step 5:** `py -3.12 -m pytest -q` → PASS.
- [ ] **Step 6:** Commit `feat: token-authenticated vacancy ingest API with OpenAPI schema`.

### Task 4: Inbox views and "Back to inbox"

**Lesson first:** composing querysets with `Q`, `Coalesce`, `Exists` subqueries; GET parameters for filters.

**Files:**
- Modify: `tracker/managers.py`, `tracker/views.py` (`InboxView`, `DashboardView`, new `VacancyRestoreView`), `tracker/urls.py`, `tracker/templates/tracker/inbox.html`
- Test: `tests/tracker/test_inbox_views.py`; update `tests/tracker/test_views_dashboard.py` (inbox counter)

**Interfaces (produces):**
- `VacancyQuerySet.for_inbox_view(owner, *, unprocessed: bool = False, below_threshold: bool = False) -> VacancyQuerySet` — owner-scoped, annotated with `age_at = Coalesce("first_seen_at", "created_at")` and `has_newer_repost = Exists(<same owner, same fingerprint, state inbox, age_at greater, different pk>)`, `select_related("company")`, ordered like `inbox()`. Sets (spec A3), with `min = owner.inbox_min_score`, `cutoff = now - timedelta(days=owner.inbox_fresh_days)`, `scored_enough = Q(score__gte=min) | Q(score__isnull=True)`:
  - default: `state=inbox & scored_enough & age_at >= cutoff & ~has_newer_repost`
  - unprocessed: `scored_enough & ((state=inbox & (age_at < cutoff | has_newer_repost)) | state=dismissed)`
  - below_threshold: `score < min & state in (inbox, dismissed)`
  - returns default OR the toggled sets.
- `InboxView` reads `?unprocessed=1` and `?low=1`; context `show_unprocessed`, `show_low`. Template: GET form with two checkboxes; per card "rough" marker when `score_stage == "rough"`; reasons `{% firstof vacancy.score_reasons_ru vacancy.score_reasons %}` with `linebreaksbr`; dismissed cards show reason + "Back to inbox" POST form; `has_newer_repost` cards show "newer repost in inbox".
- `VacancyRestoreView` (POST-only, owner-scoped): `state=inbox`, `dismiss_reason=""`, redirect to `tracker:inbox`. URL `vacancies/<pk>/restore/` name `vacancy_restore`.
- Dashboard `inbox_count = Vacancy.objects.for_inbox_view(user).count()`.

- [ ] **Step 1: Failing tests:** `test_default_shows_fresh_scored_and_manual`; **(RF #4)** `test_boundaries_score_40_and_age_exactly_fresh_days_are_default` (freeze "now" by setting `first_seen_at = timezone.now() - timedelta(days=5) + timedelta(seconds=30)`); `test_old_vacancy_moves_to_unprocessed`; `test_dismissed_40_plus_in_unprocessed_low_in_below_threshold`; `test_only_newest_repost_in_default` (older sibling in unprocessed, `has_newer_repost` True); `test_every_unapplied_vacancy_in_exactly_one_view` (build one of each kind, assert the three sets are disjoint and their union = all non-applied); `test_toggles_via_get_params`; `test_user_threshold_setting_respected` (`inbox_min_score=70`); `test_restore_returns_dismissed_to_inbox` and `test_restore_is_post_only` (405); `test_foreign_vacancy_restore_404`; `test_inbox_num_queries_with_toggles` (all toggles on, 3 queries); dashboard: `test_inbox_count_counts_default_view_only`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** `py -3.12 -m pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: inbox default view with unprocessed and below-threshold toggles`.

### Task 5: Applications archive

**Files:**
- Modify: `tracker/models.py` (`Application.CLOSED_STATUSES = (Status.REJECTED, Status.NO_RESPONSE, Status.WITHDRAWN)`), `tracker/views.py` (`ApplicationListView`), `tracker/templates/tracker/application_list.html`
- Test: `tests/tracker/test_views_application.py`

**Interfaces:** `ApplicationListView` hides `status__in=CLOSED_STATUSES` unless `?archive=1` or an explicit `?status=` is chosen; context `show_archive`; template adds an "Archive" checkbox to the existing GET form.

- [ ] **Step 1: Failing tests:** `test_closed_applications_hidden_by_default` (rejected, no_response, withdrawn hidden; offer and applied shown); `test_archive_toggle_shows_closed`; `test_explicit_status_filter_shows_closed_status`; list query budget test still 3.
- [ ] **Step 2–4:** Run → FAIL, implement, `py -3.12 -m pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: applications archive for closed statuses`.

### Task 6: Reposts and repeat applications

**Lesson first:** self-referencing ForeignKey; `Subquery`/`OuterRef` annotations to show related facts without N+1.

**Files:**
- Modify: `tracker/models.py` (`Application.previous_attempt = ForeignKey("self", null=True, blank=True, on_delete=SET_NULL, related_name="later_attempts")`; `Vacancy.mark_applied(applied_at, notes="", previous_attempt=None)`; `Vacancy.previous_applications() -> ApplicationQuerySet` — same owner + fingerprint, other vacancies, newest `applied_at` first), `tracker/managers.py` (annotations used by `for_inbox_view`), `tracker/forms.py` (`ApplyForm(*args, previous_attempts=None, **kwargs)` adds required `apply_again = BooleanField(label="Yes, apply again")` only when previous attempts exist), `tracker/views.py` (`VacancyApplyView`: passes `previous_attempts`, links new application to the most recent one; `ApplicationPageMixin` adds `select_related("previous_attempt__vacancy")` and `prefetch_related("later_attempts__vacancy")`), templates `inbox.html`, `apply_form.html`, `application_detail.html`, migration
- Test: `tests/tracker/test_reposts.py`; update detail query budget in `tests/tracker/test_views_application.py` to the new pinned number (expected 6)

**Interfaces (produces):**
- `for_inbox_view` rows additionally annotated: `prev_application_pk`, `prev_applied_at`, `prev_status` (latest application of a sibling vacancy, via `Subquery`), `prev_dismiss_reason` (latest dismissed sibling's reason). Inbox cards: "Already applied on {date} — {status}" linking to `prev_application_pk`, or "Dismissed before: {reason}".
- Apply page lists previous attempts (date, status, link) above the form when they exist.
- Application detail shows "Previous attempt: …" and "Later attempt: …" links.

- [ ] **Step 1: Failing tests:** `test_inbox_marks_vacancy_already_applied` (marker text and link); `test_inbox_marks_vacancy_dismissed_before`; `test_apply_requires_confirmation_when_previous_exists` (POST without `apply_again` → 200, no application); `test_apply_again_links_previous_attempt` (with `apply_again=on` → new application, `previous_attempt` = the earlier one); `test_first_apply_needs_no_confirmation`; `test_detail_shows_previous_and_later_links`; `test_markers_ignore_other_owners`; `test_inbox_num_queries` still 3 with markers present; detail budget updated.
- [ ] **Step 2–4:** Run → FAIL, implement, `py -3.12 -m pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: repost markers and confirmed repeat applications`.

### Task 7: Docs, full gate, PR

- [ ] **Step 1:** Update `docs/architecture.md` and `docs/architecture.ru.md`: `api/` app and the ingest contract (link the spec), inbox views, archive, reposts, Docker deployment + "rebuild live only from main", dev DB `tracker_dev`, and Decisions entries for every `Ruling:` this plan's ledger collected.
- [ ] **Step 2:** `py -3.12 -m pytest --cov=accounts --cov=tracker --cov=api --cov-report=term --cov-fail-under=85` → pass; `py -3.12 -m ruff check . && py -3.12 -m ruff format --check .` → clean; `py -3.12 -m bandit -r accounts tracker api config -q` → no findings; `py -3.12 manage.py makemigrations --check --dry-run` → no changes.
- [ ] **Step 3:** Manual API smoke with the user: user creates his token (`py -3.12 manage.py create_api_token <his username>` against the **live** container: `docker compose exec web python manage.py create_api_token <username>` after the merge), opens http://localhost:8000/api/schema/swagger-ui/, posts one sample vacancy via "Authorize" + "Try it out", sees it in the inbox.
- [ ] **Step 4:** Commit docs, push `feature/stage2-api`, user opens PR, CI green, merge, then `docker compose up -d --build web` on `main`. Tag `v0.2.0`.
- [ ] **Step 5:** Update the project dossier: Stage 2 Part A live; next = Part B in job-ai-assist (its own plan there).
