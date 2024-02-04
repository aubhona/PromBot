import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, methods, filters
from aiogram.utils.backoff import BackoffConfig

import backend.database
import backend.storage_manager as storage_manager
from backend import parser
from backend.models.user import User
from backend.storage_manager import set_user_name, set_user_gender, set_user_height
from backend.models.respond_state import RespondState
from config import *
from custom_filters import *

dp = Dispatcher()
bot = Bot(token=API_KEY)


@dp.message(filters.command.Command("help"))
async def help_user(message: types.Message):
    if message.text == "/help":
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id,
                                                   text="Отправьте вместе с /help через пробел сообщение для тех. поддержки."))
        return
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append(
        [types.InlineKeyboardButton(text="Ответить", callback_data=f"answer_{str(message.chat.id)}")])
    await bot(methods.send_message.SendMessage(chat_id=ADMIN_CHAT_ID,
                                               text=f"Пиcьмо помощи от @{message.from_user.username}\n{message.text[6:]}",
                                               reply_markup=markup))
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id,
                                               text="Мы отправили ваше сообщение в тех. поддержку. Вам придёт ответное письмо."))


@dp.message(filters.command.Command("start", "restart"))
async def send_welcome(message: types.Message):
    await start_reg(message.chat.id, message.from_user.username)


@dp.message(filters.command.Command("admin"))
async def admin_log(message: types.Message):
    if message.text[7:] == PASSWORD:
        task = bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Админка выдана."))
        await storage_manager.set_user_state(message.from_user.username, RespondState.ADMIN, message.chat.id)
        await task
        return
    task = bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Неправильный пароль от админки!"))
    user = await storage_manager.get_user_by_nick(message.from_user.username)
    if user is not None and user.is_active:
        await show_menu(message.chat.id, message.from_user.username)
    else:
        await storage_manager.set_user_state(message.from_user.username, RespondState.WAIT_FOR_CREATING,
                                             message.chat.id)
    await task


@dp.message(StateFilter({}, lambda user_states, user_state: user_state is None))
async def greeting(message: types.Message):
    await start_reg(message.chat.id, message.from_user.username)


@dp.callback_query(CallBackStateFilter({}, lambda user_states, user_state, _: user_state is None))
async def greeting_c(call: types.CallbackQuery):
    await start_reg(call.message.chat.id, call.from_user.username)


@dp.callback_query(
    CallBackStateFilter({RespondState.ADMIN},
                        lambda user_states, user_state, data: data.startswith("answer") and user_state in user_states))
async def answer_help_user_1(call: types.CallbackQuery):
    await storage_manager.set_user_state(call.from_user.username, RespondState.ADMIN, call.message.chat.id,
                                         last_seen=call.data[7:])
    await bot(methods.send_message.SendMessage(chat_id=int(call.message.chat.id),
                                               text=f"Напишите сообщение для пользователя."))


@dp.message(filters.and_f(filters.command.Command("mes"),
                          StateFilter({RespondState.ADMIN}, lambda user_states, user_state: user_state in user_states)))
async def answer_help_user_2(message: types.Message):
    await bot(methods.send_message.SendMessage(
        chat_id=int((await storage_manager.get_user_state(message.from_user.username)).last_seen),
        text=f"Письмо от тех. поддержки:\n{message.text[5:]}"))
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Пиьсмо успешно отправлено"))


@dp.message(filters.and_f(filters.command.Command("message"),
                          StateFilter({RespondState.ADMIN}, lambda user_states, user_state: user_state in user_states)))
async def message_user(message: types.Message):
    username = message.text.split(' ')[1]
    message_text = ' '.join(message.text.split(' ')[2:])
    user_state_task = storage_manager.get_user_state(username)
    await bot(methods.send_message.SendMessage(chat_id=(await user_state_task).chat_id, text=message_text))
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Сообщение успешно отправлено!"))


