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

insurance_companies = [
    ('АО "Согаз"', "SOGAZ"),
    ('ПАО СК "Росгосстрах"', "Ros"),
    ('САО "Ресо-Гарантия"', "Reco"),
    ('АО "АльфаСтрахование"', "Alfa"),
    ('СПАО "Ингосстрах"', "Ingo"),
    ('САО "ВСК"', "VSK"),
    ('ПАО «САК «Энергогарант»', "Energo"),
    ('АО "ГСК "Югория"', "Ugo"),
    ('ООО СК "Согласие"', "Soglasie"),
    ('АО «Совкомбанк страхование»', "Sovko"),
    ('АО "Макс"', "Maks"),
    ('ООО СК "Сбербанк страхование"', "Sber"),
    ('АО "Т-Страхование"', "T-ins"),
    ('ПАО "Группа Ренессанс Страхование"', "Ren"),
    ('АО СК "Чулпан"', "Chul")
]
def create_insurance_keyboard(page=0, items_per_page=5):
    """Создает клавиатуру с пагинацией для страховых компаний"""
    keyboard = types.InlineKeyboardMarkup()
    
    # Вычисляем начальный и конечный индексы для текущей страницы
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    # Добавляем кнопки для текущей страницы
    for name, callback_data in insurance_companies[start_idx:end_idx]:
        keyboard.add(types.InlineKeyboardButton(name, callback_data=callback_data))
    
    # Добавляем кнопки навигации
    row_buttons = []
    
    # Кнопка "Назад" если это не первая страница
    if page > 0:
        row_buttons.append(types.InlineKeyboardButton('◀️ Назад', callback_data=f'ins_page_{page-1}'))
    
    # Кнопка "Еще" если есть следующая страница
    if end_idx < len(insurance_companies):
        row_buttons.append(types.InlineKeyboardButton('Еще ▶️', callback_data=f'ins_page_{page+1}'))
    
    if row_buttons:
        keyboard.row(*row_buttons)
    
    # Всегда добавляем кнопку "Другое" в конце
    keyboard.add(types.InlineKeyboardButton('Другое', callback_data="other"))
    
    return keyboard

