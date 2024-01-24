from sqlalchemy import Column, String, Boolean, Float, Integer
from backend.database import Base


class User(Base):
    __tablename__ = 'users'

    nickname = Column(String(255), primary_key=True)
    name = Column(String(255))
    surname = Column(String(255))
    height = Column(Float)
    gender = Column(Boolean)
    image_path = Column(String(255), unique=True)
    faculty = Column(String(255))
    is_active = Column(Boolean, index=True)
    course = Column(Integer, index=True)
    brief_info = Column(String(500))

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
