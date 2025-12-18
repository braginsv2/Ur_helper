from telebot import types
import re
import json
import time
from datetime import datetime, timedelta
from database import (
    DatabaseManager,
    save_client_to_db_with_id_new,
    get_admin_from_db_by_user_id,
    search_clients_by_fio_in_db,
    get_client_from_db_by_client_id
)
from word_utils import create_fio_data_file, replace_words_in_word, get_next_business_date
import threading
from functools import wraps

active_callbacks = {}
callback_lock = threading.Lock()
db = DatabaseManager()

def setup_podal_z_handlers(bot, user_temp_data):
    def prevent_double_click(timeout=2.0):
        """
        Декоратор для предотвращения повторных нажатий на inline-кнопки
        timeout - время в секундах, в течение которого повторные нажатия игнорируются
        """
        def decorator(func):
            @wraps(func)
            def wrapper(call):
                user_id = call.from_user.id
                callback_data = call.data
                
                # Создаем уникальный ключ для этой комбинации пользователь+кнопка
                key = f"{user_id}_{callback_data}"
                
                with callback_lock:
                    current_time = time.time()
                    
                    # Проверяем, не обрабатывается ли уже этот callback
                    if key in active_callbacks:
                        last_time = active_callbacks[key]
                        if current_time - last_time < timeout:
                            # Слишком быстрое повторное нажатие - игнорируем
                            bot.answer_callback_query(
                                call.id, 
                                "⏳ Пожалуйста, подождите...", 
                                show_alert=False
                            )
                            return
                    
                    # Отмечаем начало обработки
                    active_callbacks[key] = current_time
                
                try:
                    # Сразу отвечаем на callback, чтобы убрать "часики"
                    bot.answer_callback_query(call.id)
                    
                    # Выполняем основную функцию
                    return func(call)
                finally:
                    # Через timeout секунд разрешаем повторное нажатие
                    def cleanup():
                        time.sleep(timeout)
                        with callback_lock:
                            if key in active_callbacks:
                                del active_callbacks[key]
                    
                    threading.Thread(target=cleanup, daemon=True).start()
            
            return wrapper
        return decorator
    @bot.callback_query_handler(func=lambda call: call.data.startswith("podal_rem_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_rem(call):
        client_id = call.data.replace("podal_rem_", "")
        user_id = call.from_user.id
        contract = get_client_from_db_by_client_id(client_id)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            if contract.get('data_json'):
                contract_data = json.loads(contract.get('data_json', '{}'))
                data = {**contract, **contract_data}
            else:
                data = contract
        except:
            data = contract
        if data.get('docs', '') == '':
            data.update({'docs': 'СТС'})
            data.update({'dkp': '-'})
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id].update(data)
        
        try:
            with open(f"clients/{data['client_id']}/Документы/{data.get('docs', 'СТС')}.pdf", 'rb') as document_file:
                msg = bot.send_document(call.message.chat.id, document_file)   
                user_temp_data[user_id]['message_id'] = msg.message_id
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, f"Файл не найден")

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_podal_continue_documents_{data['client_id']}"))
        msg = bot.send_message(
            chat_id=call.message.chat.id,
            text=f"Введите серию документа {data.get('docs', 'СТС')}",
            reply_markup = keyboard
        )
        bot.register_next_step_handler(msg, process_client_seria_docs, data['client_id'], msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("podal_viplata_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_viplata(call):
        client_id = call.data.replace("podal_viplata_", "")
        user_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("💰 Выплатили", callback_data=f"podal_viplatayes_{client_id}")
        btn_no = types.InlineKeyboardButton("🛠️ Не выплатили", callback_data=f"podal_viplatano_{client_id}")
        keyboard.add(btn_yes, btn_no)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id = call.message.message_id,
            text = f"Выберите из предложенных вариантов.",
            reply_markup = keyboard
        ) 
    @bot.callback_query_handler(func=lambda call: call.data.startswith("podal_viplatayes_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_viplatayes(call):
        client_id = call.data.replace("podal_viplatayes_", "")
        user_id = call.from_user.id
        keyboard = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("Деликт", callback_data=f"delict_{client_id}")
        btn_no = types.InlineKeyboardButton("Цессия", callback_data=f"ceccia_{client_id}")
        btn_no2 = types.InlineKeyboardButton("Заявление об изменении способа возмещения", callback_data=f"podal_izmena_{client_id}")
        keyboard.add(btn_yes)
        keyboard.add(btn_no)
        keyboard.add(btn_no2)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id = call.message.message_id,
            text = f"Выберите из предложенных вариантов.",
            reply_markup = keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("podal_izmena_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_izmena(call):
        client_id = call.data.replace("podal_izmena_", "")
        user_id = call.from_user.id
        contract = get_client_from_db_by_client_id(client_id)
        
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            if contract.get('data_json'):
                contract_data = json.loads(contract.get('data_json', '{}'))
                data = {**contract, **contract_data}
            else:
                data = contract
        except:
            data = contract
        data.update({'viborRem': 'Заявление'})
        if data.get('docs', '') == '':
            data.update({'docs': 'СТС'})
            data.update({'dkp': '-'})
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите серию документа {data.get('docs', 'СТС')}"
        )
        bot.register_next_step_handler(msg, process_client_seria_docs, data['client_id'], msg.message_id, data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("delict_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_rem(call):
        client_id = call.data.replace("delict_", "")
        user_id = call.from_user.id
        contract = get_client_from_db_by_client_id(client_id)
        
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            if contract.get('data_json'):
                contract_data = json.loads(contract.get('data_json', '{}'))
                data = {**contract, **contract_data}
            else:
                data = contract
        except:
            data = contract
        data.update({'status': 'Деликт'})
        if data.get('docs', '') == '':
            data.update({'docs': 'СТС'})
            data.update({'dkp': '-'})
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\n"
                 f"В случае максимальной выплаты по ОСАГО либо отсутствия ОСАГО у Виновника ДТП разница фактического ущерба и компенсационной выплаты взыскивается с Виновника ДТП\n"
                 f"Примерная дата завершения дела (дата через 90 дней)\n\nВведите серию документа {data.get('docs', 'СТС')}"
        )
        bot.register_next_step_handler(msg, process_client_seria_docs, data['client_id'], msg.message_id, data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("ceccia_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_rem(call):
        client_id = call.data.replace("ceccia_", "")
        user_id = call.from_user.id
        contract = get_client_from_db_by_client_id(client_id)
        
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            if contract.get('data_json'):
                contract_data = json.loads(contract.get('data_json', '{}'))
                data = {**contract, **contract_data}
            else:
                data = contract
        except:
            data = contract
        data.update({'viborRem': 'Цессия'})
        data.update({'status': 'Составлено заявление о выдаче документов ГИБДД'})
        if data.get('docs', '') == '':
            data.update({'docs': 'СТС'})
            data.update({'dkp': '-'})
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text= f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\n"
                  f"Цессия - передача права требования компенсации с Виновника ДТП третьему лицу (продажа долга)\n\nВведите серию документа {data.get('docs', 'СТС')}"
        )
        bot.register_next_step_handler(msg, process_client_seria_docs, data['client_id'], msg.message_id, data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("podal_viplatano_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_rem(call):
        client_id = call.data.replace("podal_viplatano_", "")
        user_id = call.from_user.id
        contract = get_client_from_db_by_client_id(client_id)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            if contract.get('data_json'):
                contract_data = json.loads(contract.get('data_json', '{}'))
                data = {**contract, **contract_data}
            else:
                data = contract
        except:
            data = contract
        data.update({'viborRem': 'no_viplatily'})
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id].update(data)
        if data.get('docs', '') == '':
            data.update({'docs': 'СТС'})
            data.update({'dkp': '-'})
        try:
            with open(f"clients/{data['client_id']}/Документы/{data.get('docs', 'СТС')}.pdf", 'rb') as document_file:
                msg = bot.send_document(call.message.chat.id, document_file)   
                user_temp_data[user_id]['message_id'] = msg.message_id
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, f"Файл {data.get('docs', 'СТС')}.pdf не найден")
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_podal_continue_documents_{data['client_id']}"))
        msg = bot.send_message(
            chat_id=call.message.chat.id,
            text=f"Введите серию документа {data.get('docs', 'СТС')}",
            reply_markup = keyboard
        )
        bot.register_next_step_handler(msg, process_client_seria_docs, data['client_id'], msg.message_id, data)
   
    def process_client_seria_docs(message, client_id, user_message_id, data):
        """Обработка серии документа"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['seria_docs'] = message.text.strip()
        user_temp_data[user_id].update(data)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_seria_docs"))

        msg = bot.send_message(message.chat.id, f"Введите номер документа {data.get('docs', 'СТС')}", reply_markup = keyboard)
        bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_seria_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_seria_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_podal_continue_documents_{data['client_id']}"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите серию документа {data.get('docs', 'СТС')}",
            reply_markup = keyboard
        )
        bot.register_next_step_handler(msg, process_client_seria_docs, data['client_id'], msg.message_id, data)

    def process_client_number_docs(message, client_id, user_message_id, data):
        """Обработка номера документа"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit():
            data['number_docs'] = message.text.strip()
            user_temp_data[user_id].update(data)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_number_docs"))
            msg = bot.send_message(
                message.chat.id,
                f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ:",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
        else:
            user_temp_data[user_id].update(data)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_seria_docs"))
            msg = bot.send_message(
                message.chat.id,
                f"❌ Неправильный формат!\nВведите номер документа {data.get('docs', 'СТС')} (только цифры):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_number_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_number_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_seria_docs"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите номер документа {data.get('docs', 'СТС')}",
            reply_markup = keyboard
        )
        bot.register_next_step_handler(msg, process_client_number_docs, data['client_id'], msg.message_id, data)
    
    def process_client_data_docs(message, client_id, user_message_id, data):
        """Обработка даты выдачи документа"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data['data_docs'] = message.text.strip()
            user_temp_data[user_id].update(data)
            try:
                bot.delete_message(message.chat.id, user_temp_data[user_id]['message_id'])
                del user_temp_data[user_id]['message_id']
                del data['message_id']
            except:
                pass

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"podal_health_yes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"podal_health_no"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_data_docs"))
            bot.send_message(
                user_id, 
                "Имеется ли причинения вреда здоровья в следствии ДТП?", 
                reply_markup=keyboard
            )
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_number_docs"))
            msg = bot.send_message(
                message.chat.id, 
                f"❌ Неправильный формат ввода!\nВведите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ:",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_data_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_data_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_number_docs"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ:",
            reply_markup = keyboard
        )
        bot.register_next_step_handler(call.message, process_client_data_docs, data['client_id'], msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data in ['podal_health_yes', 'podal_health_no'])
    @prevent_double_click(timeout=3.0)
    def callback_podal_health(call):
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        if call.data == 'podal_health_yes':
            if data.get('who_dtp') == "По форме ГИБДД":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"podal_place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"podal_place_dtp"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))  
                data['number_photo'] = '-'
                user_temp_data[user_id] = data
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                    reply_markup=keyboard
                )
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"podal_photo_non_gosuslugi"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, podal_number_photo, data, msg.message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"podal_culp_have_osago_yes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"podal_culp_have_osago_no"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Есть ли у пострадавшего ОСАГО?",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ['podal_culp_have_osago_yes', 'podal_culp_have_osago_no'])
    @prevent_double_click(timeout=3.0)
    def podal_culp_question(call):
        user_id = call.from_user.id
        data=user_temp_data[user_id]
        
        if call.data == 'podal_culp_have_osago_yes':
            if data.get('who_dtp') == "По форме ГИБДД":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"podal_place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"podal_place_dtp"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_culp_question"))  # Добавлена кнопка
                data['number_photo'] = '-'
                user_temp_data[user_id] = data
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                    reply_markup=keyboard
                )
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"podal_photo_non_gosuslugi"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_culp_question"))  # Добавлена кнопка
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, podal_number_photo, data, msg.message_id)
        else:
            if data.get('who_dtp') == "По форме ГИБДД":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"podal_place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"podal_place_dtp"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_culp_question"))  # Добавлена кнопка
                data['number_photo'] = '-'
                user_temp_data[user_id] = data
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                    reply_markup=keyboard
                )
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"podal_photo_non_gosuslugi"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_culp_question"))  # Добавлена кнопка
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, podal_number_photo, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_culp_question")
    @prevent_double_click(timeout=3.0)
    def back_to_health_question(call):
        """Возврат к вопросу о наличии ОСАГО"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"podal_culp_have_osago_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"podal_culp_have_osago_no"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Есть ли у пострадавшего ОСАГО?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_health")
    @prevent_double_click(timeout=3.0)
    def back_to_finish_document_upload(call):
        """Возврат к вопросу о вреде здоровью"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"podal_health_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"podal_health_no"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_data_docs"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Имеется ли причинения вреда здоровья в следствии ДТП?",
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "podal_photo_non_gosuslugi")
    @prevent_double_click(timeout=3.0)
    def handle_podal_photo_non_gosuslugi(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"next_photo_podal"))
        keyboard.add(types.InlineKeyboardButton("Я внесу фотофиксацию", callback_data=f"continue_photo_podal"))  

        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Если нет прикрепления фотофиксации в Госуслуги, то выплата ограничивается размером 100000₽",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ["next_photo_podal", "continue_photo_podal"])
    @prevent_double_click(timeout=3.0)
    def handle_podal_next_photo_gosuslugi(call):
        data = user_temp_data[call.from_user.id]
        if call.data == "next_photo_podal":
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"podal_place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"podal_place_dtp"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))  
            data['number_photo'] = '-'
            user_temp_data[call.from_user.id] = data
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                reply_markup=keyboard
            )
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"podal_photo_non_gosuslugi"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, podal_number_photo, data, msg.message_id)

    def podal_number_photo(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['number_photo'] = message.text
        user_temp_data[message.from_user.id] = data

        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"podal_place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"podal_place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_number_photo"))
        
        bot.send_message(
            message.from_user.id,
            "Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_number_photo")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_number_photo(call):
        """Возврат к вводу номера фотофиксации"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"podal_photo_non_gosuslugi"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, podal_number_photo, data, msg.message_id)
   
    @bot.callback_query_handler(func=lambda call: call.data in ["podal_place_home", "podal_place_dtp"])
    @prevent_double_click(timeout=3.0)
    def callback_podal_place(call):
        """Обработка ремонт не более 50км от места ДТП или места жительства"""
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "podal_place_home":
            data['place'] = "Жительства"
        else:
            data['place'] = "ДТП"

        user_temp_data[user_id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_number_photo_or_health"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text='Введите дату подачи заявления в страховую в формате ДД.ММ.ГГГГ',
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, podal_date_ins_pod, data, msg.message_id)

    def podal_date_ins_pod(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({'date_ins': message.text})
            data.update({'date_ins_pod': message.text})
            user_temp_data[message.from_user.id] = data

            
            context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"podal_next_bank"))
            keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"podal_cancel_bank"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_date_ins_pod"))
            
            msg = bot.send_message(
                chat_id=message.chat.id,
                text=context,
                reply_markup=keyboard
            )
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_podal_number_photo_or_health"))
            msg = bot.send_message(
                message.chat.id, 
                f"❌ Неправильный формат ввода!\nВведите дату подачи заявления в страховую в формате ДД.ММ.ГГГГ",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, podal_date_ins_pod, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_date_ins_pod")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_date_ins_pod(call):
        """Возврат к вводу даты подачи заявления в страхоую"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_number_photo_or_health"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату подачи заявления в страховую в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, podal_date_ins_pod, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_number_photo_or_health")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_number_photo_or_health(call):
        """Возврат к вопросу о фотофиксации или выбору места"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"podal_place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"podal_place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_health"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data in ["podal_next_bank", "podal_cancel_bank"])
    @prevent_double_click(timeout=3.0)
    def callback_podal_requisites(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "podal_next_bank":
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="<b>Заполнение банковских реквизитов</b>",
                    parse_mode='HTML'
                )
            user_temp_data[user_id]['message_id'] = msg.message_id
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_requisites_choice"))
            msg2 = bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Введите банк получателя клиента",
                    reply_markup = keyboard
                )
            user_message_id = msg2.message_id
            bot.register_next_step_handler(msg, bank, data, user_message_id)

        else:
            data.update({"bank": "-"})
            data.update({"bank_account": "-"})
            data.update({"bank_account_corr": "-"})
            data.update({"BIK": "-"})
            data.update({"INN": "-"})
            fields_to_remove = [
                'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
                'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
                'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back', 'message_id', 'message_id2',
                'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
            ]
            if data.get('sobstvenik', '') != 'С начала' and data.get('sobstvenik', '') != 'После заявления в страховую' and data.get('sobstvenik', '') != 'После ответа от страховой':
                data.update({"sobstvenik": "С начала"})
            if data.get('who_dtp', '') != 'Евро-протокол' and data.get('who_dtp', '') != 'По форме ГИБДД':
                data.update({"who_dtp": "По форме ГИБДД"})
            if data.get("ev", '') != 'Нет' and data.get("ev", '') != 'Да':
                data.update({"ev": "Нет"})  
            for field in fields_to_remove:
                data.pop(field, None)

            if data.get('viborRem', '') == 'no_viplatily':
                data['status'] = 'Отправлен запрос в страховую'
                data['accident'] = 'ДТП'
                data.update({'date_ins': get_next_business_date()})
                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                
                create_fio_data_file(data)
                
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                if data.get('N_dov_not', '') == '':
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                            "{{ ФИОк }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",'')), str(data.get("fio_k",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили.docx"
                else:
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')),
                                str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')),str(data.get("fio_not",'')), str(data.get("number_not",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx"

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"podal_request_act_payment_{data['client_id']}"))
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))    
                try:
                    with open(f"clients\\{data['client_id']}\\Документы\\{output_filename}", 'rb') as document_file:
                        bot.send_document(
                            call.message.chat.id, 
                            document_file, 
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(call.message.chat.id, f"Файл не найден")

                if data.get('user_id', '') != '8572367590' and user_id != data.get('user_id', ''):
                    bot.send_message(
                        data.get('user_id', '8572367590'),
                        "Составлено заявление в страховую об изменении формы страхового возмещения",
                        reply_markup=keyboard
                    )
                
                if user_id in user_temp_data:
                    user_temp_data.pop(user_id, None)

            elif data.get('viborRem', '') == 'Заявление':
                data['status'] = 'Ожидание претензии'
                data.update({'date_ins': get_next_business_date()})
                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                
                create_fio_data_file(data)
                
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                if data.get('N_dov_not', '') == '':
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                            "{{ ФИОк }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",'')), str(data.get("fio_k",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили.docx"
                else:
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')),
                                str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')),str(data.get("fio_not",'')), str(data.get("number_not",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx"

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"podal_request_act_payment_{data['client_id']}"))
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))    
                try:
                    with open(f"clients\\{data['client_id']}\\Документы\\{output_filename}", 'rb') as document_file:
                        bot.send_document(
                            call.message.chat.id, 
                            document_file, 
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(call.message.chat.id, f"Файл не найден")

                if data.get('user_id', '') != '8572367590' and user_id != data.get('user_id', ''):
                    bot.send_message(
                        data.get('user_id', '8572367590'),
                        "Составлено заявление в страховую об изменении формы страхового возмещения",
                        reply_markup=keyboard
                    )
                
                if user_id in user_temp_data:
                    user_temp_data.pop(user_id, None)
            else:
                data['status'] = 'Отправлен запрос в страховую'
                data['accident'] = 'ДТП'
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                
                create_fio_data_file(data)

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
                keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"podal_request_act_payment_{data['client_id']}"))
                bot.send_message(
                    call.message.chat.id,
                    "Ожидайте ответа от страховой компании",
                    reply_markup=keyboard
                )
                
                if user_id in user_temp_data:
                    user_temp_data.pop(user_id, None)
            

    def bank(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"bank": message.text})
        user_temp_data[message.from_user.id].update(data)
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank"))
        message = bot.send_message(message.chat.id, text="Введите счет получателя, 20 цифр", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, bank_account, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_requisites_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_requisites_choice(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.delete_message(call.message.chat.id, user_temp_data[user_id]['message_id'])
        except:
            pass
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"podal_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"podal_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_date_ins_pod"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )

    def bank_account(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit() and len(message.text) == 20:
            data.update({"bank_account": message.text})
            user_temp_data[message.from_user.id].update(data)
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank_account"))

            message = bot.send_message(
                message.chat.id,
                text="Введите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите счет получателя, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_bank")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_bank(call):
        """Возврат к вводу счета получателя"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_requisites_choice"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите банк получателя клиента",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(msg, bank, data, msg.message_id)
    def bank_account_corr(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit() and len(message.text) == 20:
            data.update({"bank_account_corr": message.text})
            user_temp_data[message.from_user.id].update(data)
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank_account_corr"))
            message = bot.send_message(
                message.chat.id,
                text="Введите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, BIK, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank_account"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_bank_account")
    @prevent_double_click(timeout=3.0)
    def back_to_bank_podal_account(call):
        """Возврат к вводу корр. счета"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите счет получателя, 20 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, bank_account, data, msg.message_id)
    def BIK(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit() and len(message.text) == 9:
            data.update({"BIK": message.text})
            user_temp_data[message.from_user.id].update(data)
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_BIK"))
            message = bot.send_message(
                message.chat.id,
                text="Введите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank_account_corr"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, БИК должен состоять только из цифр!\nВведите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, BIK, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_bank_account_corr")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_bank_account_corr(call):
        """Возврат к вводу БИК"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]
        
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank_account"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите корреспондентский счет банка, 20 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, bank_account_corr, data, msg.message_id)

    def INN(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_temp_data[user_id]['message_id'])
            del user_temp_data[user_id]['message_id']
            del data['message_id']
        except:
            pass
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        if message.text.isdigit() and len(message.text) == 10:
            data.update({"INN": message.text})
            fields_to_remove = [
                'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
                'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
                'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back', 'message_id', 'message_id2',
                'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
            ]
            if data.get('sobstvenik', '') != 'С начала' and data.get('sobstvenik', '') != 'После заявления в страховую' and data.get('sobstvenik', '') != 'После ответа от страховой':
                data.update({"sobstvenik": "С начала"})
            if data.get('who_dtp', '') != 'Евро-протокол' and data.get('who_dtp', '') != 'По форме ГИБДД':
                data.update({"who_dtp": "По форме ГИБДД"})
            if data.get("ev", '') != 'Нет' and data.get("ev", '') != 'Да':
                data.update({"ev": "Нет"})  
            for field in fields_to_remove:
                data.pop(field, None)
            if data.get('viborRem', '') == 'no_viplatily':
                data['status'] = 'Ожидание претензии'
                data['accident'] = 'ДТП'
                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                
                create_fio_data_file(data)
                data.update({'date_ins': get_next_business_date()})

                if data.get('N_dov_not', '') == '':
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                            "{{ ФИОк }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",'')), str(data.get("fio_k",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили.docx"
                else:
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')),
                                str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')),str(data.get("fio_not",'')), str(data.get("number_not",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx"

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"podal_request_act_payment_{data['client_id']}"))
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))    
                try:
                    with open(f"clients\\{data['client_id']}\\Документы\\{output_filename}", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file, 
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")

                if data.get('user_id', '') != '8572367590' and user_id != data.get('user_id', ''):
                    bot.send_message(
                        data.get('user_id', '8572367590'),
                        "Составлено заявление в страховую об изменении формы страхового возмещения",
                        reply_markup=keyboard
                    )
                
                if user_id in user_temp_data:
                    user_temp_data.pop(user_id, None)
            elif data.get('viborRem', '') == 'Заявление':
                data['status'] = 'Отправлен запрос в страховую'
                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                
                create_fio_data_file(data)
                data.update({'date_ins': get_next_business_date()})

                if data.get('N_dov_not', '') == '':
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                            "{{ ФИОк }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",'')), str(data.get("fio_k",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили.docx"
                else:
                    replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}"],
                            [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')),
                                str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')),str(data.get("fio_not",'')), str(data.get("number_not",'')), str(data.get("date_dtp",'')),
                                str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",''))],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx")
                    output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx"

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"podal_request_act_payment_{data['client_id']}"))
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))    
                try:
                    with open(f"clients\\{data['client_id']}\\Документы\\{output_filename}", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file, 
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")

                if data.get('user_id', '') != '8572367590' and user_id != data.get('user_id', ''):
                    bot.send_message(
                        data.get('user_id', '8572367590'),
                        "Составлено заявление в страховую об изменении формы страхового возмещения",
                        reply_markup=keyboard
                    )
                
                if user_id in user_temp_data:
                    user_temp_data.pop(user_id, None)
            else:
                data['status'] = 'Отправлен запрос в страховую'
                data['accident'] = 'ДТП'
                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                
                create_fio_data_file(data)
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"podal_request_act_payment_{data['client_id']}"))
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))    
                bot.send_message(
                    message.chat.id,
                    "Ожидайте ответа от страховой компании",
                    reply_markup=keyboard
                )
                
                if user_id in user_temp_data:
                    user_temp_data.pop(user_id, None)
            
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_BIK"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_podal_BIK")
    @prevent_double_click(timeout=3.0)
    def back_to_podal_BIK(call):
        """Возврат к вводу БИК"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_podal_bank_account_corr"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите БИК банка, 9 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, BIK, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('podal_request_act_payment_'))
    @prevent_double_click(timeout=3.0)
    def podal_request_act_payment_callback(call):
        user_id = call.from_user.id
        client_id = int(call.data.split('_')[-1])
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        contract = get_client_from_db_by_client_id(str(client_id))
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            data = json.loads(contract.get('data_json', '{}'))
        except:
            data = contract
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        # Выбираем нужный шаблон
        if data.get("N_dov_not", '') != '':
            template_path = "Шаблоны/1. ДТП/1. На ремонт/5. Запрос в страховую о выдаче акта и расчета/5. Запрос в страховую о выдаче акта и расчёта представитель.docx"
            output_filename = "Запрос в страховую о выдаче акта и расчёта представитель.docx"
            replace_words_in_word(
                ["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", 
                "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Телефон_представителя }}", 
                "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}", 
                "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", 
                "{{ Телефон }}"],
                [str(data.get("insurance", "")), str(data.get("city", "")), str(data.get("fio", "")), 
                str(data.get("date_of_birth", "")), str(data.get("seria_pasport", "")), 
                str(data.get("number_pasport", "")), str(data.get("where_pasport", "")), 
                str(data.get("when_pasport", "")),str(data.get("N_dov_not", "")), 
                str(data.get("data_dov_not", "")), str(data.get("fio_not", "")), str(data.get("number_not", "")), 
                str(data.get("date_dtp", "")), str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
                str(data.get("marks", "")), str(data.get("car_number", "")), 
                str(data.get("marks_culp", "")), str(data.get("number_auto_culp", "")), 
                str(data.get("number", ""))],
                template_path,
                f"clients/"+str(data['client_id'])+f"/Документы/{output_filename}"
            )
        else:
            template_path = "Шаблоны/1. ДТП/1. На ремонт/5. Запрос в страховую о выдаче акта и расчета/5. Запрос в страховую о выдаче акта и расчёта.docx"
            output_filename = "Запрос в страховую о выдаче акта и расчёта.docx"

            # Заполняем шаблон
            replace_words_in_word(
                ["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", 
                "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}", 
                "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", 
                "{{ Телефон }}", "{{ ФИОк }}"],
                [str(data.get("insurance", "")), str(data.get("city", "")), str(data.get("fio", "")), 
                str(data.get("date_of_birth", "")), str(data.get("seria_pasport", "")), 
                str(data.get("number_pasport", "")), str(data.get("where_pasport", "")), 
                str(data.get("when_pasport", "")), str(data.get("date_dtp", "")), 
                str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
                str(data.get("marks", "")), str(data.get("car_number", "")), 
                str(data.get("marks_culp", "")), str(data.get("number_auto_culp", "")), 
                str(data.get("number", "")), str(data.get("fio_k", ""))],
                template_path,
                f"clients/"+str(data['client_id'])+f"/Документы/{output_filename}"
            )
        
        # Отправляем документ агенту
        try: 
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))   
            with open(f"clients/"+str(data['client_id'])+f"/Документы/{output_filename}", 'rb') as doc:
                bot.send_document(call.message.chat.id, doc, caption="📋 Запрос на выдачу документов", reply_markup = keyboard)
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, "❌ Ошибка: файл не найден")
        
        if data['user_id'] != '8572367590' and user_id != data['user_id']:
            try:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))  
                bot.send_message(
                    int(data['user_id']),
                    f"✅ Запрос на выдачу документов составлен, ознакомиться с ним можно в личном кабинете",
                    reply_markup = keyboard
                )
            except Exception as e:
                print(f"Ошибка отправки уведомления клиенту: {e}")


    def process_client_number_auto_culp(message, client_id, user_message_id, data):
        """Обработка номера авто виновника - ФИНАЛ"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
        
        original_text = message.text.replace(" ", "")
        has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
        
        if not has_lowercase and re.match(pattern, car_number) and len(car_number) in [8, 9]:
            data['number_auto_culp'] = str(car_number)
            if data['status'] != 'Деликт' and data.get('viborRem','') != 'Цессия':
                msg = bot.send_message(message.chat.id, "Введите дату подачи заявления в страховую в формате ДД.ММ.ГГГГ")
                bot.register_next_step_handler(msg, process_client_date_ins_pod, client_id, msg.message_id, data)
            else:

                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                        
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                    # Продолжаем с текущими данными
                
                create_fio_data_file(data)
                replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                "{{ Страховая }}", "{{ винФИО }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Обложка дела.docx")
                replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                [str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                    str(data["number"]), str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx")
            
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}","{{ ФИОк }}" ],
                                [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["date_dtp"]), str(data["time_dtp"]),
                                    str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                    str(data["number"]),str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx")
                
                try:

                    with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file

                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                if data['status'] == 'Деликт':
                    bot.send_message(
                        int(data['user_id']),
                        "✅ Запросы в страховую и ГИБДД успешно сформированы!\nИсковое заявление формируется. Мы сообщим вам, когда оно будет готово!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                        reply_markup = keyboard
                    )
                elif data['viborRem'] == 'Цессия':
                    bot.send_message(
                        int(data['user_id']),
                        "✅ Запросы в страховую и ГИБДД успешно сформированы!\nДоговор Цессии формируется. Мы сообщим вам, когда он будет готов!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                        reply_markup = keyboard
                    )
                # Очищаем временные данные
                if client_id in user_temp_data:
                    user_temp_data.pop(client_id, None)

        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер авто виновника ДТП\n"
                "Пример: А123БВ77 или А123БВ777\n"
                "Все буквы должны быть заглавными!"
            )
            bot.register_next_step_handler(msg, process_client_number_auto_culp, client_id, msg.message_id, data)

    def process_client_date_ins_pod(message, client_id, user_message_id, data):
        """Обработка даты страхового полиса"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            if data.get('viborRem', '') =='Заявление':
                data.update({'date_ins_pod': message.text.strip()})
                user_id = message.from_user.id
                user_temp_data[user_id] = data
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"docsInsYesPodal"))
                keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"docsInsPodal"))
                message = bot.send_message(
                    chat_id=message.chat.id,
                    text="Необходимо заявление на выдачу документов из страховой?",
                    reply_markup = keyboard
                )
            else:
                if data.get('viborRem', '') =='':
                    data.update({'date_ins': message.text.strip()})
                    data.update({'date_ins_pod': message.text.strip()})
                elif data.get('viborRem', '') =='no_viplatily':
                    data.update({'date_ins': get_next_business_date()})
                    data.update({'date_ins_pod': message.text.strip()})
                    if data.get('N_dov_not', '') == '':
                        replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                                "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                                "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                                "{{ ФИОк }}"],
                                [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                    str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')), str(data.get("date_dtp",'')),
                                    str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",'')), str(data.get("fio_k",''))],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили.docx")
                        output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили.docx"
                    else:
                        replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                                "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                                "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                                "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}"],
                                [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')),
                                    str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),str(data.get("when_pasport",'')),
                                    str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')),str(data.get("fio_not",'')), str(data.get("number_not",'')), str(data.get("date_dtp",'')),
                                    str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),str(data.get("date_ins_pod",'')), 
                                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("city",'')), str(data.get("date_ins",''))],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx")
                        output_filename = "Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx"
                    try:
                        with open(f"clients\\{data['client_id']}\\Документы\\{output_filename}", 'rb') as document_file:
                            bot.send_document(
                                message.chat.id, 
                                document_file,
                            )   
                    except FileNotFoundError:
                        bot.send_message(message.chat.id, f"Файл не найден")
                data.update({'accident': 'ДТП'})
                try:
                    from database import save_client_to_db_with_id
                    updated_client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                        
                except Exception as e:
                    print(f"⚠️ Ошибка обновления: {e}")
                
                create_fio_data_file(data)
                replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                    "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                    "{{ Страховая }}", "{{ винФИО }}"],
                                    [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                        str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"])],
                                        "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела.docx",
                                        "clients\\"+str(data["client_id"])+"\\Документы\\"+"Обложка дела.docx")

                
                bot.send_message(
                    message.chat.id,
                    f"Ожидайте ответа от страховой",
                )
                from main_menu import show_main_menu_by_user_id
                show_main_menu_by_user_id(bot, user_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату подачи заявления в страховую в формате ДД.ММ.ГГГГ")
            bot.register_next_step_handler(msg, process_client_date_ins_pod, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data in ["docsInsYesPodal", "docsInsPodal"])
    @prevent_double_click(timeout=3.0)
    def handle_answer_docs_yes(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        if call.data == "docsInsYesPodal":
            data.update({"status": "Подано заяление на выдачу документов из страховой"})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                            
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            create_fio_data_file(data)
            if data.get("N_dov_not", '') != '':
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
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx")
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx", 'rb') as document_file:
                        bot.send_document(
                            call.message.chat.id, 
                            document_file,
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(call.message.chat.id, f"Файл не найден")
            else:
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
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта.docx")
                try:
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта.docx", 'rb') as document_file:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                        bot.send_document(
                            call.message.chat.id, 
                            document_file,
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(call.message.chat.id, f"Файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            bot.send_message(
                    int(data['user_id']),
                    "✅ Запрос в страховую о выдаче акта и расчета сформирован!\nОзнакомиться с ним можно в личном кабинете",
                    reply_markup = keyboard
                )
            # Очищаем временные данные
            if user_id in user_temp_data:
                user_temp_data.pop(user_id, None)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            bot.send_message(
                    call.message.chat.id,
                    "Ожидайте ответ от страховой",
                    reply_markup = keyboard
                )
            # Очищаем временные данные
            if user_id in user_temp_data:
                user_temp_data.pop(user_id, None)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("zayavlenie_ins_"))
    @prevent_double_click(timeout=3.0)
    def handle_zayavlenie_ins(call):
        client_id = call.data.replace("zayavlenie_ins_", "")
        user_id = call.from_user.id
        
        contract = get_client_from_db_by_client_id(client_id)

        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            if contract.get('data_json'):
                contract_data = json.loads(contract.get('data_json', '{}'))
                data = {**contract, **contract_data}
            else:
                data = contract
        except:
            data = contract

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите входящий номер в страховую"
        )
        bot.register_next_step_handler(msg, Nv_ins, data, msg.message_id)

    def Nv_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({'Nv_ins': message.text.strip()})

        msg = bot.send_message(
            chat_id=message.chat.id,
            text="Введите номер акта осмотра ТС"
        )
        bot.register_next_step_handler(msg, Na_ins, data, msg.message_id)

    def Na_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({'Na_ins': message.text.strip()})

        msg = bot.send_message(
            chat_id=message.chat.id,
            text="Введите организацию, проводившую экспертизу"
        )
        bot.register_next_step_handler(msg, org_exp, data, msg.message_id)
    
    def org_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({'org_exp': message.text.strip()})

        msg = bot.send_message(
            chat_id=message.chat.id,
            text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ"
        )
        bot.register_next_step_handler(msg, date_exp, data, msg.message_id)

    def date_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp": message.text})
            message = bot.send_message(message.chat.id, text="Введите стоимость востановительного регмонта по экспертизе без учета износа")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_exp, data, user_message_id)

        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_exp, data, user_message_id)

    def coin_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
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
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():
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
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():
            data.update({"coin_osago": message.text})
            data.update({"date_ins": get_next_business_date()})
            data['status'] = "Ожидание претензии"
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                            
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            create_fio_data_file(data)
            if data.get("fio_not", '') != '':
                replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                                        "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                        "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                                        "{{ Nакта_осмотра }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}",
                                        "{{ Nавто_клиента }}", "{{ Дата_подачи_заявления }}","{{ Организация }}", "{{ Дата_экспертизы }}",
                                        "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Город }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}",
                                        "{{ Дата }}"],
                                        [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), str(data["number_not"]),
                                            str(data["Na_ins"]),str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                            str(data["marks"]), str(data["car_number"]),str(data["date_ins_pod"]), str(data["org_exp"]),
                                            str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]), str(data["city"]),
                                            str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_ins"])],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\5. Заявление в страховую об изменении формы\\5. Заявление в страховую об изменении формы страхового возмещения выплатили представитель.docx",
                                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Заявление в страховую об изменении формы страхового возмещения выплатили представитель.docx")
                try:
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Заявление в страховую об изменении формы страхового возмещения выплатили представитель.docx", 'rb') as document_file:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            else:
                replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                                        "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                        "{{ Nакта_осмотра }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}",
                                        "{{ Nавто_клиента }}", "{{ Дата_подачи_заявления }}","{{ Организация }}", "{{ Дата_экспертизы }}",
                                        "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Город }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}",
                                        "{{ Дата }}", "{{ ФИОк }}"],
                                        [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["Na_ins"]),str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                            str(data["marks"]), str(data["car_number"]),str(data["date_ins_pod"]), str(data["org_exp"]),
                                            str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]), str(data["city"]),
                                            str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_ins"]), str(data["fio_k"])],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\5. Заявление в страховую об изменении формы\\5. Заявление в страховую об изменении формы страхового возмещения выплатили.docx",
                                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Заявление в страховую об изменении формы страхового возмещения выплатили.docx")
                try:
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Заявление в страховую об изменении формы страхового возмещения выплатили.docx", 'rb') as document_file:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                            reply_markup = keyboard
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            bot.send_message(
                    int(data['user_id']),
                    "✅ Заявление в страховую об изменении формы страхового возмещения сформировано, ознакомиться с ним можно в личном кабинете.\n\n✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                    reply_markup = keyboard
                )
            # Очищаем временные данные
            if user_id in user_temp_data:
                user_temp_data.pop(user_id, None)

        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите сумму выплаты по ОСАГО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_osago, data, user_message_id)


    def get_contract_callback(user_id, client_id):
        """Определяет правильный callback для просмотра договора в зависимости от роли пользователя"""
        from database import get_admin_from_db_by_user_id
        
        admin_data = get_admin_from_db_by_user_id(user_id)
        
        admin_value = admin_data.get('admin_value', '')
        
        if admin_value == 'Агент':
            return f"agent_view_contract_{client_id}"
        if admin_value == 'Администратор':
            return f"administrator_view_contract_{client_id}"
        if admin_value == 'Оценщик':
            return f"appraiser_view_contract_{client_id}"
        if admin_value == 'Претензионный отдел':
            return f"pret_view_contract_{client_id}"
        if admin_value == 'Претензионный отдел':
            return f"isk_view_contract_{client_id}"
        if admin_value == 'Юрист':
            return f"pret_view_contract_{client_id}"
        
        return f"view_contract_{client_id}"