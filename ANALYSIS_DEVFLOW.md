# Анализ DevFlow и Dev Agent в trading-ai-lab

## 📁 Список файлов, реализующих DevFlow / Dev Agent

### Основные модули:

1. **`orchestrator/telegram_bot.py`**
   - Обработка команд Telegram (`/devflow_simple_ma`, ответы "да/нет")
   - Отправка сообщений пользователю в Telegram
   - Интеграция с DevFlow и Dev Agent

2. **`orchestrator/dev_flow.py`**
   - Управление состоянием DevFlow (in-memory)
   - Функции для работы с DevFlow: `start_flow()`, `update_flow()`, `finish_flow()`, `add_summary()`, `get_flow()`, `find_flow_by_agent_id()`

3. **`orchestrator/cursor_client.py`**
   - Формирование запросов к Cursor Cloud Agent API
   - Создание агентов: `create_cursor_agent()`
   - Получение статуса: `get_cursor_agent_status()`

4. **`orchestrator/routers/cursor_webhook.py`**
   - Обработка вебхука от Cursor: `cursor_webhook()`
   - Обработка завершения шагов DevFlow: `_handle_devflow_step_completion()`

5. **`orchestrator/dev_agent_store.py`**
   - In-memory хранилище связи `agent_id ↔ chat_id`
   - Класс `DevAgentStore` с методами `register()`, `get()`

6. **`orchestrator/llm_router.py`**
   - Централизованная обработка сообщений от разных источников
   - Функция `handle_message()` - принимает решения о действиях
   - Модели: `IncomingMessage`, `LlmRouterAction`

7. **`orchestrator/main.py`**
   - Точка входа для Telegram webhook: `telegram_webhook()` (строка 54)
   - Регистрация роутеров, включая `cursor_webhook_router`

---

## 🔧 Функции по категориям

### 1. Принимают апдейты Telegram:

**`orchestrator/main.py`:**
- `telegram_webhook()` (строка 54) - эндпоинт `POST /telegram/webhook`
  - Извлекает `chat_id` и `text` из payload
  - Вызывает `handle_telegram_update()`

**`orchestrator/telegram_bot.py`:**
- `handle_telegram_update()` (строка 158) - основная функция обработки Telegram-сообщений
  - Обрабатывает команды: `/start`, `/help`, `/status`, `/devflow_simple_ma`, `ping`, `echo`
  - Обрабатывает ответы "да/нет" для DevFlow
  - Для остальных сообщений создаёт `IncomingMessage` и отправляет в `llm_router.handle_message()`

---

### 2. Формируют запросы к Cursor:

**`orchestrator/cursor_client.py`:**
- `create_cursor_agent()` (строка 22)
  - Принимает: `task_text`, `auto_create_pr`, `branch_name`
  - Формирует payload с промптом, репозиторием, webhook URL
  - Отправляет `POST {base_url}/v0/agents` к Cursor API
  - Возвращает `CursorAgentCreateResult` с `id`, `status`, `url`, `pr_url`, `branch_name`

**`orchestrator/telegram_bot.py`:**
- `_handle_devflow_simple_ma_start()` (строка 313)
  - Создаёт задачу для шага 1 DevFlow
  - Вызывает `create_cursor_agent(task_text=task_text_step1)`
  - Регистрирует агента в `DevAgentStore`
  
- `_handle_devflow_confirmation_yes()` (строка 368)
  - Создаёт задачи для шагов 2 и 3 DevFlow
  - Вызывает `create_cursor_agent()` для каждого шага
  - Регистрирует агентов в `DevAgentStore`

- В блоке обработки `action.action == "start_dev_agent"` (строка 260)
  - Вызывает `create_cursor_agent(task_text=action.dev_task)`
  - Регистрирует агента в `DevAgentStore`

---

### 3. Обрабатывают ответы от Cursor:

