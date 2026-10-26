# Этап 3, часть A — автозакрытие на стороне трекера — план реализации

> Перевод [английского плана](2026-10-26-stage3-part-a-tracker.md). При расхождениях главный — английский.

**Цель:** трекер выдаёт job-ai-assist список офферов Profesia, которые стоит проверить, и сам делает выводы,
когда тот сообщает, что какие-то из них закрылись.

**Архитектура:** одно новое поле (`Vacancy.closed_at`, может быть пустым), маленькая чистая функция, которая
достаёт номер оффера Profesia из адреса, метод queryset «стоит проверить» и доменный модуль
`tracker/closing.py`, где живут все правила «что значит закрытие» (как `tracker/ingest.py`). `api/` только
проверяет JSON и вызывает их; два новых эндпоинта с токеном лежат рядом с эндпоинтом приёма.

**Технологии:** Django 5.2, DRF + drf-spectacular, PostgreSQL 17, pytest-django, factory_boy.

**Спека:** `docs/superpowers/specs/2026-10-26-auto-close-design.md` (часть A).

## Общие ограничения

- «Закрыта» ⇔ так сообщил job-ai-assist; трекер сам Profesia не загружает.
- Applied → No response через `Application.change_status()`, комментарий `Posting closed on Profesia`, событие
  датировано `seen_at` — и тогда, когда вакансию перевыложили под новым номером.
- Любой другой статус отклика → статус не трогается; добавляется событие `note` с текстом
  `Posting closed on Profesia`, датированное `seen_at`.
- Отклика нет, вакансия во «Входящих» → state dismissed, `dismiss_reason` = `Closed on Profesia`. Отклика нет,
  уже отклонена → только `closed_at`.
- `closed_at` уже задан → `unchanged`, больше ничего не происходит.
- Ответ по каждому элементу: `closed` | `unchanged` | `unknown` | `invalid`; не больше 200 элементов в одном
  POST; по транзакции на элемент.
- Стоит проверить: есть `external_id`, `closed_at` пустой и (статус отклика Applied) или (отклика нет, state
  inbox, оценка ≥ `inbox_min_score` владельца или пустая).
- Оба эндпоинта: аутентификация токеном, владелец — пользователь запроса; чужие строки не видны (`unknown`).
- Текст надписи: `Closed on Profesia (ГГГГ-ММ-ДД)`.
- Бюджеты запросов прежние: «Входящие» 3, страница отклика 6, список откликов 3.
- Команды: тесты `py -3.12 -m pytest -q`; миграции `py -3.12 manage.py makemigrations tracker --noinput`.

## На что смотреть при ревью

1. Адреса Profesia бывают разными (хвост `?search_id=…`, слеш в конце, без `www`, `http`), а ещё у Profesia
   есть страницы не-офферы (`/praca/softec/`, `/praca/`). Номер берётся только из последнего сегмента пути
   вида `O\d+` на `profesia.sk`; всё прочее → ничего. Тест в задаче 2.
2. Один и тот же `external_id` дважды в одном отчёте → сначала `closed`, потом `unchanged`, событие одно.
   Тест в задаче 5.
3. Отчёт о закрытии для отклика, который уже Rejected / No response, не должен добавлять вторую смену
   статуса (анти-цель) — только заметку. Тест в задаче 4.
4. Закрытая вакансия, возвращённая кнопкой «Back to inbox», сохраняет `closed_at` и поэтому больше не
   предлагается к проверке. Тест в задаче 4.
5. Кривой `seen_at` или элемент не-объект дают `invalid` для этого элемента, а не 500; `closed` не списком
   → 400. Тест в задаче 5.

---

### Задача 1: `Vacancy.closed_at` и надпись «Closed on Profesia»

**Файлы:** `tracker/models.py`; новая миграция `0008_vacancy_closed_at.py` (генерируется);
`tracker/templates/tracker/inbox.html` (шапка карточки), `tracker/templates/tracker/application_detail.html`
(строка под заголовком); тесты `tests/tracker/test_closed_label.py`.

**Интерфейсы:** производит `Vacancy.closed_at: DateTimeField(null=True, blank=True)` — «когда трекер узнал,
что вакансия закрылась».

- [ ] **Шаг 1: падающие тесты** в `tests/tracker/test_closed_label.py`:
  - `test_inbox_card_shows_closed_date`: отклонённая вакансия (без оценки) с `closed_at=2026-10-27 08:20 UTC`;
    GET «Входящих» с `unprocessed=1` → в ответе есть `Closed on Profesia (2026-10-27)`.
  - `test_inbox_card_without_closed_date_has_no_label`: открытая вакансия → `Closed on Profesia` в ответе нет.
  - `test_application_page_shows_closed_date`: отклик с такой вакансией → на его странице есть
    `Closed on Profesia (2026-10-27)`.
