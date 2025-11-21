import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import openai

try:
    from orchestrator.ping_dev import router as ping_dev_router
except ModuleNotFoundError:  # pragma: no cover
    from ping_dev import router as ping_dev_router  # type: ignore

load_dotenv()

app = FastAPI()
app.include_router(ping_dev_router)

CONFIG_DIR = Path(__file__).parent
MEMORY_DIR = Path(__file__).parent.parent / "memory"

config = None
openai_client = None


def load_config() -> Dict:
    global config, openai_client
    
    config_path = CONFIG_DIR / "config.json"
    if not config_path.exists():
        config_path = CONFIG_DIR / "config.example.json"
    
    if not config_path.exists():
        raise FileNotFoundError("Neither config.json nor config.example.json found")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    api_key = config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise ValueError("OpenAI API key not configured")
    
    openai_client = openai.OpenAI(api_key=api_key)
    
    return config


def load_message_history(user_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
    messages_file = MEMORY_DIR / f"messages_{user_id}.jsonl"
    
    if not messages_file.exists():
        return []
    
    try:
        messages = []
        with open(messages_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        
        return messages[-max_messages:] if len(messages) > max_messages else messages
    except (json.JSONDecodeError, IOError) as e:
        return []


def save_messages(user_id: str, user_message: str, assistant_message: str) -> None:
    messages_file = MEMORY_DIR / f"messages_{user_id}.jsonl"
    
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(messages_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": "user", "content": user_message}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"role": "assistant", "content": assistant_message}, ensure_ascii=False) + "\n")
    except IOError as e:
        raise IOError(f"Failed to save messages: {e}")


def load_ai_contract() -> str:
    """
    Загружает текст AI-контракта из docs/ai_contract.md.
    Если файл не найден, возвращает пустую строку.
    """
    docs_dir = Path(__file__).parent.parent / "docs"
    contract_file = docs_dir / "ai_contract.md"
    
    if not contract_file.exists():
        return ""
    
    try:
        with open(contract_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else ""
    except IOError:
        return ""


def load_project_summary() -> str:
    summary_file = MEMORY_DIR / "project_summary.md"
    
    if not summary_file.exists():
        return ""
    
    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else ""
    except IOError:
        return ""


def load_tasks() -> Dict:
    tasks_file = MEMORY_DIR / "tasks.json"
    
    if not tasks_file.exists():
        return {"tasks": []}
    
    try:
        with open(tasks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "tasks" not in data:
                return {"tasks": []}
            return data
    except (json.JSONDecodeError, IOError):
        return {"tasks": []}


def save_tasks(data: Dict) -> None:
    tasks_file = MEMORY_DIR / "tasks.json"
    
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        raise IOError(f"Failed to save tasks: {e}")


def load_recent_results(max_results: int = 10) -> List[Dict]:
    data = load_commands()
    results = data.get("results", [])
    
    return results[-max_results:] if len(results) > max_results else results


def load_commands() -> Dict:
    commands_file = MEMORY_DIR / "commands.json"
    
    if not commands_file.exists():
        return {"commands": [], "results": []}
    
    try:
        with open(commands_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"commands": [], "results": []}
            if "commands" not in data:
                data["commands"] = []
            if "results" not in data:
                data["results"] = []
            return data
    except (json.JSONDecodeError, IOError):
        return {"commands": [], "results": []}


def save_commands(data: Dict) -> None:
    commands_file = MEMORY_DIR / "commands.json"
    
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(commands_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        raise IOError(f"Failed to save commands: {e}")


def find_command_by_id(command_id: str) -> Optional[Dict]:
    data = load_commands()
    for cmd in data.get("commands", []):
        if cmd.get("id") == command_id:
            return cmd
    return None


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


class CursorResultResponse(BaseModel):
    ok: bool


class TaskAddRequest(BaseModel):
    title: str
    details: str = ""


class TaskUpdateRequest(BaseModel):
    id: str
    status: str


@app.on_event("startup")
async def startup_event():
    load_config()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not openai_client:
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
        
        history = load_message_history(request.user_id)
        
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        messages.extend(history)
        messages.append({"role": "user", "content": request.message})
        
        model = config.get("model", "gpt-4")
        
        response = openai_client.chat.completions.create(
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
                    save_messages(request.user_id, request.message, assistant_reply)
                    return ChatResponse(reply=user_message)
                
                elif response_type == "call_cursor":
                    task_id = data.get("task_id")
                    command = data.get("command")
                    
                    if not isinstance(command, dict):
                        raise ValueError("Command must be a dictionary")
                    
                    command_id = add_command(task_id, command)
                    save_messages(request.user_id, request.message, assistant_reply)
                    
                    return ChatResponse(
                        reply="Я сформировал команду для Cursor и отправил её на выполнение.",
                        command_id=command_id
                    )
        
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            pass
        
        save_messages(request.user_id, request.message, assistant_reply)
        return ChatResponse(reply=assistant_reply)
    
    except openai.OpenAIError as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"File operation error: {str(e)}")
    except Exception as e:
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
async def get_pending_commands():
    try:
        data = load_commands()
        pending_commands = [
            {
                "id": cmd["id"],
                "task_id": cmd["task_id"],
                "command": cmd["command"]
            }
            for cmd in data.get("commands", [])
            if cmd.get("status") == "pending"
        ]
        
        return {"commands": pending_commands}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/from-cursor/result", response_model=CursorResultResponse)
async def receive_result(request: CursorResultRequest):
    try:
        data = load_commands()
        
        command_found = None
        for cmd in data["commands"]:
            if cmd.get("id") == request.command_id:
                cmd["status"] = request.status
                command_found = cmd
                break
        
        if not command_found:
            raise HTTPException(status_code=404, detail=f"Command {request.command_id} not found")
        
        result_entry = {
            "command_id": request.command_id,
            "task_id": command_found["task_id"],
            "status": request.status,
            "result": request.result
        }
        
        data["results"].append(result_entry)
        save_commands(data)
        
        return CursorResultResponse(ok=True)
    
    except HTTPException:
        raise
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"File operation error: {str(e)}")
    except Exception as e:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