@dp.message(filters.and_f(filters.command.Command("form"),
                          StateFilter({RespondState.ADMIN}, lambda user_states, user_state: user_state in user_states)))
async def message_user(message: types.Message):
    username = message.text.split(' ')[1]
    user_state_task = storage_manager.get_user_state(username)
    user_task = storage_manager.get_user_state(username)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    user = await user_task
    user_state = await user_state_task
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Забанить", callback_data=f"decline_{user.nickname}")])
    await send_form(user, markup, user_state.chat_id, True)


@dp.message(filters.and_f(filters.command.Command("stats"),
                          StateFilter({RespondState.ADMIN}, lambda user_states, user_state: user_state in user_states)))
async def message_user(message: types.Message):
    total = storage_manager.count_total()
    total_active = storage_manager.count_total_active()
    total_men = storage_manager.count_total_men()
    total_women = storage_manager.count_total_women()
    total_active_men = storage_manager.count_total_men_active()
    total_active_women = storage_manager.count_total_women_active()
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id, text=f"Всего зарегистрированных пользователей: {await total}\nВсего активных: {await total_active}\nВсего парней: {await total_men}\nВсего девушек: {await total_women}\nВсего активных анкет парней: {await total_active_men}\nВсего активных анкет девушек: {await total_active_women}"))


@dp.message(filters.and_f(filters.command.Command("show"),
                          StateFilter({RespondState.ADMIN}, lambda user_states, user_state: user_state in user_states)))
async def show_profiles(message: types.Message):
    profiles = await storage_manager.get_profiles()
    if profiles is None or len(profiles) == 0:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Анкет на модерацию пока нет."))
        return
    for profile in profiles:
        await show_procfile((await storage_manager.get_user_by_nick(profile.nickname)), message.chat.id)


@dp.callback_query(CallBackStateFilter({RespondState.ADMIN}, lambda user_states, user_state,
                                                                    data: data.startswith("allow") and user_state
                                                                          in user_states))
async def allow(call: types.CallbackQuery):
    username = call.data[6:]
    task1 = bot(
        methods.send_message.SendMessage(chat_id=call.message.chat.id, text=f"Анкета @{username} успешно одобрена!"))
    user_state_task = storage_manager.get_user_state(username)
    user_task = storage_manager.get_user_by_nick(username)
    user_state = await user_state_task
    if user_state.state != RespondState.WAIT_FOR_ALLOW:
        return
    task2 = bot(
        methods.send_message.SendMessage(chat_id=user_state.chat_id, text="Ваше объявление было успешно напечатано!"))
    await storage_manager.set_user_state(username, RespondState.WAIT_FOR_FIND, user_state.chat_id)
    task3 = show_form((await user_task), user_state.chat_id)
    task4 = storage_manager.add_user(User(nickname=username, is_active=True))
    await task1
    await task2
    await task3
    await task4


@dp.callback_query(CallBackStateFilter({RespondState.ADMIN}, lambda user_states, user_state,
                                                                    data: data.startswith("decline") and user_state
                                                                          in user_states))
async def decline_mes(call: types.CallbackQuery):
    username = call.data[8:]
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                text=f"Напишите причину отклонение анкеты пользователя @{username}."))
    await storage_manager.set_user_state(call.from_user.username, RespondState.ADMIN, call.message.chat.id, username)
    await task


@dp.message(filters.and_f(filters.command.Command("decline"), StateFilter({RespondState.ADMIN},
                                                                          lambda user_states, user_state: user_state
                                                                                                          in user_states)))
