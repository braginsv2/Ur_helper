from telebot import types
from datetime import datetime, timedelta
import re
import time
import json
import sqlite3
from num2words import num2words
from word_utils import replace_words_in_word
from database import DatabaseManager, save_client_to_db_with_id


bot = None
user_temp_data = {}


def init_bot(bot_instance, start_handler=None):
    """Инициализация бота в модуле"""
    global bot
    bot = bot_instance

    @bot.callback_query_handler(func=lambda call: call.data == "btn_pit")
    def callback_dtp(call):
        data = {'accident': 'pit'}
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Томск", callback_data="btn_city_Tomsk_pit")
        keyboard.add(btn1)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите город подачи заявления",
            reply_markup=keyboard
        ) 

    @bot.callback_query_handler(func=lambda call: call.data in ["btn_city_Tomsk_pit"])
    def callback_dtp_city(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        time.sleep(0.5)
        if call.data == "btn_city_Tomsk_pit":
            data.update({"city": "Томск"})
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Подготовьте документы:\n1. Паспорт\n2. Данные авто\n3. Документ о регистрации ТС\n4. Сведения об участниках ДТП",
            reply_markup=None)
        message = bot.send_message(call.message.chat.id, "Введите ФИО в формате Иванов Иван Иванович") 
        bot.register_next_step_handler(message, FIO, data)
    @bot.callback_query_handler(func=lambda call: call.data in ["pitdocs1Yes", "pitdocs1No"])
    def callback_send_docs_pit(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        time.sleep(0.5)

        if call.data == "pitdocs1Yes":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_обложка.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_юр_договор.docx", "name": "Юридический договор"}
            ]
            message= bot.send_message(call.message.chat.id, "Отправляю документы...")
            for doc in documents:
                try:
                    with open(doc["path"], 'rb') as document_file:
                        bot.send_document(
                            call.message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(call.message.chat.id, f"Файл не найден: {doc['path']}")
                except Exception as e:
                    bot.send_message(call.message.chat.id, f"Ошибка отправки: {e}")

        user_id = message.from_user.id
        user_temp_data[user_id] = data
        time.sleep(0.5)
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="pitadminYes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="pitadminNo")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Есть ли привлечение администрации к административной ответственности?", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["pitIskYes", "pitIskNo"])
    def callback_send_docs2_pit(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        time.sleep(0.5)

        if call.data == "pitIskYes":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_анализ_дтп.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_иск_к_администрации.docx", "name": "Юридический договор"}
            ]
            message= bot.send_message(call.message.chat.id, "Отправляю документы...")
            for doc in documents:
                try:
                    with open(doc["path"], 'rb') as document_file:
                        bot.send_document(
                            call.message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(call.message.chat.id, f"Файл не найден: {doc['path']}")
                except Exception as e:
                    bot.send_message(call.message.chat.id, f"Ошибка отправки: {e}")

        start_handler(call.message)
    
    @bot.callback_query_handler(func=lambda call: call.data in ["pitadminYes", "pitadminNo"])
    def callback_pit_admin(call):
        user_id = message.from_user.id
 
        
        data = user_temp_data[user_id]
        time.sleep(0.5)
         

        if call.data == "pitadminYes":
            bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="""Подготовьте документы:
1. Определение ГИБДД
2. Протокол об административном правонарушении
3. Экспертиза
4. Доверенность
5. Чек нотариуса и юриста
            """,
            reply_markup=None
            ) 
            message = bot.send_message(message.chat.id, text="Введите цену по экспертизе в рублях")
            bot.register_next_step_handler(message, coin_exp, data)
    @bot.callback_query_handler(func=lambda call: call.data in ["gibdd", "avarkom"])
    def callback_who_dtp_pit(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        time.sleep(0.5)
          
        if call.data == "gibdd":
            data.update({"who_dtp": "ГИБДД"})
        elif call.data == "avarkom":
            data.update({"who_dtp": "Аварком"})

        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите улицу, на которой яма",
            reply_markup=None
        )  
        bot.register_next_step_handler(message, street, data)
    @bot.callback_query_handler(func=lambda call: call.data in ["sud1", "sud2", "sud3", "sud4", "sud5", "sud6", "sudOther"])
    def callback_insurance(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
        time.sleep(0.5)
         
        if call.data == "sud1":
            data.update({"sud": 'Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58'})
        elif call.data == "sud2":
            data.update({"sud": 'Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45'})
        elif call.data == "sud3":
            data.update({"sud": 'Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21'})
        elif call.data == "sud4":
            data.update({"sud": 'Томский областной суд, 634003, г. Томск, пер. Макушина, 8'})
        elif call.data == "sud5":
            data.update({"sud": 'Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6'})
        elif call.data == "sud6":
            data.update({"sud": 'Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8'})
        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название суда",
            reply_markup=None
            )
            bot.register_next_step_handler(message, sud_other, data) 

        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите стоимость государственной пошлины",
            reply_markup=None
        ) 
  
        bot.register_next_step_handler(message, gos_money, data)

