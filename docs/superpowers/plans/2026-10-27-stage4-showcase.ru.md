# Этап 4 — Витрина: план реализации

> Перевод. Каноническая версия — `2026-10-27-stage4-showcase.md`.

> **Для агентов-исполнителей:** ОБЯЗАТЕЛЬНЫЙ СКИЛЛ: superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans, задача за задачей. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** сделать трекер проектом для портфолио: интерфейс на английском, словацком и русском,
мягкий тёплый вид с шапкой «C», команда `seed_demo`, README со скриншотами; релиз v1.0.0.

**Архитектура:** i18n Django с собственной middleware, которая смотрит только на cookie (английский,
пока пользователь не выбрал язык). Английские фразы, которые пишет программа, остаются в базе и
переводятся при показе фильтром шаблона. Вид — тонкий `theme.css` поверх Pico.css. `seed_demo`
пересоздаёт строки одного изолированного демо-пользователя. Каталоги переводов (`.po` +
скомпилированные `.mo`) коммитятся; пересобираются в одноразовом Docker-контейнере, потому что на
машине разработки нет GNU gettext.

**Технологии:** Django 5.2, Pico.css, pytest-django + factory_boy, Docker (`python:3.12-slim` для gettext).

**Спека:** `docs/superpowers/specs/2026-10-27-stage4-showcase-design.md` (+ `.ru.md`)

## Общие ограничения

- Языки: `en` (по умолчанию), `sk`, `ru`; в выпадающем списке ровно `EN`, `SK`, `RU`.
- `Accept-Language` браузера игнорируется; язык переключает только cookie (ставится через `set_language`).
- Данные, введённые пользователем, не переводятся никогда; переводятся только фиксированные системные
  фразы из задачи 4.
- В базу системные тексты пишутся по-английски при любом активном языке.
- Миграций данных нет; `python manage.py makemigrations --check --dry-run` должен сообщать «нет изменений».
- Никаких новых зависимостей (runtime и dev); на Windows ничего не ставится.
- Палитра (из спеки): страница `#faf7f2`, карточки `#fffdfa`, линии `#ece5da`, текст `#33302b`,
  приглушённый `#7a7268`, таблетки `#f2ece3`, текущая таблетка `#f5e3cf` / текст `#8a5a2b`, главная
  кнопка `#b9824d`, значок оценки `#eef3e6` / текст `#4e6b2f`; скругление карточек ~14px, очень лёгкая
  тень; только светлая тема.
- На скриншотах и в репозитории — только демо-данные, никогда настоящие строки автора.
- Порог покрытия 85%; существующие бюджеты `django_assert_num_queries` не меняются.
- Коммиты: без «written by Oleksii»; в конце строка Co-Authored-By из напоминания сессии.
- У каждого затронутого документа обновляется двойник `.ru.md` (architecture, README).

## На что смотреть ревьюеру

1. Смена статуса, сделанная в русском или словацком интерфейсе → текст события в базе английский
   (иначе перевод при показе его не узнает). Тест в задаче 4.
2. Текст события, который только похож на системную фразу («Foo → Bar.», комментарий со «→»,
   неизвестные слова статуса) → показывается ровно как сохранён. Тест в задаче 4.
3. Cookie языка с неподдерживаемым или мусорным значением (`de`, `"><script>`) → английская страница,
   без ошибки. Тест в задаче 1.
4. `set_language` с `next` на чужой сайт → переадресация остаётся на этом сайте. Тест в задаче 1.
5. `seed_demo`, когда у автора есть компании с теми же названиями, что в демо, или при повторном
   запуске → строки автора не изменились, после второго запуска числа демо-строк те же. Тест в задаче 5.

---

### Задача 1: Механика языка (cookie-only, точка переключения, конвейер каталогов)

**Файлы:**
- Создать: `config/locale.py`, `docker/i18n.sh`, `locale/sk/LC_MESSAGES/.gitkeep`, `locale/ru/LC_MESSAGES/.gitkeep`
- Изменить: `config/settings/base.py`, `config/urls.py`, `templates/base.html` (только `<html lang>`)
- Тест: `tests/test_locale.py`