async def decline(message: types.Message):
    admin_user_state = await storage_manager.get_user_state(message.from_user.username)
    username = admin_user_state.last_seen
    task4 = storage_manager.add_user(User(nickname=username, is_active=False))
    user_task = storage_manager.get_user_by_nick(username)
    task1 = bot(
        methods.send_message.SendMessage(chat_id=message.chat.id, text=f"Анкета @{username} успешно отклонена!"))
    user_state = await storage_manager.get_user_state(username)
    task2 = bot(methods.send_message.SendMessage(chat_id=user_state.chat_id,
                                                 text=f"Ваше объявление, к сожалению, не напечатали.\nПо причине:\n{message.text[9:].capitalize()}\n"
                                                      + "Перепишите своё объявление!"))
    await storage_manager.set_user_state(username, RespondState.WAIT_FOR_CREATING, user_state.chat_id)
    task3 = show_only_form((await user_task), user_state.chat_id)
    await task1
    await task2
    await task3
    await task4
    await start_reg(user_state.chat_id, username)


@dp.message(filters.and_f(filters.command.Command("menu"), StateFilter({RespondState.ADMIN,
                                                                        RespondState.WAIT_MENU,
                                                                        RespondState.WAIT_FOR_FIND},
                                                                       lambda user_states, user_state: user_state
                                                                                                       in user_states)))
async def menu_m(message: types.Message):
    await show_menu(message.chat.id, message.from_user.username)


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND, RespondState.WAIT_CHANGE},
                                       lambda user_states, user_state,
                                              data: data == "menu" and user_state
                                                    in user_states))
async def menu_c(call: types.CallbackQuery):
    await show_menu(call.message.chat.id, call.from_user.username)


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_FOR_CREATING}, lambda user_states, user_state, _: user_state
                                                                                                            in user_states))
async def input_name_c(call: types.CallbackQuery):
    await send_input_name(call.message.chat.id, call.from_user.username)


@dp.message(StateFilter({RespondState.WAIT_FOR_CREATING}, lambda user_states, user_state: user_state in user_states))
async def input_name_m(message: types.Message):
    await send_input_name(message.chat.id, message.from_user.username)


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_MENU, RespondState.WAIT_CHANGE},
                                       lambda user_states, user_state,
                                              data: data == "change_form" and user_state
                                                    in user_states))
async def change_form_confirm(call: types.CallbackQuery):
    if (await storage_manager.get_user_state(call.from_user.username)).state == RespondState.WAIT_MENU:
        task1 = storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_CHANGE, call.message.chat.id)
        markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
        markup.inline_keyboard.append([types.InlineKeyboardButton(text="✅", callback_data="change_form"),
                                       types.InlineKeyboardButton(text="❌", callback_data="menu")])
        task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                    text="Вы уверены, что хотите внести изменения в объявление? (Оно отправится на перепечать, что займёт время).",
                                                    reply_markup=markup))
        await task1
        await task
        return
    await storage_manager.add_user(User(nickname=call.from_user.username, is_active=False))
    await send_input_name(call.message.chat.id, call.from_user.username)


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_FIO}, lambda user_states, user_state: user_state in user_states))
async def input_gender_set_name_m(message: types.Message):
    fio = parser.parse_fio(message.text)
    if fio is None:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, reply_to_message_id=message.message_id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_choose_gender(message.chat.id, message.from_user.username)
    await set_user_name(nickname=message.from_user.username, name=fio)
    await task


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_FOR_CREATING_FIO}, lambda user_states, user_state, _: user_state
                                                                                                 in user_states))
async def input_gender_c(call: types.CallbackQuery):
    await send_input_name(call.message.chat.id, call.from_user.username)


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_FOR_CREATING_GENDER}, lambda user_states, user_state, _: user_state
                                                                                                    in user_states))
async def input_height_set_gender_c(call: types.CallbackQuery):
    task = send_input_height(call.message.chat.id, call.from_user.username)
    await set_user_gender(nickname=call.from_user.username, gender=call.data == "True")
    await task


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_GENDER}, lambda user_states, user_state: user_state in user_states))
async def input_height_m(message: types.Message):
    await send_choose_gender(message.chat.id, message.from_user.username)


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_HEIGHT}, lambda user_states, user_state: user_state in user_states))
async def input_brief_info_set_height_m(message: types.Message):
    height = parser.parse_height(message.text)
    if height is None:
        await bot(methods.send_message.SendMessage(reply_to_message_id=message.message_id, chat_id=message.chat.id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_input_brief_info(message.chat.id, message.from_user.username)
    await set_user_height(message.from_user.username, height)
    await task


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_FOR_CREATING_HEIGHT}, lambda user_states, user_state, _: user_state
                                                                                                    in user_states))
