from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Comment, User
from app.schemas.comment import CommentCreate
from app.services.task_service import get_task


async def add_comment(
    db: AsyncSession, task_id: int, data: CommentCreate, user: User) -> Comment:
    await get_task(db, task_id)

    comment = Comment(task_id=task_id, author_id=user.id, text=data.text)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def list_comments(db: AsyncSession, task_id: int) -> list[Comment]:
    await get_task(db, task_id)

    result = await db.scalars(
        select(Comment)
        .where(Comment.task_id == task_id)
        .order_by(Comment.created_at, Comment.id)
    )
    return list(result.all())