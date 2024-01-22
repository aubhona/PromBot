from aiogram.utils.backoff import BackoffConfig

import backend.storage_manager as storage_manager
import backend.database
import os
import logging
import sys
import asyncio

from config import *
from aiogram import Bot, Dispatcher, types, methods, filters
from backend import parser
from backend.models.user import User
from backend.models.respond_state import RespondState
from backend.storage_manager import set_user_name, set_user_gender, set_user_height

dp = Dispatcher()
bot = Bot(token=API_KEY)


@dp.message(filters.command.Command("start", "restart"))
async def send_welcome(message: types.Message):
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Давай!", callback_data="add_fio")]])
    task = bot(methods.send_message.SendMessage(chat_id=message.chat.id,
                                                text="Здравствуй, дорогой друг! Добро пожаловать в наш вестник, где собраны объявления всех людей, которые пока что не нашли себе пару. Мы уверены, что у Вас получится найти спутника на бал ФКН, скорее переходите к поиску!",
                                                reply_markup=markup))
    storage_manager.set_user_state(message.from_user.username, RespondState.WAIT_FOR_CREATING, message.chat.id)
    await task


@dp.message(filters.command.Command("admin"))
async def admin_log(message: types.Message):
    if message.text[7:] == PASSWORD:
        task = bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Админка выдана."))
        storage_manager.set_user_state(message.from_user.username, RespondState.ADMIN, message.chat.id)
        await task
        return
    task = bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Неправильный пароль от админки!"))
    user = storage_manager.get_user_by_nick(message.from_user.username)
    if user is not None and user.is_active:
        await show_menu(message.chat.id, message.from_user.username)
    else:
        storage_manager.set_user_state(message.from_user.username, RespondState.WAIT_FOR_CREATING, message.chat.id)
    await task


@dp.message(lambda message: storage_manager.get_user_state(message.from_user.username) is None)
async def greeting(message: types.Message):
    await send_welcome(message)


@dp.callback_query(lambda call: storage_manager.get_user_state(call.from_user.username) is None)
async def greeting_c(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Давай!", callback_data="add_fio")])
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                text="Здравствуй, дорогой друг! Добро пожаловать в наш вестник, где собраны объявления всех людей, которые пока что не нашли себе пару. Мы уверены, что у Вас получится найти спутника на бал ФКН, скорее переходите к поиску!",
                                                reply_markup=markup))
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CREATING, call.message.chat.id)
    await task


@dp.message(filters.and_f(filters.command.Command("show"), lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.ADMIN))
async def show_profiles(message: types.Message):
    profiles = storage_manager.get_profiles()
    if profiles is None or len(profiles) == 0:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Анкет на модерацию пока нет."))
        return
    for profile in profiles:
        await show_procfile(storage_manager.get_user_by_nick(profile.nickname), message.chat.id)


@dp.callback_query(lambda call: call.data.startswith("allow") and storage_manager.get_user_state(
    call.from_user.username).state == RespondState.ADMIN)
async def allow(call: types.CallbackQuery):
    username = call.data[6:]
    task1 = bot(
        methods.send_message.SendMessage(chat_id=call.message.chat.id, text=f"Анкета @{username} успешно одобрена!"))
    user_state = storage_manager.get_user_state(username)
    task2 = bot(
        methods.send_message.SendMessage(chat_id=user_state.chat_id, text="Ваше объявление было успешно напечатано!"))
    storage_manager.set_user_state(username, RespondState.WAIT_FOR_FIND, user_state.chat_id)
    task3 = show_form(storage_manager.get_user_by_nick(username), user_state.chat_id)
    storage_manager.add_user(User(nickname=username, is_active=True))
    await task1
    await task2
    await task3


@dp.callback_query(lambda call: call.data.startswith("decline") and storage_manager.get_user_state(
    call.from_user.username).state == RespondState.ADMIN)
async def decline_mes(call: types.CallbackQuery):
    username = call.data[8:]
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                text=f"Напишите причину отклонение анкеты пользователя @{username}."))
    storage_manager.set_user_state(call.from_user.username, RespondState.ADMIN, call.message.chat.id, username)
    await task


