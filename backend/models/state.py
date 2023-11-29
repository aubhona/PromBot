from sqlalchemy import Column, String
from sqlalchemy.types import Enum as SQLAlchemyEnum
from backend.database import Base
from backend.models.respond_state import RespondState


class State(Base):
    __tablename__ = 'states'

    nickname = Column(String, primary_key=True)
    state = Column(SQLAlchemyEnum(RespondState))
    last_seen = Column(String)

    def __repr__(self) -> str:
        return f"@{self.nickname}"
