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

def setup_net_osago_handlers(bot, user_temp_data):
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
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_net_osago_continue_documents_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_rem(call):
        client_id = call.data.replace("agent_net_osago_continue_documents_", "")
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
        keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id']))) 
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
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_seria_docs"))

        msg = bot.send_message(message.chat.id, f"Введите номер документа {data.get('docs', 'СТС')}", reply_markup = keyboard)
        bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_seria_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_seria_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_net_osago_continue_documents_{data['client_id']}"))

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
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_number_docs"))
            msg = bot.send_message(
                message.chat.id,
                f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ:",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
        else:
            user_temp_data[user_id].update(data)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_seria_docs"))
            msg = bot.send_message(
                message.chat.id,
                f"❌ Неправильный формат!\nВведите номер документа {data.get('docs', 'СТС')} (только цифры):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_number_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_number_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_seria_docs"))

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
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"net_osago_health_yes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"net_osago_health_no"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_data_docs"))
            bot.send_message(
                user_id, 
                "Имеется ли причинения вреда здоровья в следствии ДТП?", 
                reply_markup=keyboard
            )
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_number_docs"))
            msg = bot.send_message(
                message.chat.id, 
                f"❌ Неправильный формат ввода!\nВведите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ:",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_data_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_data_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_number_docs"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ:",
            reply_markup = keyboard
        )
        bot.register_next_step_handler(call.message, process_client_data_docs, data['client_id'], msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data in ['net_osago_health_yes', 'net_osago_health_no'])
    @prevent_double_click(timeout=3.0)
    def callback_net_osago_health(call):
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        if data.get('who_dtp') == "По форме ГИБДД":
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"net_osago_place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"net_osago_place_dtp"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_health"))  
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
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"net_osago_photo_non_gosuslugi"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_health"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, podal_number_photo, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_health")
    @prevent_double_click(timeout=3.0)
    def back_to_finish_document_upload(call):
        """Возврат к вопросу о вреде здоровью"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"net_osago_health_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"net_osago_health_no"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_net_osago_data_docs"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Имеется ли причинения вреда здоровья в следствии ДТП?",
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "net_osago_photo_non_gosuslugi")
    @prevent_double_click(timeout=3.0)
    def handle_podal_photo_non_gosuslugi(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"next_photo_net_osago"))
        keyboard.add(types.InlineKeyboardButton("Я внесу фотофиксацию", callback_data=f"continue_photo_net_osago"))  

        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Если нет прикрепления фотофиксации в Госуслуги, то выплата ограничивается размером 100000₽",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ["next_photo_net_osago", "continue_photo_net_osago"])
    @prevent_double_click(timeout=3.0)
    def handle_net_osago_next_photo_gosuslugi(call):
        data = user_temp_data[call.from_user.id]
        if call.data == "next_photo_net_osago":
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"net_osago_place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"net_osago_place_dtp"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_health"))  
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
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"net_osago_photo_non_gosuslugi"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_health"))
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
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"net_osago_place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"net_osago_place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_number_photo"))
        
        bot.send_message(
            message.from_user.id,
            "Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_number_photo")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_number_photo(call):
        """Возврат к вводу номера фотофиксации"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"net_osago_photo_non_gosuslugi"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_health"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, podal_number_photo, data, msg.message_id)
   
    @bot.callback_query_handler(func=lambda call: call.data in ["net_osago_place_home", "net_osago_place_dtp"])
    @prevent_double_click(timeout=3.0)
    def callback_net_osago_place(call):
        """Обработка ремонт не более 50км от места ДТП или места жительства"""
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "net_osago_place_home":
            data['place'] = "Жительства"
        else:
            data['place'] = "ДТП"

        user_temp_data[user_id] = data
        
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"net_osago_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"net_osago_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_number_photo_or_health"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_number_photo_or_health")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_number_photo_or_health(call):
        """Возврат к вопросу о фотофиксации или выбору места"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"podal_place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"podal_place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_health"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data in ["net_osago_next_bank", "net_osago_cancel_bank"])
    @prevent_double_click(timeout=3.0)
    def callback_net_osago_requisites(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "net_osago_next_bank":
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="<b>Заполнение банковских реквизитов</b>",
                    parse_mode='HTML'
                )
            user_temp_data[user_id]['message_id'] = msg.message_id
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_requisites_choice"))
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
        
            for field in fields_to_remove:
                data.pop(field, None)

            
            data['status'] = 'Деликт'
            data['accident'] = 'Нет ОСАГО'
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
            replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                        "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                        "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                        [str(data["fio"]), str(data["date_of_birth"]),
                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                            str(data["date_dtp"]), str(data["time_dtp"]),
                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                            str(data["number"]), str(data["fio_k"])],
                            "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление о выдаче копии справки участников ДТП.docx")
            
            try:
                with open(f"clients/{str(data['client_id'])}/Документы/Заявление о выдаче копии справки участников ДТП.docx", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
                    keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"net_osago_request_act_payment_{data['client_id']}"))
                    bot.send_document(call.message.chat.id, doc, caption="📋 Заявление о выдаче копии справки участников ДТП", reply_markup=keyboard)
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, "❌ Ошибка: файл не найден")
            
            if data['user_id'] != '8572367590' and user_id != data['user_id']:
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))  
                    bot.send_message(
                        int(data['user_id']),
                        f"✅ Заявление о выдаче копии справки участников ДТП составлено, ознакомиться с ним можно в личном кабинете.\nИсковое заявление формируется, убедитесь, что юридические услуги оплачены, а нотариальная доверенность загружена.",
                        reply_markup = keyboard
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления клиенту: {e}")
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
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank"))
        message = bot.send_message(message.chat.id, text="Введите счет получателя, 20 цифр", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, bank_account, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_requisites_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_requisites_choice(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.delete_message(call.message.chat.id, user_temp_data[user_id]['message_id'])
        except:
            pass
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"net_osago_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"net_osago_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_date_ins_pod"))
        
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
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank_account"))

            message = bot.send_message(
                message.chat.id,
                text="Введите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите счет получателя, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_bank")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_bank(call):
        """Возврат к вводу счета получателя"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_requisites_choice"))

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
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank_account_corr"))
            message = bot.send_message(
                message.chat.id,
                text="Введите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, BIK, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank_account"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_bank_account")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_bank_account(call):
        """Возврат к вводу корр. счета"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank"))
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
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_BIK"))
            message = bot.send_message(
                message.chat.id,
                text="Введите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank_account_corr"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, БИК должен состоять только из цифр!\nВведите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, BIK, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_bank_account_corr")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_bank_account_corr(call):
        """Возврат к вводу БИК"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]
        
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank_account"))
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
        
            for field in fields_to_remove:
                data.pop(field, None)

            data['status'] = 'Деликт'
            data['accident'] = 'Нет ОСАГО'
       
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
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
                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление о выдаче копии справки участников ДТП.docx")
            
            try:
                with open(f"clients/{str(data['client_id'])}/Документы/Заявление о выдаче копии справки участников ДТП.docx", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
                    keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"net_osago_request_act_payment_{data['client_id']}"))
                    bot.send_document(message.chat.id, doc, caption="📋 Заявление о выдаче копии справки участников ДТП", reply_markup=keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            
            if data['user_id'] != '8572367590' and user_id != data['user_id']:
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))  
                    bot.send_message(
                        int(data['user_id']),
                        f"✅ Заявление о выдаче копии справки участников ДТП составлено, ознакомиться с ним можно в личном кабинете.\nИсковое заявление формируется, убедитесь, что юридические услуги оплачены, а нотариальная доверенность загружена.",
                        reply_markup = keyboard
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления клиенту: {e}")
            if user_id in user_temp_data:
                user_temp_data.pop(user_id, None)
            
        else:
            keyboard = types.InlineKeyboardMarkup() 
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_BIK"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_net_osago_BIK")
    @prevent_double_click(timeout=3.0)
    def back_to_net_osago_BIK(call):
        """Возврат к вводу БИК"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup() 
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_net_osago_bank_account_corr"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите БИК банка, 9 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, BIK, data, msg.message_id) 

    @bot.callback_query_handler(func=lambda call: call.data.startswith("NoOsago_prod_"))
    @prevent_double_click(timeout=3.0)
    def handle_NoOsago_yes(call):
        """Клиент получил ответ от страховой"""
        client_id = call.data.replace("NoOsago_prod_", "")
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
        
        data['accident'] = 'Нет ОСАГО'
        data['status'] = 'Деликт'
        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
            print(data)
                
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
            # Продолжаем с текущими данными
        
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
                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление о выдаче копии справки участников ДТП.docx")
    
        replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                        "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                        "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}","{{ ФИОк }}" ],
                        [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                            str(data["date_dtp"]), str(data["time_dtp"]),
                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                            str(data["number"]),str(data["fio_k"])],
                            "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"Запрос в страховую о выдаче акта и расчёта.docx")
        try:
            with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Заявление о выдаче копии справки участников ДТП.docx", 'rb') as document_file:
                bot.send_document(
                    call.message.chat.id, 
                    document_file,
                )   
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, f"Файл не найден")
        try:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Запрос в страховую о выдаче акта и расчёта.docx", 'rb') as document_file:
                bot.send_document(
                    call.message.chat.id, 
                    document_file,
                    reply_markup = keyboard
                )   
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, f"Файл не найден")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        if data['user_id'] != '8572367590' and user_id != data['user_id']:
            bot.send_message(
                int(data['user_id']),
                "✅ Запросы в страховую и ГИБДД успешно сформированы!\nИсковое заявление формируется. Мы сообщим вам, когда оно будет готово!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                reply_markup = keyboard
            )
        
        # Очищаем временные данные
        if client_id in user_temp_data:
            user_temp_data.pop(client_id, None)


    @bot.callback_query_handler(func=lambda call: call.data.startswith('net_osago_request_act_payment_'))
    @prevent_double_click(timeout=3.0)
    def net_osago_request_act_payment_callback(call):
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