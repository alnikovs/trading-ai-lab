import logging
from typing import Optional, Dict

import httpx
from fastapi import FastAPI

from orchestrator.config import TelegramConfig
from orchestrator.llm_router import IncomingMessage, handle_message
from orchestrator.cursor_client import (
    create_cursor_agent,
    get_cursor_agent_status,
    create_devflow_step_agent,
)
from orchestrator.dev_flow import DevFlowStore, DevFlowState, DevFlowSession
from orchestrator.memory_store import (
    load_ai_contract,
    load_project_summary,
    load_tasks,
    load_recent_results,
    load_message_history,
)

logger = logging.getLogger("orchestrator.telegram_bot")


async def send_telegram_message(user_id: str, text: str) -> bool:
    if not TelegramConfig.TOKEN:
        logger.warning("Telegram token not configured, cannot send message")
        return False

    try:
        chat_id = int(user_id)
    except (ValueError, TypeError):
        logger.error("Invalid user_id format", extra={"user_id": user_id, "expected": "integer"})
        return False

    max_length = 4096
    messages = []

    if len(text) <= max_length:
        messages = [text]
    else:
        parts = text.split("\n")
        current_message = ""

        for part in parts:
            if len(current_message) + len(part) + 1 <= max_length:
                current_message += (part + "\n" if current_message else part)
            else:
                if current_message:
                    messages.append(current_message.rstrip())
                if len(part) <= max_length:
                    current_message = part
                else:
                    for i in range(0, len(part), max_length - 10):
                        messages.append(part[i:i + max_length - 10] + "...")
                    current_message = ""

        if current_message:
            messages.append(current_message.rstrip())

    url = f"https://api.telegram.org/bot{TelegramConfig.TOKEN}/sendMessage"

    all_success = True

    async with httpx.AsyncClient(timeout=10.0) as client:
        for msg in messages:
            payload = {
                "chat_id": chat_id,
                "text": msg,
                # Без parse_mode, чтобы избежать ошибок парсинга Markdown от Telegram
            }

            max_retries = 3
            success = False

            for attempt in range(max_retries):
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code != 200:
                        logger.warning(
                            "Telegram API returned non-200 status",
                            extra={
                                "user_id": user_id,
                                "status_code": response.status_code,
                                "response_text": response.text[:500],
                            }
                        )
                        if attempt < max_retries - 1:
                            continue
                        else:
                            all_success = False
                            break

                    data = response.json()
                    if not data.get("ok", False):
                        logger.warning(
                            "Telegram API returned ok=false",
                            extra={
                                "user_id": user_id,
                                "response": data,
                            }
                        )
                        if attempt < max_retries - 1:
                            continue
                        else:
                            all_success = False
                            break

                    success = True
                    break

                except httpx.TimeoutException:
                    if attempt < max_retries - 1:
                        logger.warning(
                            "Telegram API timeout, retrying",
                            extra={
                                "user_id": user_id,
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                            }
                        )
                    else:
                        logger.error(
                            "Telegram API timeout, giving up",
                            extra={
                                "user_id": user_id,
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                            },
                            exc_info=True,
                        )
                        all_success = False
                        break
                except httpx.RequestError as e:
                    logger.error(
                        "Telegram API request error",
                        extra={"user_id": user_id, "error": str(e)},
                        exc_info=True
                    )
                    if attempt < max_retries - 1:
                        continue
                    else:
                        all_success = False
                        break
                except Exception as e:
                    logger.error(
                        "Failed to send Telegram message",
                        extra={"user_id": user_id, "error": str(e)},
                        exc_info=True
                    )
                    all_success = False
                    break

            if not success:
                break

    if all_success:
        logger.info(
            "Telegram message sent",
            extra={"user_id": user_id, "parts_count": len(messages)}
        )

    return all_success


