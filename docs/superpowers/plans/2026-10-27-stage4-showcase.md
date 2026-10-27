# Stage 4 — Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the tracker a portfolio piece: UI in English/Slovak/Russian, a soft warm look with the
"C" header, a `seed_demo` command, and a README with screenshots; release v1.0.0.

**Architecture:** Django i18n with a cookie-only locale middleware (English unless the user picked a
language). System-written English phrases stay in the database and are translated at display time by
a template filter. A thin `theme.css` over Pico.css carries the look. `seed_demo` rebuilds one
isolated demo user's rows. Translation catalogs (`.po` + compiled `.mo`) are committed; they are
regenerated in a throwaway Docker container because the dev machine has no GNU gettext.

**Tech Stack:** Django 5.2, Pico.css, pytest-django + factory_boy, Docker (`python:3.12-slim` for
gettext).

**Spec:** `docs/superpowers/specs/2026-10-27-stage4-showcase-design.md` (+ `.ru.md`)

## Global Constraints

- Languages: `en` (default), `sk`, `ru`; dropdown labels exactly `EN`, `SK`, `RU`.
- Browser `Accept-Language` is ignored; only the language cookie (set via `set_language`) switches.
- Never translate user-typed data; translate only the fixed system phrases listed in Task 4.
- The database keeps receiving English system texts regardless of the active language.
- No data migration; `python manage.py makemigrations --check --dry-run` must report no changes.
- No new runtime or dev dependency; nothing installed on the Windows host.
- Palette (from the spec): page `#faf7f2`, cards `#fffdfa`, lines `#ece5da`, text `#33302b`, muted
  `#7a7268`, pills `#f2ece3`, current pill `#f5e3cf` / text `#8a5a2b`, main button `#b9824d`,
  score badge `#eef3e6` / text `#4e6b2f`; cards ~14px radius, very light shadow; light theme only.
- Screenshots and repo content contain only demo data, never the author's real rows.
- Coverage gate 85%; existing `django_assert_num_queries` budgets stay as they are.
- Commits: no "written by Oleksii"; end with the Co-Authored-By line from the session reminder.
- Every doc touched gets its `.ru.md` twin updated (architecture, README).

## Review Focus

1. A status change made while the UI is in Russian or Slovak → the stored event text is English
   (otherwise later display-time translation cannot recognise it). Test in Task 4.
2. An event text that merely looks like a system phrase ("Foo → Bar.", a comment containing "→",
   unknown status words) → shown exactly as stored. Test in Task 4.
3. A language cookie with an unsupported or garbage value (`de`, `"><script>`) → English page, no
   error. Test in Task 1.
4. `set_language` with `next` pointing to another host → redirect stays on this site. Test in Task 1.
5. `seed_demo` when the author's own data shares company names with the demo set, or when run
   twice → author's rows unchanged, demo counts identical after the second run. Test in Task 5.

---

### Task 1: Language machinery (cookie-only locale, switch endpoint, catalogs pipeline)

**Files:**
- Create: `config/locale.py`, `docker/i18n.sh`, `locale/sk/LC_MESSAGES/.gitkeep`, `locale/ru/LC_MESSAGES/.gitkeep`
- Modify: `config/settings/base.py`, `config/urls.py`, `templates/base.html` (only `<html lang>`)
- Test: `tests/test_locale.py`

**Interfaces:**
- Produces: setting `LANGUAGES = [("en", "English"), ("sk", "Slovenčina"), ("ru", "Русский")]`,
  `LOCALE_PATHS = [BASE_DIR / "locale"]`; middleware `config.locale.CookieLocaleMiddleware`
  placed right after `SessionMiddleware`; URL `path("i18n/", include("django.conf.urls.i18n"))` →
  name `set_language`; `docker/i18n.sh` regenerates and compiles catalogs.

- [ ] **Step 1: Write the failing tests** in `tests/test_locale.py` (logged-in client on the dashboard):
  - `test_english_by_default_even_if_browser_prefers_slovak`: `HTTP_ACCEPT_LANGUAGE="sk"` → `'<html lang="en"'` in response.
  - `test_cookie_picks_the_language`: cookie `settings.LANGUAGE_COOKIE_NAME="ru"` → `'<html lang="ru"'`.
  - `test_unsupported_cookie_falls_back_to_english` parametrized `["de", '"><script>', ""]` → status 200 and `'<html lang="en"'`.
  - `test_set_language_sets_cookie_and_returns`: POST `reverse("set_language")` `{"language": "sk", "next": "/inbox/"}` → 302 to `/inbox/`, `response.cookies[LANGUAGE_COOKIE_NAME].value == "sk"`.
  - `test_set_language_never_redirects_off_site`: `next="https://evil.example/"` → `Location` does not contain `evil.example`.

