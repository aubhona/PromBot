from cachetools import LRUCache
from sqlalchemy import and_, func
from sqlalchemy.future import select

from backend.database import *
from backend.models.respond_state import *
from backend.models.state import State
from backend.models.user import User

user_state_cache = LRUCache(maxsize=250)


async def get_user_by_nick(user_nickname):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.nickname == user_nickname)
        )
        return result.scalars().first()


async def get_users():
    async with async_session() as session:
        result = await session.execute(select(User))
        return result.scalars().all()


async def get_states():
    async with async_session() as session:
        result = await session.execute(select(State))
        return result.scalars().all()


def invalidate_user_state(user_nickname):
    user_state_cache.pop(user_nickname, None)


async def get_user_state(user_nickname):
    if user_nickname in user_state_cache:
        return user_state_cache[user_nickname]
    async with async_session() as session:
        result = await session.execute(
            select(State).where(State.nickname == user_nickname)
        )
        user_state_cache[user_nickname] = result.scalars().first()
        return user_state_cache[user_nickname]


async def set_user_state(user_nickname, state, chat_id, last_seen=None, filter_value=None):
    async with async_session() as session:
        result = await session.execute(
            select(State).where(State.nickname == user_nickname)
        )
        user_state = result.scalars().first()
        invalidate_user_state(user_nickname)
        if user_state is not None and filter_value is None:
            filter_value = user_state.filter_value
        if user_state is None and filter_value is None:
            filter_value = 16
        if not user_state:
            session.add(State(nickname=user_nickname, state=state, chat_id=chat_id, last_seen=last_seen,
                              filter_value=filter_value))
            await session.commit()
            return
        user_state.state = state
        if last_seen is not None:
            user_state.last_seen = last_seen
        if filter_value is not None:
            user_state.filter_value = filter_value
        await session.commit()


async def add_user(new_user):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.nickname == new_user.nickname)
        )
        user = result.scalars().first()
        if user is None:
            session.add(new_user)
            await session.commit()
            return
        user.set_other(new_user)
        await session.commit()
        return


async def get_active_user(gender, last_seen, min_course=1, max_course=7):
    async with async_session() as session:
        if last_seen is None:
            last_seen = chr(0)
        result = await session.execute(
            select(User).where(and_(User.course >= min_course, User.course <= max_course, User.is_active,
                                    (User.gender == (not gender)), User.nickname > last_seen)).order_by(User.nickname))
        return result.scalars().first()


async def get_profiles():
    async with async_session() as session:
        result = await session.execute(
            select(State).where(State.state == RespondState.WAIT_FOR_ALLOW)
        )
        return result.scalars().all()


async def set_user_name(nickname, name):
    user = User(nickname=nickname, name=name[1], surname=name[0])
    await add_user(user)


async def set_user_course(nickname, course):
    user = User(nickname=nickname, course=course)
    await add_user(user)


async def set_user_brief_info(nickname, brief_info):
    user = User(nickname=nickname, brief_info=brief_info)
    await add_user(user)


async def set_user_gender(nickname, gender):
    user = User(nickname=nickname, gender=gender)
    await add_user(user)


async def set_user_height(nickname, height):
    user = User(nickname=nickname, height=height)
    await add_user(user)


async def set_user_faculty(nickname, faculty):
    user = User(nickname=nickname, faculty=faculty.upper())
    await add_user(user)


async def set_user_image_path(nickname, image_path):
    user = User(nickname=nickname, image_path=image_path, is_active=False)
    await add_user(user)


async def count_total():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).select_from(User)
        )
        return result.scalar()


async def count_total_active():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).where(User.is_active == True).select_from(User)
        )
        return result.scalar()


async def count_total_men():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).where(User.gender == True).select_from(User)
        )
        return result.scalar()


async def count_total_women():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).where(User.gender == False).select_from(User)
        )
        return result.scalar()


async def count_total_men_active():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).where(and_(User.gender, User.is_active)).select_from(User)
        )
        return result.scalar()


async def count_total_women_active():
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).where(and_((not User.gender), User.is_active)).select_from(User)
        )
        return result.scalar()
