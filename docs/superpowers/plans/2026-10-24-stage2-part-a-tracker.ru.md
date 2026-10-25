# Этап 2, часть A — сторона трекера для отправки из job-ai-assist — план реализации

> **Для агентов-исполнителей:** ОБЯЗАТЕЛЬНЫЙ САБ-СКИЛЛ: superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans — выполнять план задача за задачей. Шаги размечены чекбоксами (`- [ ]`).

> Это перевод [английского плана](2026-10-24-stage2-part-a-tracker.md) для удобства автора.
> При расхождениях главный — английский файл.

**Цель:** трекер постоянно работает в Docker, принимает пакеты оценённых вакансий через REST API с
токеном и превращает их в чистые «Входящие» с переключателями «Неразобранные» / «ниже порога»,
архив откликов и повторные отклики с учётом перепостов.

**Архитектура:** логика приёма живёт в доменном приложении (`tracker/ingest.py`), HTTP — в новом
приложении `api/` (DRF + authtoken + drf-spectacular). Виды «Входящих» — это чистая сборка
queryset'ов на `VacancyQuerySet` (аннотации, без хранимых флагов). Рабочие данные остаются в
существующей базе `tracker`, их обслуживает контейнер с gunicorn; разработка переезжает в отдельную
базу `tracker_dev`.

**Стек:** Django 5.2, PostgreSQL 17, djangorestframework, drf-spectacular, gunicorn, whitenoise,
Docker Compose. Python через `py -3.12`.

**Спека:** `docs/superpowers/specs/2026-10-24-stage2-push-api-design.md` (рядом русская версия; канон
— английская). Как построено сейчас: `docs/architecture.md`.

## Глобальные ограничения

- Команды Python: `py -3.12 ...`. Новые пакеты: `py -3.12 -m pip install -r requirements/dev.txt`.
  Если импорт падает с «DLL load failed … Политика управления приложениями» (Smart App Control) —
  поставить предыдущую минорную версию пакета и закрепить её с комментарием, как сделано для psycopg.
- Лимит пакета приёма — **200** элементов; `score` — целое **0–100**; `score_stage` ∈ {`rough`,
  `final`}; нет или пустая компания → **`Unknown company`**.
- Настройки пользователя по умолчанию: `inbox_min_score` **40**, `inbox_fresh_days` **5**.
- Закрытые статусы отклика: ровно **Rejected, No response, Withdrawn**.
- Отпечаток = `f"{norm(company)}|{norm(title)}"`, где `norm` — нижний регистр, удаление диакритики
  через NFKD + выброс комбинируемых символов, схлопывание пробелов — один в один как
  `app/store.py::fingerprint` в job-ai-assist.
- Каждая запись соблюдает изоляцию владельца (`OwnerQuerySetMixin` / `request.user`); каждое
  изменение состояния — только POST и редирект.
- Бюджеты запросов закреплены: входящие **3**, список откликов **3**, список вакансий **3**,
  дашборд **6**.
- Никогда не запускать `create_api_token` из shell Claude (его вывод — секрет, аудит-лог записывает
  команды, а Claude видит вывод); пользователь запускает её сам.
- После мержа этой ветки рабочий контейнер пересобирается **только из `main`**
  (`docker compose up -d --build web`); никогда не собирать рабочий контейнер из feature-ветки с
  новыми миграциями.
- Порог покрытия 85%; ruff и bandit чистые. Ветка `feature/stage2-api`, в конце один PR.
- Формат работы: перед каждой задачей пользователь получает короткий урок простым языком (что и
  зачем, угол для собеседования); весь код пишет Claude.

## Фокус ревью

1. Названия компаний, отличающиеся только регистром или пробелами по краям («Softec » и «softec»),
   дают одну Company — задача 3.
2. Один и тот же `external_id` дважды в одном пакете → второй элемент `updated`, без IntegrityError
   — задача 3.