@dp.message(filters.and_f(filters.command.Command("decline"), lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.ADMIN))
async def decline(message: types.Message):
    admin_user_state = storage_manager.get_user_state(message.from_user.username)
    username = admin_user_state.last_seen
    task1 = bot(
        methods.send_message.SendMessage(chat_id=message.chat.id, text=f"Анкета @{username} успешно отклонена!"))
    user_state = storage_manager.get_user_state(username)
    task2 = bot(methods.send_message.SendMessage(chat_id=user_state.chat_id,
                                                 text=f"Ваша объявление, к сожалению, не напечатали.\nПо причине:\n{message.text[9:].capitalize()}\n"
                                                      + "Перепишите своё объявление!"))
    storage_manager.set_user_state(username, RespondState.WAIT_FOR_CREATING, user_state.chat_id)
    task3 = show_only_form(storage_manager.get_user_by_nick(username), user_state.chat_id)
    await task1
    await task2
    await task3
    message.chat.id = user_state.chat_id
    message.from_user.username = user_state.nickname
    await send_welcome(message)


@dp.message(filters.and_f(filters.command.Command("menu"), lambda message: storage_manager.get_user_state(
    message.from_user.username).state in {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND, RespondState.ADMIN}))
async def menu_m(message: types.Message):
    await show_menu(message.chat.id, message.from_user.username)


@dp.callback_query(lambda call: call.data == "menu" and storage_manager.get_user_state(
    call.from_user.username).state in {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND, RespondState.WAIT_CHANGE})
async def menu_c(call: types.CallbackQuery):
    await show_menu(call.message.chat.id, call.from_user.username)


@dp.callback_query(lambda call:
                   storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_FOR_CREATING)
async def input_name_c(call: types.CallbackQuery):
    await send_input_name(call.message.chat.id, call.from_user.username)


@dp.message(lambda message:
            storage_manager.get_user_state(message.from_user.username).state == RespondState.WAIT_FOR_CREATING)
async def input_name_m(message: types.Message):
    await send_input_name(message.chat.id, message.from_user.username)


@dp.callback_query(lambda call:
                   call.data == "change_form" and storage_manager.get_user_state(call.from_user.username).state in
                   {RespondState.WAIT_MENU, RespondState.WAIT_CHANGE})
async def change_form_confirm(call: types.CallbackQuery):
    if storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_MENU:
        markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
        markup.inline_keyboard.append([types.InlineKeyboardButton(text="Да", callback_data="change_form"),
                                       types.InlineKeyboardButton(text="Нет", callback_data="menu")])
        task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                    text="Вы уверены, что хотите внести изменения в объявление? (Оно отправится на перепечать, что займёт время).",
                                                    reply_markup=markup))
        storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_CHANGE, call.message.chat.id)
        await task
        return
    storage_manager.add_user(User(nickname=call.from_user.username, is_active=False))
    await send_input_name(call.message.chat.id, call.from_user.username)


@dp.message(lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_FIO)
async def input_gender_set_name_m(message: types.Message):
    fio = parser.parse_fio(message.text)
    if fio is None:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, reply_to_message_id=message.message_id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_choose_gender(message.chat.id, message.from_user.username)
    set_user_name(nickname=message.from_user.username, name=fio)
    await task


@dp.callback_query(lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_FIO)
async def input_gender_c(call: types.CallbackQuery):
    await send_input_name(call.message.chat.id, call.from_user.username)


@dp.callback_query(lambda call:
                   storage_manager.get_user_state(
                       call.from_user.username).state == RespondState.WAIT_FOR_CREATING_GENDER)
async def input_height_set_gender_c(call: types.CallbackQuery):
    task = send_input_height(call.message.chat.id, call.from_user.username)
    set_user_gender(nickname=call.from_user.username, gender=call.data == "True")
    await task


@dp.message(lambda message:
            storage_manager.get_user_state(message.from_user.username).state == RespondState.WAIT_FOR_CREATING_GENDER)
async def input_height_m(message: types.Message):
    await send_choose_gender(message.chat.id, message.from_user.username)