def init_bot(bot_instance, start_handler=None, callback_handler=None):
    """Инициализация бота в модуле"""
    global bot, callback_client_details2_handler
    bot = bot_instance
    callback_client_details2_handler = callback_handler

    @bot.callback_query_handler(func=lambda call: call.data == "btn_dtp")
    def callback_dtp(call):
        data = {'accident': 'dtp'}
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data=f"btn_dtp_own")
        btn2 = types.InlineKeyboardButton("Нет", callback_data=f"btn_dtp_Nown")
        keyboard.add(btn1)
        keyboard.add(btn2)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text='Клиент подготовит нотариальную доверенность для работы "под ключ"?',
            reply_markup=keyboard
        )
       
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_dtp_own", "btn_dtp_Nown"])
    def callback_dtp_own(call):
        if call.data == "btn_dtp_own":
            call.data = "btn_dtp_own"
        elif call.data =="btn_dtp_Nown":
            call.data = "btn_dtp_Nown"
        else:
            return
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        data.update({"answer_ins": ""}) 

        data.update({"sobstvenik": "Yes" if call.data == "btn_dtp_own" else "No"})
        user_temp_data[user_id] = data
         

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="btn_dtp_ev_Yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="btn_dtp_ev_No")
        btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_dtp")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Эвакуатор вызывали?",
            reply_markup=keyboard
        )  

    @bot.callback_query_handler(func=lambda call: call.data in ["btn_dtp_ev_Yes", "btn_dtp_ev_No"])
    def callback_dtp_ev(call):
        if call.data == "btn_dtp_ev_Yes":
            call.data = "btn_dtp_ev_Yes"
        elif call.data == "btn_dtp_ev_No":
            call.data = "btn_dtp_ev_No"
        else:
            return
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         

        data.update({"ev": "Yes" if call.data == "btn_dtp_ev_Yes" else "No"})
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()      
        btn1 = types.InlineKeyboardButton("Томск", callback_data="btn_city_Tomsk")
        keyboard.add(btn1) 
        if data["sobstvenik"] == "Yes":
            btn2 = types.InlineKeyboardButton("Назад", callback_data="btn_dtp_own")
            keyboard.add(btn2)
        elif data["sobstvenik"] == "No":
            btn2 = types.InlineKeyboardButton("Назад", callback_data="btn_dtp_Nown")
            keyboard.add(btn2)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите город подачи заявления",
            reply_markup=keyboard
        )  

    @bot.callback_query_handler(func=lambda call: call.data in ["btn_city_Tomsk"])
    def callback_dtp_city(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        if call.data == "btn_city_Tomsk":
            data.update({"city": "Томск"})
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="""Подготовьте документы:
                1. Паспорт
                2. Данные авто
                3. Документ о регистрации ТС
                4. Сведения об участниках ДТП
                5. Страховой полис
                6. Банковские реквизиты
                """,
            reply_markup=None
        )
        user_message_id = message.message_id 
        message = bot.send_message(call.message.chat.id, "Введите ФИО клиента в формате Иванов Иван Иванович")
        user_message_id1 = message.message_id
        bot.register_next_step_handler(message, FIO, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data in ["zayev_ins"])
    def callback_dtp_cityzayev_ins(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        if data['sobstvenik'] == 'No':
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="""Подготовьте документы:
                1. Паспорт
                2. Данные авто
                3. Документ о регистрации ТС
                4. Сведения об участниках ДТП
                5. Страховой полис
                6. Банковские реквизиты
                """,
                reply_markup=None
            )
        else:
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="""Подготовьте документы:
                1. Нотариальная доверенность
                2. Данные авто
                3. Документ о регистрации ТС
                4. Сведения об участниках ДТП
                5. Страховой полис
                6. Банковские реквизиты
                """,
                reply_markup=None
            )
        user_message_id = message.message_id 
        message = bot.send_message(call.message.chat.id, "Введите марку, модель авто клиента")
        user_message_id1 = message.message_id
        bot.register_next_step_handler(message, marks, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data in ["gibdd", "avarkom", "evro"])
    def callback_who_dtp(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        user_message_id = [] 
          
        if call.data == "gibdd":
            data.update({"who_dtp": "ГИБДД"})
        elif call.data == "avarkom":
            data.update({"who_dtp": "Аварком"})
        elif call.data == "evro":
            data.update({"who_dtp": "Евро-протокол"})
        data.update({"status": 'Оформлен договор'})
        data.update({"year": list(str(datetime.now().year))[2]+list(str(datetime.now().year))[3]})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
            data['client_id'] = "70001"
        create_fio_data_file(data)
        #Юр.Договор
        replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", 
                            "{{ Дата }}", "{{ ФИО }}","{{ ДР }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}",
                            "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", "{{ Индекс }}","{{ Адрес }}","{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                            [str(data['year']), str(data['client_id']), str(data["city"]), str(datetime.now().strftime("%d.%m.%Y")),
                                str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),str(data["number_pasport"]), str(data["where_pasport"]),
                                str(data["when_pasport"]), str(data["index_postal"]), str(data["address"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                                str(data["address_dtp"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\1. На ремонт\\2. Юр договор.docx",
                                data["fio"]+"\\Документы\\"+"2. Юр договор.docx")
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="Yes_ur")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="No_ur")
        keyboard.add(btn1, btn2)
        bot.send_message(call.message.chat.id, text="Данные сохранены, отправить вам документы?", reply_markup=keyboard) 

    @bot.callback_query_handler(func=lambda call: call.data in ["STS", "PTS", "DKP"])
    def callback_docs(call):
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
        user_message_id = [] 
          
        if call.data == "STS":
            data.update({"docs": "СТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_docs, data, user_message_id)

        elif call.data == "PTS":
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
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('ins_page_'))
    def handle_insurance_pagination(call):
        """Обрабатывает пагинацию страховых компаний"""
        try:
            page = int(call.data.split('_')[2])
            keyboard = create_insurance_keyboard(page)
            
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error handling pagination: {e}")

    @bot.callback_query_handler(func=lambda call: call.data in ["Reco", "Ugo", "SOGAZ", "Ingo", "Ros", "Maks", "Energo", "Sovko", "Alfa", "VSK", "Soglasie", "Sber", "T-ins", "Ren", "Chul", "other"])
    def callback_insurance(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        user_message_id = [] 
        
        # Обработка выбора страховой компании
        insurance_mapping = {
            "SOGAZ": 'АО "Согаз"',
            "Ros": 'ПАО СК "Росгосстрах"',
            "Reco": 'САО "Ресо-Гарантия"',
            "Alfa": 'АО "АльфаСтрахование"',
            "Ingo": 'СПАО "Ингосстрах"',
            "VSK": 'САО "ВСК"',
            "Energo": 'ПАО «САК «Энергогарант»',
            "Ugo": 'АО "ГСК "Югория"',
            "Soglasie": 'ООО СК "Согласие"',
            "Sovko": 'АО «Совкомбанк страхование»',
            "Maks": 'АО "Макс"',
            "Sber": 'ООО СК "Сбербанк страхование"',
            "T-ins": 'АО "Т-Страхование"',
            "Ren": 'ПАО "Группа Ренессанс Страхование"',
            "Chul": 'АО СК "Чулпан"'
        }
        
        if call.data in insurance_mapping:
            data.update({"insurance": insurance_mapping[call.data]})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию страхового полиса",
                reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        else: 
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании",
                reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, other_insurance, data, user_message_id) 

    @bot.callback_query_handler(func=lambda call: call.data in ["sud1", "sud2", "sud3", "sud4", "sud5", "sud6", "sudOther"])
    def callback_insurance(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
        user_message_id = []  
        if call.data == "sud1":
            data.update({"sud": 'Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud2":
            data.update({"sud": 'Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud3":
            data.update({"sud": 'Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud4":
            data.update({"sud": 'Томский областной суд, 634003, г. Томск, пер. Макушина, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud5":
            data.update({"sud": 'Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud6":
            data.update({"sud": 'Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название суда",
            reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, sud_other, data, user_message_id) 
    @bot.callback_query_handler(func=lambda call: call.data in ["not_rogalev","not_other"])
    def callback_notarius(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
        
          
        if call.data == "not_rogalev":
            data.update({"fio_not": 'Рогалев Семен Иннокентьевич'})
            if data["answer_ins"] == "NOOSAGO":
                data.update({"analis_ins": "Yes"})
                data.update({"pret_sto": "No"})
                data.update({"pret": "No"})
                data.update({"ombuc": "req"})
                data.update({"status": 'Отправлен запрос в страховую'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
                replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                            [str(data["fio"]), str(data["date_of_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["number"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                data["fio"]+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx")
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}","{{ ФИОк }}" ],
                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["number"]),str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                data["fio"]+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx")
                
                user_id = call.message.from_user.id
                user_temp_data[user_id] = data
                 
                keyboard = types.InlineKeyboardMarkup()

                btn1 = types.InlineKeyboardButton("Да", callback_data="YesNOOSAGO")
                btn2 = types.InlineKeyboardButton("Нет", callback_data="NoNOOSAGO")
                keyboard.add(btn1, btn2)
                bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Данные сохранены, отправить вам документы?",
                reply_markup=keyboard
                ) 
            else:
                user_id = call.message.from_user.id
                user_temp_data[user_id] = data
                 
                keyboard = types.InlineKeyboardMarkup()

                btn1 = types.InlineKeyboardButton("+79966368941", callback_data="number_rogalev")
                btn2 = types.InlineKeyboardButton("Другое", callback_data="number_not_other")
                keyboard.add(btn1)
                keyboard.add(btn2)
                bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите номер телефона представителя",
                reply_markup=keyboard
                ) 

        else:
            user_message_id = [] 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО представителя в формате Иванов Иван Иванович",
            reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_not, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["number_rogalev","number_not_other"])
    def callback_number_notarius(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        if call.data == "number_rogalev":
            data.update({"number_not": '+79966368941'})
            if data['sobstvenik'] == 'Yes' and data['bank'] =='':
                message = bot.edit_message_text(
                chat_id = call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название банка получателя клиента",
                reply_markup=None
                ) 
                user_message_id = message.message_id
                bot.register_next_step_handler(message, bank, data, user_message_id)
            elif data['sobstvenik'] == 'Yes' and data['dop_osm'] == '':
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
                keyboard = types.InlineKeyboardMarkup()

                btn1 = types.InlineKeyboardButton("Да", callback_data=f"dopYes")
                btn2 = types.InlineKeyboardButton("Нет", callback_data=f"dopNo")

                keyboard.add(btn1)
                keyboard.add(btn2)
                message = bot.edit_message_text(
                chat_id = call.message.chat.id,
                message_id=call.message.message_id,
                text="Необходим дополнительный осмотр автомобиля?",
                reply_markup=keyboard
                ) 
                
        
            else:
                data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
                data.update({"analis_ins": "Yes"})
                data.update({"pret_sto": "Yes"})
                data.update({"status": 'Отправлена претензия в страховую'}) 
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
                if data['vibor'] == "vibor1":
                    replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                        "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                        "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                        "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                        "{{ Адрес_ДТП }}", "{{ Организация }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}",
                                        "{{ С_учетом_износа }}", "{{ Выплата_ОСАГО }}","{{ Дата_претензии }}"],
                                        [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                            str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                            str(data["org_exp"]), str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]),
                                            str(data["coin_osago"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                            "Шаблоны\\1. ДТП\\1. На ремонт\\Выплата без согласования\\6. Претензия в страховую Выплата без согласования.docx",
                                            data["fio"]+"\\Документы\\"+"6. Претензия в страховую Выплата без согласования.docx")
                elif data['viborRem'] == "viborRem1":
                    replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                        "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                        "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                        "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                        "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ Дата_предоставления_ТС }}",
                                        "{{ СТО }}", "{{ Дата_отказа_СТО }}","{{ Дата_претензии }}","{{ Город_СТО }}","{{ Марка_модель }}", "{{ Nавто_клиента }}"],
                                        [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                            str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                            str(data["date_napr_sto"]), str(data["N_sto"]), str(data["date_sto"]),str(data["name_sto"]),
                                            str(data["data_otkaz_sto"]), str(data["date_pret"]), str(data["city"]), str(data["marks"]),str(data["car_number"])],
                                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\7. Претензия в страховую СТО отказала.docx",
                                            data["fio"]+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx")
                elif data['viborRem'] == "viborRem3":
                    replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                        "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                        "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                        "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                        "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}",
                                        "{{ СТО }}", "{{ Индекс_СТО }}","{{ Адрес_СТО }}","{{ Город_СТО }}","{{ Номер_направления_на_ремонт }}","{{ Дата_направления }}",
                                        "{{ Марка_модель }}", "{{ Nавто_клиента }}","{{ Дата_претензии }}"],
                                        [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                            str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                            str(data["date_napr_sto"]), str(data["N_sto"]), str(data["name_sto"]),str(data["index_sto"]),str(data["address_sto"]),
                                            str(data["city_sto"]), str(data["N_sto"]), str(data["date_napr_sto"]), str(data["marks"]),str(data["car_number"]), str(data["date_pret"])],
                                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\6. Претензия в страховую  СТО свыше 50 км.docx",
                                            data["fio"]+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx")
                
                user_id = call.message.from_user.id
                user_temp_data[user_id] = data
                
                keyboard = types.InlineKeyboardMarkup()

                btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
                btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
                keyboard.add(btn1, btn2)
                message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Данные сохранены, отправить вам документы?",
                reply_markup=keyboard
                )
        else: 
            user_message_id =[]
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер телефона представителя в формате +79XXXXXXXXX",
            reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_not, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["Yes_ur", "No_ur"])
    def callback_send_docs_ur(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
        if call.data == "Yes_ur":
            documents = [
            {"path": data["fio"]+"\\Документы\\" + "2. Юр договор.docx", "name": "Юридический договор"},
            ]

            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Отправляю документы...",
            reply_markup=None
            )
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data in ["Yes", "No"])
    def callback_send_docs(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
        if call.data == "Yes":
            if data["sobstvenik"] == "Yes" and data["ev"] == "Yes":
                documents = [
                {"path": data["fio"]+"\\Документы\\" + "1. Обложка дела.docx", "name": "Обложка дела"},
                {"path": data["fio"]+"\\Документы\\"+ "3c Заявление в Страховую ФЛ представитель с эвакуатором.docx", "name": "Заявление в страховую"}
                ]
            elif data["sobstvenik"] == "Yes" and data["ev"] == "No":
                documents = [
                {"path": data["fio"]+"\\Документы\\" + "1. Обложка дела.docx", "name": "Обложка дела"},
                {"path": data["fio"]+"\\Документы\\"+ "3d Заявление в Страховую ФЛ представитель без эвакуатора.docx", "name": "Заявление в страховую"}
                ]
            elif data["sobstvenik"] == "No" and data["ev"] == "Yes":
                documents = [
                {"path": data["fio"]+"\\Документы\\" + "1. Обложка дела.docx", "name": "Обложка дела"},
                {"path": data["fio"]+"\\Документы\\"+ "3a Заявление в Страховую ФЛ собственник с эвакуатором.docx", "name": "Заявление в страховую"}
                ]
            elif data["sobstvenik"] == "No" and data["ev"] == "No":
                documents = [
                {"path": data["fio"]+"\\Документы\\" + "1. Обложка дела.docx", "name": "Обложка дела"},
                {"path": data["fio"]+"\\Документы\\"+ "3b Заявление в Страховую ФЛ собственник без эвакуатора.docx", "name": "Заявление в страховую"}
                ]
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Отправляю документы...",
            reply_markup=None
            )
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data =="btn_dtp_back")
    def callback_NO_back(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        clear_chat_history_optimized(call.message, 6)
        callback_client_details2_handler(call.message, data['client_id'])

    @bot.callback_query_handler(func=lambda call: call.data in ["YesNOOSAGO", "NoNOOSAGO"])
    def callback_send_docs4(call):

        user_id = call.message.from_user.id 
        data = user_temp_data[user_id]
         

        if call.data == "YesNOOSAGO":
            documents = [
            {"path": data["fio"]+"\\Документы\\"+ "Деликт 3. Заявление о выдаче копии справки участников ДТП.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\Документы\\" + "Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx", "name": "Юридический договор"},
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data in ["YesPr", "NoPr"])
    def callback_send_docs_pret(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "YesPr":
            if data['vibor'] == 'vibor1':
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"6. Претензия в страховую Выплата без согласования.docx", "name": "Обложка дела"},
                ]
            elif data['viborRem'] == "viborRem1":
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx", "name": "Обложка дела"},
                ]
            elif data['viborRem'] == "viborRem3":
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx", "name": "Обложка дела"},
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data in ["dopOsmYes", "dopOsmNo"])
    def callback_send_docs_pret(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "dopOsmYes":
            if data['sobstvenik'] == 'No':
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля.docx", "name": "Обложка дела"},
                ]
            else:
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx", "name": "Обложка дела"},
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["ZaprInsYes", "ZaprInsNo"])
    def callback_send_docs_o(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         

        if call.data == "ZaprInsYes":
            if data['sobstvenik'] == 'No':
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта.docx", "name": "Обложка дела"},
                ]
            else:
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx", "name": "Обложка дела"},
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

        user_temp_data[user_id] = data
         

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Продолжить", callback_data="next")
        btn2 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        keyboard.add(btn2)
        bot.send_message(call.message.chat.id, "Анализируем ответ от страховой\nПродолжить или вернуться в главное меню?",reply_markup=keyboard)


    @bot.callback_query_handler(func=lambda call: call.data in ["YesO", "NoO"])
    def callback_send_docs_o2(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        if call.data == "YesO":
            if data["vibor"] == "vibor1":
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"7. Заявление фин. омбудсмену при выплате без согласования.docx", "name": "Обложка дела"},
                ]
            elif data["viborRem"] == "viborRem1":
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"8. Заявление фин. омбуцмену СТО отказала.docx", "name": "Обложка дела"},
                ]
            elif data["viborRem"] == "viborRem3":
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"7. Заявление фин. омбудсмену СТО свыше 50 км.docx", "name": "Обложка дела"},
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["vibor2STOYes", "vibor2STONo"])
    def callback_STOZayav(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "vibor2STOYes":
            if data['sobstvenik'] == 'No':
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"6. Заявление в СТО.docx", "name": "Обложка дела"},
                ]
            else:
                documents = [
                {"path": data["fio"]+"\\Документы\\"+"6. Заявление в СТО представитель.docx", "name": "Обложка дела"},
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard) 
    @bot.callback_query_handler(func=lambda call: call.data in ["YesIsk", "NoIsk"])
    def callback_send_docs_o3(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "YesIsk":
            documents = [
            {"path": data["fio"]+"\\Документы\\"+"Деликт 5.  Исковое заявление.docx", "name": "Обложка дела"},
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
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_dtp_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["dopOsm", "dopNotY", "dopNotN"])
    def callback_continue_dop_osm(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]

        if call.data == "dopNotY":
            data['sobstvenik'] = 'Yes'
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость услуг нотариуса",
                reply_markup=None
            )
            user_message_id = message.message_id  
            bot.register_next_step_handler(call.message, coin_not, data, user_message_id)
        elif data['sobstvenik'] == 'No' and call.data != "dopNotN":

            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"dopNotY")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"dopNotN")
            keyboard.add(btn1)
            keyboard.add(btn2)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Клиент подготовил нотариальную доверенность?",
                reply_markup=keyboard
            )
        else:
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data=f"dopYes")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"dopNo")

            keyboard.add(btn1)
            keyboard.add(btn2)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Необходим дополнительный осмотр автомобиля?",
                reply_markup=keyboard
            ) 
        
         
    @bot.callback_query_handler(func=lambda call: call.data in ["dopNotY", "dopNotN"])
    def callback_continue_dop_osm(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        

        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data=f"dopYes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data=f"dopNo")

        keyboard.add(btn1)
        keyboard.add(btn2)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходим дополнительный осмотр автомобиля?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data =="dopYes")
    def callback_dop_osm_vibor(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]

        data.update({'dop_osm': "Yes"})
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Подготовьте документы:\n1. Акт осмотра автомобиля",
            reply_markup=None
        )
        user_message_id = message.message_id  
        message = bot.send_message(
            chat_id=call.message.chat.id,
            text="Введите входящий номер в страховую",
            reply_markup=None
        )
        user_message_id1 = message.message_id  
        bot.register_next_step_handler(message, Nv_ins, data, user_message_id, user_message_id1)
         
    @bot.callback_query_handler(func=lambda call: call.data in ["continuefilling", "dopNo"])
    def callback_continue_filling(call):
        """Продолжение заполнения данных клиента"""
        
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        if call.data == "dopNo":
                    data.update({'dop_osm': "No"})
        user_temp_data[user_id] = data
        
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="YES")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="NO")
        btn3 = types.InlineKeyboardButton("Нет ОСАГО у виновника", callback_data="NOOSAGO")
        btn4 = types.InlineKeyboardButton("Назад", callback_data="dopOsm")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Имеется ли ответ страховой компании в течении 20 дней?",
            reply_markup=keyboard
        ) 
        

    @bot.callback_query_handler(func=lambda call: call.data in ["YES", "NO", "NOOSAGO"])
    def callback_have_insurance(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
         
        if call.data == "YES":
            data.update({"answer_ins": "YES"})
        elif call.data == "NO":
            data.update({"answer_ins": "NO"})

        else: 
            data.update({"answer_ins": "NOOSAGO"})
        if data["answer_ins"] != "NOOSAGO":
            db = DatabaseManager()
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            
            # Обновляем JSON данные и answer_ins
            cursor.execute(
                "UPDATE clients SET data_json = ?, answer_ins = ? WHERE client_id = ?",
                (json.dumps(data, ensure_ascii=False), data.get('answer_ins', ''), data['client_id'])
            )
            
            conn.commit()
            conn.close()

            user_id = call.message.from_user.id
            user_temp_data[user_id] = data
             

            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Да", callback_data="docsInsYes")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="docsInsNo")
            btn3 = types.InlineKeyboardButton("Назад", callback_data="continuefilling")
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходимо заявление на выдачу документов из страховой?",
            reply_markup=keyboard)

        else:
            db = DatabaseManager()
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            
            # Обновляем JSON данные и answer_ins
            cursor.execute(
                "UPDATE clients SET data_json = ?, answer_ins = ? WHERE client_id = ?",
                (json.dumps(data, ensure_ascii=False), data.get('answer_ins', ''), data['client_id'])
            )
            
            conn.commit()
            conn.close()

            user_id = call.message.from_user.id
            user_temp_data[user_id] = data
             

            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Деликт (у виновника нет ОСАГО)", callback_data="delict_NOOSAGO")
            btn2 = types.InlineKeyboardButton("Назад", callback_data="continuefilling")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите из предложенных вариантов",
            reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "delict_NOOSAGO")
    def callback_delict_NOOSAGO(call):
            
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        if data["sobstvenik"] == 'Yes':
            data.update({"analis_ins": "Yes"})
            data.update({"pret_sto": "No"})
            data.update({"pret": "No"})
            data.update({"ombuc": "req"})
            data.update({"status": 'Отправлен запрос в страховую'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ ФИОк }}", "{{ Телефон }}"],
                                [str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                    str(data["fio_k"]), str(data["number"])],
                                    "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                    data["fio"]+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx")
            replace_words_in_word(["{{ Страховая }}","{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Город }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                    str(data["city"]), str(data["number"]), str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                    data["fio"]+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx")
            
            user_id = call.message.from_user.id
            user_temp_data[user_id] = data
             
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data="YesNOOSAGO")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="NoNOOSAGO")
            keyboard.add(btn1, btn2)
            bot.send_message(call.message.chat.id, text="Данные сохранены, отправить вам документы?", reply_markup=keyboard)
        else:
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Деликт (у виновника нет ОСАГО)\nПодготовьте документы:\n1.Доверенность",
                reply_markup=None)
            
            user_message_id1 = message.message_id
            message=bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Введите номер доверенности",
                    reply_markup=None
                )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, N_dov_not, data, user_message_id, user_message_id1)

    @bot.callback_query_handler(func=lambda call: call.data in ["docsInsYes", "docsInsNo"])
    def callback_Zabr_insurance(call):
         
        user_id = call.message.from_user.id

        data = user_temp_data[user_id]
         

        if call.data == "docsInsYes":
            data.update({"status": 'Отправлен запрос в страховую'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            if data['sobstvenik'] == 'No':
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}","{{ ФИОк }}", "{{ Телефон }}"],
                            [str(data['insurance']), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                            str(data["number_pasport"]), str(data["where_pasport"]),
                            str(data["when_pasport"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), 
                            str(data["marks_culp"]), str(data["number_auto_culp"]), str(data["fio_k"]), str(data["number"])],
                            "Шаблоны\\1. ДТП\\1. На ремонт\\5. Запрос в страховую о выдаче акта и расчета\\5. Запрос в страховую о выдаче акта и расчёта.docx",
                                data["fio"]+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта.docx")
            else:
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ NДоверенности }}","{{ Дата_доверенности }}", "{{ Представитель }}","{{ Телефон_представителя }}",
                            "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}"],
                            [str(data['insurance']), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                            str(data["number_pasport"]), str(data["where_pasport"]),
                            str(data["when_pasport"]),str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]),str(data["number_not"]),
                            str(data["date_dtp"]), str(data["time_dtp"]), 
                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), 
                            str(data["marks_culp"]), str(data["number_auto_culp"]), str(data["number"])],
                            "Шаблоны\\1. ДТП\\1. На ремонт\\5. Запрос в страховую о выдаче акта и расчета\\5. Запрос в страховую о выдаче акта и расчёта представитель.docx",
                                data["fio"]+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx")

            user_temp_data[user_id] = data
            time.sleep(1)

            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data=f"ZaprInsYes")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"ZaprInsNo")
            keyboard.add(btn1, btn2)
            bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Документ сформирован, отправить вам его?",
            reply_markup=keyboard
            ) 
        elif call.data == "docsInsNo":
            user_temp_data[user_id] = data 
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Продолжить", callback_data="next")
            btn2 = types.InlineKeyboardButton("Главное меню", callback_data="btn_main_menu")
            btn3 = types.InlineKeyboardButton("Назад", callback_data="NO")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Анализируем ответ от страховой\nПродолжить или вернуться в главное меню?",
            reply_markup=keyboard
            ) 

    @bot.callback_query_handler(func=lambda call: call.data == "next")
    def callback_vibor_insurance(call):
        clear_chat_history_optimized(call.message, 6)
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        data.update({"analis_ins": "Yes"})
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        
        
        if data["answer_ins"]=="YES":
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("1", callback_data=f"vibor1")
            btn2 = types.InlineKeyboardButton("2", callback_data=f"vibor2")

            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.send_message(
            chat_id=call.message.chat.id,
            text="""Выберите подходящий вариант:
1. Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось
2. Направление на ремонт.
            """,
            reply_markup=keyboard
            ) 
        elif data["answer_ins"]=="NO":
            data.update({"vibor": "vibor1"})
            message = bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось\nПодготовьте документы:\n1. Нотариальная доверенность\n2. Ответ страховой\n3. Экспертное заключение\n4. Выплатное дело\n5. Платежное поручение",
                    reply_markup=None)
            user_message_id1 = message.message_id
            if data["Nv_ins"] != None and data["Nv_ins"] != '':
                message = bot.send_message(call.message.chat.id, text="Введите дату экспертного заключения")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id1)
            else:
                message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, Nv_ins, data, user_message_id, user_message_id1)
        elif data["answer_ins"]=="viplata":
            keyboard = types.InlineKeyboardMarkup()
            btn2 = types.InlineKeyboardButton("Направление на ремонт", callback_data=f"vibor2")
            keyboard.add(btn2)
            bot.send_message(
            chat_id=call.message.chat.id,
            text="Изменен способ возмещения",
            reply_markup=keyboard
            ) 
    @bot.callback_query_handler(func=lambda call: call.data == "nextPr")
    def callback_pret(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        

        keyboard = types.InlineKeyboardMarkup()

        if data["viborRem"] == "viborRem1" or data["viborRem"] == "viborRem3":
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"viborRem2")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"NOpr")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="СТО была заменена?",
                reply_markup=keyboard
                )
        else:
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"vibor2")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"NOpr")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Удовлетворена ли претензия?",
                reply_markup=keyboard
                )
    @bot.callback_query_handler(func=lambda call: call.data == "nextPrSto")
    def callback_pret_sto(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         

        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Нотариальную доверенность\n2. Отказ СТО",
                reply_markup=None
                )
        user_message_id1 = message.message_id
        message = bot.send_message(
            call.message.chat.id, 
            "Введите дату отказа СТО", 
            reply_markup=None
        )
        user_message_id = message.message_id

        bot.register_next_step_handler(message, data_otkaz_sto, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data == "nextO")
    def callback_ombuc(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        

        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Удовлетворил", callback_data=f"YESO")
        btn2 = types.InlineKeyboardButton("Не удовлетворил", callback_data=f"NOO")
        btn3 = types.InlineKeyboardButton("Частично удовлетворил", callback_data=f"NOO")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Омбуцмен удовлетворил?",
                reply_markup=keyboard
                )
    @bot.callback_query_handler(func=lambda call: call.data == "YESO")
    def callback_ombuc_viboryes(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          

        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Деликт", callback_data="Ura")
        btn2 = types.InlineKeyboardButton("Ура", callback_data="Ura")
        keyboard.add(btn1)
        keyboard.add(btn2)

        message=bot.send_message(
            call.message.chat.id, 
            "Выберите подходящий вариант", 
            reply_markup=keyboard
        )
        callback_client_details2_handler(call.message, data['client_id'])
    @bot.callback_query_handler(func=lambda call: call.data == "NOO")
    def callback_ombuc_exp(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="NOO_Yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="NOO_No")
        keyboard.add(btn1)
        keyboard.add(btn2)
        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Заказать независимую экспертизу?",
                reply_markup=keyboard
                )

    @bot.callback_query_handler(func=lambda call: call.data in ["NOO_Yes", "NOO_No"])
    def callback_ombuc_viboryes(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        if call.data ==  "NOO_Yes":
            data['ombuc'] = 'Yes'
            data['status'] = 'Отправлен запрос о независимой экспертизе'
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            #Обложка
            create_fio_data_file(data)
            bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"Запрос о независимой экспертизе на авто по делу {data['client_id']}",
                    reply_markup=None
                    ) 
            time.sleep(1)
            clear_chat_history_optimized(call.message, 1)
            callback_client_details2_handler(call.message, data['client_id'])
        else:
            data['ombuc'] = 'No'     
            message = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Подготовьте документы:\n1. Принятое заявление омбуцмену\n2. Ответ омбуцмена\n3. Независимую техническую экспертизу",
                    reply_markup=None
                    )
            user_message_id1 = message.message_id
            message = bot.send_message(
                call.message.chat.id, 
                "Введите серию ВУ виновника", 
                reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_vu_culp, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data == "Ura")
    def callback_ura(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          

        data.update({"Done": "Yes"})
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE clients SET data_json = ?, Done = ? WHERE client_id = ?",
            (json.dumps(data, ensure_ascii=False), data.get('Done', ''), data['client_id'])
        )
        
        conn.commit()
        conn.close()
        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="УРА",
                reply_markup=None
                )

        callback_client_details2_handler(call.message, data['client_id'])
    @bot.callback_query_handler(func=lambda call: call.data =="YESpr")
    def callback_pret_viboryes(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          

        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Деликт", callback_data=f"Delikt")
        btn2 = types.InlineKeyboardButton("Ура", callback_data=f"Ura")
        keyboard.add(btn1)
        keyboard.add(btn2)

        message=bot.send_message(
            call.message.chat.id, 
            "Выберите подходящий вариант", 
            reply_markup=keyboard
        )
        callback_client_details2_handler(call.message, data['client_id'])
    @bot.callback_query_handler(func=lambda call: call.data=="NOpr")
    def callback_pret_viboryes(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        user_message_id = []
         
        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Принятая претензия\n2. Ответ на претензию",
                reply_markup=None
                )
        user_message_id1 = message.message_id
        message = bot.send_message(
            call.message.chat.id, 
            "Введите дату принятия претензии в формате ДД.ММ.ГГГГ", 
            reply_markup=None
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_pret_prin, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data == "vibor1")
    def callback_vibor1(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        user_message_id =[] 
        data.update({"vibor": str(call.data)})

        message =bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Нотариальная доверенность\n2. Ответ страховой\n3. Экспертное заключение\n4. Выплатное дело\n5. Платежное поручение",
                reply_markup=None)
        user_message_id1 = message.message_id
        if data["Nv_ins"] != None and data["Nv_ins"] != '':
            message = bot.send_message(call.message.chat.id, text="Введите дату экспертного заключения")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id1)
        else:
            message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, Nv_ins, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data=="vibor2")
    def callback_vibor2(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        data.update({"pret_sto": ''})
        data.update({"pret": ''})
         
          
        data.update({"vibor": str(call.data)})
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
         

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("1", callback_data=f"viborRem1")
        btn2 = types.InlineKeyboardButton("2", callback_data=f"viborRem2")
        btn3 = types.InlineKeyboardButton("3", callback_data=f"viborRem3")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="""
1. Страховая компания выдала направление на ремонт, СТО отказала
2. Страховая выдала направление и ремонт произведен
3. Страховая компания выдала направление на ремонт, СТО дальше 50 км""",
                reply_markup=keyboard
                )
    @bot.callback_query_handler(func=lambda call: call.data == "viborRem1")
    def callback_viborRem1(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        user_message_id = []  
        data.update({"viborRem": str(call.data)})

        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Акт приема-передачи автомобиля\n2. Ответ страховой\n3. Экспертное заключение\n4. Направление на ремонт",
                reply_markup=None
                )
        user_message_id1 = message.message_id
        if (data["Nv_ins"] == None) or (data["Nv_ins"] == ''):
            message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, Nv_ins, data, user_message_id, user_message_id1)
        else:
            message = bot.send_message(call.message.chat.id, text="Введите название СТО")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, name_sto, data, user_message_id, user_message_id1)


    @bot.callback_query_handler(func=lambda call: call.data=="viborRem2")
    def callback_viborRem2(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        data.update({"viborRem": str(call.data)})
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
         

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Ремонт устраивает заказчика", callback_data="Ura")
        btn2 = types.InlineKeyboardButton("Ремонт не устраивает заказчика", callback_data="Ura")
        btn3 = types.InlineKeyboardButton("Сроки/условия ремонта нарушены", callback_data="Ura")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        message=bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите один из вариантов",
                reply_markup=keyboard
                )

    @bot.callback_query_handler(func=lambda call: call.data =="viborRem3")
    def callback_viborRem3(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        user_message_id = []  
        data.update({"viborRem": str(call.data)})

        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Нотариальная доверенность\n2. Ответ страховой\n3. Экспертное заключение\4. Направление на ремонт",
                reply_markup=None
                )
        user_message_id1 = message.message_id
        message = bot.send_message(call.message.chat.id, text="Введите название СТО")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, name_sto, data, user_message_id, user_message_id1)

    @bot.callback_query_handler(func=lambda call: call.data=="IskNOOSAGO")
    def callback_viborRem1(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        user_message_id = []
 

        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Выплатное дело\n2. Платежное поручение\n3. Экспертиза",
                reply_markup=None
                )
        user_message_id1 = message.message_id

        message = bot.send_message(call.message.chat.id, text="Введите название СТО")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, name_sto, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data=="vibor1yes")
    def callback_vibor1yes(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        data.update({"vibor1": "Yes"}) 
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Деликт", callback_data="vibor1yesDelikt")
        btn2 = types.InlineKeyboardButton("Ура", callback_data="vibor1yesUra")
        keyboard.add(btn1)
        keyboard.add(btn2)
        message=bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите подходящий вариант",
                reply_markup=keyboard
                )
        callback_client_details2_handler(call.message, data['client_id'])
    @bot.callback_query_handler(func=lambda call: call.data=="vibor1no")
    def callback_vibor1no(call): 
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        user_message_id =[]
          
        data.update({"vibor1": "No"}) 
        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="""Подготовьте документы:
                1. Нотариальная доверенность
                2. Ответ страховой
                3. Экспертное заключение""",
                reply_markup=None
                )
        user_message_id1 = message.message_id
        message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, Nv_ins, data, user_message_id, user_message_id1)