**Интерфейсы:**
- Даёт: `LANGUAGES = [("en", "English"), ("sk", "Slovenčina"), ("ru", "Русский")]`,
  `LOCALE_PATHS = [BASE_DIR / "locale"]`; middleware `config.locale.CookieLocaleMiddleware` сразу после
  `SessionMiddleware`; URL `path("i18n/", include("django.conf.urls.i18n"))` → имя `set_language`;
  `docker/i18n.sh` пересобирает и компилирует каталоги.

- [ ] **Шаг 1: Падающие тесты** в `tests/test_locale.py` (залогиненный клиент на дашборде):
  - `test_english_by_default_even_if_browser_prefers_slovak`: `HTTP_ACCEPT_LANGUAGE="sk"` → в ответе `'<html lang="en"'`.
  - `test_cookie_picks_the_language`: cookie `settings.LANGUAGE_COOKIE_NAME="ru"` → `'<html lang="ru"'`.
  - `test_unsupported_cookie_falls_back_to_english` с параметрами `["de", '"><script>', ""]` → статус 200 и `'<html lang="en"'`.
  - `test_set_language_sets_cookie_and_returns`: POST на `reverse("set_language")` `{"language": "sk", "next": "/inbox/"}` → 302 на `/inbox/`, `response.cookies[LANGUAGE_COOKIE_NAME].value == "sk"`.
  - `test_set_language_never_redirects_off_site`: `next="https://evil.example/"` → в `Location` нет `evil.example`.
- [ ] **Шаг 2: Запустить** `py -3.12 -m pytest tests/test_locale.py -q` — ожидается FAIL (нет URL `set_language`; `lang="en"` зашит, тест с ru падает).
- [ ] **Шаг 3: Реализовать** `CookieLocaleMiddleware` в `config/locale.py`: прочитать cookie, принять только значение из `dict(settings.LANGUAGES)`, иначе `settings.LANGUAGE_CODE`; `translation.activate(...)`, выставить `request.LANGUAGE_CODE`; в `process_response` поставить `Content-Language`. **Не** использовать `LocaleMiddleware` (он читает `Accept-Language`). Настройки и URL — как в интерфейсах. `base.html`: `{% load i18n %}{% get_current_language as LANGUAGE_CODE %}<html lang="{{ LANGUAGE_CODE }}" data-theme="light">`.
- [ ] **Шаг 4: Написать `docker/i18n.sh`** (окончания строк LF; `.gitattributes` уже держит `*.sh` в LF): ставит `gettext` через apt, `pip install -r requirements/base.txt`, `DJANGO_SETTINGS_MODULE=config.settings.dev`, затем
  `python manage.py makemessages -l sk -l ru --no-obsolete --ignore "tests/*" --ignore "docs/*" --ignore "staticfiles/*" --ignore "media/*" --ignore ".superpowers/*"` и `python manage.py compilemessages`. Комментарий в начале — почему в контейнере. Запуск из корня репозитория в PowerShell:
  `docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh docker/i18n.sh`
  Ожидается: появились `locale/sk/LC_MESSAGES/django.po` и `.mo` (и для `ru`), пока почти пустые.
- [ ] **Шаг 5: Запустить** `py -3.12 -m pytest -q` — ожидается: всё зелёное.
- [ ] **Шаг 6: Коммит** `feat: interface language picked by a cookie, English by default` (спека идёт отдельным коммитом `docs: Stage 4 spec` перед ним).

### Задача 2: Тёплая тема и шапка «C»

**Файлы:**
- Создать: `static/css/theme.css`
- Изменить: `templates/base.html`, `templates/registration/login.html`, `tracker/templatetags/tracker_extras.py`
- Тест: `tests/tracker/test_layout.py`

**Интерфейсы:**
- Берёт: URL `set_language`, `LANGUAGES` (задача 1).
- Даёт: тег `{% nav_section request as section %}` в `tracker_extras`, возвращает одно из
  `"dashboard" | "inbox" | "applications" | "vacancies" | "companies" | ""` по
  `request.resolver_match.url_name` (`dashboard`→dashboard; `inbox`, `vacancy_apply`, `vacancy_dismiss`,
  `vacancy_restore`→inbox; `application_*`, `attachment_download`→applications; остальные
  `vacancy_*`→vacancies; `company_*`→companies; всё прочее → `""`).

