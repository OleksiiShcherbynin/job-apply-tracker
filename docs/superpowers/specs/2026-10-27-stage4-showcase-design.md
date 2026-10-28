# Stage 4 — Showcase: demo data, Slovak and Russian UI, soft look, README

Status: approved by the author (2026-10-27)

## Why

The tracker is finished as a tool: the author uses it daily, job-ai-assist feeds it, closed postings
close themselves (v0.3.0). Stage 4 turns it into a portfolio piece the author can put on his resume
and LinkedIn, and show from his laptop at an interview without exposing his real applications.

Who looks at it, in the author's words and as agreed in brainstorming:
- most people read the GitHub README for half a minute and look at the screenshots; the README is
  the main showcase;
- at an interview the author may be asked to show it live from his laptop; real data must not be
  on screen, so a demo account with invented data is needed;
- a curious developer may want to run it locally.

## Decisions taken by the author

- **No live deployment.** The author will not spend money; free hosting was considered and declined
  ("и так норм будет"). The original spec's "live instance" and "hosting provider" items are
  dropped. HTTPS and security headers already live in `config/settings/prod.py` (`DJANGO_HTTPS`
  switch, HSTS, secure cookies, proxy header); nothing more is needed without a public site.
- **Two more UI languages: Slovak and Russian**, English stays the default. Russian is for the
  author's daily use; Slovak is for local employers (he is job-hunting in Bratislava) and shows
  Django i18n. The author accepted that he cannot proofread Slovak himself.
- **Demo data that looks like his real search**: invented companies in Bratislava with obviously
  fictional names (e.g. "Danubia Data s.r.o."), junior developer / data analyst vacancies with scores
  and reasons, applications in different statuses with timelines, one vacancy "closed on Profesia".
- **README pitch**, starting from the problem, not from job-ai-assist:
  > **Job Apply Tracker** — my personal job-search tracker in Django, used daily.
  > My other project, job-ai-assist, scrapes Profesia.sk and scores every posting with an LLM; the
  > good ones land here automatically. Here I act on them: apply, dismiss, follow statuses and the
  > timeline of each application. Nothing gets lost: stale applications surface on the dashboard,
  > and postings that close on Profesia close themselves.

  Then screenshots, then a short "what the code shows" list for technical readers, then how to run.

## Goals