def FIO(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО клиента в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, FIO, data, user_message_id, user_message_id)
    else:
        words = message.text.split()
        for word in words:
            if not word[0].isupper():  # Проверяем, что первая буква заглавная
                message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО клиента в формате Иванов Иван Иванович")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, FIO, data, user_message_id, user_message_id)
                return
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
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 4 цифры!\nВведите серию паспорта, например, 1234.".format(message.from_user))
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
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите номер паспорта, например, 123456".format(message.from_user))
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
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выдачи паспорта в формате ДД.ММ.ГГГГ.".format(message.from_user))
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
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите почтовый индекс, например, 123456".format(message.from_user))
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
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона клиента в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number, data, user_message_id)
    else:
        data.update({"number": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату рождения клиента в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth, data, user_message_id)

def date_of_birth(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth": message.text})
        message = bot.send_message(message.chat.id, text="Введите город рождения клиента".format(message.from_user))
        time.sleep(0.1)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, city_birth, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения клиента в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth, data, user_message_id)

def city_birth(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"city_birth": message.text})

    message = bot.send_message(message.chat.id, text="Введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_dtp, data, user_message_id)


def fio_sobs(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО собственника в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_sobs, data, user_message_id)
    else:
        words = message.text.split()
        for word in words:
            if not word[0].isupper():  # Проверяем, что первая буква заглавная
                message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО собственника в формате Иванов Иван Иванович")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, fio_sobs, data, user_message_id)
                return
        data.update({"fio_sobs": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату рождения собственника в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth_sobs, data, user_message_id)

def date_of_birth_sobs(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth_sobs": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_dtp, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения собственника в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth_sobs, data, user_message_id)

def date_dtp(message, data,user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        input_date = datetime.strptime(message.text, "%d.%m.%Y")

        current_date = datetime.now()
        three_years_ago = current_date - timedelta(days=3*365 + 1)

        if input_date > current_date:
            message = bot.send_message(message.chat.id, "Дата ДТП не может быть в будущем!\nВведите корректную дату ДТП")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_dtp, data, user_message_id)
            return
        if input_date < three_years_ago:
            message = bot.send_message(message.chat.id, "Прошло более трех лет!\nВведите корректную дату ДТП")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_dtp, data, user_message_id)
            return

        data.update({"date_dtp": message.text})
        message = bot.send_message(message.chat.id, text="Введите время ДТП в формате ЧЧ:ММ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_dtp, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_dtp, data, user_message_id)

def time_dtp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text) != 5 or message.text.count(':') != 1:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
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
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_dtp, data, user_message_id)

def address_dtp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)

    data.update({"address_dtp": message.text})
    user_id = message.from_user.id
    user_temp_data[user_id] = data
     
    keyboard = types.InlineKeyboardMarkup()

    btn1 = types.InlineKeyboardButton("ГИБДД", callback_data="gibdd")
    btn2 = types.InlineKeyboardButton("Аварком", callback_data="avarkom")
    btn3 = types.InlineKeyboardButton("Евро-протокол", callback_data="evro")
    
    keyboard.add(btn1)
    keyboard.add(btn2)
    keyboard.add(btn3)

    bot.send_message(
        message.chat.id, 
        "Кого вызывали на фиксацию дтп", 
        reply_markup=keyboard
    )