- [ ] **Шаг 1: Падающие тесты** в `tests/tracker/test_layout.py`:
  - `test_header_has_brand_and_language_dropdown`: в HTML дашборда есть `class="brand"` с `Job Apply Tracker`, `<select name="language"` с вариантами `value="en"`, `value="sk"`, `value="ru"`, подписи `EN`, `SK`, `RU`, у активного `selected` (cookie `ru` → `value="ru" selected`).
  - `test_current_section_is_marked` с параметрами: дашборд / входящие / карточка заявки / список вакансий / список компаний → ровно один `aria-current="page"`, и он на нужной ссылке (регулярка `href="{url}"[^>]*aria-current="page"`).
  - `test_nav_section_mapping` — юнит-тест тега на каждое имя URL из интерфейсов.
  - `test_theme_css_is_linked`: `css/theme.css` подключён после `css/pico.min.css`.
  - `test_login_page_uses_the_theme_without_nav`: на странице входа для анонима есть название и выбор языка, нет ссылок навигации.
- [ ] **Шаг 2: Запустить** `py -3.12 -m pytest tests/tracker/test_layout.py -q` — ожидается FAIL.
- [ ] **Шаг 3: Реализовать.** Шапка в `base.html`: строка 1 — `<a class="brand" href="dashboard">Job Apply Tracker</a>`, справа маленькая форма `method="post" action="{% url 'set_language' %}"` с `csrf_token`, скрытым `next` = `request.get_full_path`, `<select name="language" onchange="this.form.submit()">` и кнопкой в `<noscript>`; затем имя пользователя и кнопка Log out (только для вошедших). Строка 2 (только для вошедших) — пять ссылок `class="pill"`, у текущей `aria-current="page"`. `theme.css`: переопределить переменные Pico для светлой темы палитрой из общих ограничений; `.brand` ~1.4rem жирный, `line-height: 1.3`, без `overflow: hidden` (хвосты букв не обрезать); таблетки скруглённые с мягкой подложкой, текущая подсвечена; карточки (`article`) скругление ~14px, лёгкая тень; кнопки скругление ~10px, главная кнопка `#b9824d`; оценка `mark` — мягкий зелёный значок. Контраст основного текста AA (`#33302b` на `#faf7f2` проходит).
- [ ] **Шаг 4: Запустить** тесты шапки, потом `py -3.12 -m pytest -q` — ожидается: всё зелёное.
- [ ] **Шаг 5: Проверить глазами** через `py -3.12 manage.py runserver 8001`: название крупнее таблеток, «y» не обрезана, таблетки похожи на кнопки; сказать автору, на что посмотреть.
- [ ] **Шаг 6: Коммит** `feat: soft warm theme and a two-row header with a language dropdown`.

### Задача 3: Перевод интерфейса на словацкий и русский

**Файлы:**
- Изменить: все шаблоны в `templates/` и `tracker/templates/tracker/`, `tracker/models.py` (только подписи choices), `tracker/forms.py`, `tracker/views.py`, `locale/{sk,ru}/LC_MESSAGES/django.po` (+ скомпилированные `.mo`)
- Тест: `tests/test_translations.py`, `tests/tracker/test_translated_pages.py`

**Интерфейсы:**
- Берёт: `docker/i18n.sh` (задача 1).
- Даёт: ленивые подписи у `Application.Status`, `ApplicationEvent.EventType`, `Vacancy.State`
  (английский текст тот же); русские подписи статусов: Отправлена, Есть ответ, Собеседование, Оффер,
  Отказ, Нет ответа, Отозвана (их используют тесты задачи 4).