- [ ] **Step 2: Run** `py -3.12 -m pytest tests/test_locale.py -q` — Expected: FAIL (no `set_language` URL; `lang="en"` hardcoded so the ru test fails).

- [ ] **Step 3: Implement** `CookieLocaleMiddleware` in `config/locale.py`: read the cookie, accept it only if it is in `dict(settings.LANGUAGES)`, otherwise `settings.LANGUAGE_CODE`; `translation.activate(...)`, set `request.LANGUAGE_CODE`; in `process_response` set `Content-Language` and keep the active language. Do **not** use `LocaleMiddleware` (it reads `Accept-Language`). Settings + URL as in Interfaces. `base.html`: `{% load i18n %}{% get_current_language as LANGUAGE_CODE %}<html lang="{{ LANGUAGE_CODE }}" data-theme="light">`.

- [ ] **Step 4: Write `docker/i18n.sh`** (LF line endings; `.gitattributes` already keeps `*.sh` LF): installs `gettext` with apt, `pip install -r requirements/base.txt`, `DJANGO_SETTINGS_MODULE=config.settings.dev`, then
  `python manage.py makemessages -l sk -l ru --no-obsolete --ignore "tests/*" --ignore "docs/*" --ignore "staticfiles/*" --ignore "media/*" --ignore ".superpowers/*"` and `python manage.py compilemessages`. Header comment: why it runs in a container. Run from the repo root in PowerShell:
  `docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh docker/i18n.sh`
  Expected: `locale/sk/LC_MESSAGES/django.po` and `.mo` (and `ru`) exist (still nearly empty).

- [ ] **Step 5: Run** `py -3.12 -m pytest -q` — Expected: all pass.

- [ ] **Step 6: Commit** `feat: interface language picked by a cookie, English by default` (spec files ride along in this first commit as `docs: Stage 4 spec`, separate commit before it).

### Task 2: Warm theme and the "C" header

**Files:**
- Create: `static/css/theme.css`
- Modify: `templates/base.html`, `templates/registration/login.html`, `tracker/templatetags/tracker_extras.py`
- Test: `tests/tracker/test_layout.py`

**Interfaces:**
- Consumes: `set_language` URL, `LANGUAGES` (Task 1).
- Produces: template tag `{% nav_section request as section %}` in `tracker_extras` returning one of
  `"dashboard" | "inbox" | "applications" | "vacancies" | "companies" | ""` from
  `request.resolver_match.url_name` (`dashboard`→dashboard; `inbox`, `vacancy_apply`,
  `vacancy_dismiss`, `vacancy_restore`→inbox; `application_*`, `attachment_download`→applications;
  other `vacancy_*`→vacancies; `company_*`→companies; anything else → `""`).

