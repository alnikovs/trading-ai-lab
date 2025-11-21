import json
import logging
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ValidationError

from orchestrator.config import OpenAIConfig

logger = logging.getLogger("orchestrator.llm_router")

MessageSource = Literal["telegram", "cursor", "system"]


class IncomingMessage(BaseModel):
    source: MessageSource
    chat_id: Optional[str] = None
    text: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
    cursor_event_type: Optional[str] = None
    cursor_agent_id: Optional[str] = None


RouterActionType = Literal[
    "reply_only",
    "start_dev_agent",
    "check_dev_status",
    "notify_user",
    "noop",
    "debug_raw",
]


class LlmRouterAction(BaseModel):
    action: RouterActionType
    reply_text: Optional[str] = None
    dev_task: Optional[str] = None
    dev_agent_id: Optional[str] = None
    importance: Optional[Literal["info", "warning", "error", "debug"]] = None
    extra: Dict[str, Any] = {}


async def handle_message(
    msg: IncomingMessage,
    openai_client,
    config: Dict,
    load_ai_contract,
    load_project_summary,
    load_tasks,
    load_recent_results,
    load_message_history,
    chat_id: Optional[str] = None,
) -> LlmRouterAction:
    if not openai_client:
        logger.error("OpenAI client not initialized")
        return LlmRouterAction(
            action="reply_only",
            reply_text="Сервис временно недоступен. OpenAI client не инициализирован.",
            importance="error",
        )

    if not config:
        logger.error("Config not initialized")
        return LlmRouterAction(
            action="reply_only",
            reply_text="Сервис временно недоступен. Конфигурация не загружена.",
            importance="error",
        )

    try:
        ai_contract = load_ai_contract()
        project_summary = load_project_summary()
        tasks_data = load_tasks()
        recent_results = load_recent_results(10)

        system_parts = []

        system_parts.append("You are the central LLM Router (brain) of the Trading AI Lab project.")
        system_parts.append("You receive messages from different sources: Telegram users, Cursor webhooks, and system events.")
        system_parts.append("Your role is to analyze incoming messages and decide on appropriate actions.")
        system_parts.append("\nYou must always respond in strict JSON format according to the LlmRouterAction schema:")

        system_parts.append("\n" + "="*60)
        system_parts.append("ACTION TYPES:")
        system_parts.append("="*60)
        system_parts.append('- "reply_only": Reply to the user with text (use reply_text field).')
        system_parts.append('- "start_dev_agent": Launch Cloud Agent in Cursor with dev_task (task description). Can also include reply_text for user notification.')
        system_parts.append('- "check_dev_status": Check status of Dev Agent with dev_agent_id (for future use).')
        system_parts.append('- "notify_user": Important event from Cursor that should be sent to user via Telegram (use reply_text).')
        system_parts.append('- "noop": Do nothing, no response needed.')
        system_parts.append('- "debug_raw": Send technical debug response to Telegram (for developers).')

        system_parts.append("\n" + "="*60)
        system_parts.append("ACTION SEMANTICS:")
        system_parts.append("="*60)
        system_parts.append('- reply_only: Simple text response to user, no additional actions.')
        system_parts.append('- start_dev_agent: User wants to create/modify code. Create dev_task with clear instructions for Cursor Cloud Agent.')
        system_parts.append('- check_dev_status: Query status of existing Dev Agent (reserved for future implementation).')
        system_parts.append('- notify_user: Important event from Cursor (e.g., agent.completed, agent.error). Include summary and PR link if available.')
        system_parts.append('- noop: Ignore the event, no action required.')
        system_parts.append('- debug_raw: Technical response for debugging purposes.')

        system_parts.append("\n" + "="*60)
        system_parts.append("MESSAGE SOURCE HANDLING:")
        system_parts.append("="*60)
        system_parts.append('- source="telegram": User message from Telegram.')
        system_parts.append('  - If user asks to create/modify code → use "start_dev_agent" with clear dev_task description.')
        system_parts.append('  - If user asks general question → use "reply_only" with reply_text.')
        system_parts.append('  - You can use reply_text to confirm Dev Agent launch and give a short comment.')
        system_parts.append('- source="cursor": Event from Cursor webhook (updates about Dev Agent work).')
        system_parts.append('  - Important events (agent.completed, agent.error, agent.pr_created) → use "notify_user" with reply_text.')
        system_parts.append('    Include human-readable summary and PR link if available. Use Russian for user-friendly messages.')
        system_parts.append('    Set importance: "info" for success, "warning" for warnings, "error" for errors.')
        system_parts.append('  - Technical/informational events → use "noop" to ignore.')
        system_parts.append('- source="system": Internal system event. Usually noop or debug_raw.')

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
        system_parts.append("RESPONSE FORMAT:")
        system_parts.append("="*60)
        format_instructions = """
You must always respond in strict JSON format:

{
  "action": "reply_only" | "start_dev_agent" | "check_dev_status" | "notify_user" | "noop" | "debug_raw",
  "reply_text": "optional text for user notification",
  "dev_task": "optional task description for Cursor Cloud Agent (required if action=start_dev_agent)",
  "dev_agent_id": "optional agent ID (for check_dev_status)",
  "importance": "info" | "warning" | "error" | "debug" | null,
  "extra": {}
}

Examples:

1. Simple reply:
{
  "action": "reply_only",
  "reply_text": "Hello! How can I help you?",
  "importance": "info"
}

2. Start Dev Agent:
{
  "action": "start_dev_agent",
  "reply_text": "Создаю Dev Agent для выполнения задачи...",
  "dev_task": "Add a new endpoint /balance to get user balance. Create model BalanceResponse with fields: user_id, balance_usd, balance_btc.",
  "importance": "info"
}

3. Notify user about Cursor event:
{
  "action": "notify_user",
  "reply_text": "✅ Dev Agent завершил работу. PR: https://github.com/user/repo/pull/123",
  "dev_agent_id": "agent_123...",
  "importance": "info"
}

4. No action:
{
  "action": "noop"
}

Do not write any text outside JSON. Always return valid JSON.
"""
        system_parts.append(format_instructions.strip())

        system_content = "\n".join(system_parts)

        user_content_parts = []
        if msg.source == "telegram":
            user_content_parts.append(f"Source: Telegram")
            if msg.chat_id:
                user_content_parts.append(f"Chat ID: {msg.chat_id}")
            if msg.text:
                user_content_parts.append(f"User message: {msg.text}")
        elif msg.source == "cursor":
            user_content_parts.append(f"Source: Cursor webhook")
            if msg.cursor_event_type:
                user_content_parts.append(f"Event type: {msg.cursor_event_type}")
            if msg.cursor_agent_id:
                user_content_parts.append(f"Agent ID: {msg.cursor_agent_id}")
            if msg.raw_payload:
                payload_summary = _extract_cursor_payload_summary(msg.raw_payload)
                if payload_summary:
                    user_content_parts.append(f"Event details: {payload_summary}")
        elif msg.source == "system":
            user_content_parts.append(f"Source: System event")
            if msg.text:
                user_content_parts.append(f"Event: {msg.text}")
            if msg.raw_payload:
                user_content_parts.append(f"Payload: {str(msg.raw_payload)}")

        user_content = "\n".join(user_content_parts)

        messages = [{"role": "system", "content": system_content}]

        if msg.source == "telegram" and chat_id:
            history = load_message_history(chat_id)
            messages.extend(history)

        messages.append({"role": "user", "content": user_content})

        model = config.get("model", "gpt-4")

        response = openai_client.chat.completions.create(
            model=model,
            messages=messages
        )

        assistant_reply = response.choices[0].message.content

        try:
            data = json.loads(assistant_reply)
            if isinstance(data, dict):
                action = LlmRouterAction(**data)
                return action
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Failed to parse LLM response as LlmRouterAction: {e}")
            logger.debug(f"Raw LLM response: {assistant_reply}")

        return LlmRouterAction(
            action="reply_only",
            reply_text="Извините, произошла ошибка при обработке вашего запроса.",
            importance="error",
        )

    except Exception as e:
        logger.error(f"Error in handle_message: {e}", exc_info=True)
        return LlmRouterAction(
            action="reply_only",
            reply_text="Произошла ошибка при обработке сообщения.",
            importance="error",
        )


def _extract_cursor_payload_summary(payload: Dict[str, Any]) -> str:
    parts = []
    if "event" in payload:
        parts.append(f"event={payload['event']}")
    if "agentId" in payload:
        parts.append(f"agentId={payload['agentId']}")
    if "status" in payload:
        parts.append(f"status={payload['status']}")
    if "summary" in payload:
        summary = str(payload["summary"])[:200]
        parts.append(f"summary={summary}")
    if "prUrl" in payload:
        parts.append(f"prUrl={payload['prUrl']}")
    return ", ".join(parts)