def marks(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    data.update({"marks": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер авто клиента".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_auto, data, user_message_id)
def number_auto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    car_number = message.text.replace(" ", "").upper()  # Приводим к верхнему регистру
    pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
    
    # Проверяем, что исходный текст не содержит строчных букв
    original_text = message.text.replace(" ", "")
    has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
    
    if not has_lowercase and re.match(pattern, car_number) and len(car_number) in [8, 9]:
        data.update({"car_number": car_number})
        message = bot.send_message(message.chat.id, "Введите год выпуска авто клиента, например, 2025")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, year_auto, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат!\nВведите номер авто клиента\n"
            "Пример: А123БВ77 или А123БВ777\n"
            "Все буквы должны быть заглавными!"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_auto, data, user_message_id)

def year_auto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите корректный год выпуска авто.\nНапример: 2025".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, year_auto, data, user_message_id)
    else:
        data.update({"year_auto": int(message.text.replace(" ", ""))})
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
        user_message_id = [] 
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="STS")
        btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="PTS")
        btn3 = types.InlineKeyboardButton("Договор купли-продажи ТС", callback_data="DKP")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

        bot.send_message(
            message.chat.id, 
            "Выберите документ о регистрации ТС", 
            reply_markup=keyboard
        )



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
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"number_docs": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_docs, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат!\nВведите номер документа о регистрации ТС, он должен состоять только из цифр"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_docs, data, user_message_id) 

