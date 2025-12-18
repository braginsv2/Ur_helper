from telebot import types
import re
import json
import time
import threading
import os
import psycopg2.extras
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
    ('АО "Согаз"', "SOGAZ_admin"),
    ('ПАО СК "Росгосстрах"', "Ros_admin"),
    ('САО "Ресо-Гарантия"', "Reco_admin"),
    ('АО "АльфаСтрахование"', "Alfa_admin"),
    ('СПАО "Ингосстрах"', "Ingo_admin"),
    ('САО "ВСК"', "VSK_admin"),
    ('ПАО «САК «Энергогарант»', "Energo_admin"),
    ('АО "ГСК "Югория"', "Ugo_admin"),
    ('ООО СК "Согласие"', "Soglasie_admin"),
    ('АО «Совкомбанк страхование»', "Sovko_admin"),
    ('АО "Макс"', "Maks_admin"),
    ('ООО СК "Сбербанк страхование"', "Sber_admin"),
    ('АО "Т-Страхование"', "T-ins_admin"),
    ('ПАО "Группа Ренессанс Страхование"', "Ren_admin"),
    ('АО СК "Чулпан"', "Chul_admin")
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
        row_buttons.append(types.InlineKeyboardButton('◀️ Назад', callback_data=f'admin_ins_page_{page-1}'))
    
    if end_idx < len(insurance_companies):
        row_buttons.append(types.InlineKeyboardButton('Еще ▶️', callback_data=f'admin_ins_page_{page+1}'))
    
    if row_buttons:
        keyboard.row(*row_buttons)
    
    keyboard.add(types.InlineKeyboardButton('Другое', callback_data="other_admin"))
    
    keyboard.add(types.InlineKeyboardButton("◀️ Назад к году авто", callback_data="back_to_admin_car_year"))
    
    return keyboard

def cleanup_messages(bot, chat_id, message_id, count):
        """Удаляет последние N сообщений"""
        for i in range(count):
            try:
                bot.delete_message(chat_id, message_id+1 - i)
            except:
                pass

