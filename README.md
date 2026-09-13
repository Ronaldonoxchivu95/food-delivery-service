# Food Delivery Service

Учебный дипломный проект: production-ready микросервисное приложение
«Сервис доставки еды» — рестораны, меню, заказы, курьеры.

Состоит из двух независимых сервисов на FastAPI, каждый со своей БД,
взаимодействующих синхронно (REST) и асинхронно (события через RabbitMQ),
за общим Nginx-балансировщиком.

## Архитектура

```
                                   ┌─────────────┐
                     :80           │   clients   │
                                   └──────┬──────┘
                                          │
                                   ┌──────▼──────┐
                                   │    Nginx    │  reverse proxy,
                                   │             │  rate limiting,
                                   └──┬───────┬──┘  load balancing
                     /api/restaurants │       │ /api/auth, /api/orders,
                     /restaurant-docs │       │ /api/couriers, /order-docs
                                      │       │
                          ┌───────────▼──┐ ┌──▼────────────────┐
                          │ restaurant-  │ │   order-service    │
                          │  service     │ │  (2 replicas, LB)  │
                          │              │ │                    │
                          │ Restaurant   │ │ User / Courier     │
                          │ MenuCategory │ │ Order / OrderItem  │
                          │ MenuItem     │ │                    │
                          │ RestaurantStats│ JWT issue+verify   │
                          └──┬───────┬───┘ └──┬─────────┬──────┘
                             │       │        │         │
                     ┌───────▼─┐   ┌─▼────────▼─┐   ┌───▼──────┐
                     │ Postgres│   │  RabbitMQ   │   │ Postgres │
                     │(restau- │   │ (topic exch │   │ (order)  │
                     │  rant)  │   │ orders_events)   └──────────┘
                     └────┬────┘   └─────────────┘
                          │
                     ┌────▼────┐
                     │  Redis  │  (cache for restaurant/menu reads,
                     │         │   graceful degradation if down)
                     └─────────┘
```

Ключевые архитектурные решения:

* **База данных на сервис.** `restaurant-service` и `order-service` не имеют
  прямого доступа к чужой БД. `order-service` получает данные о ресторанах
  и меню синхронным REST-запросом (`GET /api/restaurants/{id}`,
  `POST /internal/menu-items/lookup`) к `restaurant-service`.
* **Снапшоты цен.** При создании заказа `order-service` сохраняет
  `name_snapshot`/`price_snapshot` в `OrderItem` — исторические заказы не
  меняются, даже если ресторан потом поднимет цены.
* **Асинхронная интеграция через RabbitMQ.** `order-service` публикует
  события `order.created` и `order.status_changed` в топик-обмен
  `orders_events`. `restaurant-service` подписан на них и обновляет
  агрегированную статистику (`RestaurantStats`), не блокируя ответ
  клиенту и не зная о существовании `order-service`.
* **Общий JWT-секрет.** `order-service` — единственный, кто выпускает
  токены (регистрация/логин). `restaurant-service` только проверяет
  подпись тем же `JWT_SECRET_KEY` — типичный паттерн stateless-аутентификации
  между независимыми сервисами.
* **Graceful degradation кэша.** Любая ошибка Redis перехватывается в
  `app/cache.py` и превращается в cache-miss с предупреждением в лог —
  сервис продолжает отвечать из Postgres.

## Стек

FastAPI · SQLAlchemy 2.0 (async, asyncpg) · Alembic · PostgreSQL 16 ·
RabbitMQ (aio-pika) · Redis · Nginx · Docker / docker-compose ·
Prometheus · pytest / pytest-asyncio · GitHub Actions · ruff

## Структура проекта

```
food-delivery-service/
├── docker-compose.yml
├── .env.example
├── .github/workflows/ci.yml
├── nginx/nginx.conf
├── restaurant-service/
│   ├── app/{main,config,database,models,schemas,security,cache,messaging,metrics}.py
│   ├── app/routers/{restaurants,menu,internal,health}.py
│   ├── alembic/…
│   └── tests/…
└── order-service/
    ├── app/{main,config,database,models,schemas,security,deps,messaging,restaurant_client,metrics}.py
    ├── app/routers/{auth,orders,couriers,health}.py
    ├── alembic/…
    └── tests/…
```

## Быстрый старт

```bash
cp .env.example .env
# при желании отредактируйте .env — как минимум смените JWT_SECRET_KEY
# и ADMIN_REGISTRATION_SECRET перед реальным использованием

docker compose up --build
```

