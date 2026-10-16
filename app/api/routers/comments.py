from fastapi import APIRouter, status
from app.api.deps import CurrentUser, DbSession
from app.schemas.comment import CommentCreate, CommentRead
from app.services import comment_service

router = APIRouter(prefix="/tasks", tags=["comments"])


@router.post(
    "/{task_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    task_id: int, data: CommentCreate, db: DbSession, user: CurrentUser
):
    return await comment_service.add_comment(db, task_id, data, user)


@router.get("/{task_id}/comments", response_model=list[CommentRead])
async def list_comments(task_id: int, db: DbSession, user: CurrentUser):
    return await comment_service.list_comments(db, task_id)