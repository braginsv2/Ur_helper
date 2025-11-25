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
from word_utils import create_fio_data_file, replace_words_in_word
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
    @bot.callback_query_handler(func=lambda call: call.data.startswith("NoOsago_no_"))
    @prevent_double_click(timeout=3.0)
    def handle_answer_no(call):
        """Клиент не получил ответ от страховой"""
        client_id = call.data.replace("NoOsago_no_", "")
        if client_id in user_temp_data:
            user_temp_data.pop(client_id, None)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        # Возвращаем в главное меню
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, client_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("NoOsago_yes_"))
    @prevent_double_click(timeout=3.0)
    def handle_NoOsago_yes(call):
        """Клиент получил ответ от страховой"""
        client_id = call.data.replace("NoOsago_yes_", "")
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
            text="Введите марку и модель авто:"
        )
        bot.register_next_step_handler_by_chat_id(user_id, process_client_car_marks, client_id, msg.message_id, data)

    def process_client_car_marks(message, client_id, user_message_id, data):
        """Обработка марки и модели авто"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['marks'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите номер авто (например, А123БВ77):")
        bot.register_next_step_handler(msg, process_client_car_number, client_id, msg.message_id, data)
    
    
    def process_client_car_number(message, client_id, user_message_id, data):
        """Обработка номера авто"""
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
            data['car_number'] = car_number
            msg = bot.send_message(message.chat.id, "Введите ФИО виновника ДТП, например, Иванов Иван Иванович")
            bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер авто\n"
                "Пример: А123БВ77 или А123БВ777\n"
                "Все буквы должны быть заглавными!"
            )
            bot.register_next_step_handler(msg, process_client_car_number, client_id, msg.message_id, data)

    def process_client_fio_culp(message, client_id, user_message_id, data):
        """Обработка марки авто виновника"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.split())<2:
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО клиента в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():  # Проверяем, что первая буква заглавная
                    msg = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО клиента в формате Иванов Иван Иванович")
                    user_message_id = message.message_id
                    bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
                    return
            data.update({"fio_culp": message.text})
            msg = bot.send_message(message.chat.id, "Введите марку, модель авто виновника ДТП:")
            bot.register_next_step_handler(msg, process_client_marks_culp, client_id, msg.message_id, data)

    def process_client_marks_culp(message, client_id, user_message_id, data):
        """Обработка марки авто виновника"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['marks_culp'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите номер авто виновника ДТП:")
        bot.register_next_step_handler(msg, process_client_number_auto_culp, client_id, msg.message_id, data)
    
    
    def process_client_number_auto_culp(message, client_id, user_message_id, data):
        """Обработка номера авто виновника"""
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
            data.update({'status': 'Деликт'})

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
                                 "{{ винФИО }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data['year']),str(data['client_id']), str(data["fio"]), str(data["fio_culp"])],
                                    "Шаблоны\\3. Деликт без ОСАГО\\Деликт (без ОСАГО) 1. Обложка дела.docx",
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
        

            try:
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx", 'rb') as document_file:
                    bot.send_document(
                        message.chat.id, 
                        document_file,
                    )   
            except FileNotFoundError:
                bot.send_message(message.chat.id, f"Файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            bot.send_message(
                int(data['user_id']),
                "✅ Запрос в ГИБДД успешно сформирован!\nИсковое заявление формируется. Мы сообщим вам, когда оно будет готово!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                reply_markup = keyboard
            )
            if int(data['user_id']) != user_id:
                bot.send_message(
                user_id,
                "✅ Запрос в ГИБДД успешно сформирован!",
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
                    call.message.chat.id, 
                    document_file,
                )   
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, f"Файл не найден")
        try:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx", 'rb') as document_file:
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
            "✅ Запросы в страховую и ГИБДД успешно сформированы!\nИсковое заявление формируется. Мы сообщим вам, когда оно будет готово!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
            reply_markup = keyboard
        )
        
        # Очищаем временные данные
        if client_id in user_temp_data:
            user_temp_data.pop(client_id, None)
        