1. **Demo data command.** `python manage.py seed_demo` creates (or recreates) a `demo` user with a
   known password and a believable data set. It touches only the demo user's rows: running it on
   the author's live database must never change or delete his data. Re-running gives the same
   result (wipe the demo user's rows, then create). Dates are relative to the day it runs, so the
   "needs attention" dashboard always has something in it.
   **Where it lives** (Claude's call): in the author's live database next to his own account, so at
   an interview he logs out and logs in as `demo`. Guard: the command refuses to run if a `demo`
   user exists that does not look like the demo account (it is staff or superuser, or has an API
   token); a test pins that another user's rows survive a run unchanged.
2. **UI in English, Slovak and Russian.** Every user-visible string in templates, forms, messages
   and model choice labels is translatable. A language switch in the header; the choice is
   remembered (Django's `set_language` + `LocaleMiddleware`, cookie; the switch itself is
   described in goal 3). Score reasons follow the
   language: Russian UI shows `score_reasons_ru` first, English and Slovak show `score_reasons`
   first, each falling back to the other when empty. (Today the inbox always prefers Russian.)
   Data typed by the user (company names, notes, dismiss reasons, event texts) is never translated.
   The API and the admin stay as they are (the admin gets Django's own translations for free).
   - **System-written texts are translated at display time** (the author's choice, 2026-10-27).
     The code itself stores a few fixed English phrases: status-change events
     `"<Old> → <New>. <comment>"` and `"→ Applied"` (`tracker/models.py`), `CLOSED_EVENT_TEXT`
     ("Posting closed on Profesia") and `CLOSED_DISMISS_REASON` ("Closed on Profesia")
     (`tracker/closing.py`). When an event text or dismiss reason is shown, these known phrases
     and status labels are rendered in the current language; any other text, including the
     author's comment after the status change, is shown as stored. The database keeps writing
     English, no data migration, live rows untouched. Storing structured events instead was
     considered and rejected: it needs a migration of the author's live data for little gain.
   - **Default language** (Claude's call): English until the user picks another one with the
     switch; the browser's `Accept-Language` is ignored, so screenshots and an interviewer with a
     Slovak browser both see English first.
3. **Soft, light, minimal look** (the author's words: "мягкий и приятный для глаза, минималистичный
   и светлый"; chosen from mockups on 2026-10-27). Pico.css stays as the base; the look is a thin
   theme on top of it.
   - **Header, layout "C":** first row — the project name on the left, then on the right the
     language dropdown, the username and a "Log out" button; second row — the five sections
     (Dashboard, Inbox, Applications, Vacancies, Companies).
   - **Name:** stays "Job Apply Tracker", clearly bigger than the navigation (~1.4rem, bold); the
     line height must not clip descenders (the "y").
   - **Sections look like buttons:** rounded "pills" with a soft background; the current section
     is highlighted.
   - **Language dropdown** with EN (default), SK, RU — choosing one switches the UI at once.
   - **Warm sand palette** (mockup values; the builder may tune them, keeping the warmth):
     page `#faf7f2`, cards `#fffdfa`, lines `#ece5da`, text `#33302b`, muted `#7a7268`,
     pills `#f2ece3`, current pill `#f5e3cf` with text `#8a5a2b`, main button `#b9824d`,
     score badge `#eef3e6` with text `#4e6b2f`. Rounded cards (~14px), very light shadow.
     Text and button contrast must stay readable (WCAG AA for body text).
   - The restyle covers every page that extends `base.html` and the login page.
4. **README** (EN canonical + `README.ru.md` twin) with the pitch above, 4–6 screenshots taken from
   the demo account (never from real data), a "what the code shows" list, and a local quick start:
   copy `.env.example`, `docker compose up -d --build`, `seed_demo`, log in as demo.
5. **Release v1.0.0** after merge — the project is complete.

## Non-goals

- Public deployment, hosting, domain, demo login on the internet.
- HTMX, Celery/Redis, digest emails, statistics page (dropped in Stage 3 and stay dropped).
- Translating the API, error responses or data from job-ai-assist (except the existing RU reasons).
- Changing how the author's live container runs.

## Anti-goals (would be a failure even if it technically works)

- Any real company, vacancy or application of the author's in a screenshot or in the repo.
- `seed_demo` touching another user's data.
- A Slovak or Russian page that mixes in untranslated English labels on the main screens
  (dashboard, inbox, applications, application detail, forms).
- Translation infrastructure the author cannot run on his Windows machine without extra installs.

## Constraints

- Same work format as Stages 2–3: plan EN + `.ru.md`, TDD, feature branch, PR, CI green, final review
  on a fable subagent; Claude writes the code with short lessons; no "written by Oleksii" in commits.
- GNU gettext is **not installed** on the author's machine (`msgfmt`/`xgettext` missing), and
  (Claude's call) the stage adds no system installs there. `makemessages`/`compilemessages` need it, so the plan
  must say where they run (e.g. inside the Docker image or CI) and whether compiled `.mo` files are
  committed so that host tests and the dev server work without gettext.
- Coverage gate 85% stays; existing query-count tests must keep passing.
- Smart App Control blocks fresh native wheels: any new dependency must be checked to import.

## Left to the builder

- Exact demo dataset (sizes, names, which statuses), the demo password (shown in the README; the
  account only ever exists locally).
- Which screens get screenshots and how they are captured (manual or Playwright), image size.
- Exact README wording below the pitch, and the "what the code shows" list (base it on
  `docs/architecture.md` decisions).
- Slovak and Russian wording.
- Exact spacing, font sizes and colour fine-tuning within the warm palette.