- [ ] **Шаг 2: запуск** `py -3.12 -m pytest tests/tracker/test_closed_label.py -q` — ожидается FAIL
  (`closed_at` — неизвестный аргумент).
- [ ] **Шаг 3:** добавить поле, `py -3.12 manage.py makemigrations tracker --noinput -n vacancy_closed_at`,
  добавить надпись в оба шаблона (`{{ closed_at|date:"Y-m-d" }}`).
- [ ] **Шаг 4: запуск** `py -3.12 -m pytest -q` — всё зелёное (счётчики запросов прежние: поле в той же строке).
- [ ] **Шаг 5: коммит** `feat: vacancies remember when their posting closed`.

### Задача 2: номер оффера Profesia из адреса

**Файлы:** новый `tracker/profesia.py`; `tracker/models.py` (`Vacancy.save`); новая миграция
`0009_backfill_profesia_external_id.py`; тесты `tests/tracker/test_profesia.py`.

**Интерфейсы:**
- `profesia_offer_id(url: str) -> str | None` в `tracker/profesia.py`.
- `Vacancy.save()` заполняет `external_id` при полном сохранении (без `update_fields`), если он пустой, адрес
  даёт номер и ни у какой другой вакансии владельца этого номера нет.
- `backfill(apps, schema_editor)` в миграции 0009 — то же правило для уже существующих строк.

- [ ] **Шаг 1: падающие тесты** в `tests/tracker/test_profesia.py`:
  - `test_offer_id_from_url` с параметрами: `…/praca/builtmind/O5330945` → `O5330945`; то же с
    `?search_id=abc` → `O5330945`; то же со слешем в конце → `O5330945`; `http://profesia.sk/praca/x/O12` →
    `O12`; `…/praca/softec/` → None; `…/praca/` → None; `https://example.com/jobs/O5330945` → None;
    `""` → None; `"not a url"` → None.
  - `test_manual_vacancy_gets_offer_id_from_url`; `test_offer_id_not_taken_twice` (номер уже у другой вакансии
    владельца → остаётся None); `test_other_owner_does_not_block` (номер у чужой вакансии → заполняется);
    `test_existing_external_id_is_kept` (`O1` и адрес с `O2` → остаётся `O1`);
    `test_non_profesia_url_leaves_none`.
  - `test_backfill_fills_existing_rows`: две вакансии одного владельца с одним адресом Profesia и
    `external_id=None` (через `.update()`), запуск `backfill(django.apps.apps, None)` → номер получает ровно одна.
- [ ] **Шаг 2: запуск** `py -3.12 -m pytest tests/tracker/test_profesia.py -q` — FAIL (нет `tracker.profesia`).
- [ ] **Шаг 3:** `profesia_offer_id` на `urllib.parse.urlsplit` (хост `profesia.sk` или `www.profesia.sk`,
  последний непустой сегмент пути целиком вида `O\d+`); заполнение в `Vacancy.save()` (только без
  `update_fields`, чтобы смена статуса и переименование компании оставались одним запросом); миграция 0009
  (`RunPython(backfill, noop)`, зависит от 0008, импортирует функцию, как 0006 импортирует `fingerprint`;
  помнит номера, выданные в этом же проходе).
- [ ] **Шаг 4: запуск** `py -3.12 -m pytest -q` — всё зелёное.
- [ ] **Шаг 5: коммит** `feat: hand-entered Profesia vacancies get their offer id from the link`.

### Задача 3: `GET /api/v1/vacancies/to-check/`

**Файлы:** `tracker/managers.py`; `api/serializers.py`, `api/views.py`, `api/urls.py`; тесты
`tests/api/test_to_check_api.py`.

**Интерфейсы:** использует `Vacancy.closed_at`; производит `VacancyQuerySet.to_check(owner)` (сортировка по
`external_id`), имя адреса `api:vacancy-to-check`, ответ `{"vacancies": [{"external_id": str, "url": str}]}`.

- [ ] **Шаг 1: падающие тесты** — каждый создаёт вакансию и проверяет, есть ли её `external_id` в списке:
  отклик Applied (оценка 10 — для откликов оценка не важна) → есть; Replied → нет; «Входящие» с оценкой 40
  → есть; без оценки → есть; 39 → нет; отклонённая → нет; уже закрытая → нет; без `external_id` → нет;
  чужая → нет; точная форма ответа; 401 без токена и с неверным; `test_to_check_num_queries` — пять вакансий в
  списке → ровно 2 запроса (токен + список).
- [ ] **Шаг 2: запуск** — FAIL (`NoReverseMatch` для `api:vacancy-to-check`).
- [ ] **Шаг 3:** `to_check(owner)` через `Q` по `application__status` / `application__isnull`,
  `ToCheckResponseSerializer` (только для схемы), `VacancyToCheckView(APIView)` с `get()` и
  `UserRateThrottle`, маршрут `v1/vacancies/to-check/`.