@dp.message(lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_HEIGHT)
async def input_brief_info_set_height_m(message: types.Message):
    height = parser.parse_height(message.text)
    if height is None:
        await bot(methods.send_message.SendMessage(reply_to_message_id=message.message_id, chat_id=message.chat.id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_input_brief_info(message.chat.id, message.from_user.username)
    set_user_height(message.from_user.username, height)
    await task


@dp.callback_query(lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_HEIGHT)
async def intput_height_c(call: types.CallbackQuery):
    await send_input_height(call.message.chat.id, call.from_user.username)


@dp.message(lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_INFO)
async def input_faculty_set_info_m(message: types.Message):
    if message.text is None or len(message.text) == 0:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, reply_to_message_id=message.message_id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_input_faculty(message.chat.id, message.from_user.username)
    storage_manager.set_user_brief_info(message.from_user.username, message.text)
    await task


@dp.callback_query(lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_INFO)
async def input_faculty_c(call: types.CallbackQuery):
    await send_input_brief_info(call.message.chat.id, call.from_user.username)


@dp.message(lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_FACULTY)
async def input_course_set_faculty_m(message: types.Message):
    if message.text is None or len(message.text) == 0:
        await bot(methods.send_message.SendMessage(chat_id=message.chat.id, reply_to_message_id=message.message_id,
                                                   text="Отправьте правильное сообщение точно по инструкциям."))
        return
    task = send_input_course(message.chat.id, message.from_user.username)
    storage_manager.set_user_faculty(message.from_user.username, message.text)
    await task


@dp.callback_query(lambda call: call.data in {"1", "2", "3", "4", "5", "6"} and
                                storage_manager.get_user_state(
                                    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_COURSE)
async def input_image_set_course_m(call: types.CallbackQuery):
    storage_manager.set_user_course(call.from_user.username, int(call.data))
    task = send_input_image(call.message.chat.id, call.from_user.username)
    await task


@dp.callback_query(lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_COURSE)
async def input_course_c(call: types.CallbackQuery):
    await send_input_course(call.message.chat.id, call.from_user.username)


@dp.message(lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_COURSE)
async def input_course_m(message: types.Message):
    await send_input_course(message.chat.id, message.from_user.username)


@dp.message(lambda message: message.content_type == types.ContentType.PHOTO and storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE)
async def set_image(message: types.Message):
    image_task = bot(methods.get_file.GetFile(file_id=message.photo[-1].file_id))
    path = os.path.join('PromBot', 'static', 'user_images', f"{message.from_user.username}.jpg")
    downloaded_image_task = bot.download((await image_task), destination=path)
    task = send_form_finish(message.chat.id, message.from_user.username)
    user = storage_manager.get_user_by_nick(message.from_user.username)
    user.image_path = path
    storage_manager.set_user_image_path(message.from_user.username, path)
    await downloaded_image_task
    await task
    await show_only_form(user, message.chat.id)
    await show_procfile(user, ADMIN_CHAT_ID)


@dp.message(lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE)
async def set_image(message: types.Message):
    await send_input_image(message.chat.id, message.from_user.username)


@dp.callback_query(lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE)
async def set_image_c(call: types.CallbackQuery):
    await send_input_image(call.message.chat.id, call.from_user.username)


@dp.callback_query(
    lambda call: call.data == "find"
                 and storage_manager.get_user_state(call.from_user.username).state in {RespondState.WAIT_FOR_FIND,
                                                                                       RespondState.ADMIN})
async def find(call: types.CallbackQuery):
    user = storage_manager.get_user_by_nick(call.from_user.username)
    user_state = storage_manager.get_user_state(user.nickname)
    new_user = storage_manager.get_active_user(user.gender, user_state.last_seen, user_state.filter_value // 10,
                                               user_state.filter_value % 10)
    if new_user is None:
        task1 = bot(
            methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Вы просмотрели все объявления, поэтому сводки будут показаны повторно."))
        user_state.last_seen = None
        new_user = storage_manager.get_active_user(user.gender, user_state.last_seen, user_state.filter_value // 10,
                                                   user_state.filter_value % 10)
        await task1
    if new_user is None:
        await bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                   text="Сейчас нет объявлений. Попробуйте позже."))
        await show_menu(call.message.chat.id, user.nickname)
        return
    task = show_user(new_user, call.message.chat.id)
    storage_manager.set_user_state(user.nickname, user_state.state, call.message.chat.id, new_user.nickname)
    await task


@dp.callback_query(
    lambda call: call.data == "find"
                 and storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_MENU)
async def find_menu(call: types.CallbackQuery):
    call_back = types.CallbackQuery(data="find", message=call.message, from_user=call.from_user, id="",
                                    chat_instance="", json_string=None)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND, call.message.chat.id)
    await find(call_back)


@dp.callback_query(
    lambda call: storage_manager.get_user_state(call.from_user.username).state in
                 {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND} and call.data == "deactivate")
async def deactivate_user(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Показывать моё объявление", callback_data="activate")])
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Ваше объявление изъято.",
                                                reply_markup=markup))
    storage_manager.set_user_state(call.from_user.username, RespondState.DEACTIVATE, call.message.chat.id)
    storage_manager.add_user(User(nickname=call.from_user.username, is_active=False))
    await task


