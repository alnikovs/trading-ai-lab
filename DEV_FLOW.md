# Development Flow

## Конфигурация

### Структура конфигов

**`.env`** (локально, в `.gitignore`)
- Содержит все секреты и API ключи
- Расположен в корне проекта: `C:\Bot\trading-ai-lab\.env`
- Пример переменных:
  - `OPENAI_API_KEY=...`
  - `CURSOR_API_KEY=...` (обязательно для работы с Cursor Cloud Agent API)
  - `CURSOR_API_BASE=https://api.cursor.com` (по умолчанию, опционально)
  - `CURSOR_REPOSITORY=...` (URL GitHub репозитория проекта, обязательно для `/dev/agents`)
  - `CURSOR_BASE_REF=main` (по умолчанию, опционально)
  - `CURSOR_WEBHOOK_URL=...` (полный URL до `/cursor/webhook`, опционально — без него Dev Agent работает, но не присылает статусы)
  - `HYPERLIQUID_API_KEY=...`, `HYPERLIQUID_API_SECRET=...`
  - `ALLORA_API_KEY=...`
  - `BOT_ENV=dev`, `BOT_LOG_LEVEL=INFO`
  - `TELEGRAM_BOT_TOKEN=...` (опционально, для Telegram-бота)
  - `TELEGRAM_ALLOWED_USER_ID=...` (опционально, для ограничения доступа)
  - `ORCHESTRATOR_BASE_URL=http://localhost:8000` (опционально, для Telegram-бота)

**`.env.example`** (опционально, шаблон)
- Создается вручную как пример структуры
- Содержит только названия переменных без реальных значений
- Не попадает в `.gitignore`

**`orchestrator/config.py`**
- Единая точка доступа ко всем ключам и настройкам
- Читает переменные из `.env` через `os.getenv()`
- Предоставляет классы: `HyperliquidConfig`, `AlloraConfig`, `OpenAIConfig`, `BotConfig`, `CursorConfig`, `TelegramConfig`, `OrchestratorConfig`
- Все секреты должны браться только отсюда, не напрямую из файлов

**`orchestrator/config.json`** (несекретные настройки)
- Содержит только публичные параметры (например, `model`)
- Не содержит API ключей или секретов
- Пример: `{"model": "gpt-4.1-mini"}`
- В `.gitignore` (локальный файл)

### Принципы

- Все секреты → `.env` → `orchestrator/config.py` → использование в коде
- Несекретные настройки → `config.json`
- Никаких захардкоженных ключей в коде
- Никаких секретов в файлах, которые попадают в репозиторий

## Запуск проекта

```bash
python -m orchestrator.main
```

При старте логируется:
- `ENV` — текущее окружение (dev/prod)
- `LOG_LEVEL` — уровень логирования (INFO/DEBUG и т.д.)
- `OpenAI API key` — превью первых 4 символов ключа (для проверки, что ключ загружен)

Сервер FastAPI запускается на `http://localhost:8000`

### Доступные эндпоинты

- `GET /health` — проверка состояния сервиса
- `GET /config/summary` — сводка конфигурации (без секретов)
- `POST /chat` — основной эндпоинт для взаимодействия с ChatGPT
- `GET /tasks`, `POST /tasks/add`, `POST /tasks/update` — управление задачами
- `GET /for-cursor/commands` — получение очереди команд для Cursor
- `POST /from-cursor/result` — получение результатов выполнения от Cursor
- `POST /dev/agents` — создание нового Cursor Cloud Agent
- `GET /dev/agents/{agent_id}` — получение статуса Cursor Cloud Agent

### Структура кода

- `orchestrator/main.py` — главный файл приложения, регистрирует routers
- `orchestrator/routers/` — модули с маршрутами (например, `status.py` для health/config endpoints)
- `orchestrator/schemas/` — Pydantic-модели для валидации запросов/ответов
- `orchestrator/config.py` — единая точка доступа к конфигурации

## Workflow с Cursor

1. **Открыть проект в Cursor**
   - Открыть папку `C:\Bot\trading-ai-lab` в Cursor

2. **Получить задачу**
   - Через ChatGPT (оркестратор) или напрямую описать задачу в Cursor

