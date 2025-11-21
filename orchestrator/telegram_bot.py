import logging
from typing import Optional, Dict

import httpx
from fastapi import FastAPI

from orchestrator.config import TelegramConfig
from orchestrator.llm_router import IncomingMessage, handle_message
from orchestrator.cursor_client import create_cursor_agent, get_cursor_agent_status
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
    for i, message_text in enumerate(messages):
        max_retries = 2
        success = False
        
        for attempt in range(max_retries):
            try:
                payload = {
                    "chat_id": chat_id,
                    "text": message_text,
                }
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, json=payload)
                    
                    if response.is_error:
                        if attempt < max_retries - 1:
                            logger.warning(
                                "Telegram API error, retrying",
                                extra={
                                    "user_id": user_id,
                                    "status_code": response.status_code,
                                    "attempt": attempt + 1,
                                    "max_retries": max_retries,
                                }
                            )
                            continue
                        else:
                            logger.error(
                                "Telegram API error after retries",
                                extra={
                                    "user_id": user_id,
                                    "status_code": response.status_code,
                                    "response_body": response.text[:200],
                                }
                            )
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
                    continue
                else:
                    logger.error("Telegram API timeout after retries", extra={"user_id": user_id}, exc_info=True)
                    all_success = False
                    break
            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Telegram API request error, retrying",
                        extra={
                            "user_id": user_id,
                            "error": str(e),
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                        }
                    )
                    continue
                else:
                    logger.error(
                        "Telegram API request error after retries",
                        extra={"user_id": user_id, "error": str(e)},
                        exc_info=True
                    )
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

    if not text:
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
            status_text = action.reply_text or (
                f"Статус Dev Agent {action.dev_agent_id}:\n"
                f"Статус: {status_data.get('status', 'unknown')}\n"
            )
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