async def intput_height_c(call: types.CallbackQuery):
    await send_input_height(call.message.chat.id, call.from_user.username)


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_INFO}, lambda user_states, user_state: user_state in user_states))
async def input_faculty_set_info_m(message: types.Message):
    if message.text is None or len(message.text) == 0:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, reply_to_message_id=message.message_id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_input_faculty(message.chat.id, message.from_user.username)
    await storage_manager.set_user_brief_info(message.from_user.username, message.text)
    await task


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_FOR_CREATING_INFO}, lambda user_states, user_state, _: user_state
                                                                                                  in user_states))
async def input_faculty_c(call: types.CallbackQuery):
    await send_input_brief_info(call.message.chat.id, call.from_user.username)


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_FACULTY}, lambda user_states, user_state: user_state in user_states))
async def input_course_set_faculty_m(message: types.Message):
    if message.text is None or len(message.text) == 0:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, reply_to_message_id=message.message_id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_input_course(message.chat.id, message.from_user.username)
    await storage_manager.set_user_faculty(message.from_user.username, message.text)
    await task


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_FOR_CREATING_COURSE},
                                       lambda user_states, user_state, data: data in {"1", "2", "3", "4", "5", "6",
                                                                                      "7"} and
                                                                             user_state in user_states)
                   )
async def input_image_set_course_m(call: types.CallbackQuery):
    await storage_manager.set_user_course(call.from_user.username, int(call.data))
    task = send_input_image(call.message.chat.id, call.from_user.username)
    await task


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_FOR_CREATING_COURSE}, lambda user_states, user_state, _: user_state
                                                                                                    in user_states))
async def input_course_c(call: types.CallbackQuery):
    await send_input_course(call.message.chat.id, call.from_user.username)


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_COURSE}, lambda user_states, user_state: user_state in user_states))
async def input_course_m(message: types.Message):
    await send_input_course(message.chat.id, message.from_user.username)


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_IMAGE}, lambda user_states, user_state: user_state in user_states))
async def set_image(message: types.Message):
    if message.content_type != types.ContentType.PHOTO:
        await send_input_image(message.chat.id, message.from_user.username)
        return
    image_task = bot(methods.get_file.GetFile(file_id=message.photo[-2].file_id))
    path = os.path.join('PromBot', 'static', 'user_images', f"{message.from_user.username}.jpg")
    task1 = storage_manager.set_user_image_path(message.from_user.username, path)
    user_task = storage_manager.get_user_by_nick(message.from_user.username)
    downloaded_image_task = bot.download((await image_task), destination=path)
    task = send_form_finish(message.chat.id, message.from_user.username)
    user = await user_task
    user.image_path = path
    await task1
    await downloaded_image_task
    await task
    await show_only_form(user, message.chat.id)
    await show_procfile(user, ADMIN_CHAT_ID)


@dp.message(
    StateFilter({RespondState.WAIT_FOR_CREATING_IMAGE}, lambda user_states, user_state: user_state in user_states))
async def set_image(message: types.Message):
    await send_input_image(message.chat.id, message.from_user.username)


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_FOR_CREATING_IMAGE},
                        lambda user_states, user_state, _: user_state in user_states))
async def set_image_c(call: types.CallbackQuery):
    await send_input_image(call.message.chat.id, call.from_user.username)


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_FOR_FIND, RespondState.ADMIN}, lambda user_states, user_state,
                                                                                                data: data == "find" and user_state in user_states))