**`orchestrator/routers/cursor_webhook.py`:**
- `cursor_webhook()` (строка 16) - эндпоинт `POST /cursor/webhook`
  - Парсит JSON payload от Cursor
  - Фильтрует только финальные события (`statusChange` с `FINISHED`/`FAILED`/`ERROR`)
  - Извлекает `agent_id`, `status`, `summary`, `pr_url`
  - Проверяет, есть ли активный DevFlow для этого агента
  - Если DevFlow активен → вызывает `_handle_devflow_step_completion()`
  - Если DevFlow нет → создаёт `IncomingMessage` и отправляет в `llm_router.handle_message()`

- `_handle_devflow_step_completion()` (строка 131)
  - Обрабатывает завершение шага DevFlow
  - Добавляет summary через `add_summary()`
  - Отправляет сообщение пользователю с результатами шага
  - Для шагов 1-2: спрашивает "Продолжить к следующему шагу? (да/нет)"
  - Для шага 3: отправляет финальное сообщение и завершает DevFlow через `finish_flow()`

**`orchestrator/llm_router.py`:**
- `handle_message()` (строка 42)
  - При `source="cursor"` анализирует событие от Cursor
  - Решает, нужно ли уведомить пользователя (`notify_user`) или игнорировать (`noop`)
  - Возвращает `LlmRouterAction` с типом действия

---

### 4. Отправляют сообщения пользователю в Telegram:

**`orchestrator/telegram_bot.py`:**
- `send_telegram_message()` (строка 22)
  - Основная функция отправки сообщений в Telegram
  - Разбивает длинные сообщения (>4096 символов) на части
  - Использует Telegram Bot API: `POST https://api.telegram.org/bot{token}/sendMessage`
  - Обрабатывает ошибки и повторные попытки

- `_handle_devflow_simple_ma_start()` (строка 313)
  - Отправляет: "🚀 Запустил Dev Flow для simple_ma стратегии (Шаг 1)..."

- `_handle_devflow_confirmation_yes()` (строка 368)
  - Отправляет: "✅ Продолжаю к шагу 2/3..."

- `_handle_devflow_confirmation_no()` (строка 455)
  - Отправляет: "🛑 Dev Flow остановлен. Выполненные шаги:..."

- В блоке обработки `action.action == "start_dev_agent"` (строка 260)
  - Отправляет: "✅ Запустил Dev Agent для этой задачи. ID: ..."

**`orchestrator/routers/cursor_webhook.py`:**
- `_handle_devflow_step_completion()` (строка 131)
  - Отправляет результаты выполнения шага
  - Для шагов 1-2: "✅ Шаг N выполнен: {summary}\n\nПродолжить к шагу N+1? (да/нет)"
  - Для шага 3: "🎉 Dev flow завершён! {summary всех шагов}"

- В `cursor_webhook()` (строка 107)
  - Если `action.action in ("notify_user", "reply_only", "debug_raw")` → вызывает `send_telegram_message()`

---

## 🔄 Жизненный цикл DevFlow-сессии (команда `/devflow_simple_ma`)

### Шаг 0: Пользователь отправляет команду

1. **Пользователь в Telegram** → отправляет `/devflow_simple_ma`
2. **Telegram** → отправляет webhook на `POST /telegram/webhook` (в `main.py`)
3. **`main.py::telegram_webhook()`** → извлекает `chat_id` и `text`, вызывает `handle_telegram_update()`

### Шаг 1: Обработка команды и запуск первого агента

4. **`telegram_bot.py::handle_telegram_update()`** (строка 218)
   - Обнаруживает команду `/devflow_simple_ma`
   - Вызывает `_handle_devflow_simple_ma_start(app, chat_id)`

5. **`telegram_bot.py::_handle_devflow_simple_ma_start()`** (строка 313)
   - Проверяет, нет ли активного DevFlow для этого `chat_id` (через `get_flow()`)
   - Создаёт новый DevFlow через `start_flow(chat_id)` → состояние: `step=1`, `status="active"`
   - Формирует `task_text_step1` с описанием задач для шага 1
   - Вызывает `create_cursor_agent(task_text=task_text_step1)`

