# Stage 3 Part A — tracker side of auto-close — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The tracker hands job-ai-assist a list of Profesia offers worth checking and applies the consequences when it reports some of them closed.

**Architecture:** One new nullable field (`Vacancy.closed_at`), a small pure helper that reads the Profesia offer id from a URL, a queryset method for "worth checking", and a domain module `tracker/closing.py` holding every rule about what a closure means (like `tracker/ingest.py`). `api/` only validates JSON and calls those; two new token-authenticated endpoints sit next to the ingest one.

**Tech Stack:** Django 5.2, DRF + drf-spectacular, PostgreSQL 17, pytest-django, factory_boy.

**Spec:** `docs/superpowers/specs/2026-10-26-auto-close-design.md` (Part A).

## Global Constraints

- Closed ⇔ reported by job-ai-assist; the tracker never fetches Profesia.
- Applied → No response via `Application.change_status()`, comment `Posting closed on Profesia`, event dated `seen_at` — also when the posting was reposted under a new offer id.
- Any other application status → status untouched; add a `note` event with text `Posting closed on Profesia`, dated `seen_at`.
- No application, state inbox → state dismissed, `dismiss_reason` = `Closed on Profesia`. No application, already dismissed → only `closed_at`.
- `closed_at` already set → `unchanged`, nothing else happens.
- Per-item results: `closed` | `unchanged` | `unknown` | `invalid`; at most 200 items per POST; one transaction per item.
- Worth checking: has `external_id`, `closed_at` empty, and (application status Applied) or (no application, state inbox, score ≥ owner's `inbox_min_score` or null).
- Both endpoints: token auth, the request's user is the owner; other owners' rows are invisible (`unknown`).
- Label copy: `Closed on Profesia (YYYY-MM-DD)`.
- Query budgets stay as pinned: inbox 3, application detail 6, application list 3.
- Commands: tests `py -3.12 -m pytest -q`; migrations `py -3.12 manage.py makemigrations tracker --noinput`.

## Review Focus

1. Profesia URLs come in several shapes (`?search_id=…` tail, trailing slash, no `www`, `http`) and Profesia also has non-offer pages (`/praca/softec/`, `/praca/`). Offer id only from the last path segment matching `O\d+` on `profesia.sk`; anything else → none. Test in Task 2.
2. The same `external_id` twice in one closed report → first `closed`, then `unchanged`, one event only. Test in Task 5.
3. A closed report for an application already Rejected / No response must not add a second status change (anti-goal) — note only. Test in Task 4.
4. A closed vacancy put "Back to inbox" keeps `closed_at` and so is not offered for checking again. Test in Task 4.
5. A malformed `seen_at` or a non-object item gives `invalid` for that item, never a 500; a non-list `closed` gives 400. Test in Task 5.

---

### Task 1: `Vacancy.closed_at` and the "Closed on Profesia" label

**Files:**
- Modify: `tracker/models.py` (Vacancy fields)
- Create: `tracker/migrations/0008_vacancy_closed_at.py` (generated)
- Modify: `tracker/templates/tracker/inbox.html` (card header), `tracker/templates/tracker/application_detail.html` (hgroup line)
- Test: `tests/tracker/test_closed_label.py`

**Interfaces:**
- Produces: `Vacancy.closed_at: DateTimeField(null=True, blank=True)` — "when the tracker learned the posting closed".

- [ ] **Step 1: Write the failing tests** in `tests/tracker/test_closed_label.py` (log in with the existing `client`/`user` fixture style of `tests/tracker/test_inbox_views.py`):
  - `test_inbox_card_shows_closed_date`: a dismissed vacancy (score null) with `closed_at=2026-10-27 08:20 UTC`; GET inbox with `unprocessed=1` → response contains `Closed on Profesia (2026-10-27)`.
  - `test_inbox_card_without_closed_date_has_no_label`: an open inbox vacancy → `Closed on Profesia` not in response.
  - `test_application_page_shows_closed_date`: application whose vacancy has that `closed_at` → its detail page contains `Closed on Profesia (2026-10-27)`.
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/tracker/test_closed_label.py -q` — Expected: FAIL (`closed_at` is an unexpected keyword).
- [ ] **Step 3: Add the field**, run `py -3.12 manage.py makemigrations tracker --noinput -n vacancy_closed_at`, add the label to both templates (`{{ closed_at|date:"Y-m-d" }}`; inbox inside the header `<small>` style, detail on the status line).
- [ ] **Step 4: Run** `py -3.12 -m pytest -q` — Expected: all pass (the pinned query counts unchanged: the field is on the row already loaded).
- [ ] **Step 5: Commit** `feat: vacancies remember when their posting closed`.

### Task 2: Profesia offer id from the URL

**Files:**
- Create: `tracker/profesia.py`
- Modify: `tracker/models.py` (`Vacancy.save`)
- Create: `tracker/migrations/0009_backfill_profesia_external_id.py`
- Test: `tests/tracker/test_profesia.py`

**Interfaces:**
- Produces: `profesia_offer_id(url: str) -> str | None` in `tracker/profesia.py`.
- Produces: `Vacancy.save()` fills `external_id` on a full save (no `update_fields`) when it is None, the URL yields an offer id, and no other vacancy of the owner holds it.
- Produces: `backfill(apps, schema_editor)` in migration 0009, same rule over existing rows.

- [ ] **Step 1: Write the failing tests** in `tests/tracker/test_profesia.py`:
  - `test_offer_id_from_url` parametrized:
    `https://www.profesia.sk/praca/builtmind/O5330945` → `O5330945`;
    `https://www.profesia.sk/praca/builtmind/O5330945?search_id=abc` → `O5330945`;
    `https://www.profesia.sk/praca/builtmind/O5330945/` → `O5330945`;
    `http://profesia.sk/praca/x/O12` → `O12`;
    `https://www.profesia.sk/praca/softec/` → None; `https://www.profesia.sk/praca/` → None;
    `https://example.com/jobs/O5330945` → None; `""` → None; `"not a url"` → None.
  - `test_manual_vacancy_gets_offer_id_from_url`: `VacancyFactory(url=…/O5330945)` → `external_id == "O5330945"`.
  - `test_offer_id_not_taken_twice`: an existing vacancy of the owner with `external_id="O5330945"`; a new manual one with that URL keeps `external_id is None`.
  - `test_other_owner_does_not_block`: the id held by another user's vacancy → filled anyway.
  - `test_existing_external_id_is_kept`: `VacancyFactory(external_id="O1", url=…/O2)` → stays `O1`.
  - `test_non_profesia_url_leaves_none`.
  - `test_backfill_fills_existing_rows`: create two vacancies of one owner, force `external_id=None` and the same Profesia URL via `.update()`, run `backfill(django.apps.apps, None)` (import as in `tests/tracker/test_fingerprints.py`) → exactly one of them gets the id, the other stays None.
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/tracker/test_profesia.py -q` — Expected: FAIL (`tracker.profesia` missing).
- [ ] **Step 3: Implement** `profesia_offer_id` with `urllib.parse.urlsplit` (host `profesia.sk` or `www.profesia.sk`, last non-empty path segment fully matching `O\d+`), the fill in `Vacancy.save()` (only when `update_fields` is None, so status/rename saves stay one query), and migration 0009 (`RunPython(backfill, noop)`, depends on 0008, imports the helper like 0006 imports `fingerprint`; tracks ids it assigned within the run per owner).
- [ ] **Step 4: Run** `py -3.12 -m pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat: hand-entered Profesia vacancies get their offer id from the link`.

### Task 3: `GET /api/v1/vacancies/to-check/`

**Files:**
- Modify: `tracker/managers.py` (`VacancyQuerySet`)
- Modify: `api/serializers.py`, `api/views.py`, `api/urls.py`
- Test: `tests/api/test_to_check_api.py`

**Interfaces:**
- Consumes: `Vacancy.closed_at` (Task 1).
- Produces: `VacancyQuerySet.to_check(owner) -> QuerySet[Vacancy]`, ordered by `external_id`.
- Produces: URL name `api:vacancy-to-check`; response `{"vacancies": [{"external_id": str, "url": str}]}`.

- [ ] **Step 1: Write the failing tests** in `tests/api/test_to_check_api.py` (fixtures as in `tests/api/test_ingest_api.py`; owner's `inbox_min_score` default 40). Each builds the vacancy and asserts whether its `external_id` is in the response list:
  - `test_applied_application_is_listed` (Applied, vacancy score 10 — score does not matter for applications) → in.
  - `test_replied_application_is_not_listed` → out.
  - `test_inbox_vacancy_at_threshold_is_listed` (score 40) → in; `test_unscored_inbox_vacancy_is_listed` → in.
  - `test_inbox_vacancy_below_threshold_is_not_listed` (score 39) → out.
  - `test_dismissed_vacancy_is_not_listed` → out.
  - `test_already_closed_is_not_listed` → out.
  - `test_vacancy_without_external_id_is_not_listed` (non-Profesia URL) → nothing listed.
  - `test_other_owners_vacancy_is_not_listed` → out.
  - `test_response_shape`: exactly `{"vacancies": [{"external_id": "O1", "url": "https://www.profesia.sk/praca/softec/O1"}]}`.
  - `test_requires_token` → 401 without/with a wrong token.
  - `test_to_check_num_queries`: five listed vacancies → `django_assert_num_queries(2)` (token + list).
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/api/test_to_check_api.py -q` — Expected: FAIL (`NoReverseMatch` for `api:vacancy-to-check`).
- [ ] **Step 3: Implement** `to_check(owner)` with `Q` objects over `application__status` / `application__isnull`, a `ToCheckResponseSerializer` (schema only), `VacancyToCheckView(APIView)` with `get()` and `UserRateThrottle`, route `v1/vacancies/to-check/`.
- [ ] **Step 4: Run** `py -3.12 -m pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat: API lists the offers worth checking for closure`.

### Task 4: What a closure means — `tracker/closing.py`

**Files:**
- Create: `tracker/closing.py`
- Test: `tests/tracker/test_closing.py`

**Interfaces:**
- Consumes: `Vacancy.closed_at`, `VacancyQuerySet.to_check` (for the restore test).
- Produces: `report_closed(owner, external_id: str, seen_at: datetime) -> str` returning `"closed" | "unchanged" | "unknown"`; constants `CLOSED_EVENT_TEXT = "Posting closed on Profesia"`, `CLOSED_DISMISS_REASON = "Closed on Profesia"`.

- [ ] **Step 1: Write the failing tests** in `tests/tracker/test_closing.py` (`SEEN = 2026-10-27 08:20 UTC`):
  - `test_applied_becomes_no_response`: result `closed`; application status `no_response`; newest event is `status_change`, `happened_at == SEEN`, text `Applied → No response. Posting closed on Profesia`; vacancy `closed_at == SEEN`.
  - `test_applied_with_repost_still_becomes_no_response`: plus an inbox vacancy with the same company/title and another offer id → still `no_response`.
  - `test_interview_gets_note_only` and `test_rejected_gets_note_only`: status unchanged; exactly one new event, type `note`, text `Posting closed on Profesia`, dated SEEN.
  - `test_inbox_vacancy_is_dismissed`: state `dismissed`, `dismiss_reason == "Closed on Profesia"`.
  - `test_dismissed_vacancy_keeps_its_reason`: dismissed with reason "too far" → reason kept, only `closed_at` set.
  - `test_second_report_is_unchanged`: two calls → `closed`, `unchanged`; one event in total; `closed_at` still the first SEEN.
  - `test_unknown_external_id` and `test_other_owners_offer_is_unknown` → `unknown`, the other owner's row untouched.
  - `test_restored_closed_vacancy_keeps_closed_at`: close an inbox vacancy, POST "Back to inbox" (`tracker:vacancy_restore`) as the owner → state inbox, `closed_at` kept, not in `Vacancy.objects.to_check(owner)`.
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/tracker/test_closing.py -q` — Expected: FAIL (`tracker.closing` missing).
- [ ] **Step 3: Implement** `report_closed`: one `transaction.atomic()`, the vacancy fetched with `select_for_update()` and its application (if any); `change_status(Application.Status.NO_RESPONSE, comment=CLOSED_EVENT_TEXT, when=seen_at)` for Applied; vacancy saved with `update_fields`. Module docstring states the rules, like `tracker/ingest.py`.
- [ ] **Step 4: Run** `py -3.12 -m pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat: a closed posting archives its application or leaves the inbox`.

### Task 5: `POST /api/v1/vacancies/closed/`

**Files:**
- Modify: `api/serializers.py`, `api/views.py`, `api/urls.py`
- Test: `tests/api/test_closed_api.py`

**Interfaces:**
- Consumes: `report_closed` (Task 4); `MAX_BATCH = 200`.
- Produces: URL name `api:vacancy-closed`; body `{"closed": [{"external_id": str, "seen_at": ISO datetime}]}`; response `{"results": [{"external_id": str, "status": "closed"|"unchanged"|"unknown"|"invalid", "errors"?: dict}]}`.

- [ ] **Step 1: Write the failing tests** in `tests/api/test_closed_api.py`:
  - `test_requires_token` → 401.
  - `test_results_per_item`: items for an Applied offer, an unknown id, and a non-object `"oops"` → statuses `["closed", "unknown", "invalid"]`, status 200.
  - `test_same_offer_twice_in_one_report` → `["closed", "unchanged"]`, one closing event.
  - `test_bad_seen_at_is_invalid`: `seen_at="yesterday"` → `invalid` with `"seen_at"` in `errors`, external_id echoed.
  - `test_closed_must_be_a_list`: `{"closed": "x"}` → 400.
  - `test_batch_limit`: 201 items → 400; 200 items → 200.
- [ ] **Step 2: Run** `py -3.12 -m pytest tests/api/test_closed_api.py -q` — Expected: FAIL (`NoReverseMatch`).
- [ ] **Step 3: Implement** `ClosedItemSerializer` (`external_id` CharField max 50, `seen_at` DateTimeField), `ClosedBatchSerializer` (raw JSON items, `max_length=MAX_BATCH`), result/response schema serializers, `VacancyClosedView` with the same per-item shape as `VacancyIngestView._ingest_one`, route `v1/vacancies/closed/`.
- [ ] **Step 4: Run** `py -3.12 -m pytest -q`, then `py -3.12 -m ruff check .`, `py -3.12 -m ruff format --check .`, `py -3.12 -m bandit -r accounts tracker api config -q`, and `py -3.12 manage.py spectacular --validate --file NUL` with dev settings — Expected: all pass / clean.
- [ ] **Step 5: Commit** `feat: API accepts reports of closed postings`.

### Task 6: Architecture docs

**Files:**
- Modify: `docs/architecture.md`, `docs/architecture.ru.md`

- [ ] **Step 1:** Add the two endpoints to the API section, `closed_at` to the model section, and Decisions 25+ (closure rules live in `tracker/closing.py`; Applied → No response even with a repost; offer id from the URL only on full saves, never stealing an id; `closed_at` survives "Back to inbox"). Same content in the `.ru` twin.
- [ ] **Step 2: Run** `py -3.12 -m pytest --cov=accounts --cov=tracker --cov=api --cov-fail-under=85 -q` — Expected: pass.
- [ ] **Step 3: Commit** `docs: Stage 3 Part A in the architecture notes`.
