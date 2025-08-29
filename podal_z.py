from telebot import types
from datetime import datetime, timedelta
import re
import time
import json
import sqlite3
from num2words import num2words
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

    @bot.callback_query_handler(func=lambda call: call.data == "btn_podal_zayavl")
    def callback_pit(call):
        data = {'accident': 'podal_zayavl'}
        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("На выплату", callback_data="btn_podal_zayavl_viplata")
        btn2 = types.InlineKeyboardButton("На ремонт", callback_data="btn_podal_zayavl_rem")
        btn3 = types.InlineKeyboardButton("Главное меню", callback_data="start")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="На что подали заявление?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["start"])
    def callback_start(call):
         clear_chat_history_optimized(call.message,1)
         start_handler(call.message)
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_podal_zayavl_viplata"])
    def callback_pit_city(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]

        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Выплатили", callback_data="btn_podal_zayavl_viplata_yes")
        btn2 = types.InlineKeyboardButton("Не выплатили", callback_data="btn_podal_zayavl_viplata_no")
        btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_podal_zayavl")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="На что подали заявление?",
            reply_markup=keyboard
        ) 
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_podal_zayavl_viplata_yes"])
    def callback_podal_zayavl_viplata_yes(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]

        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="btn_viplatily_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="btn_viplatily_no")
        btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_podal_zayavl")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Есть ли соглашение со страховой?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_viplatily_yes"])
    def callback_viplatily_yes(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]

        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Деликт", callback_data="btn_viplatily_yes_delict")
        btn2 = types.InlineKeyboardButton("Цессия", callback_data="btn_viplatily_yes_ceccia")
        btn3 = types.InlineKeyboardButton("Расторжение соглашения", callback_data="btn_viplatily_yes_rast")
        btn4 = types.InlineKeyboardButton("Назад", callback_data="btn_podal_zayavl_viplata_yes")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите из предложенных вариантов",
            reply_markup=keyboard
        )
 
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_viplatily_yes_rast"])
    def callback_viplatily_yes_rast(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]

        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Не занимаемся", callback_data="start")
        btn2 = types.InlineKeyboardButton("Ура", callback_data="start")
        btn3 = types.InlineKeyboardButton("Деликт", callback_data="start")
        btn4 = types.InlineKeyboardButton("Назад", callback_data="btn_viplatily_yes")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите из предложенных вариантов",
            reply_markup=keyboard
        ) 
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_podal_zayavl_rem", "btn_podal_zayavl_viplata_no", "btn_viplatily_yes_delict", "btn_viplatily_yes_ceccia"])
    def btn_podal_zayavl_rem(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        

        user_id = call.message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="btn_podal_zayavl_rem_own")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="btn_podal_zayavl_rem_Nown")
        keyboard.add(btn1)
        keyboard.add(btn2)
        if call.data == "btn_podal_zayavl_rem":
            data['accident'] = 'dtp'
            btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_podal_zayavl")
            keyboard.add(btn3)
        elif call.data == "btn_podal_zayavl_viplata_no":
            data['accident'] = 'dtp'
            btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_podal_zayavl_viplata")
            keyboard.add(btn3)
            data.update({'vibor': 'no_money'})
        elif call.data == "btn_viplatily_yes_delict":
            btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_viplatily_yes")
            keyboard.add(btn3)
            data.update({'vibor': 'delict'})
        elif call.data == "btn_viplatily_yes_ceccia":
            btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_viplatily_yes")
            keyboard.add(btn3)
            data.update({'vibor': 'ceccia'})
        
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Клиент собственник?",
            reply_markup=keyboard
        )
       
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_podal_zayavl_rem_own", "btn_podal_zayavl_rem_Nown"])
    def callback_podal_zayavl_rem_own(call):
        if call.data == "btn_podal_zayavl_rem_own":
            call.data = "btn_podal_zayavl_rem_own"
        elif call.data =="btn_podal_zayavl_rem_Nown":
            call.data = "btn_podal_zayavl_rem_Nown"
        else:
            return
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         

        data.update({"sobstvenik": "Yes" if call.data == "btn_podal_zayavl_rem_own" else "No"})
        user_temp_data[user_id] = data
         

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="btn_podal_zayavl_rem_ev_Yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="btn_podal_zayavl_rem_ev_No")
        btn3 = types.InlineKeyboardButton("Назад", callback_data="btn_podal_zayavl_rem")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Эвакуатор вызывали?",
            reply_markup=keyboard
        )  

    @bot.callback_query_handler(func=lambda call: call.data in ["btn_podal_zayavl_rem_ev_Yes", "btn_podal_zayavl_rem_ev_No"])
    def callback_podal_zayavl_rem_ev(call):
        if call.data == "btn_podal_zayavl_rem_ev_Yes":
            call.data = "btn_podal_zayavl_rem_ev_Yes"
        elif call.data == "btn_podal_zayavl_rem_ev_No":
            call.data = "btn_podal_zayavl_rem_ev_No"
        else:
            return
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         

        data.update({"ev": "Yes" if call.data == "btn_dtp_ev_Yes" else "No"})
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()      
        btn1 = types.InlineKeyboardButton("Томск", callback_data="btn_podal_zayavl_rem_city_Tomsk")
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

    @bot.callback_query_handler(func=lambda call: call.data in ["podal_zayavl_next"])
    def callback_podal_zayavl_next(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="""Подготовьте документы:
            1. Доверенность
            """,
            reply_markup=None
        )
        user_message_id = message.message_id 
        if data['vibor'] == 'delict':
            message = bot.send_message(call.message.chat.id, "Введите стоимость услуг нотариуса")
            user_message_id1 = message.message_id
            bot.register_next_step_handler(message, coin_not, data, user_message_id, user_message_id1)
        elif data['vibor'] == 'ceccia':
            message = bot.send_message(call.message.chat.id, "Введите ФИО цессионария в формате Иванов Иван Иванович")
            user_message_id1 = message.message_id
            bot.register_next_step_handler(message, FIO_c, data, user_message_id, user_message_id1)
    @bot.callback_query_handler(func=lambda call: call.data in ["podal_zayavl_nexto"])
    def callback_podal_zayavl_nexto(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="""Подготовьте документы:
            1. Выплатное дело
            2. Платежное поручение
            3. Экспертиза
            """,
            reply_markup=None
        )
        user_message_id = message.message_id 
        if data['vibor'] == 'delict':
            user_id = call.message.from_user.id
            data = user_temp_data[user_id]
            clear_chat_history_optimized(call.message, 6)
            callback_client_details2_handler(call.message, data['client_id'])
            # message = bot.send_message(call.message.chat.id, "Введите стоимость услуг нотариуса")
            # user_message_id1 = message.message_id
            # bot.register_next_step_handler(message, coin_not, data, user_message_id, user_message_id1)
        elif data['vibor'] == 'ceccia':
            message = bot.send_message(call.message.chat.id, "Введите номер выплатного дела")
            user_message_id1 = message.message_id
            bot.register_next_step_handler(message, N_viplat_work, data, user_message_id, user_message_id1)  
    @bot.callback_query_handler(func=lambda call: call.data in ["btn_podal_zayavl_rem_city_Tomsk"])
    def callback_podal_zayavl_rem_city(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
        if call.data == "btn_podal_zayavl_rem_city_Tomsk":
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
            6. Банковские реквизиты""",
            reply_markup=None
        )
        user_message_id = message.message_id 
        message = bot.send_message(call.message.chat.id, "Введите ФИО клиента в формате Иванов Иван Иванович")
        user_message_id1 = message.message_id
        bot.register_next_step_handler(message, FIO, data, user_message_id, user_message_id1)

    @bot.callback_query_handler(func=lambda call: call.data in ["gibdd_podal_zayavl", "avarkom_podal_zayavl", "evro_podal_zayavl"])
    def callback_who_podal_zayavl_rem(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        user_message_id = [] 
          
        if call.data == "gibdd_podal_zayavl":
            data.update({"who_dtp": "ГИБДД"})
        elif call.data == "avarkom_podal_zayavl":
            data.update({"who_dtp": "Аварком"})
        elif call.data == "evro_podal_zayavl":
            data.update({"who_dtp": "Евро-протокол"})
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку, модель клиента",
            reply_markup=None
        )
        user_message_id = message.message_id  
        bot.register_next_step_handler(message, marks, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["STS_podal_zayavl", "PTS_podal_zayavl", "DKP_podal_zayavl"])
    def callback_docs_podal_zayavl(call):
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
        user_message_id = [] 
          
        if call.data == "STS_podal_zayavl":
            data.update({"docs": "СТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_docs, data, user_message_id)

        elif call.data == "PTS_podal_zayavl":
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
    
    @bot.callback_query_handler(func=lambda call: call.data in ["Reco_podal_zayavl", "Ugo_podal_zayavl", "SOGAZ_podal_zayavl", "Ingo_podal_zayavl", "Ros_podal_zayavl", "Maks_podal_zayavl", "Energo_podal_zayavl", "Sovko_podal_zayavl", "other_podal_zayavl"])
    def callback_insurance_podal_zayavl(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        user_message_id=[] 
          
        if call.data == "SOGAZ_podal_zayavl":
            data.update({"insurance": 'АО "Согаз"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            )
            user_message_id = message.message_id 
  
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        elif call.data == "Reco_podal_zayavl":
            data.update({"insurance": 'САО "Ресо-Гарантия"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        elif call.data == "Ugo_podal_zayavl":
            data.update({"insurance": 'АО "ГСК "Югория"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        elif call.data == "Ingo_podal_zayavl":
            data.update({"insurance": 'СПАО "Ингосстрах"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        elif call.data == "Ros_podal_zayavl":
            data.update({"insurance": 'ПАО СК "Росгосстрах"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        elif call.data == "Maks_podal_zayavl":
            data.update({"insurance": 'АО "Макс"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        elif call.data == "Energo_podal_zayavl":
            data.update({"insurance": 'ПАО «САК «Энергогарант»'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        elif call.data == "Sovko_podal_zayavl":
            data.update({"insurance": 'АО «Совкомбанк страхование»'})
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
    @bot.callback_query_handler(func=lambda call: call.data in ["sud1_podal_zayavl", "sud2_podal_zayavl", "sud3_podal_zayavl", "sud4_podal_zayavl", "sud5_podal_zayavl", "sud6_podal_zayavl", "sudOther_podal_zayavl"])
    def callback_insurance(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
        user_message_id = []  
        if call.data == "sud1_podal_zayavl":
            data.update({"sud": 'Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud2_podal_zayavl":
            data.update({"sud": 'Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud3_podal_zayavl":
            data.update({"sud": 'Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud4_podal_zayavl":
            data.update({"sud": 'Томский областной суд, 634003, г. Томск, пер. Макушина, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud5_podal_zayavl":
            data.update({"sud": 'Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_money, data, user_message_id)
        elif call.data == "sud6_podal_zayavl":
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
    @bot.callback_query_handler(func=lambda call: call.data in ["YesPr_podal_z", "NoPr_podal_z"])
    def callback_send_docs_podal_zayavl2(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]

        if call.data == "YesPr_podal_z":
            if data['vibor'] == 'delict':
                documents = [
                {"path": data["fio"]+"\\"+data["fio"] + "_заявление_ГИБДД.docx", "name": "Заявление в ГИБДД"},
                {"path": data["fio"]+"\\"+data["fio"] + "_запрос_в_страховую.docx", "name": "Запрос в страховую"},
                ]
            elif data['vibor'] == 'ceccia':
                documents = [
                {"path": data["fio"]+"\\"+data["fio"] + "_соглашение_цессии.docx", "name": "Соглашение Цессии"},
                {"path": data["fio"]+"\\"+data["fio"] + "_договор_цессии.docx", "name": "Договор Цессиии"},
                {"path": data["fio"]+"\\"+data["fio"] + "_досуд_урег_цессии.docx", "name": "Досудебное урегулирование"},
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
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_podal_zayavl_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["YesIsk_podal_z", "NoIsk_podal_z"])
    def callback_isk_podal_zayavl2(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]

        if call.data == "YesIsk_podal_z":
            
            documents = [
            {"path": data["fio"]+"\\"+data["fio"] + "_исковое_заявление.docx", "name": "Исковое заявление"},
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
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_podal_zayavl_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["Yes_podal_zayavl", "No_podal_zayavl"])
    def callback_send_docs_podal_zayavl(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]

        if call.data == "Yes_podal_zayavl":
            if data['vibor'] == 'no_money':
                documents = [
            {"path": data["fio"]+"\\"+data["fio"] + "_обложка.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_юр_договор.docx", "name": "Юридический договор"},
            {"path": data["fio"]+"\\"+data["fio"] + "_заявление_в_страховую.docx", "name": "Заявление в страховую"},
            ]
            elif data['vibor'] == 'ceccia':
                documents = [
            {"path": data["fio"]+"\\"+data["fio"] + "_обложка.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_юр_договор.docx", "name": "Юридический договор"},
            {"path": data["fio"]+"\\"+data["fio"] + "_заявление_ГИБДД.docx", "name": "Заявление в ГИБДД"},
            {"path": data["fio"]+"\\"+data["fio"] + "_запрос_в_страховую.docx", "name": "Запрос в страховую"},
            ]
            else:
                documents = [
                {"path": data["fio"]+"\\"+data["fio"] + "_обложка.docx", "name": "Обложка дела"},
                {"path": data["fio"]+"\\"+data["fio"] + "_юр_договор.docx", "name": "Юридический договор"},
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
        btn1 = types.InlineKeyboardButton("Карточка клиента", callback_data="btn_podal_zayavl_back")
        keyboard.add(btn1)
        bot.send_message(call.message.chat.id, "При необходимости скачайте документы, после выхода в карточку клиента сообщения удалятся", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["not_rogalev_podal_z","not_other_podal_z"])
    def callback_notarius_podal_z(call):
        user_id = call.message.from_user.id

        data = user_temp_data[user_id]
          
        if call.data == "not_rogalev_podal_z":
            data.update({"fio_not": 'Рогалев Семен Иннокентьевич'})

            user_id = call.message.from_user.id
            user_temp_data[user_id] = data
                
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("+79966368941", callback_data="number_rogalev_podal_z")
            btn2 = types.InlineKeyboardButton("Другое", callback_data="number_not_other_podal_z")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите номер телефона представителя",
            reply_markup=keyboard
            ) 
        else:
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО представителя в формате Иванов Иван Иванович",
            reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_not, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["number_rogalev_podal_z","number_not_other_podal_z"])
    def callback_number_notarius_podal_z(call):

        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        if call.data == "number_rogalev_podal_z":
            data.update({"number_not": '+79966368941'})
            data.update({"pret": str(datetime.now().strftime("%d.%m.%Y"))})
            data.update({"date_pret": str((datetime.now() + timedelta(weeks=2)).strftime("%d.%m.%Y"))})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            if data['vibor'] == "delict":
                replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                    "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                    "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                    "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                    [str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                        str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                        str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                        str(data["number"]), str(data["fio_k"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\4. Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                        data["fio"]+"\\"+data["fio"]+"_заявление_ГИБДД.docx")
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}"
                                    "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                    "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                    "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                    [str(data["insurance"]),str(data["city"]),str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                        str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                        str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                        str(data["number"]), str(data["fio_k"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\4. Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                        data["fio"]+"\\"+data["fio"]+"_запрос_в_страховую.docx")
                data.update({"status": 'Отправлен запрос в страховую'}) 
            elif data['vibor'] == "ceccia":
                if len(data['fio_culp'])==2:
                    fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."
                else:
                    fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."+list(data['fio_culp'].split()[2])[0]+"."

                replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Дата }}", 
                                    "{{ Город }}", "{{ ЦФИО }}","{{ ЦДР }}", "{{ ЦМесто }}",
                                    "{{ ЦПаспорт_серия }}", "{{ ЦПаспорт_номер }}", "{{ ЦПаспорт_выдан }}","{{ ЦПаспорт_когда }}","{{ ЦИндекс }}",
                                    "{{ ЦАдрес }}", "{{ ФИО }}","{{ ДР }}", "{{ Место }}",
                                    "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Индекс }}",
                                    "{{ Адрес }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}"],
                                    [str(data["year"]), str(data["client_id"]), str(data["pret"]), str(data["city"]),
                                        str(data["fio_c"]), str(data["date_of_birth_c"]),str(data["city_birth_с"]), str(data["seria_pasport_c"]),
                                        str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                        str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                        str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                        str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\4. Деликт\\Цессия 5. Соглашение о замене стороны Цессия.docx",
                                        data["fio"]+"\\"+data["fio"]+"_соглашение_цессии.docx")
                replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Дата }}", 
                                    "{{ Город }}", "{{ ЦФИО }}","{{ ЦДР }}", "{{ ЦМесто }}",
                                    "{{ ЦПаспорт_серия }}", "{{ ЦПаспорт_номер }}", "{{ ЦПаспорт_выдан }}","{{ ЦПаспорт_когда }}","{{ ЦИндекс }}",
                                    "{{ ЦАдрес }}", "{{ ФИО }}","{{ ДР }}", "{{ Место }}",
                                    "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Индекс }}",
                                    "{{ Адрес }}", "{{ винФИО }}", "{{ ДР_Виновника }}", "{{ Индекс_Виновника }}","{{ Адрес_Виновника }}","{{ Разница }}",
                                    "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}",
                                    "{{ Nавто_виновник }}", "{{ винФИОкор }}", "{{ Экспертиза }}", "{{ Выплата_ОСАГО }}","{{ Стоимость_экспертизы }}","{{ Дата_экспертизы }}",
                                    "{{ Дата_уведомления }}","{{ Цена_цессии }}", " {{ Телефон }}", "{{ ФИОк }}","{{ ЦТелефон }}", "{{ ЦФИОк }}"],
                                    [str(data["year"]), str(data["client_id"]), str(data["pret"]), str(data["city"]),
                                        str(data["fio_c"]), str(data["date_of_birth_c"]),str(data["city_birth_с"]), str(data["seria_pasport_c"]),
                                        str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                        str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                        str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                        str(data["fio_culp"]), str(data["date_of_birth_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(float(data["coin_exp"])-float(data['coin_osago'])), 
                                        str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),
                                        str(data["number_auto_culp"]), str(fio_culp_k), str(data["coin_exp"]), str(data["coin_osago"]),str(data["coin_exp_izn"]),
                                        str(data["date_exp"]), str(data["date_pret"]), str(data["coin_c"]), str(data["number"]), str(data["fio_k"]), str(data["number_c"]),str(data["fio_c_k"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\Цессия 6. Договор цессии.docx",
                                        data["fio"]+"\\"+data["fio"]+"_договор_цессии.docx")
                replace_words_in_word(["{{ винФИО }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                    "{{ Разница }}", "{{ ФИО }}","{{ Год }}", "{{ NКлиента }}",
                                    "{{ Дата }}", "{{ ЦФИО }}"],
                                    [str(data["fio_culp"]), str(data["date_dtp"]), str(data["time_dtp"]), str(float(data["coin_exp"])-float(data['coin_osago'])),
                                        str(data["fio"]), str(data["year"]),str(data["client_id"]), str(data["pret"]),
                                        str(data["fio_c"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\Цессия 7. Предложение о досудебном урегулировании спора.docx",
                                        data["fio"]+"\\"+data["fio"]+"_досуд_урег_цессии.docx")
                data.update({"status": 'Отправлено предложение о досудебном урегулировании'})
            data.update({"vibor1": 'Yes'})  
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            user_id = call.message.from_user.id
            user_temp_data[user_id] = data
             
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr_podal_z")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr_podal_z")
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
    @bot.callback_query_handler(func=lambda call: call.data =="btn_podal_zayavl_back")
    def callback_podal_zayavl_back(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
        clear_chat_history_optimized(call.message, 6)
        callback_client_details2_handler(call.message, data['client_id'])

def FIO(message, data, user_message_id, user_message_id1):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, user_message_id1)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО клиента в формате Иванов Иван Иванович".format(message.from_user))
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
    if data['sobstvenik'] == 'Yes':
        data.update({"fio_sobs": "-"})
        data.update({"date_of_birth_sobs": "-"})
        message = bot.send_message(message.chat.id, text="Введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_dtp, data, user_message_id)
    else:
        message = bot.send_message(message.chat.id, text="Введите ФИО собственника в формате Иванов Иван Иванович".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, fio_sobs, data, user_message_id)

def fio_sobs(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО собственника в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_sobs, data, user_message_id)
    else:
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

    btn1 = types.InlineKeyboardButton("ГИБДД", callback_data="gibdd_podal_zayavl")
    btn2 = types.InlineKeyboardButton("Аварком", callback_data="avarkom_podal_zayavl")
    btn3 = types.InlineKeyboardButton("Евро-протокол", callback_data="evro_podal_zayavl")
    
    keyboard.add(btn1)
    keyboard.add(btn2)
    keyboard.add(btn3)

    bot.send_message(
        message.chat.id, 
        "Кого вызывали на фиксацию дтп", 
        reply_markup=keyboard
    )


def marks(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
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

        btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="STS_podal_zayavl")
        btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="PTS_podal_zayavl")
        btn3 = types.InlineKeyboardButton("Договор купли-продажи ТС", callback_data="DKP_podal_zayavl")
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
         
             
        user_message_id=[]
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton('САО "Ресо-Гарантия"', callback_data="Reco_podal_zayavl")
        btn2 = types.InlineKeyboardButton('АО "ГСК "Югория"', callback_data="Ugo_podal_zayavl")
        btn3 = types.InlineKeyboardButton('АО "Согаз"', callback_data="SOGAZ_podal_zayavl")
        btn4 = types.InlineKeyboardButton('СПАО "Ингосстрах"', callback_data="Ingo_podal_zayavl")
        btn5 = types.InlineKeyboardButton('ПАО СК "Росгосстрах"', callback_data="Ros_podal_zayavl")
        btn6 = types.InlineKeyboardButton('АО "Макс"', callback_data="Maks_podal_zayavl")
        btn7 = types.InlineKeyboardButton('ПАО «САК «Энергогарант»', callback_data="Energo_podal_zayavl")
        btn8 = types.InlineKeyboardButton('АО «Совкомбанк страхование»', callback_data="Sovko_podal_zayavl")
        btn9 = types.InlineKeyboardButton('Другое', callback_data="other_podal_zayavl")
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
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ".format(message.from_user))
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
        message = bot.send_message(message.chat.id, text="Введите дату подачи заявления в страховую в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_ins_pod, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату страхового полиса в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_insurance, data, user_message_id)
def date_ins_pod(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_ins_pod": message.text})
        message = bot.send_message(message.chat.id, text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, fio_culp, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату подачи заявления в страховую в формате ДД.ММ.ГГГГ".format(message.from_user))
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
        message = bot.send_message(message.chat.id, "Введите банк получателя клиента")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, bank, data, user_message_id)
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
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"year": list(str(datetime.now().year))[2]+list(str(datetime.now().year))[3]})
        data.update({"INN": message.text})
        data.update({"answer_ins": ''})
        data.update({"analis_ins": ''})
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
        data.update({"coin_not": ''})
        data.update({"N_dov_not": ''})
        data.update({"data_dov_not": ''})
        data.update({"fio_not": ''})
        data.update({"number_not": ''})
        data.update({"date_ins": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"pret": ''})
        data.update({"ombuc": ''})
        data.update({"data_pret_prin": ''})
        data.update({"data_pret_otv": ''})
        data.update({"N_pret_prin": ''})
        data.update({"date_ombuc": ''})
        if data['vibor'] == "no_money":
            data.update({"status": 'Отправлено заявление в страховую'})
        elif data['vibor'] == "ceccia":
            data.update({"status": 'Отправлен запрос в страховую'})
        else:
            data.update({"status": 'Заполнен договор'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
            data['client_id'] = "70001"
        #Обложка
        create_fio_data_file(data)
        if data["sobstvenik"]=="Yes":
            replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                "{{ Страховая }}", "{{ винФИО }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела\\1.ab Обложка дела.docx",
                                    data["fio"]+"\\"+data["fio"]+"_обложка.docx")
        elif data["sobstvenik"]=="No":
            replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                "{{ Страховая }}", "{{ винФИО }}", "{{ собТС_ФИО }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"]), str(data["fio_sobs"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела\\1.cd Обложка дела.docx",
                                    data["fio"]+"\\"+data["fio"]+"_обложка.docx")
        #Юр.Договор
        replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", 
                            "{{ Дата }}", "{{ ФИО }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}",
                            "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", "{{ Индекс }}","{{ Адрес }}","{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                            [str(data['year']), str(data['client_id']), str(data["city"]), str(datetime.now().strftime("%d.%m.%Y")),
                                str(data["fio"]), str(data["seria_pasport"]),str(data["number_pasport"]), str(data["where_pasport"]),
                                str(data["when_pasport"]), str(data["index_postal"]), str(data["address"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                                str(data["address_dtp"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\1. На ремонт\\2. Юр договор.docx",
                                data["fio"]+"\\"+data["fio"]+"_юр_договор.docx")
        if data['vibor'] == "no_money":
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                        "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                        "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                        "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                        "{{ ФИОк }}"],
                        [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                            str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["date_dtp"]),
                            str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),str(data["date_ins_pod"]), 
                            str(data["seria_docs"]), str(data["number_docs"]), str(data["city"]), str(data["date_ins"]), str(data["fio_k"])],
                            "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                            data["fio"]+"\\"+data["fio"]+"_заявление_в_страховую.docx")
        elif data['vibor'] == "ceccia":
                replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                    "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                    "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                    "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                    [str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                        str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                        str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                        str(data["number"]), str(data["fio_k"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 3. Заявление о выдаче копии справки участников ДТП.docx",
                                        data["fio"]+"\\"+data["fio"]+"_заявление_ГИБДД.docx")
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}",
                                    "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                    "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                    "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                    [str(data["insurance"]),str(data["city"]),str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                        str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                        str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                        str(data["number"]), str(data["fio_k"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                        data["fio"]+"\\"+data["fio"]+"_запрос_в_страховую.docx")
        
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="Yes_podal_zayavl")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="No_podal_zayavl")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)        
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН банка."
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, INN, data, user_message_id)


def coin_not(message, data, user_message_id, user_message_id1):
    if data['vibor'] == 'delict':
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, user_message_id1)
        bot.delete_message(message.chat.id, message.message_id)
    else:
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    data.update({"coin_not": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер доверенности".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, N_dov_not, data, user_message_id)

def N_dov_not(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"N_dov_not": message.text})
    message = bot.send_message(message.chat.id, text="Введите дату доверенности в формате ДД.ММ.ГГГГ.".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, data_dov_not, data, user_message_id)
def data_dov_not(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_dov_not": message.text})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Рогалев Семен Иннокентьевич", callback_data="not_rogalev_podal_z")
        btn2 = types.InlineKeyboardButton("Другое", callback_data="not_other_podal_z")
        keyboard.add(btn1)
        keyboard.add(btn2)
        bot.send_message(message.chat.id, text="Выберите ФИО представителя".format(message.from_user), reply_markup = keyboard)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату доверенности в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_dov_not, data, user_message_id)
def fio_not(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО представителя в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_not, data, user_message_id)
    else:
        data.update({"fio_not": message.text})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
            
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("+79966368941", callback_data="number_rogalev_podal_z")
        btn2 = types.InlineKeyboardButton("Другое", callback_data="number_not_other_podal_z")
        keyboard.add(btn1)
        keyboard.add(btn2)
        bot.send_message(
        chat_id = message.chat.id,
        text="Выберите номер телефона представителя",
        reply_markup=keyboard
        ) 

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
        data.update({"pret": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"date_pret": str((datetime.now() + timedelta(weeks=2)).strftime("%d.%m.%Y"))})
        
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        if data['vibor'] == "delict":
            replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                [str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                    str(data["number"]), str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\4. Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                    data["fio"]+"\\"+data["fio"]+"_заявление_ГИБДД.docx")
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}"
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                [str(data["insurance"]),str(data["city"]),str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                    str(data["number"]), str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\4. Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                    data["fio"]+"\\"+data["fio"]+"_запрос_в_страховую.docx")
            data.update({"status": 'Отправлен запрос в страховую'})
        elif data['vibor'] == "ceccia":
            if len(data['fio_culp'])==2:
                fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."
            else:
                fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."+list(data['fio_culp'].split()[2])[0]+"."

            replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Дата }}", 
                                "{{ Город }}", "{{ ЦФИО }}","{{ ЦДР }}", "{{ ЦМесто }}",
                                "{{ ЦПаспорт_серия }}", "{{ ЦПаспорт_номер }}", "{{ ЦПаспорт_выдан }}","{{ ЦПаспорт_когда }}","{{ ЦИндекс }}",
                                "{{ ЦАдрес }}", "{{ ФИО }}","{{ ДР }}", "{{ Место }}",
                                "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Индекс }}",
                                "{{ Адрес }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}"],
                                [str(data["year"]), str(data["client_id"]), str(data["pret"]), str(data["city"]),
                                    str(data["fio_c"]), str(data["date_of_birth_c"]),str(data["city_birth_с"]), str(data["seria_pasport_c"]),
                                    str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                    str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                    str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\4. Деликт\\Цессия 5. Соглашение о замене стороны Цессия.docx",
                                    data["fio"]+"\\"+data["fio"]+"_соглашение_цессии.docx")
            replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Дата }}", 
                                "{{ Город }}", "{{ ЦФИО }}","{{ ЦДР }}", "{{ ЦМесто }}",
                                "{{ ЦПаспорт_серия }}", "{{ ЦПаспорт_номер }}", "{{ ЦПаспорт_выдан }}","{{ ЦПаспорт_когда }}","{{ ЦИндекс }}",
                                "{{ ЦАдрес }}", "{{ ФИО }}","{{ ДР }}", "{{ Место }}",
                                "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Индекс }}",
                                "{{ Адрес }}", "{{ винФИО }}", "{{ ДР_Виновника }}", "{{ Индекс_Виновника }}","{{ Адрес_Виновника }}","{{ Разница }}",
                                "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}",
                                "{{ Nавто_виновник }}", "{{ винФИОкор }}", "{{ Экспертиза }}", "{{ Выплата_ОСАГО }}","{{ Стоимость_экспертизы }}","{{ Дата_экспертизы }}",
                                "{{ Дата_уведомления }}","{{ Цена_цессии }}", " {{ Телефон }}", "{{ ФИОк }}","{{ ЦТелефон }}", "{{ ЦФИОк }}"],
                                [str(data["year"]), str(data["client_id"]), str(data["pret"]), str(data["city"]),
                                    str(data["fio_c"]), str(data["date_of_birth_c"]),str(data["city_birth_с"]), str(data["seria_pasport_c"]),
                                    str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                    str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                    str(data["fio_culp"]), str(data["date_of_birth_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(float(data["coin_exp"])-float(data['coin_osago'])), 
                                    str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),
                                    str(data["number_auto_culp"]), str(fio_culp_k), str(data["coin_exp"]), str(data["coin_osago"]),str(data["coin_exp_izn"]),
                                    str(data["date_exp"]), str(data["date_pret"]), str(data["coin_c"]), str(data["number"]), str(data["fio_k"]), str(data["number_c"]),str(data["fio_c_k"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\Цессия 6. Договор цессии.docx",
                                    data["fio"]+"\\"+data["fio"]+"_договор_цессии.docx")
            replace_words_in_word(["{{ винФИО }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Разница }}", "{{ ФИО }}","{{ Год }}", "{{ NКлиента }}",
                                "{{ Дата }}", "{{ ЦФИО }}"],
                                [str(data["fio_culp"]), str(data["date_dtp"]), str(data["time_dtp"]), str(float(data["coin_exp"])-float(data['coin_osago'])),
                                    str(data["fio"]), str(data["year"]),str(data["client_id"]), str(data["pret"]),
                                    str(data["fio_c"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\Цессия 7. Предложение о досудебном урегулировании спора.docx",
                                    data["fio"]+"\\"+data["fio"]+"_досуд_урег_цессии.docx")
            data.update({"status": 'Отправлено предложение о досудебном урегулировании'})
        data.update({"vibor1": 'Yes'}) 
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)

        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr_podal_z")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr_podal_z")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, "Данные сохранены, отправить вам документы?", reply_markup=keyboard)

def FIO_c(message, data, user_message_id, user_message_id1):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, user_message_id1)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.split())<2:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО Цессионария в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, FIO_c, data, user_message_id, user_message_id)
    else:
        data.update({"fio_c": message.text})
        if len(message.text.split())==2:
            data.update({"fio_c_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."})
        else:
            data.update({"fio_c_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."+list(message.text.split()[2])[0]+"."})
        message = bot.send_message(message.chat.id, text="Введите серию паспорта Цессионария, например, 1234".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, seria_pasport_c, data, user_message_id)

def seria_pasport_c(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 4 цифры!\nВведите серию паспорта Цессионария, например, 1234.".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_pasport_c, data, user_message_id)
        else:
            data.update({"seria_pasport_c": int(message.text.replace(" ", ""))})
            message = bot.send_message(message.chat.id, text="Введите номер паспорта Цессионария, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_pasport_c, data, user_message_id)

def number_pasport_c(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите номер паспорта Цессионария, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_pasport_c,data, user_message_id)
    else:
        data.update({"number_pasport_c": int(message.text.replace(" ", ""))})
        message = bot.send_message(message.chat.id, text="Кем выдан паспорт Цессионария?".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, where_pasport_c, data, user_message_id)

def where_pasport_c(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"where_pasport_c": message.text})
    message = bot.send_message(message.chat.id, text="Когда выдан паспорт Цессионария? Введите в формате ДД.ММ.ГГГГ".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, when_pasport_c, data, user_message_id)

def when_pasport_c(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"when_pasport_c": message.text})
        message = bot.send_message(message.chat.id, text="Введите адрес проживания Цессионария".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, address_c, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выдачи паспорта Цессионария в формате ДД.ММ.ГГГГ.".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, when_pasport_c, data, user_message_id)

def address_c(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"address_c": message.text})
    message = bot.send_message(message.chat.id, text="Введите почтовый индекс Цессионария".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, index_c, data, user_message_id)
def index_c(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите почтовый индекс Цессионария, например, 123456".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index, data, user_message_id)
    else:
        data.update({"index_postal_c": int(message.text.replace(" ", ""))})
        message = bot.send_message(message.chat.id, text="Дату рождения Цессионария в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth_с, data, user_message_id)   
def date_of_birth_с(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth_с": message.text})
        message = bot.send_message(message.chat.id, text="Введите город рождения Цессионария".format(message.from_user))
        time.sleep(0.1)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, city_birth_с, data, user_message_id)
    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения Цессионария в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_of_birth_с, data, user_message_id)
def city_birth_с(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    data.update({"city_birth_с": message.text})
    message = bot.send_message(message.chat.id, text="Введите номер телефона Цессионария в формате +79XXXXXXXXX".format(message.from_user))
    user_message_id = message.message_id
    bot.register_next_step_handler(message, number_c, data, user_message_id)

def number_c(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона Цессионария в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_c, data, user_message_id)
    else:
        data.update({"number_c": message.text})
        message = bot.send_message(message.chat.id, text="Введите серию ВУ виновника ДТП".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, seria_vu_culp, data, user_message_id)

def seria_vu_culp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
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
        message = bot.send_message(message.chat.id, text="Введите дату независимой экспертизы в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_exp, data, user_message_id)

def date_exp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_exp": message.text})
        message = bot.send_message(message.chat.id, text="Введите цену по независимой экспертизе".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp, data, user_message_id)

    except ValueError:
        message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату независимой экспертизы в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_exp, data, user_message_id)

def coin_exp(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_exp": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите стоимость экспертизы"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp_izn, data, user_message_id)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену по независимой экспертизе"
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
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость экспертизы"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp_izn, data, user_message_id)
def coin_osago(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_osago": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите цену цессии"
            )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_c, data, user_message_id)
        
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите сумму выплаты по ОСАГО"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_osago, data, user_message_id)
def coin_c(message, data, user_message_id):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, message.message_id)
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_c": message.text})
        message = bot.send_message(
            message.chat.id,
            text="Введите стоимость услуг нотариуса"
            )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_not, data, user_message_id, user_message_id)
        
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену цессии"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_c, data, user_message_id)

def N_viplat_work(message, data, user_message_id, user_message_id1):
    bot.delete_message(message.chat.id, user_message_id)
    bot.delete_message(message.chat.id, user_message_id1)
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

        btn1 = types.InlineKeyboardButton("1", callback_data="sud1_podal_zayavl")
        btn2 = types.InlineKeyboardButton("2", callback_data="sud2_podal_zayavl")
        btn3 = types.InlineKeyboardButton("3", callback_data="sud3_podal_zayavl")
        btn4 = types.InlineKeyboardButton("4", callback_data="sud4_podal_zayavl")
        btn5 = types.InlineKeyboardButton("5", callback_data="sud5_podal_zayavl")
        btn6 = types.InlineKeyboardButton("6", callback_data="sud6_podal_zayavl")
        btn7 = types.InlineKeyboardButton("Другое", callback_data="sudOther_podal_zayavl")
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
        data.update({"ombuc": "Yes"})
        data.update({"Done": "Yes"})
        data.update({"date_isk": str((datetime.now()).strftime("%d.%m.%Y"))})
        data.update({"status": 'Отправлено исковое заявление'})
        if len(data['fio_culp'])==2:
                fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."
        else:
            fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."+list(data['fio_culp'].split()[2])[0]+"."
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        if data['vibor'] == "delict":
            pass    
        elif data['vibor'] == "ceccia":
            replace_words_in_word(["{{ Суд }}", "{{ ЦФИО }}", "{{ ЦДР }}", 
                                "{{ Цпаспорт_серия }}", "{{ Цпаспорт_номер }}","{{ Цпаспорт_выдан }}", "{{ Цпаспорт_когда }}",
                                "{{ ЦИндекс }}", "{{ ЦАдрес }}", "{{ ЦТелефон }}","{{ Представитель }}","{{ NДоверенности }}",
                                "{{ Дата_доверенности }}", "{{ Телефон_представителя }}","{{ винФИО }}", "{{ ДР_Виновника }}",
                                "{{ Серия_ВУвин }}", "{{ Номер_ВУвин }}", "{{ Дата_ВУвин }}","{{ Индекс_Виновника }}","{{ Адрес_Виновника }}",
                                "{{ Адрес }}", "{{ винФИО }}", "{{ ДР_Виновника }}", "{{ Индекс_Виновника }}","{{ Адрес_Виновника }}","{{ Телефон_Виновника }}",
                                "{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ Индекс }}", "{{ Адрес }}", "{{ Телефон }}", "{{ Страховая }}","{{ Разница }}","{{ Цена_пошлины }}",
                                "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}",
                                "{{ Nавто_виновник }}", "{{ винФИОкор }}", "{{ Экспертиза }}", "{{ Выплата_ОСАГО }}","{{ Nвыплатного_дела }}","{{ Дата_выплатного_дела }}",
                                "{{ Nплатежного_поручения }}","{{ Дата_поручения }}", "{{ Год }}", "{{ NКлиента }}","{{ Дата }}", "{{ Стоимость_экспертизы }}",
                                "{{ Цена_нотариус }}","{{ Город }}", "{{ Дата_искового_заявления }}"],
                                [str(data["sud"]), str(data["fio_c"]), str(data["date_of_birth_c"]), str(data["seria_pasport_c"]),
                                    str(data["number_pasport_c"]), str(data["where_pasport_c"]),str(data["when_pasport_c"]), str(data["index_postal_c"]),
                                    str(data["address_c"]), str(data["number_c"]), str(data["fio_not"]), str(data["N_dov_not"]),str(data["data_dov_not"]), 
                                    str(data["number_not"]), str(data["fio_culp"]),str(data["date_of_birth_culp"]), str(data["seria_vu_culp"]),
                                    str(data["number_vu_culp"]), str(data["data_vu_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(data["number_culp"]), 
                                    str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["index_postal"]),
                                    str(data["address"]), str(data["number"]),str(data["insurance"]), str(float(data["coin_exp"])-float(data['coin_osago'])), 
                                    str(data["gos_money"]), str(data["date_dtp"]),str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data["marks_culp"]),str(data["number_auto_culp"]), str(fio_culp_k), str(data["coin_exp"]), str(data["coin_osago"]),str(data["N_viplat_work"]),
                                    str(data["date_viplat_work"]), str(data["N_plat_por"]), str(data["date_plat_por"]), str(data["year"]), str(data["client_id"]), str(data["pret"]),
                                    str(data["coin_exp_izn"]), str(data["coin_c"]), str(data["city"]), str(data["date_isk"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 8. Исковое заявление Цессия.docx",
                                    data["fio"]+"\\"+data["fio"]+"_исковое_заявление.docx")


        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="YesIsk_podal_z")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="NoIsk_podal_z")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, "Данные сохранены, отправить вам документы?", reply_markup=keyboard)
    else:
        message = bot.send_message(
            message.chat.id,
            text="Неправильный формат, стоимость должна состоять только из цифр в рублях, например: 50000!\nВведите стоимость государственной пошлины"
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, gos_money, data, user_message_id)







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