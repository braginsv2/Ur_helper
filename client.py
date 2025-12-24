from telebot import types
import re
import json
import time
import threading
import os
from PIL import Image
from io import BytesIO
from config import ID_CHAT, ID_TOPIC_CLIENT, ID_TOPIC_EXP, TEST
from datetime import datetime, timedelta
from database import (
    DatabaseManager,
    save_client_to_db_with_id_new,
    get_admin_from_db_by_user_id,
    search_clients_by_fio_in_db,
    get_client_from_db_by_client_id,
    get_client_contracts_list
)
from word_utils import create_fio_data_file, replace_words_in_word, get_next_business_date
from functools import wraps

active_callbacks = {}
callback_lock = threading.Lock()
db = DatabaseManager()

insurance_companies = [
    ('АО "Согаз"', "SOGAZ_client"),
    ('ПАО СК "Росгосстрах"', "Ros_client"),
    ('САО "Ресо-Гарантия"', "Reco_client"),
    ('АО "АльфаСтрахование"', "Alfa_client"),
    ('СПАО "Ингосстрах"', "Ingo_client"),
    ('САО "ВСК"', "VSK_client"),
    ('ПАО «САК «Энергогарант»', "Energo_client"),
    ('АО "ГСК "Югория"', "Ugo_client"),
    ('ООО СК "Согласие"', "Soglasie_client"),
    ('АО «Совкомбанк страхование»', "Sovko_client"),
    ('АО "Макс"', "Maks_client"),
    ('ООО СК "Сбербанк страхование"', "Sber_client"),
    ('АО "Т-Страхование"', "T-ins_client"),
    ('ПАО "Группа Ренессанс Страхование"', "Ren_client"),
    ('АО СК "Чулпан"', "Chul_client")
]

def create_insurance_keyboard(page=0, items_per_page=5, show_back=False):
    """Создает клавиатуру с пагинацией для страховых компаний"""
    keyboard = types.InlineKeyboardMarkup()
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    for name, callback_data in insurance_companies[start_idx:end_idx]:
        keyboard.add(types.InlineKeyboardButton(name, callback_data=callback_data))
    
    row_buttons = []
    
    if page > 0:
        row_buttons.append(types.InlineKeyboardButton('◀️ Назад', callback_data=f'client_ins_page_{page-1}'))
    
    if end_idx < len(insurance_companies):
        row_buttons.append(types.InlineKeyboardButton('Еще ▶️', callback_data=f'client_ins_page_{page+1}'))
    
    if row_buttons:
        keyboard.row(*row_buttons)
    
    keyboard.add(types.InlineKeyboardButton('Другое', callback_data="other_client"))
    
    keyboard.add(types.InlineKeyboardButton("◀️ Назад к году авто", callback_data="back_to_car_year_client"))
    
    return keyboard