3. Элемент пакета, который не JSON-объект (строка, число) → этот элемент `invalid`, остальные
   обработаны, без 500 — задача 3.
4. Границы: оценка ровно 40 и возраст ровно `inbox_fresh_days` считаются «Входящими» по умолчанию
   — задача 4.
5. Повторная отправка со сменой названия пересчитывает отпечаток (сопоставление перепостов идёт по
   текущему названию) — задача 3.

---

### Задача 1: Постоянный Docker-контейнер, раздельные базы рабочая/разработки

**Сначала урок:** образ Docker и контейнер; gunicorn и runserver; почему рабочие данные и данные
разработки не должны делить одну базу; что делает WhiteNoise.

**Файлы:**
- Создать: `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`,
  `docker/postgres-init/01-dev-db.sql`, `.env.example`, `tests/test_settings.py`
- Изменить: `requirements/base.txt` (+ `gunicorn`, `whitenoise`), `config/settings/base.py`
  (WhiteNoise middleware сразу после SecurityMiddleware, `STATIC_ROOT = BASE_DIR / "staticfiles"`),
  `config/settings/dev.py` (`NAME` базы = `"tracker_dev"`), `config/settings/prod.py`,
  `docker-compose.yml`, `.github/workflows/ci.yml` (`POSTGRES_DB: tracker_dev`)

**Интерфейсы (производит):**
- `config.settings.prod` читает из окружения: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (список
  через запятую), `POSTGRES_DB/USER/PASSWORD/HOST/PORT`, `DJANGO_MEDIA_ROOT` (по умолчанию
  `/data/media`), `DJANGO_HTTPS` (по умолчанию `"1"`; `"0"` выключает `SECURE_SSL_REDIRECT`,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS).
- Сервис compose `web`: build `.`, `env_file: .env`, `DJANGO_SETTINGS_MODULE=config.settings.prod`,
  `POSTGRES_HOST=db`, `POSTGRES_DB=tracker`, `ports: "127.0.0.1:8000:8000"`, том `media:/data/media`,
  `restart: unless-stopped`, `depends_on: db (service_healthy)`, сети `default` и `jobnet` с
  псевдонимом **`job-apply-tracker`**. На верхнем уровне `networks: jobnet: name: job-net`
  (фиксированное имя, не external). У `db` — healthcheck `pg_isready` и монтирование
  `./docker/postgres-init` в `/docker-entrypoint-initdb.d` (создаёт `tracker_dev` на новом томе).
- Точка входа контейнера: `python manage.py migrate --noinput`, затем
  `gunicorn config.wsgi -b 0.0.0.0:8000 --workers 2`. Образ: `python:3.12-slim`, не-root пользователь
  `app` (uid 10001), `collectstatic` при сборке с фиктивным секретом.
- `.env.example`: `DJANGO_SECRET_KEY=change-me`,
  `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,job-apply-tracker`, `DJANGO_HTTPS=0`,
  `POSTGRES_USER=tracker`, `POSTGRES_PASSWORD=devpass`.

- [ ] **Шаг 1: Падающие тесты** в `tests/test_settings.py`:
  - `test_dev_settings_use_dev_database`: `settings.DATABASES["default"]["NAME"].endswith("tracker_dev")`
    (test runner добавляет префикс `test_`).
  - `test_prod_https_flags_follow_env(monkeypatch)`: с нужными переменными и `DJANGO_HTTPS="0"`
    `importlib.reload(config.settings.prod)` → `SESSION_COOKIE_SECURE is False` и
    `SECURE_SSL_REDIRECT is False`; с `"1"` → оба `True`.
  - `test_prod_uses_whitenoise`: `"whitenoise.middleware.WhiteNoiseMiddleware"` в `MIDDLEWARE`
    перезагруженного prod.