- [ ] **Шаг 1: Падающие тесты:**
  - `tests/test_translations.py::test_catalog_is_complete_and_compiled` с параметрами `["sk", "ru"]`: маленький парсер на стандартной библиотеке читает `locale/<lang>/LC_MESSAGES/django.po` (msgid/msgstr с продолжениями `""`; заголовок пропускается) и проверяет: записи есть, нет `#, fuzzy`, нет `msgid_plural`, нет пустых `msgstr`, и для каждой записи `translation.override(lang)` + `gettext(msgid) == msgstr` (доказывает, что закоммиченный `.mo` соответствует `.po`).
  - `tests/tracker/test_translated_pages.py::test_main_pages_have_no_english_labels` с параметрами `sk`, `ru` × дашборд, входящие, список заявок, карточка заявки, форма вакансии, список компаний, вход. В данных фикстуры слова, которые не могут совпасть (компания «Ľubovoľná», вакансия «Тестовая позиция», пользователь «olga»), поэтому проверка простая: в HTML нет ни одного из `["Dashboard", "Inbox", "Applications", "Vacancies", "Companies", "Log out", "Needs attention", "I applied", "Dismiss", "Timeline", "Change status", "Add event", "Attachments", "Log in", "Save"]`.
  - `test_status_labels_are_translated`: под `override("ru")` `str(Application.Status.NO_RESPONSE.label) == "Нет ответа"`.
- [ ] **Шаг 2: Запустить** оба файла — ожидается FAIL.
- [ ] **Шаг 3: Разметить строки:** подписи choices → `gettext_lazy` (`_("Applied")`…, английский тот же, миграции нет); `{% load i18n %}` + `{% translate %}` / `{% blocktranslate trimmed %}` во всех шаблонах (заголовки страниц, кнопки, placeholder-ы, строки «пусто», «posting», «score», «Closed on Profesia (…)», «applied … ago»); `gettext_lazy` для подписей и подсказок форм, `Meta.labels` (**не** добавлять `verbose_name` полям моделей — это создаст миграции), сообщений валидации; `gettext` с именованными подстановками для сообщений во view (`_("Applied: %(vacancy)s.") % {...}`). Без множественных форм.
- [ ] **Шаг 4: Пересобрать каталоги** командой `docker run … sh docker/i18n.sh` из задачи 1, заполнить все `msgstr` для `sk` и `ru` (коротко, русские статусы из интерфейсов), снова запустить контейнер для компиляции.
- [ ] **Шаг 5: Запустить** `py -3.12 -m pytest -q` и `py -3.12 manage.py makemigrations --check --dry-run` — ожидается: всё зелёное, «No changes detected».
- [ ] **Шаг 6: Коммит** `feat: the interface speaks Slovak and Russian`.

### Задача 4: Системные тексты на языке пользователя

**Файлы:**
- Изменить: `tracker/models.py` (`Vacancy.mark_applied`, `Application.change_status`), `tracker/closing.py` (пометить константы `gettext_noop`), `tracker/templatetags/tracker_extras.py`, шаблоны `dashboard.html`, `application_detail.html`, `inbox.html`, `locale/{sk,ru}/LC_MESSAGES/django.{po,mo}`
- Тест: `tests/tracker/test_system_text.py`

**Интерфейсы:**
- Берёт: `CLOSED_EVENT_TEXT`, `CLOSED_DISMISS_REASON` из `tracker/closing.py`; ленивые подписи и русские формулировки (задача 3).
- Даёт: фильтры `system_text(value: str) -> str` и `reasons(vacancy) -> str` в `tracker_extras`.

- [ ] **Шаг 1: Падающие тесты:**
  - `test_status_change_is_stored_in_english` с параметрами `["ru", "sk"]`: внутри `translation.override(lang)` вызвать `application.change_status(Status.REJECTED, comment="x")` и `vacancy.mark_applied(...)` → в базе `"Applied → Rejected. x"` и `"→ Applied"` (сейчас RED: ленивые подписи берут активный язык).
  - `test_system_text_translates_known_phrases` под `translation.override("ru")`: `"Applied → No response. Posting closed on Profesia"` → `"Отправлена → Нет ответа. Объявление закрыто на Profesia"`; `"→ Applied"` → `"→ Отправлена"`; `"Applied → Rejected."` → `"Отправлена → Отказ."`; `"Closed on Profesia"` → `"Закрыто на Profesia"`; `"Applied → Interview. позвонить в пятницу"` — комментарий остаётся дословно.
  - `test_system_text_in_english_is_unchanged`: те же входы под `override("en")` → вывод совпадает со входом.
  - `test_lookalike_text_is_left_alone` с параметрами `["Foo → Bar.", "called them → no answer", "Applied → Applied → Rejected.", "→ Hired"]` под `override("ru")` → возвращаются без изменений.
  - `test_reasons_follow_language`: вакансия с обоими полями объяснений → `ru` даёт `score_reasons_ru`, `en` и `sk` дают `score_reasons`; если заполнено одно поле, любой язык берёт его; оба пустые → `""`.
  - `test_timeline_and_inbox_use_the_filters`: карточка заявки в `ru` (cookie) с сохранённым событием о закрытии показывает перевод; карточка во входящих, отклонённая с `CLOSED_DISMISS_REASON`, показывает переведённую причину (вид «необработанные»); вакансия с обоими объяснениями под `en` показывает английское.