- [ ] **Step 1: Failing tests** in `tests/tracker/test_layout.py`:
  - `test_header_has_brand_and_language_dropdown`: dashboard HTML contains `class="brand"` with `Job Apply Tracker`, a `<select name="language"` with options `value="en"`, `value="sk"`, `value="ru"` showing `EN`, `SK`, `RU`, and `selected` on the active one (cookie `ru` → `value="ru" selected`).
  - `test_current_section_is_marked` parametrized: dashboard / inbox / application detail / vacancy list / company list → exactly one `aria-current="page"` and it sits on the matching nav link (assert the link's href precedes it, e.g. via a regex `href="{url}"[^>]*aria-current="page"`).
  - `test_nav_section_mapping` unit test of the tag for every url name listed in Interfaces.
  - `test_theme_css_is_linked`: `css/theme.css` after `css/pico.min.css` in the HTML.
  - `test_login_page_uses_the_theme_without_nav`: anonymous login page has the brand and the language dropdown, no nav links.
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/tracker/test_layout.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.** `base.html` header: row 1 = `<a class="brand" href="dashboard">Job Apply Tracker</a>`, then (right) a small form `method="post" action="{% url 'set_language' %}"` with `csrf_token`, hidden `next` = `request.get_full_path`, `<select name="language" onchange="this.form.submit()">` and a `<noscript>` submit button; then username and the Log out button (logged in only). Row 2 (logged in only) = five nav links as `class="pill"` with `aria-current="page"` on the current one. `theme.css`: override Pico variables for the light theme with the palette from Global Constraints; `.brand` ~1.4rem bold with `line-height: 1.3` and no `overflow: hidden` (descenders must not clip); pills rounded with soft background, current pill highlighted; cards (`article`) radius ~14px, light shadow; buttons radius ~10px, main button colour `#b9824d`; score `mark` as a soft green badge. Body text contrast AA (`#33302b` on `#faf7f2` passes).
- [ ] **Step 4: Run** the layout tests, then `py -3.12 -m pytest -q` — Expected: all pass (existing tests that match on nav text still pass).
- [ ] **Step 5: Check by eye** with `py -3.12 manage.py runserver 8001`: brand bigger than pills, "y" not clipped, pills look like buttons; tell the author what to look at.
- [ ] **Step 6: Commit** `feat: soft warm theme and a two-row header with a language dropdown`.

### Task 3: Translate the interface into Slovak and Russian

**Files:**
- Modify: every template under `templates/` and `tracker/templates/tracker/`, `tracker/models.py` (choice labels only), `tracker/forms.py`, `tracker/views.py`, `locale/{sk,ru}/LC_MESSAGES/django.po` (+ compiled `.mo`)
- Test: `tests/test_translations.py`, `tests/tracker/test_translated_pages.py`

**Interfaces:**
- Consumes: `docker/i18n.sh` (Task 1).
- Produces: lazy labels on `Application.Status`, `ApplicationEvent.EventType`, `Vacancy.State`
  (English text unchanged); Russian status labels Отправлена, Есть ответ, Собеседование, Оффер,
  Отказ, Нет ответа, Отозвана (Task 4's tests use them).

- [ ] **Step 1: Failing tests:**
  - `tests/test_translations.py::test_catalog_is_complete_and_compiled` parametrized `["sk", "ru"]`: a small stdlib parser of `locale/<lang>/LC_MESSAGES/django.po` (msgid/msgstr with `""` continuation lines; header entry skipped) asserts the catalog has entries, no `#, fuzzy`, no `msgid_plural`, no empty `msgstr`, and for every entry `translation.override(lang)` + `gettext(msgid) == msgstr` (proves the committed `.mo` matches the `.po`).
  - `tests/tracker/test_translated_pages.py::test_main_pages_have_no_english_labels` parametrized over `sk`, `ru` × dashboard, inbox, application list, application detail, vacancy form, company list, login. Fixture data uses words that cannot collide (company "Ľubovoľná", vacancy title "Тестовая позиция", username "olga"), so the assertion is simply: the HTML contains none of `["Dashboard", "Inbox", "Applications", "Vacancies", "Companies", "Log out", "Needs attention", "I applied", "Dismiss", "Timeline", "Change status", "Add event", "Attachments", "Log in", "Save"]`.
  - `test_status_labels_are_translated`: under `override("ru")` `str(Application.Status.NO_RESPONSE.label) == "Нет ответа"`.
- [ ] **Step 2: Run** both files — Expected: FAIL.
- [ ] **Step 3: Mark strings:** choice labels → `gettext_lazy` (`_("Applied")`…, identical English so no migration); `{% load i18n %}` + `{% translate %}` / `{% blocktranslate trimmed %}` in all templates (titles, headings, buttons, placeholders, empty-state lines, "posting", "score", "Closed on Profesia (…)", "applied … ago"); `gettext_lazy` for form labels, help texts, `Meta.labels` (do **not** add `verbose_name` to model fields — that would create migrations), validation messages; `gettext` with named placeholders for view messages (`_("Applied: %(vacancy)s.") % {...}`). Avoid plurals.
- [ ] **Step 4: Regenerate catalogs** with the `docker run … sh docker/i18n.sh` command from Task 1, fill every `msgstr` in `sk` and `ru` (short UI wording, Russian status labels from Interfaces), run the container command again to compile.
- [ ] **Step 5: Run** `py -3.12 -m pytest -q` and `py -3.12 manage.py makemigrations --check --dry-run` — Expected: all pass, "No changes detected".
- [ ] **Step 6: Commit** `feat: the interface speaks Slovak and Russian`.

### Task 4: System texts in the user's language

**Files:**
- Modify: `tracker/models.py` (`Vacancy.mark_applied`, `Application.change_status`), `tracker/closing.py` (mark constants with `gettext_noop`), `tracker/templatetags/tracker_extras.py`, templates `dashboard.html`, `application_detail.html`, `inbox.html`, `locale/{sk,ru}/LC_MESSAGES/django.{po,mo}`
- Test: `tests/tracker/test_system_text.py`

**Interfaces:**
- Consumes: `CLOSED_EVENT_TEXT`, `CLOSED_DISMISS_REASON` from `tracker/closing.py`; lazy labels and Russian wording (Task 3).
- Produces: filters `system_text(value: str) -> str` and `reasons(vacancy) -> str` in `tracker_extras`.

- [ ] **Step 1: Failing tests:**
  - `test_status_change_is_stored_in_english` parametrized `["ru", "sk"]`: inside `translation.override(lang)` call `application.change_status(Status.REJECTED, comment="x")` and `vacancy.mark_applied(...)` → stored texts `"Applied → Rejected. x"` and `"→ Applied"` (RED now: lazy labels resolve to the active language).
  - `test_system_text_translates_known_phrases` with `translation.override("ru")`: `"Applied → No response. Posting closed on Profesia"` → `"Отправлена → Нет ответа. Объявление закрыто на Profesia"`; `"→ Applied"` → `"→ Отправлена"`; `"Applied → Rejected."` → `"Отправлена → Отказ."`; `"Closed on Profesia"` → `"Закрыто на Profesia"`; `"Applied → Interview. позвонить в пятницу"` keeps the comment verbatim.
  - `test_system_text_in_english_is_unchanged`: same inputs under `override("en")` → identical output.
  - `test_lookalike_text_is_left_alone` parametrized `["Foo → Bar.", "called them → no answer", "Applied → Applied → Rejected.", "→ Hired"]` under `override("ru")` → returned unchanged.
  - `test_reasons_follow_language`: vacancy with both reason fields → `ru` gives `score_reasons_ru`, `en` and `sk` give `score_reasons`; with only one filled, every language falls back to it; both empty → `""`.
  - `test_timeline_and_inbox_use_the_filters`: application detail in `ru` (cookie) with a stored closed event shows the translated text; inbox card of a vacancy dismissed with `CLOSED_DISMISS_REASON` shows the translated reason (unprocessed view); a vacancy with both reasons shows the English one under `en`.
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/tracker/test_system_text.py -q` — Expected: FAIL (filters missing, Russian text stored).
- [ ] **Step 3: Implement.**
  - `change_status` and `mark_applied` build the event text inside `translation.override("en")`.
  - `system_text`: exact match of `CLOSED_EVENT_TEXT` / `CLOSED_DISMISS_REASON` → `gettext` of it; `"→ <Label>"` and `"<Label> → <Label>." + optional " <comment>"` where both labels are English `Application.Status` labels → translated labels; the comment is translated only when it equals `CLOSED_EVENT_TEXT`; anything else unchanged. Build the English-label → status map under `override("en")`. Mark the two constants with `gettext_noop` so they stay plain English strings but get extracted.
  - `reasons`: `get_language()` starts with `ru` → `score_reasons_ru or score_reasons`, else `score_reasons or score_reasons_ru`.
  - Templates: timeline and recent events use `event.text|system_text` (dashboard: `|system_text|truncatechars:60`); inbox uses `vacancy.dismiss_reason|system_text`, `vacancy.prev_dismiss_reason|system_text`, and `vacancy|reasons` instead of `firstof`.
  - Re-run `docker/i18n.sh`, fill the two new `msgstr` (ru: "Объявление закрыто на Profesia", "Закрыто на Profesia"; sk equivalents), compile.
- [ ] **Step 4: Run** the file, then `py -3.12 -m pytest -q` and `makemigrations --check --dry-run` — Expected: all pass, "No changes detected".
- [ ] **Step 5: Commit** `feat: system-written texts are shown in the user's language`.

### Task 5: `seed_demo` — a demo account with invented data

**Files:**
- Create: `tracker/management/commands/seed_demo.py`
- Test: `tests/tracker/test_seed_demo.py`

**Interfaces:**
- Produces: `python manage.py seed_demo` → user `demo`, password `tracker-demo` (constants
  `DEMO_USERNAME`, `DEMO_PASSWORD` in the module, used by the README); raises `CommandError` when
  the existing `demo` user is staff, superuser, or has an API token.

- [ ] **Step 1: Failing tests** (`call_command("seed_demo")`):
  - `test_creates_a_believable_demo_account`: user `demo` exists, `check_password("tracker-demo")`, not staff; ≥ 5 companies, ≥ 10 vacancies, applications covering at least `applied`, `replied`, `interview`, `rejected`, `no_response`; at least one vacancy with `closed_at`; at least one inbox vacancy with both reason fields; at least one dismissed vacancy.
  - `test_dashboard_has_something_to_show`: `Application.objects.needs_attention(demo)` non-empty and the default inbox view (`for_inbox_view(demo)`) non-empty.
  - `test_running_twice_gives_the_same_result`: counts of companies, vacancies, applications, events for `demo` equal after the second run.
  - `test_other_users_rows_are_untouched`: another user with a company named like a demo company, a vacancy and an application with an event; snapshot of their `values()` before == after.
  - `test_refuses_a_real_demo_account` parametrized: `demo` is staff / superuser / has `Token` → `CommandError`, and its rows unchanged.
  - `test_demo_urls_never_point_to_profesia`: every demo vacancy `url` starts with `https://example.com/`, `external_id` is `None`.
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/tracker/test_seed_demo.py -q` — Expected: FAIL (unknown command).
- [ ] **Step 3: Implement** inside `transaction.atomic()`: guard; get-or-create `demo` (set password, `is_staff=False`); delete demo's `Application` rows first (vacancy FK is PROTECT), then vacancies, then companies; create the data set from a module-level list of plain dicts (fictional Bratislava companies such as "Danubia Data s.r.o.", junior developer / data analyst titles, salaries in the Profesia style, EN + RU reasons, `job_ai_assist` source for scored ones, `example.com` URLs). Dates relative to `timezone.now()`: one `applied` application older than `follow_up_days` (needs attention), one fresh; `closed_at` set on a `no_response` one with the closed event written via `report_closed`-equivalent texts (`change_status(... comment=CLOSED_EVENT_TEXT)`). Print a one-line summary with the login.
- [ ] **Step 4: Run** the file, then the whole suite — Expected: all pass.
- [ ] **Step 5: Commit** `feat: seed_demo builds a demo account with invented data`.

### Task 6: README, screenshots, architecture notes

**Files:**
- Create: `README.md`, `README.ru.md`, `docs/screenshots/*.png`
- Modify: `docs/architecture.md`, `docs/architecture.ru.md`

- [ ] **Step 1:** Run `seed_demo` on the **dev** database (`py -3.12 manage.py seed_demo`, dev settings → `tracker_dev`) and start `runserver 8001`.
- [ ] **Step 2: Screenshots — the author takes them** (no browser automation is installed and none is added): log in as `demo`, window ~1280 px wide, save as PNG into `docs/screenshots/`: `dashboard.png`, `inbox.png`, `application.png` (detail with timeline), `applications.png`, `inbox-sk.png` (Slovak UI). Claude then opens every PNG and checks it shows only demo data before it is committed.
- [ ] **Step 3: README.md** — the spec's pitch verbatim at the top; screenshots; "What the code shows" (≤ 10 bullets drawn from `docs/architecture.md` decisions: owner isolation, custom QuerySets and N+1 budgets, DRF token API with per-item batch results, idempotent ingest and repost handling, auto-close domain rules, i18n with display-time system texts, 99% coverage + security CI, Docker with gthread gunicorn); "Run it locally": copy `.env.example` to `.env`, `docker compose up -d --build`, `docker compose exec web python manage.py seed_demo`, open http://localhost:8000 and log in as `demo` / `tracker-demo`; link to job-ai-assist; licence line only if the repo has one. `README.ru.md` is its Russian twin and the two link to each other.
- [ ] **Step 4: Architecture docs:** version line → v1.0.0; add i18n (cookie-only middleware, catalogs via `docker/i18n.sh`, `.mo` committed), theme, `seed_demo`; Decisions entries for every `Ruling:` in this plan's ledger plus: cookie-only language, display-time translation of system texts (and why not structured events), committed `.mo`, demo in the live DB with a guard.
- [ ] **Step 5: Run** `py -3.12 -m pytest --cov=accounts --cov=tracker --cov=api --cov-fail-under=85 -q`, `py -3.12 -m ruff check .`, `py -3.12 -m ruff format --check .`, `py -3.12 -m bandit -r accounts tracker api config -q` — Expected: all green.
- [ ] **Step 6: Commit** `docs: README with screenshots, architecture for v1.0.0`.

After merge (finishing-a-development-branch): CI green on `main` → `docker compose up -d --build web`,
`docker compose exec web python manage.py seed_demo` on live, check `/` in EN/SK/RU, tag `v1.0.0`.