@dp.callback_query(
    lambda call: call.data == "activate"
                 and storage_manager.get_user_state(call.from_user.username).state == RespondState.DEACTIVATE)
async def activate_user(call: types.CallbackQuery):
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Ваше объявление теперь показывается."))
    task1 = show_form(storage_manager.get_user_by_nick(call.from_user.username), call.message.chat.id)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND, call.message.chat.id)
    storage_manager.add_user(User(nickname=call.from_user.username, is_active=True))
    await task
    await task1


@dp.callback_query(
    lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.DEACTIVATE)
async def deactivated_user_mes(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Показывать моё объявление", callback_data="activate")])
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Ваше объявление изъято.",
                                                reply_markup=markup))
    await task


@dp.message(
    lambda message: storage_manager.get_user_state(message.from_user.username).state == RespondState.DEACTIVATE)
async def deactivated_user_mes(message: types.Message):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Показывать моё объявление", callback_data="activate")])
    task = bot(
        methods.send_message.SendMessage(chat_id=message.chat.id, text="Ваше объявление изъято.", reply_markup=markup))
    await task


@dp.message(
    lambda message: storage_manager.get_user_state(
        message.from_user.username).state == RespondState.WAIT_FOR_ALLOW)
async def wait_allow_action(message: types.Message):
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id,
                                               text="Ваша объявление на печати. Как только её одобрят, я Вас уведомлю."))


@dp.callback_query(
    lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_FOR_ALLOW)
async def wait_allow_action_c(call: types.CallbackQuery):
    await bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                               text="Ваша объявление на печати. Как только её одобрят, я Вас уведомлю."))


@dp.callback_query(lambda call: call.data == "filter" and storage_manager
                   .get_user_state(call.from_user.username).state in {RespondState.WAIT_MENU,
                                                                      RespondState.ADMIN})
async def input_filter(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Нет", callback_data='find'),
                                   types.InlineKeyboardButton(text="Да", callback_data='change_filter')])
    user_state = storage_manager.get_user_state(call.from_user.username)
    await bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                               text=f"Вам показаны объявления от {user_state.filter_value // 10} "
                                                    + f"до {user_state.filter_value % 10} курса. Хотите изменить выборку?", reply_markup=markup))


@dp.callback_query(lambda call: call.data == "change_filter" and storage_manager
                   .get_user_state(call.from_user.username).state in {RespondState.WAIT_MENU,
                                                                      RespondState.ADMIN})
async def change_filter(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    for i in range(1, 7):
        markup.inline_keyboard.append([types.InlineKeyboardButton(text=str(i), callback_data=str(i))])

    task = bot(
        methods.send_message.SendMessage(chat_id=call.message.chat.id, text="Выберите минимальный курс для просмотра.",
                                         reply_markup=markup))
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CHANGE_FILTER_1, call.message.chat.id)
    await task


@dp.callback_query(lambda call: call.data in {"1", "2", "3", "4", "5", "6"} and storage_manager
                   .get_user_state(call.from_user.username).state in {RespondState.WAIT_FOR_CHANGE_FILTER_1,
                                                                      RespondState.ADMIN})
async def process_select_min(call: types.CallbackQuery):
    min_course = int(call.data)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    for i in range(min_course, 7):
        markup.inline_keyboard.append([types.InlineKeyboardButton(text=str(i), callback_data=str(i))])

    task = bot(
        methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                         text=f"Теперь выберите максимальный курс для просмотра.",
                                         reply_markup=markup))
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CHANGE_FILTER_2, call.message.chat.id,
                                   filter_value=f"{min_course}6")
    await task