3. **Внести изменения**
   - Редактировать код через Cursor
   - Использовать AI-помощь для генерации/изменения кода

4. **Проверить запуск**
   ```bash
   python -m orchestrator.main
   ```
   - Убедиться, что сервер стартует без ошибок
   - Проверить логи (ENV, LOG_LEVEL, превью ключа)

5. **Commit & Push**
   - Сделать коммит с понятным сообщением
   - Запушить в ветку `main`
   - Убедиться, что `.env` и `config.json` не попадают в коммит (они в `.gitignore`)

## Telegram bot

Telegram-бот предоставляет интерфейс к оркестратору через Telegram.

### Настройка

В `.env` файле:
- `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather (обязательно)
- `TELEGRAM_ALLOWED_USER_ID` — ID пользователя Telegram для ограничения доступа (опционально, если не задан — бот открыт для всех)
- `ORCHESTRATOR_BASE_URL` — URL оркестратора (по умолчанию `http://localhost:8000`)

### Запуск

```bash
python -m orchestrator.telegram_bot
```

### Функциональность

- Бот пересылает сообщения пользователя на эндпоинт `/chat` оркестратора
- Возвращает ответ от оркестратора обратно пользователю в Telegram
- Команда `/start` — приветственное сообщение
- Если `TELEGRAM_ALLOWED_USER_ID` задан — только этот пользователь может использовать бота

**Важно:** Перед запуском бота убедись, что оркестратор запущен (`python -m orchestrator.main`).

## Pipeline: Telegram → Orchestrator → OpenAI → Cursor → Orchestrator → Telegram

Полная цепочка взаимодействия между компонентами:

### Шаг 1: Пользователь отправляет сообщение в Telegram
- Пользователь пишет сообщение боту в Telegram
- Telegram-бот получает сообщение и отправляет его на `/chat` оркестратора

### Шаг 2: Оркестратор анализирует сообщение
- Оркестратор проверяет, является ли сообщение техническим заданием
- Ключевые слова: "создай файл", "добавь эндпоинт", "измени код", "создай router", "создай модель" и т.д.

### Шаг 3a: Если техническое задание
- Оркестратор создает команду с UUID и добавляет её в очередь `pending_cursor_commands`
- Возвращает пользователю: "Задача отправлена Cursor, ждем результата…"

### Шаг 3b: Если обычное сообщение
- Оркестратор отправляет запрос в OpenAI ChatGPT
- Получает ответ и возвращает его пользователю в Telegram

### Шаг 4: Cursor запрашивает команды
- Cursor runner периодически опрашивает `/for-cursor/commands`
- Оркестратор возвращает все команды из очереди и очищает её
- Формат: `{"commands": [{"id": "...", "prompt": "...", "user_id": "...", "timestamp": "..."}]}`

### Шаг 5: Cursor выполняет команду
- Cursor получает команду и выполняет её через Cloud Agent API
- Результат выполнения (успех или ошибка) отправляется обратно в оркестратор

### Шаг 6: Оркестратор получает результат
- Cursor отправляет результат на `/from-cursor/result`
- Оркестратор формирует отчет:
  - ✅ Успех: сообщение, комментарии, diff изменений
  - ❌ Ошибка: описание ошибки
- Оркестратор отправляет отчет пользователю через Telegram Bot API

### Эндпоинты для Cursor

**`GET /for-cursor/commands`**
- Возвращает очередь команд для Cursor
- Формат ответа: `{"commands": [...]}`
- После возврата очередь очищается
- Каждая команда содержит: `id`, `prompt`, `user_id`, `timestamp`

**`POST /from-cursor/result`**
- Принимает результат выполнения команды от Cursor
- Формат запроса:
  ```json
  {
    "command_id": "...",
    "status": "ok" | "error",
    "result": {
      "diff": "...",
      "notes": "...",
      "message": "...",
      "error": "..." (если status="error")
    }
  }
  ```
- Находит соответствующую команду по `command_id`
- Формирует отчет и отправляет его пользователю через Telegram

## Cursor Cloud Agent API

