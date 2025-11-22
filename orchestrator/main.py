from orchestrator.config import (
    HyperliquidConfig,
    AlloraConfig,
    OpenAIConfig,
    BotConfig,
    TelegramConfig,
    OrchestratorConfig,
    CursorConfig,
    validate_required,
    get_key_preview,
)
from orchestrator.routers.status import router as status_router
from orchestrator.routers.cursor_test import router as cursor_test_router
from orchestrator.routers.cursor_webhook import router as cursor_webhook_router
from orchestrator.cursor_client import create_cursor_agent, get_cursor_agent_status
from orchestrator.llm_router import IncomingMessage, handle_message
from orchestrator.dev_agent_store import get_dev_agent_store, DevAgentStore
from orchestrator.logging_utils import setup_logging
from orchestrator.memory_store import (
    load_config,
    load_message_history,
    save_messages,
    load_ai_contract,
    load_project_summary,
    load_tasks,
    save_tasks,
    load_recent_results,
    load_commands,
    save_commands,
)
from orchestrator.telegram_bot import handle_telegram_update, send_telegram_message

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Set

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
import openai

app = FastAPI()

CONFIG_DIR = Path(__file__).parent
MEMORY_DIR = Path(__file__).parent.parent / "memory"
LOGS_DIR = Path(__file__).parent.parent / "logs"

logger = setup_logging(LOGS_DIR, "orchestrator")


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        
        if "message" in data and "text" in data.get("message", {}):
            message = data["message"]
            chat_id = str(message["chat"]["id"])
            text = message["text"]
            
            await handle_telegram_update(request.app, chat_id, text, raw_payload=data)
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}