- [ ] **Шаг 2:** `py -3.12 -m pytest tests/test_settings.py -v` → FAIL.
- [ ] **Шаг 3:** Реализовать файлы выше. Поставить зависимости.
- [ ] **Шаг 4:** `py -3.12 -m pytest -q` → всё проходит (набор теперь работает на `test_tracker_dev`).
- [ ] **Шаг 5: Вручную, вместе с пользователем** (Claude запускает только команды без секретов):
  1. Пользователь копирует `.env.example` → `.env` и сам вписывает настоящий случайный
     `DJANGO_SECRET_KEY`.
  2. `docker compose exec db createdb -U tracker tracker_dev` (том уже существует; скрипт
     инициализации срабатывает только на новом), затем `py -3.12 manage.py migrate` → база
     разработки готова, рабочая `tracker` не тронута.
  3. `docker compose up -d --build web` → http://localhost:8000 показывает существующие данные
     пользователя. (Собирать из ветки безопасно только здесь: на этом коммите в ветке нет новых
     миграций, поэтому `migrate` в точке входа ничего не меняет в рабочей базе `tracker`.)
  4. Один раз скопировать существующие файлы: `docker compose cp media/. web:/data/media/`, затем
     `docker compose exec -u root web chown -R app:app /data/media`; старое вложение скачивается.
  5. `docker network inspect job-net` показывает контейнер `web` с псевдонимом `job-apply-tracker`.
- [ ] **Шаг 6:** Коммит `feat: always-on docker container, separate dev database`.

### Задача 2: Дополнения моделей вакансии и пользователя

**Сначала урок:** миграции, добавляющие поля, и миграции данных; почему хранимый отпечаток с
индексом лучше вычисления в каждом запросе.

**Файлы:**
- Создать: `tracker/fingerprints.py`, `tests/tracker/test_fingerprints.py`
- Изменить: `tracker/models.py`, `accounts/models.py`, `accounts/admin.py`, `tracker/admin.py`,
  миграции (схема + один `RunPython`, заполняющий `fingerprint` у существующих вакансий)

**Интерфейсы (производит):**
- `tracker.fingerprints.fingerprint(company: str, title: str) -> str` (правило в Глобальных
  ограничениях).
- Новые/изменённые поля `Vacancy`: `score_stage = CharField(5, choices ScoreStage: ROUGH="rough",
  FINAL="final", blank=True)`; `score_reasons` остаётся (английский); новое
  `score_reasons_ru = TextField(blank=True)`; `first_seen_at = DateTimeField(null=True, blank=True)`;
  `fingerprint = CharField(max_length=500, db_index=True, editable=False)`; расширить `url` до
  `max_length=500`, `salary` до 200, `location` до 200.
- `Vacancy.save()` выставляет `self.fingerprint = fingerprint(self.company.name, self.title)` перед
  сохранением.
- `accounts.User`: `inbox_min_score = PositiveSmallIntegerField(default=40,
  validators=[MaxValueValidator(100)])`, `inbox_fresh_days = PositiveSmallIntegerField(default=5,
  validators=[MinValueValidator(1)])`; оба в разделе админки «Tracker» рядом с `follow_up_days`.

- [ ] **Шаг 1: Падающие тесты:**
  - `test_fingerprint_normalizes`: `fingerprint("  Softec ", "Junior  PYTHON  Developer") ==
    "softec|junior python developer"`; `fingerprint("Príležitosť s.r.o.", "Študent") ==
    "prilezitost s.r.o.|student"`.
  - `test_vacancy_save_sets_fingerprint` (тест модели, `VacancyFactory(company__name="ESET",
    title="Junior Dev")` → `"eset|junior dev"`).
  - `test_user_inbox_defaults`: `UserFactory().inbox_min_score == 40`, `.inbox_fresh_days == 5`.
- [ ] **Шаг 2:** Запустить → FAIL. **Шаг 3:** Реализовать + `makemigrations` (заполнение через
  `RunPython`, перебирая вакансии с `select_related("company")`). **Шаг 4:**
  `py -3.12 -m pytest -q` → PASS; `makemigrations --check` чисто.