- [ ] **Шаг 2: Запустить** `py -3.12 -m pytest tests/tracker/test_system_text.py -q` — ожидается FAIL (нет фильтров, в базу пишется русский).
- [ ] **Шаг 3: Реализовать.**
  - `change_status` и `mark_applied` собирают текст события внутри `translation.override("en")`.
  - `system_text`: точное совпадение с `CLOSED_EVENT_TEXT` / `CLOSED_DISMISS_REASON` → `gettext` от него; `"→ <Label>"` и `"<Label> → <Label>." + необязательный " <comment>"`, где обе подписи — английские подписи `Application.Status`, → переведённые подписи; комментарий переводится, только если он равен `CLOSED_EVENT_TEXT`; всё остальное без изменений. Словарь «английская подпись → статус» строится под `override("en")`. Обе константы пометить `gettext_noop`: они остаются обычными английскими строками, но попадают в каталог.
  - `reasons`: если `get_language()` начинается с `ru` → `score_reasons_ru or score_reasons`, иначе `score_reasons or score_reasons_ru`.
  - Шаблоны: история и недавние события — `event.text|system_text` (на дашборде `|system_text|truncatechars:60`); во входящих `vacancy.dismiss_reason|system_text`, `vacancy.prev_dismiss_reason|system_text` и `vacancy|reasons` вместо `firstof`.
  - Снова запустить `docker/i18n.sh`, заполнить два новых `msgstr` (ru: «Объявление закрыто на Profesia», «Закрыто на Profesia»; словацкие аналоги), скомпилировать.
- [ ] **Шаг 4: Запустить** файл, потом `py -3.12 -m pytest -q` и `makemigrations --check --dry-run` — ожидается: всё зелёное, «No changes detected».
- [ ] **Шаг 5: Коммит** `feat: system-written texts are shown in the user's language`.

### Задача 5: `seed_demo` — демо-аккаунт с выдуманными данными

**Файлы:**
- Создать: `tracker/management/commands/seed_demo.py`
- Тест: `tests/tracker/test_seed_demo.py`

**Интерфейсы:**
- Даёт: `python manage.py seed_demo` → пользователь `demo`, пароль `tracker-demo` (константы
  `DEMO_USERNAME`, `DEMO_PASSWORD` в модуле, их упоминает README); `CommandError`, если существующий
  `demo` — staff, суперпользователь или у него есть API-токен.

- [ ] **Шаг 1: Падающие тесты** (`call_command("seed_demo")`):
  - `test_creates_a_believable_demo_account`: есть пользователь `demo`, `check_password("tracker-demo")`, не staff; ≥ 5 компаний, ≥ 10 вакансий, заявки как минимум в статусах `applied`, `replied`, `interview`, `rejected`, `no_response`; хотя бы одна вакансия с `closed_at`; хотя бы одна вакансия во входящих с обоими объяснениями; хотя бы одна отклонённая вакансия.
  - `test_dashboard_has_something_to_show`: `Application.objects.needs_attention(demo)` не пуст, и вид входящих по умолчанию (`for_inbox_view(demo)`) не пуст.
  - `test_running_twice_gives_the_same_result`: после второго запуска у `demo` столько же компаний, вакансий, заявок и событий.
  - `test_other_users_rows_are_untouched`: другой пользователь с компанией, названной как демо-компания, вакансией и заявкой с событием; снимок их `values()` до == после.
  - `test_refuses_a_real_demo_account` с параметрами: `demo` — staff / суперпользователь / с `Token` → `CommandError`, его строки не изменились.
  - `test_demo_urls_never_point_to_profesia`: у всех демо-вакансий `url` начинается с `https://example.com/`, `external_id` — `None`.