async def find(call: types.CallbackQuery):
    user = await storage_manager.get_user_by_nick(call.from_user.username)
    user_state = await storage_manager.get_user_state(user.nickname)
    new_user = await storage_manager.get_active_user(user.gender, user_state.last_seen, user_state.filter_value // 10,
                                                     user_state.filter_value % 10)
    if new_user is None:
        task1 = bot(
            methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                             text="Вы просмотрели все объявления, поэтому сводки будут показаны повторно."))
        user_state.last_seen = None
        new_user = await storage_manager.get_active_user(user.gender, user_state.last_seen,
                                                         user_state.filter_value // 10,
                                                         user_state.filter_value % 10)
        await task1
    if new_user is None:
        await bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                   text="Сейчас нет объявлений. Попробуйте позже."))
        await show_menu(call.message.chat.id, user.nickname)
        return
    task = show_user(new_user, call.message.chat.id)
    await storage_manager.set_user_state(user.nickname, user_state.state, call.message.chat.id, new_user.nickname)
    await task


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_MENU}, lambda user_states, user_state,
                                                         data: data == "find" and user_state in user_states))
async def find_menu(call: types.CallbackQuery):
    call_back = types.CallbackQuery(data="find", message=call.message, from_user=call.from_user, id="",
                                    chat_instance="", json_string=None)
    await storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND, call.message.chat.id)
    await find(call_back)


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND}, lambda user_states, user_state,
                                                                                     data: data == "deactivate" and user_state in user_states))
async def deactivate_user(call: types.CallbackQuery):
    task1 = storage_manager.set_user_state(call.from_user.username, RespondState.DEACTIVATE, call.message.chat.id)
    task2 = storage_manager.add_user(User(nickname=call.from_user.username, is_active=False))
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append(
        [types.InlineKeyboardButton(text="Показывать моё объявление", callback_data="activate")])
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Ваше объявление изъято.",
                                                reply_markup=markup))
    await task1
    await task2
    await task


@dp.callback_query(
    CallBackStateFilter({RespondState.DEACTIVATE},
                        lambda user_states, user_state, data: data == "activate" and user_state in user_states))
async def activate_user(call: types.CallbackQuery):
    user_task = storage_manager.get_user_by_nick(call.from_user.username)
    task2 = storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND, call.message.chat.id)
    task3 = storage_manager.add_user(User(nickname=call.from_user.username, is_active=True))
    task = bot(
        methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Ваше объявление теперь показывается."))
    task1 = show_form((await user_task), call.message.chat.id)
    await task2
    await task3
    await task
    await task1


@dp.callback_query(
    CallBackStateFilter({RespondState.DEACTIVATE}, lambda user_states, user_state, _: user_state in user_states))
async def deactivated_user_mes(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append(
        [types.InlineKeyboardButton(text="Показывать моё объявление", callback_data="activate")])
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Ваше объявление изъято.",
                                                reply_markup=markup))
    await task


@dp.message(
    StateFilter({RespondState.DEACTIVATE}, lambda user_states, user_state: user_state in user_states))
async def deactivated_user_mes(message: types.Message):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append(
        [types.InlineKeyboardButton(text="Показывать моё объявление", callback_data="activate")])
    task = bot(
        methods.send_message.SendMessage(chat_id=message.chat.id, text="Ваше объявление изъято.", reply_markup=markup))
    await task


@dp.message(
    StateFilter({RespondState.WAIT_FOR_ALLOW}, lambda user_states, user_state: user_state in user_states))
async def wait_allow_action(message: types.Message):
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id,
                                               text="Ваше объявление в печати. Как только его одобрят, я Вас уведомлю."))


@dp.callback_query(
    CallBackStateFilter({RespondState.WAIT_FOR_ALLOW}, lambda user_states, user_state, _: user_state
                                                                                          in user_states))
async def wait_allow_action_c(call: types.CallbackQuery):
    await bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                               text="Ваше объявление в печати. Как только его одобрят, я Вас уведомлю."))


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_MENU, RespondState.ADMIN}, lambda user_states, user_state,
                                                                                            data: data == "filter" and user_state in user_states))