- [ ] **Шаг 5:** Коммит `feat: vacancy fingerprint, score stage, bilingual reasons, inbox settings`.

### Задача 3: API приёма

**Сначала урок:** REST, JSON, что такое сериализатор, токен против сессии, идемпотентность, зачем
результаты по каждому элементу.

**Файлы:**
- Создать: `api/__init__.py`, `api/apps.py`, `api/serializers.py`, `api/views.py`, `api/urls.py`,
  `tracker/ingest.py`, `tracker/management/__init__.py`, `tracker/management/commands/__init__.py`,
  `tracker/management/commands/create_api_token.py`, `tests/api/__init__.py`,
  `tests/api/test_ingest_api.py`, `tests/tracker/test_ingest.py`,
  `tests/tracker/test_create_api_token.py`
- Изменить: `requirements/base.txt` (+ `djangorestframework`, `drf-spectacular`),
  `config/settings/base.py` (`INSTALLED_APPS` + `rest_framework`, `rest_framework.authtoken`,
  `drf_spectacular`, `api`; `REST_FRAMEWORK` с `DEFAULT_SCHEMA_CLASS` от spectacular и
  `DEFAULT_THROTTLE_RATES = {"user": "60/hour"}`), `config/urls.py`
  (`path("api/", include("api.urls"))`), `.github/workflows/ci.yml` (`--cov=api`, bandit
  `-r accounts tracker api config`)

**Интерфейсы (производит):**
- `tracker.ingest.ingest_vacancy(owner, data: dict) -> tuple[Vacancy, str]` — `data` — проверенный
  словарь элемента; возвращает `(vacancy, "created" | "updated")`; работает в `transaction.atomic()`.
  Правила точно как в спеке, A1 «Правила приёма»: поиск по `(owner, external_id)` → обновить только
  поля, принадлежащие job-ai-assist; иначе усыновить самую свежую вакансию владельца с
  `external_id IS NULL` и тем же отпечатком (заполнить оценку / этап / причины / `first_seen_at`,
  location и salary — только если пустые; статус `"updated"`); иначе создать с
  `source=job_ai_assist`, `state=inbox`. Компания:
  `Company.objects.filter(owner=owner, name__iexact=name.strip()).first()` или создать; пусто →
  `Unknown company`. `first_seen_at` пишется только при создании/усыновлении. Списки причин хранятся
  как `"\n".join(...)`; отсутствующий ключ оставляет сохранённые причины как есть.
- `api.serializers.VacancyItemSerializer` (поля и правила из таблицы спеки);
  `VacancyBatchSerializer` (`vacancies = ListField(child=JSONField(), max_length=200,
  allow_empty=True)`).
- `api.views.VacancyIngestView(APIView)`: `authentication_classes=[TokenAuthentication]`,
  `permission_classes=[IsAuthenticated]`, `throttle_classes=[UserRateThrottle]`, `post()` → 400 при
  ошибках пакета; иначе по каждому элементу: не словарь или невалиден →
  `{"external_id": <присланный или "">, "status": "invalid", "errors": ...}`; валиден →
  `ingest_vacancy` → `{"external_id", "status", "id"}`. Ответ `{"results": [...]}`, 200. С
  `extend_schema` (сериализаторы запроса/ответа), чтобы Swagger показывал контракт.
- `api/urls.py`: `v1/vacancies/` (имя `api:vacancy-ingest`), `schema/` (`SpectacularAPIView`, имя
  `api:schema`), `schema/swagger-ui/` (`SpectacularSwaggerView`).
- `create_api_token <username> [--rotate]`: печатает ключ; если токен уже есть и нет `--rotate` →
  ошибка «token exists, use --rotate».