- [ ] **Шаг 4: запуск** `py -3.12 -m pytest -q` — всё зелёное.
- [ ] **Шаг 5: коммит** `feat: API lists the offers worth checking for closure`.

### Задача 4: что значит закрытие — `tracker/closing.py`

**Файлы:** новый `tracker/closing.py`; тесты `tests/tracker/test_closing.py`.

**Интерфейсы:** производит `report_closed(owner, external_id: str, seen_at: datetime) -> str` →
`"closed" | "unchanged" | "unknown"`; константы `CLOSED_EVENT_TEXT = "Posting closed on Profesia"`,
`CLOSED_DISMISS_REASON = "Closed on Profesia"`.

- [ ] **Шаг 1: падающие тесты** (`SEEN = 2026-10-27 08:20 UTC`):
  - Applied → `closed`, статус `no_response`, новое событие `status_change` от SEEN с текстом
    `Applied → No response. Posting closed on Profesia`, `closed_at == SEEN`.
  - То же при перевыложенной копии во «Входящих» → всё равно `no_response`.
  - Interview и Rejected → статус прежний, ровно одно новое событие `note` «Posting closed on Profesia» от SEEN.
  - Вакансия во «Входящих» → `dismissed` с причиной «Closed on Profesia».
  - Уже отклонённая с причиной «too far» → причина сохраняется, задаётся только `closed_at`.
  - Два отчёта подряд → `closed`, `unchanged`; одно событие; `closed_at` от первого.
  - Неизвестный номер и чужой оффер → `unknown`, чужая строка не тронута.
  - Закрытая вакансия, возвращённая «Back to inbox» → state inbox, `closed_at` на месте, в `to_check` её нет.
- [ ] **Шаг 2: запуск** — FAIL (нет `tracker.closing`).
- [ ] **Шаг 3:** `report_closed`: одна `transaction.atomic()`, вакансия через `select_for_update()` вместе с
  откликом; для Applied — `change_status(NO_RESPONSE, comment=CLOSED_EVENT_TEXT, when=seen_at)`; вакансия
  сохраняется с `update_fields`. Докстринг модуля перечисляет правила, как в `tracker/ingest.py`.
- [ ] **Шаг 4: запуск** `py -3.12 -m pytest -q` — всё зелёное.
- [ ] **Шаг 5: коммит** `feat: a closed posting archives its application or leaves the inbox`.

### Задача 5: `POST /api/v1/vacancies/closed/`

**Файлы:** `api/serializers.py`, `api/views.py`, `api/urls.py`; тесты `tests/api/test_closed_api.py`.

**Интерфейсы:** использует `report_closed` и `MAX_BATCH = 200`; производит имя адреса `api:vacancy-closed`;
тело `{"closed": [{"external_id": str, "seen_at": ISO-дата-время}]}`; ответ
`{"results": [{"external_id", "status", "errors"?}]}`.

- [ ] **Шаг 1: падающие тесты:** 401 без токена; три элемента (Applied, неизвестный, строка `"oops"`) →
  `["closed", "unknown", "invalid"]`, код 200; один оффер дважды → `["closed", "unchanged"]` и одно событие;
  `seen_at="yesterday"` → `invalid`, в `errors` есть `seen_at`, номер возвращается; `{"closed": "x"}` → 400;
  201 элемент → 400, 200 → 200.
- [ ] **Шаг 2: запуск** — FAIL (`NoReverseMatch`).
- [ ] **Шаг 3:** `ClosedItemSerializer` (`external_id` до 50 символов, `seen_at` DateTimeField),
  `ClosedBatchSerializer` (сырые JSON-элементы, `max_length=MAX_BATCH`), сериализаторы ответа для схемы,
  `VacancyClosedView` с тем же разбором по элементам, что `VacancyIngestView._ingest_one`, маршрут
  `v1/vacancies/closed/`.
- [ ] **Шаг 4: запуск** тестов, ruff, bandit и проверки схемы drf-spectacular — всё чисто.
- [ ] **Шаг 5: коммит** `feat: API accepts reports of closed postings`.

### Задача 6: документация архитектуры

**Файлы:** `docs/architecture.md`, `docs/architecture.ru.md`.

- [ ] **Шаг 1:** добавить оба эндпоинта в раздел API, `closed_at` в раздел модели и решения 25+ (правила
  закрытия живут в `tracker/closing.py`; Applied → No response даже при перевыкладке; номер из адреса только
  при полном сохранении и никогда не отбирается у другой вакансии; `closed_at` переживает «Back to inbox»).
  То же в `.ru`.
- [ ] **Шаг 2: запуск** гейта покрытия — проходит.
- [ ] **Шаг 3: коммит** `docs: Stage 3 Part A in the architecture notes`.