Модуль `orchestrator/cursor_client.py` предоставляет функции для работы с Cursor Cloud Agent API через эндпоинты `/dev/agents`.

### Переменные окружения для Cursor API

Для работы с Cursor Cloud Agent API требуются следующие переменные в `.env`:

- `CURSOR_API_KEY` — API ключ Cursor (обязательно)
- `CURSOR_API_BASE` — базовый URL API (по умолчанию `https://api.cursor.com`, опционально)
- `CURSOR_REPOSITORY` — URL GitHub репозитория проекта, например `https://github.com/username/repo` (обязательно)
- `CURSOR_BASE_REF` — базовая ветка для создания PR (по умолчанию `main`, опционально)
- `CURSOR_WEBHOOK_URL` — полный URL до эндпоинта `/cursor/webhook` (опционально)
  - Пример: `https://example.ngrok-free.dev/cursor/webhook` (для локальной разработки через ngrok)
  - Без этой переменной Dev Agent будет работать, но не будет присылать статусы о выполнении работы

### Использование эндпоинтов `/dev/agents`

**Создание нового Cloud Agent:**

```bash
# POST /dev/agents
curl -X POST http://localhost:8000/dev/agents \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Добавить новый эндпоинт для получения баланса",
    "auto_create_pr": true,
    "branch_name": "feature/balance-endpoint"
  }'
```

Параметры запроса:
- `task` (обязательно) — текст задания для Cloud Agent
- `auto_create_pr` (опционально, по умолчанию `true`) — автоматически создавать Pull Request
- `branch_name` (опционально) — имя ветки для создания изменений

Ответ:
```json
{
  "agent_id": "agent_123...",
  "status": "running",
  "url": "https://cursor.sh/agents/agent_123...",
  "pr_url": "https://github.com/username/repo/pull/123",
  "branch_name": "feature/balance-endpoint"
}
```

**Получение статуса Cloud Agent:**

```bash
# GET /dev/agents/{agent_id}
curl http://localhost:8000/dev/agents/agent_123...
```

Ответ:
```json
{
  "id": "agent_123...",
  "status": "completed",
  "url": "https://cursor.sh/agents/agent_123...",
  "pr_url": "https://github.com/username/repo/pull/123",
  "summary": "Successfully added balance endpoint"
}
```

### Тестирование локально

1. Убедитесь, что все необходимые переменные окружения настроены в `.env`
2. Запустите оркестратор:
   ```bash
   python -m orchestrator.main
   ```
3. Создайте тестовый Cloud Agent:
   ```bash
   curl -X POST http://localhost:8000/dev/agents \
     -H "Content-Type: application/json" \
     -d '{"task": "Test task"}'
   ```
4. Проверьте статус используя `agent_id` из ответа:
   ```bash
   curl http://localhost:8000/dev/agents/{agent_id}
   ```

### Обработка ошибок

Эндпоинты корректно обрабатывают ошибки Cursor API:
- HTTP 4xx (клиентские ошибки) — возвращают соответствующий статус код с описанием ошибки
- HTTP 5xx (серверные ошибки) — возвращают 500 с деталями ошибки
- Ошибки конфигурации (отсутствие API ключа или репозитория) — возвращают 500 с описанием проблемы

## LLM Router Architecture

Централизованный LLM Router (`orchestrator/llm_router.py`) обрабатывает все входящие сообщения от разных источников и принимает решения о дальнейших действиях.

### Архитектура потока сообщений

**Полный цикл взаимодействия:**

```
1. Пользователь в Telegram → Telegram Webhook → LLM Router
2. LLM Router → start_dev_agent (с dev_task)
3. Orchestrator → Cursor API (create_cursor_agent) + DevAgentStore.register(agent_id, chat_id)
4. Cursor работает над задачей → /cursor/webhook (с agentId и event)
5. Orchestrator → DevAgentStore.get(agent_id) → chat_id
6. Cursor Webhook → LLM Router → notify_user (с summary и PR link)
7. Orchestrator → send_telegram_message(chat_id, reply_text) → Пользователь получает отчёт
```

**Упрощённая схема:**