- [ ] **Шаг 1: Падающие доменные тесты** (`tests/tracker/test_ingest.py`):
  `test_creates_inbox_vacancy_with_job_ai_assist_source`; `test_repush_updates_score_and_keeps_state`
  (отклонённая остаётся отклонённой со своей причиной; откликнутая остаётся откликнутой);
  `test_repush_does_not_move_first_seen_at`; `test_repush_keeps_reasons_when_omitted`;
  **(ФР №5)** `test_repush_title_change_updates_fingerprint`; **(ФР №1)**
  `test_company_reused_ignoring_case_and_spaces` (`" softec "` → существующая `Softec`,
  `Company.objects.count()` не меняется); `test_blank_company_becomes_unknown_company`;
  `test_adopts_manual_vacancy_with_same_fingerprint` (ручная откликнутая вакансия получает
  `external_id`, сохраняет состояние/отклик/source; новой строки нет);
  `test_does_not_adopt_vacancy_that_already_has_external_id`; `test_ingest_is_owner_scoped` (один
  `external_id` у двух пользователей → две строки).
- [ ] **Шаг 2: Падающие тесты API** (`tests/api/test_ingest_api.py`, `APIClient` + `Token`):
  `test_requires_token` (401 без токена / с неверным); `test_created_and_updated_results` (значения
  статусов, id, порядок); `test_invalid_item_does_not_block_others` (оценка 150 → `invalid` с
  `errors["score"]`, соседний `created`); **(ФР №3)** `test_non_object_item_is_invalid`;
  **(ФР №2)** `test_same_external_id_twice_in_batch` (`["created", "updated"]`, одна строка);
  `test_more_than_200_items_is_400`; `test_missing_vacancies_key_is_400`;
  `test_schema_and_swagger_respond` (GET `api:schema` 200). Тесты команды:
  `test_create_api_token_prints_key` (перехватить stdout, `Token.objects.get(user=...).key in out`),
  `test_existing_token_requires_rotate`.
- [ ] **Шаг 3:** Запустить → FAIL. **Шаг 4:** Реализовать. **Шаг 5:** `py -3.12 -m pytest -q` → PASS.
- [ ] **Шаг 6:** Коммит `feat: token-authenticated vacancy ingest API with OpenAPI schema`.

### Задача 4: Виды «Входящих» и «Back to inbox»

**Сначала урок:** сборка queryset'ов через `Q`, `Coalesce`, подзапросы `Exists`; GET-параметры для
фильтров.

**Файлы:**
- Изменить: `tracker/managers.py`, `tracker/views.py` (`InboxView`, `DashboardView`, новая
  `VacancyRestoreView`), `tracker/urls.py`, `tracker/templates/tracker/inbox.html`
- Тесты: `tests/tracker/test_inbox_views.py`; обновить `tests/tracker/test_views_dashboard.py`
  (счётчик входящих)

**Интерфейсы (производит):**
- `VacancyQuerySet.for_inbox_view(owner, *, unprocessed: bool = False, below_threshold: bool =
  False) -> VacancyQuerySet` — с фильтром по владельцу, аннотирован
  `age_at = Coalesce("first_seen_at", "created_at")` и `has_newer_repost = Exists(<тот же владелец,
  тот же отпечаток, состояние inbox, age_at больше, другой pk>)`, `select_related("company")`,
  порядок как у `inbox()`. Множества (спека A3), где `min = owner.inbox_min_score`,
  `cutoff = now - timedelta(days=owner.inbox_fresh_days)`,
  `scored_enough = Q(score__gte=min) | Q(score__isnull=True)`:
  - по умолчанию: `state=inbox & scored_enough & age_at >= cutoff & ~has_newer_repost`
  - неразобранные: `scored_enough & ((state=inbox & (age_at < cutoff | has_newer_repost)) |
    state=dismissed)`
  - ниже порога: `score < min & state in (inbox, dismissed)`
  - возвращает «по умолчанию» ИЛИ включённые множества.
- `InboxView` читает `?unprocessed=1` и `?low=1`; контекст `show_unprocessed`, `show_low`. Шаблон:
  GET-форма с двумя галочками; на карточке пометка «rough» при `score_stage == "rough"`; причины
  `{% firstof vacancy.score_reasons_ru vacancy.score_reasons %}` с `linebreaksbr`; у отклонённых
  карточек — причина + POST-форма «Back to inbox»; при `has_newer_repost` — пометка «newer repost in
  inbox».
