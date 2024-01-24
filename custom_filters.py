from aiogram import types
from aiogram.filters import Filter
from backend.storage_manager import get_user_state


class StateFilter(Filter):
    def __init__(self, required_states, predicate):
        self.required_states = required_states
        self.predicate = predicate

    async def __call__(self, message: types.Message) -> bool:
        user_state = await get_user_state(message.from_user.username)
        return self.predicate(self.required_states, user_state.state)


class CallBackStateFilter(Filter):
    def __init__(self, required_states, predicate):
        self.required_states = required_states
        self.predicate = predicate

    async def __call__(self, call: types.CallbackQuery) -> bool:
        user_state = await get_user_state(call.from_user.username)
        return self.predicate(self.required_states, user_state.state, call.data)
