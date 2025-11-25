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
insurance_companies = [
    ('АО "Согаз"', "SOGAZ_podal"),
    ('ПАО СК "Росгосстрах"', "Ros_podal"),
    ('САО "Ресо-Гарантия"', "Reco_podal"),
    ('АО "АльфаСтрахование"', "Alfa_podal"),
    ('СПАО "Ингосстрах"', "Ingo_podal"),
    ('САО "ВСК"', "VSK_podal"),
    ('ПАО «САК «Энергогарант»', "Energo_podal"),
    ('АО "ГСК "Югория"', "Ugo_podal"),
    ('ООО СК "Согласие"', "Soglasie_podal"),
    ('АО «Совкомбанк страхование»', "Sovko_podal"),
    ('АО "Макс"', "Maks_podal"),
    ('ООО СК "Сбербанк страхование"', "Sber_podal"),
    ('АО "Т-Страхование"', "T-ins_podal"),
    ('ПАО "Группа Ренессанс Страхование"', "Ren_podal"),
    ('АО СК "Чулпан"', "Chul_podal")
]

def create_insurance_keyboard(page=0, items_per_page=5):
    """Создает клавиатуру с пагинацией для страховых компаний"""
    keyboard = types.InlineKeyboardMarkup()
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    for name, callback_data in insurance_companies[start_idx:end_idx]:
        keyboard.add(types.InlineKeyboardButton(name, callback_data=callback_data))
    
    row_buttons = []
    
    if page > 0:
        row_buttons.append(types.InlineKeyboardButton('◀️ Назад', callback_data=f'podal_ins_page_{page-1}'))
    
    if end_idx < len(insurance_companies):
        row_buttons.append(types.InlineKeyboardButton('Еще ▶️', callback_data=f'podal_ins_page_{page+1}'))
    
    if row_buttons:
        keyboard.row(*row_buttons)
    
    keyboard.add(types.InlineKeyboardButton('Другое', callback_data="other_podal"))
    
    return keyboard

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
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку и модель авто:"
        )
        bot.register_next_step_handler_by_chat_id(user_id, process_client_car_marks, client_id, msg.message_id, data)
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
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\n"
                 f"В случае максимальной выплаты по ОСАГО либо отсутствия ОСАГО у Виновника ДТП разница фактического ущерба и компенсационной выплаты взыскивается с Виновника ДТП\n"
                 f"Примерная дата завершения дела (дата через 90 дней)\n\nВведите марку и модель авто:"
        )
        bot.register_next_step_handler_by_chat_id(user_id, process_client_car_marks, client_id, msg.message_id, data)
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
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text= f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\n"
                  f"Цессия - передача права требования компенсации с Виновника ДТП третьему лицу (продажа долга)\n\nВведите марку и модель авто:"
        )
        bot.register_next_step_handler_by_chat_id(user_id, process_client_car_marks, client_id, msg.message_id, data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("podal_viplatano_"))
    @prevent_double_click(timeout=3.0)
    def handle_podal_rem(call):
        client_id = call.data.replace("podal_viplatano_", "")
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
        data.update({'viborRem': 'no_viplatily'})
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку и модель авто:"
        )
        bot.register_next_step_handler_by_chat_id(user_id, process_client_car_marks, client_id, msg.message_id, data)


    def process_client_car_marks(message, client_id, user_message_id, contract_data):
        """Обработка марки и модели авто"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        contract_data.update({'marks' :message.text.strip()})
        
        msg = bot.send_message(message.chat.id, "Введите номер авто (например, А123БВ77):")
        bot.register_next_step_handler(msg, process_client_car_number, client_id, msg.message_id, contract_data)
    
    
    def process_client_car_number(message, client_id, user_message_id, contract_data):
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
            contract_data['car_number'] = car_number
            msg = bot.send_message(message.chat.id, "Введите год выпуска авто (например, 2025):")
            bot.register_next_step_handler(msg, process_client_car_year, client_id, msg.message_id, contract_data)
        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер авто\n"
                "Пример: А123БВ77 или А123БВ777\n"
                "Все буквы должны быть заглавными!"
            )
            bot.register_next_step_handler(msg, process_client_car_number, client_id, msg.message_id, contract_data)
    
    
    def process_client_car_year(message, client_id, user_message_id, contract_data):
        """Обработка года выпуска авто"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите корректный год выпуска авто (например, 2025):")
            bot.register_next_step_handler(msg, process_client_car_year, client_id, msg.message_id, contract_data)
        else:
            contract_data['year_auto'] = int(message.text.replace(" ", ""))
            
            user_temp_data[message.from_user.id].update({'contract_data' : contract_data})
            
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="podal_STS")
            btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="podal_PTS")
            keyboard.add(btn1)
            keyboard.add(btn2)

            bot.send_message(
                message.chat.id, 
                "Выберите документ о регистрации ТС:", 
                reply_markup=keyboard
            )
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["podal_STS", "podal_PTS", "podal_DKP"])
    @prevent_double_click(timeout=3.0)
    def callback_client_docs(call):
        """Обработка выбора документа о регистрации ТС"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']
        
        if call.data == "podal_STS":
            data['docs'] = "СТС"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_seria_docs, client_id, message.message_id, data)

        elif call.data == "podal_PTS":
            data['docs'] = "ПТС"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_seria_docs, client_id, message.message_id, data)
        else: 
            data['docs'] = "ДКП"
            data['seria_docs'] = "-"
            data['number_docs'] = "-"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДКП (ДД.ММ.ГГГГ):",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_data_docs, client_id, message.message_id, data)
    
    
    def process_client_seria_docs(message, client_id, user_message_id, data):
        """Обработка серии документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['seria_docs'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите номер документа о регистрации ТС:")
        bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)
    
    
    def process_client_number_docs(message, client_id, user_message_id, data):
        """Обработка номера документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit():
            data['number_docs'] = message.text.strip()
            msg = bot.send_message(
                message.chat.id,
                "Введите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ:"
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер документа о регистрации ТС (только цифры):"
            )
            bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)
    
    
    def process_client_data_docs(message, client_id, user_message_id, data):
        """Обработка даты выдачи документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data['data_docs'] = message.text.strip()
            
            user_temp_data[client_id]['contract_data'] = data
            
            # Создаем клавиатуру с пагинацией (первая страница)
            keyboard = create_insurance_keyboard(page=0)
            
            bot.send_message(
                message.chat.id, 
                "Выберите страховую компанию:", 
                reply_markup=keyboard
            )
            
        except ValueError:
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ:"
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('podal_ins_page_'))
    @prevent_double_click(timeout=3.0)
    def handle_client_insurance_pagination(call):
        """Обрабатывает пагинацию страховых компаний для клиента"""
        try:
            page = int(call.data.split('_')[3])
            keyboard = create_insurance_keyboard(page)
            
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error handling pagination: {e}")
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["Reco_podal", "Ugo_podal", "SOGAZ_podal", "Ingo_podal", "Ros_podal", "Maks_podal", "Energo_podal", "Sovko_podal", "Alfa_podal", "VSK_podal", "Soglasie_podal", "Sber_podal", "T-ins_podal", "Ren_podal", "Chul_podal", "other_podal"] and call.from_user.id in user_temp_data and 'contract_data' in user_temp_data[call.from_user.id])
    @prevent_double_click(timeout=3.0)
    def callback_client_insurance(call):
        """Обработка выбора страховой компании клиентом"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']
        insurance_mapping = {
            "SOGAZ_podal": 'АО "Согаз"',
            "Ros_podal": 'ПАО СК "Росгосстрах"',
            "Reco_podal": 'САО "Ресо-Гарантия"',
            "Alfa_podal": 'АО "АльфаСтрахование"',
            "Ingo_podal": 'СПАО "Ингосстрах"',
            "VSK_podal": 'САО "ВСК"',
            "Energo_podal": 'ПАО «САК «Энергогарант»',
            "Ugo_podal": 'АО "ГСК "Югория"',
            "Soglasie_podal": 'ООО СК "Согласие"',
            "Sovko_podal": 'АО «Совкомбанк страхование»',
            "Maks_podal": 'АО "Макс"',
            "Sber_podal": 'ООО СК "Сбербанк страхование"',
            "T-ins_podal": 'АО "Т-Страхование"',
            "Ren_podal": 'ПАО "Группа Ренессанс Страхование"',
            "Chul_podal": 'АО СК "Чулпан"'
        }
        
        if call.data in insurance_mapping:
            data['insurance'] = insurance_mapping[call.data]
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию страхового полиса:",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_seria_insurance, client_id, message.message_id, data)
        else: 
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании:",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_other_insurance, client_id, message.message_id, data)
    
    
    def process_client_other_insurance(message, client_id, user_message_id, data):
        """Обработка другой страховой компании"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['insurance'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите серию страхового полиса:")
        bot.register_next_step_handler(msg, process_client_seria_insurance, client_id, msg.message_id, data)
    
    
    def process_client_seria_insurance(message, client_id, user_message_id, data):
        """Обработка серии страхового полиса"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['seria_insurance'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите номер страхового полиса:")
        bot.register_next_step_handler(msg, process_client_number_insurance, client_id, msg.message_id, data)
    
    
    def process_client_number_insurance(message, client_id, user_message_id, data):
        """Обработка номера страхового полиса"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['number_insurance'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите дату страхового полиса в формате ДД.ММ.ГГГГ:")
        bot.register_next_step_handler(msg, process_client_date_insurance, client_id, msg.message_id, data)
    
    
    def process_client_date_insurance(message, client_id, user_message_id, data):
        """Обработка даты страхового полиса"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data['date_insurance'] = message.text.strip()
            msg = bot.send_message(message.chat.id, "Введите ФИО виновника ДТП в формате: Иванов Иван Иванович")
            bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату страхового полиса в формате ДД.ММ.ГГГГ:")
            bot.register_next_step_handler(msg, process_client_date_insurance, client_id, msg.message_id, data)
    
    
    def process_client_fio_culp(message, client_id, user_message_id, data):
        """Обработка ФИО виновника"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.split()) < 2:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите ФИО виновника ДТП в формате: Иванов Иван Иванович")
            bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():
                    msg = bot.send_message(message.chat.id, "❌ Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО виновника ДТП в формате: Иванов Иван Иванович")
                    bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
                    return
            
            data['fio_culp'] = message.text.strip()
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
                                [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["date_dtp"]),
                                    str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),str(data["date_ins_pod"]), 
                                    str(data["seria_docs"]), str(data["number_docs"]), str(data["city"]), str(data["date_ins"]), str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx")
                        output_filename = "3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx"
                    else:
                        replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                                "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                                "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                                "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                                "{{ ФИОк }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), str(data["number_not"]), str(data["date_dtp"]),
                                    str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),str(data["date_ins_pod"]), 
                                    str(data["seria_docs"]), str(data["number_docs"]), str(data["city"]), str(data["date_ins"]), str(data["fio_k"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx")
                        output_filename = "3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx"
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