- `VacancyRestoreView` (только POST, с фильтром по владельцу): `state=inbox`, `dismiss_reason=""`,
  редирект на `tracker:inbox`. URL `vacancies/<pk>/restore/`, имя `vacancy_restore`.
- Дашборд: `inbox_count = Vacancy.objects.for_inbox_view(user).count()`.

- [ ] **Шаг 1: Падающие тесты:** `test_default_shows_fresh_scored_and_manual`; **(ФР №4)**
  `test_boundaries_score_40_and_age_exactly_fresh_days_are_default` («сейчас» фиксируется через
  `first_seen_at = timezone.now() - timedelta(days=5) + timedelta(seconds=30)`);
  `test_old_vacancy_moves_to_unprocessed`; `test_dismissed_40_plus_in_unprocessed_low_in_below_threshold`;
  `test_only_newest_repost_in_default` (старший собрат в неразобранных, `has_newer_repost` True);
  `test_every_unapplied_vacancy_in_exactly_one_view` (по одной вакансии каждого вида; три множества
  не пересекаются, а их объединение = все вакансии без отклика); `test_toggles_via_get_params`;
  `test_user_threshold_setting_respected` (`inbox_min_score=70`);
  `test_restore_returns_dismissed_to_inbox` и `test_restore_is_post_only` (405);
  `test_foreign_vacancy_restore_404`; `test_inbox_num_queries_with_toggles` (все переключатели
  включены, 3 запроса); дашборд: `test_inbox_count_counts_default_view_only`.
- [ ] **Шаг 2:** Запустить → FAIL. **Шаг 3:** Реализовать. **Шаг 4:** `py -3.12 -m pytest -q` → PASS.
- [ ] **Шаг 5:** Коммит `feat: inbox default view with unprocessed and below-threshold toggles`.

### Задача 5: Архив откликов

**Файлы:**
- Изменить: `tracker/models.py` (`Application.CLOSED_STATUSES = (Status.REJECTED,
  Status.NO_RESPONSE, Status.WITHDRAWN)`), `tracker/views.py` (`ApplicationListView`),
  `tracker/templates/tracker/application_list.html`
- Тесты: `tests/tracker/test_views_application.py`

**Интерфейсы:** `ApplicationListView` скрывает `status__in=CLOSED_STATUSES`, если нет `?archive=1`
или явно выбранного `?status=`; контекст `show_archive`; шаблон добавляет галочку «Archive» в
существующую GET-форму.

- [ ] **Шаг 1: Падающие тесты:** `test_closed_applications_hidden_by_default` (rejected,
  no_response, withdrawn скрыты; offer и applied видны); `test_archive_toggle_shows_closed`;
  `test_explicit_status_filter_shows_closed_status`; тест бюджета запросов списка всё ещё 3.
- [ ] **Шаги 2–4:** Запустить → FAIL, реализовать, `py -3.12 -m pytest -q` → PASS.
- [ ] **Шаг 5:** Коммит `feat: applications archive for closed statuses`.

### Задача 6: Перепосты и повторные отклики

**Сначала урок:** ForeignKey на саму себя; аннотации `Subquery`/`OuterRef`, чтобы показывать связанные
факты без N+1.

**Файлы:**
- Изменить: `tracker/models.py` (`Application.previous_attempt = ForeignKey("self", null=True,
  blank=True, on_delete=SET_NULL, related_name="later_attempts")`;
  `Vacancy.mark_applied(applied_at, notes="", previous_attempt=None)`;
  `Vacancy.previous_applications() -> ApplicationQuerySet` — тот же владелец + отпечаток, другие
  вакансии, сначала самый свежий `applied_at`), `tracker/managers.py` (аннотации для
  `for_inbox_view`), `tracker/forms.py` (`ApplyForm(*args, previous_attempts=None, **kwargs)`
  добавляет обязательное `apply_again = BooleanField(label="Yes, apply again")` только при наличии
  прошлых попыток), `tracker/views.py` (`VacancyApplyView`: передаёт `previous_attempts`, связывает
  новый отклик с самым свежим прошлым; `ApplicationPageMixin` добавляет
  `select_related("previous_attempt__vacancy")` и `prefetch_related("later_attempts__vacancy")`),
  шаблоны `inbox.html`, `apply_form.html`, `application_detail.html`, миграция
