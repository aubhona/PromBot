import asyncio
import telebot
import backend.storage_manager as storage_manager
import backend.database
import os

from config import *
from telebot.async_telebot import AsyncTeleBot
from backend import parser
from backend.models.user import User
from backend.models.respond_state import RespondState
from backend.storage_manager import set_user_name, set_user_gender, set_user_height

bot = AsyncTeleBot(API_KEY)


@bot.message_handler(commands=["start", "restart"])
async def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Давай!", callback_data="add_fio"))
    task = bot.send_message(message.chat.id, "Привет! Я бот для поиска пары для балла ФКН 😎. Давай создадим анкету.",
                            reply_markup=markup)
    storage_manager.set_user_state(message.from_user.username, RespondState.WAIT_FOR_CREATING, message.chat.id)
    await task


@bot.message_handler(commands=["admin"])
async def admin_log(message):
    message.text = message.text[7:]
    if message.text == PASSWORD:
        task = bot.send_message(message.chat.id, "Админка выдана.")
        storage_manager.set_user_state(message.from_user.username, RespondState.ADMIN, message.chat.id)
        await task
        return
    task = bot.send_message(message.chat.id, "Неправильный пароль от админки!")
    user = storage_manager.get_user_by_nick(message.from_user.username)
    if user is not None and user.is_active:
        await show_menu(message.chat.id, message.from_user.username)
    else:
        storage_manager.set_user_state(message.from_user.username, RespondState.WAIT_FOR_CREATING, message.chat.id)
    await task


@bot.message_handler(func=lambda message: storage_manager.get_user_state(message.from_user.username) is None)
async def greeting(message):
    await send_welcome(message)


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(call.from_user.username) is None)
async def greeting_c(call):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Давай!", callback_data="add_fio"))
    task = bot.send_message(call.message.chat.id,
                            "Привет! Я бот для поиска пары для балла ФКН 😎. Давайте создадим анкету",
                            reply_markup=markup)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CREATING, call.message.chat.id)
    await task


@bot.message_handler(commands=["show"], func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.ADMIN)
async def show_profiles(message):
    profiles = storage_manager.get_profiles()
    if profiles is None or len(profiles) == 0:
        await bot.send_message(message.chat.id, "Анкет на модерацию пока нет.")
        return
    for profile in profiles:
        await show_procfile(storage_manager.get_user_by_nick(profile.nickname), message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("allow") and storage_manager.get_user_state(
    call.from_user.username).state == RespondState.ADMIN)
async def allow(call):
    username = call.data[6:]
    task1 = bot.send_message(call.message.chat.id, f"Анкета @{username} успешно одобрена!")
    user_state = storage_manager.get_user_state(username)
    task2 = bot.send_message(user_state.chat_id, "Ваша анкета одобрена!")
    storage_manager.set_user_state(username, RespondState.WAIT_FOR_FIND, user_state.chat_id)
    task3 = show_form(storage_manager.get_user_by_nick(username), user_state.chat_id)
    storage_manager.add_user(User(nickname=username, is_active=True))
    await task1
    await task2
    await task3


@bot.callback_query_handler(func=lambda call: call.data.startswith("decline") and storage_manager.get_user_state(
    call.from_user.username).state == RespondState.ADMIN)
async def decline_mes(call):
    username = call.data[8:]
    task = bot.send_message(call.message.chat.id, f"Напишите причину отклонение анкеты пользователя @{username}.")
    storage_manager.set_user_state(call.from_user.username, RespondState.ADMIN, call.message.chat.id, username)
    await task


@bot.message_handler(commands=["decline"], func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.ADMIN)
async def decline(message):
    admin_user_state = storage_manager.get_user_state(message.from_user.username)
    username = admin_user_state.last_seen
    task1 = bot.send_message(message.chat.id, f"Анкета @{username} успешно отклонена!")
    user_state = storage_manager.get_user_state(username)
    task2 = bot.send_message(user_state.chat_id, f"Ваша анкета отклонена(\nПо причине:\n{message.text[9:]}\n"
                             + "Пересоздайте анкету.")
    storage_manager.set_user_state(username, RespondState.WAIT_FOR_CREATING, user_state.chat_id)
    task3 = show_only_form(storage_manager.get_user_by_nick(username), user_state.chat_id)
    await task1
    await task2
    await task3
    message.chat.id = user_state.chat_id
    message.from_user.username = user_state.nickname
    await send_welcome(message)