```
Telegram User → Telegram Webhook → LLM Router → Actions (Telegram / Cursor)
Cursor Webhook → DevAgentStore → LLM Router → Actions (Telegram / noop)
```

Все сообщения (от пользователя через Telegram и от Cursor через webhook) сначала обрабатываются централизованным LLM-роутером, и только потом при необходимости что-то отправляется пользователю в Telegram или в Cursor.

### Модели данных

**IncomingMessage** — входящее сообщение:
- `source`: `"telegram"` | `"cursor"` | `"system"` — источник сообщения
- `chat_id`: опциональный ID чата (для Telegram)
- `text`: опциональный текст сообщения
- `raw_payload`: опциональный полный payload от источника
- `cursor_event_type`: опциональный тип события от Cursor
- `cursor_agent_id`: опциональный ID агента Cursor

**LlmRouterAction** — решение роутера:
- `action`: тип действия (`"reply_only"`, `"start_dev_agent"`, `"check_dev_status"`, `"notify_user"`, `"noop"`, `"debug_raw"`)
- `reply_text`: опциональный текст для отправки пользователю
- `dev_task`: опциональное описание задачи для Cursor Cloud Agent
- `dev_agent_id`: опциональный ID агента (для проверки статуса)
- `importance`: опциональный уровень важности (`"info"`, `"warning"`, `"error"`, `"debug"`)
- `extra`: дополнительные данные

### Типы действий

- **`reply_only`**: Просто ответить пользователю текстом (`reply_text`)
- **`start_dev_agent`**: Запустить Cloud Agent в Cursor с описанием задачи (`dev_task`)
- **`check_dev_status`**: Запросить статус Dev Agent (резервировано для будущей реализации)
- **`notify_user`**: Важное событие от Cursor, которое нужно отправить пользователю в Telegram
- **`noop`**: Ничего не делать, игнорировать событие
- **`debug_raw`**: Отправить технический debug-ответ в Telegram

### Примеры запросов и ответов

**1. Запрос от Telegram:**

```json
{
  "source": "telegram",
  "chat_id": "123456789",
  "text": "Создай новый эндпоинт /balance для получения баланса пользователя"
}
```

**Ожидаемый JSON от LLM:**

```json
{
  "action": "start_dev_agent",
  "reply_text": "Создаю Dev Agent для выполнения задачи...",
  "dev_task": "Add a new endpoint /balance to get user balance. Create model BalanceResponse with fields: user_id, balance_usd, balance_btc.",
  "importance": "info"
}
```

**2. Webhook от Cursor:**

```json
{
  "source": "cursor",
  "cursor_event_type": "agent.completed",
  "cursor_agent_id": "agent_123...",
  "raw_payload": {
    "event": "agent.completed",
    "agentId": "agent_123...",
    "status": "completed",
    "prUrl": "https://github.com/user/repo/pull/123",
    "summary": "Successfully added balance endpoint"
  }
}
```

**Ожидаемый JSON от LLM:**

```json
{
  "action": "notify_user",
  "reply_text": "✅ Dev Agent завершил работу. PR: https://github.com/user/repo/pull/123",
  "importance": "info"
}
```

### Эндпоинты

**`POST /telegram/webhook`** — webhook от Telegram
- Принимает сообщения от пользователей
- Отправляет в LLM Router
- Выполняет действия: отправляет ответы в Telegram или запускает Dev Agent

**`POST /cursor/webhook`** — webhook от Cursor
- Принимает события от Cursor Cloud Agent API (с `agentId` и `event`)
- Использует `DevAgentStore` для поиска `chat_id` по `agent_id`
- Отправляет в LLM Router с найденным `chat_id` (если известен)
- Выполняет действия: уведомляет пользователя в Telegram (если `chat_id` найден) или логирует события
- Логирует предупреждения, если `agent_id` неизвестен или `chat_id` не найден

**Dev Agent Store** (`orchestrator/dev_agent_store.py`) — in-memory хранилище для маппинга `agent_id -> chat_id`:
- Хранит связь между Dev Agent (Cursor `agent_id`) и Telegram `chat_id`
- Регистрируется при создании Dev Agent в `handle_telegram_message`
- Используется в `/cursor/webhook` для поиска `chat_id` по `agent_id` при отправке уведомлений
- Потокобезопасно (использует threading.Lock)
- Живёт в памяти процесса (не сохраняется на диск)