- Тесты: `tests/tracker/test_reposts.py`; обновить бюджет запросов страницы отклика в
  `tests/tracker/test_views_application.py` на новое закреплённое число (ожидается 6)

**Интерфейсы (производит):**
- Строки `for_inbox_view` дополнительно аннотированы: `prev_application_pk`, `prev_applied_at`,
  `prev_status` (последний отклик вакансии-собрата, через `Subquery`), `prev_dismiss_reason`
  (причина последнего отклонённого собрата). Карточки входящих: «Already applied on {date} —
  {status}» со ссылкой на `prev_application_pk` или «Dismissed before: {reason}».
- Страница «I applied» показывает прошлые попытки (дата, статус, ссылка) над формой, если они есть.
- Страница отклика показывает ссылки «Previous attempt: …» и «Later attempt: …».

- [ ] **Шаг 1: Падающие тесты:** `test_inbox_marks_vacancy_already_applied` (текст пометки и ссылка);
  `test_inbox_marks_vacancy_dismissed_before`; `test_apply_requires_confirmation_when_previous_exists`
  (POST без `apply_again` → 200, отклика нет); `test_apply_again_links_previous_attempt` (с
  `apply_again=on` → новый отклик, `previous_attempt` = ранний); `test_first_apply_needs_no_confirmation`;
  `test_detail_shows_previous_and_later_links`; `test_markers_ignore_other_owners`;
  `test_inbox_num_queries` всё ещё 3 при наличии пометок; бюджет страницы отклика обновлён.
- [ ] **Шаги 2–4:** Запустить → FAIL, реализовать, `py -3.12 -m pytest -q` → PASS.
- [ ] **Шаг 5:** Коммит `feat: repost markers and confirmed repeat applications`.

### Задача 7: Документация, полный гейт, PR

- [ ] **Шаг 1:** Обновить `docs/architecture.md` и `docs/architecture.ru.md`: приложение `api/` и
  контракт приёма (ссылка на спеку), виды входящих, архив, перепосты, развёртывание в Docker +
  «рабочий контейнер собирается только из main», база разработки `tracker_dev`, и пункты в
  «Решения» для каждого `Ruling:` из ведомости этого плана.
- [ ] **Шаг 2:** `py -3.12 -m pytest --cov=accounts --cov=tracker --cov=api --cov-report=term
  --cov-fail-under=85` → проходит; `py -3.12 -m ruff check . && py -3.12 -m ruff format --check .`
  → чисто; `py -3.12 -m bandit -r accounts tracker api config -q` → без находок;
  `py -3.12 manage.py makemigrations --check --dry-run` → без изменений.
- [ ] **Шаг 3:** Ручной смоук API вместе с пользователем: пользователь создаёт свой токен в
  **рабочем** контейнере после мержа (`docker compose exec web python manage.py create_api_token
  <username>`), открывает http://localhost:8000/api/schema/swagger-ui/, отправляет одну пробную
  вакансию через «Authorize» + «Try it out», видит её во «Входящих».
- [ ] **Шаг 4:** Закоммитить документацию, запушить `feature/stage2-api`, пользователь открывает PR,
  CI зелёный, мерж, затем `docker compose up -d --build web` на `main`. Тег `v0.2.0`.
- [ ] **Шаг 5:** Обновить досье проекта: часть A этапа 2 работает; дальше — часть B в job-ai-assist
  (свой план там).
