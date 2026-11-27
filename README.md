# Keitaro wrapper

Обёртка над Admin API трекера Keitaro: **создаватор кампаний** и **редактор офферов** в существующей кампании.
Стек: FastAPI + SQLAlchemy 2 + Alembic, фронт на чистом HTML/JS (отдаётся тем же FastAPI).

## Что умеет

### 1. Создаватор кампаний (`#/new`)
Принимает название, гео (один или несколько кодов стран: `AU` или `MX, AU, RO`) и оффер (поиск с автокомплитом по имени или ID).
Создаёт в Keitaro:

| | Что | Как |
|---|---|---|
| Кампания | домен, группа, источник | `domain_id`, `group_id`, `traffic_source_id` из `.env` (на стенде: 1813 / FORTESTS 10332 / FORTESTS 836), ротация «по позиции» |
| Поток 1 | ловит всех из указанных стран → Google | `type=regular`, `position=1`, `schema=redirect`, `action_payload=https://google.com`, фильтр `country / accept / [AU, …]` |
| Поток 2 | все остальные → выбранный оффер | `type=default` (замыкающий), `schema=landings`, `offers=[{offer_id, share: 100}]` |

Перед созданием проверяется, что оффер существует. Если поток не создался, кампания удаляется, чтобы в Keitaro не оставалась недособранная кампания.

### 2. Редактор кампании (`#/campaigns` → кампания)
* показывает все потоки кампании: фильтры, редирект, офферы с долями;
* **добавить оффер**: поиск с автокомплитом, после добавления доли включённых офферов пересчитываются поровну;
* **удалить оффер**: оффер действительно убирается из потока, доли оставшихся пересчитываются;
* ручная правка долей и включение/выключение оффера; сохранить можно, только если сумма долей включённых офферов = 100%;
* после каждого изменения данные заново читаются из Keitaro, поэтому на экране всегда то, что реально сохранено;
* история изменений, сделанных через обёртку (хранится в БД).

**Как считаются доли** (как в редакторе Keitaro, `app/services/shares.py`):
100% делится поровну между *включёнными* офферами, целый остаток по +1% получают первые офферы в списке.
1 оффер → 100; 2 → 50/50; 3 → 34/33/33; 6 → 17/17/17/17/16/16. Выключенные офферы сохраняют свою долю и в сумму не входят.
В Keitaro уходит `PUT /streams/{id}` с полем `offers`, которое заменяет состав офферов целиком.

## Быстрый старт (Docker)

```bash
cp .env.example .env
# впишите KEITARO_API_KEY (админка Keitaro → кнопка «API ключ»)
docker compose up --build
```

Откройте http://localhost:8000. Swagger: http://localhost:8000/docs.

Compose поднимает Postgres, при старте контейнер приложения сам выполняет `alembic upgrade head`.

## Запуск без Docker

Нужен Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env          # впишите KEITARO_API_KEY; по умолчанию БД — SQLite-файл
alembic upgrade head          # применить миграции
uvicorn app.main:app --reload # http://localhost:8000
```

## Миграции

Миграции лежат в `migrations/versions`, URL базы берётся из `DATABASE_URL` в `.env`.

```bash
alembic upgrade head                              # применить все миграции
alembic downgrade -1                              # откатить последнюю
alembic revision --autogenerate -m "описание"     # создать миграцию после изменения app/models.py
alembic current                                   # текущая версия БД
```

В Docker то же самое: `docker compose exec app alembic upgrade head`.

Таблицы:
* `campaigns`: кампании, созданные через обёртку (ID в Keitaro, гео, ID обоих потоков);
* `operations`: журнал изменений (создание, добавление/удаление оффера, правка долей; доли до и после).

## Настройки (`.env`)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `KEITARO_URL` | `https://keitaro-for-tests.etolegko.com` | адрес Keitaro |
| `KEITARO_API_KEY` | — | ключ Admin API (заголовок `Api-Key`) |
| `KEITARO_DOMAIN_ID` | `1813` | домен новых кампаний |
| `KEITARO_GROUP_ID` | `10332` | группа (FORTESTS) |
| `KEITARO_TRAFFIC_SOURCE_ID` | `836` | источник (FORTESTS) |
| `GEO_REDIRECT_URL` | `https://google.com` | куда поток 1 отправляет гео-трафик |
| `DATABASE_URL` | `sqlite:///./keitaro_wrapper.db` | любая строка SQLAlchemy (в compose — Postgres) |

На форме создания видно, какие домен, группа и источник будут подставлены, и найдены ли они в Keitaro.

## API обёртки

| Метод | Путь | |
|---|---|---|
| GET | `/api/settings` | домен/группа/источник по умолчанию с именами из Keitaro |
| GET | `/api/countries` | допустимые коды стран |
| GET | `/api/offers?q=` | поиск офферов (каталог кешируется на 5 минут) |
| GET | `/api/campaigns` | кампании из Keitaro |
| POST | `/api/campaigns` | `{"name": "...", "geo": ["AU"], "offer_id": 3749}`: создать кампанию с двумя потоками |
| GET | `/api/campaigns/{id}` | кампания, потоки, офферы с именами и долями, история |
| POST | `/api/campaigns/{id}/streams/{stream_id}/offers` | `{"offer_id": 3717}`: добавить оффер |
| DELETE | `/api/campaigns/{id}/streams/{stream_id}/offers/{offer_id}` | удалить оффер |
| PUT | `/api/campaigns/{id}/streams/{stream_id}/offers` | `{"offers": [{"offer_id", "share", "state"}]}`: задать доли вручную |

Ошибки Keitaro пробрасываются с понятным текстом; неверный ключ возвращается как `502`.

## Тесты

```bash
pytest -q                                   # локально
docker compose run --rm app pytest -q       # в Docker
```

Тесты покрывают расчёт долей и все сценарии API с замоканным Keitaro (`respx`): какие запросы и с каким телом уходят в Keitaro, откат при ошибке, валидацию гео и сумм.

## Структура

```
app/
  main.py               FastAPI: роуты и обработка ошибок
  keitaro.py            async-клиент Keitaro Admin API (httpx)
  services/campaigns.py создание кампании, добавление/удаление офферов
  services/shares.py    расчёт долей
  models.py, db.py      SQLAlchemy-модели и сессия
  schemas.py            Pydantic-схемы и валидация
  static/               фронт (index.html, app.js, styles.css)
migrations/             Alembic
tests/
```