@bot.message_handler(commands=["menu"], func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state in {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND, RespondState.ADMIN})
async def menu_m(message):
    await show_menu(message.chat.id, message.from_user.username)


@bot.callback_query_handler(func=lambda call: call.data == "menu" and storage_manager.get_user_state(
    call.from_user.username).state in {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND, RespondState.WAIT_CHANGE})
async def menu_c(call):
    await show_menu(call.message.chat.id, call.from_user.username)


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_FOR_CREATING)
async def input_name_c(call):
    await send_input_name(call.message.chat.id, call.from_user.username)


@bot.message_handler(
    func=lambda message:
    storage_manager.get_user_state(message.from_user.username).state == RespondState.WAIT_FOR_CREATING)
async def input_name_m(message):
    await send_input_name(message.chat.id, message.from_user.username)


@bot.callback_query_handler(
    func=lambda call: call.data == "change_form" and storage_manager.get_user_state(call.from_user.username).state in
                      {RespondState.WAIT_MENU, RespondState.WAIT_CHANGE})
async def change_form_confirm(call):
    if storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_MENU:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Да", callback_data="change_form"),
                   telebot.types.InlineKeyboardButton("Нет", callback_data="menu"))
        task = bot.send_message(call.message.chat.id, "Вы точно хотите изменить анкету? (Она отправится на модерацию).",
                                reply_markup=markup)
        storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_CHANGE, call.message.chat.id)
        await task
        return
    storage_manager.add_user(User(nickname=call.from_user.username, is_active=False))
    await send_input_name(call.message.chat.id, call.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_FIO)
async def input_gender_set_name_m(message):
    fio = parser.parse_fio(message.text)
    if fio is None:
        await bot.reply_to(message, "Некорректно введены данные, попробуйте снова.")
        return
    task = send_choose_gender(message.chat.id, message.from_user.username)
    set_user_name(nickname=message.from_user.username, name=fio)
    await task


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_FIO)
async def input_gender_c(call):
    await send_input_name(call.message.chat.id, call.from_user.username)


@bot.callback_query_handler(
    func=lambda call:
    storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_FOR_CREATING_GENDER)
async def input_height_set_gender_c(call):
    task = send_input_height(call.message.chat.id, call.from_user.username)
    set_user_gender(nickname=call.from_user.username, gender=call.data == "True")
    await task


@bot.message_handler(
    func=lambda message:
    storage_manager.get_user_state(message.from_user.username).state == RespondState.WAIT_FOR_CREATING_GENDER)
async def input_height_m(message):
    await send_choose_gender(message.chat.id, message.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_HEIGHT)
async def input_brief_info_set_height_m(message):
    height = parser.parse_height(message.text)
    if height is None:
        await bot.reply_to(message, "Некорректно введены данные, попробуйте снова.")
        return
    task = send_input_brief_info(message.chat.id, message.from_user.username)
    set_user_height(message.from_user.username, height)
    await task


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_HEIGHT)
async def intput_height_c(call):
    await send_input_height(call.message.chat.id, call.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_INFO)
async def input_faculty_set_info_m(message):
    if message.text is None or len(message.text) == 0:
        await bot.reply_to(message, "Некорректно введены данные, попробуйте снова.")
        return
    task = send_input_faculty(message.chat.id, message.from_user.username)
    storage_manager.set_user_brief_info(message.from_user.username, message.text)
    await task


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_INFO)
async def input_faculty_c(call):
    await send_input_brief_info(call.message.chat.id, call.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_FACULTY)
async def input_course_set_faculty_m(message):
    if message.text is None or len(message.text) == 0:
        await bot.reply_to(message, "Некорректно введены данные, попробуйте снова.")
        return
    task = send_input_course(message.chat.id, message.from_user.username)
    storage_manager.set_user_faculty(message.from_user.username, message.text)
    await task


@bot.callback_query_handler(func=lambda call: call.data in {"1", "2", "3", "4", "5", "6"} and
                                              storage_manager.get_user_state(call.from_user.username).state
                                              == RespondState.WAIT_FOR_CREATING_COURSE)
async def input_image_set_course_m(call):
    storage_manager.set_user_course(call.from_user.username, int(call.data))
    task = send_input_image(call.message.chat.id, call.from_user.username)
    await task


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_COURSE)
async def input_course_c(call):
    await send_input_course(call.message.chat.id, call.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_COURSE)
async def input_course_m(message):
    await send_input_course(message.chat.id, message.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE, content_types=['photo'])
