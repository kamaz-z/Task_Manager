from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base,Time_Stamp


class User(Time_Stamp, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))