async def input_filter(call: types.CallbackQuery):
    user_state_task = storage_manager.get_user_state(call.from_user.username)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="✅", callback_data='change_filter'),
                                   types.InlineKeyboardButton(text="❌", callback_data='find')])
    user_state = await user_state_task
    await bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                               text=f"Вам показаны объявления от {user_state.filter_value // 10} "
                                                    + f"до {user_state.filter_value % 10} курса. Хотите изменить выборку?",
                                               reply_markup=markup))


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_MENU, RespondState.ADMIN}, lambda user_states, user_state,
                                                                                            data: data == "change_filter" and user_state in user_states))
async def change_filter(call: types.CallbackQuery):
    task1 = storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CHANGE_FILTER_1,
                                           call.message.chat.id)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    for i in range(1, 8):
        if i <= 6:
            markup.inline_keyboard.append([types.InlineKeyboardButton(text=str(i), callback_data=str(i))])
            continue
        markup.inline_keyboard.append([types.InlineKeyboardButton(text="6+", callback_data=str(i))])

    task = bot(
        methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Выберите минимальный курс для просмотра.",
                                         reply_markup=markup))
    await task1
    await task


@dp.callback_query(CallBackStateFilter({RespondState.ADMIN, RespondState.WAIT_FOR_CHANGE_FILTER_1},
                                       lambda user_states, user_state, data: data in {"1", "2", "3", "4", "5", "6",
                                                                                      "7"} and
                                                                             user_state in user_states))
async def process_select_min(call: types.CallbackQuery):
    min_course = int(call.data)
    task1 = storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CHANGE_FILTER_2,
                                           call.message.chat.id,
                                           filter_value=f"{min_course}7")
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    for i in range(min_course, 8):
        if i <= 6:
            markup.inline_keyboard.append([types.InlineKeyboardButton(text=str(i), callback_data=str(i))])
            continue
        markup.inline_keyboard.append([types.InlineKeyboardButton(text="6+", callback_data=str(i))])

    task = bot(
        methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                         text=f"Теперь выберите максимальный курс для просмотра.",
                                         reply_markup=markup))
    await task1
    await task


@dp.callback_query(CallBackStateFilter({RespondState.ADMIN, RespondState.WAIT_FOR_CHANGE_FILTER_2},
                                       lambda user_states, user_state, data: data in {"1", "2", "3", "4", "5", "6",
                                                                                      "7"} and
                                                                             user_state in user_states))
async def process_select_max(call: types.CallbackQuery):
    max_course = int(call.data)
    user_state = await storage_manager.get_user_state(call.from_user.username)
    max_course = max(max_course, user_state.filter_value // 10)
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                text=f"Вам показаны объявления {user_state.filter_value // 10} "
                                                     + f"- {max_course} курса."))
    if user_state.state == RespondState.WAIT_FOR_CHANGE_FILTER_2:
        await storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND,
                                             call.message.chat.id,
                                             filter_value=f"{user_state.filter_value // 10}{max_course}")
    task1 = find(call)
    await task
    await task1


@dp.callback_query(CallBackStateFilter({RespondState.WAIT_FOR_CHANGE_FILTER_1, RespondState.WAIT_FOR_CHANGE_FILTER_2},
                                       lambda user_states, user_state, _: user_state in user_states))
async def unknown_filter_call(call: types.CallbackQuery):
    user_state = await storage_manager.get_user_state(call.from_user.username)
    if user_state.state == RespondState.WAIT_FOR_CHANGE_FILTER_1:
        await change_filter(call)
        return
    call.data = str(user_state.filter_value // 10)
    await process_select_min(call)


@dp.message(StateFilter({RespondState.WAIT_FOR_CHANGE_FILTER_1, RespondState.WAIT_FOR_CHANGE_FILTER_2},
                        lambda user_states, user_state: user_state in user_states))
async def unknown_filter_message(message: types.Message):
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id,
                                               text="Отправьте правильное сообщение точно по инструкциям."))