async def set_image(message):
    image_task = bot.get_file(message.photo[-1].file_id)
    downloaded_image_task = bot.download_file((await image_task).file_path)
    task = send_form_finish(message.chat.id, message.from_user.username)
    path = os.path.join('PromBot', 'static', 'user_images', f"{message.from_user.username}.jpg")
    user = storage_manager.get_user_by_nick(message.from_user.username)
    user.image_path = path
    storage_manager.set_user_image_path(message.from_user.username, path)
    with open(path, 'wb') as file:
        file.write((await downloaded_image_task))
        file.close()
    await task
    await show_only_form(user, message.chat.id)
    await show_procfile(user, ADMIN_CHAT_ID)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE)
async def set_image(message):
    await send_input_image(message.chat.id, message.from_user.username)


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE)
async def set_image_c(call):
    await send_input_image(call.message.chat.id, call.from_user.username)


@bot.callback_query_handler(
    func=lambda call: call.data == "find"
                      and storage_manager.get_user_state(call.from_user.username).state in {RespondState.WAIT_FOR_FIND,
                                                                                            RespondState.ADMIN})
async def find(call):
    user = storage_manager.get_user_by_nick(call.from_user.username)
    user_state = storage_manager.get_user_state(user.nickname)
    new_user = storage_manager.get_active_user(user.gender, user_state.last_seen, user_state.filter_value // 10,
                                               user_state.filter_value % 10)
    if new_user is None:
        task1 = bot.send_message(call.message.chat.id, "Показ анкет начинается сначала.")
        user_state.last_seen = None
        new_user = storage_manager.get_active_user(user.gender, user_state.last_seen, user_state.filter_value // 10,
                                                   user_state.filter_value % 10)
        await task1
    if new_user is None:
        await bot.send_message(chat_id=call.message.chat.id, text="Сейчас нет свободных анкет. Попробуйте позже")
        await show_menu(call.message.chat.id, user.nickname)
        return
    task = show_user(new_user, call.message.chat.id)
    storage_manager.set_user_state(user.nickname, user_state.state, call.message.chat.id, new_user.nickname)
    await task


@bot.callback_query_handler(
    func=lambda call: call.data == "find"
                      and storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_MENU)
async def find_menu(call):
    call_back = telebot.types.CallbackQuery(data="find", message=call.message, from_user=call.from_user, id=None,
                                            chat_instance=None, json_string=None)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND, call.message.chat.id)
    await find(call_back)


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state in
                      {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND} and call.data == "deactivate")
async def deactivate_user(call):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Включить анкету", callback_data="activate"))
    task = bot.send_message(chat_id=call.message.chat.id, text="Ваша анкета отключена.", reply_markup=markup)
    storage_manager.set_user_state(call.from_user.username, RespondState.DEACTIVATE, call.message.chat.id)
    storage_manager.add_user(User(nickname=call.from_user.username, is_active=False))
    await task


@bot.callback_query_handler(
    func=lambda call: call.data == "activate"
                      and storage_manager.get_user_state(call.from_user.username).state == RespondState.DEACTIVATE)
async def activate_user(call):
    task = bot.send_message(chat_id=call.message.chat.id, text="Ваша анкета включена.")
    task1 = show_form(storage_manager.get_user_by_nick(call.from_user.username), call.message.chat.id)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND, call.message.chat.id)
    storage_manager.add_user(User(nickname=call.from_user.username, is_active=True))
    await task
    await task1


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.DEACTIVATE)
async def deactivated_user_mes(call):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Включить анкету", callback_data="activate"))
    task = bot.send_message(chat_id=call.message.chat.id, text="Ваша анкета отключена.", reply_markup=markup)
    await task


@bot.message_handler(
    func=lambda message: storage_manager.get_user_state(message.from_user.username).state == RespondState.DEACTIVATE)
async def deactivated_user_mes(message):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Включить анкету", callback_data="activate"))
    task = bot.send_message(chat_id=message.chat.id, text="Ваша анкета отключена.", reply_markup=markup)
    await task


@bot.message_handler(
    func=lambda message: storage_manager.get_user_state(
        message.from_user.username).state == RespondState.WAIT_FOR_ALLOW)
async def wait_allow_action(message):
    await bot.send_message(message.chat.id, "Ваша анкета на модерации. Как только её одобрят вам придёт уведомление.")


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_FOR_ALLOW)
async def wait_allow_action_c(call):
    await bot.send_message(call.message.chat.id, "Ваша анкета на модерации. "
                           + "Как только её одобрят вам придёт уведомление.")


