import logging

from fastapi import APIRouter, HTTPException

from orchestrator.config import OrchestratorConfig, CursorConfig
from orchestrator.integrations.cursor_client import CursorClient

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/test_launch")
async def test_launch():
    try:
        api_key = OrchestratorConfig.CURSOR_API_KEY
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="CURSOR_API_KEY not configured in OrchestratorConfig"
            )

        repository = CursorConfig.REPOSITORY
        if not repository:
            raise HTTPException(
                status_code=500,
                detail="CURSOR_REPOSITORY not configured. Set CURSOR_REPOSITORY in .env"
            )

        async with CursorClient(api_key=api_key) as client:
            result = await client.launch_agent(
                prompt_text="orchestrator test",
                repository=repository,
            )
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in test_launch: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to launch Cursor agent: {str(e)}"
        )

