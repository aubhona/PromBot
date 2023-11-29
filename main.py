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
    task = bot.send_message(message.chat.id, "Привет! Я бот для поиска пары для балла ФКН 😎. Давай создадим анкету",
                            reply_markup=markup)
    storage_manager.set_user_state(message.from_user.username, RespondState.WAIT_FOR_CREATING)
    await task


@bot.message_handler(commands=["menu"], func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state in {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND})
async def menu_m(message):
    await show_menu(message.chat.id, message.from_user.username)


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state in {RespondState.WAIT_MENU, RespondState.WAIT_FOR_FIND} and call.data == "menu")
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
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_MENU
    and call.data == "change_form")
async def change_form(call):
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
async def input_faculty_set_height_m(message):
    height = parser.parse_height(message.text)
    if height is None:
        await bot.reply_to(message, "Некорректно введены данные, попробуйте снова.")
        return
    task = send_input_faculty(message.chat.id, message.from_user.username)
    set_user_height(message.chat.id, height)
    await task


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_HEIGHT)
async def input_faculty_c(call):
    await send_input_height(call.message.chat.id, call.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_FACULTY)
async def input_image_set_faculty_m(message):
    if message.text is None or len(message.text) == 0:
        await bot.reply_to(message, "Некорректно введены данные, попробуйте снова.")
        return
    task = send_input_image(message.chat.id, message.from_user.username)
    storage_manager.set_user_faculty(message.from_user.username, message.text)
    await task


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_FACULTY)
async def input_image_c(call):
    await send_input_faculty(call.message.chat.id, call.from_user.username)


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE, content_types=['photo'])
async def set_image(message):
    image_task = bot.get_file(message.photo[-1].file_id)
    downloaded_image_task = bot.download_file((await image_task).file_path)
    task = send_form_finish(message.chat.id, message.from_user.username)
    task1 = show_form(storage_manager.get_user_by_nick(message.from_user.username), message.chat.id)
    path = os.path.join('static', 'user_images', f"{message.from_user.username}.jpg")
    storage_manager.set_user_name(message.from_user.username, path)
    with open(path, 'wb') as file:
        file.write((await downloaded_image_task))
    await task
    await task1


@bot.message_handler(func=lambda message: storage_manager.get_user_state(
    message.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE)
async def set_image(message):
    await send_input_image(message.chat.id, message.from_user.username)


@bot.callback_query_handler(func=lambda call: storage_manager.get_user_state(
    call.from_user.username).state == RespondState.WAIT_FOR_CREATING_IMAGE)
async def set_image_c(call):
    await send_input_image(call.message.chat.id, call.from_user.username)


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_FOR_FIND
    and call.data == "find")
async def find(call):
    user = storage_manager.get_user_by_nick(call.from_user.username)
    user_state = storage_manager.get_user_state(user.nickname)
    new_user = storage_manager.get_active_user(user.gender, user_state.last_seen)
    if new_user is None:
        user_state.last_seen = None
        new_user = storage_manager.get_active_user(user.gender, user_state.last_seen)
    if new_user is None:
        await bot.send_message(chat_id=call.message.chat.id, text="Сейчас нет свободных анкет. Попробуйте позже")
        await show_menu(call.message.chat.id, user.nickname)
        return
    task = show_user(new_user, call.message.chat.id)
    storage_manager.set_user_state(user.nickname, user_state.state, new_user.nickname)
    await task


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_MENU
    and call.data == "find")
async def find_menu(call):
    call_back = telebot.types.CallbackQuery(data="find", message=call.message, from_user=call.from_user, id=None,
                                            chat_instance=None, json_string=None)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND)
    await find(call_back)


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.WAIT_MENU
    and call.data == "deactivate")
async def deactivate_user(call):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Включить анкету", callback_data="activate"))
    task = bot.send_message(chat_id=call.message.chat.id, text="Ваша анкета отключена.", reply_markup=markup)
    storage_manager.set_user_state(call.from_user.username, RespondState.DEACTIVATE)
    storage_manager.add_user(User(nickname=call.from_user.username, is_active=False))
    await task


@bot.callback_query_handler(
    func=lambda call: storage_manager.get_user_state(call.from_user.username).state == RespondState.DEACTIVATE
    and call.data == "activate")
async def activate_user(call):
    task = bot.send_message(chat_id=call.message.chat.id, text="Ваша анкета включена.")
    task1 = show_form(storage_manager.get_user_by_nick(call.from_user.username), call.message.chat.id)
    storage_manager.set_user_state(call.from_user.username, RespondState.WAIT_FOR_FIND)
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


async def show_user(user, chat_id):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Следующая анкета", callback_data="find"),
               telebot.types.InlineKeyboardButton("Меню", callback_data="menu"))
    with open(user.image_path, "rb") as photo:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=f"{user.name.capitalize()} " +
                                                                   f"{user.surname.capitalize()}\nРост: {user.height}" +
                                                                   f" см.\nНаправление: {user.faculty.upper()}\n"
                                                                   + f"Тг: {user}", reply_markup=markup)


async def show_form(user, chat_id):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Меню", callback_data="menu"))
    with open(user.image_path, "rb") as photo:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=f"{user.name.capitalize()} " +
                                                                   f"{user.surname.capitalize()}\nРост: {user.height}" +
                                                                   f" см.\nНаправление: {user.faculty.upper()}\n"
                                                                   + f"Тг: {user}", reply_markup=markup)


async def show_menu(chat_id, nickname):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Найти пару", callback_data="find"),
               telebot.types.InlineKeyboardButton("Изменить анкету", callback_data="change_form"),
               telebot.types.InlineKeyboardButton("Отключить анкету", callback_data="deactivate"))
    task = bot.send_message(chat_id=chat_id, text="Меню", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_MENU)
    await task


async def send_choose_gender(chat_id, nickname):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Я парень", callback_data='True'),
               telebot.types.InlineKeyboardButton("Я девушка", callback_data='False'))
    task = bot.send_message(chat_id, "Выберите пол", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_GENDER)
    await task


async def send_input_name(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Введи фамилию и имя (через пробел, в этом порядке):",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FIO)
    await task


async def send_input_height(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Введите свой рост в см (например 176.1 или 120):",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_HEIGHT)
    await task


async def send_input_faculty(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Введите свой факультет и направление (например ФКН ПИ):",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_FACULTY)
    await task


async def send_input_image(chat_id, nickname):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Отправьте фото для анкеты (именно как фото):",
                            reply_markup=remove_markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_CREATING_IMAGE)
    await task


async def send_form_finish(chat_id, nickname):
    markup = telebot.types.ReplyKeyboardRemove()
    task = bot.send_message(chat_id, "Ваша анкета готова.", reply_markup=markup)
    storage_manager.set_user_state(nickname, RespondState.WAIT_FOR_FIND)
    await task


@bot.callback_query_handler(func=lambda call: True)
async def anyone(call):
    await bot.send_message(call.message.chat.id, call.data)
    await bot.send_message(call.message.chat.id, str(storage_manager.get_user_state(call.from_user.username).state))


@bot.message_handler()
async def anyone(message):
    await bot.send_message(message.chat.id, message.text)
    await bot.send_message(message.chat.id, str(storage_manager.get_user_state(message.from_user.username).state))


backend.database.init_db()
asyncio.run(bot.polling())