def FIO(message, data):
    if len(message.text.split())<2:
            bot.send_message(message.chat.id, text="Неправильный формат ввода".format(message.from_user))
            bot.register_next_step_handler(message, FIO, data)
    else:
        data.update({"fio": message.text})
        if len(message.text.split())==2:
            data.update({"fio_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."})
        else:
            data.update({"fio_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."+list(message.text.split()[2])[0]+"."})
        bot.send_message(message.chat.id, text="Введите серию паспорта".format(message.from_user))
        bot.register_next_step_handler(message, seria_pasport, data)

def seria_pasport(message, data):
        if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
            bot.send_message(message.chat.id, text="Неправильный формат ввода".format(message.from_user))
            bot.register_next_step_handler(message, seria_pasport, data)
        else:
            data.update({"seria_pasport": int(message.text.replace(" ", ""))})
            bot.send_message(message.chat.id, text="Введите номер паспорта".format(message.from_user))
            bot.register_next_step_handler(message, number_pasport, data)

def number_pasport(message, data):
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода".format(message.from_user))
        bot.register_next_step_handler(message, number_pasport,data)
    else:
        data.update({"number_pasport": int(message.text.replace(" ", ""))})
        bot.send_message(message.chat.id, text="Кем выдан паспорт?".format(message.from_user))
        bot.register_next_step_handler(message, where_pasport, data)

def where_pasport(message, data):
    data.update({"where_pasport": message.text})
    bot.send_message(message.chat.id, text="Когда выдан паспорт? Введите в формате ДД.ММ.ГГГГ".format(message.from_user))
    bot.register_next_step_handler(message, when_pasport, data)