def setup_admin_handlers(bot, user_temp_data, upload_sessions):
    """Регистрация обработчиков для самостоятельного оформления клиентом"""
    def create_back_keyboard(callback_data):
        """Создает клавиатуру с кнопкой Назад"""
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=callback_data))
        return keyboard
    
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
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("administrator_view_contract_"))
    @prevent_double_click(timeout=3.0)
    def agent_view_contract_handler(call):
        """Просмотр договора агентом своего клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=5)
        admin_id = call.from_user.id
        client_id = call.data.replace("administrator_view_contract_", "")
        
        from database import get_client_from_db_by_client_id
        contract = get_client_from_db_by_client_id(client_id)
        
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        # Парсим данные
        try:
            contract_data = json.loads(contract.get('data_json', '{}'))
        except:
            contract_data = contract
        
        # Сохраняем данные в user_temp_data
        if admin_id not in user_temp_data:
            user_temp_data[admin_id] = {}
        user_temp_data[admin_id] = contract
        user_temp_data[admin_id]['client_id'] = client_id
        
        # Формируем текст
        contract_text = f"📄 <b>Договор {client_id}</b>\n\n"
        
        if contract.get('created_at'):
            contract_text += f"📅 Дата создания: {contract.get('created_at')}\n\n"
        
        contract_text += f"<b>Информация о клиенте:</b>\n"
        contract_text += f"👤 ФИО: {contract.get('fio', 'Не указано')}\n"
        contract_text += f"📱 Телефон: {contract.get('number', 'Не указан')}\n\n"
        
        contract_text += f"<b>Информация о ДТП:</b>\n"
        if contract.get('accident'):
            contract_text += f"⚠️ Тип обращения: {contract.get('accident')}\n"
        if contract_data.get('date_dtp'):
            contract_text += f"📅 Дата ДТП: {contract_data.get('date_dtp')}\n"
        if contract_data.get('time_dtp'):
            contract_text += f"🕐 Время ДТП: {contract_data.get('time_dtp')}\n"
        if contract_data.get('address_dtp'):
            contract_text += f"📍 Адрес ДТП: {contract_data.get('address_dtp')}\n"
        if contract_data.get('insurance'):
            contract_text += f"🏢 Страховая: {contract_data.get('insurance')}\n"
        if contract.get('status'):
            contract_text += f"📊 Статус: {contract.get('status')}\n"
        
        keyboard = types.InlineKeyboardMarkup()

        print(contract_data)

        # Кнопка "Заявление на доп. осмотр" - только если еще не заполнялась
        if contract_data.get('accident') == 'ДТП':
            if contract_data.get('status', '') == "Оформлен договор":
                if contract_data.get('sobstvenik', '') == 'С начала':
                    if contract_data.get('N_dov_not', '') != '':
                        if contract_data.get('user_id', '') == '8572367590':
                            keyboard.add(types.InlineKeyboardButton("📋 Заявление в страховую", callback_data=f"dtp_continue_documents2_{client_id}"))
                        else:
                            keyboard.add(types.InlineKeyboardButton("📋 Заявление в страховую", callback_data=f"dtp_continue_documents_{client_id}"))
                else:
                    if contract_data.get('user_id', '') == '8572367590':
                        keyboard.add(types.InlineKeyboardButton("📋 Заявление в страховую", callback_data=f"dtp_continue_documents2_{client_id}"))
                    else:
                        keyboard.add(types.InlineKeyboardButton("📋 Заявление в страховую", callback_data=f"dtp_continue_documents_{client_id}"))
            else:
                if contract_data.get('dop_osm') != 'Yes' and (contract_data.get('vibor', '') == ''):
                    keyboard.add(types.InlineKeyboardButton("📋 Заявление на доп. осмотр", callback_data=f"agent_dop_osm_{client_id}"))
                    
                # Кнопка "Ответ от страховой" - только если еще не заполнялась
                if (contract_data.get('vibor', '') == ''):
                    keyboard.add(types.InlineKeyboardButton("❓ Ответ от страховой", callback_data=f"agent_answer_insurance_{client_id}"))

        elif contract_data.get('accident', '') == "Нет ОСАГО" and contract_data.get('status', '') == "Оформлен договор":
            keyboard.add(types.InlineKeyboardButton("👮 Заполнить запрос в ГИБДД", callback_data=f"agent_net_osago_continue_documents_{contract_data['client_id']}"))
        elif contract_data.get('accident', '') == "Подал заявление":
            if contract_data.get('status', '') == "Оформлен договор":
                keyboard.add(types.InlineKeyboardButton("📋 Заявление в страховую", callback_data=f"agent_podal_continue_documents_{client_id}"))

        payment_pending = contract_data.get('payment_pending', '') == 'Yes'
        payment_confirmed = contract_data.get('payment_confirmed', '') == 'Yes'
        doverennost_pending = contract_data.get('doverennost_pending', '') == 'Yes'
        doverennost_confirmed = contract_data.get('doverennost_confirmed', '') == 'Yes'


        if doverennost_pending and not doverennost_confirmed:
            contract_text += "\n⏳ Доверенность ожидает проверки"
        elif doverennost_confirmed:
            contract_text += "\n📜 Доверенность подтверждена"

        # Проверяем, загружена ли оплата
        payment_confirmed = contract_data.get('payment_confirmed', '') == 'Yes'
        if not payment_confirmed and not payment_pending:
            keyboard.add(types.InlineKeyboardButton("💰 Оплатить Юр.услуги", callback_data="load_payment"))
        elif payment_pending and not payment_confirmed:
            contract_text += "\n\n⏳ Оплата ожидает проверки"
        else:
            contract_text += "\n💰 Юридические услуги оплачены"
            try:
                db = DatabaseManager()
                with db.get_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                        cursor.execute("""
                            SELECT receipt_number, receipt_uploaded_at 
                            FROM pending_approvals 
                            WHERE client_id = %s AND document_type = 'payment' AND status = 'approved'
                            ORDER BY reviewed_at DESC LIMIT 1
                        """, (client_id,))
                        receipt_data = cursor.fetchone()
                        
                        if receipt_data and receipt_data['receipt_number']:
                            contract_text += f"\n   📝 Номер чека: {receipt_data['receipt_number']}"
                            if receipt_data['receipt_uploaded_at']:
                                # Форматируем дату
                                uploaded_date = receipt_data['receipt_uploaded_at']
                                if isinstance(uploaded_date, str):
                                    from datetime import datetime
                                    uploaded_date = datetime.fromisoformat(uploaded_date)
                                contract_text += f"\n   📅 Дата загрузки: {uploaded_date.strftime('%d.%m.%Y %H:%M:%S')}"
            except Exception as e:
                print(f"Ошибка получения данных чека: {e}")
        # Проверяем, загружена ли доверенность
        doverennost_provided = contract_data.get('doverennost_provided', '') == 'Yes'
        if not doverennost_provided:
            keyboard.add(types.InlineKeyboardButton("📨 Загрузить доверенность", callback_data="download_dov_not"))
        if contract_data.get('calculation', '') == '' or contract_data.get('calculation', '') == None:
            keyboard.add(types.InlineKeyboardButton("💰 Загрузить калькуляцию", callback_data=f"download_calc_{client_id}"))
        if contract_data.get('accident', '') != 'После ямы' and contract_data.get('accident', '') != 'Нет ОСАГО':
            keyboard.add(types.InlineKeyboardButton("📤 Добавить выплату от страховой", callback_data="add_osago_payment"))
        keyboard.add(types.InlineKeyboardButton("📸 Загрузить фото ДТП", callback_data="download_foto"))
        keyboard.add(types.InlineKeyboardButton("📤 Загрузить документы", callback_data="download_docs"))
        keyboard.add(types.InlineKeyboardButton("✏️ Редактировать данные", callback_data=f"edit_contract_data_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("📋 Просмотр данных", callback_data="view_db"))
        keyboard.add(types.InlineKeyboardButton("📂 Просмотреть документы", callback_data="view_client_documents"))
        keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_my_clients"))
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.send_message(
            chat_id=call.message.chat.id,
            text=contract_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    # ========== НАЧАЛО ОФОРМЛЕНИЯ ДОГОВОРА КЛИЕНТОМ ==========
    @bot.callback_query_handler(func=lambda call: call.data == "callback_registr_alone")
    @prevent_double_click(timeout=3.0)
    def admin_new_contract_handler(call):
        """Самостоятельное заполнение договора Администратором"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        data = {}
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="btn_add_client"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="👤 Введите ФИО клиента в формате: Иванов Иван Иванович",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(msg, admin_fio, data, msg.message_id)

    def admin_fio(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        if len(message.text.split()) < 2:
            keyboard = create_back_keyboard("btn_add_client")
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО клиента в формате: Иванов Иван Иванович", reply_markup=keyboard)
            user_message_id = message.message_id
            bot.register_next_step_handler(message, admin_fio, data, user_message_id)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():
                    keyboard = create_back_keyboard("btn_add_client")
                    message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО клиента в формате Иванов Иван Иванович", reply_markup=keyboard)
                    user_message_id = message.message_id
                    bot.register_next_step_handler(message, admin_fio, data, user_message_id)
                    return
            
            data.update({"fio": message.text})
            if len(message.text.split())==2:
                data.update({"fio_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."})
            else:
                data.update({"fio_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."+list(message.text.split()[2])[0]+"."})
            
            keyboard = create_back_keyboard("callback_registr_alone")
            message = bot.send_message(message.chat.id, text="Введите номер телефона клиента в формате: +7ХХХХХХХХХХ", reply_markup=keyboard)
            user_message_id = message.message_id
            bot.register_next_step_handler(message, admin_number, data, user_message_id)

    def admin_number(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        phone = message.text.strip()
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            keyboard = create_back_keyboard("callback_registr_alone")
            msg = bot.send_message(message.chat.id, "❌ Неверный формат.\nВведите номер телефона клиента в формате: +7ХХХХХХХХХХ", reply_markup = keyboard)
            bot.register_next_step_handler(msg, admin_number, data, msg.message_id)
            return
        
        data.update({'number': phone})

        passport_info_msg = bot.send_message(
            message.chat.id,
            "🤖 <b>Заполните паспортные данные</b>",
            parse_mode='HTML'
        )
        user_temp_data[user_id] = data
        user_temp_data[user_id].update({'pasport_message_id': passport_info_msg.message_id})

        keyboard = create_back_keyboard("back_to_admin_number")
        msg = bot.send_message(message.chat.id, text="Введите серию паспорта клиента, 4 цифры", reply_markup=keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, admin_seria_pasport, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_number")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_number(call):
        """Возвращение к вводу номера телефона клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        try:
            bot.delete_message(user_id, user_temp_data[user_id]['pasport_message_id'])
            del user_temp_data[user_id]['pasport_message_id']
        except:
            pass

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("callback_registr_alone")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер телефона клиента в формате: +7ХХХХХХХХХХ",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(call.message, admin_number, data, msg.message_id)
    
    def admin_seria_pasport(message, data, user_message_id):
        """Обработка серии паспорта"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        series = message.text.strip()
        
        if not series.isdigit() or len(series) != 4:
            keyboard = create_back_keyboard("back_to_admin_number")
            msg = bot.send_message(
                message.chat.id,
                "❌ Серия паспорта должна содержать 4 цифры.\nВведите серию паспорта клиента, 4 цифры",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_seria_pasport, data, msg.message_id)
            return
        
        data.update({'seria_pasport': series})
        user_temp_data[user_id].update(data)
        
        keyboard = create_back_keyboard("back_to_admin_seria_pasport")
        msg = bot.send_message(message.chat.id, "Введите номер паспорта клиента, 6 цифр", reply_markup=keyboard)
        bot.register_next_step_handler(msg, admin_number_pasport, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_seria_pasport")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_seria_pasport(call):
        """Возвращение к вводу серии паспорта клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_number")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию паспорта клиента, 4 цифры",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(call.message, admin_seria_pasport, data, msg.message_id)

    def admin_number_pasport(message, data, user_message_id):
        """Обработка номера паспорта"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        number = message.text.strip()
        
        if not number.isdigit() or len(number) != 6:
            keyboard = create_back_keyboard("back_to_admin_seria_pasport")
            msg = bot.send_message(
                message.chat.id,
                "❌ Номер паспорта должна содержать 6 цифр.\nВведите номер паспорта клиента, 6 цифр",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_number_pasport, data, msg.message_id)
            return
        
        data.update({'number_pasport': number})
        user_temp_data[user_id].update(data)
        
        keyboard = create_back_keyboard("back_to_admin_number_pasport")
        msg = bot.send_message(message.chat.id, "Введите кем выдан паспорт клиента", reply_markup=keyboard)
        bot.register_next_step_handler(msg, admin_where_pasport, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_number_pasport")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_number_pasport(call):
        """Возвращение к вводу серии паспорта клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_seria_pasport")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер паспорта клиента, 6 цифр",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(call.message, admin_number_pasport, data, msg.message_id)

    def admin_where_pasport(message, data, user_message_id):
        """Обработка кем выдан паспорт"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        data.update({'where_pasport': message.text})
        user_temp_data[user_id].update(data)
        
        keyboard = create_back_keyboard("back_to_admin_where_pasport")
        msg = bot.send_message(message.chat.id, "Введите когда выдан паспорт клиента в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
        bot.register_next_step_handler(msg, admin_when_pasport, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_where_pasport")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_where_pasport(call):
        """Возвращение к вводу кем выдан паспорт клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_number_pasport")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите кем выдан паспорт клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(call.message, admin_where_pasport, data, msg.message_id)

    def admin_when_pasport(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        try:
            input_date = datetime.strptime(message.text.strip(), "%d.%m.%Y")
            data.update({'when_pasport': message.text.strip()})
            user_temp_data[user_id].update(data)
            
            keyboard = create_back_keyboard("back_to_admin_when_pasport")
            msg = bot.send_message(message.chat.id, "Введите дату рождения клиента в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
            bot.register_next_step_handler(msg, admin_date_of_birth, data, msg.message_id)


        except ValueError:
            keyboard = create_back_keyboard("back_to_admin_where_pasport")
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите когда выдан паспорт клиента в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
            bot.register_next_step_handler(msg, admin_when_pasport, data, msg.message_id)
            return
        
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_when_pasport")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_when_pasport(call):
        """Возвращение к вводу когда выдан паспорт клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_where_pasport")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите когда выдан паспорт клиента в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(call.message, admin_when_pasport, data, msg.message_id)

    def admin_date_of_birth(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        try:
            input_date = datetime.strptime(message.text.strip(), "%d.%m.%Y")
            data.update({'date_of_birth': message.text.strip()})
            user_temp_data[user_id].update(data)
            
            keyboard = create_back_keyboard("back_to_admin_date_of_birth")
            msg = bot.send_message(message.chat.id, "Введите город рождения клиента", reply_markup=keyboard)
            bot.register_next_step_handler(msg, admin_city_birth, data, msg.message_id)

        except ValueError:
            keyboard = create_back_keyboard("back_to_admin_when_pasport")
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату рождения клиента в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
            bot.register_next_step_handler(msg, admin_when_pasport, data, msg.message_id)
            return
        
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_date_of_birth")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_date_of_birth(call):
        """Возвращение к вводу даты рождения клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_when_pasport")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату рождения клиента в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(call.message, admin_date_of_birth, data, msg.message_id)

    def admin_city_birth(message, data, user_message_id):

        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        data.update({'city_birth': message.text})
        user_temp_data[user_id].update(data)
        
        keyboard = create_back_keyboard("back_to_admin_city_birth")
        msg = bot.send_message(message.chat.id, "Введите адрес регистрации по паспорту клиента", reply_markup=keyboard)
        bot.register_next_step_handler(msg, admin_address, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_city_birth")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_city_birth(call):
        """Возвращение к вводу города рождения клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_date_of_birth")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите город рождения клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(call.message, admin_city_birth, data, msg.message_id)

    def admin_address(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        data.update({'address': message.text})
        user_temp_data[user_id].update(data)
        
        keyboard = create_back_keyboard("back_to_admin_address")
        msg = bot.send_message(message.chat.id, "Введите почтовый индекс клиента, 6 цифр", reply_markup=keyboard)
        bot.register_next_step_handler(msg, admin_index, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_address")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_address(call):
        """Возвращение к вводу адреса прописки клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_city_birth")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес регистрации по паспорту клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(call.message, admin_address, data, msg.message_id)

    def admin_index(message, data, user_message_id):
        """Обработка почтового индекса"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        index = message.text.strip()
        
        if not index.isdigit() or len(index) != 6:
            keyboard = create_back_keyboard("back_to_admin_address")
            msg = bot.send_message(
                message.chat.id,
                "❌ Почтовый индекс должен содержать 6 цифр.\nВведите почтовый индекс клиента, 6 цифр",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_index, data, msg.message_id)
            return
        
        data.update({'index_postal': index})
        user_temp_data[user_id].update(data)
        try:
            bot.delete_message(message.chat.id, user_temp_data[user_id]['pasport_message_id'])
        except:
            print("Сообщение с заполнением паспортных данных не удалено!!!")

        try:
            del user_temp_data[user_id]['pasport_message_id']
        except:
            print("pasport_message_id не удален!!!")
        
        data = user_temp_data[user_id]
        keyboard = create_back_keyboard("back_to_admin_index")
        # Переходим к загрузке фото паспорта
        msg = bot.send_message(
            message.chat.id,
            "✅ Данные приняты!\n\n🤖 Прикрепите фото основного разворота паспорта (2-3 стр):",
            reply_markup = keyboard
        )
    
        bot.register_next_step_handler(msg, admin_passport_photo_2_3, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_index")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_index(call):
        """Возвращение к вводу почтового индекса клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_address")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите почтовый индекс клиента, 6 цифр",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(call.message, admin_index, data, msg.message_id)

    def admin_passport_photo_2_3(message, data, message_id):
        """Обработка фото 2-3 страницы паспорта для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)

        file_id = None
        file_extension = None
        
        if message.photo:
            file_id = message.photo[-1].file_id
            file_extension = "jpg"
        elif message.document:
            mime_type = message.document.mime_type
            file_name = message.document.file_name.lower()
            
            allowed_formats = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf']
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.heic']
            
            if (mime_type not in allowed_formats and 
                not any(file_name.endswith(ext) for ext in allowed_extensions)):
                try:
                    bot.delete_message(message.chat.id, message_id)
                    bot.delete_message(message.chat.id, message.message_id)
                except:
                    pass
                keyboard = create_back_keyboard("back_to_admin_index")
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Неподдерживаемый формат файла. Отправьте фото или файл в формате JPG, PNG, PDF:\n\n"
                    "Прикрепите фото основного разворота паспорта (2-3 стр):",
                    reply_markup = keyboard
                )
                bot.register_next_step_handler(msg, admin_passport_photo_2_3, data, msg.message_id)
                return
            
            file_id = message.document.file_id
            if '.' in file_name:
                file_extension = file_name.split('.')[-1]
            elif mime_type == 'application/pdf':
                file_extension = 'pdf'
            elif mime_type == 'image/png':
                file_extension = 'png'
            else:
                file_extension = 'jpg'
        else:
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            keyboard = create_back_keyboard("back_to_admin_index")
            msg = bot.send_message(
                message.chat.id, 
                "❌ Пожалуйста, отправьте фото или файл. Прикрепите фото основного разворота паспорта (2-3 стр):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_passport_photo_2_3, data, msg.message_id)
            return
        
        try:
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            fio = data.get('fio', 'Unknown')
            folder_path = f"admins_info/{fio}"
            os.makedirs(folder_path, exist_ok=True)
            
            file_path = f"{folder_path}/Паспорт_2-3.{file_extension}"
            
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            keyboard = create_back_keyboard("back_to_admin_photo_2_3")
            msg = bot.send_message(
                message.chat.id, 
                "✅ Файл принят!\n\n📎 Теперь прикрепите фотографию страницы паспорта с регистрацией (разворот страниц 4–5 или 6–7).",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_passport_photo_4_5, data, msg.message_id)
            
        except Exception as e:
            print(f"❌ Ошибка при обработке файла: {e}")
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            keyboard = create_back_keyboard("back_to_admin_index")
            msg = bot.send_message(
                message.chat.id, 
                "❌ Ошибка при загрузке файла. Попробуйте еще раз:\n\n"
                "Прикрепите фото основного разворота паспорта (2-3 стр):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_passport_photo_2_3, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_photo_2_3")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_photo_2_3(call):
        """Возвращение к загрузке фото паспотра клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]
        
        keyboard = create_back_keyboard("back_to_admin_index")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Данные приняты!\n\n🤖 Прикрепите фото основного разворота паспорта (2-3 стр):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_passport_photo_2_3, data, msg.message_id)

    def admin_passport_photo_4_5(message, data, message_id):
        """Обработка фото 4-5 страницы паспорта для приглашенного клиента - ФИНАЛ"""
        file_id = None
        file_extension = None
        user_id = message.from_user.id
        if message.photo:
            file_id = message.photo[-1].file_id
            file_extension = "jpg"
        elif message.document:
            mime_type = message.document.mime_type
            file_name = message.document.file_name.lower()
            
            allowed_formats = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf']
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.heic']
            
            if (mime_type not in allowed_formats and 
                not any(file_name.endswith(ext) for ext in allowed_extensions)):
                try:
                    bot.delete_message(message.chat.id, message_id)
                    bot.delete_message(message.chat.id, message.message_id)
                except:
                    pass
                keyboard = create_back_keyboard("back_to_admin_photo_2_3")
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Неподдерживаемый формат файла. Отправьте фото или файл в формате JPG, PNG, PDF:\n\n"
                    "Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):",
                    reply_markup = keyboard
                )
                bot.register_next_step_handler(msg, admin_passport_photo_4_5, data, msg.message_id)
                return
            
            file_id = message.document.file_id
            if '.' in file_name:
                file_extension = file_name.split('.')[-1]
            elif mime_type == 'application/pdf':
                file_extension = 'pdf'
            elif mime_type == 'image/png':
                file_extension = 'png'
            else:
                file_extension = 'jpg'
        else:
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            keyboard = create_back_keyboard("back_to_admin_photo_2_3")
            msg = bot.send_message(
                message.chat.id, 
                "❌ Пожалуйста, отправьте фото или файл. Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_passport_photo_4_5, data, msg.message_id)
            return
        
        try:
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            fio = data.get('fio', 'Unknown')
            folder_path = f"admins_info/{fio}"
            os.makedirs(folder_path, exist_ok=True)
            
            file_path = f"{folder_path}/Прописка.{file_extension}"
            
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            # Удаляем промежуточные сообщения
            if 'passport_info_message_id' in data:
                try:
                    bot.delete_message(message.chat.id, data['passport_info_message_id'])
                except:
                    pass
            
            try:
                bot.delete_message(message.chat.id, message.message_id)
                bot.delete_message(message.chat.id, message_id)
            except:
                pass
            data_admin = get_admin_from_db_by_user_id(user_id)
            data.update({'city': str(data_admin['city_admin'])})
            data.update({'year': str(datetime.now().year)[-2:]})
            data.update({'user_id': '8572367590'})
            data.update({'agent_id': str(user_id)})
            data.update({'creator_user_id': str(message.from_user.id)})
            print(data)
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="admin_accident_dtp")
            btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="admin_accident_podal_zayavl")
            btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="admin_accident_pit")
            btn4 = types.InlineKeyboardButton("❌ У виновника ДТП нет ОСАГО", callback_data="admin_accident_net_osago")
            
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)

            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_photo_4_5"))
            msg = bot.send_message(
                message.chat.id, 
                "Выберите тип обращения",
                reply_markup = keyboard
            )


        except Exception as e:
            print(f"❌ Ошибка при обработке файла: {e}")
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            keyboard = create_back_keyboard("back_to_admin_photo_2_3")
            msg = bot.send_message(
                message.chat.id, 
                "❌ Ошибка при загрузке файла. Попробуйте еще раз:\n\n"
                "Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_passport_photo_4_5, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_photo_4_5")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_photo_4_5(call):
        """Возвращение к загрузке фото прописки клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]
        
        keyboard = create_back_keyboard("back_to_admin_photo_2_3")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Данные приняты!\n\n🤖 Прикрепите фото прописки паспорта (4-5 или 6-7 стр):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_passport_photo_4_5, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_accident_"))
    @prevent_double_click(timeout=3.0)
    def handle_admin_accident_type(call):
        """Обработка выбора типа обращения клиентом"""
        user_id = call.from_user.id
        
        if call.data == 'admin_accident_dtp':
            user_temp_data[user_id].update({'accident': "ДТП"})
            context = f"Примерные сроки:\n\nПримерная дата первой выплаты от Страховой в случае отказа производить восстановительный ремонт {(datetime.now() + timedelta(days=20)).strftime('%d.%m.%Y')}\n\nПримерная дата завершения дела {(datetime.now() + timedelta(days=280)).strftime('%d.%m.%Y')}\n\nЭвакуатор вызывали?"
        elif call.data == 'admin_accident_podal_zayavl':
            user_temp_data[user_id].update({'accident': "Подал заявление"})
            context = f"Примерная дата завершения дела {(datetime.now() + timedelta(days=280)).strftime('%d.%m.%Y')}\n\nЭвакуатор вызывали?"
        elif call.data == 'admin_accident_pit':
            user_temp_data[user_id].update({'accident': "После ямы"})
            context = f"Эвакуатор вызывали?"
        elif call.data == 'admin_accident_net_osago':
            user_temp_data[user_id].update({'accident': "Нет ОСАГО"})
            context = f"Примерная дата завершения дела {(datetime.now() + timedelta(days=90)).strftime('%d.%m.%Y')}\n\nЭвакуатор вызывали?"
        else:
            context = f"Эвакуатор вызывали?"
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="admin_ev_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="admin_ev_no")
        btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_accident_choice")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_accident_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_accident_choice(call):
        """Возвращение к выбору типа обращения"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="admin_accident_dtp")
        btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="admin_accident_podal_zayavl")
        btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="admin_accident_pit")
        btn4 = types.InlineKeyboardButton("❌ У виновника ДТП нет ОСАГО", callback_data="admin_accident_net_osago")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)

        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_photo_4_5"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите тип обращения",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_passport_photo_4_5, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["admin_ev_yes", "admin_ev_no"])
    @prevent_double_click(timeout=3.0)
    def handle_admin_evacuator(call):
        """Обработка эвакуатора"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "admin_ev_yes":
            user_temp_data[user_id].update({'ev': "Да"})
        elif call.data == "admin_ev_no":
            user_temp_data[user_id].update({'ev': "Нет"})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_admin"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_admin"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_ev"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату ДТП:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_ev")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_ev(call):
        """Обработка эвакуатора"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="admin_ev_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="admin_ev_no")
        btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_accident_choice")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Эвакуатор вызывали?",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_date_today_admin", "dtp_date_other_admin"])
    @prevent_double_click(timeout=3.0)
    def handle_dtp_date_choice(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "dtp_date_today_admin":
            # Красноярское время
            from datetime import datetime
            import pytz
            krasnoyarsk_tz = pytz.timezone('Asia/Krasnoyarsk')
            date_dtp = datetime.now(krasnoyarsk_tz).strftime("%d.%m.%Y")
            user_temp_data[user_id].update({'date_dtp': date_dtp})
            data = user_temp_data[user_id]
            # Продолжить к следующему шагу (время ДТП)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_dtp"))
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Дата ДТП: {date_dtp}\n\nВведите время ДТП (ЧЧ:ММ):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(call.message, admin_dtp_time, data, msg.message_id)
            
        elif call.data == "dtp_date_other_admin":
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_dtp"))
            data = user_temp_data[user_id]
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДТП (ДД.ММ.ГГГГ):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(call.message, admin_date_dtp, data, msg.message_id) 

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_date_dtp")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_ev(call):
        """Обработка эвакуатора"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_admin"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_admin"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_ev"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату ДТП:",
            reply_markup=keyboard
        )

    def admin_date_dtp(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        date_text = message.text.strip()
        
        try:
            input_date = datetime.strptime(date_text, "%d.%m.%Y")
            current_date = datetime.now()
            three_years_ago = current_date - timedelta(days=3*365 + 1)

            if input_date > current_date:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_dtp"))
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Дата ДТП не может быть в будущем!\nВведите корректную дату ДТП:",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, admin_date_dtp, data, msg.message_id)
                return
            
            if input_date < three_years_ago:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_dtp"))
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Прошло более трех лет!\nВведите корректную дату ДТП:",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, admin_date_dtp, data, msg.message_id)
                return
            
            
            data.update({'date_dtp': date_text})
            user_temp_data[user_id].update(data)
            
            keyboard = create_back_keyboard("back_to_admin_date_dtp")
            msg = bot.send_message(message.chat.id, "Введите время ДТП в формате ЧЧ:ММ", reply_markup=keyboard)
            bot.register_next_step_handler(msg, admin_dtp_time, data, msg.message_id)
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_dtp"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите дату ДТП в формате ДД.ММ.ГГГГ:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_date_dtp, data, msg.message_id)
            return
        
    def admin_dtp_time(message, data, prev_msg_id):
        """Обработка времени ДТП"""
        if not message.text:
            return
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        time_text = message.text.strip()
        
        if not re.match(r'^\d{2}:\d{2}$', time_text):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_dtp"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат времени. Введите время ДТП в формате ЧЧ:ММ:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_dtp_time, data, msg.message_id)
            return
        data.update({'time_dtp': time_text})
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_dtp_time"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите адрес ДТП:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_dtp_address, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_dtp_time")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_dtp_time(call):
        """Обработка возврата к дате ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_dtp")
        keyboard.add(btn1)
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите время ДТП в формате ЧЧ:ММ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_dtp_time, data, msg.message_id)

    def admin_dtp_address(message, data, prev_msg_id):
        """Обработка адреса ДТП"""
        if not message.text:
            return
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({'address_dtp': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        if data.get('ev', '') == 'Да':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_address_dtp"))
            msg = bot.send_message(
                message.chat.id, 
                "Введите адрес местонахождения транспортного средства, где будет произведена оценка ущерба.",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_address_park, data, msg.message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd_admin"))
            keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro_admin"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_address_dtp"))
            msg = bot.send_message(
                message.chat.id, 
                "Выберите документ фиксации ДТП", 
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_address_dtp")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_address_dtp(call):
        """Обработка возврата к адресу ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_dtp_time")
        keyboard.add(btn1)
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес ДТП",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_dtp_address, data, msg.message_id)

    def admin_address_park(message, data, prev_msg_id):
        """Обработка адреса парковки"""
        if not message.text:
            return
        user_id = message.from_user.id    
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({'address_park': message.text.strip()})
        user_temp_data[user_id].update(data)

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd_admin"))
        keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro_admin"))
        if data.get('ev', '') == 'Да':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_address_park"))
        else:
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_address_dtp"))
        msg = bot.send_message(
            message.chat.id, 
            "Выберите документ фиксации ДТП", 
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_address_park")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_address_park(call):
        """Обработка возврата к адресу парковки"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_address_dtp")
        keyboard.add(btn1)
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес местонахождения транспортного средства, где будет произведена оценка ущерба.",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_address_park, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_gibdd_admin", "dtp_evro_admin"])
    @prevent_double_click(timeout=3.0)
    def handle_dtp_gibdd_evro_admin(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        if call.data == "dtp_gibdd_admin":
            data.update({'who_dtp': "По форме ГИБДД"})
        elif call.data == "dtp_evro_admin":
            data.update({'who_dtp': "Евро-протокол"})

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_who_dtp"))
        
        msg = bot.send_message(
            call.message.chat.id,
            "Введите марку и модель авто клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_marks, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_who_dtp")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_who_dtp(call):
        """Обработка возврата к адресу парковки"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd_admin"))
        keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro_admin"))
        if data.get('ev', '') == 'Да':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_address_park"))
        else:
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_address_dtp"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите документ фиксации ДТП",
            reply_markup=keyboard
        )

    def admin_marks(message, data, user_message_id):
        """Обработка марки и модели авто клиента"""
        user_id = message.from_user.id

        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'marks': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_early")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите номер вашего авто (например, А123БВ77):", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_car_number, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_marks")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_marks(call):
        """Обработка возврата к адресу парковки"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_who_dtp"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку и модель авто клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_marks, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "admin_non_standart_number_car_early")
    @prevent_double_click(timeout=3.0)
    def handle_client_non_standart_number_early(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_car_number"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер вашего авто",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_non_standart_car_number, data, msg.message_id)

    def admin_non_standart_car_number(message, data, user_message_id):
        """Обработка марки и модели авто клиента"""
        user_id = message.from_user.id

        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'car_number': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_non_standart_number_car_early")
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите год выпуска авто (например, 2025)", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_car_year, data, msg.message_id)

    def admin_car_number(message, data, user_message_id):
        """Обработка номера авто клиента"""
        if not message.text:
            return
        user_id = message.from_user.id    
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
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_early")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n"
                "Все буквы должны быть заглавными!\n\n"
                "Введите номер вашего авто (Пример: А123БВ77)",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_car_number, data, msg.message_id)
            return
        
        if not match:
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_early")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks")
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
            bot.register_next_step_handler(msg, admin_car_number, data, msg.message_id)
            return
        
        # Извлекаем части номера
        letter1 = match.group(1)  # Первая буква
        digits = match.group(2)   # 3 цифры
        letters2 = match.group(3) # 2 буквы
        region = match.group(4)   # Код региона (2-3 цифры)
        
        # Проверяем, что цифры не состоят только из нулей
        if digits == "000":
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_early")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Основные цифры номера не могут быть 000\n\n"
                "Введите корректный номер авто (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_car_number, data, msg.message_id)
            return
        
        # Проверяем, что код региона не состоит только из нулей
        if region == "00" or region == "000":
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_early")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Код региона не может быть 00 или 000\n\n"
                "Введите корректный номер авто (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_car_number, data, msg.message_id)
            return
        
        # Все проверки пройдены - сохраняем номер
        data.update({'car_number' : car_number})
        user_temp_data[user_id].update(data)
        
        # Запрашиваем год авто
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_car_number"))
        msg = bot.send_message(
            message.chat.id, 
            "Введите год выпуска авто (например, 2025)",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_car_year, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_car_number")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_car_number(call):
        """Обработка возврата к вводу номера авто клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_early")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер авто клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_car_number, data, msg.message_id)

    def admin_car_year(message, data, user_message_id):
        """Обработка года выпуска авто клиента"""
        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        user_id = message.from_user.id
        text = message.text.replace(" ", "")
        
        # Проверка формата
        if len(text) != 4 or not text.isdigit():
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_car_number"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите корректный год выпуска авто клиента (например, 2025)",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_car_year, data, msg.message_id)
            return
        
        year = int(text)
        current_year = datetime.now().year
        
        # Проверка диапазона
        if not (1900 < year <= current_year):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_car_number"))
            msg = bot.send_message(
                message.chat.id, 
                f"❌ Год должен быть в диапазоне от 1901 до {current_year}!\nВведите корректный год выпуска авто клиента",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_car_year, data, msg.message_id)
            return
        
        # Сохраняем год
        data.update({'year_auto': str(year)})
        user_temp_data[user_id].update(data)
        
        # ПЕРЕХОД К ВЫБОРУ СТРАХОВОЙ
        keyboard = create_insurance_keyboard(page=0,show_back=True)
        bot.send_message(
            message.chat.id,
            "Выберите страховую компанию виновника ДТП",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_ins_page_'))
    @prevent_double_click(timeout=3.0)
    def handle_admin_insurance_pagination_early(call):
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


    @bot.callback_query_handler(func=lambda call: call.data in ["Reco_admin", "Ugo_admin", "SOGAZ_admin", "Ingo_admin", "Ros_admin", "Maks_admin", "Energo_admin", "Sovko_admin", "Alfa_admin", "VSK_admin", "Soglasie_admin", "Sber_admin", "T-ins_admin", "Ren_admin", "Chul_admin", "other_admin"] and call.from_user.id in user_temp_data)
    @prevent_double_click(timeout=3.0)
    def callback_admin_insurance_early(call):
        """Обработка выбора страховой компании клиентом ДО договора"""
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        insurance_mapping = {
            "SOGAZ_admin": 'АО "Согаз"',
            "Ros_admin": 'ПАО СК "Росгосстрах"',
            "Reco_admin": 'САО "Ресо-Гарантия"',
            "Alfa_admin": 'АО "АльфаСтрахование"',
            "Ingo_admin": 'СПАО "Ингосстрах"',
            "VSK_admin": 'САО "ВСК"',
            "Energo_admin": 'ПАО «САК «Энергогарант»',
            "Ugo_admin": 'АО "ГСК "Югория"',
            "Soglasie_admin": 'ООО СК "Согласие"',
            "Sovko_admin": 'АО «Совкомбанк страхование»',
            "Maks_admin": 'АО "Макс"',
            "Sber_admin": 'ООО СК "Сбербанк страхование"',
            "T-ins_admin": 'АО "Т-Страхование"',
            "Ren_admin": 'ПАО "Группа Ренессанс Страхование"',
            "Chul_admin": 'АО СК "Чулпан"'
        }
        
        if call.data in insurance_mapping:
            data.update({'insurance': insurance_mapping[call.data]})
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_insurance"))
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию страхового полиса",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_seria_insurance, data, msg.message_id)
        else: 
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_insurance"))
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_other_insurance, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_car_year")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_car_year(call):
        """Обработка возврата к вводу номера авто клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_car_number")
        keyboard.add(btn_back)
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите год выпуска авто (например, 2025)",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_car_year, data, msg.message_id)

    def admin_other_insurance(message, data, user_message_id):
        """Обработка другой страховой компании"""
        user_id = message.from_user.id

        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'insurance': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_insurance")
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите серию страхового полиса", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_seria_insurance, data, msg.message_id)

    def admin_seria_insurance(message, data, user_message_id):
        """Обработка другой страховой компании"""
        user_id = message.from_user.id

        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'seria_insurance': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_seria_insurance")
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите номер страхового полиса", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_number_insurance, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_insurance(call):
        """Обработка возврата к вводу номера авто клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = create_insurance_keyboard(page=0,show_back=True)
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите страховую компанию виновника ДТП",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_seria_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_seria_insurance(call):
        """Обработка возврата к вводу серии страхового полиса"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_insurance"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_seria_insurance, data, msg.message_id)

    def admin_number_insurance(message, data, user_message_id):
        """Обработка номера страховой компании"""
        user_id = message.from_user.id

        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'number_insurance': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_insurance")
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите дату заключения договора ОСАГО в формате ДД.ММ.ГГГГ", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_date_insurance, data, msg.message_id)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_number_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_number_insurance(call):
        """Обработка возврата к вводу номера страхового полиса"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_seria_insurance"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер страхового полиса",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_number_insurance, data, msg.message_id)

    def admin_date_insurance(message, data, user_message_id):
        """Обработка даты страхового полиса"""
        if not message.text:
            return
        user_id = message.from_user.id
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
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_insurance"))
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Дата не может быть в будущем!\n"
                    "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, admin_date_insurance, data, msg.message_id)
                return
            
            # Проверка: дата не старше 1 года
            if insurance_date < two_years_ago:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_insurance"))
                msg = bot.send_message(
                    message.chat.id, 
                    f"❌ Полис не может быть старше 1 года!\n"
                    f"Минимальная дата: {two_years_ago.strftime('%d.%m.%Y')}\n\n"
                    "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, admin_date_insurance, data, msg.message_id)
                return
            
            # Все проверки пройдены - сохраняем дату
            data.update({'date_insurance' : message.text.strip()})
            user_temp_data[user_id].update(data)
            if data.get('accident', '') != 'После ямы':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_insurance"))
                msg = bot.send_message(
                    message.chat.id, 
                    "Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, admin_fio_culp, data, msg.message_id)
            else:
                show_admin_contract_summary(message, data)
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_insurance"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\n"
                "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_date_insurance, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_date_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_date_insurance(call):
        """Обработка возврата к вводу даты страхового полиса"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_insurance"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_date_insurance, data, msg.message_id)

    def admin_fio_culp(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        if len(message.text.split()) < 2:
            keyboard = create_back_keyboard("back_to_admin_date_insurance")
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, admin_fio_culp, data, user_message_id)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():
                    keyboard = create_back_keyboard("back_to_admin_date_insurance")
                    message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович", reply_markup=keyboard)
                    user_message_id = message.message_id
                    bot.register_next_step_handler(message, admin_fio_culp, data, user_message_id)
                    return
            
            data.update({"fio_culp": message.text})
            user_temp_data[user_id].update(data)
            keyboard = create_back_keyboard("back_to_admin_fio_culp")
            msg = bot.send_message(message.chat.id, text="Введите марку и модель авто виновника ДТП", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, admin_marks_culp, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_fio_culp")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_fio_culp(call):
        """Обработка возврата к вводу фио виновника ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_insurance"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_fio_culp, data, msg.message_id)

    def admin_marks_culp(message, data, user_message_id):
        """Обработка марки авто виновника ДТП"""
        user_id = message.from_user.id

        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'marks_culp': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_culp")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks_culp")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.send_message(
            message.chat.id, 
            "Введите номер авто виновника ДТП", 
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_number_auto_culp, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_marks_culp")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_marks_culp(call):
        """Обработка возврата к вводу марки авто виновника ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_fio_culp"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку и модель авто виновника ДТП",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_marks_culp, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "admin_non_standart_number_car_culp")
    @prevent_double_click(timeout=3.0)
    def admin_non_standart_number_car_culp(call):
        """Обработка нестандартного номера авто виновника ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_auto_culp"))
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер авто виновника ДТП",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_non_standart_number_auto_culp, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_number_auto_culp")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_number_auto_culp(call):
        """Обработка возврата к вводу номера авто виновника ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_culp")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks_culp")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер авто виновника ДТП",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_number_auto_culp, data, msg.message_id)

    def admin_non_standart_number_auto_culp(message, data, user_message_id):
        """Обработка марки авто виновника ДТП"""
        user_id = message.from_user.id

        if not message.text:
            return
            
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'number_auto_culp': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        show_admin_contract_summary(message, data)

    def admin_number_auto_culp(message, data, user_message_id):
        """Обработка номера авто виновника - ФИНАЛ ПЕРЕД ПОКАЗОМ ИТОГОВ"""
        if not message.text:
            return
        user_id = message.from_user.id
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

            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks_culp")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n"
                "Все буквы должны быть заглавными!\n\n"
                "Введите номер авто виновника ДТП (Пример: А123БВ77)",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_number_auto_culp, data, msg.message_id)
            return
        
        if not match:
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks_culp")
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
            bot.register_next_step_handler(msg, admin_number_auto_culp, data, msg.message_id)
            return
        
        # Извлекаем части номера
        letter1 = match.group(1)  # Первая буква
        digits = match.group(2)   # 3 цифры
        letters2 = match.group(3) # 2 буквы
        region = match.group(4)   # Код региона (2-3 цифры)
        
        # Проверяем, что цифры не состоят только из нулей
        if digits == "000":
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks_culp")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Основные цифры номера не могут быть 000\n\n"
                "Введите корректный номер авто виновника ДТП (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_number_auto_culp, data, msg.message_id)
            return
        
        # Проверяем, что код региона не состоит только из нулей
        if region == "00" or region == "000":
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"admin_non_standart_number_car_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_marks_culp")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Код региона не может быть 00 или 000\n\n"
                "Введите корректный номер авто виновника ДТП (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_number_auto_culp, data, msg.message_id)
            return
        
        # Все проверки пройдены - сохраняем номер
        data.update({'number_auto_culp' :str(car_number)})
        user_temp_data[user_id].update(data)
        
        # Показываем итоговые данные
        show_admin_contract_summary(message, data)

    def show_admin_contract_summary(message, data):
        """Отправка ПОЛНЫХ данных договора админу на подтверждение"""
        
        # Формируем сообщение для клиента со ВСЕМИ данными
        summary = "📋 <b>Проверьте данные договора:</b>\n\n"
        summary += f"👤 ФИО: {data.get('fio', '')}\n"
        summary += f"📅 Дата рождения: {data.get('date_of_birth', '')}\n"
        summary += f"📍 Город: {data.get('city', '')}\n"
        summary += f"📄 Паспорт: {data.get('seria_pasport', '')} {data.get('number_pasport', '')}\n"
        summary += f"📍 Выдан: {data.get('where_pasport', '')}\n"
        summary += f"📅 Дата выдачи: {data.get('when_pasport', '')}\n"
        summary += f"📍 Место рождения: {data.get('city_birth', '')}\n"
        summary += f"📮 Индекс: {data.get('index_postal', '')}\n"
        summary += f"🏠 Адрес: {data.get('address', '')}\n\n"
        
        summary += f"<b>Данные о ДТП:</b>\n"
        summary += f"🚗 Дата ДТП: {data.get('date_dtp', '')}\n"
        summary += f"⏰ Время ДТП: {data.get('time_dtp', '')}\n"
        summary += f"📍 Адрес ДТП: {data.get('address_dtp', '')}\n"
        summary += f"📍 Фиксация ДТП: {data.get('who_dtp', '')}\n\n"
        
        summary += f"<b>Автомобиль клиента:</b>\n"
        summary += f"🚙 Марка/модель: {data.get('marks', '')}\n"
        summary += f"🔢 Номер: {data.get('car_number', '')}\n"
        summary += f"📅 Год выпуска: {data.get('year_auto', '')}\n\n"
        
        summary += f"<b>Страховая компания:</b>\n"
        summary += f"🏢 Название: {data.get('insurance', '')}\n"
        summary += f"📋 Полис: {data.get('seria_insurance', '')} {data.get('number_insurance', '')}\n"
        summary += f"📅 Дата полиса: {data.get('date_insurance', '')}\n\n"
        
        summary += f"<b>Виновник ДТП:</b>\n"
        summary += f"👤 ФИО: {data.get('fio_culp', '')}\n"
        summary += f"🚙 Марка/модель: {data.get('marks_culp', '')}\n"
        summary += f"🔢 Номер авто: {data.get('number_auto_culp', '')}\n"

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"admin_confirm_contract"))
        keyboard.add(types.InlineKeyboardButton("✏️ Редактировать данные", callback_data=f"admin_edit_contract"))
  
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        bot.send_message(message.chat.id, summary, parse_mode='HTML', reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "admin_edit_contract")
    @prevent_double_click(timeout=3.0)
    def admin_edit_contract(call):
        """Начало редактирования отклоненного договора"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data:
            bot.answer_callback_query(call.id, "❌ Данные для редактирования не найдены", show_alert=True)
            return
        
        # Показываем меню редактирования
        admin_show_contract_edit_menu(bot, call.message.chat.id, call.message.message_id, user_id, user_temp_data)


    def admin_show_contract_edit_menu(bot, chat_id, message_id, user_id, user_temp_data):
        """Показать меню редактирования договора"""
        if user_id not in user_temp_data:
            bot.send_message(chat_id, "❌ Ошибка: данные для редактирования не найдены")
            return
        
        data = user_temp_data[user_id]
        
        # Формируем текст с текущими данными
        text = "📋 <b>Текущие данные договора:</b>\n\n"
        
        # Персональные данные
        text += "<b>Персональные данные:</b>\n"
        text += f"👤 ФИО: {data.get('fio', 'не указано')}\n"
        text += f"🏙 Город: {data.get('city', 'не указано')}\n"
        text += f"📱 Номер телефона: {data.get('number', 'не указан')}\n"
        text += f"📅 Дата рождения: {data.get('date_of_birth', 'не указана')}\n"
        text += f"🏙 Место рождения: {data.get('city_birth', 'не указано')}\n"
        text += f"📄 Серия паспорта: {data.get('seria_pasport', 'не указана')}\n"
        text += f"📄 Номер паспорта: {data.get('number_pasport', 'не указан')}\n"
        text += f"📍 Кем выдан: {data.get('where_pasport', 'не указано')}\n"
        text += f"📅 Дата выдачи: {data.get('when_pasport', 'не указана')}\n"
        text += f"📮 Индекс: {data.get('index_postal', 'не указан')}\n"
        text += f"🏠 Адрес: {data.get('address', 'не указан')}\n\n"
        
        # Данные о ДТП
        text += "<b>Данные о ДТП:</b>\n"
        text += f"🚗 Дата ДТП: {data.get('date_dtp', 'не указана')}\n"
        text += f"⏰ Время ДТП: {data.get('time_dtp', 'не указано')}\n"
        text += f"📍 Адрес ДТП: {data.get('address_dtp', 'не указан')}\n"
        text += f"🚗 Фиксация ДТП: {data.get('who_dtp', 'не указан')}\n\n"
        
        # Автомобиль клиента
        text += "<b>Автомобиль клиента:</b>\n"
        text += f"🚙 Марка/модель: {data.get('marks', 'не указано')}\n"
        text += f"🔢 Номер авто: {data.get('car_number', 'не указан')}\n"
        text += f"📅 Год выпуска: {data.get('year_auto', 'не указан')}\n\n"
        
        # Страховая компания
        text += "<b>Страховая компания:</b>\n"
        text += f"🏢 Название: {data.get('insurance', 'не указано')}\n"
        text += f"📋 Серия полиса: {data.get('seria_insurance', 'не указана')}\n"
        text += f"📋 Номер полиса: {data.get('number_insurance', 'не указан')}\n"
        text += f"📅 Дата полиса: {data.get('date_insurance', 'не указана')}\n\n"
        
        # Виновник ДТП
        text += "<b>Виновник ДТП:</b>\n"
        text += f"👤 ФИО виновника: {data.get('fio_culp', 'не указано')}\n"
        text += f"🚙 Марка/модель: {data.get('marks_culp', 'не указано')}\n"
        text += f"🔢 Номер авто: {data.get('number_auto_culp', 'не указан')}\n\n"
        
        text += "Выберите поле для редактирования:"
        
        # Создаем клавиатуру с кнопками редактирования
        keyboard = types.InlineKeyboardMarkup()
        
        # Персональные данные
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО", callback_data="admin_edit_field_fio"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер телефона", callback_data="admin_edit_field_number"))
        keyboard.add(types.InlineKeyboardButton("✏️ Город", callback_data="admin_edit_field_city"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата рождения", callback_data="admin_edit_field_date_of_birth"))
        keyboard.add(types.InlineKeyboardButton("✏️ Место рождения", callback_data="admin_edit_field_city_birth"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия паспорта", callback_data="admin_edit_field_seria_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер паспорта", callback_data="admin_edit_field_number_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Кем выдан паспорт", callback_data="admin_edit_field_where_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата выдачи паспорта", callback_data="admin_edit_field_when_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Индекс", callback_data="admin_edit_field_index_postal"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес", callback_data="admin_edit_field_address"))
        
        # Данные о ДТП
        keyboard.add(types.InlineKeyboardButton("✏️ Дата ДТП", callback_data="admin_edit_field_date_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Время ДТП", callback_data="admin_edit_field_time_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес ДТП", callback_data="admin_edit_field_address_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Фиксация ДТП", callback_data="admin_edit_field_who_dtp"))
        
        # Автомобиль клиента
        keyboard.add(types.InlineKeyboardButton("✏️ Марка/модель авто", callback_data="admin_edit_field_marks"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер авто", callback_data="admin_edit_field_car_number"))
        keyboard.add(types.InlineKeyboardButton("✏️ Год выпуска", callback_data="admin_edit_field_year_auto"))
        
        # Страховая компания
        keyboard.add(types.InlineKeyboardButton("✏️ Название страховой", callback_data="admin_edit_field_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия полиса", callback_data="admin_edit_field_seria_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер полиса", callback_data="admin_edit_field_number_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата полиса", callback_data="admin_edit_field_date_insurance"))
        
        # Виновник ДТП
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО виновника", callback_data="admin_edit_field_fio_culp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Марка/модель виновника", callback_data="admin_edit_field_marks_culp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер авто виновника", callback_data="admin_edit_field_number_auto_culp"))
        
        # Кнопки действий
        keyboard.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data="admin_confirm_contract"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_edit_field_"))
    @prevent_double_click(timeout=3.0)
    def admin_edit_field(call):
        """Начало редактирования конкретного поля"""
        user_id = call.from_user.id
        field = call.data.replace("admin_edit_field_", "")
        
        if user_id not in user_temp_data:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        data = user_temp_data[user_id]
        # Названия полей для отображения
        field_names = {
            # Персональные данные
            'fio': 'ФИО (Иванов Иван Иванович)',
            'number': 'Номер телефона (+79123456789)',
            'date_of_birth': 'Дата рождения (ДД.ММ.ГГГГ)',
            'city': 'Город',
            'city_birth': 'Место рождения',
            'seria_pasport': 'Серия паспорта (4 цифры)',
            'number_pasport': 'Номер паспорта (6 цифр)',
            'when_pasport': 'Дата выдачи паспорта (ДД.ММ.ГГГГ)',
            'where_pasport': 'Кем выдан паспорт',
            'index_postal': 'Индекс (6 цифр)',
            'address': 'Адрес проживания',
            
            # Данные о ДТП
            'date_dtp': 'Дата ДТП (ДД.ММ.ГГГГ)',
            'time_dtp': 'Время ДТП (ЧЧ:ММ)',
            'address_dtp': 'Адрес ДТП',
            'who_dtp': 'Фиксация ДТП (По форме ГИБДД / Евро-протокол)',
            
            # Автомобиль клиента
            'marks': 'Марка и модель авто',
            'car_number': 'Номер авто (А123БВ77)',
            'year_auto': 'Год выпуска авто (например, 2025)',
            
            # Страховая компания
            'insurance': 'Название страховой компании',
            'seria_insurance': 'Серия страхового полиса',
            'number_insurance': 'Номер страхового полиса',
            'date_insurance': 'Дата полиса (ДД.ММ.ГГГГ)',
            
            # Виновник ДТП
            'fio_culp': 'ФИО виновника (Иванов Иван Иванович)',
            'marks_culp': 'Марка и модель авто виновника',
            'number_auto_culp': 'Номер авто виновника (А123БВ77)'
        }
        
        field_display = field_names.get(field, field)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✏️ Редактирование поля: <b>{field_display}</b>\n\n"
                f"Текущее значение: <code>{data[field]}</code>\n\n"
                f"Введите новое значение:",
            parse_mode='HTML'
        )
        
        bot.register_next_step_handler(call.message, admin_process_field_edit, data, call.message.message_id, field)


    def admin_process_field_edit(message, data, prev_msg_id, field):
        """Обработка нового значения поля"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if user_id not in user_temp_data:
            bot.send_message(message.chat.id, "❌ Ошибка: сессия редактирования потеряна")
            return
        
        new_value = message.text.strip()
        
        # Валидация в зависимости от типа поля
        validation_error = None
        
        # Даты
        if field in ['date_of_birth', 'when_pasport', 'date_dtp', 'date_insurance']:
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', new_value):
                validation_error = "❌ Неверный формат даты! Используйте ДД.ММ.ГГГГ"
            else:
                try:
                    datetime.strptime(new_value, "%d.%m.%Y")
                except ValueError:
                    validation_error = "❌ Некорректная дата!"
        
        # Время
        elif field == 'time_dtp':
            if not re.match(r'^\d{2}:\d{2}$', new_value):
                validation_error = "❌ Неверный формат времени! Используйте ЧЧ:ММ"
        
        # Номер паспорта
        elif field == 'number_pasport':
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Номер паспорта должен содержать 6 цифр"
        
        # Серия паспорта
        elif field == 'seria_pasport':
            if not new_value.isdigit() or len(new_value) != 4:
                validation_error = "❌ Серия паспорта должна содержать 4 цифры"
        
        # Индекс
        elif field == 'index_postal':
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Индекс должен содержать 6 цифр"
        
        # ФИО (клиента и виновника)
        elif field in ['fio', 'fio_culp']:
            if len(new_value.split()) < 2:
                validation_error = "❌ Неправильный формат! Введите ФИО (минимум Фамилия Имя):"
            else:
                words = new_value.split()
                for word in words:
                    if not word[0].isupper():
                        validation_error = "❌ Каждое слово должно начинаться с заглавной буквы!"
                        break
        
        # Номер телефона
        elif field == 'number':
            clean_number = ''.join(filter(str.isdigit, new_value))
            if len(clean_number) != 11:
                validation_error = "❌ Номер телефона должен содержать 11 цифр (например: +79123456789)"
        
        # Год выпуска
        elif field == 'year_auto':
            if not new_value.isdigit() or len(new_value) != 4:
                validation_error = "❌ Год должен быть 4-значным числом (например: 2025)"
            else:
                year = int(new_value)
                current_year = datetime.now().year
                if not (1900 < year <= current_year):
                    validation_error = f"❌ Год должен быть в диапазоне от 1901 до {current_year}"
        
        # Если есть ошибка валидации - запрашиваем снова
        if validation_error:
            msg = bot.send_message(message.chat.id, validation_error + "\n\nВведите значение снова:")
            bot.register_next_step_handler(msg, admin_process_field_edit, data, msg.message_id, field)
            return
        
        # Сохраняем новое значение
        data[field] = new_value
        user_temp_data[user_id].update(data)
        # Возвращаемся в меню редактирования
        msg = bot.send_message(message.chat.id, f"✅ Поле обновлено!")
        admin_show_contract_edit_menu(bot, message.chat.id, msg.message_id, user_id, user_temp_data)




    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_confirm_contract"))
    @prevent_double_click(timeout=3.0)
    def admin_confirm_contract(call):
        """Обработка ответа про нотариальную доверенность"""
        user_id = call.from_user.id
        
        # КРИТИЧЕСКИ ВАЖНО: проверяем наличие данных
        if user_id not in user_temp_data:
            bot.answer_callback_query(call.id, "❌ Данные потеряны (сессия истекла)", show_alert=True)
            return
        
        data = user_temp_data[user_id]
        


        keyboard = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("1", callback_data=f"admin_not_dov_yes")
        btn_no = types.InlineKeyboardButton("2", callback_data=f"admin_not_dov_no")
        btn_no2 = types.InlineKeyboardButton("3", callback_data=f"admin_not_dov_no2")
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
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_not_dov_"))
    @prevent_double_click(timeout=3.0)
    def confirm_not_dov_yes(call):
        """Подтверждение этапа доверенности"""
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        if "admin_not_dov_yes" in call.data:
            data.update({'sobstvenik': 'С начала'})
        elif "admin_not_dov_no" in call.data:
            data.update({'sobstvenik': 'После заявления в страховую'})
        else:
            data.update({'sobstvenik': 'После ответа от страховой'})

        fields_to_remove = [
            'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
            'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
            'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back',
            'editing_contract', 'editing_field', 'client_user_id', 'data', 'step_history', 'add_client_mode', 'search_fio'
        ]
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        for field in fields_to_remove:
            data.pop(field, None)
        data.update({'status': 'Оформлен договор'})
        try:
            from database import save_client_to_db_with_id_new
            updated_client_id, updated_data = save_client_to_db_with_id_new(data)
            data.update(updated_data)
            print(data)
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")

        # ФОРМИРУЕМ ОБЛОЖКУ ДЕЛА
        create_fio_data_file(data)
        
        if data.get('accident', '') != 'После ямы':
            replace_words_in_word(
                ["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}", "{{ NКлиента }}", "{{ ФИО }}",
                "{{ Страховая }}", "{{ винФИО }}"],
                [str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), 
                str(data.get("marks",'')), str(data.get("car_number",'')),
                str(data.get('year','')), str(data.get('client_id','')), str(data.get("fio",'')), 
                str(data.get("insurance",'')), str(data.get("fio_culp",''))],
                "Шаблоны/1. ДТП/1. На ремонт/1. Обложка дела.docx",
                f"clients/{str(data['client_id'])}/Документы/Обложка дела.docx"
            )
        else:
            replace_words_in_word(
                ["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}", "{{ NКлиента }}", "{{ ФИО }}",
                "{{ Телефон }}", "{{ Город }}"],
                [str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), 
                str(data.get("marks",'')), str(data.get("car_number",'')),
                str(data.get('year','')), str(data.get('client_id','')), str(data.get("fio",'')), 
                str(data.get("number",'')), str(data.get("city",''))],
                "Шаблоны/2. Яма/Яма 1. Обложка дела.docx",
                f"clients/{str(data['client_id'])}/Документы/Обложка дела.docx"
            )
        
        # ФОРМИРУЕМ ЮР ДОГОВОР
        replace_words_in_word(
            ["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", "{{ Дата }}", "{{ ФИО }}", 
            "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
            "{{ Паспорт_когда }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Дата_ДТП }}", 
            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
            [str(data.get('year','')), str(data.get("client_id",'')), str(data.get("city",'')), 
            str(datetime.now().strftime("%d.%m.%Y")), str(data.get("fio",'')), 
            str(data.get("date_of_birth",'')), str(data.get("seria_pasport",'')), 
            str(data.get("number_pasport",'')), str(data.get("where_pasport",'')),
            str(data.get("when_pasport",'')), str(data.get("index_postal",'')), 
            str(data.get("address",'')), str(data.get("date_dtp",'')), 
            str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), 
            str(data.get('fio_k',''))],
            "Шаблоны/1. ДТП/1. На ремонт/2. Юр договор.docx",
            f"clients/{str(data['client_id'])}/Документы/Юр договор.docx")
        
        # Отправляем документ
        try:
            with open(f"clients/{str(data['client_id'])}/Документы/Юр договор.docx", 'rb') as document_file:
                msg2 = bot.send_document(
                    user_id, 
                    document_file,
                    caption="📄 Юридический договор"
                )
        except Exception as e:
            print(f"Ошибка отправки документа: {e}")
            bot.send_message(user_id, "❌ Ошибка при формировании документа")
            return
        if TEST == 'No':
            try:
                bot.send_message(
                    chat_id=ID_CHAT,
                    message_thread_id=ID_TOPIC_CLIENT,
                    text=f"Клиент {data['client_id']} {data['fio']} добавлен"
                )
            except Exception as e:
                print(f"Ошибка при отправке сообщения в тему: {e}")
        data.update({'message_id': msg2.message_id})
        user_temp_data[user_id] = data
        # Запрашиваем фото лицевой стороны ВУ
        msg = bot.send_message(
            chat_id=call.message.chat.id,
            text="📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
            parse_mode='HTML',
            reply_markup = None
        )
        bot.register_next_step_handler(msg, admin_driver_license_front, data, msg.message_id)

    def admin_driver_license_front(message, data, user_message_id):
        """Обработка фото лицевой стороны ВУ"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, data['message_id'])
            del data['message_id']
    
        except:
            pass
        user_id = message.from_user.id
        user_temp_data[user_id] = data
        if not message.photo:
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
                parse_mode='HTML',
                reply_markup=None  
            )
            bot.register_next_step_handler(msg, admin_driver_license_front, data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
                  
            keyboard = create_back_keyboard("back_to_admin_driver_license_front")
            # Запрашиваем обратную сторону
            msg = bot.send_message(
                message.chat.id,
                "✅ Фотография лицевой стороны принята.\n\n📸 Теперь отправьте фотографию обратной стороны водительского удостоверения.",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_driver_license_back, data, msg.message_id, downloaded_file)
            
        except Exception as e:
            print(f"Ошибка при обработке фото ВУ (лицевая сторона): {e}")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, admin_driver_license_front, data, msg.message_id)
            
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_driver_license_front")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_driver_license_front(call):
        """Обработка возврата к адресу ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        # Запрашиваем фото лицевой стороны ВУ
        msg = bot.send_message(
            chat_id=call.message.chat.id,
            text="📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
            parse_mode='HTML',
            reply_markup = None
        )
        bot.register_next_step_handler(msg, admin_driver_license_front, data, msg.message_id)

    def admin_driver_license_back(message, data, user_message_id, front_photo):
        """Обработка фото обратной стороны ВУ и создание PDF"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            keyboard = create_back_keyboard("back_to_admin_driver_license_front")  # ✅ Добавлена кнопка
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>обратной стороны</b> водительского удостоверения:",
                parse_mode='HTML',
                reply_markup=keyboard  # ✅ Добавлена клавиатура
            )
            bot.register_next_step_handler(msg, admin_driver_license_back, data, msg.message_id, front_photo)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/Водительское_удостоверение.pdf"
            create_pdf_from_images_admin(front_photo, downloaded_file, pdf_path)
            
            # Переходим к выбору документа ТС
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="admin_STS")
            btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="admin_PTS")
            btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_driver_license_front")
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
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
            bot.register_next_step_handler(msg, admin_driver_license_back, data, msg.message_id, front_photo)

    def create_pdf_from_images_admin(image1_bytes, image2_bytes, output_path):
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
    
    @bot.callback_query_handler(func=lambda call: call.data in ["admin_STS", "admin_PTS"])
    @prevent_double_click(timeout=3.0)
    def callback_docs(call):
        user_id = call.from_user.id
        
        data = user_temp_data[user_id]
        
        if call.data == "admin_STS":
            data.update({"docs": "СТС"})
            data['dkp'] = '-'
            user_temp_data[user_id] = data
            keyboard = create_back_keyboard("back_to_admin_doc_choice")
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📸 Отправьте фото <b>лицевой стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup=keyboard 
            )
            
            bot.register_next_step_handler(msg, admin_sts_front, data, msg.message_id)

        elif call.data == "admin_PTS":
            data['docs'] = "ПТС"
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Управляю по ДКП", callback_data="admin_DKP")
            btn2 = types.InlineKeyboardButton("Продолжить", callback_data="admin_DKP_next")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_doc_choice")
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn_back)
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите из следующих вариантов",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_doc_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_doc_choice(call):
        """Возврат к выбору документа ТС"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="admin_STS")
        btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="admin_PTS")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_driver_license_front")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn_back)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Водительское удостоверение успешно сохранено!\nВыберите документ о регистрации ТС:",
            reply_markup=keyboard
        )

    def admin_sts_front(message, data, user_message_id):
        """Обработка фото лицевой стороны СТС"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        user_id = message.from_user.id
        if not message.photo:
            keyboard = create_back_keyboard("back_to_admin_doc_choice")  
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>лицевой стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_sts_front, data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            data = user_temp_data[user_id]
            keyboard = create_back_keyboard("admin_STS")
            # Запрашиваем обратную сторону
            msg = bot.send_message(
                message.chat.id,
                "✅ Лицевая сторона получена!\n\n📸 Теперь отправьте фото <b>обратной стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_sts_back, data, msg.message_id, downloaded_file)
            
        except Exception as e:
            print(f"Ошибка при обработке фото СТС (лицевая сторона): {e}")
            keyboard = create_back_keyboard("back_to_admin_doc_choice")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_sts_front, data, msg.message_id)


    def admin_sts_back(message, data, user_message_id, front_photo):
        """Обработка фото обратной стороны СТС и создание PDF"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            keyboard = create_back_keyboard("admin_STS")
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>обратной стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_sts_back, data, msg.message_id, front_photo)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/СТС.pdf"
            create_pdf_from_images_admin(front_photo, downloaded_file, pdf_path)
            
            if data.get("who_dtp", '') == 'Евро-протокол':
                protocol_text = "Евро-протокола"
            else:
                protocol_text = "протокола ГИБДД"
            user_temp_data[user_id]['protocol_photos'] = []
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_admin_{data['user_id']}")

            if data.get("docs", '') == 'СТС':
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_STS")
            elif data.get('dkp', '') != '-':
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP")
            else:
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP_next")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                    chat_id=message.chat.id,
                    text=f"📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:",
                    reply_markup=keyboard
                )
            

            
        except Exception as e:
            print(f"Ошибка при создании PDF СТС: {e}")
            keyboard = create_back_keyboard("admin_STS")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, admin_sts_back, data, msg.message_id, front_photo)

    @bot.callback_query_handler(func=lambda call: call.data in ["admin_DKP", "admin_DKP_next"])
    @prevent_double_click(timeout=3.0)
    def callback_admin_dkp(call):
        """Обработка выбора ДКП"""
        user_id = call.from_user.id
        data = user_temp_data[user_id]

        if call.data == "admin_DKP":
            data['dkp'] = 'Договор ДКП'
        else:
            data['dkp'] = '-'
        user_temp_data[user_id] = data
        user_temp_data[user_id]['pts_photos'] = []
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_pts_upload_admin_{user_id}")
        keyboard.add(btn_finish)
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"admin_PTS"))
        bot.send_message(
            call.message.chat.id,
            "📸 Отправьте фото страниц ПТС\n\n"
            "Можно отправлять по одной фотографии или несколько сразу.\n"
            "Когда загрузите все страницы, нажмите кнопку ниже:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_pts_upload_admin_'))
    @prevent_double_click(timeout=3.0)
    def finish_pts_upload_callback(call):
        """Завершение загрузки ПТС"""
        user_id = call.from_user.id
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if user_id not in user_temp_data or 'pts_photos' not in user_temp_data[user_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[user_id]['pts_photos']

            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_pts_upload_admin_{user_id}")
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_PTS") 
                keyboard.add(btn_finish)
                keyboard.add(btn_back)
                
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Отправьте фото страниц ПТС:",
                    reply_markup=keyboard
                )
                return
            
            
            try:
                del user_temp_data[user_id]['pts_photos']
                if 'pts_timer' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['pts_timer']
            except:
                print("Ошибка удаления pts_photos")
            data = user_temp_data[user_id]
            
            

            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/ПТС.pdf"
            create_pdf_from_images_admin2(photos, pdf_path)
            
            msg = bot.send_message(call.message.chat.id, f"✅ ПТС успешно сохранен! (Страниц: {len(photos)})")
            print(data)
            print(data.get('dkp'))
            # Проверяем, нужно ли загружать ДКП
            if data.get('dkp') == 'Договор ДКП':
                start_dkp_upload_admin(call.message.chat.id, user_id, data, msg.message_id)
            else:
                finish_document_upload_admin(call.message.chat.id, user_id, data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при сохранении ПТС: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении документа.")
    
    def start_dkp_upload_admin(chat_id, user_id, data, user_message_id):
        """Начало загрузки ДКП"""
        # Инициализируем хранилище для фото ДКП
        try:
            bot.delete_message(chat_id, user_message_id)
        except:
            pass
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['dkp_photos'] = []
        user_temp_data[user_id] = data

        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dkp_upload_admin_{user_id}")
        btn_finish2 = types.InlineKeyboardButton("◀️ Назад", callback_data=f"admin_DKP")
        keyboard.add(btn_finish)
        keyboard.add(btn_finish2)
        bot.send_message(
            chat_id,
            "📸 Отправьте фото страниц Договора купли-продажи\n\n"
            "Можно отправлять по одной фотографии или несколько сразу.\n"
            "Когда загрузите все страницы, нажмите кнопку ниже:",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_dkp_upload_admin_'))
    @prevent_double_click(timeout=3.0)
    def finish_dkp_upload_callback(call):
        """Завершение загрузки ДКП"""
        user_id = call.from_user.id
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if user_id not in user_temp_data or 'dkp_photos' not in user_temp_data[user_id]:
                keyboard.add(btn_finish)
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.", rely_markup = keyboard)
                return
            
            photos = user_temp_data[user_id]['dkp_photos']

            if len(photos) == 0:
                
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dkp_upload_admin_{user_id}")
                btn_finish2 = types.InlineKeyboardButton("◀️ Назад", callback_data=f"admin_DKP")
                keyboard.add(btn_finish)
                keyboard.add(btn_finish2)
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Отправьте фото страниц Договора купли-продажи:",
                    reply_markup=keyboard
                )
                return
            
            try:
                del user_temp_data[user_id]['dkp_photos']
                if 'dkp_timer' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['dkp_timer']
            except:
                print("Ошибка удаления dkp_photos")

            data = user_temp_data[user_id]

            
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/ДКП.pdf"
            create_pdf_from_images_admin2(photos, pdf_path)
            
            msg = bot.send_message(call.message.chat.id, f"✅ Договор купли-продажи успешно сохранен! (Страниц: {len(photos)})")
            
            # Завершаем загрузку документов
            finish_document_upload_admin(call.message.chat.id, user_id, data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при сохранении ДКП: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении документа.")

    def finish_document_upload_admin(chat_id, user_id, data, user_message_id):
        """Завершение загрузки всех документов и переход к выбору страховой"""
        try:
            bot.delete_message(chat_id, user_message_id)
        except:
            pass
        user_temp_data[user_id] = data

        if data.get("who_dtp", '') == 'Евро-протокол':
            protocol_text = "Евро-протокола"
        else:
            protocol_text = "протокола ГИБДД"
        user_temp_data[user_id]['protocol_photos'] = []
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_admin_{data['user_id']}")

        if data.get("docs", '') == 'СТС':
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_STS")
        elif data.get('dkp', '') != '-':
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP")
        else:
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP_next")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        msg = bot.send_message(
                chat_id=chat_id,
                text=f"📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:",
                reply_markup=keyboard
            )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_protocol_photos_upload_admin_'))
    @prevent_double_click(timeout=3.0)
    def finish_protocol_photos_upload_callback(call):
        """Завершение загрузки фото протокола (ГИБДД или Евро-протокол)"""
        user_id = call.from_user.id
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if user_id not in user_temp_data or 'protocol_photos' not in user_temp_data[user_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[user_id]['protocol_photos']
            data = user_temp_data[user_id]
            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_admin_{user_id}")
                if data.get("docs", '') == 'СТС':
                    btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_STS")
                elif data.get('dkp', '') != '-':
                    btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP")
                else:
                    btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP_next")

                keyboard.add(btn_finish)
                keyboard.add(btn_back)
                
                protocol_type = "Евро-протокола" if data.get("who_dtp", '') == 'Евро-протокол' else "протокола ГИБДД"
                
                bot.send_message(
                    call.message.chat.id,
                    f"❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Прикрепите фото {protocol_type}:",
                    reply_markup=keyboard
                )
                return
            
            try:
                del user_temp_data[user_id]['protocol_photos']
                if 'protocol_timer' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['protocol_timer']
            except:
                print("Ошибка удаления protocol_photos")
            data = user_temp_data[user_id]

            
            
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
            create_pdf_from_images_admin2(photos, pdf_path)
            
            
            bot.send_message(call.message.chat.id, success_message)
            
            user_temp_data[user_id]['dtp_photos'] = []
            user_temp_data[user_id] = data

            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_upload_admin_{user_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_requisites_or_protocol")  
            keyboard.add(btn_finish)
            keyboard.add(btn_back)

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

    def create_pdf_from_images_admin2(image_bytes_list, output_path):
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
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_admin_requisites_or_protocol'))
    @prevent_double_click(timeout=3.0)
    def back_to_admin_requisites_or_protocol(call):
        """Загрузки фото протокола (ГИБДД или Евро-протокол)"""
        user_id = call.from_user.id
        try:
            bot.delete_message(user_id, call.message.message_id)
        except:
            pass
        data = user_temp_data[user_id]

        if data.get("who_dtp", '') == 'Евро-протокол':
            protocol_text = "Евро-протокола"
        else:
            protocol_text = "протокола ГИБДД"
        user_temp_data[user_id]['protocol_photos'] = []
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_admin_{data['user_id']}")

        if data.get("docs", '') == 'СТС':
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_STS")
        elif data.get('dkp', '') != '-':
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP")
        else:
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="admin_DKP_next")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        msg = bot.send_message(
                chat_id=user_id,
                text=f"📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:",
                reply_markup=keyboard
            )
        
    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_dtp_photos_upload_admin_'))
    @prevent_double_click(timeout=3.0)
    def finish_dtp_photos_upload_callback(call):
        """Завершение загрузки фото ДТП"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if user_id not in user_temp_data or 'dtp_photos' not in user_temp_data[user_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[user_id]['dtp_photos']

            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_upload_admin_{user_id}")
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_requisites_or_protocol")
                keyboard.add(btn_finish)
                keyboard.add(btn_back)
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Прикрепите фото с ДТП:",
                    reply_markup=keyboard
                )
                return
            
            try:
                del user_temp_data[user_id]['dtp_photos']
                if 'dtp_timer' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['dtp_timer']
            except:
                print("Ошибка удаления dtp_photos")
            data = user_temp_data[user_id]
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF из фото ДТП
            pdf_path = f"{client_dir}/Фото_ДТП.pdf"
            create_pdf_from_images_admin2(photos, pdf_path)
            
            fields_to_remove = [
                'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
                'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
                'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back',
                'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
            ]
            
            for field in fields_to_remove:
                data.pop(field, None)

            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            if user_id in user_temp_data:
                    user_temp_data.pop(user_id, None)
            keyboard = types.InlineKeyboardMarkup()  
            client_id = data['client_id']      
            if data.get('accident','') == 'ДТП':
                if data.get('sobstvenik','') != 'С начала':
                    keyboard.add(types.InlineKeyboardButton("Заполнить заявление в страховую ", callback_data=f"dtp_continue_documents_{client_id}"))
                keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"request_act_payment_{data['client_id']}"))  
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
            
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Выберите из следующих вариантов",
                    reply_markup=keyboard
                )
            elif data.get('accident','') == 'Подал заявление':
                keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"agent_podal_continue_documents_{client_id}"))
                keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"request_act_payment_{data['client_id']}"))  
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
            
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Готовы продолжить заполнение?",
                    reply_markup=keyboard
                )
            elif data.get('accident','') == 'Нет ОСАГО':
                keyboard.add(types.InlineKeyboardButton("📄 Заявление о выдаче из ГИБДД", callback_data=f"agent_net_osago_continue_documents_{client_id}"))
                keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"request_act_payment_{data['client_id']}"))  
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
            
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Готовы продолжить заполнение?",
                    reply_markup=keyboard
                ) 
            else:
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Данные сохранены",
                    reply_markup=keyboard
                )
        except Exception as e:
            print(f"Ошибка при сохранении фото ДТП: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении фото.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('request_act_payment_'))
    @prevent_double_click(timeout=3.0)
    def request_act_payment_callback(call):
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
            if data.get('seria_insurance', '') == '':
                if data.get('accident', '') == 'ДТП' and data.get('sobstvenik', '') != 'С начала':
                    keyboard.add(types.InlineKeyboardButton("▶️ К заявлению в страховую", callback_data=f"dtp_continue_documents2_{data['client_id']}"))
                elif data.get('accident', '') == 'Подал заявление':
                    keyboard.add(types.InlineKeyboardButton("▶️ Продолжить", callback_data=f"agent_podal_continue_documents_{data['client_id']}"))
                elif data.get('accident', '') == 'Нет ОСАГО':
                    keyboard.add(types.InlineKeyboardButton("▶️ К заявлению в ГИБДД", callback_data=f"agent_net_osago_continue_documents_{data['client_id']}")) 
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))   
            with open(f"clients/"+str(data['client_id'])+f"/Документы/{output_filename}", 'rb') as doc:
                bot.send_document(call.message.chat.id, doc, caption="📋 Запрос на выдачу документов", reply_markup = keyboard)
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, "❌ Ошибка: файл не найден")
        
        if data.get('user_id','') != '8572367590':
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

    @bot.callback_query_handler(func=lambda call: call.data.startswith('dtp_continue_documents2_'))
    @prevent_double_click(timeout=3.0)
    def dtp_continue_documents2_callback(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        client_id = int(call.data.split('_')[-1])
        user_id = call.from_user.id
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        contract = get_client_from_db_by_client_id(str(client_id))

        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        try:
            data = json.loads(contract.get('data_json', '{}'))
        except:
            data = contract
        print(data)

        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id] = data
        if data.get('docs','') =='':
            data.update({'docs': 'СТС'})
            data.update({'dkp': '-'})
        try: 
            with open(f"clients/"+str(data['client_id'])+f"/Документы/{data.get('docs', 'СТС')}.pdf", 'rb') as doc:
                msg2 = bot.send_document(call.message.chat.id, doc, caption=f"{data.get('docs', 'СТС')}")
        except FileNotFoundError:
            msg2 = bot.send_message(call.message.chat.id, f"❌ Ошибка: файл {data.get('docs', 'СТС')}.pdf не найден")

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(user_id, data['client_id']))) 
        msg = bot.send_message(
                call.message.chat.id,
                f"Введите серию документа {data.get('docs', 'СТС')}",
                reply_markup=keyboard
            )
        bot.register_next_step_handler(call.message, admin_seria_docs, data, msg.message_id, msg2.message_id)

    def admin_seria_docs(message, data, user_message_id, message_id_docs):
        """Обработка серии документа регистрации ТС"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        data.update({'seria_docs': message.text.strip()})
        data.update({'message_id': message_id_docs})
        user_temp_data[user_id].update(data)
        
        keyboard = create_back_keyboard("back_to_admin_seria_docs")
        msg = bot.send_message(message.chat.id, f"Введите номер документа {data.get('docs', 'СТС')}", reply_markup=keyboard)
        bot.register_next_step_handler(msg, admin_number_docs, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_admin_seria_docs')
    @prevent_double_click(timeout=3.0)
    def back_to_admin_seria_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(user_id, data['client_id']))) 
        msg = bot.send_message(
                call.message.chat.id,
                f"Введите серию документа {data.get('docs', 'СТС')}",
                reply_markup=keyboard
            )
        bot.register_next_step_handler(call.message, admin_seria_docs, data, msg.message_id, data['message_id'])

    def admin_number_docs(message, data, user_message_id):
        """Обработка номера документа регистрации ТС"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        data.update({'number_docs': message.text.strip()})
        user_temp_data[user_id].update(data)
        
        keyboard = create_back_keyboard("back_to_admin_number_docs")
        msg = bot.send_message(message.chat.id, f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
        bot.register_next_step_handler(msg, admin_date_docs, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_admin_number_docs')
    @prevent_double_click(timeout=3.0)
    def back_to_admin_number_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        data = user_temp_data[user_id]

        keyboard = create_back_keyboard("back_to_admin_seria_docs")
        msg = bot.send_message(
                call.message.chat.id,
                f"Введите номер документа {data.get('docs', 'СТС')}",
                reply_markup=keyboard
            )
        bot.register_next_step_handler(call.message, admin_number_docs, data, msg.message_id)

    def admin_date_docs(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id

        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        date_text = message.text.strip()
        
        try:
            datetime.strptime(date_text, "%d.%m.%Y")           
            
            data.update({'data_docs': date_text})
            try:
                bot.delete_message(message.chat.id, data['message_id'])
                del data['message_id']
            except:
                pass
            
            user_temp_data[user_id] = data
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"admin_health_yes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"admin_health_no"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_admin_date_docs"))
            bot.send_message(
                message.from_user.id, 
                "Имеется ли причинения вреда здоровья в следствии ДТП?", 
                reply_markup=keyboard
            )
            
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_docs"))
            msg = bot.send_message(
                message.chat.id, 
                f"❌ Неправильный формат ввода!\nВведите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_date_docs, data, msg.message_id)
            return
        
    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_admin_date_docs')
    @prevent_double_click(timeout=3.0)
    def back_to_admin_date_docs(call):
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        data = user_temp_data[user_id]
        try: 
            with open(f"clients/"+str(data['client_id'])+f"/Документы/{data.get('docs', 'СТС')}.pdf", 'rb') as doc:
                msg2 = bot.send_document(call.message.chat.id, doc, caption=f"{data.get('docs', 'СТС')}")
        except FileNotFoundError:
            msg2 = bot.send_message(call.message.chat.id, "❌ Ошибка: файл не найден")
        data.update({'message_id': msg2.message_id})
        keyboard = create_back_keyboard("back_to_admin_number_docs")
        user_temp_data[user_id] = data
        msg = bot.send_message(
                call.message.chat.id,
                f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
        bot.register_next_step_handler(call.message, admin_date_docs, data, msg.message_id)
    
    @bot.callback_query_handler(func=lambda call: call.data in ['admin_health_yes', 'admin_health_no'])
    @prevent_double_click(timeout=3.0)
    def admin_health_callback(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]

        if call.data == 'admin_health_yes':
            if data.get('who_dtp') == "По форме ГИБДД":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"admin_place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"admin_place_dtp"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_health_question"))  
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
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"admin_photo_non_gosuslugi"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_health_question"))
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, admin_number_photo, data, msg.message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"admin_culp_have_osago_yes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"admin_culp_have_osago_no"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_health_question"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Есть ли у пострадавшего ОСАГО?",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ['admin_culp_have_osago_yes', 'admin_culp_have_osago_no'])
    @prevent_double_click(timeout=3.0)
    def admin_culp_have_osago(call):
        user_id = call.from_user.id
        data = user_temp_data[call.from_user.id]
        
        if data.get('who_dtp') == "По форме ГИБДД":
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"admin_place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"admin_place_dtp"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_culp_question"))  # Добавлена кнопка
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
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"admin_photo_non_gosuslugi"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_culp_question"))  # Добавлена кнопка
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_number_photo, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_health_question")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_health_question(call):
        """Возврат к вопросу о наличии вреда здоровью"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"admin_health_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"admin_health_no"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_admin_date_docs"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Имеется ли причинения вреда здоровья в следствии ДТП?",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_culp_question")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_culp_question(call):
        """Возврат к вопросу о наличии ОСАГО"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"admin_culp_have_osago_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"admin_culp_have_osago_no"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_date_docs"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Есть ли у пострадавшего ОСАГО?",
            reply_markup=keyboard
        )

    def admin_number_photo(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['number_photo'] = message.text
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"admin_place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"admin_place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_number_photo"))
        
        bot.send_message(
            message.from_user.id,
            "Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_number_photo")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_number_photo(call):
        """Возврат к вводу номера фотофиксации"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"admin_photo_non_gosuslugi"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_health_question"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, admin_number_photo, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "admin_photo_non_gosuslugi")
    @prevent_double_click(timeout=3.0)
    def handle_admin_photo_non_gosuslugi(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"next_photo_admin"))
        keyboard.add(types.InlineKeyboardButton("Я внесу фотофиксацию", callback_data=f"continue_photo_admin"))  

        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Если нет прикрепления фотофиксации в Госуслуги, то выплата ограничивается размером 100000₽",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ["next_photo_admin", "continue_photo_admin"])
    @prevent_double_click(timeout=3.0)
    def handle_admin_next_photo_gosuslugi(call):
        data = user_temp_data[call.from_user.id]
        if call.data == "next_photo_admin":
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"admin_place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"admin_place_dtp"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_health_question"))

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
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"admin_photo_non_gosuslugi"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_health_question"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, admin_number_photo, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["admin_place_home", "admin_place_dtp"])
    @prevent_double_click(timeout=3.0)
    def callback_agent_place(call):
        """Обработка ремонт не более 50км от места ДТП или места жительства"""
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "admin_place_home":
            data['place'] = "Жительства"
        else:
            data['place'] = "ДТП"

        user_temp_data[user_id] = data

        
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"admin_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"admin_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_place"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_place")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_place(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"admin_place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"admin_place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_health_question"))

        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data in ["admin_next_bank", "admin_cancel_bank"])
    @prevent_double_click(timeout=3.0)
    def callback_admin_requisites(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.delete_message(call.message.chat.id, data['message_id'])
        except:
            pass
        if call.data == "admin_next_bank":
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="<b>Заполнение банковских реквизитов</b>",
                    parse_mode='HTML'
                )
            data.update({'message_id': msg.message_id})
            user_temp_data[user_id].update(data)
            keyboard = create_back_keyboard("back_to_admin_requisites_choice")
            msg2 = bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Введите банк получателя клиента",
                    reply_markup = keyboard
                )
            user_message_id = msg2.message_id
            bot.register_next_step_handler(msg, admin_bank, data, user_message_id)

        else:
            data.update({"bank": "-"})
            data.update({"bank_account": "-"})
            data.update({"bank_account_corr": "-"})
            data.update({"BIK": "-"})
            data.update({"INN": "-"})
            if data.get('sobstvenik', '') != 'С начала' and data.get('sobstvenik', '') != 'После заявления в страховую' and data.get('sobstvenik', '') != 'После ответа от страховой':
                data.update({"sobstvenik": "С начала"})
            if data.get('who_dtp', '') != 'Евро-протокол' and data.get('who_dtp', '') != 'По форме ГИБДД':
                data.update({"who_dtp": "По форме ГИБДД"})
            if data.get("ev", '') != 'Нет' and data.get("ev", '') != 'Да':
                data.update({"ev": "Нет"})  
            try:
                del user_temp_data[user_id]
            except:
                pass
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            fields_to_remove = [
                'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
                'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
                'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back', 'message_id', 'message_id2',
                'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
            ]
            
            for field in fields_to_remove:
                data.pop(field, None)

            data['date_ins'] = str(get_next_business_date())
            data['date_ins_pod'] = str(get_next_business_date())
            data['status'] = 'Отправлен запрос в страховую'

            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            
            # Выбираем шаблон в зависимости от эвакуатора    

            if data.get("who_dtp", '') == 'Евро-протокол' and data.get("ev", '') == 'Нет':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", "{{ Фотофиксация }}",
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("number_photo",'')), str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент европротокол.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            elif data.get("who_dtp", '') == 'Евро-протокол' and data.get("ev", '') == 'Да':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", "{{ Фотофиксация }}",
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}", "{{ Адрес_стоянки }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("number_photo",'')), str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",'')), str(data.get("address_park",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент эвакуатор европротокол.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            elif data.get("who_dtp", '') == 'По форме ГИБДД' and data.get("ev", '') == 'Да':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", 
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}", "{{ Адрес_стоянки }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",'')), str(data.get("address_park",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент эвакуатор по форме ГИБДД.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            elif data.get("who_dtp", '') == 'По форме ГИБДД' and data.get("ev", '') == 'Нет':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", 
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент по форме ГИБДД.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            try:
                with open(f"clients/{data['client_id']}/Документы/Заявление в страховую.docx", 'rb') as document_file:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
                    keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"request_act_payment_{data['client_id']}"))
                    bot.send_document(call.from_user.id, document_file, caption ="✅ Заявление в страховую успешно сформировано!", reply_markup=keyboard)   
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, f"Файл не найден")                

            

    def admin_bank(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"bank": message.text})
        user_temp_data[user_id].update(data)
        keyboard = create_back_keyboard("admin_next_bank")  
        message = bot.send_message(message.chat.id, text="Введите счет получателя, 20 цифр", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, admin_bank_account, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_requisites_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_requisites_choice(call):
        """Возврат к вводу банка"""
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"admin_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"admin_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin_place"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )

    def admin_bank_account(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit() and len(message.text) == 20:
            data.update({"bank_account": message.text})
            user_temp_data[user_id].update(data)
            keyboard = create_back_keyboard("back_to_admin_bank_account_corr")
            message = bot.send_message(
                message.chat.id,
                text="Введите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, admin_bank_account_corr, data, user_message_id)
        else:
            keyboard = create_back_keyboard("admin_next_bank")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите счет получателя, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, admin_bank_account, data, user_message_id)

    def admin_bank_account_corr(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit() and len(message.text) == 20:
            data.update({"bank_account_corr": message.text})
            user_temp_data[user_id].update(data)
            
            keyboard = create_back_keyboard("back_to_admin_BIK")
            message = bot.send_message(
                message.chat.id,
                text="Введите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, admin_BIK, data, user_message_id)
        else:
            keyboard = create_back_keyboard("back_to_admin_bank_account_corr")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, admin_bank_account_corr, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_bank_account_corr")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_bank_account_corr(call):
        """Возврат к вводу корр. счета"""
        user_id = call.message.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        keyboard = create_back_keyboard("admin_next_bank")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите счет получателя, 20 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, admin_bank_account, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_INN")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_INN(call):
        """Возврат к вводу корр. счета"""
        user_id = call.message.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        keyboard = create_back_keyboard("back_to_admin_BIK")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите БИК банка, 9 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, admin_BIK, data, msg.message_id)
    def admin_BIK(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit() and len(message.text) == 9:
            data.update({"BIK": message.text})
            user_temp_data[user_id].update(data)
            
            keyboard = create_back_keyboard("back_to_admin_INN")
            message = bot.send_message(
                message.chat.id,
                text="Введите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)
        else:
            keyboard = create_back_keyboard("back_to_admin_BIK")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, БИК должен состоять только из цифр!\nВведите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, admin_BIK, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_BIK")
    @prevent_double_click(timeout=3.0)
    def back_to_admin_BIK(call):
        """Возврат к вводу БИК"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[user_id]
        
        keyboard = create_back_keyboard("back_to_admin_bank_account_corr")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите корреспондентский счет банка, 20 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, admin_bank_account_corr, data, msg.message_id)
    def INN(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, data['message_id'])
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
            del data['message_id']
        except:
            pass
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        if message.text.isdigit() and len(message.text) == 10:
            data.update({"INN": message.text})
            try:
                del user_temp_data[user_id]
            except:
                pass

            fields_to_remove = [
                'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
                'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
                'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back', 'message_id', 'message_id2',
                'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
            ]
            
            for field in fields_to_remove:
                data.pop(field, None)

            # ПРОДОЛЖАЕМ с логикой формирования заявления
           
            data['date_ins'] = str(get_next_business_date())
            data['date_ins_pod'] = str(get_next_business_date())
            data['status'] = 'Отправлен запрос в страховую'
            if data.get('sobstvenik', '') != 'С начала' and data.get('sobstvenik', '') != 'После заявления в страховую' and data.get('sobstvenik', '') != 'После ответа от страховой':
                data.update({"sobstvenik": "С начала"})
            if data.get('who_dtp', '') != 'Евро-протокол' and data.get('who_dtp', '') != 'По форме ГИБДД':
                data.update({"who_dtp": "По форме ГИБДД"})
            if data.get("ev", '') != 'Нет' and data.get("ev", '') != 'Да':
                data.update({"ev": "Нет"})  
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            
            # Выбираем шаблон в зависимости от эвакуатора    

            if data.get("who_dtp", '') == 'Евро-протокол' and data.get("ev", '') == 'Нет':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", "{{ Фотофиксация }}",
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("number_photo",'')), str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент европротокол.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            elif data.get("who_dtp", '') == 'Евро-протокол' and data.get("ev", '') == 'Да':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", "{{ Фотофиксация }}",
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}", "{{ Адрес_стоянки }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("number_photo",'')), str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",'')), str(data.get("address_park",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент эвакуатор европротокол.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            elif data.get("who_dtp", '') == 'По форме ГИБДД' and data.get("ev", '') == 'Да':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", 
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}", "{{ Адрес_стоянки }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",'')), str(data.get("address_park",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент эвакуатор по форме ГИБДД.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            elif data.get("who_dtp", '') == 'По форме ГИБДД' and data.get("ev", '') == 'Нет':
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                    "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                    "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                    "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                    "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                    "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                    "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Место_Ж_Д }}", 
                    "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                    [str(data.get("insurance",'')), str(data.get("fio",'')), str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),
                    str(data.get("date_of_birth",'')), str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                    str(data.get("city_birth",'')), str(data.get("index_postal",'')), str(data.get("address",'')), str(data.get("docs",'')), 
                    str(data.get("seria_docs",'')), str(data.get("number_docs",'')), str(data.get("data_docs",'')), 
                    str(data.get("dkp",'')), str(data.get("marks",'')), str(data.get("year_auto",'')),
                    str(data.get("car_number",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')),
                    str(data.get("address_dtp",'')), str(data.get("fio_culp",'')), str(data.get("marks_culp",'')), str(data.get("seria_insurance",'')),
                    str(data.get("number_insurance",'')), str(data.get("date_insurance",'')), str(data.get("city",'')), str(data.get("place",'')),
                    str(data.get("bank",'')), str(data.get("bank_account",'')), str(data.get("bank_account_corr",'')),
                    str(data.get("BIK",'')), str(data.get("INN",'')), str(data.get("date_ins",''))],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент по форме ГИБДД.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            try:
                with open(f"clients/{data['client_id']}/Документы/Заявление в страховую.docx", 'rb') as document_file:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id']))) 
                    bot.send_document(message.from_user.id, document_file, caption ="✅ Заявление в страховую успешно сформировано!", reply_markup=keyboard)   
            except FileNotFoundError:
                bot.send_message(message.chat.id, f"Файл не найден")                


        else:
            keyboard = create_back_keyboard("back_to_admin_INN")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)

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