@bot.callback_query_handler(func=lambda call: call.data == "filter" and storage_manager
                            .get_user_state(call.from_user.username).state in {RespondState.WAIT_MENU,
                                                                               RespondState.ADMIN})
async def input_filter(call):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Назад", callback_data='find'),
               telebot.types.InlineKeyboardButton("Изменить фильтр", callback_data='change_filter'))
    user_state = storage_manager.get_user_state(call.from_user.username)
    await bot.send_message(call.message.chat.id, f"У вас установлен фильтр на курсы от {user_state.filter_value // 10} "
                           + f"до {user_state.filter_value % 10} курса.", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "change_filter" and storage_manager
                            .get_user_state(call.from_user.username).state in {RespondState.WAIT_MENU,
                                                                               RespondState.ADMIN})
async def change_filter(call):
    markup = telebot.types.InlineKeyboardMarkup()
    for i in range(1, 7):
        markup.add(telebot.types.InlineKeyboardButton(str(i), callback_data=str(i)))

    task = bot.send_message(call.message.chat.id, "Выберите минимальный курс для просмотра.", reply_markup=markup)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CHANGE_FILTER_1, call.message.chat.id)
    await task


@bot.callback_query_handler(func=lambda call: call.data in {"1", "2", "3", "4", "5", "6"} and storage_manager
                            .get_user_state(call.from_user.username).state in {RespondState.WAIT_FOR_CHANGE_FILTER_1,
                                                                               RespondState.ADMIN})
async def process_select_min(call):
    min_course = int(call.data)
    markup = telebot.types.InlineKeyboardMarkup()
    for i in range(min_course, 7):
        markup.add(telebot.types.InlineKeyboardButton(str(i), callback_data=str(i)))

    task = bot.send_message(call.message.chat.id, f"Теперь выберите максимальный курс для просмотра.",
                            reply_markup=markup)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_CHANGE_FILTER_2, call.message.chat.id,
                                   filter_value=f"{min_course}6")
    await task


@bot.callback_query_handler(func=lambda call: call.data in {"1", "2", "3", "4", "5", "6"} and storage_manager
                            .get_user_state(call.from_user.username).state in {RespondState.WAIT_FOR_CHANGE_FILTER_2,
                                                                               RespondState.ADMIN})
async def process_select_max(call):
    max_course = int(call.data)
    user_state = storage_manager.get_user_state(call.from_user.username)
    max_course = max(max_course, user_state.filter_value // 10)
    task = bot.send_message(call.message.chat.id, f"Выбран фильтр по курсу: {user_state.filter_value // 10} "
                            + f"- {max_course}.")
    if user_state.state == RespondState.WAIT_FOR_CHANGE_FILTER_2:
        storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND,
                                       call.message.chat.id,
                                       filter_value=f"{user_state.filter_value // 10}{max_course}")
    task1 = find(call)
    await task
    await task1


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(call.from_user.username)
                            .state in {RespondState.WAIT_FOR_CHANGE_FILTER_1, RespondState.WAIT_FOR_CHANGE_FILTER_2})
async def unknown_filter_call(call):
    user_state = storage_manager.get_user_state(call.from_user.username)
    if user_state.state == RespondState.WAIT_FOR_CHANGE_FILTER_1:
        await change_filter(call)
        return
    call.data = str(user_state.filter_value // 10)
    await process_select_min(call)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(message.from_user.username)
                     .state in {RespondState.WAIT_FOR_CHANGE_FILTER_1, RespondState.WAIT_FOR_CHANGE_FILTER_2})
async def unknown_filter_message(message):
    await bot.send_message(message.chat.id, "Выберите корректную команду.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("like")
                                              and storage_manager.get_user_state(call.from_user.username).state
                                              in {RespondState.WAIT_FOR_FIND,
                                                  RespondState.ADMIN})
async def like_user(call):
    user_state = storage_manager.get_user_state(call.data[6:])
    task1 = bot.send_message(user_state.chat_id, "Вас лайкнул пользователь. Вот его анкета.")
    task2 = show_only_form(storage_manager.get_user_by_nick(call.from_user.username), user_state.chat_id)
    task3 = bot.send_message(call.message.chat.id, f"Вы успешно лайкнули @{user_state.nickname}.")
    task4 = find(call)
    await task1
    await task2
    await task3
    await task4


