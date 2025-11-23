import json
import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from orchestrator.config import CursorConfig
from orchestrator.prompts import BUILDER_LLM_SYSTEM_PROMPT
from orchestrator.dev_agent_store import get_dev_agent_store
from orchestrator.devflow_prompts import build_devflow_system_prompt

logger = logging.getLogger("orchestrator.cursor_client")


class CursorAgentCreateResult(BaseModel):
    id: str
    status: str
    url: Optional[str] = None
    pr_url: Optional[str] = None
    branch_name: Optional[str] = None


async def create_cursor_agent(
    task_text: str,
    auto_create_pr: bool = True,
    branch_name: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> CursorAgentCreateResult:
    api_key = CursorConfig.API_KEY
    base_url = CursorConfig.BASE_URL
    repository = CursorConfig.REPOSITORY
    base_ref = CursorConfig.BASE_REF

    if not api_key:
        raise ValueError("CURSOR_API_KEY not configured in .env")

    if not repository:
        raise ValueError("CURSOR_REPOSITORY not configured in .env")

    url = f"{base_url}/v0/agents"

    # Используем переданный системный промпт или дефолтный BUILDER_LLM_SYSTEM_PROMPT
    effective_system_prompt = system_prompt if system_prompt is not None else BUILDER_LLM_SYSTEM_PROMPT
    
    # Объединяем системный промпт с задачей пользователя
    full_prompt = f"{effective_system_prompt}\n\n---\n\nTASK: {task_text}"

    payload: dict = {
        "prompt": {
            "text": full_prompt,
        },
        "source": {
            "repository": repository,
            "ref": base_ref,
        },
        "target": {
            "autoCreatePr": auto_create_pr,
        },
    }

    if branch_name:
        payload["target"]["branchName"] = branch_name

    webhook_url = CursorConfig.WEBHOOK_URL
    if webhook_url:
        if not isinstance(webhook_url, str) or not webhook_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid CURSOR_WEBHOOK_URL format: {webhook_url}. Must be a valid HTTP(S) URL.")
        payload["webhook"] = {"url": webhook_url}

    payload_preview_str = json.dumps(payload, default=str, indent=None)
    payload_preview = payload_preview_str[:200] + "..." if len(payload_preview_str) > 200 else payload_preview_str

    logger.info(
        "Creating Cursor agent",
        extra={
            "url": url,
            "repository": repository,
            "ref": base_ref,
            "branch": branch_name or "default",
            "webhook_attached": bool(webhook_url),
            "payload_preview": payload_preview[:200],
        },
    )

    try:
        async with httpx.AsyncClient(auth=(api_key, ""), timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            agent_id = data.get("id", "")
            status = data.get("status", "unknown")

            result = CursorAgentCreateResult(
                id=agent_id,
                status=status,
                url=data.get("url"),
                pr_url=data.get("pr_url"),
                branch_name=data.get("branch_name") or branch_name,
            )

            logger.info(
                "Cursor agent created: id=%s, status=%s, url=%s, pr_url=%s, branch=%s",
                agent_id,
                status,
                result.url or "N/A",
                result.pr_url or "N/A",
                result.branch_name or "N/A",
            )

            return result

    except httpx.HTTPStatusError as e:
        error_text = f"HTTP {e.response.status_code}: {e.response.text}"
        response_preview = e.response.text[:200] if e.response.text else ""
        logger.error(
            "HTTP error creating Cursor agent",
            extra={
                "url": url,
                "status_code": e.response.status_code,
                "response_preview": response_preview,
                "payload_preview": payload_preview,
            },
            exc_info=True,
        )
        http_error = RuntimeError(error_text)
        http_error.status_code = e.response.status_code
        http_error.response_text = e.response.text
        raise http_error from e
    except httpx.RequestError as e:
        logger.error(
            "Network error creating Cursor agent",
            extra={
                "url": url,
                "error": str(e),
                "payload_preview": payload_preview,
            },
            exc_info=True,
        )
        raise RuntimeError(f"Request failed: {str(e)}") from e


async def get_cursor_agent_status(agent_id: str) -> dict:
    api_key = CursorConfig.API_KEY
    base_url = CursorConfig.BASE_URL

    if not api_key:
        raise ValueError("CURSOR_API_KEY not configured in .env")

    url = f"{base_url}/v0/agents/{agent_id}"

    logger.debug("Getting Cursor agent status", extra={"agent_id": agent_id, "url": url})

    try:
        async with httpx.AsyncClient(auth=(api_key, ""), timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            logger.debug(
                "Cursor agent status retrieved",
                extra={
                    "agent_id": agent_id,
                    "status": data.get("status", "unknown"),
                },
            )

            return data

    except httpx.HTTPStatusError as e:
        error_text = f"HTTP {e.response.status_code}: {e.response.text}"
        response_preview = e.response.text[:200] if e.response.text else ""
        logger.error(
            "HTTP error getting Cursor agent status",
            extra={
                "agent_id": agent_id,
                "url": url,
                "status_code": e.response.status_code,
                "response_preview": response_preview,
            },
            exc_info=True,
        )
        http_error = RuntimeError(error_text)
        http_error.status_code = e.response.status_code
        http_error.response_text = e.response.text
        raise http_error from e
    except httpx.RequestError as e:
        logger.error(
            "Network error getting Cursor agent status",
            extra={
                "agent_id": agent_id,
                "url": url,
                "error": str(e),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Request failed: {str(e)}") from e


async def create_devflow_step_agent(
    chat_id: str,
    flow_id: str,
    step: int,
    step_prompt: str,
) -> str:
    """Создать Cursor-агента для конкретного шага DevFlow и привязать его к DevAgentStore.
    Возвращает agent_id (строка).
    
    Args:
        chat_id: ID чата Telegram
        flow_id: ID DevFlow сессии
        step: Номер шага (1-based)
        step_prompt: Текст задачи для этого шага
    
    Returns:
        agent_id: ID созданного Cursor агента
    """
    logger.info(
        "DevFlow: creating Cursor agent for flow_id=%s step=%s (chat_id=%s)",
        flow_id, step, chat_id
    )
    
    # Строим системный промпт для DevFlow с подстановкой задачи шага
    devflow_system_prompt = build_devflow_system_prompt(step_prompt)
    
    # Формируем task_text (может быть пустым или содержать дополнительный контекст)
    task_text = f"[DevFlow simple_ma | flow_id={flow_id} | step={step}]"

    # DevFlow runs in "dev mode": we want agents to commit directly to the base branch
    # (CursorConfig.BASE_REF, typically "main") instead of opening PRs in cursor/* branches.
    result = await create_cursor_agent(
        task_text=task_text,
        auto_create_pr=False,  # DevFlow: commit directly to base_ref (e.g. main), no PR
        system_prompt=devflow_system_prompt,
    )

    # Регистрируем агента в DevAgentStore с флагами DevFlow
    store = get_dev_agent_store()
    try:
        store.register(
            agent_id=result.id,
            chat_id=chat_id,
            original_text=f"DevFlow simple_ma flow_id={flow_id} step={step}",
            dev_task=step_prompt,
            is_devflow=True,
            flow_type="simple_ma",
            step_index=step - 1,  # step приходит 1-based, step_index должен быть 0-based
        )
        logger.info(
            "DevFlow: registered agent_id=%s for flow_id=%s step=%s chat_id=%s",
            result.id, flow_id, step, chat_id
        )
    except Exception as e:
        logger.error(
            "Failed to register DevFlow agent in DevAgentStore",
            extra={
                "agent_id": result.id,
                "chat_id": chat_id,
                "flow_id": flow_id,
                "step": step,
                "error": str(e),
            },
            exc_info=True,
        )

    return result.id
