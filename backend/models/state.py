from sqlalchemy import Column, String, Integer, Tuple
from sqlalchemy.types import Enum as SQLAlchemyEnum
from backend.database import Base
from backend.models.respond_state import RespondState


class State(Base):
    __tablename__ = 'states'

    nickname = Column(String, primary_key=True)
    state = Column(SQLAlchemyEnum(RespondState), index=True)
    last_seen = Column(String)
    chat_id = Column(Integer)
    filter_value = Column(Integer)

    def __repr__(self) -> str:
        return f"@{self.nickname}"