6. **`cursor_client.py::create_cursor_agent()`** (строка 22)
   - Формирует payload с промптом, репозиторием, webhook URL (если задан `CURSOR_WEBHOOK_URL`)
   - Отправляет `POST https://api.cursor.com/v0/agents` к Cursor API
   - Получает ответ с `agent_id`, `status`, `url`
   - Возвращает `CursorAgentCreateResult`

7. **`telegram_bot.py::_handle_devflow_simple_ma_start()`** (продолжение)
   - Регистрирует агента в `DevAgentStore`: `store.register(agent_id, chat_id, ...)`
   - Обновляет DevFlow: `update_flow(chat_id, last_agent_id=result.id)`
   - Отправляет пользователю: "🚀 Запустил Dev Flow для simple_ma стратегии (Шаг 1). Agent ID: ... Жду завершения шага 1..."

### Шаг 2: Cursor работает над задачей

8. **Cursor Cloud Agent** → выполняет задачу (читает файл, вносит изменения, создаёт коммит/PR)

### Шаг 3: Cursor отправляет webhook о завершении

9. **Cursor API** → отправляет webhook на `POST /cursor/webhook` (если задан `CURSOR_WEBHOOK_URL`)
   - Payload содержит: `event="statusChange"`, `status="FINISHED"`, `agentId`, `summary`, `prUrl`

10. **`cursor_webhook.py::cursor_webhook()`** (строка 16)
    - Парсит payload, проверяет, что это финальное событие
    - Извлекает `agent_id` из payload
    - Использует `DevAgentStore.get(agent_id)` → получает `chat_id`
    - Вызывает `find_flow_by_agent_id(agent_id, store)` → получает активный DevFlow
    - Если DevFlow найден и активен → вызывает `_handle_devflow_step_completion()`

11. **`cursor_webhook.py::_handle_devflow_step_completion()`** (строка 131)
    - Извлекает `summary` и `pr_url` из payload
    - Вызывает `add_summary(chat_id, summary_text)` → добавляет summary в DevFlow
    - Для шага 1:
      - Отправляет пользователю: "✅ Шаг 1 выполнен: {summary}\n\nПродолжить к шагу 2? (да/нет)"
      - Вызывает `update_flow(chat_id, awaiting_confirmation=True)`

### Шаг 4: Пользователь подтверждает продолжение

12. **Пользователь в Telegram** → отвечает "да"

13. **`telegram_bot.py::handle_telegram_update()`** (строка 223)
    - Обнаруживает ответ "да"
    - Вызывает `_handle_devflow_confirmation_yes(app, chat_id)`

14. **`telegram_bot.py::_handle_devflow_confirmation_yes()`** (строка 368)
    - Получает DevFlow через `get_flow(chat_id)`
    - Проверяет, что `flow.awaiting_confirmation == True` и `flow.status == "active"`
    - Если `flow.step == 1`:
      - Формирует `task_text_step2` с описанием задач для шага 2
      - Вызывает `create_cursor_agent(task_text=task_text_step2)`
      - Регистрирует агента в `DevAgentStore`
      - Обновляет DevFlow: `update_flow(chat_id, step=2, last_agent_id=result.id, awaiting_confirmation=False)`
      - Отправляет пользователю: "✅ Продолжаю к шагу 2. Agent ID: ... Жду завершения шага 2..."

### Шаг 5: Повторение для шага 2

15. **Cursor работает** → выполняет задачи шага 2
16. **Cursor отправляет webhook** → `POST /cursor/webhook` с результатами шага 2
17. **`cursor_webhook.py::_handle_devflow_step_completion()`**
    - Для шага 2:
      - Отправляет: "✅ Шаг 2 выполнен: {summary}\n\nПерейти к шагу 3? (да/нет)"
      - Устанавливает `awaiting_confirmation=True`