def data_docs(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_docs": message.text})
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
        
        # Создаем клавиатуру с пагинацией (первая страница)
        keyboard = create_insurance_keyboard(page=0)
        
        bot.send_message(
            message.chat.id, 
            text="Выберите страховую компанию".format(message.from_user), 
            reply_markup=keyboard
        )
        
    except ValueError:
        message = bot.send_message(
            message.chat.id, 
            text="Неправильный формат ввода!\nВведите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ".format(message.from_user)
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_docs, data, user_message_id)

def other_insurance(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"insurance": message.text})
    message = bot.send_message(message.chat.id, text="Введите серию страхового полиса".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
def seria_insurance(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"seria_insurance": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер страхового полиса".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_insurance, data, user_message_id)

def number_insurance(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"number_insurance": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату страхового полиса в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_insurance, data,user_message_id)
def date_insurance(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_insurance": message.text})
        message = bot.send_message(message.chat.id, text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, fio_culp, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату страхового полиса в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_insurance, data, user_message_id)
def fio_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
    else:
        words = message.text.split()
        for word in words:
            if not word[0].isupper():  # Проверяем, что первая буква заглавная
                message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, fio_culp, data, user_message_id)
                return
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
        if data['sobstvenik'] == 'No':
            message = bot.send_message(message.chat.id, "Введите название банка получателя клиента")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank, data, user_message_id)
        else:
            message = bot.send_message(message.chat.id, "Введите стоимость услуг нотариуса в рублях, число")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_not, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат!\nВведите номер авто виновника ДТП\n"
            "Пример: А123БВ77 или А123БВ777\n"
            "Все буквы должны быть заглавными!"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_auto_culp, data, user_message_id)

def bank(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"bank": message.text})
    message = bot.send_message(message.chat.id, text="Введите счет получателя".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, bank_account, data, user_message_id)

def bank_account(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"bank_account": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите корреспондентский счет банка"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, счет должен состоять только из цифр!\nВведите счет получателя"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, bank_account, data, user_message_id) 
def bank_account_corr(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"bank_account_corr": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите БИК банка"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, BIK, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, счет должен состоять только из цифр!\nВведите корреспондентский счет банка"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
def BIK(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"BIK": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите ИНН банка"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, INN, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, БИК должен состоять только из цифр!\nВведите БИК банка"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, BIK, data, user_message_id)
def INN(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    user_message_id = []
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"INN": message.text})
        data.update({"answer_ins": ''})
        data.update({"analis_ins": ''})
        data.update({"vibor": ''})
        data.update({"vibor1yes": ''})
        data.update({"Nv_ins": ''})
        data.update({"date_coin_ins": ''})
        data.update({"Na_ins": ''})
        data.update({"date_Na_ins": ''})
        data.update({"date_exp": ''})
        data.update({"org_exp": ''})
        data.update({"coin_exp": ''})
        data.update({"date_sto": ''})
        data.update({"time_sto": ''})
        data.update({"address_sto": ''})
        data.update({"coin_exp_izn": ''})
        data.update({"coin_osago": ''})
        data.update({"date_ins": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"pret": ''})
        data.update({"ombuc": ''})
        data.update({"data_pret_prin": ''})
        data.update({"data_pret_otv": ''})
        data.update({"N_pret_prin": ''})
        data.update({"date_ombuc": ''})
        data.update({"date_ins_pod": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"status": 'Отправлен запрос в страховую'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
            data['client_id'] = "70001"
        #Обложка
        create_fio_data_file(data)
        replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                "{{ Страховая }}", "{{ винФИО }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела.docx",
                                    data["fio"]+"\\Документы\\"+"1. Обложка дела.docx")

        #Заявление в страховую
        if data["sobstvenik"] == "Yes" and data["ev"] == "Yes":
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3c Заявление в Страховую ФЛ представитель с эвакуатором.docx",
                                    data["fio"]+"\\Документы\\"+"3c Заявление в Страховую ФЛ представитель с эвакуатором.docx")
        elif data["sobstvenik"] == "Yes" and data["ev"] == "No":
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3d Заявление в Страховую ФЛ представитель без эвакуатора.docx",
                                    data["fio"]+"\\Документы\\"+"3d Заявление в Страховую ФЛ представитель без эвакуатора.docx")
        elif data["sobstvenik"] == "No" and data["ev"] == "Yes":
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]),  str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3a Заявление в Страховую ФЛ собственник с эвакуатором.docx",
                                    data["fio"]+"\\Документы\\"+"3a Заявление в Страховую ФЛ собственник с эвакуатором.docx")
        else:
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]),  str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3b Заявление в Страховую ФЛ собственник без эвакуатора.docx",
                                    data["fio"]+"\\Документы\\"+"3b Заявление в Страховую ФЛ собственник без эвакуатора.docx")
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="Yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="No")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)        
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН банка."
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, INN, data, user_message_id)   


def date_coin_ins(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_coin_ins": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, Na_ins, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выплаты страховой в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_coin_ins, data, user_message_id)

def Nv_ins(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    data.update({"Nv_ins": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, Na_ins, data, user_message_id)
def Na_ins(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"Na_ins": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ.".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_Na_ins, data, user_message_id)
def date_Na_ins(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_Na_ins": message.text})
        if data["viborRem"] == "viborRem3":
            
            if data['date_exp'] !='' and data['date_exp'] != None:
                data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
                data.update({"analis_ins": "Yes"})
                data.update({"pret_sto": "Yes"})
                data.update({"status": 'Отправлена претензия в страховую'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}",
                                            "{{ СТО }}", "{{ Индекс_СТО }}","{{ Адрес_СТО }}","{{ Город_СТО }}","{{ Номер_направления_на_ремонт }}","{{ Дата_направления }}",
                                            "{{ Марка_модель }}", "{{ Nавто_клиента }}","{{ Дата_претензии }}"],
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["date_napr_sto"]), str(data["N_sto"]), str(data["name_sto"]),str(data["index_sto"]),str(data["address_sto"]),
                                                str(data["city_sto"]), str(data["N_sto"]), str(data["date_napr_sto"]), str(data["marks"]),str(data["car_number"]), str(data["date_pret"])],
                                                "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\6. Претензия в страховую  СТО свыше 50 км.docx",
                                                data["fio"]+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx")
                user_id = message.from_user.id
                user_temp_data[user_id] = data
                
                keyboard = types.InlineKeyboardMarkup()

                btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
                btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
                keyboard.add(btn1, btn2)
                bot.send_message(message.chat.id, "Данные сохранены, отправить вам документы?", reply_markup=keyboard)
            else:
                message = bot.send_message(message.chat.id, text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
                user_message_id = message.message_id
                bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id)
        elif data["viborRem"] == "viborRem1":
            message = bot.send_message(message.chat.id, text="Введите название СТО".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, name_sto, data, user_message_id, user_message_id)
        elif data["dop_osm"] == "Yes":
            message = bot.send_message(message.chat.id, text="Введите адрес своего СТО".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_sto_main, data, user_message_id)
        else:
            message = bot.send_message(message.chat.id, text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ.".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_Na_ins, data, user_message_id)
def date_exp(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_exp": message.text})
        message = bot.send_message(message.chat.id, text="Введите организацию, сделавшую экспертизу".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, org_exp, data, user_message_id)

    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id)

def org_exp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"org_exp": message.text})
    message = bot.send_message(message.chat.id, text="Введите цену по экспертизе без учета износа".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, coin_exp, data, user_message_id)
def coin_exp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_exp": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите цену по экспертизе с учетом износа"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp_izn, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену по экспертизе без учета износа"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp, data, user_message_id)
def coin_exp_izn(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_exp_izn": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите сумму выплаты по ОСАГО"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_osago, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену по экспертизе с учетом износа"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp_izn, data, user_message_id)
def coin_osago(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_osago": message.text})
        if data["answer_ins"] =="NOOSAGO":
            message = bot.send_message(
            message.chat.id,
            text="Введите серию ВУ виновника ДТП"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_vu_culp, data, user_message_id, user_message_id)
        elif data["viborRem"] == "viborRem1":
            message = bot.send_message(
            message.chat.id,
            text="Введите дату передачи авто на СТО в формате ДД.ММ.ГГГГ"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_sto, data, user_message_id)
        else:
            if data['sobstvenik'] == 'No':
                message = bot.send_message(
                    message.chat.id,
                    text="Введите стоимость услуг нотариуса"
                )
                user_message_id = message.message_id
                bot.register_next_step_handler(message, coin_not, data, user_message_id)
            else:
                if data["answer_ins"] == "NOOSAGO":
                    data.update({"analis_ins": "Yes"})
                    data.update({"pret_sto": "No"})
                    data.update({"pret": "No"})
                    data.update({"ombuc": "req"})
                    data.update({"status": 'Отправлен запрос в страховую'})
                    try:
                        client_id, updated_data = save_client_to_db_with_id(data)
                        data.update(updated_data)
                    except Exception as e:
                        print(f"Ошибка базы данных: {e}")
                    create_fio_data_file(data)
                    replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                        "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                        "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                        "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ ФИОк }}"],
                                        [str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                            str(data["fio_k"])],
                                            "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                            data["fio"]+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx")
                    replace_words_in_word(["{{ Страховая }}","{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                        "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                        "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                        "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}"],
                                        [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"])],
                                            "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                            data["fio"]+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx")
                    
                    user_id = message.from_user.id
                    user_temp_data[user_id] = data
                    
                    keyboard = types.InlineKeyboardMarkup()

                    btn1 = types.InlineKeyboardButton("Да", callback_data="YesNOOSAGO")
                    btn2 = types.InlineKeyboardButton("Нет", callback_data="NoNOOSAGO")
                    keyboard.add(btn1, btn2)
                    bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?", reply_markup=keyboard)
                else:
                    data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
                    data.update({"analis_ins": "Yes"})
                    data.update({"pret_sto": "Yes"})
                    data.update({"status": 'Отправлена претензия в страховую'})
                    try:
                        client_id, updated_data = save_client_to_db_with_id(data)
                        data.update(updated_data)
                    except Exception as e:
                        print(f"Ошибка базы данных: {e}")
                    create_fio_data_file(data)
                    if data['vibor'] == "vibor1":
                        replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Организация }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}",
                                            "{{ С_учетом_износа }}", "{{ Выплата_ОСАГО }}","{{ Дата_претензии }}"],
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["org_exp"]), str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]),
                                                str(data["coin_osago"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                                "Шаблоны\\1. ДТП\\1. На ремонт\\Выплата без согласования\\6. Претензия в страховую Выплата без согласования.docx",
                                                data["fio"]+"\\Документы\\"+"6. Претензия в страховую Выплата без согласования.docx")
                    elif data['viborRem'] == "viborRem1":
                        replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ Дата_предоставления_ТС }}",
                                            "{{ СТО }}", "{{ Дата_отказа_СТО }}","{{ Дата_претензии }}","{{ Город_СТО }}","{{ Марка_модель }}", "{{ Nавто_клиента }}"], 
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["date_napr_sto"]), str(data["N_sto"]), str(data["date_sto"]),str(data["name_sto"]),
                                                str(data["data_otkaz_sto"]), str(data["date_pret"]), str(data["city"]), str(data["marks"]),str(data["car_number"])],
                                                "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\7. Претензия в страховую СТО отказала.docx",
                                                data["fio"]+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx")
                    elif data['viborRem'] == "viborRem3":
                        replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}",
                                            "{{ СТО }}", "{{ Индекс_СТО }}","{{ Адрес_СТО }}","{{ Город_СТО }}","{{ Номер_направления_на_ремонт }}","{{ Дата_направления }}",
                                            "{{ Марка_модель }}", "{{ Nавто_клиента }}","{{ Дата_претензии }}"],
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["date_napr_sto"]), str(data["N_sto"]), str(data["name_sto"]),str(data["index_sto"]),str(data["address_sto"]),
                                                str(data["city_sto"]), str(data["N_sto"]), str(data["date_napr_sto"]), str(data["marks"]),str(data["car_number"]), str(data["date_pret"])],
                                                "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\6. Претензия в страховую  СТО свыше 50 км.docx",
                                                data["fio"]+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx")
                    
                    user_id = message.from_user.id
                    user_temp_data[user_id] = data
                    
                    keyboard = types.InlineKeyboardMarkup()

                    btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
                    btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
                    keyboard.add(btn1, btn2)
                    bot.send_message(message.chat.id, "Данные сохранены, отправить вам документы?", reply_markup=keyboard)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите сумму выплаты по ОСАГО"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_osago, data, user_message_id)

