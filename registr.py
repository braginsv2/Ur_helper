from telebot import types
import re
from io import BytesIO
import os
import config
from database import (
    DatabaseManager, 
    get_admin_from_db_by_user_id,
    search_clients_by_fio_in_db
)
import threading
import time
from functools import wraps
from scan_pasport import process_passport_image
from config import GIGACHAT_TOKEN
# Словарь для отслеживания активных обработок
active_callbacks = {}
callback_lock = threading.Lock()
db = DatabaseManager()
active_handlers = {}
handler_lock = threading.Lock()

def setup_registration_handlers(bot, user_temp_data):
    """Регистрация всех обработчиков регистрации"""
    def clear_step_handler(bot, chat_id):
        """Отменяет ожидание ввода для пользователя"""
        with handler_lock:
            if chat_id in active_handlers:
                try:
                    bot.clear_step_handler_by_chat_id(chat_id)
                except:
                    pass
                del active_handlers[chat_id]
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
    @bot.callback_query_handler(func=lambda call: call.data == "process_invited_client")
    @prevent_double_click(timeout=3.0)
    def process_invited_client_consent(call):
        """Показ согласия приглашенному клиенту"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        inviter_fio = data.get('inviter_fio', 'агент')
        
        consent_text = (
            f"Вас пригласил {inviter_fio}\n\n"
            "Моя задача — собрать ваши личные данные для передачи команде юристов.\n\n"
            "Сейчас Вам поступит предложение подписать «Согласие на обработку персональных данных». Ознакомьтесь с документом и подтвердите его."
        )
        
        keyboard = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("✅ Подтвердить", callback_data="consent_invited_yes")
        btn_no = types.InlineKeyboardButton("❌ Отклонить", callback_data="consent_invited_no")
        keyboard.add(btn_yes, btn_no)
        
        try:
            with open("Согласие на обработку персональных данных.pdf", "rb") as pdf_file:
                bot.send_document(call.message.chat.id, pdf_file, caption=consent_text, reply_markup=keyboard)
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, consent_text + "\n\n⚠️ Файл соглашения не найден", reply_markup=keyboard)
    # ========== ОБРАБОТКА ПРИГЛАШЕННЫХ КЛИЕНТОВ ==========

    @bot.callback_query_handler(func=lambda call: call.data in ["consent_invited_yes", "consent_invited_no"])
    @prevent_double_click(timeout=3.0)
    def handle_invited_consent(call):
        """Обработка согласия приглашенного клиента"""
        user_id = call.from_user.id
        
        if call.data == "consent_invited_no":
            # Отказ от согласия
            if user_id in user_temp_data:
                del user_temp_data[user_id]
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ Вы отказались от обработки персональных данных."
            )
            
            keyboard = types.InlineKeyboardMarkup()
            btn_register = types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data="btn_registratsia")
            keyboard.add(btn_register)
            
            bot.send_message(
                call.message.chat.id,
                "Для работы с ботом необходимо зарегистрироваться.",
                reply_markup=keyboard
            )
            return
        
        # Согласие получено
        data = user_temp_data.get(user_id, {})
        inviter_type = data.get('invited_by_type')

        # ВАЖНО: Проверяем, что все данные есть
        print(f"DEBUG CONSENT: Данные перед заполнением паспортных:")
        print(f"  - ФИО: {data.get('fio')}")
        print(f"  - Телефон: {data.get('number')}")
        print(f"  - Город: {data.get('city_admin')}")
        print(f"  - Inviter ID: {data.get('invited_by_user_id')}")
        print(f"  - Inviter type: {inviter_type}")

        # Если телефона или города нет, пытаемся достать из pending_invites
        if not data.get('number') or not data.get('city_admin'):
            client_fio = data.get('fio', '')
            inviter_id = data.get('invited_by_user_id', '')
            pending_key = f"{inviter_id}_{client_fio.split()[0]}"
            pending_data = user_temp_data.get('pending_invites', {}).get(pending_key)
            
            if pending_data:
                if not data.get('number'):
                    data['number'] = pending_data.get('phone', '')
                if not data.get('city_admin'):
                    data['city_admin'] = pending_data.get('city', '')
                
                print(f"DEBUG CONSENT: Данные взяты из pending_invites:")
                print(f"  - Телефон: {data.get('number')}")
                print(f"  - Город: {data.get('city_admin')}")

        # Определяем admin_value
        if inviter_type == 'agent' or inviter_type == 'admin':
            data['admin_value'] = 'Клиент_агент'
        else:
            data['admin_value'] = 'Клиент'

        data['user_id'] = str(user_id)

        if data.get('invited_by_user_id', '') != data['user_id']:
            user_id = int(data.get('invited_by_user_id', ''))
        # Сохраняем данные во временное хранилище
        user_temp_data[user_id] = data

        # Удаляем сообщение с согласием
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        # Отправляем сообщение о начале заполнения паспортных данных
        passport_info_msg = bot.send_message(
            int(user_id),
            "🤖 <b>Заполните паспортные данные</b>",
            parse_mode='HTML'
        )

        # Сохраняем ID этого сообщения
        if passport_info_msg and hasattr(passport_info_msg, 'message_id'):
            data['passport_info_message_id'] = passport_info_msg.message_id
            user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        # Запрашиваем серию паспорта
        msg = bot.send_message(
            user_id,
            "🤖 Прикрепите фото основного разворота паспорта (2-3 стр):",
            reply_markup = keyboard
        )
        active_handlers[msg.chat.id] = 'waiting_invited_passport_photo_2_3'
        bot.register_next_step_handler(msg, process_invited_client_passport_photo_2_3, data, msg.message_id)

    def process_invited_client_passport_series(message, data, prev_message_id):
        """Обработка серии паспорта для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id) 
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        series = message.text.strip()
        
        if not series.isdigit() or len(series) != 4:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Серия паспорта должна содержать 4 цифры. Попробуйте снова:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_invited_passport_series'
            bot.register_next_step_handler(msg, process_invited_client_passport_series, data, msg.message_id)
            return
        
        data['seria_pasport'] = series
        user_temp_data[message.from_user.id].update(data)
        if data['number_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите номер паспорта (6 цифр):"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_number, data, msg.message_id)

        elif data['where_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите, кем выдан паспорт:"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_issued_by, data, msg.message_id)
        elif data['when_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату выдачи паспорта (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_date, data, msg.message_id)
        elif data['date_of_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату рождения (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
        elif data['city_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите город рождения:"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "Введите адрес регистрации по паспорту:"
            )

            bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_consent")
    @prevent_double_click(timeout=3.0)
    def back_invited_consent_handler(call):
        """Возврат к согласию приглашенного клиента"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        # Удаляем сообщение "Заполните паспортные данные"
        if 'passport_info_message_id' in data:
            try:
                bot.delete_message(call.message.chat.id, data['passport_info_message_id'])
                del data['passport_info_message_id']
            except:
                pass
        # Возвращаемся к показу согласия
        process_invited_client_consent(call)

    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_passport_series")
    @prevent_double_click(timeout=3.0)
    def back_invited_passport_series_handler(call):
        """Возврат к вводу серии паспорта для приглашенного"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию паспорта (4 цифры):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_invited_passport_series'
        bot.register_next_step_handler(message, process_invited_client_passport_series, data, message.message_id)

    def process_invited_client_passport_number(message, data, prev_message_id):
        """Обработка номера паспорта для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)  # ДОБАВИТЬ
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        number = message.text.strip()
        
        if not number.isdigit() or len(number) != 6:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_passport_series"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Номер паспорта должен содержать 6 цифр. Попробуйте снова:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_invited_passport_number'
            bot.register_next_step_handler(msg, process_invited_client_passport_number, data, msg.message_id)
            return
        
        data['number_pasport'] = number
        user_temp_data[message.from_user.id].update(data)
        
        if data['where_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите, кем выдан паспорт:"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_issued_by, data, msg.message_id)
        elif data['when_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату выдачи паспорта (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_date, data, msg.message_id)
        elif data['date_of_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату рождения (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
        elif data['city_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите город рождения:"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "Введите адрес регистрации по паспорту:"
            )

            bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_passport_number")
    @prevent_double_click(timeout=3.0)
    def back_invited_passport_number_handler(call):
        """Возврат к вводу номера паспорта для приглашенного"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_passport_series"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер паспорта (6 цифр):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_invited_passport_number'
        bot.register_next_step_handler(message, process_invited_client_passport_number, data, message.message_id)

    def process_invited_client_passport_issued_by(message, data, prev_message_id):
        """Обработка поля 'кем выдан' для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)  # ДОБАВИТЬ
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['where_pasport'] = message.text.strip()
        user_temp_data[message.from_user.id].update(data)

        if data['when_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату выдачи паспорта (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_date, data, msg.message_id)
        elif data['date_of_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату рождения (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
        elif data['city_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите город рождения:"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "Введите адрес регистрации по паспорту:"
            )

            bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)


    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_passport_issued")
    @prevent_double_click(timeout=3.0)
    def back_invited_passport_issued_handler(call):
        """Возврат к вводу 'кем выдан' для приглашенного"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_passport_number"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите, кем выдан паспорт:",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_invited_passport_issued'
        bot.register_next_step_handler(message, process_invited_client_passport_issued_by, data, message.message_id)

    def process_invited_client_passport_date(message, data, prev_message_id):
        """Обработка даты выдачи паспорта для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id) 
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        date_text = message.text.strip()
        
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_passport_issued"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат даты. Введите в формате ДД.ММ.ГГГГ:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_invited_passport_date'
            bot.register_next_step_handler(msg, process_invited_client_passport_date, data, msg.message_id)
            return
        
        data['when_pasport'] = date_text
        user_temp_data[message.from_user.id].update(data)
        if data['date_of_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату рождения (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
        elif data['city_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите город рождения:"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "Введите адрес регистрации по паспорту:"
            )

            bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)


    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_passport_date")
    @prevent_double_click(timeout=3.0)
    def back_invited_passport_date_handler(call):
        """Возврат к вводу даты выдачи паспорта для приглашенного"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_passport_issued"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату выдачи паспорта (ДД.ММ.ГГГГ):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_invited_passport_date'
        bot.register_next_step_handler(message, process_invited_client_passport_date, data, message.message_id)

    def process_invited_client_birth_date(message, data, prev_message_id):
        """Обработка даты рождения для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        date_text = message.text.strip()
        
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_passport_date"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат даты. Введите в формате ДД.ММ.ГГГГ:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_invited_birth_date'
            bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
            return
        
        data['date_of_birth'] = date_text
        user_temp_data[message.from_user.id].update(data)
        if data['city_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите город рождения:"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "Введите адрес регистрации по паспорту:"
            )

            bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)


    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_birth_date")
    @prevent_double_click(timeout=3.0)
    def back_invited_birth_date_handler(call):
        """Возврат к вводу даты рождения для приглашенного"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_passport_date"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату рождения (ДД.ММ.ГГГГ):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_invited_birth_date'
        bot.register_next_step_handler(message, process_invited_client_birth_date, data, message.message_id)

    def process_invited_client_birth_city(message, data, prev_message_id):
        """Обработка города рождения для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['city_birth'] = message.text.strip()
        user_temp_data[message.from_user.id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_birth_city"))
        msg = bot.send_message(message.chat.id, "Введите адрес регистрации по паспорту:", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_invited_address'
        bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_birth_city")
    @prevent_double_click(timeout=3.0)
    def back_invited_birth_city_handler(call):
        """Возврат к вводу города рождения для приглашенного"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_birth_date"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите город рождения:",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_invited_birth_city'
        bot.register_next_step_handler(message, process_invited_client_birth_city, data, message.message_id)

    def process_invited_client_address(message, data, prev_message_id):
        """Обработка адреса прописки для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['address'] = message.text.strip()
        user_temp_data[message.from_user.id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_address"))
        msg = bot.send_message(message.chat.id, "Введите почтовый индекс:", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_invited_postal_index'
        bot.register_next_step_handler(msg, process_invited_client_postal_index, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_invited_address")
    @prevent_double_click(timeout=3.0)
    def back_invited_address_handler(call):
        """Возврат к вводу адреса для приглашенного"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_birth_city"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес регистрации по паспорту:",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_invited_address'
        bot.register_next_step_handler(message, process_invited_client_address, data, message.message_id)

    def process_invited_client_postal_index(message, data, prev_message_id):
        """Обработка почтового индекса для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        index = message.text.strip()
        
        if not index.isdigit() or len(index) != 6:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_invited_address"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Почтовый индекс должен содержать 6 цифр. Попробуйте снова:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_invited_postal_index'
            bot.register_next_step_handler(msg, process_invited_client_postal_index, data, msg.message_id)
            return
        
        data['index_postal'] = index
        user_temp_data[message.from_user.id].update(data)
        
        show_registration_summary(bot, message.chat.id, data)


    def process_invited_client_passport_photo_2_3(message, data, message_id):
        """Обработка фото 2-3 страницы паспорта для приглашенного клиента"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)

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
                
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Неподдерживаемый формат файла. Отправьте фото или файл в формате JPG, PNG, PDF:\n\n"
                    "Прикрепите фото основного разворота паспорта (2-3 стр)",
                    reply_markup = keyboard
                )
                bot.register_next_step_handler(msg, process_invited_client_passport_photo_2_3, data, msg.message_id)
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
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, message.message_id)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Пожалуйста, отправьте фото или файл. Прикрепите фото основного разворота паспорта (2-3 стр):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_invited_client_passport_photo_2_3, data, msg.message_id)
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
            
            data['passport_photo_2_3'] = file_path
            user_temp_data[message.from_user.id] = data
            
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, message.message_id)
            
            msg = bot.send_message(
                message.chat.id, 
                "✅ Файл принят!\n\n📎 Теперь прикрепите фотографию страницы паспорта с регистрацией (разворот страниц 4–5 или 6–7)."
            )
            bot.register_next_step_handler(msg, process_invited_client_passport_photo_4_5, data, msg.message_id)
            
        except Exception as e:
            print(f"❌ Ошибка при обработке файла: {e}")
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            msg = bot.send_message(
                message.chat.id, 
                "❌ Ошибка при загрузке файла. Попробуйте еще раз:\n\n"
                "Прикрепите фото основного разворота паспорта (2-3 стр):",
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_invited_client_passport_photo_2_3, data, msg.message_id)


    def process_invited_client_passport_photo_4_5(message, data, message_id):
        """Обработка фото 4-5 страницы паспорта для приглашенного клиента - ФИНАЛ"""
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
                
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Неподдерживаемый формат файла. Отправьте фото или файл в формате JPG, PNG, PDF:\n\n"
                    "Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):"
                )
                bot.register_next_step_handler(msg, process_invited_client_passport_photo_4_5, data, msg.message_id)
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
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, message.message_id)
            msg = bot.send_message(
                message.chat.id, 
                "❌ Пожалуйста, отправьте фото или файл. Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):"
            )
            bot.register_next_step_handler(msg, process_invited_client_passport_photo_4_5, data, msg.message_id)
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
            
            data['passport_photo_4_5'] = file_path
            user_temp_data[message.from_user.id] = data
            
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
            print(data['passport_photo_2_3'])
            data_pasport = process_passport_image(data['passport_photo_2_3'], GIGACHAT_TOKEN)

            data.update({'seria_pasport': data_pasport['seria_pasport']})
            data.update({'number_pasport': data_pasport['number_pasport']})
            data.update({'where_pasport': data_pasport['where_pasport']})
            data.update({'when_pasport': data_pasport['when_pasport']})
            data.update({'date_of_birth': data_pasport['date_of_birth']})
            data.update({'city_birth': data_pasport['city_birth']})
            print(data)
            if data['seria_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите серию паспорта (4 цифры):"
                )

                bot.register_next_step_handler(message, process_invited_client_passport_series, data, msg.message_id)
            elif data['number_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите номер паспорта (6 цифр):"
                )

                bot.register_next_step_handler(msg, process_invited_client_passport_number, data, msg.message_id)

            elif data['where_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите, кем выдан паспорт:"
                )

                bot.register_next_step_handler(msg, process_invited_client_passport_issued_by, data, msg.message_id)
            elif data['when_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите дату выдачи паспорта (ДД.ММ.ГГГГ):"
                )

                bot.register_next_step_handler(msg, process_invited_client_passport_date, data, msg.message_id)
            elif data['date_of_birth'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите дату рождения (ДД.ММ.ГГГГ):"
                )

                bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
            elif data['city_birth'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите город рождения:"
                )

                bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
            else:
                msg = bot.send_message(
                    message.chat.id,
                    "Введите адрес регистрации по паспорту:"
                )

                bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)
            # # ТЕПЕРЬ СОХРАНЯЕМ В БД И ОТПРАВЛЯЕМ НА ПОДТВЕРЖДЕНИЕ
            # user_id = data['user_id']
            # inviter_type = data.get('invited_by_type')
            
            # # Сохраняем в БД
            # try:
            #     db.save_admin(data)
                
            #     # Сохраняем связь клиент-агент если приглашающий был агентом
            #     if inviter_type == 'agent':
            #         with db.get_connection() as conn:
            #             with conn.cursor() as cursor:
            #                 cursor.execute("""
            #                     INSERT INTO client_agent_relationships (client_user_id, agent_id)
            #                     VALUES (%s, %s)
            #                     ON CONFLICT (client_user_id) DO NOTHING
            #                 """, (user_id, data['invited_by_user_id']))
            #                 conn.commit()
                
            #     # Очищаем временные данные
            #     if user_id in user_temp_data:
            #         del user_temp_data[user_id]
                
            #     # Очищаем pending_invites для этого ФИО
            #     client_fio = data.get('fio', '')
            #     if 'pending_invites' in user_temp_data and (str(data['invited_by_user_id'])+'_'+client_fio.split()[0]) in user_temp_data['pending_invites']:
            #         del user_temp_data['pending_invites'][str(data['invited_by_user_id'])+'_'+client_fio.split()[0]]
                
            #     # Логика для разных типов клиентов
            #     if data['admin_value'] == 'Клиент_агент':
            #         # Отправляем запрос на подтверждение регистрации АГЕНТУ
            #         inviter_id = data.get('invited_by_user_id')
                    
            #         # Клиенту говорим ждать
            #         msg = bot.send_message(
            #             int(data['user_id']),
            #             "✅ Регистрация завершена!\n\n"
            #             "⏳ Ожидайте подтверждения от агента."
            #         )
            #         if message.from_user.id not in user_temp_data:
            #             user_temp_data[message.from_user.id] = {}
            #         user_temp_data[message.from_user.id]['message_id'] = msg.message_id
            #         # Агенту отправляем запрос на подтверждение
            #         keyboard = types.InlineKeyboardMarkup()
            #         btn_approve = types.InlineKeyboardButton(
            #             "✅ Подтвердить", 
            #             callback_data=f"approve_client_reg_{user_id}"
            #         )
            #         btn_reject = types.InlineKeyboardButton(
            #             "❌ Отклонить", 
            #             callback_data=f"reject_client_reg_{user_id}"
            #         )
            #         keyboard.add(btn_approve, btn_reject)
                    
            #         bot.send_message(
            #             inviter_id,
            #             f"📝 <b>Клиент завершил регистрацию</b>\n\n"
            #             f"👤 ФИО: {data.get('fio', 'Не указано')}\n"
            #             f"📱 Телефон: {data.get('number', 'Не указан')}\n"
            #             f"🏙 Город: {data.get('city_admin', 'Не указан')}\n\n"
            #             f"Подтвердите регистрацию клиента:",
            #             parse_mode='HTML',
            #             reply_markup=keyboard
            #         )
                    
            #     elif data['admin_value'] == 'Клиент':
            #         keyboard = types.InlineKeyboardMarkup()
            #         keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            #         bot.send_message(
            #             message.chat.id,
            #             "✅ Регистрация завершена!",
            #             reply_markup = keyboard
            #         )
            #         bot.send_message(
            #             data['invited_by_user_id'],
            #             f"✅ Клиент {data['fio']} завершил регистрацию!",
            #             reply_markup = keyboard
            #         )
    
                    
            # except Exception as e:
            #     print(f"Ошибка сохранения приглашенного клиента: {e}")
            #     import traceback
            #     traceback.print_exc()
            #     bot.send_message(message.chat.id, "❌ Ошибка регистрации. Попробуйте позже.")
            
        except Exception as e:
            print(f"❌ Ошибка при обработке файла: {e}")
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            msg = bot.send_message(
                message.chat.id, 
                "❌ Ошибка при загрузке файла. Попробуйте еще раз:\n\n"
                "Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):"
            )
            bot.register_next_step_handler(msg, process_invited_client_passport_photo_4_5, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("approve_client_reg_"))
    @prevent_double_click(timeout=3.0)
    def approve_client_registration_by_agent(call):
        """Подтверждение регистрации клиента агентом"""
        agent_id = call.from_user.id
        client_user_id = int(call.data.replace("approve_client_reg_", ""))
        
        # Получаем данные клиента
        client_data = get_admin_from_db_by_user_id(client_user_id)
        agent_data = get_admin_from_db_by_user_id(agent_id)
        print(client_data)
        if not client_data or not agent_data:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        # Обновляем сообщение агента
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📝 <b>Клиент завершил регистрацию</b>\n\n"
                f"👤 ФИО: {client_data.get('fio', 'Не указано')}\n"
                f"📱 Телефон: {client_data.get('number', 'Не указан')}\n"
                f"🏙 Город: {client_data.get('city_admin', 'Не указан')}\n\n"
                f"✅ <b>ПОДТВЕРЖДЕНО</b>",
            parse_mode='HTML'
        )
        
        # Сохраняем связь клиент-агент в БД (если еще не сохранена)
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO client_agent_relationships (client_user_id, agent_id)
                        VALUES (%s, %s)
                        ON CONFLICT (client_user_id) 
                        DO UPDATE SET agent_id = EXCLUDED.agent_id, created_at = CURRENT_TIMESTAMP
                    """, (client_user_id, agent_id))
                    conn.commit()
        except Exception as e:
            print(f"Ошибка сохранения связи: {e}")
        
        # Инициализируем данные для договора
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        
        from datetime import datetime
        user_temp_data[agent_id]['contract_data'] = {
            'fio': client_data.get('fio', ''),
            'fio_k': client_data.get('fio_k', ''),
            'number': client_data.get('number', ''),
            'city': agent_data.get('city_admin', ''),
            'year': str(datetime.now().year)[-2:],
            'user_id': str(client_user_id),
            'creator_user_id': str(agent_id),
            'date_of_birth': client_data.get('date_of_birth', ''),
            'city_birth': client_data.get('city_birth', ''),
            'seria_pasport': client_data.get('seria_pasport', ''),
            'number_pasport': client_data.get('number_pasport', ''),
            'where_pasport': client_data.get('where_pasport', ''),
            'when_pasport': client_data.get('when_pasport', ''),
            'index_postal': client_data.get('index_postal', ''),
            'address': client_data.get('address', '')
        }
        user_temp_data[agent_id]['client_user_id'] = client_user_id
        
        # Показываем агенту кнопку для начала заполнения договора
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            "📋 Начать заполнение договора", 
            callback_data="start_agent_client_contract"
        ))
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        try:
            bot.delete_message(agent_id, msg.message_id)
        except:
            pass
        bot.send_message(
            agent_id,
            f"✅ Регистрация клиента подтверждена!\n\n"
            f"Теперь вы можете начать заполнение договора.",
            reply_markup=keyboard
        )
        
        # Уведомляем клиента
        try:
            try:
                bot.delete_message(client_user_id, user_temp_data[client_user_id]['message_id'])
            except:
                pass
            keyboard_client = types.InlineKeyboardMarkup()
            keyboard_client.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            msg = bot.send_message(
                client_user_id,
                "✅ Ваша регистрация подтверждена агентом!\n\n"
                "Сейчас агент начнет заполнять данные договора.",
                reply_markup=keyboard_client
            )
            user_temp_data[client_user_id]['message_id'] = msg.message_id
        except Exception as e:
            print(f"Ошибка уведомления клиента: {e}")
        
        bot.answer_callback_query(call.id, "✅ Регистрация подтверждена")


    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_client_reg_"))
    @prevent_double_click(timeout=3.0)
    def reject_client_registration_by_agent(call):
        """Отклонение регистрации клиента агентом"""
        agent_id = call.from_user.id
        client_user_id = int(call.data.replace("reject_client_reg_", ""))
        
        # Получаем данные клиента
        client_data = get_admin_from_db_by_user_id(client_user_id)
        
        if not client_data:
            bot.answer_callback_query(call.id, "❌ Данные клиента не найдены", show_alert=True)
            return
        
        # Обновляем сообщение агента
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📝 <b>Клиент завершил регистрацию</b>\n\n"
                f"👤 ФИО: {client_data.get('fio', 'Не указано')}\n"
                f"📱 Телефон: {client_data.get('number', 'Не указан')}\n"
                f"🏙 Город: {client_data.get('city_admin', 'Не указан')}\n\n"
                f"❌ <b>ОТКЛОНЕНО</b>",
            parse_mode='HTML'
        )
        
        # Удаляем клиента из БД (или помечаем как неактивного)
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE admins 
                        SET is_active = false 
                        WHERE user_id = %s
                    """, (str(client_user_id),))
                    conn.commit()
        except Exception as e:
            print(f"Ошибка удаления клиента: {e}")
        
        # Уведомляем клиента
        try:
            bot.send_message(
                client_user_id,
                "❌ Ваша регистрация была отклонена агентом.\n\n"
                "Для повторной регистрации используйте /start"
            )
        except Exception as e:
            print(f"Ошибка уведомления клиента: {e}")
        
        # Возвращаем агента в главное меню
        import time
        time.sleep(1)
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, agent_id)
        
        bot.answer_callback_query(call.id, "❌ Регистрация отклонена")
    
    # ========== САМОСТОЯТЕЛЬНАЯ РЕГИСТРАЦИЯ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data == "btn_registratsia")
    @prevent_double_click(timeout=3.0)
    def callback_registratsia(call):
        """Начало регистрации - показ соглашения"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        # Отправляем соглашение с PDF документом
        consent_text = (
            "Для начала сотрудничества нам необходимо ваше согласие на обработку персональных данных.\n\n"
            "Ознакомьтесь с документом и подтвердите его."
        )
        
        keyboard = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить", callback_data="consent_confirm")
        btn_decline = types.InlineKeyboardButton("❌ Отклонить", callback_data="consent_decline")
        keyboard.add(btn_confirm, btn_decline)
        
        # Отправляем PDF документ
        try:
            with open("Согласие на обработку персональных данных.pdf", "rb") as pdf_file:
                bot.send_document(call.message.chat.id, pdf_file, caption=consent_text, reply_markup=keyboard)
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, consent_text + "\n\n⚠️ Файл соглашения не найден", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["consent_confirm", "consent_decline"])
    @prevent_double_click(timeout=3.0)
    def handle_consent_decision(call):
        """Обработка решения по согласию"""
        user_id = call.from_user.id
        
        if call.data == "consent_decline":
            
            bot.delete_message(call.message.chat.id, call.message.message_id)
            keyboard = types.InlineKeyboardMarkup()
            btn_register = types.InlineKeyboardButton("📝 Зарегистрироваться заново", callback_data="btn_registratsia")
            keyboard.add(btn_register)
            
            bot.send_message(call.message.chat.id, "❌ Вы отказались от обработки персональных данных.\nДля работы с ботом необходимо дать согласие.\nВы можете начать регистрацию заново.", reply_markup=keyboard)
            return
        
        # Согласие подтверждено - переход к выбору роли
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🏢 ЦПР", callback_data="admin_CPR")
        btn2 = types.InlineKeyboardButton("👨‍💼 Офис", callback_data="admin_agent")
        btn3 = types.InlineKeyboardButton("👤 Клиент", callback_data="admin_client")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        bot.send_message(
            call.message.chat.id,
            "✅ Согласие получено!\nВыберите из предложенных вариантов:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["admin_CPR", "admin_agent"])
    @prevent_double_click(timeout=3.0)
    def callback_registratsia_pers(call):
        """Выбор роли в ЦПР или Агент"""
        keyboard = types.InlineKeyboardMarkup()
        
        if call.data == "admin_CPR":
            btn1 = types.InlineKeyboardButton("👔 Генеральный директор", callback_data="admin_CPR_director")
            btn2 = types.InlineKeyboardButton("💻 IT отдел", callback_data="admin_CPR_it")
            btn3 = types.InlineKeyboardButton("⚖️ Претензионный отдел", callback_data="admin_CPR_pret")
            btn4 = types.InlineKeyboardButton("🔍 Исковой отдел", callback_data="admin_CPR_isk")
            btn5 = types.InlineKeyboardButton("📊 Бухгалтер", callback_data="admin_CPR_accountant")
            btn6 = types.InlineKeyboardButton("🏷️ Оценщик", callback_data="admin_CPR_appraiser")
            btn7 = types.InlineKeyboardButton("👥 HR отдел", callback_data="admin_CPR_hr")

            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)
            keyboard.add(btn5)
            keyboard.add(btn6)
            keyboard.add(btn7)
        
        elif call.data == "admin_agent":
            btn1 = types.InlineKeyboardButton("👨‍💼 Директор офиса", callback_data="admin_office_director_office")
            btn2 = types.InlineKeyboardButton("📋 Администратор", callback_data="admin_office_admin")
            btn3 = types.InlineKeyboardButton("⚖️ Юрист", callback_data="admin_office_ur")
            btn4 = types.InlineKeyboardButton("🤝 Агент", callback_data="admin_office_agent")
            
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)

        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="btn_registratsia")
        keyboard.add(btn_back)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите должность:",
            reply_markup=keyboard
        )
    
    
    @bot.callback_query_handler(func=lambda call: call.data in [
        "admin_CPR_director", "admin_CPR_it", "admin_CPR_pret", "admin_CPR_isk", "admin_CPR_accountant", "admin_CPR_appraiser", "admin_CPR_hr",
        "admin_office_director_office", "admin_office_admin", "admin_office_ur", "admin_office_agent","admin_client"
    ])
    @prevent_double_click(timeout=3.0)
    def callback_admin_city(call):
        """Выбор конкретной роли и переход к выбору города"""
        role_mapping = {
            "admin_CPR_director": "Генеральный директор",
            "admin_CPR_it": "IT отдел",
            "admin_CPR_pret": "Претензионный отдел",
            "admin_CPR_isk": "Исковой отдел",
            "admin_CPR_accountant": "Бухгалтер",
            "admin_CPR_appraiser": "Оценщик",
            "admin_CPR_hr": "HR отдел",
            "admin_office_director_office": "Директор офиса",
            "admin_office_admin": "Администратор",
            "admin_office_ur": "Юрист",
            "admin_office_agent": "Агент",
            "admin_client": "Клиент"
        }
        
        user_id = call.from_user.id
        data = {'admin_value': role_mapping[call.data]}
        if data.get('admin_value', '') == "Оценщик":
            if user_id not in user_temp_data:
                user_temp_data[user_id] = {}
            user_temp_data[user_id].update(data)
            
            keyboard = types.InlineKeyboardMarkup()
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="btn_registratsia")
            keyboard.add(btn_back)
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Для начала работы, пожалуйста, предоставьте ваши данные.\n\nВведите название организации",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, org_admin, data, msg.message_id)
        else:
            data.update({'org': '-'})
            if user_id not in user_temp_data:
                user_temp_data[user_id] = {}
            user_temp_data[user_id].update(data)
            
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🏙 Томск", callback_data="btn_city_Tomsk_admin")
            btn2 = types.InlineKeyboardButton("🏙 Красноярск", callback_data="btn_city_Krasnoyarsk_admin")
            btn3 = types.InlineKeyboardButton("🏙 Новосибирск", callback_data="btn_city_Novosibirsk_admin")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="btn_registratsia")
            
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn_back)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Для начала работы, пожалуйста, предоставьте ваши данные.\n\nВыберите город:",
                reply_markup=keyboard
            )
    def org_admin(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({'org': message.text.strip()})
        if user_id not in user_temp_data:
                user_temp_data[user_id] = {}
        user_temp_data[user_id].update(data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🏙 Томск", callback_data="btn_city_Tomsk_admin")
        btn2 = types.InlineKeyboardButton("🏙 Красноярск", callback_data="btn_city_Krasnoyarsk_admin")
        btn3 = types.InlineKeyboardButton("🏙 Новосибирск", callback_data="btn_city_Novosibirsk_admin")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_org_admin")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn_back)
        
        bot.send_message(
            chat_id=message.chat.id,
            text="Выберите город:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_org_admin")
    @prevent_double_click(timeout=3.0)
    def back_to_org_admin(call):
        """Возврат к выбору роли"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)

        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}

        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="btn_registratsia")
        keyboard.add(btn_back)
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название вашей организации",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, org_admin, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["btn_city_Tomsk_admin", "btn_city_Krasnoyarsk_admin", "btn_city_Novosibirsk_admin"])
    @prevent_double_click(timeout=3.0)
    def callback_admin_value(call):
        """Выбор города и запрос ФИО"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        if call.data == "btn_city_Tomsk_admin":
            data['city_admin'] = "Томск"
        elif call.data == "btn_city_Krasnoyarsk_admin":
            data['city_admin'] = "Красноярск"
        elif call.data == "btn_city_Novosibirsk_admin":
            data['city_admin'] = "Новосибирск"
        
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_role_selection"))
        # Запрос ФИО
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🤖 Прикрепите фото основного разворота паспорта (2-3 стр):",
            reply_markup = keyboard
        )
        
        bot.register_next_step_handler(message, process_passport_photo_2_3, data, message.message_id)
        
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_role_selection")
    @prevent_double_click(timeout=3.0)
    def back_to_role_selection(call):
        """Возврат к выбору роли"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)

        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🏙 Томск", callback_data="btn_city_Tomsk_admin")
        btn2 = types.InlineKeyboardButton("🏙 Красноярск", callback_data="btn_city_Krasnoyarsk_admin")
        btn3 = types.InlineKeyboardButton("🏙 Новосибирск", callback_data="btn_city_Novosibirsk_admin")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="btn_registratsia")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn_back)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите город:",
            reply_markup=keyboard
        )
    
    def process_fio_admin(message, data, prev_message_id):
        """Обработка ввода ФИО"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)

        try:
            bot.delete_message(message.chat.id, prev_message_id)
        except:
            pass
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        # Проверка формата ФИО
        if len(message.text.split()) < 2:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_role_selection"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат ввода!\nВведите ФИО в формате: Иванов Иван Иванович",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_fio'
            bot.register_next_step_handler(msg, process_fio_admin, data, msg.message_id)
            return
        
        words = message.text.split()
        for word in words:
            if not word[0].isupper():
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_role_selection"))
                msg = bot.send_message(
                    message.chat.id,
                    "❌ Каждое слово должно начинаться с заглавной буквы!\n"
                    "Введите ФИО в формате: Иванов Иван Иванович",
                    reply_markup=keyboard
                )
                active_handlers[message.chat.id] = 'waiting_fio'
                bot.register_next_step_handler(msg, process_fio_admin, data, msg.message_id)
                return
        
        client_fio = message.text.strip()
        
        # Проверка существующих клиентов с таким ФИО
        # existing_clients = search_clients_by_fio_in_db(client_fio)
        
        # if existing_clients:
        #     keyboard = types.InlineKeyboardMarkup()
            
        #     response = f"⚠️ Найдены пользователи с ФИО '{client_fio}':\n\n"
        #     for i, client in enumerate(existing_clients[:5], 1):
        #         response += f"{i}. 📱 {client.get('number', 'Не указан')}\n"
        #         response += f"   📅 Регистрация: {client.get('created_at', '')[:10]}\n\n"
                
        #         btn_text = f"{i}. Телефон {client.get('number', 'н/д')}"
        #         btn_callback = f"select_existing_reg_{client['client_id']}"
        #         keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
            
        #     keyboard.add(types.InlineKeyboardButton("➕ Создать нового", callback_data="create_new_reg_client"))
        #     keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="callback_start"))
            
        #     # Сохраняем ФИО
        #     user_id = message.from_user.id
        #     if user_id not in user_temp_data:
        #         user_temp_data[user_id] = {}
        #     user_temp_data[user_id]['pending_fio'] = client_fio
        #     user_temp_data[user_id].update(data)
            
        #     bot.send_message(message.chat.id, response, reply_markup=keyboard)
        #     return
        
        # ФИО уникально - продолжаем регистрацию
        data['fio'] = client_fio
        if len(client_fio.split())==2:
            data.update({"fio_k": client_fio.split()[0]+" "+list(client_fio.split()[1])[0]+"."})
        else:
            data.update({"fio_k": client_fio.split()[0]+" "+list(client_fio.split()[1])[0]+"."+list(client_fio.split()[2])[0]+"."})
        
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_fio_input"))
        msg = bot.send_message(message.chat.id, "Введите номер телефона (например, +79001234567):", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_phone'
        bot.register_next_step_handler(msg, process_phone_registration, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_fio_input")
    @prevent_double_click(timeout=3.0)
    def back_to_fio_input(call):
        """Возврат к вводу ФИО"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_role_selection"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО в формате: Иванов Иван Иванович",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_fio'
        bot.register_next_step_handler(message, process_fio_admin, data, message.message_id)

    def process_phone_registration(message, data, prev_message_id):
        """Обработка номера телефона"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        phone = message.text.strip()
        
        # Базовая проверка номера телефона
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_fio_input"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат номера телефона. Введите снова (например, +79001234567):",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_phone'
            bot.register_next_step_handler(msg, process_phone_registration, data, msg.message_id)
            return
        
        data['number'] = phone
        user_temp_data[message.from_user.id] = data
        
        if data['seria_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите серию паспорта (4 цифры):"
            )

            bot.register_next_step_handler(message, process_invited_client_passport_series, data, msg.message_id)
        elif data['number_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите номер паспорта (6 цифр):"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_number, data, msg.message_id)

        elif data['where_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите, кем выдан паспорт:"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_issued_by, data, msg.message_id)
        elif data['when_pasport'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату выдачи паспорта (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_passport_date, data, msg.message_id)
        elif data['date_of_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите дату рождения (ДД.ММ.ГГГГ):"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
        elif data['city_birth'] == '':
            msg = bot.send_message(
                message.chat.id,
                "Введите город рождения:"
            )

            bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "Введите адрес регистрации по паспорту:"
            )

            bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_phone_input")
    @prevent_double_click(timeout=3.0)
    def back_to_phone_input(call):
        """Возврат к вводу телефона"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        # Удаляем сообщение с паспортными данными если оно есть
        if 'passport_info_message_id' in data:
            try:
                bot.delete_message(call.message.chat.id, data['passport_info_message_id'])
                del data['passport_info_message_id']
            except:
                pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_fio_input"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер телефона (например, +79001234567):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_phone'
        bot.register_next_step_handler(message, process_phone_registration, data, message.message_id)

    def process_new_passport_series(message, data, prev_message_id):
        """Обработка серии паспорта"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        series = message.text.strip()
        
        if not series.isdigit() or len(series) != 4:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_phone_input"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Серия паспорта должна содержать 4 цифры. Попробуйте снова:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_passport_series'
            bot.register_next_step_handler(msg, process_new_passport_series, data, msg.message_id)
            return
        
        data['seria_pasport'] = series
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_series"))
        msg = bot.send_message(message.chat.id, "Введите номер паспорта (6 цифр):", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_passport_number'
        bot.register_next_step_handler(msg, process_new_passport_number, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_passport_series")
    @prevent_double_click(timeout=3.0)
    def back_to_passport_series(call):
        """Возврат к вводу серии паспорта"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_phone_input"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию паспорта (4 цифры):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_passport_series'
        bot.register_next_step_handler(message, process_new_passport_series, data, message.message_id)

    def process_new_passport_number(message, data, prev_message_id):
        """Обработка номера паспорта"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        number = message.text.strip()
        
        if not number.isdigit() or len(number) != 6:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_series"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Номер паспорта должен содержать 6 цифр. Попробуйте снова:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_passport_number'
            bot.register_next_step_handler(msg, process_new_passport_number, data, msg.message_id)
            return
        
        data['number_pasport'] = number
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_number"))
        msg = bot.send_message(message.chat.id, "Введите, кем выдан паспорт:", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_passport_issued'
        bot.register_next_step_handler(msg, process_new_passport_issued_by, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_passport_number")
    @prevent_double_click(timeout=3.0)
    def back_to_passport_number(call):
        """Возврат к вводу номера паспорта"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_series"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер паспорта (6 цифр):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_passport_number'
        bot.register_next_step_handler(message, process_new_passport_number, data, message.message_id)

    def process_new_passport_issued_by(message, data, prev_message_id):
        """Обработка поля 'кем выдан'"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['where_pasport'] = message.text.strip()
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_issued"))
        msg = bot.send_message(message.chat.id, "Введите дату выдачи паспорта (ДД.ММ.ГГГГ):", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_passport_date'
        bot.register_next_step_handler(msg, process_new_passport_date, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_passport_issued")
    @prevent_double_click(timeout=3.0)
    def back_to_passport_issued_handler(call):
        """Возврат к вводу 'кем выдан'"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_number"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите, кем выдан паспорт:",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_passport_issued'
        bot.register_next_step_handler(message, process_new_passport_issued_by, data, message.message_id)

    def process_new_passport_date(message, data, prev_message_id):
        """Обработка даты выдачи паспорта"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        date_text = message.text.strip()
        
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_issued"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат даты. Введите в формате ДД.ММ.ГГГГ:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_passport_date'
            bot.register_next_step_handler(msg, process_new_passport_date, data, msg.message_id)
            return
        
        data['when_pasport'] = date_text
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_date"))
        msg = bot.send_message(message.chat.id, "Введите дату рождения (ДД.ММ.ГГГГ):", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_birth_date'
        bot.register_next_step_handler(msg, process_birth_date, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_passport_date")
    @prevent_double_click(timeout=3.0)
    def back_to_passport_date_handler(call):
        """Возврат к вводу даты выдачи паспорта"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_issued"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату выдачи паспорта (ДД.ММ.ГГГГ):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_passport_date'
        bot.register_next_step_handler(message, process_new_passport_date, data, message.message_id)

    def process_birth_date(message, data, prev_message_id):
        """Обработка даты рождения"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        date_text = message.text.strip()
        
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_date"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат даты. Введите в формате ДД.ММ.ГГГГ:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_birth_date'
            bot.register_next_step_handler(msg, process_birth_date, data, msg.message_id)
            return
        
        data['date_of_birth'] = date_text
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_birth_date"))
        msg = bot.send_message(message.chat.id, "Введите город рождения:", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_birth_city'
        bot.register_next_step_handler(msg, process_birth_city, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_birth_date")
    @prevent_double_click(timeout=3.0)
    def back_to_birth_date_handler(call):
        """Возврат к вводу даты рождения"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_passport_date"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату рождения (ДД.ММ.ГГГГ):",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_birth_date'
        bot.register_next_step_handler(message, process_birth_date, data, message.message_id)

    def process_birth_city(message, data, prev_message_id):
        """Обработка города рождения"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['city_birth'] = message.text.strip()
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_birth_city"))
        msg = bot.send_message(message.chat.id, "Введите адрес регистрации по паспорту:", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_address'
        bot.register_next_step_handler(msg, process_address, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_birth_city")
    @prevent_double_click(timeout=3.0)
    def back_to_birth_city_handler(call):
        """Возврат к вводу города рождения"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_birth_date"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите город рождения:",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_birth_city'
        bot.register_next_step_handler(message, process_birth_city, data, message.message_id)

    def process_address(message, data, prev_message_id):
        """Обработка адреса прописки"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['address'] = message.text.strip()
        user_temp_data[message.from_user.id] = data
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address"))
        msg = bot.send_message(message.chat.id, "Введите почтовый индекс:", reply_markup=keyboard)
        active_handlers[message.chat.id] = 'waiting_postal_index'
        bot.register_next_step_handler(msg, process_postal_index, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_address")
    @prevent_double_click(timeout=3.0)
    def back_to_address_handler(call):
        """Возврат к вводу адреса"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        
        data = user_temp_data.get(user_id, {})
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_birth_city"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес регистрации по паспорту:",
            reply_markup=keyboard
        )
        
        active_handlers[call.message.chat.id] = 'waiting_address'
        bot.register_next_step_handler(message, process_address, data, message.message_id)

    def process_postal_index(message, data, prev_message_id):
        """Обработка почтового индекса"""
        user_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        index = message.text.strip()
        
        if not index.isdigit() or len(index) != 6:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address"))
            msg = bot.send_message(
                message.chat.id,
                "❌ Почтовый индекс должен содержать 6 цифр. Попробуйте снова:",
                reply_markup=keyboard
            )
            active_handlers[message.chat.id] = 'waiting_postal_index'
            bot.register_next_step_handler(msg, process_postal_index, data, msg.message_id)
            return
        
        data['index_postal'] = index
        user_temp_data[message.from_user.id] = data
        
        # Показываем все введенные данные для подтверждения
        show_registration_summary(bot, message.chat.id, data)

    def show_registration_summary(bot, chat_id, data):
        """Показ всех введенных данных с кнопками подтверждения"""
        summary = "📋 <b>Проверьте введенные данные:</b>\n\n"
        summary += f"👤 <b>ФИО:</b> {data.get('fio', 'Не указано')}\n"
        summary += f"📱 <b>Телефон:</b> {data.get('number', 'Не указан')}\n"
        summary += f"🏙 <b>Город:</b> {data.get('city_admin', 'Не указан')}\n"
        summary += f"💼 <b>Должность:</b> {data.get('admin_value', 'Не указано')}\n\n"
        summary += f"📄 <b>Паспортные данные:</b>\n"
        summary += f"• Серия: {data.get('seria_pasport', 'Не указана')}\n"
        summary += f"• Номер: {data.get('number_pasport', 'Не указан')}\n"
        summary += f"• Кем выдан: {data.get('where_pasport', 'Не указано')}\n"
        summary += f"• Когда выдан: {data.get('when_pasport', 'Не указано')}\n"
        summary += f"• Дата рождения: {data.get('date_of_birth', 'Не указана')}\n"
        summary += f"• Город рождения: {data.get('city_birth', 'Не указан')}\n"
        summary += f"• Адрес прописки: {data.get('address', 'Не указан')}\n"
        summary += f"• Почтовый индекс: {data.get('index_postal', 'Не указан')}\n"
        
        keyboard = types.InlineKeyboardMarkup()
        btn_accept = types.InlineKeyboardButton("✅ Принять данные", callback_data="accept_registration_data")
        btn_change = types.InlineKeyboardButton("✏️ Изменить данные", callback_data="change_registration_data")
        keyboard.add(btn_accept)
        keyboard.add(btn_change)
        
        bot.send_message(chat_id, summary, parse_mode='HTML', reply_markup=keyboard)

    # ========== ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ ПОЛЕЙ ==========
    @bot.callback_query_handler(func=lambda call: call.data == "edit_fio")
    @prevent_double_click(timeout=3.0)
    def edit_fio_handler(call):
        """Редактирование ФИО"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новое ФИО в формате: Иванов Иван Иванович"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_fio, data, call.message.message_id)

    def update_fio(message, data, prev_message_id):
        """Обновление ФИО"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.split()) < 2:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат! Введите ФИО заново:")
            bot.register_next_step_handler(msg, update_fio, data, msg.message_id)
            return
        
        words = message.text.split()
        for word in words:
            if not word[0].isupper():
                msg = bot.send_message(message.chat.id, "❌ Каждое слово должно начинаться с заглавной буквы!")
                bot.register_next_step_handler(msg, update_fio, data, msg.message_id)
                return
        
        data['fio'] = message.text.strip()
        if len(message.text.split()) == 2:
            data['fio_k'] = message.text.split()[0] + " " + list(message.text.split()[1])[0] + "."
        else:
            data['fio_k'] = message.text.split()[0] + " " + list(message.text.split()[1])[0] + "." + list(message.text.split()[2])[0] + "."
        
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_phone")
    @prevent_double_click(timeout=3.0)
    def edit_phone_handler(call):
        """Редактирование телефона"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новый номер телефона (например, +79001234567):"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_phone, data, call.message.message_id)

    def update_phone(message, data, prev_message_id):
        """Обновление телефона"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        phone = message.text.strip()
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            msg = bot.send_message(message.chat.id, "❌ Неверный формат. Введите заново:")
            bot.register_next_step_handler(msg, update_phone, data, msg.message_id)
            return
        
        data['number'] = phone
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_city")
    @prevent_double_click(timeout=3.0)
    def edit_city_handler(call):
        """Редактирование города"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новый город проживания:"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_city, data, call.message.message_id)

    def update_city(message, data, prev_message_id):
        """Обновление города"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['city_admin'] = message.text.strip()
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_birth_date")
    @prevent_double_click(timeout=3.0)
    def edit_birth_date_handler(call):
        """Редактирование даты рождения"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новую дату рождения (ДД.ММ.ГГГГ):"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_birth_date, data, call.message.message_id)

    def update_birth_date(message, data, prev_message_id):
        """Обновление даты рождения"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        date_text = message.text.strip()
        
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            msg = bot.send_message(message.chat.id, "❌ Неверный формат. Введите в формате ДД.ММ.ГГГГ:")
            bot.register_next_step_handler(msg, update_birth_date, data, msg.message_id)
            return
        
        data['date_of_birth'] = date_text
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_birth_city")
    @prevent_double_click(timeout=3.0)
    def edit_birth_city_handler(call):
        """Редактирование города рождения"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новый город рождения:"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_birth_city, data, call.message.message_id)

    def update_birth_city(message, data, prev_message_id):
        """Обновление города рождения"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['city_birth'] = message.text.strip()
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_series")
    @prevent_double_click(timeout=3.0)
    def edit_passport_series_handler(call):
        """Редактирование серии паспорта"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новую серию паспорта (4 цифры):"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_passport_series, data, call.message.message_id)

    def update_passport_series(message, data, prev_message_id):
        """Обновление серии паспорта"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        series = message.text.strip()
        
        if not series.isdigit() or len(series) != 4:
            msg = bot.send_message(message.chat.id, "❌ Серия должна содержать 4 цифры:")
            bot.register_next_step_handler(msg, update_passport_series, data, msg.message_id)
            return
        
        data['seria_pasport'] = series
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_number")
    @prevent_double_click(timeout=3.0)
    def edit_passport_number_handler(call):
        """Редактирование номера паспорта"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новый номер паспорта (6 цифр):"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_passport_number, data, call.message.message_id)

    def update_passport_number(message, data, prev_message_id):
        """Обновление номера паспорта"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        number = message.text.strip()
        
        if not number.isdigit() or len(number) != 6:
            msg = bot.send_message(message.chat.id, "❌ Номер должен содержать 6 цифр:")
            bot.register_next_step_handler(msg, update_passport_number, data, msg.message_id)
            return
        
        data['number_pasport'] = number
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_issued")
    @prevent_double_click(timeout=3.0)
    def edit_passport_issued_handler(call):
        """Редактирование 'кем выдан'"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новые данные - кем выдан паспорт:"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_passport_issued, data, call.message.message_id)

    def update_passport_issued(message, data, prev_message_id):
        """Обновление 'кем выдан'"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['where_pasport'] = message.text.strip()
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_date")
    @prevent_double_click(timeout=3.0)
    def edit_passport_date_handler(call):
        """Редактирование даты выдачи паспорта"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новую дату выдачи паспорта (ДД.ММ.ГГГГ):"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_passport_date, data, call.message.message_id)

    def update_passport_date(message, data, prev_message_id):
        """Обновление даты выдачи паспорта"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        date_text = message.text.strip()
        
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            msg = bot.send_message(message.chat.id, "❌ Неверный формат. Введите в формате ДД.ММ.ГГГГ:")
            bot.register_next_step_handler(msg, update_passport_date, data, msg.message_id)
            return
        
        data['when_pasport'] = date_text
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_address")
    @prevent_double_click(timeout=3.0)
    def edit_address_handler(call):
        """Редактирование адреса прописки"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новый адрес прописки:"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_address, data, call.message.message_id)

    def update_address(message, data, prev_message_id):
        """Обновление адреса"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['address'] = message.text.strip()
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_postal")
    @prevent_double_click(timeout=3.0)
    def edit_postal_handler(call):
        """Редактирование почтового индекса"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите новый почтовый индекс (6 цифр):"
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, update_postal, data, call.message.message_id)

    def update_postal(message, data, prev_message_id):
        """Обновление почтового индекса"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        index = message.text.strip()
        
        if not index.isdigit() or len(index) != 6:
            msg = bot.send_message(message.chat.id, "❌ Индекс должен содержать 6 цифр:")
            bot.register_next_step_handler(msg, update_postal, data, msg.message_id)
            return
        
        data['index_postal'] = index
        user_temp_data[message.from_user.id] = data
        show_registration_summary(bot, message.chat.id, data)
    @bot.callback_query_handler(func=lambda call: call.data == "change_registration_data")
    @prevent_double_click(timeout=3.0)
    def change_registration_data_handler(call):
        """Показ кнопок для изменения конкретных полей"""
        user_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("👤 ФИО", callback_data="edit_fio"))
        keyboard.add(types.InlineKeyboardButton("📱 Номер телефона", callback_data="edit_phone"))
        keyboard.add(types.InlineKeyboardButton("🏙 Город", callback_data="edit_city"))
        keyboard.add(types.InlineKeyboardButton("📅 Дата рождения", callback_data="edit_birth_date"))
        keyboard.add(types.InlineKeyboardButton("🏙 Город рождения", callback_data="edit_birth_city"))
        keyboard.add(types.InlineKeyboardButton("📄 Серия паспорта", callback_data="edit_passport_series"))
        keyboard.add(types.InlineKeyboardButton("📄 Номер паспорта", callback_data="edit_passport_number"))
        keyboard.add(types.InlineKeyboardButton("🏢 Кем выдан", callback_data="edit_passport_issued"))
        keyboard.add(types.InlineKeyboardButton("📅 Когда выдан", callback_data="edit_passport_date"))
        keyboard.add(types.InlineKeyboardButton("🏠 Адрес прописки", callback_data="edit_address"))
        keyboard.add(types.InlineKeyboardButton("📮 Почтовый индекс", callback_data="edit_postal"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к данным", callback_data="back_to_summary"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите поле для изменения:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_summary")
    @prevent_double_click(timeout=3.0)
    def back_to_summary_handler(call):
        """Возврат к просмотру данных"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_registration_summary(bot, call.message.chat.id, data)
    @bot.callback_query_handler(func=lambda call: call.data == "accept_registration_data")
    @prevent_double_click(timeout=3.0)
    def accept_registration_data_handler(call):
        """Принятие данных и запрос фото паспорта"""
        user_id = call.from_user.id
        data = user_temp_data.get(user_id, {})
        
        if not data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
    
        # Удаляем старое сообщение "Заполните паспортные данные" если оно есть
        if 'passport_info_message_id' in data:
            try:
                bot.delete_message(call.message.chat.id, data['passport_info_message_id'])
            except:
                pass
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        if data['admin_value'] == 'Клиент_агент':
            # ТЕПЕРЬ СОХРАНЯЕМ В БД И ОТПРАВЛЯЕМ НА ПОДТВЕРЖДЕНИЕ
            data['admin_value'] = 'Клиент'
            user_id = data['user_id']
            inviter_type = data.get('invited_by_type')
            
            # Сохраняем в БД
            try:
                db.save_admin(data)
                
                # Сохраняем связь клиент-агент если приглашающий был агентом
                if inviter_type == 'agent':
                    with db.get_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                INSERT INTO client_agent_relationships (client_user_id, agent_id)
                                VALUES (%s, %s)
                                ON CONFLICT (client_user_id) DO NOTHING
                            """, (user_id, data['invited_by_user_id']))
                            conn.commit()
                
                # Очищаем временные данные
                if user_id in user_temp_data:
                    del user_temp_data[user_id]
                
                # Очищаем pending_invites для этого ФИО
                client_fio = data.get('fio', '')
                if 'pending_invites' in user_temp_data and (str(data['invited_by_user_id'])+'_'+client_fio.split()[0]) in user_temp_data['pending_invites']:
                    del user_temp_data['pending_invites'][str(data['invited_by_user_id'])+'_'+client_fio.split()[0]]
                
                
                # Отправляем запрос на подтверждение регистрации АГЕНТУ
                inviter_id = data.get('invited_by_user_id')
                
                # Клиенту говорим ждать
                msg = bot.send_message(
                    int(data['user_id']),
                    "✅ Регистрация завершена!\n\n"
                    "⏳ Ожидайте подтверждения от агента."
                )
                if call.message.from_user.id not in user_temp_data:
                    user_temp_data[call.message.from_user.id] = {}
                user_temp_data[call.message.from_user.id]['message_id'] = msg.message_id
                # Агенту отправляем запрос на подтверждение
                keyboard = types.InlineKeyboardMarkup()
                btn_approve = types.InlineKeyboardButton(
                    "✅ Подтвердить", 
                    callback_data=f"approve_client_reg_{user_id}"
                )
                btn_reject = types.InlineKeyboardButton(
                    "❌ Отклонить", 
                    callback_data=f"reject_client_reg_{user_id}"
                )
                keyboard.add(btn_approve, btn_reject)
                
                bot.send_message(
                    inviter_id,
                    f"📝 <b>Клиент завершил регистрацию</b>\n\n"
                    f"👤 ФИО: {data.get('fio', 'Не указано')}\n"
                    f"📱 Телефон: {data.get('number', 'Не указан')}\n"
                    f"🏙 Город: {data.get('city_admin', 'Не указан')}\n\n"
                    f"Подтвердите регистрацию клиента:",
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                    
    
                    
            except Exception as e:
                print(f"Ошибка сохранения приглашенного клиента: {e}")
                import traceback
                traceback.print_exc()
                bot.send_message(call.message.chat.id, "❌ Ошибка регистрации. Попробуйте позже.")
        else:
            finalize_registration(bot, user_id, data)


    def process_passport_photo_2_3(message, data, message_id):
        """Обработка фото 2-3 страницы паспорта (поддерживает фото и файлы)"""
        file_id = None
        file_extension = None
        
        # Проверяем разные типы контента
        if message.photo:
            # Обработка фото
            file_id = message.photo[-1].file_id
            file_extension = "jpg"
        elif message.document:
            # Обработка файлов (PDF, PNG, JPG и т.д.)
            mime_type = message.document.mime_type
            file_name = message.document.file_name.lower()
            
            # Разрешенные форматы
            allowed_formats = [
                'image/jpeg', 'image/jpg', 'image/png', 'image/jpeg', 
                'application/pdf', 'image/jpeg'
            ]
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.heic']
            
            # Проверяем формат файла
            if (mime_type not in allowed_formats and 
                not any(file_name.endswith(ext) for ext in allowed_extensions)):
                
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Неподдерживаемый формат файла. Отправьте фото или файл в формате JPG, PNG, PDF:\n\n"
                    "Прикрепите фото основного разворота паспорта (2-3 стр):"
                )
                bot.register_next_step_handler(msg, process_passport_photo_2_3, data, msg.message_id)
                return
            
            file_id = message.document.file_id
            # Определяем расширение из имени файла или MIME типа
            if '.' in file_name:
                file_extension = file_name.split('.')[-1]
            elif mime_type == 'application/pdf':
                file_extension = 'pdf'
            elif mime_type == 'image/png':
                file_extension = 'png'
            elif mime_type in ['image/jpeg', 'image/jpg']:
                file_extension = 'jpg'
            else:
                file_extension = 'jpg'  # fallback
        else:
            try:
                # Ни фото ни файл не отправлены
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            msg = bot.send_message(
                message.chat.id, 
                "❌ Пожалуйста, отправьте фото или файл. Прикрепите фото основного разворота паспорта (2-3 стр):"
            )
            bot.register_next_step_handler(msg, process_passport_photo_2_3, data, msg.message_id)
            return
        
        try:
            # Получаем информацию о файле
            if message.photo:
                file_info = bot.get_file(file_id)
            else:
                file_info = bot.get_file(file_id)
            
            downloaded_file = bot.download_file(file_info.file_path)
            
            fio = data.get('fio', 'Unknown')
            folder_path = f"admins_info/{fio}"
            os.makedirs(folder_path, exist_ok=True)
            
            # Сохраняем файл с правильным расширением
            file_path = f"{folder_path}/Паспорт_2-3.{file_extension}"
            
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            data['passport_photo_2_3'] = file_path
            user_temp_data[message.from_user.id] = data

            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, message.message_id)

            msg = bot.send_message(
                message.chat.id, 
                "✅ Файл принят!\n\n🤖 Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):"
            )
            bot.register_next_step_handler(msg, process_passport_photo_4_5, data, msg.message_id)
            
        except Exception as e:
            print(f"❌ Ошибка при обработке файла: {e}")
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, message.message_id)
            msg = bot.send_message(
                message.chat.id, 
                "❌ Ошибка при загрузке файла. Попробуйте еще раз:\n\n"
                "Прикрепите фото основного разворота паспорта (2-3 стр):"
            )
            bot.register_next_step_handler(msg, process_passport_photo_2_3, data, msg.message_id)

    def process_passport_photo_4_5(message, data, message_id):
        """Обработка фото 4-5 страницы паспорта (поддерживает фото и файлы)"""
        file_id = None
        file_extension = None
        
        # Проверяем разные типы контента
        if message.photo:
            # Обработка фото
            file_id = message.photo[-1].file_id
            file_extension = "jpg"
        elif message.document:
            # Обработка файлов (PDF, PNG, JPG и т.д.)
            mime_type = message.document.mime_type
            file_name = message.document.file_name.lower()
            
            # Разрешенные форматы
            allowed_formats = [
                'image/jpeg', 'image/jpg', 'image/png', 'image/jpeg', 
                'application/pdf', 'image/jpeg'
            ]
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.heic']
            
            # Проверяем формат файла
            if (mime_type not in allowed_formats and 
                not any(file_name.endswith(ext) for ext in allowed_extensions)):
                
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Неподдерживаемый формат файла. Отправьте фото или файл в формате JPG, PNG, PDF:\n\n"
                    "Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):"
                )
                bot.register_next_step_handler(msg, process_passport_photo_4_5, data, msg.message_id)
                return
            
            file_id = message.document.file_id
            # Определяем расширение из имени файла или MIME типа
            if '.' in file_name:
                file_extension = file_name.split('.')[-1]
            elif mime_type == 'application/pdf':
                file_extension = 'pdf'
            elif mime_type == 'image/png':
                file_extension = 'png'
            elif mime_type in ['image/jpeg', 'image/jpg']:
                file_extension = 'jpg'
            else:
                file_extension = 'jpg'  # fallback
        else:
            # Ни фото ни файл не отправлены
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, message.message_id)
            msg = bot.send_message(
                message.chat.id, 
                "❌ Пожалуйста, отправьте фото или файл. Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):"
            )
            bot.register_next_step_handler(msg, process_passport_photo_4_5, data, msg.message_id)
            return
        
        try:
            # Получаем информацию о файле
            if message.photo:
                file_info = bot.get_file(file_id)
            else:
                file_info = bot.get_file(file_id)
            
            downloaded_file = bot.download_file(file_info.file_path)
            
            fio = data.get('fio', 'Unknown')
            folder_path = f"admins_info/{fio}"
            os.makedirs(folder_path, exist_ok=True)
            
            # Сохраняем файл с правильным расширением
            file_path = f"{folder_path}/Прописка.{file_extension}"
            
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            data['passport_photo_4_5'] = file_path
            data['user_id'] = str(message.from_user.id)
            user_temp_data[message.from_user.id] = data
            
            # Удаляем все промежуточные сообщения
            # Удаляем сообщение с информацией о паспортных данных
            if 'passport_info_message_id' in data:
                try:
                    bot.delete_message(message.chat.id, data['passport_info_message_id'])
                except:
                    pass
            
            # Удаляем текущее сообщение с фото
            try:
                bot.delete_message(message.chat.id, message.message_id)
                bot.delete_message(message.chat.id, message_id)
            except:
                pass
            data_pasport = process_passport_image(data['passport_photo_2_3'], GIGACHAT_TOKEN)
            data.update({'fio': data_pasport['fio']})
            data.update({'seria_pasport': data_pasport['seria_pasport']})
            data.update({'number_pasport': data_pasport['number_pasport']})
            data.update({'where_pasport': data_pasport['where_pasport']})
            data.update({'when_pasport': data_pasport['when_pasport']})
            data.update({'date_of_birth': data_pasport['date_of_birth']})
            data.update({'city_birth': data_pasport['city_birth']})
            print(data)
            if data['fio'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите ФИО (Иванов Иван Иванович)"
                )

                bot.register_next_step_handler(message, process_fio_admin, data, msg.message_id)
            elif data.get('number') in (None, ''):
                msg = bot.send_message(message.chat.id, "Введите номер телефона (например, +79001234567):")

                bot.register_next_step_handler(msg, process_phone_registration, data, msg.message_id)
            elif data['seria_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите серию паспорта (4 цифры):"
                )

                bot.register_next_step_handler(message, process_invited_client_passport_series, data, msg.message_id)
            elif data['number_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите номер паспорта (6 цифр):"
                )

                bot.register_next_step_handler(msg, process_invited_client_passport_number, data, msg.message_id)

            elif data['where_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите, кем выдан паспорт:"
                )

                bot.register_next_step_handler(msg, process_invited_client_passport_issued_by, data, msg.message_id)
            elif data['when_pasport'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите дату выдачи паспорта (ДД.ММ.ГГГГ):"
                )

                bot.register_next_step_handler(msg, process_invited_client_passport_date, data, msg.message_id)
            elif data['date_of_birth'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите дату рождения (ДД.ММ.ГГГГ):"
                )

                bot.register_next_step_handler(msg, process_invited_client_birth_date, data, msg.message_id)
            elif data['city_birth'] == '':
                msg = bot.send_message(
                    message.chat.id,
                    "Введите город рождения:"
                )

                bot.register_next_step_handler(msg, process_invited_client_birth_city, data, msg.message_id)
            else:
                msg = bot.send_message(
                    message.chat.id,
                    "Введите адрес регистрации по паспорту:"
                )

                bot.register_next_step_handler(msg, process_invited_client_address, data, msg.message_id)
            
            
        except Exception as e:
            print(f"❌ Ошибка при обработке файла: {e}")
            try:
                bot.delete_message(message.chat.id, message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            msg = bot.send_message(
                message.chat.id, 
                "❌ Ошибка при загрузке файла. Попробуйте еще раз:\n\n"
                "Теперь прикрепите фото прописки паспорта (4-5 или 6-7 стр):"
            )
            bot.register_next_step_handler(msg, process_passport_photo_4_5, data, msg.message_id)

    def finalize_registration(bot, user_id, data):
        """Завершение регистрации в зависимости от роли"""
        admin_value = data.get('admin_value', '')
        # Добавляем user_id перед сохранением
        data['user_id'] = str(user_id)
        print(data)
        if len(data['fio'].split())==2:
            data.update({"fio_k": data['fio'].split()[0]+" "+list(data['fio'].split()[1])[0]+"."})
        else:
            data.update({"fio_k": data['fio'].split()[0]+" "+list(data['fio'].split()[1])[0]+"."+list(data['fio'].split()[2])[0]+"."})
        # Сохраняем в БД используя метод save_admin
        try:
            db.save_admin(data)
            print(f"✅ Пользователь {data.get('fio')} сохранен в БД")
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            bot.send_message(user_id, "❌ Ошибка при сохранении данных. Попробуйте позже.")
            return
        
        if admin_value == 'Клиент':
            # Клиент сразу переходит в главное меню
            msg = bot.send_message(user_id, "✅ Регистрация завершена!")
            import time
            time.sleep(1)
            bot.delete_message(msg.chat.id, msg.message_id)
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
            
            # Очищаем временные данные
            if user_id in user_temp_data:
                del user_temp_data[user_id]
        else:
            # ЦПР и Агент ждут подтверждения
            bot.send_message(user_id, "✅ Данные отправлены!\n\n⏳ Ожидайте подтверждения регистрации администратором...")
            
            # Отправка на подтверждение главному администратору
            send_confirmation_request(bot, user_id, data)
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["consent_self_registration_yes", "consent_self_registration_no"])
    @prevent_double_click(timeout=3.0)
    def handle_self_registration_consent(call):
        """Обработка согласия при самостоятельной регистрации"""
        user_id = call.from_user.id
        
        if call.data == "consent_self_registration_no":
            # Отказ от согласия
            if user_id in user_temp_data:
                del user_temp_data[user_id]
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ Вы отказались от обработки персональных данных.\n\n"
                    "Для работы с ботом необходимо дать согласие."
            )
            
            keyboard = types.InlineKeyboardMarkup()
            btn_register = types.InlineKeyboardButton("📝 Зарегистрироваться заново", callback_data="btn_registratsia")
            keyboard.add(btn_register)
            
            bot.send_message(
                call.message.chat.id,
                "Вы можете начать регистрацию заново.",
                reply_markup=keyboard
            )
            return
        
        # Согласие получено
        data = user_temp_data.get(user_id, {})
        
        if not data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Согласие получено!\n\n⏳ Ожидайте подтверждения регистрации администратором..."
        )
        
        # Отправка на подтверждение главному администратору
        send_confirmation_request(bot, user_id, data)
        
        bot.answer_callback_query(call.id, "Данные отправлены на проверку")
    def send_confirmation_request(bot, user_id, data):
        """Отправка запроса на подтверждение главному администратору"""
        keyboard = types.InlineKeyboardMarkup()
        btn_approve = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_reg_{user_id}")
        btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_reg_{user_id}")
        keyboard.add(btn_approve, btn_reject)
        
        confirmation_text = f"""
📝 <b>Новая заявка на регистрацию</b>

👤 ФИО: {data.get('fio', 'Не указано')}
💼 Должность: {data.get('admin_value', 'Не указано')}
📱 Телефон: {data.get('number', 'Не указан')}
🏙 Город: {data.get('city_admin', 'Не указан')}
🆔 User ID: {user_id}
        """
        
        bot.send_message(
            config.MAIN_ADMIN,
            confirmation_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("approve_reg_"))
    @prevent_double_click(timeout=3.0)
    def approve_registration(call):
        """Подтверждение регистрации администратором"""
        user_id_to_approve = int(call.data.replace("approve_reg_", ""))
        data = user_temp_data.get(user_id_to_approve, {})
        
        if not data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        try:
            if 'user_id' not in data:
                data['user_id'] = str(user_id_to_approve)
            if data.get('admin_value') == 'Клиент':
                if 'seria_pasport' not in data or not data['seria_pasport']:
                    data['seria_pasport'] = '0000'
                if 'number_pasport' not in data or not data['number_pasport']:
                    data['number_pasport'] = '000000'
                if 'where_pasport' not in data or not data['where_pasport']:
                    data['where_pasport'] = '-'
                if 'when_pasport' not in data or not data['when_pasport']:
                    data['when_pasport'] = '-'
            # Сохраняем в БД
            db.save_admin(data)
            
            msg2 = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=call.message.text + "\n\n✅ <b>ПОДТВЕРЖДЕНО</b>",
                parse_mode='HTML'
            )
            
            # Уведомляем пользователя
            msg = bot.send_message(
                user_id_to_approve,
                "✅ Ваша регистрация подтверждена!\n\nТеперь вы можете пользоваться ботом."
            )

            # Показываем главное меню СНАЧАЛА
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id_to_approve)

            # Ждем немного
            import time
            time.sleep(0.3)

            # ПОТОМ чистим старые сообщения (уменьшаем count чтобы не удалить меню)
            cleanup_messages(bot, msg.chat.id, msg.message_id, count=3)
            cleanup_messages(bot, msg2.chat.id, msg2.message_id, count=1)
            
        except Exception as e:
            print(f"Ошибка подтверждения регистрации: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при подтверждении", show_alert=True)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_reg_"))
    @prevent_double_click(timeout=3.0)
    def reject_registration(call):
        """Отклонение регистрации администратором"""
        user_id_to_reject = int(call.data.replace("reject_reg_", ""))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=call.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
            parse_mode='HTML'
        )
        cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=2)
        # Уведомляем пользователя
        bot.send_message(
            user_id_to_reject,
            "❌ Ваша регистрация была отклонена администратором.\n\n"
            "Для повторной регистрации используйте /start"
        )
        
        # Очищаем временные данные
        if user_id_to_reject in user_temp_data:
            del user_temp_data[user_id_to_reject]
        
        bot.answer_callback_query(call.id, "❌ Регистрация отклонена")

def cleanup_messages(bot, chat_id, message_id, count):
    """Удаляет последние N сообщений"""
    for i in range(count):
        try:
            bot.delete_message(chat_id, message_id - i)
        except:
            pass


