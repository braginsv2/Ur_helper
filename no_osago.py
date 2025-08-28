from telebot import types
from datetime import datetime, timedelta
import re
import time
import json
import sqlite3
from word_utils import replace_words_in_word, create_fio_data_file
from database import DatabaseManager, save_client_to_db_with_id
from telebot.apihelper import ApiException

bot = None
callback_client_details2_handler = None
user_temp_data = {}


def init_bot(bot_instance, start_handler=None, callback_handler=None):
    """Инициализация бота в модуле"""
    global bot, callback_client_details2_handler
    bot = bot_instance
    callback_client_details2_handler = callback_handler

    @bot.callback_query_handler(func=lambda call: call.data == "btn_net_osago")
    def callback_net_osago(call):
        data = {'accident': 'net_osago'}
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Томск", callback_data="btn_city_Tomsk_NO")
        keyboard.add(btn1)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите город подачи заявления",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_city_Tomsk_NO"])
    def callback_NO_city(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        time.sleep(0.5)
        if call.data == "btn_city_Tomsk_NO":
            data.update({"city": "Томск"})
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Подготовьте документы:\n1. Паспорт\n2. Данные авто\n3. Страховой полис\n4. Сведения об участниках ДТП",
            reply_markup=None)
        user_message_id1 = message.message_id
        message = bot.send_message(call.message.chat.id, "Введите ФИО в формате Иванов Иван Иванович")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, FIO, data, user_message_id,user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data in ["STS_NO", "PTS_NO", "DKP_NO"])
    def callback_docs_pit(call):
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "STS_NO":
            data.update({"docs": "СТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_docs, data, user_message_id)

        elif call.data == "PTS_NO":
            data.update({"docs": "ПТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_docs, data, user_message_id)
        else: 
            data.update({"docs": "ДКП"})
            data.update({"seria_docs": "-"})
            data.update({"number_docs": "-"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДКП",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, data_docs, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["docs1Yes_NO", "docs1No_NO"])
    def callback_send_docs_NO(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        time.sleep(0.5)

        if call.data == "docs1Yes_NO":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_обложка.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_юр_договор.docx", "name": "Юридический договор"},
            {"path": data["fio"]+"\\"+data["fio"] + "_заявление_о_выдаче_копии_справкиГИБДД.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_заявление_о_выдаче_док_страх.docx", "name": "Юридический договор"}
            ]
            for doc in documents:
                try:
                    with open(doc["path"], 'rb') as document_file:
                        bot.send_document(
                            call.message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(call.message.chat.id, f"Файл не найден: {doc['path']}")
                    callback_client_details2_handler(call.message, data['client_id'])
                except Exception as e:
                    bot.send_message(call.message.chat.id, f"Ошибка отправки: {e}")
                    callback_client_details2_handler(call.message, data['client_id'])
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_NO_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data =="btn_NO_back")
    def callback_NO_back(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        clear_chat_history_optimized(call.message, 6)
        callback_client_details2_handler(call.message, data['client_id'])

    @bot.callback_query_handler(func=lambda call: call.data in ["Reco_NO", "Ugo_NO", "SOGAZ_NO", "Ingo_NO", "Ros_NO", "Maks_NO", "Energo_NO", "Sovko_NO", "other_NO"])
    def callback_insurance(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
          
        if call.data == "SOGAZ_NO":
            data.update({"insurance": 'АО "Согаз"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            )
            user_message_id = message.message_id
  
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        elif call.data == "Reco_NO":
            data.update({"insurance": 'САО "Ресо-Гарантия"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        elif call.data == "Ugo_NO":
            data.update({"insurance": 'АО "ГСК "Югория"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        elif call.data == "Ingo_NO":
            data.update({"insurance": 'СПАО "Ингосстрах"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        elif call.data == "Ros_NO":
            data.update({"insurance": 'ПАО СК "Росгосстрах"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        elif call.data == "Maks_NO":
            data.update({"insurance": 'АО "Макс"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        elif call.data == "Energo_NO":
            data.update({"insurance": 'ПАО «САК «Энергогарант»'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        elif call.data == "Sovko_NO":
            data.update({"insurance": 'АО «Совкомбанк страхование»'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название вашей страховой компании",
            reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, other_insurance, data, user_message_id) 
    @bot.callback_query_handler(func=lambda call: call.data == "NO_next")
    def callback_next_NO(call):
        """Продолжение заполнения данных клиента"""
        
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Подготовьте документы:\n1. Доверенность",
        )
        user_message_id = message.message_id
        bot.send_message(message.chat.id, text="Неправильный формат ввода".format(message.from_user)) 
def FIO(message, data, user_message_id, user_message_id1):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, user_message_id1)
    bot.delete_message(message.chat.id, message.message_id)

    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, введите ФИО в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, FIO, data, user_message_id, user_message_id)
    else:
        data.update({"fio": message.text})
        if len(message.text.split())==2:
            data.update({"fio_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."})
        else:
            data.update({"fio_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."+list(message.text.split()[2])[0]+"."})
        message = bot.send_message(message.chat.id, text="Введите серию паспорта, например, 1234".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, seria_pasport, data, user_message_id)

def seria_pasport(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 4 цифры. Введите серию паспорта, например, 1234 ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_pasport, data, user_message_id)
        else:
            data.update({"seria_pasport": int(message.text.replace(" ", ""))})
            message = bot.send_message(message.chat.id, text="Введите номер паспорта, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_pasport, data, user_message_id)

def number_pasport(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр. Введите номер паспорта, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_pasport,data, user_message_id)
    else:
        data.update({"number_pasport": int(message.text.replace(" ", ""))})
        message = bot.send_message(message.chat.id, text="Кем выдан паспорт?".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, where_pasport, data, user_message_id)

def where_pasport(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"where_pasport": message.text})
    message = bot.send_message(message.chat.id, text="Когда выдан паспорт? Введите в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, when_pasport, data, user_message_id)

def when_pasport(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)   
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"when_pasport": message.text})
        message = bot.send_message(message.chat.id, text="Введите адрес проживания клиента".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, address, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, введите, когда выдан паспорт в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, when_pasport, data, user_message_id)

def address(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)   
    data.update({"address": message.text})
    message = bot.send_message(message.chat.id, text="Введите почтовый индекс, например, 123456".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, index, data, user_message_id)

def index(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)     
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр. Введите почтовый индекс, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index, data, user_message_id)
    else:
        data.update({"index_postal": int(message.text.replace(" ", ""))})
        message = bot.send_message(message.chat.id, text="Введите номер телефона клиента в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number, data, user_message_id)   

def number(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)     
    if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, введите номер телефона клиента в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number, data, user_message_id)
    else:
        data.update({"number": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату рождения в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth, data, user_message_id)

def date_of_birth(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth": message.text})
        message = bot.send_message(message.chat.id, text="Введите город рождения клиента".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, city_birth, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, введите дату рождения клиента в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth, data, user_message_id)

def city_birth(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    data.update({"city_birth": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_dtp, data, user_message_id)


def date_dtp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    try:
        input_date = datetime.strptime(message.text, "%d.%m.%Y")

        current_date = datetime.now()
        three_years_ago = current_date - timedelta(days=3*365 + 1)

        if input_date > current_date:
            message = bot.send_message(message.chat.id, "Дата ДТП не может быть в будущем! Введите корректную дату ДТП в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_dtp, data, user_message_id)
            return
        if input_date < three_years_ago:
            message = bot.send_message(message.chat.id, "Прошло более трех лет! Введите корректную дату ДТП в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_dtp, data, user_message_id)
            return

        data.update({"date_dtp": message.text})
        message = bot.send_message(message.chat.id, text="Введите время ДТП в формате ЧЧ:ММ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_dtp, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_dtp, data, user_message_id)

def time_dtp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    if len(message.text) != 5 or message.text.count(':') != 1:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат времени!\n"
            "Введите время ДТП в формате ЧЧ:ММ (например: 14:30):"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_dtp, data, user_message_id)
        return
    try:
 
        datetime.strptime(message.text, "%H:%M")

        data.update({"time_dtp": message.text})
        message = bot.send_message(message.chat.id, "Введите адрес ДТП")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, address_dtp, data, user_message_id)    
    except ValueError:
        message = bot.send_message(
            message.chat.id, 
            "Неправильный формат времени!\n"
            "Введите время ДТП в формате ЧЧ:ММ (например: 14:30):"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_dtp, data, user_message_id)

def address_dtp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    data.update({"address_dtp": message.text})

    message = bot.send_message(
        message.chat.id, 
        "Введите марку, модель клиента", 
        reply_markup=None
    )
    user_message_id = message.message_id
    bot.register_next_step_handler(message, marks, data, user_message_id)

def marks(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    data.update({"marks": message.text})
    message= bot.send_message(message.chat.id, text="Введите номер авто клиента".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_auto, data, user_message_id)

def number_auto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    car_number = message.text.replace(" ", "").upper()
    pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
    if re.match(pattern, car_number) and len(car_number) in [8, 9]:
        data.update({"car_number": car_number})
        message = bot.send_message(message.chat.id, "Введите год выпуска авто клиента")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, year_auto, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат!\nВведите номер авто клиента\n"
            "Пример: А123БВ77 или А123БВ777"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_auto, data, user_message_id)

def year_auto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, введите корректный год выпуска авто клиента.\nНапример: 2025".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, year_auto, data, user_message_id)
    else:
        data.update({"year_auto": int(message.text.replace(" ", ""))})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton('САО "Ресо-Гарантия"', callback_data="Reco_NO")
        btn2 = types.InlineKeyboardButton('АО "ГСК "Югория"', callback_data="Ugo_NO")
        btn3 = types.InlineKeyboardButton('АО "Согаз"', callback_data="SOGAZ_NO")
        btn4 = types.InlineKeyboardButton('СПАО "Ингосстрах"', callback_data="Ingo_NO")
        btn5 = types.InlineKeyboardButton('ПАО СК "Росгосстрах"', callback_data="Ros_NO")
        btn6 = types.InlineKeyboardButton('АО "Макс"', callback_data="Maks_NO")
        btn7 = types.InlineKeyboardButton('ПАО «САК «Энергогарант»', callback_data="Energo_NO")
        btn8 = types.InlineKeyboardButton('АО «Совкомбанк страхование»', callback_data="Sovko_NO")
        btn9 = types.InlineKeyboardButton('Другое', callback_data="other_NO")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn5)
        keyboard.add(btn6)
        keyboard.add(btn7)
        keyboard.add(btn8)
        keyboard.add(btn9)
        bot.send_message(message.chat.id, text="Выберите страховую компанию".format(message.from_user), reply_markup=keyboard)

def other_insurance(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"insurance": message.text})
    message = bot.send_message(message.chat.id, text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, fio_culp, data, user_message_id)

def fio_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, введите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
    else:
        data.update({"fio_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите марку, модель виновника ДТП".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, marks_culp, data, user_message_id)

def marks_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    data.update({"marks_culp": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер авто виновника ДТП".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_auto_culp, data, user_message_id)
def number_auto_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    car_number = message.text.replace(" ", "").upper()  # Приводим к верхнему регистру
    pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
    
    # Проверяем, что исходный текст не содержит строчных букв
    original_text = message.text.replace(" ", "")
    has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
    
    if not has_lowercase and re.match(pattern, car_number) and len(car_number) in [8, 9]:
        data.update({"number_auto_culp": str(car_number)})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
        time.sleep(0.5)
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data=f"STS_NO")
        btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data=f"PTS_NO")
        btn3 = types.InlineKeyboardButton("Договор купли-продажи ТС", callback_data=f"DKP_NO")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

        bot.send_message(
            message.chat.id, 
            "Выберите документ о регистрации ТС", 
            reply_markup=keyboard
        )
    else:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат!\nВведите номер авто виновника ДТП\n"
            "Пример: А123БВ77 или А123БВ777\n"
            "Все буквы должны быть заглавными!"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_auto_culp, data, user_message_id)

def seria_docs(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    data.update({"seria_docs": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер документа о регистрации ТС".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_docs, data, user_message_id)

def number_docs(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    data.update({"number_docs": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, data_docs, data, user_message_id)

def data_docs(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id) 
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_docs": message.text})
        data.update({"date_ins": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"year": list(str(datetime.now().year))[2]+list(str(datetime.now().year))[3]})
        data.update({"analis_ins": "Yes"})
        data.update({"Done": "Yes"})
        data.update({"status": 'Отправлен запрос в страховую'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                            "{{ винФИО }}"],
                            [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                str(data["year"]),str(data['client_id']), str(data["fio"]), str(data["fio_culp"])],
                                "Шаблоны\\3. Деликт без ОСАГО\\Деликт (без ОСАГО) 1. Обложка дела.docx",
                                data["fio"]+"\\"+data["fio"]+"_обложка.docx")
        
        replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", 
                           "{{ Дата }}", "{{ ФИО }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}",
                           "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", "{{ Индекс }}","{{ Адрес }}","{{ Дата_ДТП }}",
                           "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                           [str(datetime.now().year), str(data['client_id']), str(data['city']), str(datetime.now().strftime("%d.%m.%Y")),
                            str(data["fio"]), str(data["seria_pasport"]),str(data["number_pasport"]), str(data["where_pasport"]),
                            str(data["when_pasport"]), str(data["index_postal"]), str(data["address"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                            str(data["address_dtp"]), str(data["fio_k"])],
                            "Шаблоны\\3. Деликт без ОСАГО\\Деликт (без ОСАГО) 2. Юр договор.docx",
                             data["fio"]+"\\"+data["fio"]+"_юр_договор.docx")
        
        replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                            [str(data["fio"]), str(data["date_of_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["number"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                data["fio"]+"\\"+data["fio"]+"_заявление_о_выдаче_копии_справкиГИБДД.docx")
        
        replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}","{{ ФИОк }}" ],
                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["number"]),str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                data["fio"]+"\\"+data["fio"]+"_заявление_о_выдаче_док_страх.docx")
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
        time.sleep(0.5)
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data=f"docs1Yes_NO")
        btn2 = types.InlineKeyboardButton("Нет", callback_data=f"docs1No_NO")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)

    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода. Введите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_docs, data, user_message_id)




def clear_chat_history_optimized(message, count):
    """
    Быстрое удаление последних N сообщений
    """
    chat_id = message.chat.id
    current_message_id = message.message_id
    deleted_count = 0
    # Удаляем последние N сообщений без статусных сообщений для максимальной скорости
    for message_id in range(current_message_id, max(1, current_message_id - count), -1):
        try:
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            deleted_count += 1
        except ApiException as e:
            # Пропускаем ошибки и продолжаем
            if "message to delete not found" in str(e).lower():
                continue
            elif "message can't be deleted" in str(e).lower():
                continue
            elif "too many requests" in str(e).lower():
                time.sleep(0.3)  # Короткая пауза при превышении лимитов
                continue
        except Exception:
            continue