### Полный цикл работы Dev Agent

**1. Пользователь запрашивает задачу в Telegram:**
- Пользователь отправляет сообщение: "Создай новый эндпоинт /balance для получения баланса"
- `handle_telegram_message()` создаёт `IncomingMessage(source="telegram", chat_id=..., text=...)`
- Отправляется в `llm_router.handle_message()`

**2. LLM Router принимает решение:**
- LLM анализирует запрос и решает запустить Dev Agent
- Возвращает `LlmRouterAction(action="start_dev_agent", dev_task="Add a new endpoint /balance...", reply_text="Создаю Dev Agent...")`

**3. Orchestrator создаёт Dev Agent:**
- Вызывается `create_cursor_agent(task_text=action.dev_task)`
- Если задана `CURSOR_WEBHOOK_URL`, передаётся `webhook.url` в payload для Cursor API
- Получается `result.id` (agent_id)
- Регистрируется связь: `DevAgentStore.register(agent_id=result.id, chat_id=chat_id, original_text=text, dev_task=action.dev_task)`
- Пользователю отправляется подтверждение: "✅ Запустил Dev Agent. ID: agent_123..."

**4. Cursor работает над задачей:**
- Cursor Cloud Agent выполняет задачу
- Создаёт изменения в репозитории
- Создаёт Pull Request (если `auto_create_pr=True`)

**5. Cursor отправляет webhook (если задан CURSOR_WEBHOOK_URL):**
- После завершения работы Dev Agent Cursor отправляет событие на указанный `CURSOR_WEBHOOK_URL` (эндпоинт `/cursor/webhook`):
  ```json
  {
    "event": "agent.completed",
    "agentId": "agent_123...",
    "status": "completed",
    "prUrl": "https://github.com/user/repo/pull/123",
    "summary": "Successfully added balance endpoint"
  }
  ```
- Если `CURSOR_WEBHOOK_URL` не задан, webhook не отправляется (Dev Agent работает, но статусы не приходят)

**6. Orchestrator обрабатывает webhook:**
- Извлекает `agent_id` из payload
- Использует `DevAgentStore.get(agent_id)` для поиска `chat_id`
- Создаёт `IncomingMessage(source="cursor", chat_id=chat_id, ...)`
- Отправляет в `llm_router.handle_message()`

**7. LLM Router формирует отчёт:**
- LLM анализирует событие от Cursor
- Решает уведомить пользователя
- Возвращает `LlmRouterAction(action="notify_user", reply_text="✅ Dev Agent завершил работу. PR: https://...", importance="info")`

**8. Пользователь получает отчёт в Telegram:**
- Вызывается `send_telegram_message(chat_id, action.reply_text)`
- Пользователь видит уведомление с результатами работы Dev Agent

### Интеграция с LLM

LLM Router использует существующую интеграцию с OpenAI:
- Конфигурация из `config.json` (модель и другие параметры)
- API ключ из `.env` через `OpenAIConfig`
- История сообщений из `memory/messages_{chat_id}.jsonl`
- Контекст проекта: AI Contract, Project Summary, Tasks, Recent Results

### Dev Agent Store

Модуль `orchestrator/dev_agent_store.py` предоставляет in-memory хранилище для связи Dev Agent ↔ Telegram:
- **Хранит:** `agent_id`, `chat_id`, `original_text`, `dev_task`, `created_at`
- **Регистрируется:** при создании Dev Agent в `handle_telegram_message()`
- **Используется:** в `/cursor/webhook` для поиска `chat_id` по `agent_id`
- **Потокобезопасно:** использует `threading.Lock` для синхронизации
- **В памяти процесса:** не сохраняется на диск (теряется при перезапуске)

## Важные замечания

- При добавлении новых API ключей: добавить в `.env` и создать соответствующий класс в `orchestrator/config.py`
- При изменении несекретных настроек: редактировать `config.json`
- Все секреты должны быть только в `.env`, никогда не коммитить их