@bot.callback_query_handler(func=lambda call: True)
async def anything(call):
    task = bot.send_message(call.message.chat.id, "Некорректное действие. Следуйте строго моим инструкциям.")
    user_state = storage_manager.get_user_state(call.from_user.username)
    await bot.send_message(HELP_CHAT_ID, call.data)
    await bot.send_message(HELP_CHAT_ID, str(user_state.state))
    await bot.send_message(HELP_CHAT_ID, f"@{str(user_state.nickname)}")
    await task


@bot.message_handler()
async def anything(message):
    task = bot.send_message(message.chat.id, "Некорректное действие. Следуйте строго моим инструкциям.")
    user_state = storage_manager.get_user_state(message.from_user.username)
    await bot.send_message(HELP_CHAT_ID, message.text)
    await bot.send_message(HELP_CHAT_ID, str(user_state.state))
    await bot.send_message(HELP_CHAT_ID, f"@{str(user_state.nickname)}")
    await task


async def show_user(user, chat_id):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(telebot.types.InlineKeyboardButton("Следующая анкета", callback_data="find"),
               telebot.types.InlineKeyboardButton("Меню", callback_data="menu"),
               telebot.types.InlineKeyboardButton("❤️", callback_data=f"like_{user}"))
    await send_form(user, markup, chat_id)


async def show_only_form(user, chat_id):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    await send_form(user, remove_markup, chat_id)


async def show_form(user, chat_id):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Меню", callback_data="menu"))
    await send_form(user, markup, chat_id)


async def show_procfile(user, chat_id):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Одоборить", callback_data=f"allow_{user.nickname}"),
               telebot.types.InlineKeyboardButton("Отклонить", callback_data=f"decline_{user.nickname}"))
    await send_form(user, markup, chat_id, True)


async def show_menu(chat_id, nickname):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(telebot.types.InlineKeyboardButton("Найти пару", callback_data="find"),
               telebot.types.InlineKeyboardButton("Изменить анкету", callback_data="change_form"),
               telebot.types.InlineKeyboardButton("Отключить анкету", callback_data="deactivate"),
               telebot.types.InlineKeyboardButton("Поставить фильтр по курсу", callback_data="filter"))
    task = bot.send_message(chat_id=chat_id, text="Меню", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_MENU, chat_id)
    await task


async def send_choose_gender(chat_id, nickname):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Я парень", callback_data='True'),
               telebot.types.InlineKeyboardButton("Я девушка", callback_data='False'))
    task = bot.send_message(chat_id, "Выберите пол.", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_GENDER, chat_id)
    await task


async def send_input_name(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Введите фамилию и имя (через пробел, в этом порядке):",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FIO, chat_id)
    await task


async def send_input_height(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Введите свой рост в см (например 176.1 или 120):",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_HEIGHT, chat_id)
    await task


async def send_input_faculty(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Введите свой факультет и направление (например ФКН ПИ):",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FACULTY, chat_id)
    await task


async def send_input_image(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Отправьте фото для анкеты (именно как фото).",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_IMAGE, chat_id)
    await task


async def send_input_course(chat_id, nickname):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("1", callback_data="1"),
               telebot.types.InlineKeyboardButton("2", callback_data="2"),
               telebot.types.InlineKeyboardButton("3", callback_data="3"),
               telebot.types.InlineKeyboardButton("4", callback_data="4"),
               telebot.types.InlineKeyboardButton("5", callback_data="5"),
               telebot.types.InlineKeyboardButton("6", callback_data="6"))
    task = bot.send_message(chat_id, "Выберите номер вашего курса (если вы учтитесь на магистратуре 1 курса, "
                            + "то выбирайте 5 курс и т.д.).", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_COURSE, chat_id)
    await task


async def send_form_finish(chat_id, nickname):
    markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Ваша анкета отправлена на одобрение.", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_ALLOW, chat_id)
    await task


async def send_form(user, markup, chat_id, gender=False):
    with open(user.image_path, "rb") as photo:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=f"{user.name.capitalize()} " +
                                                                   f"{user.surname.capitalize()}\nРост: {user.height}" +
                                                                   f" см.\nО себе:\n{user.brief_info}\n" +
                                                                   f"{('Пол: М' if user.gender else 'Пол: Ж') if gender else ''}\n" +
                                                                   f"Направление: {user.faculty}\n"
                                                                   + f"Курс: {user.course}\n"
                                                                   + f"Тг: {user}", reply_markup=markup)
        photo.close()


async def send_input_brief_info(chat_id, nickname):
    markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Расскажите немного о себе: ", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_INFO, chat_id)
    await task


backend.database.init_db()
asyncio.run(bot.polling())