@dp.callback_query(lambda call: call.data in {"1", "2", "3", "4", "5", "6"} and storage_manager
                   .get_user_state(call.from_user.username).state in {RespondState.WAIT_FOR_CHANGE_FILTER_2,
                                                                      RespondState.ADMIN})
async def process_select_max(call: types.CallbackQuery):
    max_course = int(call.data)
    user_state = storage_manager.get_user_state(call.from_user.username)
    max_course = max(max_course, user_state.filter_value // 10)
    task = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                text=f"Вам показаны объявления {user_state.filter_value // 10} "
                                                     + f"- {max_course} курса."))
    if user_state.state == RespondState.WAIT_FOR_CHANGE_FILTER_2:
        storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND,
                                       call.message.chat.id,
                                       filter_value=f"{user_state.filter_value // 10}{max_course}")
    task1 = find(call)
    await task
    await task1


@dp.callback_query(lambda call: storage_manager.get_user_state(call.from_user.username)
                   .state in {RespondState.WAIT_FOR_CHANGE_FILTER_1, RespondState.WAIT_FOR_CHANGE_FILTER_2})
async def unknown_filter_call(call: types.CallbackQuery):
    user_state = storage_manager.get_user_state(call.from_user.username)
    if user_state.state == RespondState.WAIT_FOR_CHANGE_FILTER_1:
        await change_filter(call)
        return
    call.data = str(user_state.filter_value // 10)
    await process_select_min(call)


@dp.message(lambda message: storage_manager.get_user_state(message.from_user.username)
            .state in {RespondState.WAIT_FOR_CHANGE_FILTER_1, RespondState.WAIT_FOR_CHANGE_FILTER_2})
async def unknown_filter_message(message: types.Message):
    await bot(methods.send_message.SendMessage(chat_id=message.chat.id, text="Отправьте правильное сообщение точно по инструкциям."))


@dp.callback_query(lambda call: call.data.startswith("like")
                                and storage_manager.get_user_state(call.from_user.username).state
                                in {RespondState.WAIT_FOR_FIND,
                                    RespondState.ADMIN})
async def like_user(call: types.CallbackQuery):
    user_state = storage_manager.get_user_state(call.data[6:])
    task1 = bot(
        methods.send_message.SendMessage(chat_id=user_state.chat_id, text="Вы приглянулись кое-кому, скорее напишите ему весточку:"))
    task2 = show_user(storage_manager.get_user_by_nick(call.from_user.username), user_state.chat_id)
    task3 = bot(methods.send_message.SendMessage(chat_id=call.message.chat.id,
                                                 text=f"Вы отдали свое сердце @{user_state.nickname}."))
    task4 = find(call)
    await task1
    await task2
    await task3
    await task4


# @dp.callback_query(lambda call: True)
# async def anything(call: types.CallbackQuery):
#     task = methods.send_message.SendMessage(call.message.chat.id, "Некорректное действие. Следуйте строго моим инструкциям.")
#     user_state = storage_manager.get_user_state(call.from_user.username)
#     await methods.send_message.SendMessage(HELP_CHAT_ID, call.data)
#     await methods.send_message.SendMessage(HELP_CHAT_ID, str(user_state.state))
#     await methods.send_message.SendMessage(HELP_CHAT_ID, f"@{str(user_state.nickname)}")
#     await task
#
#
# @dp.message()
# async def anything(message: types.Message):
#     task = methods.send_message.SendMessage(message.chat.id, "Некорректное действие. Следуйте строго моим инструкциям.")
#     user_state = storage_manager.get_user_state(message.from_user.username)
#     await methods.send_message.SendMessage(HELP_CHAT_ID, message.text)
#     await methods.send_message.SendMessage(HELP_CHAT_ID, str(user_state.state))
#     await methods.send_message.SendMessage(HELP_CHAT_ID, f"@{str(user_state.nickname)}")
#     await task


async def show_user(user, chat_id):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.row_width = 1
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Следующее объявление", callback_data="find")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Варианты действий", callback_data="menu")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text=f"{'Приглянулась глазу' if user.gender else 'Приглянулся глазу'}❤️", callback_data=f"like_{user}")])
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
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.row_width = 1
    markup.inline_keyboard.append([types.InlineKeyboardButton(text=f"{'Найти спутни(-ка/-цу)'}", callback_data="find")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Переписать свое объявление", callback_data="change_form")])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Изъять объявление", callback_data="deactivate")])
    markup.inline_keyboard.append(
        [types.InlineKeyboardButton(text="Установить выборку по году обучения", callback_data="filter")])
    task = bot(methods.send_message.SendMessage(chat_id=chat_id, text="Меню", reply_markup=markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_MENU, chat_id)
    await task


async def send_choose_gender(chat_id, nickname):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="Я сударь", callback_data='True'),
                                   types.InlineKeyboardButton(text="Я сударыня", callback_data='False')])
    task = bot(methods.send_message.SendMessage(chat_id=chat_id, text="Выберите Ваш пол:", reply_markup=markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_GENDER, chat_id)
    await task


async def send_input_name(chat_id, nickname):
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(
        methods.send_message.SendMessage(chat_id=chat_id, text="Впишите Ваши фамилию и имя (именно в этом порядке через пробел):",
                                         reply_markup=remove_markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FIO, chat_id)
    await task


async def send_input_height(chat_id, nickname):
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(
        methods.send_message.SendMessage(chat_id=chat_id, text="Введите Ваш рост (в сантиметрах):",
                                         reply_markup=remove_markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_HEIGHT, chat_id)
    await task


async def send_input_faculty(chat_id, nickname):
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(methods.send_message.SendMessage(chat_id=chat_id,
                                                text="Напишите Ваш факультет и направление (например, ФКН ПИ):",
                                                reply_markup=remove_markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FACULTY, chat_id)
    await task


async def send_input_image(chat_id, nickname):
    remove_markup = types.ReplyKeyboardRemove()
    task = bot(methods.send_message.SendMessage(chat_id=chat_id, text="Отправьте фотоснимок для вашего объявления (именно как фотоснимок (не документом) и ровно один):",
                                                reply_markup=remove_markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_IMAGE, chat_id)
    await task


async def send_input_course(chat_id, nickname):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[[]])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="1", callback_data="1"),
                                   types.InlineKeyboardButton(text="2", callback_data="2"),
                                   types.InlineKeyboardButton(text="3", callback_data="3"),
                                   types.InlineKeyboardButton(text="4", callback_data="4"),
                                   types.InlineKeyboardButton(text="5", callback_data="5"),
                                   types.InlineKeyboardButton(text="6", callback_data="6")])
    task = bot(methods.send_message.SendMessage(chat_id=chat_id,
                                                text="Выберите номер вашего курса (если вы учтитесь на магистратуре 1 курса, "
                                                     + "то выбирайте 5 курс и т.д.).", reply_markup=markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_COURSE, chat_id)
    await task


async def send_form_finish(chat_id, nickname):
    markup = types.ReplyKeyboardRemove()
    task = bot(methods.send_message.SendMessage(chat_id=chat_id, text="Ваше объявление отправлено на проверку перед печатью.",
                                                reply_markup=markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_ALLOW, chat_id)
    await task


async def send_form(user, markup, chat_id, gender=False):
    await bot(methods.send_photo.SendPhoto(chat_id=chat_id,
                                           photo=types.input_file.BufferedInputFile.from_file(user.image_path),
                                           caption=f"{user.name.capitalize()} " +
                                                   f"{user.surname.capitalize()}\nРост: {user.height}" +
                                                   f" см.\nО себе:\n{user.brief_info}\n" +
                                                   f"{('Пол: М' if user.gender else 'Пол: Ж') if gender else ''}\n" +
                                                   f"Направление: {user.faculty}\n"
                                                   + f"Курс: {user.course}\n"
                                                   + f"Адрес для писем: {user}", reply_markup=markup))


async def send_input_brief_info(chat_id, nickname):
    markup = types.ReplyKeyboardRemove()
    task = bot(
        methods.send_message.SendMessage(chat_id=chat_id, text="Извольте-с рассказать немного о себе: ", reply_markup=markup))
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_INFO, chat_id)
    await task


async def main() -> None:
    await dp.start_polling(bot, skip_updates=True, handle_signals=True, polling_timeout=10, handle_as_tasks=True,
                           close_bot_session=True,
                           backoff_config=BackoffConfig(min_delay=1, max_delay=10, jitter=0.1, factor=1.3))


logging.basicConfig(level=logging.INFO, stream=sys.stdout)
backend.database.init_db()
asyncio.run(main())