### Шаг 6: Пользователь подтверждает шаг 3

18. **Пользователь** → отвечает "да"
19. **`telegram_bot.py::_handle_devflow_confirmation_yes()`**
    - Если `flow.step == 2`:
      - Формирует `task_text_step3`
      - Создаёт агента для шага 3
      - Обновляет DevFlow: `step=3`
      - Отправляет: "✅ Продолжаю к шагу 3 (финальному)..."

### Шаг 7: Завершение DevFlow

20. **Cursor работает** → выполняет задачи шага 3
21. **Cursor отправляет webhook** → результаты шага 3
22. **`cursor_webhook.py::_handle_devflow_step_completion()`**
    - Для шага 3:
      - Формирует итоговое сообщение со всеми summaries
      - Отправляет: "🎉 Dev flow завершён! {PR link}\n\nКраткий итог:\nШаг 1: ...\nШаг 2: ...\nШаг 3: ..."
      - Вызывает `finish_flow(chat_id)` → удаляет DevFlow из памяти

---

## 📊 Схема потока данных

```
Telegram User
    ↓
POST /telegram/webhook (main.py)
    ↓
handle_telegram_update() (telegram_bot.py)
    ↓
_handle_devflow_simple_ma_start() (telegram_bot.py)
    ↓
start_flow() (dev_flow.py) → создаёт DevFlowState
    ↓
create_cursor_agent() (cursor_client.py)
    ↓
POST https://api.cursor.com/v0/agents
    ↓
Cursor Cloud Agent работает...
    ↓
POST /cursor/webhook (cursor_webhook.py)
    ↓
_handle_devflow_step_completion() (cursor_webhook.py)
    ↓
add_summary() (dev_flow.py) → сохраняет summary
    ↓
send_telegram_message() (telegram_bot.py)
    ↓
Telegram User видит результат
```

---

## 🔑 Ключевые структуры данных

### DevFlowState (`dev_flow.py`, строка 12):
```python
- chat_id: str
- step: int (1, 2, 3)
- awaiting_confirmation: bool
- status: "active" | "finished"
- last_agent_id: Optional[str]
- summaries: list[str]
```

### DevAgentRecord (`dev_agent_store.py`, строка 11):
```python
- agent_id: str
- chat_id: str
- original_text: str
- dev_task: Optional[str]
- created_at: float
```

### IncomingMessage (`llm_router.py`, строка 14):
```python
- source: "telegram" | "cursor" | "system"
- chat_id: Optional[str]
- text: Optional[str]
- raw_payload: Optional[Dict]
- cursor_event_type: Optional[str]
- cursor_agent_id: Optional[str]
```

### LlmRouterAction (`llm_router.py`, строка 33):
```python
- action: "reply_only" | "start_dev_agent" | "check_dev_status" | "notify_user" | "noop" | "debug_raw"
- reply_text: Optional[str]
- dev_task: Optional[str]
- dev_agent_id: Optional[str]
- importance: Optional["info" | "warning" | "error" | "debug"]
- extra: Dict
```

---

## ⚠️ Важные замечания

1. **In-memory состояние**: DevFlow и DevAgentStore хранят данные только в памяти процесса. При перезапуске оркестратора все активные DevFlow теряются.

2. **Один DevFlow на chat_id**: Нельзя запустить второй DevFlow, пока активен первый.

3. **Webhook опционален**: Если `CURSOR_WEBHOOK_URL` не задан, Dev Agent работает, но статусы о завершении не приходят. Пользователь не получит уведомления.

4. **Команда `/dev`**: Упоминается в help, но не обрабатывается явно. Вероятно, обрабатывается через LLM Router при обычных сообщениях пользователя.

5. **Потокобезопасность**: DevFlow и DevAgentStore используют `threading.Lock` для синхронизации доступа.