def when_pasport(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"when_pasport": message.text})
        bot.send_message(message.chat.id, text="Введите адрес проживания клиента".format(message.from_user))
        bot.register_next_step_handler(message, address, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода".format(message.from_user))
        bot.register_next_step_handler(message, when_pasport, data)

def address(message, data):
    data.update({"address": message.text})
    bot.send_message(message.chat.id, text="Введите почтовый индекс".format(message.from_user))
    bot.register_next_step_handler(message, index, data)

def index(message, data):
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр".format(message.from_user))
        bot.register_next_step_handler(message, index, data)
    else:
        data.update({"index_postal": int(message.text.replace(" ", ""))})
        bot.send_message(message.chat.id, text="Введите номер телефона клиента в формате +79XXXXXXXXX".format(message.from_user))
        bot.register_next_step_handler(message, number, data)   

def number(message, data):
    if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате +79XXXXXXXXX".format(message.from_user))
        bot.register_next_step_handler(message, number, data)
    else:
        data.update({"number": message.text})
        bot.send_message(message.chat.id, text="Введите дату рождения в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_of_birth, data)

def date_of_birth(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth": message.text})
        bot.send_message(message.chat.id, text="Введите город рождения клиента".format(message.from_user))
        bot.register_next_step_handler(message, city_birth, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_of_birth, data)

def city_birth(message, data):
    data.update({"city_birth": message.text})
    bot.send_message(message.chat.id, text="Введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
    bot.register_next_step_handler(message, date_dtp, data)


def date_dtp(message, data):
    try:
        input_date = datetime.strptime(message.text, "%d.%m.%Y")

        current_date = datetime.now()
        three_years_ago = current_date - timedelta(days=3*365 + 1)

        if input_date > current_date:
            bot.send_message(message.chat.id, "Дата ДТП не может быть в будущем! Введите корректную дату")
            bot.register_next_step_handler(message, date_dtp, data)
            return
        if input_date < three_years_ago:
            bot.send_message(message.chat.id, "Прошло более трех лет! Введите корректную дату")
            bot.register_next_step_handler(message, date_dtp, data)
            return

        data.update({"date_dtp": message.text})
        bot.send_message(message.chat.id, text="Введите время ДТП в формате ЧЧ:ММ".format(message.from_user))
        bot.register_next_step_handler(message, time_dtp, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_dtp, data)

def time_dtp(message, data):
    if len(message.text) != 5 or message.text.count(':') != 1:
        bot.send_message(
            message.chat.id,
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        bot.register_next_step_handler(message, time_dtp, data)
        return
    try:
 
        datetime.strptime(message.text, "%H:%M")

        data.update({"time_dtp": message.text})
        bot.send_message(message.chat.id, "Введите адрес ДТП")
        bot.register_next_step_handler(message, address_dtp, data)    
    except ValueError:
        bot.send_message(
            message.chat.id, 
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        bot.register_next_step_handler(message, time_dtp, data)

def address_dtp(message, data):
    data.update({"address_dtp": message.text})
    user_id = message.from_user.id
    user_temp_data[user_id] = data
    time.sleep(0.5)
    keyboard = types.InlineKeyboardMarkup()

    btn1 = types.InlineKeyboardButton("ГИБДД", callback_data=f"gibdd")
    btn2 = types.InlineKeyboardButton("Аварком", callback_data=f"avarkom")
    
    keyboard.add(btn1)
    keyboard.add(btn2)
    

    bot.send_message(
        message.chat.id, 
        "Кого вызывали на фиксацию дтп", 
        reply_markup=keyboard
    )
def street(message, data):
    data.update({"street": message.text})
    bot.send_message(message.chat.id, text="Введите марку, модель клиента".format(message.from_user))
    bot.register_next_step_handler(message, marks, data)

def marks(message, data):
    data.update({"marks": message.text})
    bot.send_message(message.chat.id, text="Введите номер авто клиента".format(message.from_user))
    bot.register_next_step_handler(message, number_auto, data)

def number_auto(message, data):
    car_number = message.text.replace(" ", "").upper()
    pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
    if re.match(pattern, car_number) and len(car_number) in [8, 9]:
        data.update({"car_number": car_number})
        bot.send_message(message.chat.id, "Введите год выпуска авто клиента")
        bot.register_next_step_handler(message, year_auto, data)
    else:
        bot.send_message(
            message.chat.id,
            "Неправильный формат!\n"
            "Пример: А123БВ77 или А123БВ777"
        )
        bot.register_next_step_handler(message, number_auto, data)

def year_auto(message, data):
    if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите корректный год.\nНапример: 2025".format(message.from_user))
        bot.register_next_step_handler(message, year_auto, data)
    else:
        data.update({"year_auto": int(message.text.replace(" ", ""))})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
        time.sleep(0.5)
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data=f"STS_{user_id}")
        btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data=f"PTS_{user_id}")
        btn3 = types.InlineKeyboardButton("Договор купли-продажи ТС", callback_data=f"DKP_{user_id}")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

        bot.send_message(
            message.chat.id, 
            "Выберите документ о регистрации ТС", 
            reply_markup=keyboard
        )



def seria_docs(message, data):
    data.update({"seria_docs": message.text})
    bot.send_message(message.chat.id, text="Введите номер документа о регистрации ТС".format(message.from_user))
    bot.register_next_step_handler(message, number_docs, data)

def number_docs(message, data):
    data.update({"number_docs": message.text})
    bot.send_message(message.chat.id, text="Введите дату выдачи документа о регистрации ТС".format(message.from_user))
    bot.register_next_step_handler(message, data_docs, data)

def data_docs(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_docs": message.text})
        data.update({"date_ins": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"year": list(str(datetime.now().year))[2]+list(str(datetime.now().year))[3]})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        print(data)
        replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                            "{{ Телефон }}", "{{ Город }}"],
                            [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                str(data["year"]),str(data['client_id']), str(data["fio"]), str(data["number"]), str(data["city"])],
                                "Шаблоны\\2. Яма\\Яма 1. Обложка дела.docx",
                                data["fio"]+"\\"+data["fio"]+"_обложка.docx")
        
        replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", 
                           "{{ Дата }}", "{{ ФИО }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}",
                           "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", "{{ Индекс }}","{{ Адрес }}","{{ Дата_ДТП }}",
                           "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                           [str(datetime.now().year), str(data['client_id']), "Томск", str(datetime.now().strftime("%d.%m.%Y")),
                            str(data["fio"]), str(data["seria_pasport"]),str(data["number_pasport"]), str(data["where_pasport"]),
                            str(data["when_pasport"]), str(data["index_postal"]), str(data["address"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                            str(data["address_dtp"]), str(data["fio_k"])],
                            "Шаблоны\\2. Яма\\Яма 2. Юр договор.docx",
                             data["fio"]+"\\"+data["fio"]+"_юр_договор.docx")
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
        time.sleep(0.5)
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data=f"pitdocs1Yes_{user_id}")
        btn2 = types.InlineKeyboardButton("Нет", callback_data=f"pitdocs1No_{user_id}")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)

    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода".format(message.from_user))
        bot.register_next_step_handler(message, data_docs, data)


def coin_exp(message, data):
    data.update({"coin_exp": message.text})
    bot.send_message(message.chat.id, text="Введите дату экспертизы в формате ДД.ММ.ГГГГ".format(message.from_user))
    bot.register_next_step_handler(message, date_exp, data)
def date_exp(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_exp": message.text})
        bot.send_message(message.chat.id, text="Введите дату осмотра авто экспертом в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_sto, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_exp, data)
def date_sto(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_sto": message.text})
        bot.send_message(message.chat.id, text="Введите перечень поврежденных частей через запятую".format(message.from_user))
        bot.register_next_step_handler(message, coin_exp_izn, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_sto, data)
def coin_exp_izn(message, data):
    data.update({"coin_exp_izn": message.text})
    bot.send_message(message.chat.id, text="Введите номер определения ГАИ".format(message.from_user))
    bot.register_next_step_handler(message, N_gui, data)

def N_gui(message, data):
    data.update({"N_gui": message.text})
    bot.send_message(message.chat.id, text="Введите дату определения ГАИ".format(message.from_user))
    bot.register_next_step_handler(message, date_gui, data)
def date_gui(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_gui": message.text})
        bot.send_message(message.chat.id, text="Введите номер протокола об административном правонарушении".format(message.from_user))
        bot.register_next_step_handler(message, N_prot, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_gui, data)
def N_prot(message, data):
    data.update({"N_prot": message.text})
    bot.send_message(message.chat.id, text="Введите дату протокола об административном правонарушении".format(message.from_user))
    bot.register_next_step_handler(message, date_prot, data)
def date_prot(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_prot": message.text})
        bot.send_message(message.chat.id, text="Введите дату обследования дорожного покрытия".format(message.from_user))
        bot.register_next_step_handler(message, date_road, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_prot, data)
def date_road(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_road": message.text})
        bot.send_message(message.chat.id, text="Введите дату искового заявления".format(message.from_user))
        bot.register_next_step_handler(message, date_isk, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_road, data)
def date_isk(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_isk": message.text})
        bot.send_message(message.chat.id, text="Введите стоимость услуг нотариуса".format(message.from_user))
        bot.register_next_step_handler(message, coin_not, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_isk, data)

def coin_not(message, data):
    data.update({"coin_not": message.text})
    bot.send_message(message.chat.id, text="Введите номер доверенности".format(message.from_user))
    bot.register_next_step_handler(message, N_dov_not, data)

def N_dov_not(message, data):
    data.update({"N_dov_not": message.text})
    bot.send_message(message.chat.id, text="Введите дату доверенности".format(message.from_user))
    bot.register_next_step_handler(message, data_dov_not, data)
def data_dov_not(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_dov_not": message.text})
        bot.send_message(message.chat.id, text="Введите ФИО представителя в формате Иванов Иван Иванович".format(message.from_user))
        bot.register_next_step_handler(message, fio_not, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, data_dov_not, data)
def fio_not(message, data):
    if len(message.text.split())<2:
            bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате Иванов Иван Иванович".format(message.from_user))
            bot.register_next_step_handler(message, fio_not, data)
    else:
        data.update({"fio_not": message.text})
        bot.send_message(message.chat.id, text="Введите номер квитанции об оплате услуг нотариуса".format(message.from_user))
        bot.register_next_step_handler(message, N_kv_not, data)
def N_kv_not(message, data):
    data.update({"N_kv_not": message.text})
    bot.send_message(message.chat.id, text="Введите дату квитанции об оплате услуг нотариуса".format(message.from_user))
    bot.register_next_step_handler(message, date_kv_not, data)
def date_kv_not(message, data):
    if len(message.text.split())<2:
            bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате Иванов Иван Иванович".format(message.from_user))
            bot.register_next_step_handler(message, date_kv_not, data)
    else:
        data.update({"date_kv_not": message.text})
        bot.send_message(message.chat.id, text="Введите номер чека об оплате юридических услуг".format(message.from_user))
        bot.register_next_step_handler(message, N_kv_ur, data)
def N_kv_ur(message, data):
    data.update({"N_kv_ur": message.text})
    bot.send_message(message.chat.id, text="Введите дату чека об оплате юридических услуг".format(message.from_user))
    bot.register_next_step_handler(message, date_kv_ur, data)
def date_kv_ur(message, data):
    if len(message.text.split())<2:
            bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате Иванов Иван Иванович".format(message.from_user))
            bot.register_next_step_handler(message, date_kv_ur, data)
    else:
        data.update({"date_kv_ur": message.text})

        user_id = message.from_user.id
        user_temp_data[user_id] = data
        time.sleep(0.5)
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("1", callback_data=f"sud1_{user_id}")
        btn2 = types.InlineKeyboardButton("2", callback_data=f"sud2_{user_id}")
        btn3 = types.InlineKeyboardButton("3", callback_data=f"sud3_{user_id}")
        btn4 = types.InlineKeyboardButton("4", callback_data=f"sud4_{user_id}")
        btn5 = types.InlineKeyboardButton("5", callback_data=f"sud5_{user_id}")
        btn6 = types.InlineKeyboardButton("6", callback_data=f"sud6_{user_id}")
        btn7 = types.InlineKeyboardButton("Другое", callback_data=f"sudOther_{user_id}")
        keyboard.add(btn1, btn2, btn3)
        keyboard.add(btn4, btn5, btn6)
        keyboard.add(btn7)

        bot.send_message(message.chat.id, text="""Выберите суд
1. Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58
2. Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45
3. Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21
4. Томский областной суд, 634003, г. Томск, пер. Макушина, 8
5. Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6
6. Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8""", reply_markup=keyboard)
        
def sud_other(message, data):
    data.update({"sud": message.text})
    bot.send_message(message.chat.id, text="Введите стоимость государственной пошлины".format(message.from_user))
    bot.register_next_step_handler(message, gos_money, data)
def gos_money(message, data):
    data.update({"gos_money": message.text})
    data.update({"date_ins": str(datetime.now().strftime("%d.%m.%Y"))})
    try:
        client_id, updated_data = save_client_to_db_with_id(data)
        data.update(updated_data)
    except Exception as e:
        print(f"Ошибка базы данных: {e}")
    print(data)
    replace_words_in_word(["{{ Дата_ДТП }}", "{{ Марка_модель }}", "{{ Год_авто }}", 
                        "{{ Nавто_клиента }}", "{{ ФИО }}", "{{ Адрес_ДТП }}","{{ Город }}", "{{ ФИОк }}",
                        "{{ Nопределения }}", "{{ Дата_определения }}", "{{ Дата_протокола }}", "{{ Nпротокола }}",
                        "{{ Улица }}","{{ Дата_обследования }}", "{{ Год }}","{{ NКлиента }}", "{{ Дата_экспертизы }}", 
                        "{{ Дата_осмотра }}","{{ Перечень_ущерба }}", "{{ Экспертиза }}", "{{ Экспертиза_текст }}",
                        "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}"],
                        [str(data["date_dtp"]), str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["fio"]),
                            str(data["address_dtp"]),str(data['city']), str(data["fio_k"]), str(data["N_gui"]), str(data["date_gui"]),
                            str(data["date_prot"]),str(data['N_prot']), str(data["street"]), str(data["date_road"]),
                            str(data["year"]),str(data['client_id']), str(data["date_exp"]),str(data["date_sto"]), str(data["coin_exp_izn"]),str(data["coin_exp"]),
                            str(num2words(data["coin_exp"], lang ='ru')),str(data['N_dov_not']), str(data["data_dov_not"]), str(data["fio_not"])],
                            "Шаблоны\\2. Яма\\Яма 3.  Анализ ДТП.docx",
                            data["fio"]+"\\"+data["fio"]+"_анализ_дтп.docx")
    
    replace_words_in_word(["{{ Суд }}", "{{ ФИО }}", "{{ ДР }}", 
                        "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                        "{{ Индекс }}", "{{ Адрес }}","{{ Телефон }}","{{ Представитель }}",
                        "{{ NДоверенности }} ", "{{ Дата_доверенности }}", "{{ Экспертиза }}",
                        "{{ Экспертиза_текст }}", "{{ Цена_пошлины }}","{{ Марка_модель }}", "{{ Nавто_клиента }}",
                        "{{ Документ }}", "{{ Док_серия }}", "{{ Док_номер }}","{{ Док_когда }}","{{ Дата_ДТП }}",
                        "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Перечень_ущерба }}", "{{ Сотрудник }}",
                        "{{ Nопределения }}", "{{ Дата_определения }}", "{{ Улица }}","{{ Nпротокола }}","{{ Дата_протокола }}",
                        "{{ Дата_обследования }}", "{{ Год }}","{{ NКлиента }}", "{{ Дата_экспертизы }}",
                        "{{ Цена_пошлины_текст }}","{{ Чек_экспертизы }}",
                        "{{ Nчека_юр }}", "{{ Дата_чека_юр }}", "{{ Цена_нотариус }}","{{ Цена_нотариус_текст }}","{{ Nчека_нотариус }}",
                        "{{ Дата_чека_нотариус }}", "{{ Дата_искового_заявления }}"],
                        [str(data["sud"]), str(data['fio']), str(data['date_of_birth']), str(data['seria_pasport']),
                        str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["index_postal"]),
                        str(data["address"]), str(data["number"]), str(data["fio_not"]), str(data["N_dov_not"]), str(data["data_dov_not"]), 
                        str(data["coin_exp"]), str(num2words(data["coin_exp"], lang ='ru')),str(data["gos_money"]), str(data['marks']), str(data['car_number']),
                        str(data['docs']), str(data["seria_docs"]), str(data['number_docs']), str(data['data_docs']), str(data['date_dtp']),
                        str(data["time_dtp"]), str(data["address_dtp"]),str(data["coin_exp_izn"]), str(data["who_dtp"]),
                        str(data["N_gui"]), str(data["date_gui"]), str(data["street"]), str(data["N_prot"]), str(data["date_prot"]), 
                        str(data["date_road"]), str(data["year"]),str(data["client_id"]), str(data['date_exp']), str(num2words(data["gos_money"], lang ='ru')),
                        str(data['N_kv_exp']), str(data["N_kv_ur"]), str(data['date_kv_ur']),str(data['coin_not']), str(num2words(data["coin_not"], lang ='ru')),
                        str(data['N_kv_not']), str(data['date_kv_not']), str(data['date_isk'])],
                        "Шаблоны\\2. Яма\\Яма 4. Иск к администрации.docx",
                            data["fio"]+"\\"+data["fio"]+"_иск_к_администрации.docx")
    
    user_id = message.from_user.id
    user_temp_data[user_id] = data
    time.sleep(0.5)
    keyboard = types.InlineKeyboardMarkup()

    btn1 = types.InlineKeyboardButton("Да", callback_data=f"pitIskYes")
    btn2 = types.InlineKeyboardButton("Нет", callback_data=f"pitIsk1No")
    keyboard.add(btn1, btn2)
    bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)