async def handle_telegram_update(
    app: FastAPI,
    chat_id: str,
    text: str,
    raw_payload: Optional[Dict] = None
) -> None:
    text_lower = text.strip().lower() if text else ""

    if text_lower == "/start":
        reply = (
            "Привет! Я trading-бот.\n\n"
            "Пока я умею немного, но скоро здесь будет:\n"
            "- подключение к бирже\n"
            "- стратегии\n"
            "- AI-прогнозы.\n\n"
            "Напиши: help — чтобы увидеть команды."
        )
        await send_telegram_message(chat_id, reply)
        return
    elif text_lower in ("help", "/help"):
        reply = (
            "Команды:\n"
            "- /start — приветствие\n"
            "- /help — показать это сообщение\n"
            "- /status — статус бота и конфигурации\n"
            "- /dev <TASK_ID> — запустить Dev Agent для задачи (например, /dev T004)\n"
            "- ping — проверить связь\n"
            "- echo <текст> — вернуть твой текст\n"
        )
        await send_telegram_message(chat_id, reply)
        return
    elif text_lower == "ping":
        reply = "pong 🟢"
        await send_telegram_message(chat_id, reply)
        return
    elif text_lower == "/status":
        from orchestrator.config import (
            OpenAIConfig,
            CursorConfig,
            TelegramConfig,
            BotConfig,
        )

        status_lines = [
            "Статус оркестратора:",
            f"- Окружение: {BotConfig.ENV}",
            f"- OpenAI API key: {'✅ PRESENT' if OpenAIConfig.API_KEY else '❌ MISSING'}",
            f"- Cursor API key: {'✅ PRESENT' if CursorConfig.API_KEY else '❌ MISSING'}",
            f"- Cursor Repository: {'✅ SET' if CursorConfig.REPOSITORY else '❌ NOT SET'}",
            f"- Cursor Webhook URL: {'✅ SET' if CursorConfig.WEBHOOK_URL else '❌ NOT SET'}",
            f"- Telegram Bot Token: {'✅ PRESENT' if TelegramConfig.TOKEN else '❌ MISSING'}",
        ]
        reply = "\n".join(status_lines)
        await send_telegram_message(chat_id, reply)
        return
    elif text_lower.startswith("echo "):
        reply = text[5:].strip() or "Ты ничего не написал после echo 😅"
        await send_telegram_message(chat_id, reply)
        return

    # --- DevFlow: команда /devflow_simple_ma ---
    if text_lower == "/devflow_simple_ma":
        existing_session = DevFlowStore.get_session(chat_id)
        if existing_session and existing_session.state in (
            DevFlowState.RUNNING_STEP,
            DevFlowState.AWAITING_CONFIRMATION,
        ):
            reply = (
                "⚠️ У тебя уже есть активный DevFlow simple_ma.\n"
                "Сначала заверши текущий (ответь «да» или «нет»), "
                "или подожди завершения шага, а потом запускай новый."
            )
            await send_telegram_message(chat_id, reply)
            return

        # Создаём новую сессию
        session = DevFlowStore.create_simple_ma_session(chat_id)
        session.start()
        DevFlowStore.save_session(session)
        
        # Получаем промпт для первого шага
        step_prompt = session.build_step_prompt()
        if not step_prompt:
            await send_telegram_message(chat_id, "❌ Ошибка: не удалось получить задание для шага 1")
            return

        # Создаём агента для шага 1
        agent_id = await create_devflow_step_agent(
            chat_id=session.chat_id,
            flow_id=session.flow_id,
            step=session.current_step_index + 1,
            step_prompt=step_prompt,
        )
        session.on_step_agent_created(agent_id)
        DevFlowStore.save_session(session)

        reply = (
            f"🚀 DevFlow simple_ma: запускаю шаг {session.current_step_index + 1} из {session.total_steps}.\n"
            "Я пришлю отчёт, когда агент завершит этот шаг."
        )
        await send_telegram_message(chat_id, reply)
        return

    if not text:
        return

    # --- DevFlow: обработка ответов "да" / "нет" ---
    session = DevFlowStore.get_session(chat_id)
    if session and session.state == DevFlowState.AWAITING_CONFIRMATION:
        text_normalized = text_lower.strip()
        yes_variants = {"да", "yes", "y", "д", "ага"}
        no_variants = {"нет", "no", "n", "не", "stop"}
        
        logger.info(
            "DevFlow: user replied '%s' for chat_id=%s, state=%s",
            text_normalized, chat_id, session.state
        )

        if text_normalized in yes_variants:
            # Проверяем, есть ли следующий шаг
            if session.current_step_index + 1 < session.total_steps:
                # Переходим к следующему шагу
                session.advance_to_next_step()
                DevFlowStore.save_session(session)
                
                logger.info(
                    "DevFlow: advancing to step %s/%s for chat_id=%s",
                    session.current_step_index + 1, session.total_steps, chat_id
                )

                # Получаем промпт для следующего шага
                step_prompt = session.build_step_prompt()
                if not step_prompt:
                    await send_telegram_message(chat_id, f"❌ Ошибка: не удалось получить задание для шага {session.current_step_index + 1}")
                    return

                # Создаём агента для следующего шага
                agent_id = await create_devflow_step_agent(
                    chat_id=session.chat_id,
                    flow_id=session.flow_id,
                    step=session.current_step_index + 1,
                    step_prompt=step_prompt,
                )
                session.on_step_agent_created(agent_id)
                DevFlowStore.save_session(session)

                reply = (
                    f"✅ Ок, продолжаем DevFlow simple_ma.\n"
                    f"Запускаю шаг {session.current_step_index + 1} из {session.total_steps}."
                )
                await send_telegram_message(chat_id, reply)
                return
            else:
                # Это был последний шаг
                session.finish()
                DevFlowStore.finish_session(chat_id)
                
                logger.info("DevFlow: session finished for chat_id=%s", chat_id)
                
                reply = (
                    f"🎉 DevFlow simple_ma завершён ✅\n"
                    f"Всего шагов: {session.total_steps}.\n"
                    "Можешь запустить его снова командой /devflow_simple_ma."
                )
                await send_telegram_message(chat_id, reply)
                return

        elif text_normalized in no_variants:
            # Отменяем DevFlow
            DevFlowStore.finish_session(chat_id)
            
            logger.info("DevFlow: session cancelled for chat_id=%s", chat_id)
            
            reply = (
                "⏹ DevFlow simple_ma остановлен по твоему запросу.\n"
                "Если захочешь — запусти его снова командой /devflow_simple_ma."
            )
            await send_telegram_message(chat_id, reply)
            return
        else:
            # Непонятный ответ - напоминаем
            reply = (
                "Я сейчас жду ответ по DevFlow simple_ma.\n"
                "Пожалуйста, ответь «да» чтобы продолжить, или «нет» чтобы остановить."
            )
            await send_telegram_message(chat_id, reply)
            return

    incoming = IncomingMessage(
        source="telegram",
        chat_id=chat_id,
        text=text,
        raw_payload=raw_payload,
    )

    app_state = app.state
    action = await handle_message(
        incoming,
        app_state.openai_client,
        app_state.config,
        load_ai_contract,
        load_project_summary,
        load_tasks,
        load_recent_results,
        load_message_history,
        chat_id=chat_id,
    )

    if action.action in ("reply_only", "notify_user", "debug_raw"):
        if action.reply_text:
            reply_text = action.reply_text
            if len(reply_text) > 4096:
                reply_text = reply_text[:4090] + "\n..."
            await send_telegram_message(chat_id, reply_text)

    elif action.action == "start_dev_agent" and action.dev_task:
        try:
            result = await create_cursor_agent(task_text=action.dev_task)

            store = app_state.dev_agent_store
            store.register(
                agent_id=result.id,
                chat_id=chat_id,
                original_text=text,
                dev_task=action.dev_task,
            )
            logger.info(f"Registered Dev Agent {result.id} for chat_id {chat_id}")

            confirm_text = action.reply_text or (
                f"✅ Запустил Dev Agent для этой задачи.\n"
                f"ID: {result.id}\n"
                f"Статус: {result.status}"
            )
            if len(confirm_text) > 4096:
                confirm_text = confirm_text[:4090] + "\n..."
            await send_telegram_message(chat_id, confirm_text)
        except Exception as e:
            logger.error(f"Error starting Dev Agent: {e}", exc_info=True)
            error_text = f"❌ Ошибка при запуске Dev Agent: {str(e)}"
            if len(error_text) > 4096:
                error_text = error_text[:4090] + "\n..."
            await send_telegram_message(chat_id, error_text)

    elif action.action == "check_dev_status" and action.dev_agent_id:
        try:
            status_data = await get_cursor_agent_status(action.dev_agent_id)
            status_text = f"Статус Dev Agent {action.dev_agent_id}:\n"
            status_text += f"- status: {status_data.get('status', 'unknown')}\n"
            if "url" in status_data and status_data["url"]:
                status_text += f"URL: {status_data['url']}\n"
            if "pr_url" in status_data and status_data["pr_url"]:
                status_text += f"PR: {status_data['pr_url']}\n"
            if len(status_text) > 4096:
                status_text = status_text[:4090] + "\n..."
            await send_telegram_message(chat_id, status_text)
        except Exception as e:
            logger.error(f"Error checking Dev Agent status: {e}", exc_info=True)
            error_text = f"❌ Ошибка при проверке статуса Dev Agent: {str(e)}"
            if len(error_text) > 4096:
                error_text = error_text[:4090] + "\n..."
            await send_telegram_message(chat_id, error_text)

    elif action.action == "noop":
        pass