После старта (миграции Alembic накатываются автоматически при запуске
каждого сервиса через `entrypoint.sh`):

| Что | URL |
|---|---|
| Nginx (единая точка входа) | http://localhost/ |
| Swagger restaurant-service | http://localhost/restaurant-docs |
| Swagger order-service | http://localhost/order-docs |
| RabbitMQ management UI | http://localhost:15672 (guest/guest) |
| Метрики restaurant-service | http://localhost/restaurant-metrics |
| Метрики order-service | http://localhost/order-metrics |

### Пример сценария

```bash
# 1. Регистрация администратора (ADMIN_REGISTRATION_SECRET из .env)
curl -X POST http://localhost/api/auth/register -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password123","full_name":"Admin","admin_secret":"change-me-to-a-long-random-secret"}'

# 2. Логин, получаем access_token
TOKEN=$(curl -s -X POST http://localhost/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 3. Создаём ресторан и позицию меню
RID=$(curl -s -X POST http://localhost/api/restaurants -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"Pizza Place","address":"1 Main St"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -X POST http://localhost/api/restaurants/$RID/menu-items -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"Margherita","price":8.5}'

# 4. Обычный пользователь оформляет заказ (после своей регистрации/логина)
curl -X POST http://localhost/api/orders -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"restaurant_id\": $RID, \"items\":[{\"menu_item_id\":1,\"quantity\":2}]}"
```

## Тесты

```bash
cd restaurant-service && pip install -r requirements-dev.txt && pytest -v
cd order-service && pip install -r requirements-dev.txt && pytest -v
```

Тесты используют SQLite in-memory вместо Postgres и мокируют внешние
зависимости (RabbitMQ-консьюмер/паблишер, HTTP-вызов к restaurant-service),
поэтому запускаются без docker-compose. Всего собрано ~36 тестов
(unit + integration) в обоих сервисах.

## События RabbitMQ

| routing key | издатель | подписчик | payload |
|---|---|---|---|
| `order.created` | order-service | restaurant-service | `order_id, user_id, restaurant_id, total_price` |
| `order.status_changed` | order-service | restaurant-service | `order_id, status, courier_id` |

Обмен: `orders_events` (topic, durable). Очередь потребителя:
`restaurant_service.order_events`, биндинг `order.*`.

## Кэширование

`GET /api/restaurants`, `GET /api/restaurants/{id}` и
`GET /api/restaurants/{id}/menu` кэшируются в Redis (TTL из
`CACHE_TTL_SECONDS`). Кэш точечно инвалидируется при создании/изменении
ресторана, категории или позиции меню. При недоступности Redis сервис
не падает — просто перестаёт кэшировать (см. `app/cache.py`).

## Нагрузка/отказоустойчивость на уровне Nginx

* `order-service` поднят в двух репликах (`order-service-1/2`), Nginx
  балансирует между ними (`least_conn`).
* `limit_req_zone` — рейт-лимит 10 запросов/сек на IP с burst=20.
* Проксируются заголовки `Host`, `X-Real-IP`, `X-Forwarded-For`,
  `X-Forwarded-Proto`.

## Мониторинг

Оба сервиса отдают `/metrics` в формате Prometheus:

* `http_requests_total{method,endpoint,status_code}`
* `http_request_duration_seconds{method,endpoint}`
* `restaurants_created_total` / `orders_created_total{restaurant_id}`
* `order_events_consumed_total{event_type}` / `order_events_published_total{event_type}`

`/health` в каждом сервисе проверяет подключение к БД (и Redis — для
restaurant-service) и возвращает `ok`/`degraded`.

## Что не входит в объём (согласно заданию)

Kafka, Kubernetes, service mesh, Saga/CQRS и деплой в облако сознательно
не реализованы — задание отмечает их как необязательные. Бонусные пункты
(Grafana-дашборд, SSL, blue-green/canary, WebSocket, облачный деплой) также
не реализованы в этой версии, чтобы полностью сфокусироваться на
обязательных критериях.

## Известное ограничение среды разработки

Эта версия кода писалась и статически проверялась (компиляция всех
`.py`-файлов, валидация `docker-compose.yml` через `docker compose config`,
ручная сверка логики) в песочнице без доступа к PyPI/Docker Hub, поэтому
`pytest` и `docker compose up` здесь не выполнялись end-to-end. Перед
защитой обязательно прогоните `docker compose up --build` и тесты локально
или в CI (GitHub Actions это сделает автоматически при пуше).
#   -  
 