app.include_router(status_router)
app.include_router(cursor_test_router, prefix="/cursor", tags=["cursor"])
app.include_router(cursor_webhook_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def is_technical_task(message: str) -> bool:
    """Проверяет, является ли сообщение техническим заданием для Cursor."""
    message_lower = message.lower()
    technical_keywords = [
        "создай файл",
        "добавь эндпоинт",
        "измени код",
        "создай router",
        "создай модель",
        "сформируй команду для cursor",
        "create file",
        "add endpoint",
        "modify code",
        "create router",
        "create model",
        "form command for cursor",
    ]
    return any(keyword in message_lower for keyword in technical_keywords)


def add_command(task_id: Optional[str], command: Dict) -> str:
    command_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    new_command = {
        "id": command_id,
        "task_id": task_id or "",
        "status": "pending",
        "command": command,
        "created_at": created_at
    }
    
    data = load_commands()
    data["commands"].append(new_command)
    save_commands(data)
    
    return command_id


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    command_id: Optional[str] = None


class CommandRequest(BaseModel):
    task_id: str
    command: Dict


class CommandResponse(BaseModel):
    ok: bool
    command_id: str


class CursorResultRequest(BaseModel):
    command_id: str
    status: str
    result: Dict
    user_id: Optional[str] = None


class CursorResultResponse(BaseModel):
    ok: bool


class TaskAddRequest(BaseModel):
    title: str
    details: str = ""


class TaskUpdateRequest(BaseModel):
    id: str
    status: str


class DevAgentStartRequest(BaseModel):
    task: str
    auto_create_pr: bool = True
    branch_name: Optional[str] = None


class DevAgentStartResponse(BaseModel):
    agent_id: str
    status: str
    url: Optional[str] = None
    pr_url: Optional[str] = None
    branch_name: Optional[str] = None


class DevAgentStatusResponse(BaseModel):
    id: str
    status: str
    url: Optional[str] = None
    pr_url: Optional[str] = None
    summary: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    if os.getenv("TESTING") == "1":
        logger.info("Starting FastAPI orchestrator in TESTING mode")
        from orchestrator.dev_agent_store import get_dev_agent_store
        from orchestrator.dev_flow import DevFlowStore
        
        app.state.config = {"model": "gpt-4"}
        app.state.openai_client = None
        app.state.dev_agent_store = get_dev_agent_store()
        app.state.dev_flow_store = DevFlowStore
        app.state.handled_cursor_runs: Set[str] = set()
        app.state.pending_cursor_commands: List[Dict] = []
        
        logger.info("FastAPI orchestrator started in TESTING mode successfully")
        return
    
    logger.info("Starting FastAPI orchestrator")
    logger.info(f"ENV: {BotConfig.ENV}")
    logger.info(f"LOG_LEVEL: {BotConfig.LOG_LEVEL}")
    
    config_data = load_config()
    
    api_key = OpenAIConfig.API_KEY
    if not api_key:
        raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in .env file")
    
    openai_client_instance = openai.OpenAI(api_key=api_key)
    
    from orchestrator.dev_agent_store import get_dev_agent_store
    from orchestrator.dev_flow import DevFlowStore
    
    app.state.config = config_data
    app.state.openai_client = openai_client_instance
    app.state.dev_agent_store = get_dev_agent_store()
    app.state.dev_flow_store = DevFlowStore
    app.state.handled_cursor_runs: Set[str] = set()
    app.state.pending_cursor_commands: List[Dict] = []
    
    logger.info("Configuration summary:")
    logger.info(f"  OpenAI API key: {'PRESENT' if OpenAIConfig.API_KEY else 'MISSING'}")
    logger.info(f"  Cursor API key: {'PRESENT' if CursorConfig.API_KEY else 'MISSING'}")
    logger.info(f"  Cursor Repository: {'SET' if CursorConfig.REPOSITORY else 'NOT SET'}")
    logger.info(f"  Cursor Webhook URL: {'SET' if CursorConfig.WEBHOOK_URL else 'NOT SET'}")
    logger.info(f"  Telegram Bot Token: {'PRESENT' if TelegramConfig.TOKEN else 'MISSING'}")
    
    cursor_webhook_url = CursorConfig.WEBHOOK_URL
    if cursor_webhook_url:
        logger.info(f"  Cursor Webhook URL: {cursor_webhook_url[:50]}...")
    
    logger.info("FastAPI orchestrator started successfully")


@app.post("/chat", response_model=ChatResponse)
async def chat(chat_request: ChatRequest, request: Request):
    app_state = request.app.state
    message_preview = chat_request.message[:50] + "..." if len(chat_request.message) > 50 else chat_request.message
    logger.info(f"Chat request: user_id={chat_request.user_id}, message_preview='{message_preview}'")
    
    if is_technical_task(chat_request.message):
        logger.info("Technical task detected, creating Cursor command", extra={"user_id": chat_request.user_id})
        command_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        command_entry = {
            "id": command_id,
            "timestamp": timestamp,
            "prompt": chat_request.message,
            "user_id": chat_request.user_id
        }
        
        data = load_commands()
        data["commands"].append(command_entry)
        save_commands(data)
        
        app_state.pending_cursor_commands.append(command_entry)
        logger.info(
            "Command added to queue and saved to commands.json",
            extra={
                "command_id": command_id,
                "queue_size": len(app_state.pending_cursor_commands),
            }
        )
        
        return ChatResponse(reply="Задача отправлена Cursor, ждем результата…")
    
    if not app_state.openai_client:
        logger.error("OpenAI client not initialized")
        raise HTTPException(status_code=500, detail="OpenAI client not initialized")
    
    try:
        ai_contract = load_ai_contract()
        project_summary = load_project_summary()
        tasks_data = load_tasks()
        recent_results = load_recent_results(10)
        
        system_parts = []
        
        system_parts.append("You are the strategic AI of the Trading AI Lab project.")
        system_parts.append("You always use the project summary, tasks list and recent results injected above.")
        system_parts.append("\nYour responsibilities:")
        system_parts.append("- Maintain and update the task list.")
        system_parts.append("- Plan the next development steps.")
        system_parts.append("- Decide when to call Cursor Cloud Agent via { \"type\": \"call_cursor\" }.")
        system_parts.append("- Keep context between requests using the injected memory.")
        system_parts.append("- Do NOT rewrite whole files unless required; plan modular changes.")
        
        system_parts.append("\n" + "="*60)
        system_parts.append("TASK MANAGEMENT RULES:")
        system_parts.append("="*60)
        system_parts.append("- If the user asks to add/update/list tasks, you MUST NOT call Cursor.")
        system_parts.append("- For task management: produce plain text responses only.")
        system_parts.append("- Calling Cursor is forbidden for task management operations.")
        
        system_parts.append("\n" + "="*60)
        system_parts.append("CURSOR EXECUTION RULES:")
        system_parts.append("="*60)
        system_parts.append("- Only call Cursor when user explicitly requests code creation/modification,")
        system_parts.append("  or when strategic planning requires actual code changes.")
        
        if ai_contract:
            system_parts.append("\n" + "="*60)
            system_parts.append("AI CONTRACT:")
            system_parts.append("="*60)
            system_parts.append(ai_contract)
        
        system_parts.append("\n" + "="*60)
        system_parts.append("PROJECT SUMMARY:")
        system_parts.append("="*60)
        if project_summary:
            system_parts.append(project_summary)
        else:
            system_parts.append("(No project summary available)")
        
        system_parts.append("\n" + "="*60)
        system_parts.append("CURRENT TASKS:")
        system_parts.append("="*60)
        tasks_list = tasks_data.get("tasks", [])
        if tasks_list:
            for task in tasks_list:
                status = task.get("status", "open")
                task_id = task.get("id", "")
                title = task.get("title", "")
                details = task.get("details") or task.get("description", "")
                system_parts.append(f"- [{status}] {task_id} {title}")
                if details:
                    system_parts.append(f"  {details}")
        else:
            system_parts.append("(No tasks)")
        
        system_parts.append("\n" + "="*60)
        system_parts.append("RECENT CURSOR RESULTS:")
        system_parts.append("="*60)
        if recent_results:
            for result in recent_results:
                result_status = result.get("status", "unknown")
                task_id = result.get("task_id", "")
                command_id = result.get("command_id", "")
                result_data = result.get("result", {})
                system_parts.append(f"\nCommand ID: {command_id} | Task: {task_id} | Status: {result_status}")
                if result_status == "ok" and result_data:
                    if "notes" in result_data:
                        system_parts.append(f"  Notes: {result_data.get('notes')}")
                    if "message" in result_data:
                        system_parts.append(f"  Message: {result_data.get('message')}")
                elif result_status == "error" and result_data:
                    error_msg = result_data.get("error", "Unknown error")
                    system_parts.append(f"  Error: {error_msg}")
        else:
            system_parts.append("(No recent results)")
        
        system_parts.append("\n" + "="*60)
        system_parts.append("ФОРМАТ ОТВЕТОВ CHATGPT")
        system_parts.append("="*60)
        format_instructions = """
Каждый твой ответ должен быть строго в JSON-формате:

1) Если ты отвечаешь человеку — используй формат:

{
  "type": "reply_user",
  "message": "<твой обычный текст>"
}

2) Если для выполнения нужен Cursor — используй формат:

{
  "type": "call_cursor",
  "task_id": "<id задачи или произвольная строка>",
  "command": {
      "prompt": "<подробное текстовое задание для Cloud Agent Cursor на английском или русском языке>"
  }
}

Важно: prompt должен содержать понятное для Cursor описание: какие файлы создать/изменить, какую функцию добавить, какие тесты написать. Никаких других полей в command на этом этапе не требуется.

Не пиши текст вне JSON.

Если пользователь попросил изменить код — создавай call_cursor.

Если нет — reply_user.
"""
        system_parts.append(format_instructions.strip())
        
        system_content = "\n".join(system_parts)
        
        history = load_message_history(chat_request.user_id)
        
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        messages.extend(history)
        messages.append({"role": "user", "content": chat_request.message})
        
        model = app_state.config.get("model", "gpt-4")
        
        response = app_state.openai_client.chat.completions.create(
            model=model,
            messages=messages
        )
        
        assistant_reply = response.choices[0].message.content
        
        try:
            data = json.loads(assistant_reply)
            if isinstance(data, dict) and "type" in data:
                response_type = data.get("type")
                
                if response_type == "reply_user":
                    user_message = data.get("message", "")
                    save_messages(chat_request.user_id, chat_request.message, assistant_reply)
                    return ChatResponse(reply=user_message)
                
                elif response_type == "call_cursor":
                    task_id = data.get("task_id")
                    command = data.get("command")
                    
                    if not isinstance(command, dict):
                        raise ValueError("Command must be a dictionary")
                    
                    command_id = add_command(task_id, command)
                    prompt_preview = command.get("prompt", "")[:100] + "..." if len(command.get("prompt", "")) > 100 else command.get("prompt", "")
                    logger.info(
                        "Cursor command created",
                        extra={
                            "command_id": command_id,
                            "task_id": task_id,
                            "user_id": chat_request.user_id,
                            "prompt_preview": prompt_preview,
                        }
                    )
                    save_messages(chat_request.user_id, chat_request.message, assistant_reply)
                    
                    return ChatResponse(
                        reply="Я сформировал команду для Cursor и отправил её на выполнение.",
                        command_id=command_id
                    )
        
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            logger.debug(f"Failed to parse assistant reply as JSON, treating as plain text")
        
        save_messages(chat_request.user_id, chat_request.message, assistant_reply)
        return ChatResponse(reply=assistant_reply)
    
    except openai.OpenAIError as e:
        logger.error(f"OpenAI API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")
    except IOError as e:
        logger.error(f"File operation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"File operation error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in /chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/from-chatgpt/command", response_model=CommandResponse)
async def receive_command(request: CommandRequest):
    try:
        command_id = add_command(request.task_id, request.command)
        return CommandResponse(ok=True, command_id=command_id)
    
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"File operation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/for-cursor/commands")
async def get_pending_commands(request: Request):
    try:
        app_state = request.app.state
        commands_to_return = app_state.pending_cursor_commands.copy()
        app_state.pending_cursor_commands.clear()
        
        if commands_to_return:
            command_ids = [cmd["id"] for cmd in commands_to_return]
            logger.info(f"Cursor commands requested: {len(commands_to_return)} commands returned and cleared, ids={command_ids}")
        else:
            logger.debug("Cursor commands requested: queue is empty")
        
        formatted_commands = [
            {
                "id": cmd["id"],
                "prompt": cmd["prompt"],
                "user_id": cmd["user_id"],
                "timestamp": cmd["timestamp"]
            }
            for cmd in commands_to_return
        ]
        
        return {"commands": formatted_commands}
    
    except Exception as e:
        logger.error(f"Error getting pending commands: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/from-cursor/result", response_model=CursorResultResponse)
async def receive_result(cursor_result: CursorResultRequest, request: Request):
    try:
        command_found = None
        user_id = None
        
        data = load_commands()
        for cmd in data.get("commands", []):
            if cmd.get("id") == cursor_result.command_id:
                command_found = cmd
                user_id = cmd.get("user_id")
                break
        
        if not command_found:
            app_state = request.app.state
            for cmd in app_state.pending_cursor_commands:
                if cmd.get("id") == cursor_result.command_id:
                    command_found = cmd
                    user_id = cmd.get("user_id")
                    break
        
        if not command_found:
            logger.warning(
                "Cursor result received for unknown command_id",
                extra={"command_id": cursor_result.command_id}
            )
        
        if user_id is None:
            user_id = cursor_result.user_id
        
        if user_id is None and isinstance(cursor_result.result, dict):
            user_id = cursor_result.result.get("user_id")
        
        logger.info(
            "Cursor result received",
            extra={
                "command_id": cursor_result.command_id,
                "status": cursor_result.status,
                "user_id": user_id,
            }
        )
        
        result_text = "✅ Cursor выполнил задачу\n\n"
        
        if cursor_result.status == "error":
            error_msg = cursor_result.result.get("error", "Unknown error") if isinstance(cursor_result.result, dict) else "Unknown error"
            logger.error(
                "Cursor command failed",
                extra={"command_id": cursor_result.command_id, "error": error_msg}
            )
            result_text = f"❌ Cursor выполнил задачу с ошибкой\n\nОшибка: {error_msg}\n\n"
        else:
            diff = cursor_result.result.get("diff", "") if isinstance(cursor_result.result, dict) else ""
            notes = cursor_result.result.get("notes", "") if isinstance(cursor_result.result, dict) else ""
            message = cursor_result.result.get("message", "") if isinstance(cursor_result.result, dict) else ""
            
            if message:
                result_text += f"{message}\n\n"
            
            if notes:
                result_text += f"Комментарии: {notes}\n\n"
            
            if diff:
                result_text += f"```\n{diff}\n```"
        
        if user_id:
            success = await send_telegram_message(user_id, result_text)
            if success:
                logger.info("Result sent to Telegram", extra={"user_id": user_id})
            else:
                logger.warning("Failed to send result to Telegram", extra={"user_id": user_id})
        else:
            logger.info("No user_id found, result logged but not sent to Telegram")
        
        if command_found:
            data = load_commands()
            result_entry = {
                "command_id": cursor_result.command_id,
                "task_id": command_found.get("task_id", ""),
                "status": cursor_result.status,
                "result": cursor_result.result
            }
            
            data["results"].append(result_entry)
            save_commands(data)
        
        return CursorResultResponse(ok=True)
    
    except HTTPException:
        raise
    except IOError as e:
        logger.error(
            "File operation error when saving cursor result",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"File operation error: {str(e)}")
    except Exception as e:
        logger.error(
            "Unexpected error when processing cursor result",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/for-chatgpt/results")
async def get_results(task_id: Optional[str] = Query(None)):
    try:
        data = load_commands()
        results = data.get("results", [])
        
        if task_id:
            results = [r for r in results if r.get("task_id") == task_id]
        
        return {"results": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/tasks")
async def get_tasks():
    try:
        tasks_data = load_tasks()
        return tasks_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/tasks/add")
async def add_task(request: TaskAddRequest):
    try:
        tasks_data = load_tasks()
        tasks_list = tasks_data.get("tasks", [])
        
        max_id = 0
        for task in tasks_list:
            task_id_str = task.get("id", "")
            if task_id_str.startswith("T") and len(task_id_str) > 1:
                try:
                    num = int(task_id_str[1:])
                    if num > max_id:
                        max_id = num
                except ValueError:
                    pass
        
        new_id = f"T{max_id + 1:03d}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        new_task = {
            "id": new_id,
            "title": request.title,
            "status": "open",
            "details": request.details,
            "created_at": created_at
        }
        
        tasks_list.append(new_task)
        tasks_data["tasks"] = tasks_list
        save_tasks(tasks_data)
        
        return {"ok": True, "task": new_task}
    
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"File operation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/tasks/update")
async def update_task(request: TaskUpdateRequest):
    try:
        tasks_data = load_tasks()
        tasks_list = tasks_data.get("tasks", [])
        
        task_found = None
        for task in tasks_list:
            if task.get("id") == request.id:
                task["status"] = request.status
                if "updated_at" not in task:
                    task["updated_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    task["updated_at"] = datetime.now(timezone.utc).isoformat()
                task_found = task
                break
        
        if not task_found:
            raise HTTPException(status_code=404, detail=f"Task {request.id} not found")
        
        if request.status not in ["open", "in_progress", "done"]:
            raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}. Must be one of: open, in_progress, done")
        
        tasks_data["tasks"] = tasks_list
        save_tasks(tasks_data)
        
        return {"ok": True, "task": task_found}
    
    except HTTPException:
        raise
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"File operation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/dev/agents", response_model=DevAgentStartResponse)
async def create_dev_agent(request: DevAgentStartRequest):
    try:
        result = await create_cursor_agent(
            task_text=request.task,
            auto_create_pr=request.auto_create_pr,
            branch_name=request.branch_name,
        )
        return DevAgentStartResponse(
            agent_id=result.id,
            status=result.status,
            url=result.url,
            pr_url=result.pr_url,
            branch_name=result.branch_name,
        )
    except ValueError as e:
        logger.error(f"Configuration error in create_dev_agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        error_str = str(e)
        status_code = getattr(e, "status_code", None)
        response_text = getattr(e, "response_text", None)
        
        if status_code:
            detail = response_text or error_str.split(": ", 1)[1] if ": " in error_str else error_str
            logger.error(f"HTTP error in create_dev_agent: {error_str}", exc_info=True)
            raise HTTPException(status_code=status_code, detail=detail)
        
        logger.error(f"Runtime error in create_dev_agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create Cursor agent: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in create_dev_agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/dev/agents/{agent_id}", response_model=DevAgentStatusResponse)
async def get_dev_agent_status(agent_id: str):
    try:
        status_data = await get_cursor_agent_status(agent_id)
        
        return DevAgentStatusResponse(
            id=status_data.get("id", agent_id),
            status=status_data.get("status", "unknown"),
            url=status_data.get("url"),
            pr_url=status_data.get("pr_url"),
            summary=status_data.get("summary"),
        )
    except ValueError as e:
        logger.error(f"Configuration error in get_dev_agent_status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        error_str = str(e)
        status_code = getattr(e, "status_code", None)
        response_text = getattr(e, "response_text", None)
        
        if status_code:
            detail = response_text or error_str.split(": ", 1)[1] if ": " in error_str else error_str
            logger.error(f"HTTP error in get_dev_agent_status: {error_str}", exc_info=True)
            raise HTTPException(status_code=status_code, detail=detail)
        
        logger.error(f"Runtime error in get_dev_agent_status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get Cursor agent status: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_dev_agent_status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