def data_otkaz_sto(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_otkaz_sto": message.text})
        if data['sobstvenik'] == 'No':
            message = bot.send_message(message.chat.id, text="Введите стоимость услуг нотариуса".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_not, data, user_message_id)
        else:
            data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
            data.update({"analis_ins": "Yes"})
            data.update({"pret_sto": "Yes"})
            data.update({"status": 'Отправлена претензия в страховую'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                    "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                    "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                    "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                    "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ Дата_предоставления_ТС }}",
                                    "{{ СТО }}", "{{ Дата_отказа_СТО }}","{{ Дата_претензии }}","{{ Город_СТО }}","{{ Марка_модель }}", "{{ Nавто_клиента }}"], 
                                    [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                        str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                        str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                        str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                        str(data["date_napr_sto"]), str(data["N_sto"]), str(data["date_sto"]),str(data["name_sto"]),
                                        str(data["data_otkaz_sto"]), str(data["date_pret"]), str(data["city"]), str(data["marks"]),str(data["car_number"])],
                                        "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\7. Претензия в страховую СТО отказала.docx",
                                        data["fio"]+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx")
            user_id = message.from_user.id
            user_temp_data[user_id] = data
            
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
            keyboard.add(btn1, btn2)
            bot.send_message(message.chat.id, "Данные сохранены, отправить вам документы?", reply_markup=keyboard)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату отказа СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_otkaz_sto, data, user_message_id, user_message_id)
def coin_not(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_not": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите номер доверенности"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, N_dov_not, data, user_message_id, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость услуг нотариуса"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_not, data, user_message_id)

def N_dov_not(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    data.update({"N_dov_not": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату доверенности в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, data_dov_not, data, user_message_id)
def data_dov_not(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
         
             
        user_message_id = []
        data.update({"data_dov_not": message.text})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Рогалев Семен Иннокентьевич", callback_data="not_rogalev")
        btn2 = types.InlineKeyboardButton("Другое", callback_data="not_other")
        keyboard.add(btn1)
        keyboard.add(btn2)
        bot.send_message(message.chat.id, text="Выберите ФИО представителя",reply_markup=keyboard)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату доверенности в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_dov_not, data, user_message_id)
def fio_not(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            user_message_id = message.message_id
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО представителя в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_not, data, user_message_id)
    else:
        words = message.text.split()
        for word in words:
            if not word[0].isupper():  # Проверяем, что первая буква заглавная
                message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО представителя в формате Иванов Иван Иванович")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, fio_not, data, user_message_id)
                return
        data.update({"fio_not": message.text})
        if data["answer_ins"] == "NOOSAGO":
            data.update({"analis_ins": "Yes"})
            data.update({"pret_sto": "No"})
            data.update({"pret": "No"})
            data.update({"ombuc": "req"})
            data.update({"status": 'Отправлен запрос в страховую'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ ФИОк }}"],
                                [str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                    str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                    data["fio"]+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx")
            replace_words_in_word(["{{ Страховая }}","{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"])],
                                    "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                    data["fio"]+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx")
            
            user_id = message.from_user.id
            user_temp_data[user_id] = data
             
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data="YesNOOSAGO")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="NoNOOSAGO")
            keyboard.add(btn1, btn2)
            bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?", reply_markup=keyboard)
        else:
            user_id = message.from_user.id
            user_temp_data[user_id] = data
             
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("+79966368941", callback_data="number_rogalev")
            btn2 = types.InlineKeyboardButton("Другое", callback_data="number_not_other")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.send_message(message.chat.id, text="Выберите номер телефона представителя", reply_markup=keyboard)



def number_not(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
        user_message_id = message.message_id
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона представителя в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_not, data, user_message_id)
    else:
         
             
        data.update({"number_not": message.text})
        if data['sobstvenik'] == 'Yes' and data['bank'] == '':
            message = bot.send_message(message.chat.id, text="Введите название банка получателя клиента".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank, data, user_message_id)
        elif data['sobstvenik'] == 'Yes' and data['dop_osm'] == '':
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data=f"dopYes")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"dopNo")

            keyboard.add(btn1)
            keyboard.add(btn2)
            
            bot.send_message(
                chat_id=message.chat.id,
                text="Необходим дополнительный осмотр автомобиля?",
                reply_markup=keyboard
            ) 
        else:
            data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
            data.update({"analis_ins": "Yes"})
            data.update({"pret_sto": "Yes"})
            data.update({"status": 'Отправлена претензия в страховую'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            if data['vibor'] == "vibor1":
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                    "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                    "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                    "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                    "{{ Адрес_ДТП }}", "{{ Организация }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}",
                                    "{{ С_учетом_износа }}", "{{ Выплата_ОСАГО }}","{{ Дата_претензии }}"],
                                    [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                        str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                        str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                        str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                        str(data["org_exp"]), str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]),
                                        str(data["coin_osago"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                        "Шаблоны\\1. ДТП\\1. На ремонт\\Выплата без согласования\\6. Претензия в страховую Выплата без согласования.docx",
                                        data["fio"]+"\\Документы\\"+"6. Претензия в страховую Выплата без согласования.docx")
            elif data['viborRem'] == "viborRem1":
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                    "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                    "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                    "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                    "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ Дата_предоставления_ТС }}",
                                    "{{ СТО }}", "{{ Дата_отказа_СТО }}","{{ Дата_претензии }}","{{ Город_СТО }}","{{ Марка_модель }}", "{{ Nавто_клиента }}"], 
                                    [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                        str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                        str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                        str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                        str(data["date_napr_sto"]), str(data["N_sto"]), str(data["date_sto"]),str(data["name_sto"]),
                                        str(data["data_otkaz_sto"]), str(data["date_pret"]), str(data["city"]), str(data["marks"]),str(data["car_number"])],
                                        "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\7. Претензия в страховую СТО отказала.docx",
                                        data["fio"]+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx")
            elif data['viborRem'] == "viborRem3":
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                    "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                    "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                    "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                    "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}",
                                    "{{ СТО }}", "{{ Индекс_СТО }}","{{ Адрес_СТО }}","{{ Город_СТО }}","{{ Номер_направления_на_ремонт }}","{{ Дата_направления }}",
                                    "{{ Марка_модель }}", "{{ Nавто_клиента }}","{{ Дата_претензии }}"],
                                    [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                        str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                        str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                        str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                        str(data["date_napr_sto"]), str(data["N_sto"]), str(data["name_sto"]),str(data["index_sto"]),str(data["address_sto"]),
                                        str(data["city_sto"]), str(data["N_sto"]), str(data["date_napr_sto"]), str(data["marks"]),str(data["car_number"]), str(data["date_pret"])],
                                        "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\6. Претензия в страховую  СТО свыше 50 км.docx",
                                        data["fio"]+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx")
            
            user_id = message.from_user.id
            user_temp_data[user_id] = data
            
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
            keyboard.add(btn1, btn2)
            bot.send_message(message.chat.id, "Данные сохранены, отправить вам документы?", reply_markup=keyboard)