def setup_client_handlers(bot, user_temp_data, upload_sessions):
    """Регистрация обработчиков для самостоятельного оформления клиентом"""
    def register_step_with_back(bot, message, handler_func, client_id, *args, back_callback=None):
        """
        Регистрирует обработчик с возможностью отмены через кнопку Назад
        """
        keyboard = types.InlineKeyboardMarkup()
        if back_callback:
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=back_callback))
        
        # Сохраняем ID сообщения для возможности удаления
        if client_id not in user_temp_data:
            user_temp_data[client_id] = {}
        user_temp_data[client_id]['last_message_id'] = message.message_id
        
        bot.register_next_step_handler(message, handler_func, client_id, message.message_id, *args)
        
        # Редактируем сообщение, добавляя кнопку если её нет
        if back_callback:
            try:
                bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    reply_markup=keyboard
                )
            except:
                pass
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
    # ========== НАЧАЛО ОФОРМЛЕНИЯ ДОГОВОРА КЛИЕНТОМ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data == "btn_client")
    @prevent_double_click(timeout=3.0)
    def btn_client_handler(call):
        """Оформить договор - Клиент проверяет существующие договоры"""
        client_id = call.from_user.id
        # Получаем данные клиента
        client_data = get_admin_from_db_by_user_id(client_id)
        
        if not client_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        start_new_contract_for_client(bot, call, client_id, user_temp_data)
    
    
    @bot.callback_query_handler(func=lambda call: call.data == "client_new_contract")
    @prevent_double_click(timeout=3.0)
    def client_new_contract_handler(call):
        """Новый договор с нуля"""
        client_id = call.from_user.id
        start_new_contract_for_client(bot, call, client_id, user_temp_data)
    
    
    def start_new_contract_for_client(bot, call, client_id, user_temp_data):
        """Начало заполнения нового договора с нуля"""
        client_data = get_admin_from_db_by_user_id(client_id)
        print(client_data)
        if not client_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        # Инициализируем данные
        if client_id not in user_temp_data:
            user_temp_data[client_id] = {}
        
        user_temp_data[client_id]['contract_data'] = {
            'fio': client_data.get('fio', ''),
            'fio_k': client_data.get('fio_k', ''),
            'number': client_data.get('number', ''),
            'city': client_data.get('city_admin', ''),
            'year': str(datetime.now().year)[-2:],
            'user_id': str(client_id),
            'creator_user_id': str(client_id),
            # ПАСПОРТНЫЕ ДАННЫЕ ИЗ БД
            'date_of_birth': client_data.get('date_of_birth', ''),
            'city_birth': client_data.get('city_birth', ''),
            'seria_pasport': client_data.get('seria_pasport', ''),
            'number_pasport': client_data.get('number_pasport', ''),
            'where_pasport': client_data.get('where_pasport', ''),
            'when_pasport': client_data.get('when_pasport', ''),
            'index_postal': client_data.get('index_postal', ''),
            'address': client_data.get('address', '')
        }
        
        ask_accident_type(bot, call, client_id, user_temp_data)
    
    
    def ask_accident_type(bot, call, client_id, user_temp_data):
        """Спросить тип обращения"""
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="client_accident_dtp")
        btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="client_accident_podal_zayavl")
        btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="client_accident_pit")
        btn4 = types.InlineKeyboardButton("❌ У виновника ДТП Нет ОСАГО", callback_data="client_accident_net_osago")
        
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)

        keyboard.add(types.InlineKeyboardButton("🔄 Назад", callback_data="callback_start"))

        contract_data = user_temp_data[client_id]['contract_data']
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📋 Оформление нового договора\n\n"
                f"👤 ФИО: {contract_data.get('fio', '')}\n"
                f"📱 Телефон: {contract_data.get('number', '')}\n\n"
                f"Выберите тип обращения",
            reply_markup=keyboard
        )
    
    # ========== ОБРАБОТЧИКИ ТИПА ОБРАЩЕНИЯ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("client_accident_"))
    @prevent_double_click(timeout=3.0)
    def handle_client_accident_type(call):
        """Обработка выбора типа обращения клиентом"""
        client_id = call.from_user.id
        
        if call.data == 'client_accident_dtp':
            user_temp_data[client_id]['contract_data']['accident'] = "ДТП"
            context = f"Вы попали в ДТП с участием двух и более автомобилей.\n\nСейчас вы находитесь на стадии оформления ДТП.\nЗаявление в страховую компанию ещё не подавали.\n\nПримерные сроки:\n\nПримерная дата первой выплаты от Страховой в случае отказа производить восстановительный ремонт {(datetime.now() + timedelta(days=20)).strftime('%d.%m.%Y')}\n\nПримерная дата завершения дела {(datetime.now() + timedelta(days=280)).strftime('%d.%m.%Y')}\n\nЭвакуатор вызывали?"
        elif call.data == 'client_accident_podal_zayavl':
            user_temp_data[client_id]['contract_data']['accident'] = "Подал заявление"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nЗаявление в страховую подали самостоятельно на выплату или ремонт.\nПримерная дата завершения дела {(datetime.now() + timedelta(days=280)).strftime('%d.%m.%Y')}\n\nЭвакуатор вызывали?"
        elif call.data == 'client_accident_pit':
            user_temp_data[client_id]['contract_data']['accident'] = "После ямы"
            context = f"🤖 Вы попали в ДТП по вине дорожных служб (ямы, люки, остатки ограждений и т.д.)\n\nЭвакуатор вызывали?"
        elif call.data == 'client_accident_net_osago':
            user_temp_data[client_id]['contract_data']['accident'] = "Нет ОСАГО"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nНаходитесь на стадии оформления в ГИБДД.\nДанная ситуация является не страховым случаем.\nКомпенсирует убыток Виновник ДТП.\nПримерная дата завершения дела {(datetime.now() + timedelta(days=90)).strftime('%d.%m.%Y')}\n\nЭвакуатор вызывали?"
        else:
            context = f"Эвакуатор вызывали?"
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="client_ev_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="client_ev_no")
        btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_accident_choice_client")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_accident_choice_client")
    @prevent_double_click(timeout=3.0)
    def back_to_accident_choice(call):
        """Возврат к выбору типа обращения"""
        client_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('accident', None)
            contract_data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="client_accident_dtp")
        btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="client_accident_podal_zayavl")
        btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="client_accident_pit")
        btn4 = types.InlineKeyboardButton("❌ У виновника ДТП Нет ОСАГО", callback_data="client_accident_net_osago")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(types.InlineKeyboardButton("🔄 Назад", callback_data="callback_start"))
        
        bot.send_message(
            call.message.chat.id,
            f"📋 Оформление нового договора\n\n"
            f"👤 ФИО: {contract_data.get('fio', '')}\n"
            f"📱 Телефон: {contract_data.get('number', '')}\n\n"
            f"Выберите тип обращения",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["client_ev_yes", "client_ev_no"])
    @prevent_double_click(timeout=3.0)
    def handle_client_evacuator(call):
        """Обработка эвакуатора"""
        client_id = call.from_user.id

        if call.data == "client_ev_yes":
            user_temp_data[client_id]['contract_data']['ev'] = "Да"
        elif call.data == "client_ev_no":
            user_temp_data[client_id]['contract_data']['ev'] = "Нет"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_client"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_client"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_accident_choice_client"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату ДТП:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_date_today_client", "dtp_date_other_client"])
    @prevent_double_click(timeout=3.0)
    def handle_dtp_date_choice(call):
        agent_id = call.from_user.id
        
        if call.data == "dtp_date_today_client":
            # Красноярское время
            from datetime import datetime
            import pytz
            krasnoyarsk_tz = pytz.timezone('Asia/Krasnoyarsk')
            date_dtp = datetime.now(krasnoyarsk_tz).strftime("%d.%m.%Y")
            user_temp_data[agent_id]['contract_data']['date_dtp'] = date_dtp
            
            # Продолжить к следующему шагу (время ДТП)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_choice_client"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Дата ДТП: {date_dtp}\n\nВведите время ДТП (ЧЧ:ММ):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(call.message, process_client_dtp_time, agent_id, call.message.message_id)
            
        elif call.data == "dtp_date_other_client":
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_choice_client"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДТП (ДД.ММ.ГГГГ):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(call.message, process_client_dtp_date, agent_id, call.message.message_id) 
    
    
    def process_client_dtp_date(message, client_id, prev_msg_id):
        """Обработка даты ДТП"""
        # Проверяем, не была ли нажата кнопка (callback_query обрабатывается отдельно)
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        date_text = message.text.strip()
        
        try:
            input_date = datetime.strptime(date_text, "%d.%m.%Y")
            current_date = datetime.now()
            three_years_ago = current_date - timedelta(days=3*365 + 1)

            if input_date > current_date:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_choice_client"))
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Дата ДТП не может быть в будущем!\nВведите корректную дату ДТП:",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, process_client_dtp_date, client_id, msg.message_id)
                return
            
            if input_date < three_years_ago:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_choice_client"))
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Прошло более трех лет!\nВведите корректную дату ДТП:",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, process_client_dtp_date, client_id, msg.message_id)
                return
            
            user_temp_data[client_id]['contract_data']['date_dtp'] = date_text
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_choice_client"))
            msg = bot.send_message(
                message.chat.id, 
                "Введите время ДТП (ЧЧ:ММ):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_dtp_time, client_id, msg.message_id)
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_choice_client"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите дату ДТП в формате ДД.ММ.ГГГГ:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_dtp_date, client_id, msg.message_id)
            return
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dtp_date_choice_client")
    @prevent_double_click(timeout=3.0)
    def back_to_dtp_date_choice(call):
        """Возврат к выбору даты ДТП"""
        agent_id = call.from_user.id
        
        # Очищаем обработчики для этого чата
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        # Удаляем сообщение
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # Возвращаемся к выбору даты
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_client"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_client"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="client_new_contract"))
        
        bot.send_message(
            call.message.chat.id,
            "Выберите дату ДТП:",
            reply_markup=keyboard
        )
    def process_client_dtp_time(message, client_id, prev_msg_id):
        """Обработка времени ДТП"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        time_text = message.text.strip()
        
        if not re.match(r'^\d{2}:\d{2}$', time_text):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_input_client"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат времени. Введите в формате ЧЧ:ММ:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_dtp_time, client_id, msg.message_id)
            return
        
        user_temp_data[client_id]['contract_data']['time_dtp'] = time_text
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_time_input_client"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите адрес ДТП:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_dtp_address, client_id, msg.message_id)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dtp_date_input_client")
    @prevent_double_click(timeout=3.0)
    def back_to_dtp_date_input(call):
        """Возврат к вводу даты ДТП"""
        agent_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_choice_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите дату ДТП (ДД.ММ.ГГГГ):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_dtp_date, agent_id, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dtp_time_input_client")
    @prevent_double_click(timeout=3.0)
    def back_to_dtp_time_input(call):
        """Возврат к вводу времени ДТП"""
        agent_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        # Удаляем текущее значение времени, чтобы можно было ввести заново
        if agent_id in user_temp_data and 'contract_data' in user_temp_data[agent_id]:
            user_temp_data[agent_id]['contract_data'].pop('time_dtp', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_date_input_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите время ДТП (ЧЧ:ММ):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_dtp_time, agent_id, msg.message_id)
    def process_client_dtp_address(message, client_id, prev_msg_id):
        """Обработка адреса ДТП"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        user_temp_data[client_id]['contract_data']['address_dtp'] = message.text.strip()
        
        if user_temp_data[client_id]['contract_data']['ev'] == 'Да':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_address_input_client"))
            msg = bot.send_message(
                message.chat.id, 
                "Введите адрес местонахождения транспортного средства, где будет произведена оценка ущерба.",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_dtp_address_park, client_id, msg.message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd_client"))
            keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro_client"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_address_input_client"))
            msg = bot.send_message(
                message.chat.id, 
                "Выберите документ фиксации ДТП", 
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dtp_address_input_client")
    @prevent_double_click(timeout=3.0)
    def back_to_dtp_address_input(call):
        """Возврат к вводу адреса ДТП"""
        agent_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if agent_id in user_temp_data and 'contract_data' in user_temp_data[agent_id]:
            user_temp_data[agent_id]['contract_data'].pop('address_dtp', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_time_input_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите адрес ДТП:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_dtp_address, agent_id, msg.message_id)
    def process_client_dtp_address_park(message, client_id, prev_msg_id):
        """Обработка адреса парковки"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        user_temp_data[client_id]['contract_data']['address_park'] = message.text.strip()

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd_client"))
        keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro_client"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_park_client"))
        msg = bot.send_message(
            message.chat.id, 
            "Выберите документ фиксации ДТП", 
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_address_park_client")
    @prevent_double_click(timeout=3.0)
    def back_to_address_park(call):
        """Возврат к вводу адреса парковки"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('address_park', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_address_input_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите адрес местонахождения транспортного средства, где будет произведена оценка ущерба.",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_dtp_address_park, client_id, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_gibdd_client", "dtp_evro_client"])
    @prevent_double_click(timeout=3.0)
    def handle_dtp_gibdd_evro(call):
        agent_id = call.from_user.id
        
        if call.data == "dtp_gibdd_client":
            user_temp_data[agent_id]['contract_data']['who_dtp'] = "По форме ГИБДД"
        elif call.data == "dtp_evro_client":
            user_temp_data[agent_id]['contract_data']['who_dtp'] = "Евро-протокол"

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # ИЗМЕНЕНО: Сначала запрашиваем данные авто клиента
        contract_data = user_temp_data[agent_id]['contract_data']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_fixation_choice_client"))
        
        msg = bot.send_message(
            call.message.chat.id,
            "Введите марку и модель вашего авто:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_car_marks_early, agent_id, msg.message_id, contract_data)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_fixation_choice_client")
    @prevent_double_click(timeout=3.0)
    def back_to_fixation_choice(call):
        """Возврат к выбору документа фиксации ДТП"""
        agent_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if agent_id in user_temp_data and 'contract_data' in user_temp_data[agent_id]:
            user_temp_data[agent_id]['contract_data'].pop('who_dtp', None)
            user_temp_data[agent_id]['contract_data'].pop('marks', None)
            contract_data = user_temp_data[agent_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd_client"))
        keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro_client"))
        
        # Проверяем, был ли эвакуатор
        if contract_data.get('ev') == 'Да':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_park_client"))
        else:
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_address_input_client"))
        
        bot.send_message(
            call.message.chat.id,
            "Выберите документ фиксации ДТП",
            reply_markup=keyboard
        )
    def process_client_car_marks_early(message, client_id, user_message_id, contract_data):
        """Обработка марки и модели авто клиента"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        contract_data['marks'] = message.text.strip()
        user_temp_data[client_id]['contract_data'] = contract_data
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_early_{client_id}")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_marks_client")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите номер вашего авто (например, А123БВ77):", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_car_number_early, client_id, msg.message_id, contract_data)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_car_marks_client")
    @prevent_double_click(timeout=3.0)
    def back_to_car_marks(call):
        """Возврат к вводу марки авто"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('marks', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # Возврат к выбору документа фиксации ДТП
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd_client"))
        keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro_client"))
        
        # Проверяем, был ли эвакуатор
        contract_data = user_temp_data[client_id].get('contract_data', {})
        if contract_data.get('ev') == 'Да':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_park_client"))
        else:
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_address_input_client"))
        
        bot.send_message(
            call.message.chat.id,
            "Выберите документ фиксации ДТП",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("non_standart_number_car_early_"))
    @prevent_double_click(timeout=3.0)
    def handle_client_non_standart_number_early(call):
        client_id = int(call.data.replace("non_standart_number_car_early_", ""))
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        contract_data = user_temp_data[client_id]['contract_data']
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер вашего авто",
            reply_markup=None
        )
        bot.register_next_step_handler(msg, process_client_car_number_non_standart_early, client_id, msg.message_id, contract_data)


    def process_client_car_number_non_standart_early(message, client_id, user_message_id, contract_data):
        """Обработка номера авто клиента - нестандартный формат"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        contract_data['car_number'] = car_number
        user_temp_data[client_id]['contract_data'] = contract_data
        
        # Запрашиваем год авто
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_number_client"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите год выпуска авто (например, 2025):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_car_year_early, client_id, msg.message_id, contract_data)


    def process_client_car_number_early(message, client_id, user_message_id, contract_data):
        """Обработка номера авто клиента"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        
        # Разрешенные русские буквы на номерах (совпадают с латинскими)
        allowed_letters = 'АВЕКМНОРСТУХ'
        
        # Паттерн: 1 буква + 3 цифры + 2 буквы + 2-3 цифры региона
        pattern = r'^([АВЕКМНОРСТУХ]{1})(\d{3})([АВЕКМНОРСТУХ]{2})(\d{2,3})$'
        
        original_text = message.text.replace(" ", "")
        has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
        
        # Проверяем формат
        match = re.match(pattern, car_number)
        
        if has_lowercase:
            user_temp_data[client_id]['contract_data'] = contract_data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_marks_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n"
                "Все буквы должны быть заглавными!\n\n"
                "Введите номер вашего авто (Пример: А123БВ77)",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_car_number_early, client_id, msg.message_id, contract_data)
            return
        
        if not match:
            user_temp_data[client_id]['contract_data'] = contract_data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_marks_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n\n"
                "📝 Правила ввода:\n"
                "• Формат: А123БВ77 или А123БВ777\n"
                f"• Разрешенные буквы: {', '.join(allowed_letters)}\n"
                "• Все буквы заглавные\n\n"
                "Введите номер вашего авто:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_car_number_early, client_id, msg.message_id, contract_data)
            return
        
        # Извлекаем части номера
        letter1 = match.group(1)  # Первая буква
        digits = match.group(2)   # 3 цифры
        letters2 = match.group(3) # 2 буквы
        region = match.group(4)   # Код региона (2-3 цифры)
        
        # Проверяем, что цифры не состоят только из нулей
        if digits == "000":
            user_temp_data[client_id]['contract_data'] = contract_data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_marks_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Основные цифры номера не могут быть 000\n\n"
                "Введите корректный номер авто (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_car_number_early, client_id, msg.message_id, contract_data)
            return
        
        # Проверяем, что код региона не состоит только из нулей
        if region == "00" or region == "000":
            user_temp_data[client_id]['contract_data'] = contract_data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_marks_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Код региона не может быть 00 или 000\n\n"
                "Введите корректный номер авто (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_car_number_early, client_id, msg.message_id, contract_data)
            return
        
        # Все проверки пройдены - сохраняем номер
        contract_data['car_number'] = car_number
        user_temp_data[client_id]['contract_data'] = contract_data
        
        # Запрашиваем год авто
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_number_client"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите год выпуска авто (например, 2025):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_car_year_early, client_id, msg.message_id, contract_data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_car_number_client")
    @prevent_double_click(timeout=3.0)
    def back_to_car_number(call):
        """Возврат к вводу номера авто"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('car_number', None)
            contract_data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_early_{client_id}")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_marks_client")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            call.message.chat.id,
            "Введите номер вашего авто (например, А123БВ77):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_car_number_early, client_id, msg.message_id, contract_data)

    def process_client_car_year_early(message, client_id, user_message_id, contract_data):
        """Обработка года выпуска авто клиента"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        text = message.text.replace(" ", "")
        
        # Проверка формата
        if len(text) != 4 or not text.isdigit():
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_number_client"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите корректный год выпуска авто (например, 2025):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_car_year_early, client_id, msg.message_id, contract_data)
            return
        
        year = int(text)
        current_year = datetime.now().year
        
        # Проверка диапазона
        if not (1900 < year <= current_year):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_number_client"))
            msg = bot.send_message(
                message.chat.id, 
                f"❌ Год должен быть в диапазоне от 1901 до {current_year}!\nВведите корректный год выпуска авто:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_car_year_early, client_id, msg.message_id, contract_data)
            return
        
        # Сохраняем год
        contract_data['year_auto'] = year
        user_temp_data[client_id]['contract_data'] = contract_data
        
        # ПЕРЕХОД К ВЫБОРУ СТРАХОВОЙ
        keyboard = create_insurance_keyboard(page=0,show_back=True)
        bot.send_message(
            message.chat.id,
            "Выберите страховую компанию виновника ДТП:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_insurance_client")
    @prevent_double_click(timeout=3.0)
    def back_to_date_insurance(call):
        """Возврат к вводу даты полиса"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('date_insurance', None)
            data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_insurance_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_date_insurance_early, client_id, msg.message_id, data)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_car_year_client")
    @prevent_double_click(timeout=3.0)
    def back_to_car_year(call):
        """Возврат к вводу года авто"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('year_auto', None)
            contract_data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_car_number_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите год выпуска авто (например, 2025):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_car_year_early, client_id, msg.message_id, contract_data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('client_ins_page_'))
    @prevent_double_click(timeout=3.0)
    def handle_client_insurance_pagination_early(call):
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


    @bot.callback_query_handler(func=lambda call: call.data in ["Reco_client", "Ugo_client", "SOGAZ_client", "Ingo_client", "Ros_client", "Maks_client", "Energo_client", "Sovko_client", "Alfa_client", "VSK_client", "Soglasie_client", "Sber_client", "T-ins_client", "Ren_client", "Chul_client", "other_client"] and call.from_user.id in user_temp_data and 'contract_data' in user_temp_data[call.from_user.id])
    @prevent_double_click(timeout=3.0)
    def callback_client_insurance_early(call):
        """Обработка выбора страховой компании клиентом ДО договора"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']
        insurance_mapping = {
            "SOGAZ_client": 'АО "Согаз"',
            "Ros_client": 'ПАО СК "Росгосстрах"',
            "Reco_client": 'САО "Ресо-Гарантия"',
            "Alfa_client": 'АО "АльфаСтрахование"',
            "Ingo_client": 'СПАО "Ингосстрах"',
            "VSK_client": 'САО "ВСК"',
            "Energo_client": 'ПАО «САК «Энергогарант»',
            "Ugo_client": 'АО "ГСК "Югория"',
            "Soglasie_client": 'ООО СК "Согласие"',
            "Sovko_client": 'АО «Совкомбанк страхование»',
            "Maks_client": 'АО "Макс"',
            "Sber_client": 'ООО СК "Сбербанк страхование"',
            "T-ins_client": 'АО "Т-Страхование"',
            "Ren_client": 'ПАО "Группа Ренессанс Страхование"',
            "Chul_client": 'АО СК "Чулпан"'
        }
        
        if call.data in insurance_mapping:
            data['insurance'] = insurance_mapping[call.data]
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_insurance_choice_client"))
            
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию страхового полиса:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(message, process_client_seria_insurance_early, client_id, message.message_id, data)
        else: 
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_insurance_choice_client"))
            
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(message, process_client_other_insurance_early, client_id, message.message_id, data)


    def process_client_other_insurance_early(message, client_id, user_message_id, data):
        """Обработка другой страховой компании"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['insurance'] = message.text.strip()
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_insurance_choice_client"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите серию страхового полиса:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_seria_insurance_early, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_insurance_choice_client")
    @prevent_double_click(timeout=3.0)
    def back_to_insurance_choice(call):
        """Возврат к выбору страховой компании"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('insurance', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = create_insurance_keyboard(page=0, show_back=True)
        bot.send_message(
            call.message.chat.id,
            "Выберите страховую компанию:",
            reply_markup=keyboard
        )
    def process_client_seria_insurance_early(message, client_id, user_message_id, data):
        """Обработка серии страхового полиса"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['seria_insurance'] = message.text.strip()
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_insurance_client"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите номер страхового полиса:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_number_insurance_early, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_seria_insurance_client")
    @prevent_double_click(timeout=3.0)
    def back_to_seria_insurance(call):
        """Возврат к вводу серии полиса"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('seria_insurance', None)
            data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = create_insurance_keyboard(page=0, show_back=True)
        bot.send_message(
            call.message.chat.id,
            "Выберите страховую компанию:",
            reply_markup=keyboard
        )
    def process_client_number_insurance_early(message, client_id, user_message_id, data):
        """Обработка номера страхового полиса"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['number_insurance'] = message.text.strip()
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_insurance_client"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_date_insurance_early, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_insurance_client")
    @prevent_double_click(timeout=3.0)
    def back_to_number_insurance(call):
        """Возврат к вводу номера полиса"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('number_insurance', None)
            data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_seria_insurance_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите серию страхового полиса:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_seria_insurance_early, client_id, msg.message_id, data)
    def process_client_date_insurance_early(message, client_id, user_message_id, data):
        """Обработка даты страхового полиса"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            # Парсим введенную дату
            insurance_date = datetime.strptime(message.text, "%d.%m.%Y")
            current_date = datetime.now()
            
            # Вычисляем дату 1 года назад от сегодняшнего дня
            two_years_ago = current_date - timedelta(days=365)  # 1 года = 365 дней
            
            # Проверка: дата не в будущем
            if insurance_date > current_date:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_insurance_client"))
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Дата не может быть в будущем!\n"
                    "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, process_client_date_insurance_early, client_id, msg.message_id, data)
                return
            
            # Проверка: дата не старше 1 года
            if insurance_date < two_years_ago:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_insurance_client"))
                msg = bot.send_message(
                    message.chat.id, 
                    f"❌ Полис не может быть старше 1 года!\n"
                    f"Минимальная дата: {two_years_ago.strftime('%d.%m.%Y')}\n\n"
                    "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, process_client_date_insurance_early, client_id, msg.message_id, data)
                return
            
            # Все проверки пройдены - сохраняем дату
            data['date_insurance'] = message.text.strip()
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_insurance_client"))
            msg = bot.send_message(
                message.chat.id, 
                "Введите ФИО виновника ДТП в формате: Иванов Иван Иванович",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_fio_culp_early, client_id, msg.message_id, data)
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_insurance_client"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\n"
                "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_date_insurance_early, client_id, msg.message_id, data)


    def process_client_fio_culp_early(message, client_id, user_message_id, data):
        """Обработка ФИО виновника"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.split()) < 2:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_insurance_client"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите ФИО виновника ДТП в формате: Иванов Иван Иванович",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_fio_culp_early, client_id, msg.message_id, data)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_insurance_client"))
                    msg = bot.send_message(
                        message.chat.id, 
                        "❌ Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО виновника ДТП в формате: Иванов Иван Иванович",
                        reply_markup=keyboard
                    )
                    bot.register_next_step_handler(msg, process_client_fio_culp_early, client_id, msg.message_id, data)
                    return
            
            data['fio_culp'] = message.text.strip()
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_fio_culp_client"))
            msg = bot.send_message(
                message.chat.id, 
                "Введите марку, модель авто виновника ДТП:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_marks_culp_early, client_id, msg.message_id, data)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_fio_culp_client")
    @prevent_double_click(timeout=3.0)
    def back_to_fio_culp(call):
        """Возврат к вводу даты полиса"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('fio_culp', None)
            data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_insurance_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_date_insurance_early, client_id, msg.message_id, data)

    def process_client_marks_culp_early(message, client_id, user_message_id, data):
        """Обработка марки авто виновника"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['marks_culp'] = message.text.strip()
        user_temp_data[client_id]['contract_data'] = data
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_culp_early_{client_id}")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_marks_culp_client")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите номер авто виновника ДТП:", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_number_auto_culp_early, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_marks_culp_client")
    @prevent_double_click(timeout=3.0)
    def back_to_marks_culp(call):
        """Возврат к вводу ФИО виновника"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('marks_culp', None)
            data = user_temp_data[client_id]['contract_data']
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_fio_culp_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите ФИО виновника ДТП в формате: Иванов Иван Иванович",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_client_fio_culp_early, client_id, msg.message_id, data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("non_standart_number_car_culp_early_"))
    @prevent_double_click(timeout=3.0)
    def handle_client_non_standart_number_culp_early(call):
        client_id = int(call.data.replace("non_standart_number_car_culp_early_", ""))
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        contract_data = user_temp_data[client_id]['contract_data']
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер авто виновника ДТП",
            reply_markup=None
        )
        bot.register_next_step_handler(msg, process_client_car_number_non_standart_culp_early, client_id, msg.message_id, contract_data)


    def process_client_car_number_non_standart_culp_early(message, client_id, user_message_id, contract_data):
        """Обработка номера авто виновника - нестандартный формат"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        contract_data['number_auto_culp'] = car_number
        user_temp_data[client_id]['contract_data'] = contract_data
        
        # Показываем итоговые данные
        show_client_contract_summary(bot, message.chat.id, client_id, user_temp_data)


    def process_client_number_auto_culp_early(message, client_id, user_message_id, data):
        """Обработка номера авто виновника - ФИНАЛ ПЕРЕД ПОКАЗОМ ИТОГОВ"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        
        # Разрешенные русские буквы на номерах (совпадают с латинскими)
        allowed_letters = 'АВЕКМНОРСТУХ'
        
        # Паттерн: 1 буква + 3 цифры + 2 буквы + 2-3 цифры региона
        pattern = r'^([АВЕКМНОРСТУХ]{1})(\d{3})([АВЕКМНОРСТУХ]{2})(\d{2,3})$'
        
        original_text = message.text.replace(" ", "")
        has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
        
        # Проверяем формат
        match = re.match(pattern, car_number)
        
        if has_lowercase:
            user_temp_data[client_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_culp_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_marks_culp_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n"
                "Все буквы должны быть заглавными!\n\n"
                "Введите номер авто виновника ДТП (Пример: А123БВ77)",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_number_auto_culp_early, client_id, msg.message_id, data)
            return
        
        if not match:
            user_temp_data[client_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_culp_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_marks_culp_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n\n"
                "📝 Правила ввода:\n"
                "• Формат: А123БВ77 или А123БВ777\n"
                f"• Разрешенные буквы: {', '.join(allowed_letters)}\n"
                "• Все буквы заглавные\n\n"
                "Введите номер авто виновника ДТП:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_number_auto_culp_early, client_id, msg.message_id, data)
            return
        
        # Извлекаем части номера
        letter1 = match.group(1)  # Первая буква
        digits = match.group(2)   # 3 цифры
        letters2 = match.group(3) # 2 буквы
        region = match.group(4)   # Код региона (2-3 цифры)
        
        # Проверяем, что цифры не состоят только из нулей
        if digits == "000":
            user_temp_data[client_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_culp_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_marks_culp_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Основные цифры номера не могут быть 000\n\n"
                "Введите корректный номер авто виновника ДТП (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_number_auto_culp_early, client_id, msg.message_id, data)
            return
        
        # Проверяем, что код региона не состоит только из нулей
        if region == "00" or region == "000":
            user_temp_data[client_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_culp_early_{client_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_marks_culp_client")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Код региона не может быть 00 или 000\n\n"
                "Введите корректный номер авто виновника ДТП (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_client_number_auto_culp_early, client_id, msg.message_id, data)
            return
        
        # Все проверки пройдены - сохраняем номер
        data['number_auto_culp'] = str(car_number)
        user_temp_data[client_id]['contract_data'] = data
        
        # Показываем итоговые данные
        show_client_contract_summary(bot, message.chat.id, client_id, user_temp_data)
    
    def show_client_contract_summary(bot, chat_id, client_id, user_temp_data):
        """Показ итоговых данных клиенту"""
        # ДОБАВЛЕНО: Проверка и инициализация
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.send_message(chat_id, "❌ Ошибка: данные потеряны")
            return
        
        contract_data = user_temp_data[client_id]['contract_data']
        
        summary = "📋 <b>Проверьте данные договора:</b>\n\n"
        summary += f"👤 ФИО: {contract_data.get('fio', '')}\n"
        summary += f"📅 Дата рождения: {contract_data.get('date_of_birth', '')}\n"
        summary += f"📍 Город: {contract_data.get('city', '')}\n"
        summary += f"📄 Паспорт: {contract_data.get('seria_pasport', '')} {contract_data.get('number_pasport', '')}\n"
        summary += f"📍 Выдан: {contract_data.get('where_pasport', '')}\n"
        summary += f"📅 Дата выдачи: {contract_data.get('when_pasport', '')}\n"
        summary += f"📮 Индекс: {contract_data.get('index_postal', '')}\n"
        summary += f"🏠 Адрес: {contract_data.get('address', '')}\n"
        summary += f"🚗 Дата ДТП: {contract_data.get('date_dtp', '')}\n"
        summary += f"⏰ Время ДТП: {contract_data.get('time_dtp', '')}\n"
        summary += f"📍 Адрес ДТП: {contract_data.get('address_dtp', '')}\n"
        summary += f"📍 Фиксация ДТП: {contract_data.get('who_dtp', '')}\n"
        summary += f"🚗 Марка/модель вашего авто: {contract_data.get('marks', '')}\n"
        summary += f"🚗 Номер вашего авто: {contract_data.get('car_number', '')}\n"
        summary += f"📅 Год выпуска: {contract_data.get('year_auto', '')}\n"
        summary += f"🏢 Страховая: {contract_data.get('insurance', '')}\n"
        summary += f"📋 Полис: {contract_data.get('seria_insurance', '')} {contract_data.get('number_insurance', '')}\n"
        summary += f"📅 Дата полиса: {contract_data.get('date_insurance', '')}\n"
        summary += f"👤 Виновник ДТП: {contract_data.get('fio_culp', '')}\n"
        summary += f"🚗 Авто виновника: {contract_data.get('marks_culp', '')} {contract_data.get('number_auto_culp', '')}\n"

        keyboard = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("✅ Подтвердить", callback_data="client_power_attorney_yes")
        btn_no = types.InlineKeyboardButton("❌ Отклонить", callback_data="client_power_attorney_no")
        keyboard.add(btn_yes, btn_no)
        
        bot.send_message(chat_id, summary, parse_mode='HTML', reply_markup=keyboard)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("client_power_attorney_"))
    @prevent_double_click(timeout=3.0)
    def handle_client_power_attorney(call):
        """Обработка ответа про нотариальную доверенность"""
        client_id = call.from_user.id
        
        # КРИТИЧЕСКИ ВАЖНО: проверяем наличие данных
        if client_id not in user_temp_data:
            bot.answer_callback_query(call.id, "❌ Данные потеряны (сессия истекла)", show_alert=True)
            return
        
        if 'contract_data' not in user_temp_data[client_id]:
            bot.answer_callback_query(call.id, "❌ Данные договора не найдены", show_alert=True)
            return
        
        contract_data = user_temp_data[client_id]['contract_data']
        
        # ОТЛАДКА
        print(f"DEBUG handle_client_power_attorney: client_id={client_id}")
        print(f"DEBUG contract_data keys: {contract_data.keys()}")
        
        if call.data == "client_power_attorney_yes":

            keyboard = types.InlineKeyboardMarkup()
            btn_yes = types.InlineKeyboardButton("1", callback_data=f"client_not_dov_yes")
            btn_no = types.InlineKeyboardButton("2", callback_data=f"client_not_dov_no")
            btn_no2 = types.InlineKeyboardButton("3", callback_data=f"client_not_dov_no2")
            keyboard.add(btn_yes, btn_no, btn_no2)
            context = """📝 Необходимо выбрать, на каком этапе будет оформлена нотариальная доверенность:

1. С начала — полное сопровождение от подачи заявления в страховую до получения полной компенсации. Юрист формирует и подаёт документы, анализирует ответы и представляет ваши интересы в суде.

2. Перед дополнительным осмотром авто страховой компанией — первичное заявление в страховую вы подаёте самостоятельно. Далее к работе подключается наш юрист и ведёт дело до получения полной компенсации.

3. После получения ответа от страховой — вы самостоятельно подаёте первичное заявление в страховую, назначаете и присутствуете на дополнительном осмотре, получаете все документы от страховой компании. Далее юрист подключается к процессу.
"""
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=context,
                reply_markup = keyboard
            )
            
        else:  # client_power_attorney_no
            try:
                # КРИТИЧЕСКИ ВАЖНО: НЕ изменяем contract_data, работаем с тем что есть
                # Данные УЖЕ в user_temp_data[client_id]['contract_data']
                user_temp_data[client_id]['contract_data'] = contract_data
                # ОТЛАДКА
                print(f"DEBUG Отклонение: contract_data сохранен с ключами: {contract_data.keys()}")
                print(f"DEBUG user_temp_data[{client_id}] содержит: {user_temp_data[client_id].keys()}")
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("✏️ Редактировать данные", callback_data=f"start_edit_contract_client"))
                keyboard.add(types.InlineKeyboardButton("🔄 Назад", callback_data="back_client_contract"))
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Вы отклонили данные договора.\n\nВы можете отредактировать существующие данные.",
                    reply_markup=keyboard
                )

            except Exception as e:
                print(f"Ошибка отклонения данных: {e}")
                import traceback
                traceback.print_exc()

    @bot.callback_query_handler(func=lambda call: call.data in ["client_not_dov_yes", "client_not_dov_no", "client_not_dov_no2"])
    @prevent_double_click(timeout=3.0)
    def handle_dtp_gibdd_evro(call):
        client_id = call.from_user.id
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.send_message(call.message.chat.id, "❌ Ошибка: данные потеряны")
            return
        
        contract_data = user_temp_data[client_id]['contract_data']
        if call.data == "client_not_dov_yes":
            user_temp_data[client_id]['contract_data']['sobstvenik'] = "С начала"
        elif call.data == "client_not_dov_no":
            user_temp_data[client_id]['contract_data']['sobstvenik'] = "После заявления в страховую"
        elif call.data == "client_not_dov_no2":
            user_temp_data[client_id]['contract_data']['sobstvenik'] = "После ответа от страховой"
        contract_data['status'] = 'Оформлен договор'
            
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📝 Данные подтверждены\n\n⏳ Сохраняем договор..."
        )
        
        # Сохраняем в БД и получаем client_id
        try:
            client_contract_id, updated_data = save_client_to_db_with_id_new(contract_data)
            contract_data.update(updated_data)
            contract_data['client_id'] = client_contract_id
            print(contract_data)
            # ВАЖНО: обновляем в user_temp_data
            user_temp_data[client_id]['contract_data'] = contract_data
            
            print(f"Договор сохранен клиентом с client_id: {client_contract_id}")
            
            # Создаем файл с данными
            create_fio_data_file(contract_data)
            
            # Заполняем шаблон юр договора
            replace_words_in_word(
                ["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", "{{ Дата }}", "{{ ФИО }}", 
                "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
                "{{ Паспорт_когда }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Дата_ДТП }}", 
                "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                [str(contract_data['year']), str(client_contract_id), str(contract_data["city"]), 
                str(datetime.now().strftime("%d.%m.%Y")), str(contract_data["fio"]), 
                str(contract_data["date_of_birth"]), str(contract_data["seria_pasport"]), 
                str(contract_data["number_pasport"]), str(contract_data["where_pasport"]),
                str(contract_data["when_pasport"]), str(contract_data["index_postal"]), 
                str(contract_data["address"]), str(contract_data["date_dtp"]), 
                str(contract_data["time_dtp"]), str(contract_data["address_dtp"]), 
                str(contract_data['fio_k'])],
                "Шаблоны/1. ДТП/1. На ремонт/2. Юр договор.docx",
                f"clients/{client_contract_id}/Документы/Юр договор.docx"
            )
            replace_words_in_word(
                ["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}", 
                "{{ NКлиента }}", "{{ ФИО }}", "{{ Страховая }}", "{{ винФИО }}"],
                [str(contract_data["date_dtp"]), str(contract_data["time_dtp"]), 
                str(contract_data["address_dtp"]), str(contract_data["marks"]), 
                str(contract_data["car_number"]), str(contract_data['year']), 
                str(client_contract_id), str(contract_data["fio"]), 
                str(contract_data["insurance"]), str(contract_data["fio_culp"])],
                "Шаблоны/1. ДТП/1. На ремонт/1. Обложка дела.docx",
                f"clients/{client_contract_id}/Документы/Обложка дела.docx"
            )
            if TEST == 'No':
                try:
                    bot.send_message(
                        chat_id=ID_CHAT,
                        message_thread_id=ID_TOPIC_CLIENT,
                        text=f"Клиент {contract_data['client_id']} {contract_data['fio']} добавлен"
                    )
                except Exception as e:
                    print(f"Ошибка при отправке сообщения в тему: {e}")
            import shutil
            import os

            fio_folder = contract_data.get('fio', '')
            source_folder = f"admins_info/{fio_folder}"
            destination_folder = f"clients/{client_contract_id}/Документы"

            # Список файлов для копирования (ищем файлы начинающиеся с этих имен)
            files_to_copy = []

            try:
                if os.path.exists(source_folder):
                    all_files = os.listdir(source_folder)
                    # Ищем файлы паспорта (начинаются с "Паспорт_")
                    passport_files = [f for f in all_files if f.startswith("Паспорт_")]
                    if passport_files:
                        files_to_copy.extend(passport_files)
                    
                    # Ищем файл прописки
                    propiska_files = [f for f in all_files if f.startswith("Прописка")]
                    if propiska_files:
                        files_to_copy.extend(propiska_files)
                    
                    # Копируем найденные файлы
                    for filename in files_to_copy:
                        source_path = os.path.join(source_folder, filename)
                        dest_path = os.path.join(destination_folder, filename)
                        
                        if os.path.isfile(source_path):
                            shutil.copy2(source_path, dest_path)
                            print(f"✅ Скопирован файл: {filename}")
                        else:
                            print(f"⚠️ Файл не найден: {source_path}")
                    
                    if not files_to_copy:
                        print(f"⚠️ В папке {source_folder} не найдены файлы паспорта или прописки")
                else:
                    print(f"⚠️ Папка {source_folder} не существует")
                    
            except Exception as e:
                print(f"❌ Ошибка при копировании файлов: {e}")
                import traceback
                traceback.print_exc()
        except Exception as e:
            print(f"Ошибка сохранения в БД: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(client_id, "❌ Ошибка сохранения договора. Попробуйте снова.")
            return
        
        # Отправляем клиенту юр договор
        send_legal_contract_to_client(bot, client_id, msg.message_id, contract_data)

    @bot.callback_query_handler(func=lambda call: call.data == "back_client_contract")
    @prevent_double_click(timeout=3.0)
    def show_client_contract_summary_back(call):
        """Показ итоговых данных клиенту"""
        client_id = call.from_user.id
        
        # ДОБАВЛЕНО: проверка данных
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.answer_callback_query(call.id, "❌ Данные потеряны", show_alert=True)
            return
        
        # Удаляем старое сообщение
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # Показываем итоговые данные
        show_client_contract_summary(bot, call.message.chat.id, client_id, user_temp_data)
    @bot.callback_query_handler(func=lambda call: call.data == "start_edit_contract_client")
    @prevent_double_click(timeout=3.0)
    def start_edit_contract(call):
        """Начало редактирования отклоненного договора"""
        client_id = call.from_user.id
        
        # Показываем меню редактирования
        show_contract_edit_menu(bot, call.message.chat.id, call.message.message_id, client_id, user_temp_data)


    def show_contract_edit_menu(bot, chat_id, message_id, client_id, user_temp_data):
        """Показать меню редактирования договора"""
        print(f"DEBUG show_contract_edit_menu: client_id={client_id}")
        print(f"DEBUG user_temp_data keys: {user_temp_data.get(client_id, {}).keys()}")
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.send_message(chat_id, "❌ Ошибка: данные для редактирования не найдены")
            return
        
        contract_data = user_temp_data[client_id]['contract_data']
        
        # Формируем текст с текущими данными
        text = "📋 <b>Текущие данные договора:</b>\n\n"
        text += f"👤 ФИО: {contract_data.get('fio', 'не указано')}\n"
        text += f"📅 Дата рождения: {contract_data.get('date_of_birth', 'не указана')}\n"
        text += f"🏙 Город: {contract_data.get('city', 'не указано')}\n"
        text += f"📄 Серия паспорта: {contract_data.get('seria_pasport', 'не указана')}\n"
        text += f"📄 Номер паспорта: {contract_data.get('number_pasport', 'не указан')}\n"
        text += f"📍 Кем выдан: {contract_data.get('where_pasport', 'не указано')}\n"
        text += f"📅 Дата выдачи: {contract_data.get('when_pasport', 'не указана')}\n"
        text += f"📮 Индекс: {contract_data.get('index_postal', 'не указан')}\n"
        text += f"🏠 Адрес: {contract_data.get('address', 'не указан')}\n"
        text += f"📅 Дата ДТП: {contract_data.get('date_dtp', 'не указана')}\n"
        text += f"⏰ Время ДТП: {contract_data.get('time_dtp', 'не указано')}\n"
        text += f"📍 Адрес ДТП: {contract_data.get('address_dtp', 'не указан')}\n"
        text += f"🚗 Фиксация ДТП: {contract_data.get('who_dtp', 'не указан')}\n"
        text += f"🚗 Марка/модель вашего авто: {contract_data.get('marks', 'не указана')}\n"
        text += f"🚗 Номер вашего авто: {contract_data.get('car_number', 'не указан')}\n"
        text += f"📅 Год выпуска: {contract_data.get('year_auto', 'не указан')}\n"
        text += f"🏢 Страховая: {contract_data.get('insurance', 'не указана')}\n"
        text += f"📋 Серия полиса: {contract_data.get('seria_insurance', 'не указана')}\n"
        text += f"📋 Номер полиса: {contract_data.get('number_insurance', 'не указан')}\n"
        text += f"📅 Дата полиса: {contract_data.get('date_insurance', 'не указана')}\n"
        text += f"👤 ФИО виновника: {contract_data.get('fio_culp', 'не указано')}\n"
        text += f"🚗 Марка авто виновника: {contract_data.get('marks_culp', 'не указана')}\n"
        text += f"🚗 Номер авто виновника: {contract_data.get('number_auto_culp', 'не указан')}\n\n"
        text += "Выберите поле для редактирования:"
        
        # Создаем клавиатуру с кнопками редактирования
        keyboard = types.InlineKeyboardMarkup()
        
        # Поля для редактирования
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО", callback_data="edit_client_field_fio"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата рождения", callback_data="edit_client_field_date_of_birth"))
        keyboard.add(types.InlineKeyboardButton("✏️ Город", callback_data="edit_client_field_city"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия паспорта", callback_data="edit_client_field_seria_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер паспорта", callback_data="edit_client_field_number_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Кем выдан паспорт", callback_data="edit_client_field_where_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата выдачи паспорта", callback_data="edit_client_field_when_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Индекс", callback_data="edit_client_field_index_postal"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес", callback_data="edit_client_field_address"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата ДТП", callback_data="edit_client_field_date_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Время ДТП", callback_data="edit_client_field_time_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес ДТП", callback_data="edit_client_field_address_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Фиксация ДТП", callback_data="edit_client_field_fixacia_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Марка/модель авто", callback_data="edit_client_field_marks"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер авто", callback_data="edit_client_field_car_number"))
        keyboard.add(types.InlineKeyboardButton("✏️ Год выпуска авто", callback_data="edit_client_field_year_auto"))
        keyboard.add(types.InlineKeyboardButton("✏️ Страховая компания", callback_data="edit_client_field_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия полиса", callback_data="edit_client_field_seria_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер полиса", callback_data="edit_client_field_number_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата полиса", callback_data="edit_client_field_date_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО виновника", callback_data="edit_client_field_fio_culp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Марка авто виновника", callback_data="edit_client_field_marks_culp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер авто виновника", callback_data="edit_client_field_number_auto_culp"))
        # Кнопки действий
        keyboard.add(types.InlineKeyboardButton("✅ Редактирование завершено", callback_data="submit_edited_client_contract"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "submit_edited_client_contract")
    @prevent_double_click(timeout=3.0)
    def submit_edited_contract(call):
        """Отправка отредактированного договора на подтверждение"""
        client_id = call.from_user.id
        
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.answer_callback_query(call.id, "❌ Данные потеряны", show_alert=True)
            return
        
        # Возвращаемся к показу итоговых данных
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_client_contract_summary(bot, call.message.chat.id, client_id, user_temp_data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_client_field_"))
    @prevent_double_click(timeout=3.0)
    def handle_field_edit(call):
        """Начало редактирования конкретного поля"""
        client_id = call.from_user.id
        field = call.data.replace("edit_client_field_", "")
        
        # КРИТИЧЕСКИ ВАЖНО: сначала проверяем наличие user_temp_data[client_id]
        if client_id not in user_temp_data:
            print(f"DEBUG ERROR: client_id={client_id} НЕ НАЙДЕН в user_temp_data")
            print(f"DEBUG user_temp_data содержит ключи: {user_temp_data.keys()}")
            bot.answer_callback_query(call.id, "❌ Ошибка: данные потеряны", show_alert=True)
            return
        
        # Теперь проверяем contract_data
        if 'contract_data' not in user_temp_data[client_id]:
            print(f"DEBUG ERROR: contract_data НЕ НАЙДЕН для client_id={client_id}")
            print(f"DEBUG user_temp_data[{client_id}] содержит: {user_temp_data[client_id].keys()}")
            bot.answer_callback_query(call.id, "❌ Ошибка: данные договора потеряны", show_alert=True)
            return
        
        # Сохраняем какое поле редактируем
        user_temp_data[client_id]['editing_field'] = field
        
        # Названия полей для отображения
        field_names = {
            'fio': 'ФИО (Иванов Иван Иванович)',
            'date_of_birth': 'Дата рождения (ДД.ММ.ГГГГ)',
            'city': 'Место рождения',
            'seria_pasport': 'Серия паспорта (4 цифры)',
            'number_pasport': 'Номер паспорта (6 цифр)',
            'when_pasport': 'Дата выдачи паспорта (ДД.ММ.ГГГГ)',
            'where_pasport': 'Кем выдан паспорт',
            'index_postal': 'Индекс (6 цифр)',
            'address': 'Адрес проживания',
            'date_dtp': 'Дата ДТП (ДД.ММ.ГГГГ)',
            'time_dtp': 'Время ДТП (ЧЧ:ММ)',
            'address_dtp': 'Адрес ДТП',
            'who_dtp': 'Фиксация ДТП',
            # ДОБАВЛЕНО:
            'marks': 'Марка и модель авто',
            'car_number': 'Номер авто',
            'year_auto': 'Год выпуска авто (4 цифры)',
            'insurance': 'Страховая компания',
            'seria_insurance': 'Серия полиса',
            'number_insurance': 'Номер полиса',
            'date_insurance': 'Дата полиса (ДД.ММ.ГГГГ)',
            'fio_culp': 'ФИО виновника ДТП',
            'marks_culp': 'Марка авто виновника',
            'number_auto_culp': 'Номер авто виновника'
        }
        
        field_display = field_names.get(field, field)
        current_value = user_temp_data[client_id]['contract_data'].get(field, 'не указано')
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✏️ Редактирование поля: <b>{field_display}</b>\n\n"
                f"Текущее значение: <code>{current_value}</code>\n\n"
                f"Введите новое значение:",
            parse_mode='HTML'
        )
        
        bot.register_next_step_handler(call.message, process_field_edit, client_id, call.message.message_id, field)


    def process_field_edit(message, agent_id, prev_msg_id, field):
        """Обработка нового значения поля"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if agent_id not in user_temp_data or 'contract_data' not in user_temp_data[agent_id]:
            bot.send_message(message.chat.id, "❌ Ошибка: сессия редактирования потеряна")
            return
        
        new_value = message.text.strip()
        
        # Валидация в зависимости от типа поля
        validation_error = None
        
        if field in ['date_of_birth', 'when_pasport', 'date_dtp']:
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', new_value):
                validation_error = "❌ Неверный формат даты! Используйте ДД.ММ.ГГГГ"
            else:
                try:
                    datetime.strptime(new_value, "%d.%m.%Y")
                except ValueError:
                    validation_error = "❌ Некорректная дата!"
        
        elif field == 'time_dtp':
            if not re.match(r'^\d{2}:\d{2}$', new_value):
                validation_error = "❌ Неверный формат времени! Используйте ЧЧ:ММ"
        
        elif field == 'number_pasport':
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Номер паспорта должен содержать 6 цифр"
        
        elif field == 'seria_pasport':
            if not new_value.isdigit() or len(new_value) != 4:
                validation_error = "❌ Серия паспорта должна содержать 4 цифры"
        
        elif field == 'index_postal':
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Индекс должен содержать 6 цифр"
        
        elif field == 'fio':
            if len(new_value.split()) < 2:
                validation_error = "❌ Неправильный формат! Введите ФИО заново:"
            else:
                words = new_value.split()
                for word in words:
                    if not word[0].isupper():
                        validation_error = "❌ Каждое слово должно начинаться с заглавной буквы!"
                        break
        elif field == 'year_auto':
            if len(new_value) != 4 or not new_value.isdigit():
                validation_error = "❌ Год должен содержать 4 цифры"
            else:
                year = int(new_value)
                current_year = datetime.now().year
                if not (1900 < year <= current_year):
                    validation_error = f"❌ Год должен быть в диапазоне от 1901 до {current_year}"
        
        # Если есть ошибка валидации - запрашиваем снова
        if validation_error:
            msg = bot.send_message(message.chat.id, validation_error + "\n\nВведите значение снова:")
            bot.register_next_step_handler(msg, process_field_edit, agent_id, msg.message_id, field)
            return
        
        # Сохраняем новое значение
        user_temp_data[agent_id]['contract_data'][field] = new_value  # ← ИСПРАВЛЕНО (убрали ['data'])
        
        # Возвращаемся в меню редактирования
        msg = bot.send_message(message.chat.id, f"✅ Поле обновлено!")
        show_contract_edit_menu(bot, message.chat.id, msg.message_id, agent_id, user_temp_data)
    def send_legal_contract_to_client(bot, client_id, message_id, contract_data):
        """Отправка юридического договора клиенту"""
        
        client_contract_id = contract_data.get('client_id')
        document_path = f"clients/{client_contract_id}/Документы/Юр договор.docx"
        
        contract_text = """
📄 <b>Договор оказания юридических услуг</b>

Настоящий договор регулирует оказание юридической помощи по делу о возмещении ущерба после ДТП. Юрист обязуется защищать Ваши права и интересы, а Вы обязуетесь оплатить его услуги.

Основные условия:

Обязанности юриста: Вы поручаете юристу подготовить материалы по делу о ДТП, добиться компенсации причинённого ущерба, а в случае отказа страховой компании — представлять Ваши интересы в суде.

Оплата услуг: Вознаграждение юриста в размере 25 000 ₽ подлежит оплате в срок не позднее 10 дней с момента получения ответа от страховой компании.

Гонорар успеха: Дополнительно предусмотрено вознаграждение юристу («гонорар успеха») в размере 50% от сумм штрафа и неустойки, взысканных по решению суда.

Судебные расходы: Все судебные издержки оплачиваются Вами отдельно.

Гарантии: Мы гарантируем профессиональный подход к ведению Вашего дела при условии неукоснительного соблюдения всех наших рекомендаций.

Ваши обязанности: Вы обязуетесь своевременно предоставлять всю запрашиваемую информацию и документы.

Срок действия договора: Работа юриста по договору завершается после вступления решения суда в законную силу.

Внимательно прочитайте договор перед подписанием. Убедитесь, что все пункты Вам понятны.

Подписать договор 👇
        """
        keyboard = types.InlineKeyboardMarkup()
        btn_sign = types.InlineKeyboardButton("✍️ Подписать Юр договор", callback_data="client_sign_legal_contract")
        keyboard.add(btn_sign)
        msg = bot.send_message(
                    client_id, 
                    text=contract_text, 
                    parse_mode='HTML', 
                    reply_markup=None
                )
        # Отправляем документ
        try:
            with open(document_path, 'rb') as document_file:
                msg = bot.send_document(
                    client_id, 
                    document_file,
                    caption="Договор", 
                    parse_mode='HTML', 
                    reply_markup=keyboard
                )
        except Exception as e:
            print(f"Ошибка отправки документа: {e}")
            bot.send_message(client_id, "❌ Ошибка при формировании документа")
            return
        
        # Отправляем текст с кнопкой
        
        bot.delete_message(msg.chat.id, message_id)
    
    @bot.callback_query_handler(func=lambda call: call.data == "client_sign_legal_contract")
    @prevent_double_click(timeout=3.0)
    def client_sign_legal_contract(call):
        """Подписание юридического договора клиентом"""
        client_id = call.from_user.id
        cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=5)
        contract_data = user_temp_data.get(client_id, {}).get('contract_data', {})
        accident_type = contract_data.get('accident', '')

        
        # Проверяем тип обращения
        if accident_type == "ДТП":
            # Переходим к заполнению заявления в страховую

            msg = bot.send_message(
                chat_id=call.message.chat.id,
                text="✅ Договор успешно оформлен!\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
                parse_mode='HTML'
            )
            
            bot.register_next_step_handler(msg, process_driver_license_front, client_id, contract_data, msg.message_id)
        
        elif accident_type == "После ямы":
            bot.send_message(
                client_id,
                "✅ Договор успешно оформлен!\n\n"
                "Тип обращения: После ямы\n"
            )
            
            # Очищаем данные
            if client_id in user_temp_data:
                user_temp_data.pop(client_id, None)
            
            # Возвращаем в главное меню
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, client_id)
        
        elif accident_type =="Нет ОСАГО":
            keyboard = types.InlineKeyboardMarkup()
            btn_yes = types.InlineKeyboardButton("✅ Да", callback_data=f"NoOsago_yes_{contract_data['client_id']}")
            btn_no = types.InlineKeyboardButton("❌ Заполнить позже", callback_data=f"NoOsago_no_{client_id}")
            keyboard.add(btn_yes, btn_no)
            bot.send_message(
                chat_id=call.message.chat.id,
                text = f"✅ Договор успешно оформлен!\n\n"
                       f"Тип обращения: Нет ОСАГО у виновника ДТП\nЗаполнить заявление в ГИБДД?",
                reply_markup = keyboard
            )
        elif accident_type =="Подал заявление":
            keyboard = types.InlineKeyboardMarkup()
            btn_yes = types.InlineKeyboardButton("💰 На выплату", callback_data=f"podal_viplata_{contract_data['client_id']}")
            btn_no = types.InlineKeyboardButton("🛠️ На ремонт", callback_data=f"podal_rem_{contract_data['client_id']}")
            keyboard.add(btn_yes, btn_no)
            bot.send_message(
                chat_id=call.message.chat.id,
                text = f"✅ Договор успешно оформлен!\n\n"
                       f"Тип обращения: Подал заявление\nБыло подано заявление на выплату или на ремонт?",
                reply_markup = keyboard
            )    
        
        bot.answer_callback_query(call.id, "Договор подписан!")
    
    
    # ========== ЗАПОЛНЕНИЕ ЗАЯВЛЕНИЯ В СТРАХОВУЮ ==========

    def process_driver_license_front(message, client_id, contract_data, user_message_id):
        """Обработка фото лицевой стороны ВУ"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if not message.photo:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Отменить", callback_data="cancel_driver_license_client"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
                parse_mode='HTML',
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_driver_license_front, client_id, contract_data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем во временное хранилище
            if client_id not in user_temp_data:
                user_temp_data[client_id] = {}
            
            user_temp_data[client_id]['driver_license_front'] = downloaded_file
            user_temp_data[client_id]['contract_data'] = contract_data
            
            # Запрашиваем обратную сторону
            msg = bot.send_message(
                message.chat.id,
                "✅ Фотография лицевой стороны принята.\n\n📸 Теперь отправьте фотографию обратной стороны водительского удостоверения.",
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_driver_license_back, client_id, contract_data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при обработке фото ВУ (лицевая сторона): {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Отменить", callback_data="cancel_driver_license_client"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
                parse_mode='HTML',
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_driver_license_front, client_id, contract_data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_driver_license_client")
    @prevent_double_click(timeout=3.0)
    def cancel_driver_license(call):
        """Отмена загрузки водительского удостоверения"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        # Очищаем временные данные
        if client_id in user_temp_data:
            user_temp_data[client_id].pop('driver_license_front', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        bot.send_message(
            call.message.chat.id,
            "❌ Загрузка водительского удостоверения отменена.\n\n"
            "Вы можете продолжить загрузку документов позже из личного кабинета."
        )
        
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, client_id)
    def process_driver_license_back(message, client_id, contract_data, user_message_id):
        """Обработка фото обратной стороны ВУ и создание PDF"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>обратной стороны</b> водительского удостоверения:",
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_driver_license_back, client_id, contract_data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Получаем лицевую сторону из временного хранилища
            front_photo = user_temp_data[client_id]['driver_license_front']
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{contract_data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/Водительское_удостоверение.pdf"
            create_pdf_from_images(front_photo, downloaded_file, pdf_path)
            
            # Очищаем временные данные
            if 'driver_license_front' in user_temp_data[client_id]:
                del user_temp_data[client_id]['driver_license_front']
            
            # Переходим к выбору документа ТС
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="client_STS")
            btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="client_PTS")
            keyboard.add(btn1)
            keyboard.add(btn2)
            bot.send_message(
                message.chat.id, 
                "✅ Водительское удостоверение успешно сохранено!\nВыберите документ о регистрации ТС:", 
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка при создании PDF ВУ: {e}")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:\n\n📸 Отправьте фото <b>обратной стороны</b> водительского удостоверения:",
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_driver_license_back, client_id, contract_data, msg.message_id)


    def create_pdf_from_images(image1_bytes, image2_bytes, output_path):
        """
        Создает PDF файл из двух изображений
        
        Args:
            image1_bytes: байты первого изображения (лицевая сторона)
            image2_bytes: байты второго изображения (обратная сторона)
            output_path: путь для сохранения PDF
        """
        try:
            # Открываем изображения
            img1 = Image.open(BytesIO(image1_bytes))
            img2 = Image.open(BytesIO(image2_bytes))
            
            # Конвертируем в RGB (необходимо для PDF)
            if img1.mode != 'RGB':
                img1 = img1.convert('RGB')
            if img2.mode != 'RGB':
                img2 = img2.convert('RGB')
            
            # Оптимизируем размер (опционально, для уменьшения размера файла)
            max_size = (1920, 1920)  # Максимальный размер стороны
            img1.thumbnail(max_size, Image.Resampling.LANCZOS)
            img2.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Сохраняем как PDF (первое изображение + второе как дополнительная страница)
            img1.save(
                output_path,
                "PDF",
                resolution=100.0,
                save_all=True,
                append_images=[img2]
            )
            
            print(f"PDF успешно создан: {output_path}")
            
        except Exception as e:
            print(f"Ошибка при создании PDF: {e}")
            raise
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["client_STS", "client_PTS"])
    @prevent_double_click(timeout=3.0)
    def callback_client_docs(call):
        """Обработка выбора документа о регистрации ТС"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']
        
        if call.data == "client_STS":
            data.update({"docs": "СТС"})
            data['dkp'] = '-'
            user_temp_data[client_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_client_type_docs")
            keyboard.add(btn)
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📸 Отправьте фото <b>лицевой стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup=keyboard 
            )
            
            bot.register_next_step_handler(msg, client_sts_front, client_id, data, msg.message_id)

        elif call.data == "client_PTS":
            data['docs'] = "ПТС"
            user_temp_data[client_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Управляю по ДКП", callback_data="client_DKP")
            btn2 = types.InlineKeyboardButton("Продолжить", callback_data="client_DKP_next")
            btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_client_type_docs")
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите из следующих вариантов",
                reply_markup=keyboard
            )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_client_type_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_client_type_docs(call):
        """Возврат к выбору типа документа"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            user_temp_data[client_id]['contract_data'].pop('seria_docs', None)
            user_temp_data[client_id]['contract_data'].pop('docs', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="client_STS")
        btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="client_PTS")
        keyboard.add(btn1)
        keyboard.add(btn2)
        
        bot.send_message(
            call.message.chat.id,
            "✅ Водительское удостоверение успешно сохранено!\nВыберите документ о регистрации ТС:",
            reply_markup=keyboard
        )
        # ==================== СТС (2 стороны) ====================

    def client_sts_front(message, client_id, data, user_message_id):
        """Обработка фото лицевой стороны СТС"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            keyboard = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_client_type_docs")
            keyboard.add(btn)
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>лицевой стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, client_sts_front, client_id, data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем во временное хранилище
            if client_id not in user_temp_data:
                user_temp_data[client_id] = {}
            
            user_temp_data[client_id]['sts_front'] = downloaded_file
            user_temp_data[client_id]['contract_data'] = data
            
            # Запрашиваем обратную сторону
            keyboard = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_client_type_docs")
            keyboard.add(btn)
            msg = bot.send_message(
                message.chat.id,
                "✅ Лицевая сторона получена!\n\n📸 Теперь отправьте фото <b>обратной стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_sts_back, client_id, data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при обработке фото СТС (лицевая сторона): {e}")
            keyboard = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_client_type_docs")
            keyboard.add(btn)
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, client_sts_front, client_id, data, msg.message_id)


    def process_sts_back(message, client_id, data, user_message_id):
        """Обработка фото обратной стороны СТС и создание PDF"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>обратной стороны</b> СТС:",
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_sts_back, client_id, data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Получаем лицевую сторону из временного хранилища
            front_photo = user_temp_data[client_id]['sts_front']
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/СТС.pdf"
            create_pdf_from_images2([front_photo, downloaded_file], pdf_path)
            
            # Очищаем временные данные
            if 'sts_front' in user_temp_data[client_id]:
                del user_temp_data[client_id]['sts_front']
            if 'sts_front' in data:
                del data['sts_front']

            user_temp_data[client_id]['contract_data'] = data

            if data.get("who_dtp", '') == 'Евро-протокол':
                protocol_text = "Евро-протокола"
            else:
                protocol_text = "протокола ГИБДД"
            user_temp_data[client_id]['protocol_photos'] = []
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_client_{data['user_id']}")

            if data.get("docs", '') == 'СТС':
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_STS")
            elif data.get('dkp', '') != '-':
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_DKP")
            else:
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_DKP_next")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                    chat_id=message.chat.id,
                    text=f"✅ СТС успешно сохранен!\n\n📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:",
                    reply_markup=keyboard
                )
            
        except Exception as e:
            print(f"Ошибка при создании PDF СТС: {e}")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:",
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_sts_back, client_id, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["client_DKP", "client_DKP_next"])
    @prevent_double_click(timeout=3.0)
    def callback_client_dkp(call):
        """Обработка выбора ДКП"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']

        if call.data == "client_DKP":
            data['dkp'] = 'Договор ДКП'
        else:
            data['dkp'] = '-'
        user_temp_data[client_id]['contract_data'] = data
        user_temp_data[client_id]['pts_photos'] = []
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_pts_upload_client_{client_id}")
        keyboard.add(btn_finish)
        message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📸 Отправьте фото страниц ПТС\n\n"
                     "Можно отправлять по одной фотографии или несколько сразу.\n"
                     "Когда загрузите все страницы, нажмите кнопку ниже:",
                reply_markup=keyboard
            )  

    # ==================== ПТС (множественные фото) ====================

    @bot.message_handler(content_types=['photo'], 
                         func=lambda message: message.chat.id not in upload_sessions or 'photos' not in upload_sessions.get(message.chat.id, {}))
    def handle_pts_photos(message):
        """Обработчик фотографий ПТС (множественная загрузка)"""
        client_id = message.chat.id
        cleanup_messages(bot, message.chat.id, message.message_id, 3)
        
        def send_photo_confirmation(chat_id, photo_type, count):
            """Отправка отложенного подтверждения загрузки"""
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_{photo_type}_upload_client_{chat_id}")
            keyboard.add(btn_finish)
            
            bot.send_message(
                chat_id,
                f"✅ Загружено фото: {count}\n\n"
                "Можете отправить еще фото или завершить загрузку:",
                reply_markup=keyboard
            )
        
        # Проверяем, идет ли загрузка ПТС
        if client_id in user_temp_data and 'pts_photos' in user_temp_data[client_id]:
            try:
                # Обрабатываем все фотографии в сообщении
                if message.photo:
                    file_info = bot.get_file(message.photo[-1].file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    user_temp_data[client_id]['pts_photos'].append(downloaded_file)
                
                photos_count = len(user_temp_data[client_id]['pts_photos'])
                
                # Отменяем предыдущий таймер если он есть
                if 'pts_timer' in user_temp_data[client_id]:
                    user_temp_data[client_id]['pts_timer'].cancel()
                
                # Запускаем новый таймер на 2 секунды
                timer = threading.Timer(2.0, send_photo_confirmation, args=(client_id, 'pts', photos_count))
                timer.start()
                user_temp_data[client_id]['pts_timer'] = timer
                
            except Exception as e:
                print(f"Ошибка при загрузке фото ПТС: {e}")
                bot.send_message(message.chat.id, "❌ Ошибка при загрузке фото. Попробуйте снова.")
        
        # Проверяем, идет ли загрузка ДКП
        elif client_id in user_temp_data and 'dkp_photos' in user_temp_data[client_id]:
            try:
                # Обрабатываем все фотографии в сообщении
                if message.photo:
                    file_info = bot.get_file(message.photo[-1].file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    user_temp_data[client_id]['dkp_photos'].append(downloaded_file)
                
                photos_count = len(user_temp_data[client_id]['dkp_photos'])
                
                # Отменяем предыдущий таймер если он есть
                if 'dkp_timer' in user_temp_data[client_id]:
                    user_temp_data[client_id]['dkp_timer'].cancel()
                
                # Запускаем новый таймер на 2 секунды
                timer = threading.Timer(2.0, send_photo_confirmation, args=(client_id, 'dkp', photos_count))
                timer.start()
                user_temp_data[client_id]['dkp_timer'] = timer
                
            except Exception as e:
                print(f"Ошибка при загрузке фото ДКП: {e}")
                bot.send_message(message.chat.id, "❌ Ошибка при загрузке фото. Попробуйте снова.")

        elif client_id in user_temp_data and 'protocol_photos' in user_temp_data[client_id]:
            try:
                if message.photo:
                    file_info = bot.get_file(message.photo[-1].file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    user_temp_data[client_id]['protocol_photos'].append(downloaded_file)
                
                photos_count = len(user_temp_data[client_id]['protocol_photos'])
                
                # Отменяем предыдущий таймер если он есть
                if 'protocol_timer' in user_temp_data[client_id]:
                    user_temp_data[client_id]['protocol_timer'].cancel()
                
                # Запускаем новый таймер на 2 секунды
                timer = threading.Timer(2.0, send_photo_confirmation, args=(client_id, 'protocol_photos', photos_count))
                timer.start()
                user_temp_data[client_id]['protocol_timer'] = timer
                
            except Exception as e:
                print(f"Ошибка при загрузке фото протокола: {e}")
                bot.send_message(message.chat.id, "❌ Ошибка при загрузке фото. Попробуйте снова.")
        elif client_id in user_temp_data and 'dtp_photos' in user_temp_data[client_id]:
            try:
                if message.photo:
                    file_info = bot.get_file(message.photo[-1].file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    user_temp_data[client_id]['dtp_photos'].append(downloaded_file)
                
                photos_count = len(user_temp_data[client_id]['dtp_photos'])
                
                # Отменяем предыдущий таймер если он есть
                if 'dtp_timer' in user_temp_data[client_id]:
                    user_temp_data[client_id]['dtp_timer'].cancel()
                
                # Запускаем новый таймер на 2 секунды
                timer = threading.Timer(2.0, send_photo_confirmation, args=(client_id, 'dtp_photos', photos_count))
                timer.start()
                user_temp_data[client_id]['dtp_timer'] = timer
                
            except Exception as e:
                print(f"Ошибка при загрузке фото ДТП: {e}")
                bot.send_message(message.chat.id, "❌ Ошибка при загрузке фото. Попробуйте снова.")
        elif client_id in user_temp_data and 'dtp_photos_cabinet' in user_temp_data[client_id]:
            try:
                if message.photo:
                    file_info = bot.get_file(message.photo[-1].file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    user_temp_data[client_id]['dtp_photos_cabinet'].append(downloaded_file)
                
                photos_count = len(user_temp_data[client_id]['dtp_photos_cabinet'])
                
                # Отменяем предыдущий таймер если он есть
                if 'dtp_cabinet_timer' in user_temp_data[client_id]:
                    user_temp_data[client_id]['dtp_cabinet_timer'].cancel()
                
                # Запускаем новый таймер на 2 секунды
                timer = threading.Timer(2.0, send_photo_confirmation, args=(client_id, 'dtp_photos_cabinet', photos_count))
                timer.start()
                user_temp_data[client_id]['dtp_cabinet_timer'] = timer
                
            except Exception as e:
                print(f"Ошибка при загрузке фото ДТП: {e}")
                bot.send_message(message.chat.id, "❌ Ошибка при загрузке фото. Попробуйте снова.")
        
        # Проверяем, идет ли загрузка доверенности
        elif client_id in user_temp_data and 'doverennost_photos' in user_temp_data[client_id]:
            try:
                if message.photo:
                    file_info = bot.get_file(message.photo[-1].file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    user_temp_data[client_id]['doverennost_photos'].append(downloaded_file)
                
                photos_count = len(user_temp_data[client_id]['doverennost_photos'])
                
                # Отменяем предыдущий таймер если он есть
                if 'dov_timer' in user_temp_data[client_id]:
                    user_temp_data[client_id]['dov_timer'].cancel()
                
                # Запускаем новый таймер на 2 секунды
                timer = threading.Timer(2.0, send_photo_confirmation, args=(client_id, 'doverennost_photos', photos_count))
                timer.start()
                user_temp_data[client_id]['dov_timer'] = timer
                
            except Exception as e:
                print(f"Ошибка при загрузке доверенности: {e}")
                bot.send_message(message.chat.id, "❌ Ошибка при загрузке фото. Попробуйте снова.")


    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_pts_upload_client_'))
    @prevent_double_click(timeout=3.0)
    def finish_pts_upload_callback(call):
        """Завершение загрузки ПТС"""
        client_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if client_id not in user_temp_data or 'pts_photos' not in user_temp_data[client_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[client_id]['pts_photos']
            data = user_temp_data[client_id]['contract_data']
            
            if len(photos) == 0:
                
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_pts_upload_client_{client_id}")
                keyboard.add(btn_finish)
                
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Отправьте фото страниц ПТС:",
                    reply_markup=keyboard
                )
                return
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/ПТС.pdf"
            create_pdf_from_images2(photos, pdf_path)
            
            # Очищаем временные данные
            del user_temp_data[client_id]['pts_photos']
            
            
            # Проверяем, нужно ли загружать ДКП
            if data.get('dkp') == 'Договор ДКП':
                start_dkp_upload(call.message.chat.id, client_id, data)
            else:
                if data.get("who_dtp", '') == 'Евро-протокол':
                    protocol_text = "Евро-протокола"
                else:
                    protocol_text = "протокола ГИБДД"
                user_temp_data[client_id]['protocol_photos'] = []
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_client_{data['user_id']}")

                if data.get("docs", '') == 'СТС':
                    btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_STS")
                elif data.get('dkp', '') != '-':
                    btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_DKP")
                else:
                    btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_DKP_next")
                keyboard.add(btn_finish)
                keyboard.add(btn_back)
                msg = bot.send_message(
                        chat_id=call.message.chat.id,
                        text=f"✅ ПТС успешно сохранен!\n\n📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:",
                        reply_markup=keyboard
                    )
            
        except Exception as e:
            print(f"Ошибка при сохранении ПТС: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении документа.")


    # ==================== ДКП (множественные фото) ====================

    def start_dkp_upload(chat_id, client_id, data):
        """Начало загрузки ДКП"""

        if client_id not in user_temp_data:
            user_temp_data[client_id] = {}
        user_temp_data[client_id]['dkp_photos'] = []
        user_temp_data[client_id]['contract_data'] = data
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dkp_upload_client_{client_id}")
        keyboard.add(btn_finish)
        
        bot.send_message(
            chat_id,
            "✅ ПТС успешно сохранен!\n"
            "📸 Отправьте фото страниц Договора купли-продажи\n\n"
            "Можно отправлять по одной фотографии или несколько сразу.\n"
            "Когда загрузите все страницы, нажмите кнопку ниже:",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_dkp_upload_client_'))
    @prevent_double_click(timeout=3.0)
    def finish_dkp_upload_callback(call):
        """Завершение загрузки ДКП"""
        client_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if client_id not in user_temp_data or 'dkp_photos' not in user_temp_data[client_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[client_id]['dkp_photos']
            data = user_temp_data[client_id]['contract_data']
            
            if len(photos) == 0:
                
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dkp_client_{client_id}")
                keyboard.add(btn_finish)
                
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Отправьте фото страниц Договора купли-продажи:",
                    reply_markup=keyboard
                )
                return
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/ДКП.pdf"
            create_pdf_from_images2(photos, pdf_path)
            
            # Очищаем временные данные
            del user_temp_data[client_id]['dkp_photos']          
            
            if data.get("who_dtp", '') == 'Евро-протокол':
                protocol_text = "Евро-протокола"
            else:
                protocol_text = "протокола ГИБДД"
            user_temp_data[client_id]['protocol_photos'] = []
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_client_{data['user_id']}")

            if data.get("docs", '') == 'СТС':
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_STS")
            elif data.get('dkp', '') != '-':
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_DKP")
            else:
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="client_DKP_next")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                    chat_id=call.message.chat.id,
                    text=f"✅ Договор купли-продажи успешно сохранен!\n\n📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:",
                    reply_markup=keyboard
                )
            
        except Exception as e:
            print(f"Ошибка при сохранении ДКП: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении документа.")


    # ==================== Завершение загрузки ====================

    def finish_document_upload(chat_id, client_id, data, user_message_id):
        """Завершение загрузки всех документов и переход к выбору страховой"""
        try:
            bot.delete_message(chat_id, user_message_id)
        except:
            pass
        # Создаем клавиатуру с пагинацией (первая страница)
        user_temp_data[client_id]['contract_data'] = data
        
        keyboard = types.InlineKeyboardMarkup()
        if data.get('accident','') == 'ДТП':
            if data.get('sobstvenik','') != 'С начала':
                keyboard.add(types.InlineKeyboardButton("Заполнить заявление в страховую ", callback_data=f"dtp_continue_documents2_{client_id}"))
            keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"request_act_payment_{data['client_id']}"))  
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{client_id}"))
        
            bot.send_message(
                chat_id=chat_id,
                text="✅ Все документы успешно загружены!",
                reply_markup=keyboard
            )
        elif data.get('accident','') == 'Подал заявление':
            keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"agent_podal_continue_documents_{client_id}"))
            keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"request_act_payment_{data['client_id']}"))  
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{client_id}"))
        
            bot.send_message(
                chat_id=chat_id,
                text="✅ Все документы успешно загружены!\n\nГотовы продолжить заполнение?",
                reply_markup=keyboard
            )
        elif data.get('accident','') == 'Нет ОСАГО':
            keyboard.add(types.InlineKeyboardButton("📄 Заявление о выдаче из ГИБДД", callback_data=f"agent_net_osago_continue_documents_{client_id}"))
            keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"request_act_payment_{data['client_id']}"))  
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{client_id}"))
        
            bot.send_message(
                chat_id=chat_id,
                text="✅ Все документы успешно загружены!\n\nГотовы продолжить заполнение?",
                reply_markup=keyboard
            ) 
        else:
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{client_id}"))
            bot.send_message(
                chat_id=chat_id,
                text="✅ Все документы успешно загружены!",
                reply_markup=keyboard
            )

    @bot.callback_query_handler(func=lambda call: call.data in ['health_yes_client', 'health_no_client'])
    @prevent_double_click(timeout=3.0)
    def finish_dkp_health_callback(call):
        agent_id = call.from_user.id
        if call.data == 'health_yes_client':
            data = user_temp_data[call.from_user.id]['contract_data']
            if data.get('who_dtp') == "По форме ГИБДД":
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"client_place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"client_place_dtp"))  
                data['number_photo'] = '-'
                user_temp_data[call.from_user.id]['contract_data'] = data
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                    reply_markup=keyboard
                )
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"client_photo_non_gosuslugi"))
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, client_number_photo, data, msg.message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"culp_have_osago_yes_client"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"culp_have_osago_no_client"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Есть ли у пострадавшего ОСАГО?",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ['culp_have_osago_yes_client', 'culp_have_osago_no_client'])
    @prevent_double_click(timeout=3.0)
    def finish_culp_have_osago_callback(call):
        agent_id = call.from_user.id
        if call.data == 'health_yes_client':
            data = user_temp_data[call.from_user.id]['contract_data']
            if data.get('who_dtp') == "По форме ГИБДД":
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"client_place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"client_place_dtp"))  
                data['number_photo'] = '-'
                user_temp_data[call.from_user.id]['contract_data'] = data
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                    reply_markup=keyboard
                )
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"client_photo_non_gosuslugi"))
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, client_number_photo, data, msg.message_id)
        else:
            data = user_temp_data[call.from_user.id]['contract_data']
            if data.get('who_dtp') == "По форме ГИБДД":
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"client_place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"client_place_dtp"))  
                data['number_photo'] = '-'
                user_temp_data[call.from_user.id]['contract_data'] = data
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                    reply_markup=keyboard
                )
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"client_photo_non_gosuslugi"))
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, client_number_photo, data, msg.message_id)

    # ==================== Функция создания PDF ====================

    def create_pdf_from_images2(image_bytes_list, output_path):
        """
        Создает PDF файл из списка изображений
        
        Args:
            image_bytes_list: список байтов изображений
            output_path: путь для сохранения PDF
        """
        try:
            images = []
            
            # Открываем все изображения
            for img_bytes in image_bytes_list:
                img = Image.open(BytesIO(img_bytes))
                
                # Конвертируем в RGB (необходимо для PDF)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Оптимизируем размер
                max_size = (1920, 1920)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                images.append(img)
            
            if len(images) == 0:
                raise ValueError("Нет изображений для создания PDF")
            
            # Сохраняем как PDF
            if len(images) == 1:
                images[0].save(output_path, "PDF", resolution=100.0)
            else:
                images[0].save(
                    output_path,
                    "PDF",
                    resolution=100.0,
                    save_all=True,
                    append_images=images[1:]
                )
            
            print(f"PDF успешно создан: {output_path}")
            
        except Exception as e:
            print(f"Ошибка при создании PDF: {e}")
            raise

    @bot.callback_query_handler(func=lambda call: call.data == "client_photo_non_gosuslugi")
    @prevent_double_click(timeout=3.0)
    def handle_agent_photo_non_gosuslugi(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"next_photo_client"))
        keyboard.add(types.InlineKeyboardButton("Я внесу фотофиксацию", callback_data=f"continue_photo_client"))  

        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Если нет прикрепления фотофиксации в Госуслуги, то выплата ограничивается размером 100000₽",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ["next_photo_client", "continue_photo_client"])
    @prevent_double_click(timeout=3.0)
    def handle_agent_next_photo_gosuslugi(call):
        data = user_temp_data[call.from_user.id]['contract_data']
        if call.data == "next_photo_client":
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"client_place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"client_place_dtp"))  
            data['number_photo'] = '-'
            user_temp_data[call.from_user.id]['contract_data'] = data
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                reply_markup=keyboard
            )
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"client_photo_non_gosuslugi"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, client_number_photo, data, msg.message_id)
    def client_number_photo(message, data, user_message_id):
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['number_photo'] = message.text
        user_temp_data[message.from_user.id]['contract_data'] = data

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"client_place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"client_place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_photo_client"))
        
        bot.send_message(
            message.from_user.id,
            "Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_photo_client")
    @prevent_double_click(timeout=3.0)
    def back_to_number_photo(call):
        """Возврат к вводу номера фотофиксации"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['contract_data']
            data.pop('number_photo', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"client_photo_non_gosuslugi"))
        bot.send_message(
            call.message.chat.id,
            "Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
            reply_markup=keyboard
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, client_number_photo, data, call.message.message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["client_place_home", "client_place_dtp"])
    @prevent_double_click(timeout=3.0)
    def callback_client_place(call):
        """Обработка ремонт не более 50км от места ДТП или места жительства"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']

        if call.data == "client_place_home":
            data['place'] = "Жительства"
        else:
            data['place'] = "ДТП"
        user_temp_data[client_id]['contract_data'] = data
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"client_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"client_cancel_bank")) 
        msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=context,
                    reply_markup = keyboard
                )

    @bot.callback_query_handler(func=lambda call: call.data in ["client_next_bank", "client_cancel_bank"])
    @prevent_double_click(timeout=3.0)
    def callback_client_requisites(call):
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']
        if call.data == "client_next_bank":
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="<b>Заполнение банковских реквизитов</b>",
                    parse_mode='HTML'
                )
            msg2 = bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Введите банк получателя клиента"
                )
            user_message_id = msg2.message_id
            bot.register_next_step_handler(msg, client_bank, data, user_message_id, msg.message_id)

        else:
            data.update({"bank": "-"})
            data.update({"bank_account": "-"})
            data.update({"bank_account_corr": "-"})
            data.update({"BIK": "-"})
            data.update({"INN": "-"})
            # Инициализируем хранилище для фото протокола (ГИБДД или Евро-протокол)
            if client_id not in user_temp_data:
                user_temp_data[client_id] = {}
            user_temp_data[client_id]['protocol_photos'] = []
            user_temp_data[client_id]['contract_data'] = data

            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_client_{client_id}")
            keyboard.add(btn_finish)

            # Определяем текст в зависимости от типа протокола
            if data.get("who_dtp", '') == 'Евро-протокол':
                protocol_text = "Евро-протокола"
            else:
                protocol_text = "протокола ГИБДД"

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:",
                reply_markup=keyboard
            )
            
    def client_bank(message, data, user_message_id, save_message):
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"bank": message.text})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_choice_client"))
        message = bot.send_message(
            message.chat.id, 
            text="Введите счет получателя, 20 цифр",
            reply_markup=keyboard
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, client_bank_account, data, user_message_id, save_message)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_bank_choice_client")
    @prevent_double_click(timeout=3.0)
    def back_to_bank_choice(call):
        """Возврат к выбору заполнения реквизитов"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['contract_data']
            data.pop('bank', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"client_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"client_cancel_bank"))
        
        bot.send_message(
            call.message.chat.id,
            context,
            reply_markup=keyboard
        )
    def client_bank_account(message, data, user_message_id, save_message):
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        account_text = message.text.strip()
        
        # Проверяем что текст состоит только из цифр и содержит 20 символов
        if account_text.isdigit() and len(account_text) == 20:
            data.update({"bank_account": account_text})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_account_client"))
            message = bot.send_message(
                message.chat.id,
                text="Введите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, client_bank_account_corr, data, user_message_id, save_message)
        else:
            error_msg = ""
            if not account_text.isdigit():
                error_msg = "❌ Счет должен состоять только из цифр!"
            elif len(account_text) != 20:
                error_msg = f"❌ Счет должен содержать 20 цифр! Вы ввели: {len(account_text)}"
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_choice_client"))
            message = bot.send_message(
                message.chat.id,
                text=f"{error_msg}\n\nВведите счет получателя, 20 цифр:",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, client_bank_account, data, user_message_id, save_message)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_bank_account_client")
    @prevent_double_click(timeout=3.0)
    def back_to_bank_account(call):
        """Возврат к вводу счета"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['contract_data']
            data.pop('bank_account', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_choice_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите счет получателя, 20 цифр",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, client_bank_account, data, user_message_id, msg.message_id)
    def client_bank_account_corr(message, data, user_message_id, save_message):
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        account_text = message.text.strip().replace(' ', '')  # Убираем пробелы
        
        # Проверяем что текст состоит только из цифр и содержит 20 символов
        if account_text.isdigit() and len(account_text) == 20:
            data.update({"bank_account_corr": account_text})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_account_corr_client"))
            message = bot.send_message(
                message.chat.id,
                text="✅ Корреспондентский счет сохранен!\n\nВведите БИК банка, 9 цифр:",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, client_BIK, data, user_message_id, save_message)
        else:
            error_msg = ""
            if not account_text.isdigit():
                error_msg = "❌ Счет должен состоять только из цифр!"
            elif len(account_text) != 20:
                error_msg = f"❌ Счет должен содержать 20 цифр! Вы ввели: {len(account_text)}"
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_account_client"))
            message = bot.send_message(
                message.chat.id,
                text=f"{error_msg}\n\nВведите корреспондентский счет банка, 20 цифр:",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, client_bank_account_corr, data, user_message_id, save_message)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_bank_account_corr_client")
    @prevent_double_click(timeout=3.0)
    def back_to_bank_account_corr(call):
        """Возврат к вводу корр. счета"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['contract_data']
            data.pop('bank_account_corr', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_account_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите корреспондентский счет банка, 20 цифр",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, client_bank_account_corr, data, user_message_id, msg.message_id)
    def client_BIK(message, data, user_message_id, save_message):
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        bik_text = message.text.strip().replace(' ', '')  # Убираем пробелы
        
        # Проверяем что текст состоит только из цифр и содержит 9 символов
        if bik_text.isdigit() and len(bik_text) == 9:
            data.update({"BIK": bik_text})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bik_client"))
            message = bot.send_message(
                message.chat.id,
                text="✅ БИК банка сохранен!\n\nВведите ИНН банка, 10 цифр:",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, client_INN, data, user_message_id, save_message)
        else:
            error_msg = ""
            if not bik_text.isdigit():
                error_msg = "❌ БИК должен состоять только из цифр!"
            elif len(bik_text) != 9:
                error_msg = f"❌ БИК должен содержать 9 цифр! Вы ввели: {len(bik_text)}"
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_account_corr_client"))
            message = bot.send_message(
                message.chat.id,
                text=f"{error_msg}\n\nВведите БИК банка, 9 цифр:",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, client_BIK, data, user_message_id, save_message)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_bik_client")
    @prevent_double_click(timeout=3.0)
    def back_to_bik(call):
        """Возврат к вводу БИК"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'contract_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['contract_data']
            data.pop('BIK', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bank_account_corr_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите БИК банка, 9 цифр:",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, client_BIK, data, user_message_id, msg.message_id)
    def client_INN(message, data, user_message_id, save_message):
        client_id = message.from_user.id
        
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, save_message)
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        inn_text = message.text.strip().replace(' ', '')  # Убираем пробелы
        
        # Проверяем что текст состоит только из цифр и содержит 10 символов
        if inn_text.isdigit() and len(inn_text) == 10:
            data.update({"INN": inn_text})

            # Инициализируем хранилище для фото протокола (ГИБДД или Евро-протокол)
            if client_id not in user_temp_data:
                user_temp_data[client_id] = {}
            user_temp_data[client_id]['protocol_photos'] = []
            user_temp_data[client_id]['contract_data'] = data

            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_client_{client_id}")
            keyboard.add(btn_finish)

            # Определяем текст в зависимости от типа протокола
            if data.get("who_dtp", '') == 'Евро-протокол':
                protocol_text = "Евро-протокола"
            else:
                protocol_text = "протокола ГИБДД"

            bot.send_message(
                message.chat.id,
                f"✅ ИНН банка сохранен!\n\n"
                f"📸 Прикрепите фото {protocol_text}\n\n"
                "Фото должны быть четкими, не засвечены.\n"
                "Можно отправлять по одной фотографии или несколько сразу.\n"
                "Когда загрузите все фото, нажмите кнопку ниже:",
                reply_markup=keyboard
            )
        else:
            error_msg = ""
            if not inn_text.isdigit():
                error_msg = "❌ ИНН должен состоять только из цифр!"
            elif len(inn_text) != 10:
                error_msg = f"❌ ИНН должен содержать 10 цифр! Вы ввели: {len(inn_text)}"
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_bik_client"))
            message = bot.send_message(
                message.chat.id,
                text=f"{error_msg}\n\nВведите ИНН банка, 10 цифр:",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, client_INN, data, user_message_id, save_message)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_protocol_photos_upload_client_'))
    @prevent_double_click(timeout=3.0)
    def finish_protocol_photos_upload_callback(call):
        """Завершение загрузки фото протокола (ГИБДД или Евро-протокол)"""
        agent_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if agent_id not in user_temp_data or 'protocol_photos' not in user_temp_data[agent_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[agent_id]['protocol_photos']
            data = user_temp_data[agent_id]['contract_data']
            
            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_agent_{agent_id}")
                keyboard.add(btn_finish)
                
                protocol_type = "Евро-протокола" if data.get("who_dtp", '') == 'Евро-протокол' else "протокола ГИБДД"
                
                bot.send_message(
                    call.message.chat.id,
                    f"❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Прикрепите фото {protocol_type}:",
                    reply_markup=keyboard
                )
                return
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Определяем имя файла в зависимости от типа протокола
            if data.get("who_dtp", '') == 'Евро-протокол':
                pdf_filename = "Евро-протокол.pdf"
                success_message = f"✅ Евро-протокол успешно сохранен! ({len(photos)} фото)"
            else:
                pdf_filename = "Протокол_ГИБДД.pdf"
                success_message = f"✅ Протокол ГИБДД успешно сохранен! ({len(photos)} фото)"
            
            # Создаем PDF из фото протокола
            pdf_path = f"{client_dir}/{pdf_filename}"
            create_pdf_from_images2(photos, pdf_path)
            
            # Очищаем временные данные фото протокола
            del user_temp_data[agent_id]['protocol_photos']
            if 'protocol_timer' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['protocol_timer']
            
            bot.send_message(call.message.chat.id, success_message)
            
            # Теперь переходим к загрузке фото ДТП
            if agent_id not in user_temp_data:
                user_temp_data[agent_id] = {}
            user_temp_data[agent_id]['dtp_photos'] = []
            user_temp_data[agent_id]['contract_data'] = data

            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_upload_client_{agent_id}")
            keyboard.add(btn_finish)

            bot.send_message(
                call.message.chat.id,
                "📸 Прикрепите фото с ДТП\n\n"
                "Фото должны быть четкими, не засвечены. Обзор 360 градусов.\n"
                "Можно отправлять по одной фотографии или несколько сразу.\n"
                "Когда загрузите все фото, нажмите кнопку ниже:",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка при сохранении фото протокола: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении фото.")
    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_dtp_photos_upload_client_'))
    @prevent_double_click(timeout=3.0)
    def finish_dtp_photos_upload_callback(call):
        """Завершение загрузки фото ДТП"""
        client_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if client_id not in user_temp_data or 'dtp_photos' not in user_temp_data[client_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[client_id]['dtp_photos']
            data = user_temp_data[client_id]['contract_data']
            
            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_upload_client_{client_id}")
                keyboard.add(btn_finish)
                
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Прикрепите фото с ДТП:",
                    reply_markup=keyboard
                )
                return
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF из фото ДТП
            pdf_path = f"{client_dir}/Фото_ДТП.pdf"
            create_pdf_from_images2(photos, pdf_path)
            
            # Очищаем временные данные
            del user_temp_data[client_id]['dtp_photos']
            msg = bot.send_message(
                    call.message.chat.id,
                    "✅ Фото с ДТП успешно загружены!",
                    reply_markup=None
                )
            finish_document_upload(call.message.chat.id, data['client_id'], data, msg.message_id)
        except Exception as e:
            print(f"Ошибка при сохранении фото ДТП: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении фото.")
    @bot.callback_query_handler(func=lambda call: call.data.startswith("dop_osm_yes_"))
    @prevent_double_click(timeout=3.0)
    def handle_dop_osm_yes(call):
        """Клиент согласен на доп осмотр"""
        client_id = call.data.replace("dop_osm_yes_", "")

        contract = get_client_from_db_by_client_id(client_id)
        if contract:
            actual_user_id = contract.get('user_id')
            if actual_user_id:
                user_id = int(actual_user_id)
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return

        try:
            if contract.get('data_json'):
                import json
                json_data = json.loads(contract['data_json'])
                data = {**contract, **json_data}
            else:
                data = contract
        except:
            data = contract
        
        # Сохраняем в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}

        user_temp_data[user_id]['dop_osm_data'] = data
        user_temp_data[user_id]['client_id'] = client_id

        # Обновляем статус в БД
        from database import DatabaseManager
        db = DatabaseManager()
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE clients 
                    SET data_json = jsonb_set(
                        COALESCE(data_json::jsonb, '{}'::jsonb),
                        '{dop_osm_answer}',
                        '"Yes"'
                    )
                    WHERE client_id = %s
                """, (client_id,))
                conn.commit()
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🤖 Подготовьте:\n1. Принятое страховой Заявление\n2. Акт осмотра ТС\n3. Предзапись в СТО"
        )
        msg2 = bot.send_message(
            chat_id=call.message.chat.id,
            text="Введите входящий номер в страховую"
        )
        user_message_id = msg2.message_id 
        bot.register_next_step_handler(msg2, Nv_ins, data, user_message_id, msg.message_id)

    def Nv_ins(message, data, user_message_id, message_id):
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"Nv_ins": message.text})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_nv_ins_client"))
        msg = bot.send_message(
            message.chat.id, 
            text="Введите номер акта осмотра ТС",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, Na_ins, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_nv_ins_client")
    @prevent_double_click(timeout=3.0)
    def back_to_nv_ins(call):
        """Возврат к вводу входящего номера"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'dop_osm_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['dop_osm_data']
            data.pop('Nv_ins', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        msg = bot.send_message(
            call.message.chat.id,
            "🤖 Подготовьте:\n1. Принятое страховой Заявление\n2. Акт осмотра ТС\n3. Предзапись в СТО"
        )
        msg2 = bot.send_message(
            call.message.chat.id,
            "Введите входящий номер в страховую"
        )
        user_message_id = msg2.message_id
        bot.register_next_step_handler(msg2, Nv_ins, data, user_message_id, msg.message_id)

    def Na_ins(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        data.update({"Na_ins": message.text})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_na_ins_client"))
        msg = bot.send_message(
            message.chat.id, 
            text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_na_ins_client")
    @prevent_double_click(timeout=3.0)
    def back_to_na_ins(call):
        """Возврат к вводу номера акта"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'dop_osm_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['dop_osm_data']
            data.pop('Na_ins', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_nv_ins_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите номер акта осмотра ТС",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, Na_ins, data, user_message_id)
    def date_Na_ins(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_Na_ins": message.text})

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_na_ins_client"))
            msg = bot.send_message(
                message.chat.id, 
                text="Введите адрес своего СТО",
                reply_markup=keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, address_sto_main, data, user_message_id)
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_na_ins_client"))
            msg = bot.send_message(
                message.chat.id, 
                text="Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_na_ins_client")
    @prevent_double_click(timeout=3.0)
    def back_to_date_na_ins(call):
        """Возврат к вводу даты акта"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'dop_osm_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['dop_osm_data']
            data.pop('date_Na_ins', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_na_ins_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)
    def address_sto_main(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        data.update({"address_sto_main": message.text})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_sto_main_client"))
        msg = bot.send_message(
            message.chat.id, 
            text="Введите дату записи в свое СТО для дополнительного осмотра в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_sto_main, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_address_sto_main_client")
    @prevent_double_click(timeout=3.0)
    def back_to_address_sto_main(call):
        """Возврат к вводу адреса СТО"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'dop_osm_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['dop_osm_data']
            data.pop('address_sto_main', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_na_ins_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите адрес своего СТО",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, address_sto_main, data, user_message_id)
    def date_sto_main(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_sto_main": message.text})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_sto_main_client"))
            msg = bot.send_message(
                message.chat.id, 
                text="Введите время записи в свое СТО для дополнительного осмотра в формате ЧЧ:ММ",
                reply_markup=keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, time_sto_main, data, user_message_id)
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_sto_main_client"))
            msg = bot.send_message(
                message.chat.id, 
                text="Неправильный формат ввода!\nВведите дату записи в свое СТО для дополнительного осмотра в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_sto_main, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_sto_main_client")
    @prevent_double_click(timeout=3.0)
    def back_to_date_sto_main(call):
        """Возврат к вводу даты СТО"""
        client_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if client_id in user_temp_data and 'dop_osm_data' in user_temp_data[client_id]:
            data = user_temp_data[client_id]['dop_osm_data']
            data.pop('date_sto_main', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_sto_main_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите дату записи в свое СТО для дополнительного осмотра в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_sto_main, data, user_message_id)
    def time_sto_main(message, data, user_message_id):
        user_id = message.from_user.id
        
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        if len(message.text) != 5 or message.text.count(':') != 1:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_sto_main_client"))
            msg = bot.send_message(
                message.chat.id,
                "Неправильный формат времени!\n"
                "Введите время записи в свое СТО для дополнительного осмотра в формате ЧЧ:ММ (например: 14:30)",
                reply_markup=keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, time_sto_main, data, user_message_id)
            return
        
        try:
            datetime.strptime(message.text, "%H:%M")

            data.update({"time_sto_main": message.text})
            data.update({"dop_osm": "Yes"})
            data.update({"data_dop_osm": str(datetime.now().strftime("%d.%m.%Y"))})

            
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                        
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            
            if data.get("N_dov_not", '') != '':
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
                                    "Шаблоны/1. ДТП/1. На ремонт/4. Заявление о проведении доп осмотра/4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx")
                try:
                    with open("clients/"+str(data["client_id"])+"/Документы/"+"4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            else:
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
                                    "Шаблоны/1. ДТП/1. На ремонт/4. Заявление о проведении доп осмотра/4. Заявление о проведении дополнительного осмотра автомобиля.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"4. Заявление о проведении дополнительного осмотра автомобиля.docx")
                try:
                    with open("clients/"+str(data["client_id"])+"/Документы/"+"4. Заявление о проведении дополнительного осмотра автомобиля.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_sto_main_client"))
            msg = bot.send_message(
                message.chat.id, 
                "Неправильный формат времени!\n"
                "Введите время записи в свое СТО в формате ЧЧ:ММ (например: 14:30)",
                reply_markup=keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, time_sto_main, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("dop_osm_no_"))
    @prevent_double_click(timeout=3.0)
    def handle_dop_osm_no(call):
        """Клиент не согласен на доп осмотр"""
        client_id = call.data.replace("dop_osm_no_", "")
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Спасибо за ответ! Если передумаете, в личном кабинете можно составить заявление."
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("client_answer_insurance_"))
    @prevent_double_click(timeout=3.0)
    def callback_client_answer_insurance(call):
        """Ответ от страховой от клиента"""
        user_id = call.from_user.id
        client_id = call.data.replace("client_answer_insurance_", "")
        
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
        
        # Сохраняем в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['answer_insurance_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = contract.get('user_id')
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("💰 Получена выплата", callback_data="client_answer_payment"))
        keyboard.add(types.InlineKeyboardButton("🔧 Получено направление на ремонт", callback_data="client_answer_repair"))
        keyboard.add(types.InlineKeyboardButton("📋 У виновника ДТП Нет ОСАГО", callback_data=f"NoOsago_prod_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"view_contract_{client_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Что получено от страховой?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "client_answer_payment")
    @prevent_double_click(timeout=3.0)
    def client_answer_payment(call):
        """Клиент получил выплату - запрашиваем сумму"""
        user_id = call.from_user.id
        client_id = user_temp_data[user_id]['client_id']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"client_answer_insurance_{client_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💰 Введите сумму выплаты по ОСАГО (только число):",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(call.message, process_client_insurance_payment_amount, user_id, call.message.message_id)


    def process_client_insurance_payment_amount(message, user_id, prev_message_id):
        """Обработка суммы выплаты от страховой для клиента"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            amount = float(message.text.strip().replace(',', '.'))
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Введите корректное число:")
            bot.register_next_step_handler(msg, process_client_insurance_payment_amount, user_id, msg.message_id)
            return
        
        client_id = user_temp_data[user_id]['client_id']
        
        # Получаем текущее значение coin_osago
        from database import get_client_from_db_by_client_id
        client_data = get_client_from_db_by_client_id(client_id)
        
        try:
            data_json = json.loads(client_data.get('data_json', '{}'))
            current_osago = float(data_json.get('coin_osago', 0))
        except:
            current_osago = 0
        
        # Прибавляем новую сумму
        new_total = current_osago + amount
        
        # Обновляем в базе
        client_data['coin_osago'] = new_total
        
        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(client_data)
            client_data.update(updated_data)
            print(client_data)
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
        
        # Сохраняем сумму для загрузки квитанции
        user_temp_data[user_id]['client_insurance_osago_amount'] = amount
        user_temp_data[user_id]['client_insurance_osago_total'] = new_total
        
        # Инициализируем сессию загрузки квитанции
        chat_id = message.chat.id
        upload_sessions[chat_id] = {
            'client_id': user_id,
            'photos': [],
            'message_id': None,
            'number_id': client_id,
            'type': 'client_insurance_payment'
        }
        
        msg = bot.send_message(
            chat_id,
            f"✅ Добавлено: {amount} руб.\n"
            f"💰 Общая сумма выплат: {new_total} руб.\n\n"
            f"📸 Теперь загрузите квитанцию (одну или несколько фотографий):",
            reply_markup=create_upload_keyboard_client_insurance()
        )
        
        upload_sessions[chat_id]['message_id'] = msg.message_id


    def create_upload_keyboard_client_insurance():
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_upload_client_insurance_payment"))
        return keyboard


    @bot.callback_query_handler(func=lambda call: call.data == 'finish_upload_client_insurance_payment')
    def handle_finish_upload_client_insurance_payment(call):
        """Завершение загрузки квитанции после выплаты от страховой (клиент)"""
        chat_id = call.message.chat.id
        
        if chat_id not in upload_sessions or not upload_sessions[chat_id]['photos']:
            bot.answer_callback_query(call.id, "❌ Нет загруженных фото")
            return
        
        session = upload_sessions[chat_id]
        
        try:
            # Определяем имя файла
            client_id = session['number_id']
            docs_dir = f"clients/{client_id}/Документы"
            
            # Проверяем существующие квитанции
            counter = 1
            filename = "Квитанция.pdf"
            while os.path.exists(os.path.join(docs_dir, filename)):
                counter += 1
                filename = f"Квитанция{counter}.pdf"
            
            pdf_path = os.path.join(docs_dir, filename)
            
            # Создаем PDF из фото
            create_kvitancia_pdf(session['photos'], session['number_id'], pdf_path)
            
            # Удаляем сообщение с кнопкой
            bot.delete_message(chat_id, session['message_id'])
            
            user_id = session['client_id']
            osago_amount = user_temp_data.get(user_id, {}).get('client_insurance_osago_amount', 0)
            osago_total = user_temp_data.get(user_id, {}).get('client_insurance_osago_total', 0)
            
            bot.send_message(
                chat_id,
                f"✅ Квитанция успешно сохранена как '{filename}'!\n"
                f"💰 Добавлено: {osago_amount} руб.\n"
                f"💰 Итого выплат: {osago_total} руб.\n"
                f"📸 Загружено фото: {len(session['photos'])}"
            )
            
            # Очищаем сессию
            del upload_sessions[chat_id]
            if user_id in user_temp_data:
                user_temp_data[user_id].pop('client_insurance_osago_amount', None)
                user_temp_data[user_id].pop('client_insurance_osago_total', None)
            
            # Теперь спрашиваем про заявление на выдачу документов
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data="docsInsYes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data="docsInsNo"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"client_answer_insurance_{client_id}"))
            
            bot.send_message(
                chat_id,
                "Необходимо заявление на выдачу документов из страховой?",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Error creating PDF: {e}")
            bot.send_message(chat_id, "❌ Ошибка при создании PDF файла")
        
        bot.answer_callback_query(call.id)


    @bot.callback_query_handler(func=lambda call: call.data == "client_answer_repair")
    @prevent_double_click(timeout=3.0)
    def client_answer_repair(call):
        """Клиент получил направление на ремонт - сразу к вопросу о заявлении"""
        user_id = call.from_user.id
        client_id = user_temp_data[user_id]['client_id']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data="docsInsYes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data="docsInsNo"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"client_answer_insurance_{client_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходимо заявление на выдачу документов из страховой?",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data in ["docsInsNo"])
    @prevent_double_click(timeout=3.0)
    def handle_answer_docs_no(call):
        user_id = call.from_user.id
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data=f"vibor1"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data=f"vibor2"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data=f"vibor3"))
        keyboard.add(types.InlineKeyboardButton("4", callback_data=f"vibor4"))
        keyboard.add(types.InlineKeyboardButton("5", callback_data=f"vibor5"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"client_answer_insurance_{user_temp_data[user_id]['client_id']}"))
        bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = "Выберите из предложенных вариантов:\n\n1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n" \
        "2) Страховая компания выдала направление на ремонт, СТО отказала.\n" \
        "3) У страховой компании нет СТО.\n" \
        "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.\n" \
        "5) Страховая компания не организовала ремонт.",
        reply_markup = keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["docsInsYes"])
    @prevent_double_click(timeout=3.0)
    def handle_answer_docs_yes(call):
        user_id = call.from_user.id
        print(user_temp_data)
        client_id = user_temp_data[user_id]['client_id']
        contract = get_client_from_db_by_client_id(client_id)

        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return

        try:
            if contract.get('data_json'):
                import json
                json_data = json.loads(contract['data_json'])
                data = {**contract, **json_data}
            else:
                data = contract
        except:
            data = contract
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
                            "Шаблоны/1. ДТП/1. На ремонт/5. Запрос в страховую о выдаче акта и расчета/5. Запрос в страховую о выдаче акта и расчёта представитель.docx",
                                "clients/"+str(data["client_id"])+"/Документы/"+"Запрос в страховую о выдаче акта и расчёта представитель.docx")
            try:
                with open("clients/"+str(data["client_id"])+"/Документы/"+"Запрос в страховую о выдаче акта и расчёта представитель.docx", 'rb') as document_file:
                    bot.send_document(
                        call.message.chat.id, 
                        document_file,
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
                            "Шаблоны/1. ДТП/1. На ремонт/5. Запрос в страховую о выдаче акта и расчета/5. Запрос в страховую о выдаче акта и расчёта.docx",
                                "clients/"+str(data["client_id"])+"/Документы/"+"Запрос в страховую о выдаче акта и расчёта.docx")
            try:
                with open("clients/"+str(data["client_id"])+"/Документы/"+"Запрос в страховую о выдаче акта и расчёта.docx", 'rb') as document_file:
                    bot.send_document(
                        call.message.chat.id, 
                        document_file,
                    )   
            except FileNotFoundError:

                bot.send_message(call.message.chat.id, f"Файл не найден")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data=f"vibor1"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data=f"vibor2"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data=f"vibor3"))
        keyboard.add(types.InlineKeyboardButton("4", callback_data=f"vibor4"))
        keyboard.add(types.InlineKeyboardButton("5", callback_data=f"vibor5"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"client_answer_insurance_{client_id}"))
        bot.send_message(call.message.chat.id, "Выберите из предложенных вариантов:\n\n1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n" \
        "2) Страховая компания выдала направление на ремонт, СТО отказала.\n" \
        "3) У страховой компании нет СТО.\n" \
        "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.\n" \
        "5) Страховая компания не организовала ремонт.",
        reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data in ["vibor1","vibor2","vibor3","vibor4", "vibor5"])
    @prevent_double_click(timeout=3.0)
    def handle_vibor(call):
        user_id = call.from_user.id
        client_id = user_temp_data[user_id]['client_id']
        
        if call.data in ["vibor1", "vibor3","vibor4", "vibor5"]:
            contract = get_client_from_db_by_client_id(client_id)

            if not contract:
                bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
                return

            try:
                if contract.get('data_json'):
                    import json
                    json_data = json.loads(contract['data_json'])
                    data = {**contract, **json_data}
                else:
                    data = contract
            except:
                data = contract
            data.update({"vibor": call.data})
            data.update({"status": "Ожидание претензии"})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)              
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                reply_markup = keyboard
            )

        elif call.data == "vibor2":

            contract = get_client_from_db_by_client_id(client_id)
            if not contract:
                bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
                return
            try:
                if contract.get('data_json'):
                    import json
                    json_data = json.loads(contract['data_json'])
                    data = {**contract, **json_data}
                else:
                    data = contract
            except:
                data = contract
            data.update({"vibor": call.data})
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название СТО"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, name_sto, data, user_message_id)
    
    def name_sto(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
    
        data.update({"name_sto": message.text})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_vibor_client"))
        message = bot.send_message(
            message.chat.id, 
            text="Введите ИНН СТО",
            reply_markup=keyboard
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, inn_sto, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_vibor_client")
    @prevent_double_click(timeout=3.0)
    def back_to_vibor(call):
        """Возврат к выбору варианта ответа страховой"""
        user_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data=f"vibor1"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data=f"vibor2"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data=f"vibor3"))
        keyboard.add(types.InlineKeyboardButton("4", callback_data=f"vibor4"))
        keyboard.add(types.InlineKeyboardButton("5", callback_data=f"vibor5"))
        bot.send_message(
            call.message.chat.id, 
            "Выберите из предложенных вариантов:\n\n"
            "1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n"
            "2) Страховая компания выдала направление на ремонт, СТО отказала.\n"
            "3) У страховой компании нет СТО.\n"
            "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.\n"
            "5) Страховая компания не организовала ремонт.",
            reply_markup=keyboard
        )
    def create_kvitancia_pdf(photo_paths, client_id, pdf_path=None):
        """Создает PDF файл из загруженных фото"""
        # Создаем папки если не существуют
        docs_path = f"clients/{client_id}/Документы"
        os.makedirs(docs_path, exist_ok=True)
        
        if pdf_path is None:
            pdf_path = os.path.join(docs_path, "Квитанция.pdf")
        
        # Конвертируем фото в PDF
        images = []
        for photo_path in photo_paths:
            try:
                img = Image.open(photo_path)
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                images.append(img)
            except Exception as e:
                print(f"Error opening image {photo_path}: {e}")
        
        if images:
            # Сохраняем как PDF
            images[0].save(
                pdf_path, 
                "PDF", 
                resolution=100.0, 
                save_all=True, 
                append_images=images[1:]
            )
    def inn_sto(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"inn_sto": message.text})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_name_sto_client"))
            message = bot.send_message(
                message.chat.id, 
                text="Введите индекс СТО, например, 123456",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_sto, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_vibor_client"))
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН СТО",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, inn_sto, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_name_sto_client")
    @prevent_double_click(timeout=3.0)
    def back_to_name_sto(call):
        """Возврат к вводу названия СТО"""
        user_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if user_id in user_temp_data and 'contract_data' in user_temp_data[user_id]:
            data = user_temp_data[user_id]['contract_data']
            data.pop('inn_sto', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_vibor_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите название СТО",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, name_sto, data, user_message_id)
    def index_sto(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_inn_sto_client"))
            message = bot.send_message(
                message.chat.id, 
                text="Неправильный формат ввода, должно быть 6 цифр!\nВведите индекс СТО, например, 123456",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_sto, data, user_message_id)
        else:
            data.update({"index_sto": message.text})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_index_sto_client"))
            message = bot.send_message(
                message.chat.id, 
                text="Введите адрес СТО",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_sto, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_inn_sto_client")
    @prevent_double_click(timeout=3.0)
    def back_to_inn_sto(call):
        """Возврат к вводу ИНН СТО"""
        user_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if user_id in user_temp_data and 'contract_data' in user_temp_data[user_id]:
            data = user_temp_data[user_id]['contract_data']
            data.pop('index_sto', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_name_sto_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите ИНН СТО",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, inn_sto, data, user_message_id)


    @bot.callback_query_handler(func=lambda call: call.data == "back_to_index_sto_client")
    @prevent_double_click(timeout=3.0)
    def back_to_index_sto(call):
        """Возврат к вводу индекса СТО"""
        user_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if user_id in user_temp_data and 'contract_data' in user_temp_data[user_id]:
            data = user_temp_data[user_id]['contract_data']
            data.pop('address_sto', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_inn_sto_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите индекс СТО, например, 123456",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, index_sto, data, user_message_id)
    def address_sto(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        data.update({"address_sto": message.text})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_sto_client"))
        message = bot.send_message(
            message.chat.id, 
            text="Введите номер направления СТО",
            reply_markup=keyboard
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, N_sto, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_address_sto_client")
    @prevent_double_click(timeout=3.0)
    def back_to_address_sto(call):
        """Возврат к вводу адреса СТО"""
        user_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if user_id in user_temp_data and 'contract_data' in user_temp_data[user_id]:
            data = user_temp_data[user_id]['contract_data']
            data.pop('N_sto', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_index_sto_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите адрес СТО",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, address_sto, data, user_message_id)
    def N_sto(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        data.update({"N_sto": message.text})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_n_sto_client"))
        message = bot.send_message(
            message.chat.id, 
            text="Введите дату предоставления авто на СТО в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_sto, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_n_sto_client")
    @prevent_double_click(timeout=3.0)
    def back_to_n_sto(call):
        """Возврат к вводу номера направления СТО"""
        user_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if user_id in user_temp_data and 'contract_data' in user_temp_data[user_id]:
            data = user_temp_data[user_id]['contract_data']
            data.pop('date_sto', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_sto_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите номер направления СТО",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, N_sto, data, user_message_id)
    def date_sto(message, data, user_message_id):
        if not message.text:
            return
            
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_sto": message.text})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_sto_client"))
            message = bot.send_message(
                message.chat.id, 
                text="Введите дату направления на СТО в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_n_sto_client"))
            message = bot.send_message(
                message.chat.id, 
                text="Неправильный формат ввода!\nВведите дату предоставления авто на СТО в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_sto, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_sto_client")
    @prevent_double_click(timeout=3.0)
    def back_to_date_sto(call):
        """Возврат к вводу даты предоставления авто на СТО"""
        user_id = call.from_user.id
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        if user_id in user_temp_data and 'contract_data' in user_temp_data[user_id]:
            data = user_temp_data[user_id]['contract_data']
            data.pop('date_napr_sto', None)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_n_sto_client"))
        msg = bot.send_message(
            call.message.chat.id,
            "Введите дату предоставления авто на СТО в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_sto, data, user_message_id)
    def date_napr_sto(message, data, user_message_id):
        user_id = message.from_user.id
    
        if not message.text:
            return
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_napr_sto": message.text})
            data.update({"date_zayav_sto": str(datetime.now().strftime("%d.%m.%Y"))})
            data.update({"status": "Ожидание претензии"})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                            
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")

            create_fio_data_file(data)
            if data.get("N_dov_not", '') != '':
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
                                    "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/6. Заявление в СТО представитель.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"Заявление в СТО представитель.docx")
                try:
                    with open("clients/"+str(data["client_id"])+"/Документы/"+"Заявление в СТО представитель.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
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
                                    "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/6. Заявление в СТО.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"Заявление в СТО.docx")
                try:
                    with open("clients/"+str(data["client_id"])+"/Документы/"+"Заявление в СТО.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            bot.send_message(message.chat.id, "✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                             reply_markup = keyboard)

        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_sto_client"))
            message = bot.send_message(
                message.chat.id, 
                text="Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)

def notify_directors_about_document(bot, client_id, fio, doc_type):
    """Уведомить всех директоров о новом документе"""
    db_instance = DatabaseManager()
    try:
        with db_instance.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id FROM admins 
                    WHERE admin_value = 'Директор' AND is_active = true
                """)
                directors = cursor.fetchall()
                
                for director in directors:
                    try:
                        bot.send_message(
                            director[0],
                            f"📄 {doc_type} ожидает подтверждения по договору {client_id} {fio}"
                        )
                    except Exception as e:
                        print(f"Не удалось уведомить директора {director[0]}: {e}")
    except Exception as e:
        print(f"Ошибка уведомления директоров: {e}")

def cleanup_messages(bot, chat_id, message_id, count):
    """Удаляет последние N сообщений"""
    for i in range(count):
        try:
            bot.delete_message(chat_id, message_id - i)
        except:
            pass