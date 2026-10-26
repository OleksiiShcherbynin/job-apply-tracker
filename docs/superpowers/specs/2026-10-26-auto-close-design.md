# Stage 3 — closed Profesia postings close themselves

Date: 2026-10-26
Status: reviewed by a builder check, awaiting the author's approval
Builds on: [Stage 2 design](2026-10-24-stage2-push-api-design.md), [architecture as built](../../architecture.md)

## Why

The author does not chase companies: most applications end in an auto-rejection e-mail or in
silence, and the only sign of silence is that the posting disappears from Profesia. Today he notices
that by chance and moves the application to the archive by hand; closed postings also keep sitting in
the inbox. Profesia marks a closed posting with a fixed notice, and job-ai-assist already visits
Profesia every day — so the tracker can learn about closures without anyone looking.

The original Stage 3 items were reviewed with the author and dropped from this stage: the
"needs attention" morning digest (he does not send follow-ups), a statistics page (he wants a simple,
functional tool, not charts). HTMX and the Slovak UI may come back in Stage 4 or not at all.

## Goals

1. An application still waiting for an answer (status **Applied**) whose Profesia posting has closed
   moves to the archive by itself, with the reason in its timeline.
2. A not-yet-applied inbox vacancy whose posting has closed leaves the inbox by itself.
3. No manual step and no extra cost: no Gemini calls, a light load on Profesia.

## Non-goals