def time_sto(message, data,user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text) != 5 or message.text.count(':') != 1:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_sto, data, user_message_id)
        return
    try:
 
        datetime.strptime(message.text, "%H:%M")

        data.update({"time_sto": message.text})
        if data["viborRem"]=="viborRem3":
            message = bot.send_message(message.chat.id, "Введите город СТО")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, city_sto, data, user_message_id) 
        else:
            message = bot.send_message(message.chat.id, "Введите адрес СТО")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_sto, data, user_message_id)    
    except ValueError:
        message = bot.send_message(
            message.chat.id, 
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_sto, data, user_message_id)



def data_pret_prin(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_pret_prin": message.text})
        if data["viborRem"]=="viborRem1":
            message = bot.send_message(message.chat.id, text="Введите номер принятой претензии".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, N_pret_prin, data, user_message_id)
        else:
            message = bot.send_message(message.chat.id, text="Введите дату ответа на претензию в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_pret_otv, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату принятия претензии в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_pret_prin, data, user_message_id, user_message_id)
def data_pret_otv(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_pret_otv": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер принятой претензии".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, N_pret_prin, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ответа на претензию в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_pret_otv, data, user_message_id)
def N_pret_prin(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"N_pret_prin": message.text})
    data.update({"pret": "Yes"})
    data.update({"date_ombuc": str(datetime.now().strftime("%d.%m.%Y"))})
    data.update({"status": 'Отправлено заявление фин.омбуд.'})
         
    try:
        client_id, updated_data = save_client_to_db_with_id(data)
        data.update(updated_data)
    except Exception as e:
        print(f"Ошибка базы данных: {e}")
    create_fio_data_file(data)
    if data["vibor"] == "vibor1":
        replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}","{{ Город }}", "{{ ФИО }}", 
                            "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                            "{{ Паспорт_когда }}", "{{ Адрес }}", "{{ Телефон }}","{{ Серия_полиса }}","{{ Номер_полиса }}",
                            "{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                            "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                            "{{ Организация }}", "{{ Nэкспертизы }}","{{ Дата_экспертизы }}", "{{ Без_учета_износа }}",
                            "{{ С_учетом_износа }}", "{{ Дата_претензии }}", "{{ Дата_ответа_на_претензию }}", "{{ Выплата_ОСАГО }}", "{{ ФИОк }}", "{{ Nв_страховую }}"],
                            [str(data["date_ombuc"]), str(data["insurance"]),str(data["city"]), str(data["fio"]), str(data["date_of_birth"]), str(data["city_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["address"]), str(data["number"]), str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_insurance"]), 
                                str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                str(data["date_ins_pod"]), str(data["org_exp"]), str(data["Na_ins"]),str(data["date_exp"]),
                                str(data["coin_exp"]), str(data["coin_exp_izn"]),str(data["date_pret"]),
                                str(data["data_pret_otv"]), str(data["coin_osago"]),str(data["fio_k"]), str(data["Nv_ins"])],
                                "Шаблоны\\1. ДТП\\1. На ремонт\\Выплата без согласования\\7. Заявление фин. омбудсмену при выплате без согласования.docx",
                                data["fio"]+"\\Документы\\"+"7. Заявление фин. омбудсмену при выплате без согласования.docx")
    elif data["viborRem"] == "viborRem1":
            replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}", "{{ ФИО }}", 
                        "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                        "{{ Паспорт_когда }}", "{{ Адрес }}", "{{ Телефон }}","{{ Серия_полиса }}","{{ Номер_полиса }}",
                        "{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                        "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                        "{{ Nв_страховую }}", "{{ Дата_направления_ремонт }}","{{ Номер_направления_СТО }}", "{{ СТО }}",
                        "{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ Дата_предоставления_ТС }}", "{{ Дата_принятия_претензии }}", "{{ Nпринятой_претензии }}",
                        "{{ Дата_претензии }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}","{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}",
                        "{{ ФИОк }}","{{ Организация }}", "{{ Nэкспертизы }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Город }}" ],
                        [str(data["date_ombuc"]), str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["city_birth"]),
                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                            str(data["address"]), str(data["number"]), str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_insurance"]), 
                            str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                            str(data["date_ins_pod"]), str(data["Nv_ins"]), str(data["date_napr_sto"]),str(data["N_sto"]),
                            str(data["name_sto"]), str(data["index_sto"]),str(data["address_sto"]), str(data["date_sto"]),
                            str(data["data_pret_prin"]),str(data["N_pret_prin"]),str(data["date_pret"]),str(data["bank"]),str(data["bank_account"]),
                            str(data["bank_account_corr"]),str(data["BIK"]),str(data["INN"]),str(data["fio_k"]), str(data["org_exp"]),str(data["Na_ins"]),
                            str(data["date_exp"]), str(data["coin_exp"]), str(data["coin_exp_izn"]), str(data["city"])],
                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\8. Заявление фин. омбуцмену СТО отказала.docx",
                            data["fio"]+"\\Документы\\"+"8. Заявление фин. омбуцмену СТО отказала.docx")
    elif data["viborRem"] == "viborRem3":
            replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}", "{{ ФИО }}", 
                        "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                        "{{ Паспорт_когда }}", "{{ Адрес }}", "{{ Телефон }}","{{ Серия_полиса }}","{{ Номер_полиса }}",
                        "{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                        "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                        "{{ Nв_страховую }}", "{{ Дата_направления_ремонт }}","{{ Номер_направления_СТО }}", "{{ СТО }}",
                        "{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ Дата_предоставления_ТС }}", "{{ Дата_принятия_претензии }}", "{{ Nпринятой_претензии }}",
                        "{{ Дата_претензии }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}","{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}",
                        "{{ ФИОк }}","{{ Организация }}", "{{ Nэкспертизы }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}", "{{ С_учетом_износа }}",
                        "{{ Город }}","{{ Город_СТО }}"],
                        [str(data["date_ombuc"]), str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["city_birth"]),
                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                            str(data["address"]), str(data["number"]), str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_insurance"]), 
                            str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                            str(data["date_ins_pod"]), str(data["Nv_ins"]), str(data["date_napr_sto"]),str(data["N_sto"]),
                            str(data["name_sto"]), str(data["index_sto"]),str(data["address_sto"]), str(data["date_sto"]),
                            str(data["data_pret_prin"]),str(data["N_pret_prin"]),str(data["date_pret"]),str(data["bank"]),str(data["bank_account"]),
                            str(data["bank_account_corr"]),str(data["BIK"]),str(data["INN"]),str(data["fio_k"]), str(data["org_exp"]),str(data["Na_ins"]),
                            str(data["date_exp"]), str(data["coin_exp"]), str(data["coin_exp_izn"]), str(data["city"]), str(data["city_sto"])],
                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\7. Заявление фин. омбудсмену СТО свыше 50 км.docx",
                            data["fio"]+"\\Документы\\"+"7. Заявление фин. омбудсмену СТО свыше 50 км.docx")
    
    user_id = message.from_user.id
    user_temp_data[user_id] = data
     
    keyboard = types.InlineKeyboardMarkup()

    btn1 = types.InlineKeyboardButton("Да", callback_data="YesO")
    btn2 = types.InlineKeyboardButton("Нет", callback_data="NoO")
    keyboard.add(btn1, btn2)
    bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)


def seria_vu_culp(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    data.update({"seria_vu_culp": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер ВУ виновника".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_vu_culp, data, user_message_id)
def number_vu_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"number_vu_culp": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату ВУ виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, data_vu_culp, data, user_message_id)
def data_vu_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_vu_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату рождения виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth_culp, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ВУ виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_vu_culp, data, user_message_id)
def date_of_birth_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите почтовый индекс виновника, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index_culp, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth_culp, data, user_message_id)
def index_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите почтовый индекс виновника, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index_culp, data, user_message_id)
    else:
        data.update({"index_culp": int(message.text.replace(" ", ""))})
        message = bot.send_message(message.chat.id, text="Введите адрес виновника".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, address_culp, data, user_message_id)  
def address_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"address_culp": message.text})
    message =bot.send_message(message.chat.id, text="Введите номер телефона виновника ДТП в формате +79XXXXXXXXX".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_culp, data, user_message_id)
def number_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона виновника ДТП в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_culp, data, user_message_id)
    else:
        data.update({"number_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер выплатного дела".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, N_viplat_work, data, user_message_id)
def N_viplat_work(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"N_viplat_work": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату выплатного дела в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_viplat_work, data, user_message_id)
def date_viplat_work(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_viplat_work": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер платежного поручения".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, N_plat_por, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выплатного дела в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_viplat_work, data, user_message_id)
def N_plat_por(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"N_plat_por": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату платежного поручения в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_plat_por, data, user_message_id)
def date_plat_por(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:   
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_plat_por": message.text})

        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("1", callback_data="sud1")
        btn2 = types.InlineKeyboardButton("2", callback_data="sud2")
        btn3 = types.InlineKeyboardButton("3", callback_data="sud3")
        btn4 = types.InlineKeyboardButton("4", callback_data="sud4")
        btn5 = types.InlineKeyboardButton("5", callback_data="sud5")
        btn6 = types.InlineKeyboardButton("6", callback_data="sud6")
        btn7 = types.InlineKeyboardButton("Другое", callback_data="sudOther")
        keyboard.add(btn1, btn2, btn3)
        keyboard.add(btn4, btn5, btn6)
        keyboard.add(btn7)

        bot.send_message(message.chat.id, text="""
1. Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58
2. Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45
3. Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21
4. Томский областной суд, 634003, г. Томск, пер. Макушина, 8
5. Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6
6. Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8""", reply_markup=keyboard)


    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату платежного поручения в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_plat_por, data, user_message_id)
def sud_other(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"sud": message.text})
    message = bot.send_message(message.chat.id, text="Введите стоимость государственной пошлины".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, gos_money, data, user_message_id)