@dp.callback_query(CallBackStateFilter({RespondState.ADMIN, RespondState.WAIT_FOR_FIND},
                                       lambda user_states, user_state, data: data.startswith("like") and
                                                                             user_state in user_states))
async def like_user(call: types.CallbackQuery):
    user_state = await storage_manager.get_user_state(call.data[6:])
    if user_state.state not in {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND,
                                RespondState.WAIT_FOR_CHANGE_FILTER_1,
                                RespondState.WAIT_FOR_CHANGE_FILTER_2, RespondState.WAIT_CHANGE}:
        await bot.send_message(chat_id=call.message.chat.id,
                               text="Пользователь в данный момент не активен. Вы не можете лайкнуть.")
        return
    user_task = storage_manager.get_user_by_nick(call.from_user.username)
    user = await user_task
    task1 = bot(
        methods.send_message.SendMessage(chat_id=user_state.chat_id,
                                         text=f"Вы приглянулись кое-кому, скорее напишите {('ему' if user.gender else 'ей')} весточку:"))
    task2 = show_user(user, user_state.chat_id)
    task3 = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                 text=f"Вы отдали свое сердце @{user_state.nickname}."))
    task4 = find(call)
    await task1
    await task2
    await task3
    await task4


@dp.callback_query()
async def anything(call: types.CallbackQuery):
    await bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                               text="Отправьте правильное сообщение точно по инструкциям."))


@dp.message()
async def anything(message: types.Message):
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id,
                                               text="Некорректное действие. Следуйте строго моим инструкциям."))


async def show_user(user, chat_id):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.row_width = 1
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Следующее объявление", callback_data="find")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Варианты действий", callback_data="menu")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(
        text=f"{'Приглянулась глазу' if not user.gender else 'Приглянулся глазу'}❤️", callback_data=f"like_{user}")])
    await send_form(user, markup, chat_id)


async def show_only_form(user, chat_id):
    remove_markup = types.ReplyKeyboardRemove()
    await send_form(user, remove_markup, chat_id)


async def show_form(user, chat_id):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Варианты действий", callback_data="menu")])
    await send_form(user, markup, chat_id)


async def show_procfile(user, chat_id):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Одоборить", callback_data=f"allow_{user.nickname}"),
                                   types.InlineKeyboardButton(text="Отклонить",
                                                              callback_data=f"decline_{user.nickname}")])
    await send_form(user, markup, chat_id, True)


async def show_menu(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_MENU, chat_id)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.row_width = 1
    markup.inline_keyboard.append([types.InlineKeyboardButton(text=f"{'Найти спутни(-ка/-цу)'}", callback_data="find")])
    markup.inline_keyboard.append(
        [types.InlineKeyboardButton(text="Переписать свое объявление", callback_data="change_form")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Изъять объявление", callback_data="deactivate")])
    markup.inline_keyboard.append(
        [types.InlineKeyboardButton(text="Установить выборку по году обучения", callback_data="filter")])
    task = bot(methods.send_message.SendMessage(chat_id=chat_id, text="Меню", reply_markup=markup))
    await task1
    await task


async def send_choose_gender(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_GENDER, chat_id)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Я кавалер", callback_data='True'),
                                   types.InlineKeyboardButton(text="Я дама", callback_data='False')])
    task = bot(methods.send_message.SendMessage(chat_id=chat_id, text="Выберите Ваш пол:", reply_markup=markup))
    await task1
    await task


async def send_input_name(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FIO, chat_id)
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(
        methods.send_message.SendMessage(chat_id=chat_id,
                                         text="Впишите Ваши фамилию и имя (именно в этом порядке через пробел):",
                                         reply_markup=remove_markup))
    await task1
    await task


