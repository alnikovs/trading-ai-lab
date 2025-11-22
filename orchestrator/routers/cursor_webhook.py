import json
import logging
from typing import Set

from fastapi import APIRouter, Request

from orchestrator.llm_router import IncomingMessage, handle_message
from orchestrator.telegram_bot import send_telegram_message
from orchestrator.dev_flow import DevFlowState, build_step_completed_message

logger = logging.getLogger("orchestrator.cursor_webhook")

router = APIRouter()


@router.post("/cursor/webhook")
async def cursor_webhook(request: Request):
    print(">>> CURSOR WEBHOOK HANDLER ENTERED", flush=True)
    
    try:
        payload = await request.json()
    except Exception:
        logger.exception("Cursor webhook: failed to parse JSON payload")
        return {"ok": False, "error": "invalid_json"}
    
    logger.info("Cursor webhook payload: %s", json.dumps(payload, ensure_ascii=False))
    
    event_type = payload.get("event")
    status = payload.get("status")
    run_id = payload.get("id") or payload.get("run_id") or payload.get("agentId") or payload.get("agent_id")
    summary = payload.get("summary") or payload.get("message")
    
    logger.info(
        "Cursor webhook parsed: run_id=%s status=%s summary=%s event=%s",
        run_id, status, summary, event_type,
    )
    
    normalized_status = (status or "").upper()
    is_final_status = normalized_status in ("FINISHED", "FAILED", "ERROR")
    
    if not is_final_status or event_type != "statusChange":
        logger.info(
            "Cursor webhook: skipping non-final event for run_id=%s status=%s event_type=%s",
            run_id, status, event_type,
        )
        return {"ok": True}
    
    app_state = request.app.state
    
    if not run_id:
        logger.warning("Cursor webhook: missing run_id in final event, skipping notification")
        return {"ok": True}
    
    if run_id in app_state.handled_cursor_runs:
        logger.info("Cursor webhook: run_id %s already notified, skipping duplicate final event", run_id)
        return {"ok": True}
    
    app_state.handled_cursor_runs.add(run_id)
    
    try:
        agent_id = payload.get("agentId") or payload.get("agent_id") or run_id
        
        store = app_state.dev_agent_store
        record = store.get(agent_id) if agent_id else None
        
        if agent_id and not record:
            logger.warning(f"Received Cursor webhook for unknown agent_id: {agent_id}")
            # Fallback на старое поведение для неизвестных агентов
            chat_id = None
        else:
            chat_id = record.chat_id if record else None
            
            # Проверяем, это DevFlow-агент?
            if record and record.is_devflow:
                logger.info(
                    "DevFlow: webhook received for DevFlow agent_id=%s flow_type=%s step_index=%s chat_id=%s",
                    agent_id, record.flow_type, record.step_index, chat_id
                )
                
                # Получаем DevFlowStore из app.state
                dev_flow_store = app_state.dev_flow_store
                session = dev_flow_store.get_session(chat_id) if chat_id else None
                
                if not session:
                    logger.warning(
                        f"DevFlow: session not found for chat_id={chat_id}, flow_type={record.flow_type}, "
                        f"falling back to generic notification"
                    )
                    # Fallback на старое поведение - продолжим ниже
                else:
                    # Обрабатываем завершение шага DevFlow
                    summary_text = summary or "Задача выполнена"
                    
                    # Формируем красивое сообщение
                    message = build_step_completed_message(session, summary_text)
                    
                    # Отправляем в Telegram
                    await send_telegram_message(chat_id, message)
                    
                    # Обновляем состояние сессии
                    session.on_step_completed(summary_text)
                    dev_flow_store.save_session(session)
                    
                    logger.info(
                        "DevFlow: step %s/%s completed for chat_id=%s; sent step completion message",
                        session.current_step_index + 1, session.total_steps, session.chat_id
                    )
                    
                    return {"ok": True}
        
        # Старое поведение для обычных Dev Agents (если record отсутствует, или record.is_devflow == False)
        incoming = IncomingMessage(
            source="cursor",
            chat_id=chat_id,
            text=None,
            raw_payload=payload,
            cursor_event_type=event_type,
            cursor_agent_id=agent_id,
        )
        
        from orchestrator.memory_store import (
            load_ai_contract,
            load_project_summary,
            load_tasks,
            load_recent_results,
            load_message_history,
        )
        
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
        
        if chat_id and action.action in ("notify_user", "reply_only", "debug_raw"):
            if action.reply_text:
                reply_text = action.reply_text
                if len(reply_text) > 4096:
                    reply_text = reply_text[:4090] + "\n..."
                await send_telegram_message(chat_id, reply_text)
                logger.info(f"Sent notification to chat_id {chat_id} for agent {agent_id}")
        elif action.action == "notify_user" and action.reply_text and not chat_id:
            logger.warning(
                f"LLM returned notify_user for agent {agent_id}, but chat_id is unknown. "
                "Notification not sent."
            )
        elif action.action == "debug_raw" and action.reply_text:
            logger.debug(f"Cursor debug event for agent {agent_id}: {action.reply_text}")
        elif action.action == "noop":
            logger.debug(f"Cursor webhook event ignored (noop): {event_type}")
        
        return {"ok": True}
    
    except Exception:
        logger.exception("Error while handling Cursor webhook business logic")
        return {"ok": False, "error": "internal_error"}