- [ ] **Шаг 2: Запустить** `py -3.12 -m pytest tests/tracker/test_seed_demo.py -q` — ожидается FAIL (неизвестная команда).
- [ ] **Шаг 3: Реализовать** внутри `transaction.atomic()`: защита; получить или создать `demo` (задать пароль, `is_staff=False`); сначала удалить его `Application` (FK вакансии — PROTECT), потом вакансии, потом компании; создать набор из списка обычных словарей на уровне модуля (выдуманные компании Братиславы вроде «Danubia Data s.r.o.», вакансии junior developer / data analyst, зарплаты в стиле Profesia, объяснения EN + RU, источник `job_ai_assist` у оценённых, адреса `example.com`). Даты от `timezone.now()`: одна заявка `applied` старше `follow_up_days` (требует внимания), одна свежая; у одной `no_response` стоит `closed_at` и событие о закрытии через `change_status(... comment=CLOSED_EVENT_TEXT)`. В конце одна строка-итог с логином.
- [ ] **Шаг 4: Запустить** файл, потом весь набор — ожидается: всё зелёное.
- [ ] **Шаг 5: Коммит** `feat: seed_demo builds a demo account with invented data`.

### Задача 6: README, скриншоты, архитектурные заметки

**Файлы:**
- Создать: `README.md`, `README.ru.md`, `docs/screenshots/*.png`
- Изменить: `docs/architecture.md`, `docs/architecture.ru.md`

- [ ] **Шаг 1:** Запустить `seed_demo` на **dev**-базе (`py -3.12 manage.py seed_demo`, dev-настройки → `tracker_dev`) и `runserver 8001`.
- [ ] **Шаг 2: Скриншоты делает автор** (автоматизации браузера нет, и её не добавляем): войти как `demo`, окно ~1280 px в ширину, сохранить PNG в `docs/screenshots/`: `dashboard.png`, `inbox.png`, `application.png` (карточка с историей), `applications.png`, `inbox-sk.png` (словацкий интерфейс). Затем Claude открывает каждый PNG и проверяет, что там только демо-данные, и только потом коммитит.
- [ ] **Шаг 3: README.md** — вступление из спеки дословно наверху; скриншоты; «What the code shows» (≤ 10 пунктов по решениям из `docs/architecture.md`: изоляция по владельцу, свои QuerySet и бюджеты N+1, DRF API с токенами и поэлементными итогами пачки, идемпотентный приём и переопубликации, правила автозакрытия в домене, i18n с переводом системных текстов при показе, покрытие 99% + CI безопасности, Docker с gunicorn gthread); «Run it locally»: скопировать `.env.example` в `.env`, `docker compose up -d --build`, `docker compose exec web python manage.py seed_demo`, открыть http://localhost:8000 и войти как `demo` / `tracker-demo`; ссылка на job-ai-assist; строка о лицензии, только если она есть в репозитории. `README.ru.md` — русский двойник, файлы ссылаются друг на друга.
- [ ] **Шаг 4: Архитектурные документы:** строка версии → v1.0.0; добавить i18n (middleware только по cookie, каталоги через `docker/i18n.sh`, `.mo` в репозитории), тему, `seed_demo`; в Decisions — по записи на каждый `Ruling:` из журнала этого плана, плюс: язык только по cookie, перевод системных текстов при показе (и почему не структурные события), `.mo` в репозитории, демо в живой базе с защитой.
- [ ] **Шаг 5: Запустить** `py -3.12 -m pytest --cov=accounts --cov=tracker --cov=api --cov-fail-under=85 -q`, `py -3.12 -m ruff check .`, `py -3.12 -m ruff format --check .`, `py -3.12 -m bandit -r accounts tracker api config -q` — ожидается: всё зелёное.
- [ ] **Шаг 6: Коммит** `docs: README with screenshots, architecture for v1.0.0`.

После слияния (finishing-a-development-branch): CI на `main` зелёный → `docker compose up -d --build web`,
`docker compose exec web python manage.py seed_demo` на живой базе, проверить `/` на EN/SK/RU, тег `v1.0.0`.