def gos_money(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"gos_money": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату извещения о ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_izvesh_dtp, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, стоимость должна состоять только из цифр в рублях, например: 50000!\nВведите стоимость государственной пошлины"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, gos_money, data, user_message_id)

def date_izvesh_dtp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")   
        data.update({"date_izvesh_dtp": message.text})
        data.update({"ombuc": "req"})
        data.update({"date_isk": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"Done": "Yes"})
        data.update({"status": 'Отправлено исковое заявление'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        replace_words_in_word(["{{ Суд }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Индекс }}",
                            "{{ Адрес }}", "{{ Телефон }}", "{{ Представитель }}","{{ NДоверенности }}","{{ Дата_доверенности }}",
                            "{{ винФИО }}", "{{ ДР_Виновника }}", "{{ Серия_ВУвин }}", 
                            "{{ Номер_ВУвин }}", "{{ Дата_ВУвин }}", "{{ Индекс_Виновника }}", "{{ Адрес_Виновника }}",
                            "{{ Телефон_Виновника }}", "{{ Страховая }}","{{ Разница }}", "{{ Выплата_ОСАГО }}",
                            "{{ Экспертиза }}", "{{ Дата_выплаты }}", "{{ Цена_пошлины }}", "{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}",
                            "{{ Выплата_ОСАГО }}", "{{ Nвыплатного_дела }}","{{ Дата_выплатного_дела }}", "{{ Nплатежного_поручения }}",
                            "{{ Дата_поручения }}","{{ Стоимость_экспертизы }}","{{ NКлиента }}", "{{ Дата_экспертизы }}",
                            "{{ Дата }}","{{ Документ }}","{{ Док_серия }}", "{{ Док_номер }}","{{ Дата_извещения }}", "{{ Дата_искового_заявления }}", "{{ Год }}"],
                            [str(data["sud"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                str(data["where_pasport"]), str(data["when_pasport"]),str(data["index_postal"]), str(data["address"]), str(data["number"]),
                                str(data["fio_not"]), str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_culp"]), str(data["date_of_birth_culp"]),str(data["seria_vu_culp"]), 
                                str(data["number_vu_culp"]), str(data["data_vu_culp"]), str(data["index_culp"]), str(data["address_culp"]), str(data["number_culp"]),
                                str(data["insurance"]), str(float(data["coin_exp"])-float(data["coin_osago"])), str(data["coin_osago"]),str(data["coin_exp_izn"]),
                                str(data["date_coin_ins"]), str(data["gos_money"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]),str(data["marks"]),str(data["car_number"]),str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["coin_osago"]),str(data["N_viplat_work"]),str(data["date_viplat_work"]),str(data["N_plat_por"]),
                                str(data["date_plat_por"]),str(data["coin_exp"]),str(data["client_id"]),str(data["date_exp"]),
                                str(data["date_ins"]),str(data["docs"]),str(data["seria_docs"]),str(data["number_docs"]),
                                str(data["date_izvesh_dtp"]), str(data["date_isk"]), str(data['year'])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 5.  Исковое заявление.docx",
                                data["fio"]+"\\Документы\\"+"Деликт 5.  Исковое заявление.docx")
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="YesIsk")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="NoIsk")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату извещения о ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_izvesh_dtp, data, user_message_id)

def name_sto(message, data, user_message_id, user_message_id1):
    if user_message_id1 == user_message_id:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    data.update({"name_sto": message.text})
    message = bot.send_message(message.chat.id, text="Введите ИНН СТО".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, inn_sto, data, user_message_id)
def inn_sto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"inn_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите индекс СТО, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index_sto, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН СТО"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, inn_sto, data, user_message_id)
def index_sto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите индекс СТО, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index_sto, data, user_message_id)
    else:
        data.update({"index_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите адрес СТО".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, address_sto, data, user_message_id) 
def address_sto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"address_sto": message.text})
    message = bot.send_message(message.chat.id, text="Введите город СТО".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, city_sto, data, user_message_id)
def city_sto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"city_sto": message.text})
    message = bot.send_message(message.chat.id, "Введите номер направления СТО")
    user_message_id = message.message_id
    bot.register_next_step_handler(message, N_sto, data, user_message_id) 
def N_sto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"N_sto": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату направления на СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
def date_napr_sto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_napr_sto": message.text})
        if data["viborRem"]=="viborRem3":
            if data['Nv_ins'] == '' or data['Nv_ins'] == None:
                message = bot.send_message(message.chat.id, text="Введите входящий номер в страховую".format(message.from_user))
                user_message_id = message.message_id
                bot.register_next_step_handler(message, Nv_ins, data, user_message_id, user_message_id)
            elif (data['Nv_ins'] == '' or data['Nv_ins'] == None) and (data['date_exp'] == '' or data['date_exp'] == None):
                data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
                data.update({"analis_ins": "Yes"})
                data.update({"pret_sto": "Yes"})
                data.update({"status": 'Отправлена претензия в страховую'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}",
                                            "{{ СТО }}", "{{ Индекс_СТО }}","{{ Адрес_СТО }}","{{ Город_СТО }}","{{ Номер_направления_на_ремонт }}","{{ Дата_направления }}",
                                            "{{ Марка_модель }}", "{{ Nавто_клиента }}","{{ Дата_претензии }}"],
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["date_napr_sto"]), str(data["N_sto"]), str(data["name_sto"]),str(data["index_sto"]),str(data["address_sto"]),
                                                str(data["city_sto"]), str(data["N_sto"]), str(data["date_napr_sto"]), str(data["marks"]),str(data["car_number"]), str(data["date_pret"])],
                                                "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\6. Претензия в страховую  СТО свыше 50 км.docx",
                                                data["fio"]+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx")
                user_id = message.from_user.id
                user_temp_data[user_id] = data
                
                keyboard = types.InlineKeyboardMarkup()

                btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
                btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
                keyboard.add(btn1, btn2)
                bot.send_message(message.chat.id, "Данные сохранены, отправить вам документы?", reply_markup=keyboard)
            else:
                message = bot.send_message(message.chat.id, text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
                user_message_id = message.message_id
                bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id)
        else:
            if data['date_exp'] == '' or data['date_exp'] == None:
                message = bot.send_message(message.chat.id, text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
                user_message_id = message.message_id
                bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id)
            else:
                message = bot.send_message(message.chat.id, text="Введите дату предоставления авто на СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
                user_message_id = message.message_id
                bot.register_next_step_handler(message, date_sto, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
def date_sto(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_sto": message.text})
        data.update({"date_zayav_sto": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"status": 'Отправлено заявление СТО'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        if data['sobstvenik'] == 'Yes':
            replace_words_in_word(["{{ СТО }}", "{{ ИНН_СТО }}", "{{ Индекс_СТО }}", 
                                "{{ Адрес_СТО }}", "{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}",
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}","{{ Телефон_представителя }}",
                                "{{ Номер_направления_СТО }}",
                                "{{ Страховая }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_предоставления_ТС }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}",
                                "{{ Дата_Заявления_СТО }}", "{{ ФИОк }}", "{{ Дата }}", "{{ Телефон }}"],
                                [str(data["name_sto"]), str(data["inn_sto"]), str(data["index_sto"]),
                                    str(data["address_sto"]), str(data["fio"]),str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), str(data["number_not"]),
                                    str(data["N_sto"]),
                                    str(data["insurance"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_sto"]), str(data["marks"]), str(data["car_number"]), str(data["date_zayav_sto"]),str(data["fio_k"]),
                                    str(data["date_ins"]), str(data["number"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\6. Заявление в СТО представитель.docx",
                                    data["fio"]+"\\Документы\\"+"6. Заявление в СТО представитель.docx")
        else:
            replace_words_in_word(["{{ СТО }}", "{{ ИНН_СТО }}", "{{ Индекс_СТО }}", 
                                "{{ Адрес_СТО }}", "{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}",
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}","{{ Номер_направления_СТО }}",
                                "{{ Страховая }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_предоставления_ТС }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}",
                                "{{ Дата_Заявления_СТО }}", "{{ ФИОк }}", "{{ Дата }}", "{{ Телефон }}"],
                                [str(data["name_sto"]), str(data["inn_sto"]), str(data["index_sto"]),
                                    str(data["address_sto"]), str(data["fio"]),str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["N_sto"]),
                                    str(data["insurance"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_sto"]), str(data["marks"]), str(data["car_number"]), str(data["date_zayav_sto"]),str(data["fio_k"]),
                                    str(data["date_ins"]), str(data["number"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\6. Заявление в СТО.docx",
                                    data["fio"]+"\\Документы\\"+"6. Заявление в СТО.docx")
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="vibor2STOYes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="vibor2STONo")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)

    
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату предоставления авто на СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_sto, data, user_message_id)

def address_sto_main(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"address_sto_main": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату записи в свое СТО для дополнительного осмотра в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, date_sto_main, data, user_message_id)
def date_sto_main(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_sto_main": message.text})
        message = bot.send_message(message.chat.id, text="Введите время записи в свое СТО для дополнительного осмотра в формате ЧЧ:ММ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_sto_main, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату записи в свое СТО для дополнительного осмотра в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_sto_main, data, user_message_id)
def time_sto_main(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text) != 5 or message.text.count(':') != 1:
        message = bot.send_message(
            message.chat.id,
            "Неправильный формат времени!\n"
            "Введите время записи в свое СТО для дополнительного осмотра в формате ЧЧ:ММ (например: 14:30)"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_sto_main, data, user_message_id)
        return
    try:
 
        datetime.strptime(message.text, "%H:%M")

        data.update({"time_sto_main": message.text})
        data.update({"dop_osm": "Yes"})
        data.update({"data_dop_osm": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"status": 'Отправлено заявление на доп.осмотр'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        if data['sobstvenik'] == 'No':
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", "{{ Nакта_осмотра }}", "{{ Дата }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_осмотра }}",
                                "{{ Дата_свое_СТО }}","{{ Время_свое_СТО }}","{{ Адрес_свое_СТО }}", "{{ Телефон }}",
                                "{{ Дата_заявления_доп_осмотр }}"],
                                [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["Na_ins"]), str(data["date_ins"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_Na_ins"]), str(data["date_sto_main"]),
                                    str(data["time_sto_main"]), str(data["address_sto_main"]), str(data["number"]),
                                    str(data["data_dop_osm"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\4. Заявление о проведении доп осмотра\\4. Заявление о проведении дополнительного осмотра автомобиля.docx",
                                    data["fio"]+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля.docx")
        else:
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", 
                                "{{ NДоверенности }} ", "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Телефон_представителя }}",
                                "{{ Nакта_осмотра }}", "{{ Дата }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_осмотра }}",
                                "{{ Дата_свое_СТО }}","{{ Время_свое_СТО }}","{{ Адрес_свое_СТО }}", "{{ Телефон }}", 
                                "{{ Дата_заявления_доп_осмотр }}"],
                                [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),
                                    str(data["Na_ins"]), str(data["date_ins"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_Na_ins"]), str(data["date_sto_main"]),
                                    str(data["time_sto_main"]), str(data["address_sto_main"]), str(data["number"]),
                                    str(data["data_dop_osm"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\4. Заявление о проведении доп осмотра\\4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx",
                                    data["fio"]+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx")
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="dopOsmYes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="dopOsmNo")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)
    except ValueError:
        message = bot.send_message(
            message.chat.id, 
            "Неправильный формат времени!\n"
            "Введите время записи в свое СТО в формате ЧЧ:ММ (например: 14:30)"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, time_sto_main, data, user_message_id)




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