async def send_input_height(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_HEIGHT, chat_id)
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(
        methods.send_message.SendMessage(chat_id=chat_id, text="Введите Ваш рост (в сантиметрах):",
                                         reply_markup=remove_markup))
    await task1
    await task


async def send_input_faculty(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FACULTY, chat_id)
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(methods.send_message.SendMessage(chat_id=chat_id,
                                                text="Напишите Ваш факультет и направление (например, ФКН ПИ):",
                                                reply_markup=remove_markup))
    await task1
    await task


async def send_input_image(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_IMAGE, chat_id)
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(methods.send_message.SendMessage(chat_id=chat_id,
                                                text="Отправьте фотоснимок для вашего объявления (именно как фотоснимок (не документом) и ровно один):",
                                                reply_markup=remove_markup))
    await task1
    await task


async def send_input_course(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_COURSE, chat_id)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="1", callback_data="1"),
                                   types.InlineKeyboardButton(text="2", callback_data="2"),
                                   types.InlineKeyboardButton(text="3", callback_data="3")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="4", callback_data="4"),
                                   types.InlineKeyboardButton(text="5", callback_data="5"),
                                   types.InlineKeyboardButton(text="6", callback_data="6")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Другое", callback_data="7")])
    task = bot(methods.send_message.SendMessage(chat_id=chat_id,
                                                text="Выберите номер вашего курса (если вы учтитесь на магистратуре 1 курса, "
                                                     + "то выбирайте 5 курс и т.д.)\nЕсли вы не находите свой курс (выпускник, сотрудник и т.д.), то выберите 'Другое'.",
                                                reply_markup=markup))
    await task1
    await task


async def send_form_finish(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_ALLOW, chat_id)
    markup = types.ReplyKeyboardRemove()
    task = bot(methods.send_message.SendMessage(chat_id=chat_id,
                                                text="Ваше объявление в печати. Как только его одобрят, я Вас уведомлю.",
                                                reply_markup=markup))
    await task1
    await task


async def send_form(user, markup, chat_id, gender=False):
    gender_info = ''
    if gender:
        gender_info = f"{('Пол: М' if user.gender else 'Пол: Ж') if gender else ''}\n"
    await bot(methods.send_photo.SendPhoto(chat_id=chat_id,
                                           photo=types.input_file.BufferedInputFile.from_file(user.image_path),
                                           caption=f"{user.name.capitalize()} " +
                                                   f"{user.surname.capitalize()}\nРост: {user.height}" +
                                                   f" см.\nО себе:\n{user.brief_info}\n" +
                                                   gender_info +
                                                   f"Направление: {user.faculty}\n"
                                                   + f"Курс: {user.course}\n"
                                                   + f"Адрес для писем: {user}", reply_markup=markup))


async def send_input_brief_info(chat_id, nickname):
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_INFO, chat_id)
    markup = types.ReplyKeyboardRemove()
    task = bot(
        methods.send_message.SendMessage(chat_id=chat_id, text="Извольте-с рассказать немного о себе: ",
                                         reply_markup=markup))
    await task1
    await task


async def main() -> None:
    await dp.start_polling(bot, handle_signals=True, polling_timeout=10, handle_as_tasks=True,
                           close_bot_session=True,
                           backoff_config=BackoffConfig(min_delay=1, max_delay=10, jitter=0.1, factor=1.3))


async def start_reg(chat_id, nickname) -> None:
    task1 = storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING, chat_id)
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Давай!", callback_data="add_fio")]])
    task = bot(methods.send_message.SendMessage(chat_id=chat_id,
                                                text="Здравствуй, дорогой друг! Добро пожаловать в наш вестник, где собраны объявления всех людей, которые пока что не нашли себе пару. Мы уверены, что у Вас получится найти спутника на бал ФКН, скорее переходите к поиску!",
                                                reply_markup=markup))
    await task1
    await task


logging.basicConfig(level=logging.INFO, stream=sys.stdout)
asyncio.run(backend.database.init_db())
asyncio.run(main())
