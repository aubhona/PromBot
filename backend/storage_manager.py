from backend.models.user import User
from backend.models.state import State
from backend.database import Session


def get_user_by_nick(user_nickname):
    session = Session()
    try:
        return session.query(User).filter(User.nickname == user_nickname).first()
    finally:
        session.close()


def get_active_users(gender):
    session = Session()
    try:
        return session.query(User).filter(User.is_active and User.gender == (not gender)).all()
    finally:
        session.close()


def get_user_state(user_nickname):
    session = Session()
    try:
        user_state = session.query(State).filter(State.nickname == user_nickname).first()
        return user_state
    finally:
        session.close()


def set_user_state(user_nickname, state, last_seen=None):
    session = Session()
    try:
        user_state = session.query(State).filter(State.nickname == user_nickname).first()
        if not user_state:
            session.add(State(nickname=user_nickname, state=state, last_seen=last_seen))
            session.commit()
            return
        user_state.state = state
        if last_seen is not None:
            user_state.last_seen = last_seen
        session.commit()
    finally:
        session.close()


def add_user(new_user):
    session = Session()
    try:
        user = session.query(User).filter(User.nickname == new_user.nickname).first()
        if user is None:
            session.add(new_user)
            session.commit()
            return
        user.set_other(new_user)
        session.commit()
    finally:
        session.close()


def get_active_user(gender, last_seen):
    session = Session()
    try:
        if last_seen is None:
            last_seen = chr(0)
        return session.query(User).where(User.is_active and User.gender ==
                                         (not gender)).order_by(User.nickname).where(User.nickname > last_seen).first()
    finally:
        session.close()


def set_user_name(nickname, name):
    user = User(nickname=nickname, name=name[1], surname=name[0])
    add_user(user)


def set_user_gender(nickname, gender):
    user = User(nickname=nickname, gender=gender)
    add_user(user)


def set_user_height(nickname, height):
    user = User(nickname=nickname, height=height)
    add_user(user)


def set_user_faculty(nickname, faculty):
    user = User(nickname=nickname, faculty=faculty)
    add_user(user)


def set_user_image_path(nickname, image_path):
    user = User(nickname=nickname, image_path=image_path, is_active=True)
    add_user(user)