- Statistics, digests, reminders, HTMX, translations.
- Checking postings outside Profesia (company career sites, Workable, …).
- Checking low-score vacancies (below the owner's `inbox_min_score`, ~1000 of them).
- Detecting that a closed posting reopened.

## Anti-goals (a failure even if it "works")

- An open posting marked closed. Only the exact Profesia notice counts; a network error, a non-200
  answer, a captcha or an unexpected page is "don't know", never "closed".
- An application in Replied / Interview / Offer / any closed status changes status because its posting
  closed (the company already answered; the posting closing means nothing).
- A tracker or Profesia problem breaks or delays the daily run or the Telegram report.
- Hundreds of Profesia requests a day.

## How "closed" is recognised (verified 2026-10-26)

Closed postings keep answering `200` at the same URL, with the title and details still shown, plus a
`div.alert.alert-warning` under the title containing:

> "Ľutujeme, spoločnosť ponúkajúca danú pracovnú pozíciu **ukončila zverejnenie ponuky** na stránke."

and **no** "Reagovať na ponuku" (apply) button. Open postings have no such notice and do have the
button. Checked on 9 real offers (6 closed, 3 open): the phrase `ukončila zverejnenie ponuky` matched
exactly the closed ones. The rule: **closed ⇔ HTTP 200 and the page contains that phrase**.

## Division of work

| | job-ai-assist | job-apply-tracker |
|---|---|---|
| Knows which offers matter to the author | no | yes |
| Fetches Profesia pages | yes (already does) | never |
| Decides what a closure means for the author's data | no | yes |

So the tracker hands out a **list of offers worth checking**, job-ai-assist checks them and reports
**which are closed**, and the tracker applies the consequences. The only coupling stays the JSON API
with the same token as Stage 2.

**Coupling stays behind ports (the author's decision).** A Redis message bus was considered and
declined for now: two services owned by one person do not repay an extra container, a background
consumer and a rewrite of the Stage 2 sender; it may return in Stage 4 as a portfolio item. Instead
the existing ports-and-adapters boundary carries the new traffic: in job-ai-assist the
`VacancyTracker` port gains "offers to check" and "report closed", the HTTP details stay in the one
adapter, and `is_closed(html)` is pure core logic; in the tracker everything external stays in `api/`
and the rules in a domain module (like `tracker/ingest.py`).

## Part A — tracker

### A1. Vacancy field

`Vacancy.closed_at` (nullable datetime): when the tracker learned the posting closed. Shown on cards
and the application page as "Closed on Profesia (DATE)".

### A1b. Profesia offer id from the URL

A vacancy typed in by hand with a Profesia posting URL but no `external_id` gets its `external_id`
filled from the URL (`…/O1234567`) on save, when no other vacancy of the owner already has that id;
a one-off data migration does the same for existing rows. Otherwise such applications would never be
checked (and pushes could not recognise them). *Claude's call, from the builder check.*

### A2. `GET /api/v1/vacancies/to-check/`

Token-authenticated like the ingest endpoint. Returns the request owner's offers worth checking:

```json
{"vacancies": [{"external_id": "O5330945", "url": "https://www.profesia.sk/praca/builtmind/O5330945"}]}
```

An offer is worth checking when it has an `external_id`, `closed_at` is empty, and either
- its application has status **Applied**, or
- it has no application, is in state **inbox**, and its score is ≥ the owner's `inbox_min_score`
  or empty.

### A3. `POST /api/v1/vacancies/closed/`

Body `{"closed": [{"external_id": "O5330945", "seen_at": "2026-10-27T08:20:00+00:00"}]}`, at most
200 items. Per-item answer like the ingest endpoint:
`{"results": [{"external_id", "status": "closed" | "unchanged" | "unknown" | "invalid"}]}`.

For each known `external_id` of the owner, in one transaction per item:
- `closed_at` already set → `unchanged`.
- Otherwise set `closed_at = seen_at`, then:
  - application status **Applied** → change status to **No response** through
    `Application.change_status()` with the comment "Posting closed on Profesia" and the event dated
    `seen_at` (so the timeline and status stay in step). This holds **even if the company reposted
    the vacancy under a new offer id** — the author's decision: a closed offer without an answer
    counts as silence; the repost sits in the inbox marked "Already applied" if he wants to try again;
  - application in any other status → status untouched, add a `note` event
    "Posting closed on Profesia";
  - no application and state **inbox** → state **dismissed**, `dismiss_reason` "Closed on Profesia";
  - no application, already dismissed → only `closed_at`.
  Answer `closed`.
- Unknown `external_id` → `unknown`; malformed item → `invalid`.

Repeating the same report is harmless (`unchanged`).

### A4. Where the author sees it

- Applications archive: closed-by-Profesia applications sit there as No response with the timeline
  event — nothing new to build beyond the event text.
- Inbox "Unprocessed": closed vacancies appear as dismissed with reason "Closed on Profesia";
  "Back to inbox" still works (and keeps `closed_at`, so it is not reported again).
- Cards and the application page show "Closed on Profesia (DATE)" when `closed_at` is set.

## Part B — job-ai-assist (its repo, after Part A)

- Once per day, after the run and the tracker push, and only when the tracker settings exist:
  `GET to-check` → for each offer fetch the posting page → collect closed ones → `POST closed`.
- "Once per day" is remembered in the store (like the run marker), so restarts and the 15-minute checks
  do not repeat it. *Claude's calls, from the builder check:*
  - `GET to-check` fails (e.g. the tracker container starts later than job-ai-assist after boot) →
    the day is **not** marked; the next 15-minute check tries again.
  - Once the pages are fetched, the day **is** marked and the closed ones are kept in the store as a
    pending report (the Stage 2 outbox idea again); `POST closed` is retried on later checks from
    that stored list until accepted — Profesia is never walked twice in a day.
  - A page that failed to load is simply checked again tomorrow.
  - The check does not depend on the daily run succeeding; it needs only the tracker settings.
    It also runs under `--once` when not yet done today.
- Only URLs on `www.profesia.sk` are fetched; anything else in the list is skipped. Fetching needs a
  new raw-page method (status + HTML): the existing `fetch_detail` returns cleaned text and raises on
  non-200.
- The page fetch reuses the existing Profesia HTTP client and headers. Pace: about one request every
  2 seconds; the list is expected to hold tens of offers.
- Detection lives in pure code: `is_closed(html) -> bool` true only on the phrase above. A fetch error,
  non-200, or a page without a title (`<h1>`) → skipped for today, not closed.
- No Gemini calls. A failure anywhere logs one WARNING and never affects the run or Telegram.
- Tests with saved, trimmed fixtures of one closed and one open posting (tokens redacted, per the
  repo's rule about raw Profesia HTML) and fake HTTP; no network.

## Testing

- Part A: to-check selection (Applied yes; Replied no; inbox 40+ yes; below threshold no; dismissed
  no; already closed no; no external_id no; other owner no); closed-report effects for each case
  above (including "Applied whose posting was reposted" → still No response), idempotency, unknown /
  invalid items, auth 401, batch limit; external_id filled from a Profesia URL (and not when another
  vacancy already holds it, nor for non-Profesia URLs) plus the data migration; the card /
  application page show the closed date; query counts stay pinned.
- Part B: `is_closed` on the closed and open fixtures and on an error page; once-per-day guard
  (not marked when `GET to-check` fails; marked after fetching; a failed `POST closed` retried from the
  stored list without refetching); non-Profesia URLs skipped; failure isolation; pacing called between
  fetches (without real sleeping in tests).

## Left to the builder

Serializer and view structure; exact field names in payloads beyond those above; how "once per day"
is stored; the exact pause between requests (around 2 s); markup of the "Closed on Profesia" label.

## Order

Part A in the tracker repo first, then Part B in job-ai-assist; one plan, branch and PR per repo.
