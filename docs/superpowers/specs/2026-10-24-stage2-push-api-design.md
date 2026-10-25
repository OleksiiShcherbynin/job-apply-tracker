# Stage 2 — job-ai-assist pushes vacancies into the tracker

Date: 2026-10-24
Status: reviewed by a builder check, awaiting the author's approval
Builds on: [MVP design](2026-10-14-job-apply-tracker-design.md), [architecture as built](../../architecture.md)

## Why

Every morning job-ai-assist (the author's scraper + LLM scorer for Profesia.sk) produces scored
vacancies and sends a Telegram report. The author reads the 40+ ones, opens them, decides — and
today has to retype the interesting ones into the tracker by hand. Stage 2 removes the retyping:
job-ai-assist pushes every scored vacancy into the tracker, the inbox shows the ones worth a look,
and the author only decides.

It also adds what daily use already asks for: a clean inbox that doesn't pile up, an archive for
closed applications, and protection against applying twice to the same reposted vacancy.

## Goals

1. job-ai-assist delivers every **scored** vacancy (any score) to the tracker automatically after
   its daily run, without the author doing anything.
2. The inbox shows by default only what deserves attention today; everything else is one toggle away.
3. Closed applications move out of the way into an archive but stay fully visible on demand.
4. Applying again to a reposted vacancy is a conscious decision, visible on both attempts.
5. The tracker runs permanently on the laptop next to job-ai-assist, no `runserver` needed.
6. Portfolio: a real token-authenticated REST API with an OpenAPI schema, idempotent bulk ingest,
   tests.

## Non-goals

- Pulling from job-ai-assist, webhooks, any other vacancy source.
- Editing or deleting tracker data through the API (ingest only).
- Deploying to the internet (Stage 4), background jobs / e-mail digests (Stage 3).
- Per-company rejection statistics (explicitly rejected by the author: one company posts many
  different vacancies, so a company-level "they rejected you" marker would be misleading).

## Anti-goals (would be a failure even if it "works")

- A push overwrites a decision the author made (dismissed / applied vacancy reappears in the inbox,
  state or notes changed).
- The same offer shows up twice in the inbox.
- A tracker outage breaks or delays the morning Telegram report.
- The API token ends up in git, logs, or a shell command line (the machine's audit hook logs every
  command).

## Constraints

- Two separate repos and two separate containers in the same Docker Desktop. The only coupling is
  the JSON contract below. Each repo must still run on its own.
- The tracker keeps its existing PostgreSQL data (the `pgdata` volume of the current compose).
- job-ai-assist is ports & adapters (pure `core/`, adapters in `local_connectors/`, wiring in `app/`);
  its connector must follow that style. The tracker stays layered Django.
- Everything from the MVP stands: owner isolation, POST/redirect/GET, query budgets pinned by tests,
  coverage gate, security CI.
- Work format: Claude writes all code; short lessons before blocks (author's choice).

## Part A — tracker (this repo)

### A1. Ingest API

- New app `api/`. Django REST Framework, `rest_framework.authtoken`, drf-spectacular.
- `POST /api/v1/vacancies/` — authenticated by `Authorization: Token <key>`; everything is created
  for `request.user`. Anonymous or bad token → 401.
- Token per user, created with a management command (`create_api_token <username>`, prints the key
  once) or in the admin. The author puts it into job-ai-assist's `.env` himself.
- Throttling: a per-user rate generous enough for one daily batch plus retries (builder's choice of
  the exact number; job-ai-assist sends a handful of requests a day).
- OpenAPI schema at `/api/schema/` and Swagger UI at `/api/schema/swagger-ui/`; the schema holds no
  data and may be public.

**Request** — a batch, max 200 items:

```json
{
  "vacancies": [
    {
      "external_id": "O5350242",
      "title": "Junior Python Developer",
      "company": "Softec",
      "url": "https://www.profesia.sk/praca/softec/O5350242",
      "location": "Bratislava",
      "salary": "1 800 - 2 200 EUR/month",
      "score": 78,
      "score_stage": "final",
      "reasons_en": ["Python and Django match", "Junior-friendly"],
      "reasons_ru": ["Совпадает стек Python и Django", "Подходит джуниору"],
      "first_seen_at": "2026-10-20T08:14:03+00:00"
    }
  ]
}
```

| Field | Rule |
|---|---|
| `external_id` | required, ≤ 50 chars; Profesia offer id |
| `title` | required, ≤ 255 |
| `company` | optional; missing or empty → company named `Unknown company` |
| `url` | required, valid URL |
| `location`, `salary` | optional text, as shown on Profesia |
| `score` | required, integer 0–100 |
| `score_stage` | required, `rough` or `final` |
| `reasons_en`, `reasons_ru` | optional lists of strings |
| `first_seen_at` | optional ISO 8601 with timezone; when job-ai-assist first saw the offer |

**Response** — `200`, one result per item, in request order:

```json
{"results": [
  {"external_id": "O5350242", "status": "created", "id": 41},
  {"external_id": "O5349001", "status": "updated", "id": 17},
  {"external_id": "", "status": "invalid", "errors": {"external_id": ["This field may not be blank."]}}
]}
```

Items are independent: an invalid item does not block the valid ones (so one bad record can't jam
the sender's retry queue forever). A malformed body (not JSON, no `vacancies` list, more than 200
items) is a `400` for the whole request.

**Ingest rules** (all within the request user's data):

- **New `external_id`, and the owner has a vacancy without `external_id` with the same
  fingerprint** (one the author typed in by hand before Stage 2) → **adopt** it: set its
  `external_id` and fill the job-ai-assist fields (score, stage, reasons, `first_seen_at`, and
  location / salary only where empty). Its state, application, notes, company link and `source`
  stay as they are. One row, no duplicate. If several manual rows match, adopt the most recent.
- **New `external_id`, nothing to adopt** → new `Vacancy` with `source=job_ai_assist`,
  `state=inbox`. Company is looked up by name case-insensitively and created if missing.
- **Known `external_id`** → update only what job-ai-assist owns: title, url, location, salary,
  score, score stage, reasons (reasons only when sent). Never touch `state`, `dismiss_reason`, the
  company link, or the application. No duplicate, no resurrection into the inbox.
- `first_seen_at` is stored once (on create) and never moved by later pushes.
- Each item is saved atomically; the whole batch need not be.

### A2. Vacancy model additions

- `score_stage` (`rough` / `final`, blank for manual vacancies).
- English and Russian score reasons stored separately (existing `score_reasons` becomes the English
  one or is replaced — builder's choice, with a data migration if renamed).
- `first_seen_at` (nullable); the vacancy's **age** = `first_seen_at` if set, else `created_at`.
  This matters for the first push: the backlog of already-seen offers must land as old, not as
  five-day-fresh.
- Text limits wide enough that real Profesia data never becomes `invalid` (builder checks the
  lengths of `url`, `salary`, `location` against what job-ai-assist stores).
- A normalized **fingerprint** of company + title (lowercase, accents stripped, whitespace collapsed
  — the same rule job-ai-assist uses for reposts), stored and indexed, computed on save, for manual
  and pushed vacancies alike.

### A3. Inbox: what shows by default, and two toggles

New per-user settings next to `follow_up_days` (editable in the admin):
`inbox_min_score` (default **40**) and `inbox_fresh_days` (default **5**).

Every not-applied vacancy falls into exactly one view:

- **Default inbox** — state `inbox`, score ≥ `inbox_min_score` **or no score** (manual), age ≤
  `inbox_fresh_days`, and it is the **newest** of its fingerprint among undecided vacancies (when a
  company reposts while the original is still undecided, only the repost shows; the older one moves
  to "Unprocessed" with a "newer repost in inbox" marker). Sorted by score as today.
- **Toggle "Unprocessed"** — score ≥ `inbox_min_score` or no score, and either still `inbox` but
  older than the fresh window (or hidden by a newer repost), or `dismissed` (shown with its reason).
  Manual vacancies age like pushed ones.
- **Toggle "Score below 40"** — score < `inbox_min_score`, state `inbox` or `dismissed`, any age.
- Toggles are GET parameters (bookmarkable) and combinable.
- Cards in every view offer **"I applied"**; dismissed cards also offer **"Back to inbox"**
  (POST-only, clears the dismissal and resets nothing else).
- Each card shows: score with a small "rough" marker for `score_stage=rough`; Russian reasons if
  present, else English.
- The dashboard's inbox counter counts the default inbox only.

### A4. Applications archive

- Statuses **Rejected, No response, Withdrawn** are "closed". The applications list hides closed
  ones by default; toggle **"Archive"** shows them. Nothing is deleted.
- Offer stays visible (it is a result, not something to hide). Needs-attention is unchanged
  (it already ignores closed statuses).

### A5. Reposts and repeat applications

"The same vacancy" = same owner, same fingerprint, different vacancy row (works for pushed and
manual vacancies, so the first push also links to applications the author entered by hand).

- **Inbox card** of a vacancy whose fingerprint matches a vacancy the author **applied to**:
  marker "Already applied on DATE — STATUS" linking to that application. If the match was
  **dismissed** instead: marker "Dismissed before: REASON".
- **"I applied" on such a vacancy** shows a warning with the previous attempt(s) and requires an
  explicit confirmation (e.g. a checkbox "Yes, apply again") before creating the application.
- The new application records its **previous attempt** (link to the earlier application of the same
  fingerprint, most recent one). Both application pages show the link (newer ↔ earlier).
- If the earlier application is still active, both stay active and both are marked as related. If it
  is closed, it already sits in the archive (A4) and the author works with the new one.
- One application per vacancy row stays (OneToOne); the repeat lives on the new vacancy row.

### A6. The tracker runs permanently in Docker

- A `Dockerfile` for the web app (Python 3.12 slim, non-root user, gunicorn, static files served
  by WhiteNoise) and a `web` service in the existing `docker-compose.yml` next to `db`, with
  `restart: unless-stopped`. On start it applies migrations.
- **Live and development data are separated.** The container owns the existing `tracker` database
  (the author's real data stays where it is). Development (`runserver`, `migrate` from a feature
  branch, tests) switches to its own `tracker_dev` database on the same Postgres server, so working
  on a branch never migrates or pollutes the live data.
- Uploaded files of the live app live in a named volume; files already in the host's `media/`
  are copied into it once during setup. Development keeps using `./media`. Media stays private
  (served only through `attachment_download`).
- Production-style settings driven by environment variables, with HTTPS-only flags switchable off
  for this local HTTP setup. Secrets (Django secret key) come from a git-ignored `.env`.
- The browser reaches it at `http://localhost:8000`. job-ai-assist reaches it over a **shared Docker
  network** with a fixed name that **both** compose files declare (not `external`), so whichever
  starts first creates it and job-ai-assist still starts when the tracker has never been brought
  up; the web service's name is the host. *(This replaces the `host.docker.internal`
  idea mentioned in the conversation: a shared network does not depend on how Docker Desktop routes
  to the host.)* The URL is configuration on the job-ai-assist side.
- `runserver` remains for development only.

## Part B — sender in job-ai-assist (its repo, after Part A)

- An adapter in `local_connectors/` that POSTs batches to the tracker; a port in `core/ports.py`
  if that is how the repo models outbound systems.
- Outbox in the existing SQLite store, modeled on the existing `deliveries` table (Telegram):
  every scored vacancy (statuses `scored-rough`, `scored-final`, `repost-of-*`) is queued with its
  current payload; successfully accepted items (`created` / `updated`) are marked delivered;
  `invalid` items are logged and not retried; transport failures leave items queued.
- A re-score (rough → final) re-queues the vacancy so the tracker gets the new score.
- Sending happens after the daily run and on every 15-minute idle check while anything is queued.
  Failure to reach the tracker never fails the run or delays the Telegram report.
- First deployment queues the whole backlog of already scored vacancies once (sent with
  `first_seen_at`, so they land as old).
- Config: tracker URL and token from `.env` (the author edits `.env`; the token is never printed,
  logged, or passed on a command line). Without them the sender is simply off.
- Its compose declares the same fixed-name network (see A6); it must start and run normally
  when the tracker is absent.
- `score_stage` for `repost-of-*` comes from the original's status (`scored-final` → `final`).
- Tests with a fake HTTP endpoint; no network in tests (repo rule).

## Testing

- Part A: API tests — auth (401), create, idempotent re-push, no resurrection of dismissed / applied,
  company reuse ignoring case, `Unknown company`, adoption of a matching manual vacancy (no
  duplicate, decisions kept), per-item invalid results, 400 for malformed body
  and > 200 items, `first_seen_at` kept on update; inbox default / toggles / age / threshold tests;
  every not-applied vacancy lands in exactly one view; only the newest undecided repost in the
  default inbox; "Back to inbox"; archive toggle; repost markers, confirmation required,
  previous-attempt link; query-count tests
  stay fixed for inbox and applications list. Coverage gate unchanged.
- Docker: a manual smoke checklist (container up, login, live data present, dev runs on
  `tracker_dev`, API reachable from another container on the shared network, job-ai-assist starts
  with the tracker down).
- Part B: tests in job-ai-assist's own suite and style.

## Left to the builder

Exact throttle rate; field names inside the tracker models; how the Docker settings module is named
and how HTTPS flags are toggled; serializer / view structure in `api/`; markup of markers and
toggles; whether the confirmation is a checkbox or a second step; how the outbox table is shaped in
job-ai-assist.

## Order

Part A in this repo first (API usable with curl and Swagger before any sender exists), then Part B
in job-ai-assist. Each part gets its own plan, branch and PR.
