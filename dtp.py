from telebot import types
from datetime import datetime, timedelta
import re
import time
import json
import sqlite3
from word_utils import replace_words_in_word, create_fio_data_file
from database import DatabaseManager, save_client_to_db_with_id


bot = None
user_temp_data = {}


def init_bot(bot_instance, start_handler=None):
    """Инициализация бота в модуле"""
    global bot
    bot = bot_instance

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
            text="Клиент собственник?",
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
        bot.edit_message_text(
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
        message = bot.send_message(call.message.chat.id, "Введите ФИО в формате Иванов Иван Иванович")
        print(data)  
        bot.register_next_step_handler(message, FIO, data)
    @bot.callback_query_handler(func=lambda call: call.data in ["gibdd", "avarkom", "evro"])
    def callback_who_dtp(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        if call.data == "gibdd":
            data.update({"who_dtp": "ГИБДД"})
        elif call.data == "avarkom":
            data.update({"who_dtp": "Аварком"})
        elif call.data == "evro":
            data.update({"who_dtp": "Евро-протокол"})
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку, модель клиента",
            reply_markup=None
        )  
        print(data)  
        bot.register_next_step_handler(message, marks, data)

    @bot.callback_query_handler(func=lambda call: call.data in ["STS", "PTS", "DKP"])
    def callback_docs(call):
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "STS":
            data.update({"docs": "СТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )

            bot.register_next_step_handler(message, seria_docs, data)

        elif call.data == "PTS":
            data.update({"docs": "ПТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )

            bot.register_next_step_handler(message, seria_docs, data)
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
            bot.register_next_step_handler(message, data_docs, data)
    
    @bot.callback_query_handler(func=lambda call: call.data in ["Reco", "Ugo", "SOGAZ", "Ingo", "Ros", "Maks", "Energo", "Sovko", "other"])
    def callback_insurance(call):
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        if call.data == "SOGAZ":
            data.update({"insurance": 'АО "Согаз"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
  
            bot.register_next_step_handler(message, seria_insurance, data)
        elif call.data == "Reco":
            data.update({"insurance": 'САО "Ресо-Гарантия"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
            bot.register_next_step_handler(message, seria_insurance, data)
        elif call.data == "Ugo":
            data.update({"insurance": 'АО "ГСК "Югория"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
            bot.register_next_step_handler(message, seria_insurance, data)
        elif call.data == "Ingo":
            data.update({"insurance": 'СПАО "Ингосстрах"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
  
            bot.register_next_step_handler(message, seria_insurance, data)
        elif call.data == "Ros":
            data.update({"insurance": 'ПАО СК "Росгосстрах"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
  
            bot.register_next_step_handler(message, seria_insurance, data)
        elif call.data == "Maks":
            data.update({"insurance": 'АО "Макс"'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
  
            bot.register_next_step_handler(message, seria_insurance, data)
        elif call.data == "Energo":
            data.update({"insurance": 'ПАО «САК «Энергогарант»'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
  
            bot.register_next_step_handler(message, seria_insurance, data)
        elif call.data == "Sovko":
            data.update({"insurance": 'АО «Совкомбанк страхование»'})
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=None
            ) 
  
            bot.register_next_step_handler(message, seria_insurance, data)
        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название страховой компании",
            reply_markup=None
            )
            bot.register_next_step_handler(message, other_insurance, data) 

    @bot.callback_query_handler(func=lambda call: call.data in ["sud1", "sud2", "sud3", "sud4", "sud5", "sud6", "sudOther"])
    def callback_insurance(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "sud1":
            data.update({"sud": 'Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            bot.register_next_step_handler(message, gos_money, data)
        elif call.data == "sud2":
            data.update({"sud": 'Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            bot.register_next_step_handler(message, gos_money, data)
        elif call.data == "sud3":
            data.update({"sud": 'Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            bot.register_next_step_handler(message, gos_money, data)
        elif call.data == "sud4":
            data.update({"sud": 'Томский областной суд, 634003, г. Томск, пер. Макушина, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            bot.register_next_step_handler(message, gos_money, data)
        elif call.data == "sud5":
            data.update({"sud": 'Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            bot.register_next_step_handler(message, gos_money, data)
        elif call.data == "sud6":
            data.update({"sud": 'Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            bot.register_next_step_handler(message, gos_money, data)
        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название суда",
            reply_markup=None
            )
            bot.register_next_step_handler(message, sud_other, data) 
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
                data.update({"ombuc": "No"})

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
                                        data["fio"]+"\\"+data["fio"]+"_заявление_о_выдаче_копии_справкиГИБДД.docx")
                replace_words_in_word(["{{ Страховая }}","{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                    "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                    "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                    "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}"],
                                    [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                        str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                        str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                        str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"])],
                                        "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Заявление о выдаче документов от страховой.docx",
                                        data["fio"]+"\\"+data["fio"]+"_заявление_о_выдаче_док_страх.docx")
                user_id = call.message.from_user.id
                user_temp_data[user_id] = data
                 
                keyboard = types.InlineKeyboardMarkup()

                btn1 = types.InlineKeyboardButton("Да", callback_data="YesNOOSAGO")
                btn2 = types.InlineKeyboardButton("Нет", callback_data="NoNOOSAGO")
                keyboard.add(btn1, btn2)
                bot.send_message(call.message.chat.id, text="Данные сохранены, отправить вам документы?", reply_markup=keyboard)
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
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО представителя в формате Иванов Иван Иванович",
            reply_markup=None
            )
            bot.register_next_step_handler(message, fio_not, data)
    @bot.callback_query_handler(func=lambda call: call.data in ["number_rogalev","number_not_other"])
    def callback_number_notarius(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "number_rogalev":
            data.update({"number_not": '+79966368941'})
            data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
            data.update({"analis_ins": "Yes"})
            data.update({"pret_sto": "Yes"})
            print(data)
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            print(data)
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
                                        "Шаблоны\\1. ДТП\\1. На ремонт\Выплата без согласования\\6. Претензия в страховую Выплата без согласования.docx",
                                        data["fio"]+"\\"+data["fio"]+"_претензия_в_страховую.docx")
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
                                        "Шаблоны\\1. ДТП\\1. На ремонт\Ремонт не произведен СТО отказала\\7. Претензия в страховую СТО отказала.docx",
                                        data["fio"]+"\\"+data["fio"]+"_претензия_в_страховую.docx")
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
                                        data["fio"]+"\\"+data["fio"]+"_претензия_в_страховую.docx")
                
            user_id = call.message.from_user.id
            user_temp_data[user_id] = data
             
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
            keyboard.add(btn1, btn2)
            bot.send_message(call.message.chat.id, text="Данные сохранены, отправить вам документы?", reply_markup=keyboard)



        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер телефона представителя в формате +79XXXXXXXXX",
            reply_markup=None
            )
            bot.register_next_step_handler(message, number_not, data)
    @bot.callback_query_handler(func=lambda call: call.data in ["Yes", "No"])
    def callback_send_docs(call):

        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
        if call.data == "Yes":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"] + "_обложка.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_юр_договор.docx", "name": "Юридический договор"},
            {"path": data["fio"]+"\\"+data["fio"] + "_заявление_в_страховую.docx", "name": "Заявление в страховую"}
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
    @bot.callback_query_handler(func=lambda call: call.data in ["YesNOOSAGO", "NoNOOSAGO"])
    def callback_send_docs4(call):

        user_id = call.message.from_user.id 
        data = user_temp_data[user_id]
         

        if call.data == "YesNOOSAGO":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"] + "_заявление_о_выдаче_копии_справкиГИБДД.docx", "name": "Обложка дела"},
            {"path": data["fio"]+"\\"+data["fio"] + "_заявление_о_выдаче_док_страх.docx", "name": "Юридический договор"},
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
    @bot.callback_query_handler(func=lambda call: call.data in ["YesPr", "NoPr"])
    def callback_send_docs_pret(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "YesPr":

            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_претензия_в_страховую.docx", "name": "Обложка дела"},
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
    @bot.callback_query_handler(func=lambda call: call.data in ["dopOsmYes", "dopOsmNo"])
    def callback_send_docs_pret(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "dopOsmYes":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_Заявление_о_доп_осмотра.docx", "name": "Обложка дела"},
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
    @bot.callback_query_handler(func=lambda call: call.data in ["ZaprInsYes", "ZaprInsNo"])
    def callback_send_docs_o(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         

        if call.data == "ZaprInsYes":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_запрос_в_страховую.docx", "name": "Обложка дела"},
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
        btn2 = types.InlineKeyboardButton("Главное меню", callback_data="btn_main_menu")
        keyboard.add(btn1)
        keyboard.add(btn2)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Анализируем ответ от страховой\nПродолжить или вернуться в главное меню?",
            reply_markup=keyboard
        ) 

    @bot.callback_query_handler(func=lambda call: call.data in ["YesO", "NoO"])
    def callback_send_docs_o2(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        if call.data == "YesO":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_заявление_фин_обуцмену.docx", "name": "Обложка дела"},
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
    @bot.callback_query_handler(func=lambda call: call.data in ["vibor2STOYes", "vibor2STONo"])
    def callback_STOZayav(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "vibor2STOYes":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_Заявление_СТО_отказ.docx", "name": "Обложка дела"},
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
    @bot.callback_query_handler(func=lambda call: call.data in ["YesIsk", "NoIsk"])
    def callback_send_docs_o3(call):
         
        user_id = call.message.from_user.id
        
        data = user_temp_data[user_id]
         
          
        if call.data == "YesIsk":
            documents = [
            {"path": data["fio"]+"\\"+data["fio"]+"_Исковое_заявление.docx", "name": "Обложка дела"},
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
    @bot.callback_query_handler(func=lambda call: call.data in ["dopOsm"])
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
            text="Введите входящий номер в страховую",
            reply_markup=None
        )  
        bot.register_next_step_handler(message, Nv_ins, data)
         
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
        btn3 = types.InlineKeyboardButton("Нет ОСАГО", callback_data="NOOSAGO")
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
        bot.send_message(
                chat_id=call.message.chat.id,
                text="Деликт (у виновника нет ОСАГО)\nПодготовьте документы:\n1.Доверенность",
                reply_markup=None
            )
        message=bot.send_message(
                chat_id=call.message.chat.id,
                text="Введите номер доверенности",
                reply_markup=None
            )
        bot.register_next_step_handler(message, N_dov_not, data)

    @bot.callback_query_handler(func=lambda call: call.data in ["docsInsYes", "docsInsNo"])
    def callback_Zabr_insurance(call):
         
        user_id = call.message.from_user.id

        data = user_temp_data[user_id]
         

        if call.data == "docsInsYes":
            create_fio_data_file(data)
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                        "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                        "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                        "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}","{{ ФИОк }}", "{{ Телефон }}"],
                        [str(data['insurance']), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                        str(data["number_pasport"]), str(data["where_pasport"]),
                        str(data["when_pasport"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                        str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), 
                        str(data["marks_culp"]), str(data["number_auto_culp"]), str(data["fio_k"]), str(data["number"])],
                        "Шаблоны\\1. ДТП\\1. На ремонт\\5. Запрос в страховую о выдаче акта и расчёта.docx",
                            data["fio"]+"\\"+data["fio"]+"_запрос_в_страховую.docx")

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
            bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="""Выберите подходящий вариант:
1. Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось
2. Направление на ремонт.
            """,
            reply_markup=keyboard
            ) 
        elif data["answer_ins"]=="NO":
            bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось",
                    reply_markup=None
                    )
            data.update({"vibor": "vibor1"})
            bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Подготовьте документы:\n1. Нотариальная доверенность\n2. Ответ страховой\n3. Экспертное заключение\n4. Выплатное дело\n5. Платежное поручение",
                    reply_markup=None)
            if data["Nv_ins"] != None or data["Nv_ins"] != '':
                message = bot.send_message(call.message.chat.id, text="Введите дату экспертного заключения")
                bot.register_next_step_handler(message, date_exp, data)
            else:
                message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                bot.register_next_step_handler(message, Nv_ins, data)
                
        elif data["answer_ins"]=="NOOSAGO":
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("У виновника нет ОСАГО", callback_data=f"vibor3")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Деликт",
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
            bot.send_message(
            call.message.chat.id, 
            "СТО была заменена?", 
            reply_markup=keyboard
        )
        else:
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"vibor2")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"NOpr")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.send_message(
                call.message.chat.id, 
                "Удовлетворена ли претензия?", 
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data == "nextPrSto")
    def callback_pret_sto(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          

        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Нотариальную доверенность\n2. Отказ СТО",
                reply_markup=None
                )

        message = bot.send_message(
            call.message.chat.id, 
            "Введите дату отказа СТО", 
            reply_markup=None
        )

        bot.register_next_step_handler(message, data_otkaz_sto, data)
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

        bot.send_message(
            call.message.chat.id, 
            "Омбуцмен удовлетворил?", 
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
        start_handler(message)
    @bot.callback_query_handler(func=lambda call: call.data == "NOO")
    def callback_ombuc_viboryes(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          

        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Принятое заявление омбуцмену\n2. Ответ омбуцмена\n3. Независимую техническую экспертизу",
                reply_markup=None
                )


        message = bot.send_message(
            call.message.chat.id, 
            "Введите серию ВУ виновника", 
            reply_markup=None
        )
        bot.register_next_step_handler(message, seria_vu_culp, data)
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

        start_handler(message)
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
        start_handler(message)
    @bot.callback_query_handler(func=lambda call: call.data=="NOpr")
    def callback_pret_viboryes(call):
        """Продолжение заполнения данных клиента"""
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          

         
        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Принятая претензия\n2. Ответ на претензию",
                reply_markup=None
                )

        message = bot.send_message(
            call.message.chat.id, 
            "Введите дату принятия претензии в формате ДД.ММ.ГГГГ", 
            reply_markup=None
        )
        bot.register_next_step_handler(message, data_pret_prin, data)
    @bot.callback_query_handler(func=lambda call: call.data == "vibor1")
    def callback_vibor1(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        data.update({"vibor": str(call.data)})

        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Нотариальная доверенность\n2. Ответ страховой\n3. Экспертное заключение\n4. Выплатное дело\n5. Платежное поручение",
                reply_markup=None)
        if data["Nv_ins"] != None or data["Nv_ins"] != '':
            message = bot.send_message(call.message.chat.id, text="Введите дату экспертного заключения")
            bot.register_next_step_handler(message, date_exp, data)
        else:
            message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
            bot.register_next_step_handler(message, Nv_ins, data)
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
         
          
        data.update({"viborRem": str(call.data)})

        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Акт приема-передачи автомобиля\n2. Ответ страховой\n3. Экспертное заключение\n4. Направление на ремонт",
                reply_markup=None
                )
        if (data["Nv_ins"] == None) or (data["Nv_ins"] == ''):
            message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
            bot.register_next_step_handler(message, Nv_ins, data)
        else:
            message = bot.send_message(call.message.chat.id, text="Введите название СТО")
            bot.register_next_step_handler(message, name_sto, data)


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
        start_handler(message)
    @bot.callback_query_handler(func=lambda call: call.data =="viborRem3")
    def callback_viborRem3(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        data.update({"viborRem": str(call.data)})

        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Нотариальная доверенность\n2. Ответ страховой\n3. Экспертное заключение\4. Направление на ремонт",
                reply_markup=None
                )

        message = bot.send_message(call.message.chat.id, text="Введите название СТО")
        bot.register_next_step_handler(message, name_sto, data)

    @bot.callback_query_handler(func=lambda call: call.data=="IskNOOSAGO")
    def callback_viborRem1(call):
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
 

        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Подготовьте документы:\n1. Выплатное дело\n2. Платежное поручение\n3. Экспертиза",
                reply_markup=None
                )
        message = bot.send_message(call.message.chat.id, text="Введите название СТО")
        bot.register_next_step_handler(message, name_sto, data)
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
        start_handler(message)
    @bot.callback_query_handler(func=lambda call: call.data=="vibor1no")
    def callback_vibor1no(call): 
         
        user_id = call.message.from_user.id
        data = user_temp_data[user_id]
         
          
        data.update({"vibor1": "No"}) 
        bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="""Подготовьте документы:
                1. Нотариальная доверенность
                2. Ответ страховой
                3. Экспертное заключение""",
                reply_markup=None
                )
        message = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
        bot.register_next_step_handler(message, Nv_ins, data)

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
            bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 4 цифры".format(message.from_user))
            bot.register_next_step_handler(message, seria_pasport, data)
        else:
            data.update({"seria_pasport": int(message.text.replace(" ", ""))})
            bot.send_message(message.chat.id, text="Введите номер паспорта".format(message.from_user))
            bot.register_next_step_handler(message, number_pasport, data)

def number_pasport(message, data):
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр".format(message.from_user))
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
    if data['sobstvenik'] == 'Yes':
        data.update({"fio_sobs": "-"})
        data.update({"date_of_birth_sobs": "-"})
        bot.send_message(message.chat.id, text="Введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_dtp, data)
    else:
        bot.send_message(message.chat.id, text="Введите ФИО собственника в формате Иванов Иван Иванович".format(message.from_user))
        bot.register_next_step_handler(message, fio_sobs, data)

def fio_sobs(message, data):
    if len(message.text.split())<2:
            bot.send_message(message.chat.id, text="Неправильный формат ввода".format(message.from_user))
            bot.register_next_step_handler(message, fio_sobs, data)
    else:
        data.update({"fio_sobs": message.text})
        bot.send_message(message.chat.id, text="Введите дату рождения собственника в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_of_birth_sobs, data)

def date_of_birth_sobs(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth_sobs": message.text})
        bot.send_message(message.chat.id, text="Введите дату ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_dtp, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_of_birth_sobs, data)

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


def marks(message, data):
    data.update({"marks": message.text})
    bot.send_message(message.chat.id, text="Введите номер авто клиента".format(message.from_user))
    bot.register_next_step_handler(message, number_auto, data)
def number_auto(message, data):
    car_number = message.text.replace(" ", "").upper()  # Приводим к верхнему регистру
    pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
    
    # Проверяем, что исходный текст не содержит строчных букв
    original_text = message.text.replace(" ", "")
    has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
    
    if not has_lowercase and re.match(pattern, car_number) and len(car_number) in [8, 9]:
        data.update({"car_number": car_number})
        bot.send_message(message.chat.id, "Введите год выпуска авто клиента")
        bot.register_next_step_handler(message, year_auto, data)
    else:
        bot.send_message(
            message.chat.id,
            "Неправильный формат!\n"
            "Пример: А123БВ77 или А123БВ777\n"
            "Все буквы должны быть заглавными!"
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



def seria_docs(message, data):
    data.update({"seria_docs": message.text})
    bot.send_message(message.chat.id, text="Введите номер документа о регистрации ТС".format(message.from_user))
    bot.register_next_step_handler(message, number_docs, data)
def number_docs(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"number_docs": message.text})
        bot.send_message(
            message.chat.id,
            text="Введите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ"
        )
        bot.register_next_step_handler(message, data_docs, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Номер документа должен состоять только из цифр. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, number_docs, data) 

def data_docs(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_docs": message.text})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton('САО "Ресо-Гарантия"', callback_data="Reco")
        btn2 = types.InlineKeyboardButton('АО "ГСК "Югория"', callback_data="Ugo")
        btn3 = types.InlineKeyboardButton('АО "Согаз"', callback_data="SOGAZ")
        btn4 = types.InlineKeyboardButton('СПАО "Ингосстрах"', callback_data="Ingo")
        btn5 = types.InlineKeyboardButton('ПАО СК "Росгосстрах"', callback_data="Ros")
        btn6 = types.InlineKeyboardButton('АО "Макс"', callback_data="Maks")
        btn7 = types.InlineKeyboardButton('ПАО «САК «Энергогарант»', callback_data="Energo")
        btn8 = types.InlineKeyboardButton('АО «Совкомбанк страхование»', callback_data="Sovko")
        btn9 = types.InlineKeyboardButton('Другое', callback_data="other")
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
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, data_docs, data)
def other_insurance(message, data):
    data.update({"insurance": message.text})
    bot.send_message(message.chat.id, text="Введите серию страхового полиса".format(message.from_user))
    bot.register_next_step_handler(message, seria_insurance, data)
def seria_insurance(message, data):
    data.update({"seria_insurance": message.text})
    bot.send_message(message.chat.id, text="Введите номер страхового полиса".format(message.from_user))
    bot.register_next_step_handler(message, number_insurance, data)

def number_insurance(message, data):
    data.update({"number_insurance": message.text})
    bot.send_message(message.chat.id, text="Введите дату страхового полиса в формате ДД.ММ.ГГГГ".format(message.from_user))
    bot.register_next_step_handler(message, date_insurance, data)
def date_insurance(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_insurance": message.text})
        bot.send_message(message.chat.id, text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
        bot.register_next_step_handler(message, fio_culp, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_insurance, data)
def fio_culp(message, data):
    if len(message.text.split())<2:
            bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате Иванов Иван Иванович".format(message.from_user))
            bot.register_next_step_handler(message, fio_culp, data)
    else:
        data.update({"fio_culp": message.text})
        bot.send_message(message.chat.id, text="Введите марку, модель виновника ДТП".format(message.from_user))
        bot.register_next_step_handler(message, marks_culp, data)

def marks_culp(message, data):
    data.update({"marks_culp": message.text})
    bot.send_message(message.chat.id, text="Введите номер авто виновника ДТП".format(message.from_user))
    bot.register_next_step_handler(message, number_auto_culp, data)
def number_auto_culp(message, data):
    car_number = message.text.replace(" ", "").upper()  # Приводим к верхнему регистру
    pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
    
    # Проверяем, что исходный текст не содержит строчных букв
    original_text = message.text.replace(" ", "")
    has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
    
    if not has_lowercase and re.match(pattern, car_number) and len(car_number) in [8, 9]:
        data.update({"number_auto_culp": str(car_number)})
        bot.send_message(message.chat.id, "Введите банк получателя клиента")
        bot.register_next_step_handler(message, bank, data)
    else:
        bot.send_message(
            message.chat.id,
            "Неправильный формат!\n"
            "Пример: А123БВ77 или А123БВ777\n"
            "Все буквы должны быть заглавными!"
        )
        bot.register_next_step_handler(message, number_auto_culp, data)

    
def bank(message, data):
    data.update({"bank": message.text})
    bot.send_message(message.chat.id, text="Введите счет получателя".format(message.from_user))
    bot.register_next_step_handler(message, bank_account, data)

def bank_account(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"bank_account": message.text})
        bot.send_message(
            message.chat.id,
            text="Введите корреспондентский счет банка"
        )
        bot.register_next_step_handler(message, bank_account_corr, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Счет должен состоять только из цифр. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, bank_account, data) 
def bank_account_corr(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"bank_account_corr": message.text})
        bot.send_message(
            message.chat.id,
            text="Введите БИК банка"
        )
        bot.register_next_step_handler(message, BIK, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Счет должен состоять только из цифр. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, bank_account_corr, data)
def BIK(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"BIK": message.text})
        bot.send_message(
            message.chat.id,
            text="Введите ИНН банка"
        )
        bot.register_next_step_handler(message, INN, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! БИК должен состоять только из цифр. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, BIK, data)
def INN(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"year": list(str(datetime.now().year))[2]+list(str(datetime.now().year))[3]})
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
        data.update({"date_ins_pod": str(datetime.now().strftime("%d.%m.%Y"))})
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
        #Заявление в страховую
        if data["sobstvenik"] == "Yes" and data["ev"] == "Yes":
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3a Заявление в Страховую ФЛ собственник с эвакуатором.docx",
                                    data["fio"]+"\\"+data["fio"]+"_заявление_в_страховую.docx")
        elif data["sobstvenik"] == "Yes" and data["ev"] == "No":
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3b Заявление в Страховую ФЛ собственник без эвакуатора.docx",
                                    data["fio"]+"\\"+data["fio"]+"_заявление_в_страховую.docx")
        elif data["sobstvenik"] == "No" and data["ev"] == "Yes":
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}","{{ собТС_ФИО }}","{{ собДР }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y")), str(data["fio_sobs"]), str(data["date_of_birth_sobs"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3c Заявление в Страховую ФЛ водитель с эвакуатором.docx",
                                    data["fio"]+"\\"+data["fio"]+"_заявление_в_страховую.docx")
        else:
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}","{{ собТС_ФИО }}","{{ собДР }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y")), str(data["fio_sobs"]), str(data["date_of_birth_sobs"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3d Заявление в Страховую ФЛ водитель без эвакуатора.docx",
                                    data["fio"]+"\\"+data["fio"]+"_заявление_в_страховую.docx")
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="Yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="No")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)        
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! БИК должен состоять только из цифр. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, INN, data)   


def date_coin_ins(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_coin_ins": message.text})
        bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС".format(message.from_user))
        bot.register_next_step_handler(message, Na_ins, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_coin_ins, data)

def Nv_ins(message, data):
    data.update({"Nv_ins": message.text})
    bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС".format(message.from_user))
    bot.register_next_step_handler(message, Na_ins, data)
def Na_ins(message, data):
    data.update({"Na_ins": message.text})
    bot.send_message(message.chat.id, text="Введите дату акта осмотра ТС".format(message.from_user))
    bot.register_next_step_handler(message, date_Na_ins, data)
def date_Na_ins(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_Na_ins": message.text})
        if data["viborRem"] == "viborRem3":
            bot.send_message(message.chat.id, text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
            bot.register_next_step_handler(message, date_exp, data)
        elif data["viborRem"] == "viborRem1":
            bot.send_message(message.chat.id, text="Введите название СТО".format(message.from_user))
            bot.register_next_step_handler(message, name_sto, data)
        elif data["dop_osm"] == "Yes":
            bot.send_message(message.chat.id, text="Введите адрес своего СТО".format(message.from_user))
            bot.register_next_step_handler(message, address_sto_main, data)
        else:
            bot.send_message(message.chat.id, text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
            bot.register_next_step_handler(message, date_exp, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_Na_ins, data)
def date_exp(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_exp": message.text})
        bot.send_message(message.chat.id, text="Введите организацию, сделавшую экспертизу".format(message.from_user))
        bot.register_next_step_handler(message, org_exp, data)

    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_exp, data)

def org_exp(message, data):
    data.update({"org_exp": message.text})
    bot.send_message(message.chat.id, text="Введите цену по экспертизе без учета износа".format(message.from_user))
    bot.register_next_step_handler(message, coin_exp, data)
def coin_exp(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_exp": message.text})
        bot.send_message(
            message.chat.id,
            text="Введите цену по экспертизе с учетом износа"
        )
        bot.register_next_step_handler(message, coin_exp_izn, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Цена должна состоять только из цифр в рублях. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, coin_exp, data)
def coin_exp_izn(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_exp_izn": message.text})
        bot.send_message(
            message.chat.id,
            text="Введите сумму выплаты по ОСАГО"
        )
        bot.register_next_step_handler(message, coin_osago, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Цена должна состоять только из цифр в рублях. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, coin_exp_izn, data)
def coin_osago(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_osago": message.text})
        if data["answer_ins"] =="NOOSAGO":
            bot.send_message(
            message.chat.id,
            text="Введите серию ВУ виновника ДТП"
            )
            bot.register_next_step_handler(message, seria_vu_culp, data)
        elif data["viborRem"] == "viborRem1":
            bot.send_message(
            message.chat.id,
            text="Введите дату передачи авто на СТО"
            )
            bot.register_next_step_handler(message, date_sto, data)
        else:
            bot.send_message(
                message.chat.id,
                text="Введите стоимость услуг нотариуса"
            )
            bot.register_next_step_handler(message, coin_not, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Цена должна состоять только из цифр в рублях. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, coin_osago, data)

def data_otkaz_sto(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_otkaz_sto": message.text})
        bot.send_message(message.chat.id, text="Введите стоимость услуг нотариуса".format(message.from_user))
        bot.register_next_step_handler(message, coin_not, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, data_otkaz_sto, data)
def coin_not(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"coin_not": message.text})
        bot.send_message(
            message.chat.id,
            text="Введите номер доверенности"
        )
        bot.register_next_step_handler(message, N_dov_not, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Цена должна состоять только из цифр в рублях. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, coin_not, data)

def N_dov_not(message, data):
    data.update({"N_dov_not": message.text})
    bot.send_message(message.chat.id, text="Введите дату доверенности".format(message.from_user))
    bot.register_next_step_handler(message, data_dov_not, data)
def data_dov_not(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_dov_not": message.text})
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Рогалев Семен Иннокентьевич", callback_data="not_rogalev")
        btn2 = types.InlineKeyboardButton("Другое", callback_data="not_other")
        keyboard.add(btn1)
        keyboard.add(btn2)
        bot.send_message(message.chat.id, text="Выберите ФИО представителя".format(message.from_user), reply_markup = keyboard)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, data_dov_not, data)
def fio_not(message, data):
    if len(message.text.split())<2:
            bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате Иванов Иван Иванович".format(message.from_user))
            bot.register_next_step_handler(message, fio_not, data)
    else:
        data.update({"fio_not": message.text})
        
        if data["answer_ins"] == "NOOSAGO":
            data.update({"analis_ins": "Yes"})
            data.update({"pret_sto": "No"})
            data.update({"pret": "No"})
            data.update({"ombuc": "No"})

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
                                    data["fio"]+"\\"+data["fio"]+"_заявление_о_выдаче_копии_справкиГИБДД.docx")
            replace_words_in_word(["{{ Страховая }}","{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ NДоверенности }}",
                                "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"])],
                                    "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Заявление о выдаче документов от страховой.docx",
                                    data["fio"]+"\\"+data["fio"]+"_заявление_о_выдаче_док_страх.docx")
            user_id = message.from_user.id
            user_temp_data[user_id] = data
             
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("Да", callback_data="YesNOOSAGO")
            btn2 = types.InlineKeyboardButton("Нет", callback_data="NoNOOSAGO")
            keyboard.add(btn1, btn2)
            bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)
        else:
            user_id = message.from_user.id
            user_temp_data[user_id] = data
             
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("+79966368941", callback_data="number_rogalev")
            btn2 = types.InlineKeyboardButton("Другое", callback_data="number_not_other")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text="Выберите номер телефона представителя",
            reply_markup=keyboard
            ) 


def number_not(message, data):
    if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате +79XXXXXXXXX".format(message.from_user))
        bot.register_next_step_handler(message, number_not, data)
    else:
        data.update({"number_not": message.text})
        data.update({"date_pret": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"analis_ins": "Yes"})
        data.update({"pret_sto": "Yes"})
        print(data)
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        print(data)
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
                                    "Шаблоны\\1. ДТП\\1. На ремонт\Выплата без согласования\\6. Претензия в страховую Выплата без согласования.docx",
                                    data["fio"]+"\\"+data["fio"]+"_претензия_в_страховую.docx")
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
                                    "Шаблоны\\1. ДТП\\1. На ремонт\Ремонт не произведен СТО отказала\\7. Претензия в страховую СТО отказала.docx",
                                    data["fio"]+"\\"+data["fio"]+"_претензия_в_страховую.docx")
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
                                    data["fio"]+"\\"+data["fio"]+"_претензия_в_страховую.docx")
            
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="YesPr")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="NoPr")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)


def time_sto(message, data):
    if len(message.text) != 5 or message.text.count(':') != 1:
        bot.send_message(
            message.chat.id,
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        bot.register_next_step_handler(message, time_sto, data)
        return
    try:
 
        datetime.strptime(message.text, "%H:%M")

        data.update({"time_sto": message.text})
        if data["viborRem"]=="viborRem3":
            bot.send_message(message.chat.id, "Введите город СТО")
            bot.register_next_step_handler(message, city_sto, data) 
        else:
            bot.send_message(message.chat.id, "Введите адрес СТО")
            bot.register_next_step_handler(message, address_sto, data)    
    except ValueError:
        bot.send_message(
            message.chat.id, 
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        bot.register_next_step_handler(message, time_sto, data)



def data_pret_prin(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_pret_prin": message.text})
        if data["viborRem"]=="viborRem1":
            bot.send_message(message.chat.id, text="Введите номер принятой претензии".format(message.from_user))
            bot.register_next_step_handler(message, N_pret_prin, data)
        else:
            bot.send_message(message.chat.id, text="Введите дату ответа на претензию в формате ДД.ММ.ГГГГ".format(message.from_user))
            bot.register_next_step_handler(message, data_pret_otv, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, data_pret_prin, data)
def data_pret_otv(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_pret_otv": message.text})
        bot.send_message(message.chat.id, text="Введите номер принятой претензии".format(message.from_user))
        bot.register_next_step_handler(message, N_pret_prin, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, data_pret_otv, data)
def N_pret_prin(message, data):
    data.update({"N_pret_prin": message.text})
    data.update({"pret": "Yes"})
    data.update({"date_ombuc": str(datetime.now().strftime("%d.%m.%Y"))})
    print(data)
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
                                data["fio"]+"\\"+data["fio"]+"_заявление_фин_обуцмену.docx")
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
                            data["fio"]+"\\"+data["fio"]+"_заявление_фин_обуцмену.docx")
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
                            data["fio"]+"\\"+data["fio"]+"_заявление_фин_обуцмену.docx")
    user_id = message.from_user.id
    user_temp_data[user_id] = data
     
    keyboard = types.InlineKeyboardMarkup()

    btn1 = types.InlineKeyboardButton("Да", callback_data="YesO")
    btn2 = types.InlineKeyboardButton("Нет", callback_data="NoO")
    keyboard.add(btn1, btn2)
    bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)


def seria_vu_culp(message, data):
    data.update({"seria_vu_culp": message.text})
    bot.send_message(message.chat.id, text="Введите номер ВУ виновника".format(message.from_user))
    bot.register_next_step_handler(message, number_vu_culp, data)
def number_vu_culp(message, data):
    data.update({"number_vu_culp": message.text})
    bot.send_message(message.chat.id, text="Введите дату ВУ виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
    bot.register_next_step_handler(message, data_vu_culp, data)
def data_vu_culp(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"data_vu_culp": message.text})
        bot.send_message(message.chat.id, text="Введите дату рождения виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_of_birth_culp, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, data_vu_culp, data)
def date_of_birth_culp(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_of_birth_culp": message.text})
        bot.send_message(message.chat.id, text="Введите почтовый индекс виновника".format(message.from_user))
        bot.register_next_step_handler(message, index_culp, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_of_birth_culp, data)
def index_culp(message, data):
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр".format(message.from_user))
        bot.register_next_step_handler(message, index_culp, data)
    else:
        data.update({"index_culp": int(message.text.replace(" ", ""))})
        bot.send_message(message.chat.id, text="Введите адрес виновника".format(message.from_user))
        bot.register_next_step_handler(message, address_culp, data)  
def address_culp(message, data):
    data.update({"address_culp": message.text})
    bot.send_message(message.chat.id, text="Введите номер телефона виновника в формате +79XXXXXXXXX".format(message.from_user))
    bot.register_next_step_handler(message, number_culp, data)
def number_culp(message, data):
    if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате +79XXXXXXXXX".format(message.from_user))
        bot.register_next_step_handler(message, number_culp, data)
    else:
        data.update({"number_culp": message.text})
        bot.send_message(message.chat.id, text="Введине номер выплатного дела".format(message.from_user))
        bot.register_next_step_handler(message, N_viplat_work, data)
def N_viplat_work(message, data):
    data.update({"N_viplat_work": message.text})
    bot.send_message(message.chat.id, text="Введите дату выплатного дела в формате ДД.ММ.ГГГГ".format(message.from_user))
    bot.register_next_step_handler(message, date_viplat_work, data)
def date_viplat_work(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_viplat_work": message.text})
        bot.send_message(message.chat.id, text="Введите номер платежного поручения".format(message.from_user))
        bot.register_next_step_handler(message, N_plat_por, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_viplat_work, data)
def N_plat_por(message, data):
    data.update({"N_plat_por": message.text})
    bot.send_message(message.chat.id, text="Введите дату платежного поручения в формате ДД.ММ.ГГГГ".format(message.from_user))
    bot.register_next_step_handler(message, date_plat_por, data)
def date_plat_por(message, data):
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
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_plat_por, data)
def sud_other(message, data):
    data.update({"sud": message.text})
    bot.send_message(message.chat.id, text="Введите стоимость государственной пошлины".format(message.from_user))
    bot.register_next_step_handler(message, gos_money, data)
def gos_money(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"gos_money": message.text})
        bot.send_message(message.chat.id, text="Введите дату извещения о ДТП".format(message.from_user))
        bot.register_next_step_handler(message, date_izvesh_dtp, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! Стоимость должна состоять только из цифр в рублях, например: 50000. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, gos_money, data)

def date_izvesh_dtp(message, data):
    #try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_izvesh_dtp": message.text})
        data.update({"ombuc": "Yes"})
        data.update({"date_isk": str(datetime.now().strftime("%d.%m.%Y"))})
        data.update({"Done": "Yes"})
        print(data)
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
                                data["fio"]+"\\"+data["fio"]+"_Исковое_заявление.docx")


        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="YesIsk")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="NoIsk")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)
    # except ValueError:
    #     bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
    #     bot.register_next_step_handler(message, date_izvesh_dtp, data)

def name_sto(message, data):
    data.update({"name_sto": message.text})
    bot.send_message(message.chat.id, text="Введите ИНН СТО".format(message.from_user))
    bot.register_next_step_handler(message, inn_sto, data)
def inn_sto(message, data):
    if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
        data.update({"inn_sto": message.text})
        bot.send_message(message.chat.id, text="Введите индекс СТО".format(message.from_user))
        bot.register_next_step_handler(message, index_sto, data)
    else:
        bot.send_message(
            message.chat.id,
            text="Неправильный формат! ИНН должен состоять только из цифр. Попробуйте ещё раз."
        )
        bot.register_next_step_handler(message, inn_sto, data)
def index_sto(message, data):
    if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
        bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр".format(message.from_user))
        bot.register_next_step_handler(message, index_sto, data)
    else:
        data.update({"index_sto": message.text})
        bot.send_message(message.chat.id, text="Введите адрес СТО".format(message.from_user))
        bot.register_next_step_handler(message, address_sto, data) 
def address_sto(message, data):
    data.update({"address_sto": message.text})
    bot.send_message(message.chat.id, text="Введите город СТО".format(message.from_user))
    bot.register_next_step_handler(message, city_sto, data)
def city_sto(message, data):
    data.update({"city_sto": message.text})
    bot.send_message(message.chat.id, "Введите номер направления СТО")
    bot.register_next_step_handler(message, N_sto, data) 
def N_sto(message, data):
    data.update({"N_sto": message.text})
    bot.send_message(message.chat.id, text="Введите дату направления на СТО".format(message.from_user))
    bot.register_next_step_handler(message, date_napr_sto, data)
def date_napr_sto(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_napr_sto": message.text})
        if data["viborRem"]=="viborRem3":
            bot.send_message(message.chat.id, text="Введите входящий номер в страховую".format(message.from_user))
            bot.register_next_step_handler(message, Nv_ins, data)
        else:
            bot.send_message(message.chat.id, text="Введите дату экспертного заключения".format(message.from_user))
            bot.register_next_step_handler(message, date_exp, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_napr_sto, data)
def date_sto(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_sto": message.text})
        data.update({"date_zayav_sto": str(datetime.now().strftime("%d.%m.%Y"))})

        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
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
                                data["fio"]+"\\"+data["fio"]+"_Заявление_СТО_отказ.docx")
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="vibor2STOYes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="vibor2STONo")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)

    
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_sto, data)

def address_sto_main(message, data):
    data.update({"address_sto_main": message.text})
    bot.send_message(message.chat.id, text="Введите дату записи в свое СТО".format(message.from_user))
    bot.register_next_step_handler(message, date_sto_main, data)
def date_sto_main(message, data):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        data.update({"date_sto_main": message.text})
        bot.send_message(message.chat.id, text="Введите время записи в свое СТО".format(message.from_user))
        bot.register_next_step_handler(message, time_sto_main, data)
    except ValueError:
        bot.send_message(message.chat.id, text="Неправильный формат ввода, введите в формате ДД.ММ.ГГГГ".format(message.from_user))
        bot.register_next_step_handler(message, date_sto_main, data)
def time_sto_main(message, data):
    if len(message.text) != 5 or message.text.count(':') != 1:
        bot.send_message(
            message.chat.id,
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        bot.register_next_step_handler(message, time_sto_main, data)
        return
    try:
 
        datetime.strptime(message.text, "%H:%M")

        data.update({"time_sto_main": message.text})
        data.update({"dop_osm": "Yes"})
        data.update({"data_dop_osm": str(datetime.now().strftime("%d.%m.%Y"))})

        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                            "{{ Паспорт_когда }}", "{{ Nакта_осмотра }}", "{{ Дата }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                            "{{ Адрес_ДТП }}", "{{ Дата_осмотра }}", "{{ Организация }}", "{{ Дата_экспертизы }}",
                            "{{ Без_учета_износа }}", "{{ Дата_свое_СТО }}","{{ Время_свое_СТО }}","{{ Адрес_свое_СТО }}", "{{ Телефон }}", "{{ ФИОк }}",
                            "{{ Дата_заявления_доп_осмотр }}"],
                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["Na_ins"]), str(data["date_ins"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                str(data["date_Na_ins"]), str(data["org_exp"]), str(data["date_exp"]), str(data["coin_exp"]), str(data["date_sto_main"]),
                                str(data["time_sto_main"]), str(data["address_sto_main"]), str(data["number"]),str(data["fio_k"]),
                                str(data["data_dop_osm"])],
                                "Шаблоны\\1. ДТП\\1. На ремонт\\4. Заявление о проведении дополнительного осмотра автомобиля.docx",
                                data["fio"]+"\\"+data["fio"]+"_Заявление_о_доп_осмотра.docx")
        user_id = message.from_user.id
        user_temp_data[user_id] = data
         
        keyboard = types.InlineKeyboardMarkup()

        btn1 = types.InlineKeyboardButton("Да", callback_data="dopOsmYes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="dopOsmNo")
        keyboard.add(btn1, btn2)
        bot.send_message(message.chat.id, text="Данные сохранены, отправить вам документы?".format(message.from_user), reply_markup=keyboard)
    except ValueError:
        bot.send_message(
            message.chat.id, 
            "Неправильный формат времени!\n"
            "Введите время в формате ЧЧ:ММ (например: 14:30):"
        )
        bot.register_next_step_handler(message, time_sto_main, data)