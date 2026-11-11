# order-service

[![CI](https://github.com/Reevan8899/order-service/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Reevan8899/order-service/actions/workflows/ci.yml)

Практическая работа № 8. Сервис заказов проверяет пользователя по REST. [Контракт API](docs/api-contract.md)

## Локальный запуск

Нужен Python 3.10+ со SQLite 3.35+.

```sh
python -m pip install -r requirements.txt
python -m app.main
```

`HOST` и `PORT` задают адрес прослушивания. По умолчанию `127.0.0.1:5002`. `ORDER_DB_PATH` задаёт путь SQLite, по умолчанию `data/orders.sqlite3`.

## API

Локальный адрес сервиса `http://localhost:5002`. Запрос создания использует `Content-Type: application/json`. Данные и ошибки возвращаются в JSON.

| Метод | Путь | Назначение | Коды ответа |
|---|---|---|---|
| POST | `/orders` | Проверить пользователя и создать заказ | 201, 400, 404, 503 |
| GET | `/orders` | Получить список по возрастанию ID | 200 |
| GET | `/orders/{id}` | Получить заказ | 200, 404 |
| GET | `/health` | Проверить сервис и показать состояние зависимости | 200 |

POST принимает объект `{"user_id":1,"total":1500.50}`. `user_id` — положительное целое число. `total` — положительное конечное число до `999999999.99` включительно с точностью до копеек. Перед записью заказов сервис выполняет `GET /users/{user_id}` в user-service. Ответ 404 означает отсутствие пользователя, а исчерпание повторов или открытый автоматический выключатель даёт 503. Запись создаётся после успешного подтверждения пользователя.

```json
{
  "id": 1,
  "user_id": 1,
  "total": 1500.50,
  "status": "created",
  "created_at": "2026-11-11T12:05:00Z"
}
```

Список содержит массив объектов `Order`. Ошибка имеет поля `error` и `code`. Для 503 коды `user_service_unavailable` и `circuit_open` различают исчерпание попыток и блокировку вызовов. Поле `dependencies.user-service` в `/health` показывает `ok` либо `unavailable`, поле `circuit_breaker` показывает `closed`, `open` либо `half-open`. HTTP 200 от `/health` означает, что сам order-service отвечает.

## Проверки и контейнер

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check app tests
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80
docker build -t order-service .
docker run --rm -p 5002:5002 order-service
```

CI собирает и публикует образы `ghcr.io/reevan8899/order-service` с тегами `latest` и `sha-<commit>`. Для приватного пакета GHCR используется авторизация владельца.

`USER_SERVICE_URL` задаёт адрес user-service. По умолчанию `http://127.0.0.1:5001`. В Compose используется `http://user-service:5001`.

На сетевую попытку устанавливается таймаут 2 секунды. В закрытом состоянии выключателя клиент выполняет до трёх попыток с паузами 0,5 и 1 секунда. Ответ 404 обрабатывается сразу. После пяти неуспешных логических проверок выключатель открывается на 30 секунд. Затем допускается одна пробная проверка.

Для Compose разместите `user-service` и `order-service` в одной папке. Из этой папки выполните `docker compose -f order-service/docker-compose.yml up --build --wait`. Порт 80 открывает шлюз Nginx с путями `/api/users` и `/api/orders`. Порты 5001 и 5002 доступны на loopback для диагностики. Для интеграционных тестов установите `RUN_INTEGRATION=1` и выполните `python -m pytest -m integration -v` в каталоге order-service.
