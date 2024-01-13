from sqlalchemy import Column, String, Boolean, Double, Integer
from backend.database import Base


class User(Base):
    __tablename__ = 'users'

    nickname = Column(String, primary_key=True)
    name = Column(String)
    surname = Column(String)
    height = Column(Double)
    gender = Column(Boolean)
    image_path = Column(String, unique=True)
    faculty = Column(String)
    is_active = Column(Boolean, index=True)
    course = Column(Integer, index=True)
    brief_info = Column(String)

    def __repr__(self) -> str:
        return f"@{self.nickname}"

    def set_other(self, other):
        if other.name is not None:
            self.name = other.name
        if other.surname is not None:
            self.surname = other.surname
        if other.height is not None:
            self.height = other.height
        if other.gender is not None:
            self.gender = other.gender
        if other.image_path is not None:
            self.image_path = other.image_path
        if other.faculty is not None:
            self.faculty = other.faculty
        if other.is_active is not None:
            self.is_active = other.is_active
        if other.course is not None:
            self.course = other.course
        if other.brief_info is not None:
            self.brief_info = other.brief_info
