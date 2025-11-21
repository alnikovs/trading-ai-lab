from fastapi import APIRouter


router = APIRouter()


@router.get("/ping-dev")
async def ping_dev():
    """Health check endpoint for development environments."""
    return {"status": "dev-ok"}
