from telebot import types
import re
import threading
from datetime import datetime, timedelta
from database import (
    DatabaseManager,
    save_client_to_db_with_id_new,
    get_admin_from_db_by_user_id,
    get_client_from_db_by_client_id,
    get_admin_from_db_by_fio
)
from config import ID_CHAT, ID_TOPIC_CLIENT, ID_TOPIC_EXP, TEST
import os
from PIL import Image
from io import BytesIO
from word_utils import create_fio_data_file,  replace_words_in_word, get_next_business_date
import json
import time
from functools import wraps


active_callbacks = {}
callback_lock = threading.Lock()
db = DatabaseManager()

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

def setup_client_agent_handlers(bot, user_temp_data,upload_sessions):
    """Регистрация обработчиков для работы агента с клиентом"""
    def create_back_keyboard(callback_data):
        """Создает клавиатуру с кнопкой Назад"""
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=callback_data))
        return keyboard

    def save_step_state(user_id, step_name, data):
        """Сохраняет состояние текущего шага"""
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        if 'step_history' not in user_temp_data[user_id]:
            user_temp_data[user_id]['step_history'] = []
        
        user_temp_data[user_id]['step_history'].append({
            'step': step_name,
            'data': data.copy() if isinstance(data, dict) else data
        })

    def go_back_step(bot, user_id, chat_id, message_id):
        """Возвращается на предыдущий шаг"""
        if user_id not in user_temp_data or 'step_history' not in user_temp_data[user_id]:
            return False
        
        history = user_temp_data[user_id]['step_history']
        if len(history) < 2:
            return False
        
        # Удаляем текущий шаг
        history.pop()
        # Получаем предыдущий шаг
        prev_step = history[-1]
        
        # Восстанавливаем данные
        if 'contract_data' in user_temp_data[user_id]:
            user_temp_data[user_id]['contract_data'].update(prev_step['data'])
        
        return prev_step['step']
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
    # ========== НАЧАЛО ЗАПОЛНЕНИЯ ДОГОВОРА ==========
    
    @bot.callback_query_handler(func=lambda call: call.data == "start_agent_client_contract")
    @prevent_double_click(timeout=3.0)
    def start_contract_filling(call):
        """Начало заполнения договора агентом для клиента"""
        agent_id = call.from_user.id
        
        # Получаем данные клиента из БД
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT client_user_id FROM client_agent_relationships 
                    WHERE agent_id = %s
                    ORDER BY created_at DESC LIMIT 1
                """, (agent_id,))
                result = cursor.fetchone()
                
                if not result:
                    bot.answer_callback_query(call.id, "❌ Клиент не найден", show_alert=True)
                    return
                
                client_user_id = result[0]

        # Получаем данные агента и клиента
        agent_data = get_admin_from_db_by_user_id(agent_id)
        client_data = get_admin_from_db_by_user_id(client_user_id)
        if not client_data:
            bot.answer_callback_query(call.id, "❌ Данные клиента не найдены", show_alert=True)
            return

        if not agent_data:
            bot.answer_callback_query(call.id, "❌ Данные агента не найдены", show_alert=True)
            return

        # DEBUG: проверяем что достали из БД
        print(f"DEBUG CONTRACT START: Данные из БД:")
        print(f"  - Client user_id: {client_user_id}")
        print(f"  - Client ФИО: {client_data.get('fio')}")
        print(f"  - Client Телефон: {client_data.get('number')}")
        print(f"  - Client Паспорт: {client_data.get('seria_pasport')} {client_data.get('number_pasport')}")
        print(f"  - Agent Город: {agent_data.get('city_admin')}")

        # Инициализируем данные договора
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        try:
            bot.delete_message(client_user_id, user_temp_data[client_user_id]['message_id'])
        except:
            pass
        # ЗАГРУЖАЕМ ВСЕ ДАННЫЕ КЛИЕНТА ИЗ БД (включая паспортные)
        user_temp_data[agent_id]['contract_data'] = {
            'fio': client_data.get('fio', ''),
            'fio_k': client_data.get('fio_k', ''),
            'number': client_data.get('number', ''),
            'city': agent_data.get('city_admin', ''),
            'year': str(datetime.now().year)[-2:],
            'user_id': str(client_user_id),
            'creator_user_id': str(agent_id),
            # ПАСПОРТНЫЕ ДАННЫЕ ИЗ БД КЛИЕНТА
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

        print(f"✅ Загружены ВСЕ данные клиента из БД, включая паспортные")

        # Проверка что данные есть
        if not client_data.get('number'):
            bot.answer_callback_query(call.id, "⚠️ У клиента не указан номер телефона", show_alert=True)
            print(f"WARNING: У клиента {client_user_id} нет номера телефона в БД!")

        if not agent_data.get('city_admin'):
            bot.answer_callback_query(call.id, "⚠️ У агента не указан город", show_alert=True)
            print(f"WARNING: У агента {agent_id} нет города в БД!")

        if not client_data.get('seria_pasport'):
            bot.answer_callback_query(call.id, "⚠️ У клиента не заполнены паспортные данные", show_alert=True)
            print(f"WARNING: У клиента {client_user_id} нет паспортных данных в БД!")

        if agent_data.get('admin_value') == 'Агент':
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="accident_dtp")
            btn2 = types.InlineKeyboardButton("Другое", callback_data=f"otherAccident")
            keyboard.add(btn1)
            keyboard.add(btn2)

            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"📋 Начинаем заполнение договора для клиента\n\n"
                    f"👤 ФИО: {client_data.get('fio', 'не указано')}\n"
                    f"📱 Телефон: {client_data.get('number', 'не указан')}\n"
                    f"🏙 Город: {agent_data.get('city_admin', 'не указан')}\n"
                    f"📄 Паспорт: {client_data.get('seria_pasport', '')} {client_data.get('number_pasport', '')}\n"
                    f"🏠 Адрес: {client_data.get('address', 'не указан')}\n\n"
                    f"Выберите тип обращения\n",
                reply_markup=keyboard
            )
        else:
        # Спрашиваем тип обращения
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="accident_dtp")
            btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="accident_podal_zayavl")
            btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="accident_pit")
            btn4 = types.InlineKeyboardButton("❌ У виновника ДТП нет ОСАГО", callback_data="accident_net_osago")
            
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)

            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"📋 Начинаем заполнение договора для клиента\n\n"
                    f"Выберите тип обращения",
                reply_markup=keyboard
            )
        try:
            keyboard_client = types.InlineKeyboardMarkup()
            keyboard_client.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            msg = bot.send_message(
                int(client_user_id),
                "📄 Агент приступил к заполнению договора.\n\n"
                "После завершения оформления вам поступит запрос на подтверждение данных.",
                reply_markup=keyboard_client
            )
            user_temp_data[agent_id]['contract_data'].update({'message_id': msg.message_id})
        except Exception as e:
            print(f"Ошибка уведомления клиента: {e}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("use_existing_contract_"))
    @prevent_double_click(timeout=3.0)
    def use_existing_contract_handler(call):
        """Использование данных существующего договора для нового"""
        agent_id = call.from_user.id
        old_client_id = call.data.replace("use_existing_contract_", "")
        
        # Получаем данные старого договора
        from database import get_client_from_db_by_client_id
        old_contract = get_client_from_db_by_client_id(old_client_id)
        
        if not old_contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        # Парсим данные
        try:
            contract_data = json.loads(old_contract.get('data_json', '{}'))
            merged_data = {**old_contract, **contract_data}
        except:
            merged_data = old_contract
        
        # Получаем город агента
        agent_data = get_admin_from_db_by_user_id(agent_id)
        
        # Инициализируем данные нового договора с существующими данными
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        
        user_temp_data[agent_id]['contract_data'] = {
            'fio': merged_data.get('fio', ''),
            'number': merged_data.get('number', ''),
            'city': agent_data.get('city_admin', ''),
            'date_of_birth': merged_data.get('date_of_birth', ''),
            'city_birth': merged_data.get('city_birth', ''),
            'seria_pasport': merged_data.get('seria_pasport', ''),
            'number_pasport': merged_data.get('number_pasport', ''),
            'where_pasport': merged_data.get('where_pasport', ''),
            'when_pasport': merged_data.get('when_pasport', ''),
            'index_postal': merged_data.get('index_postal', ''),
            'address': merged_data.get('address', ''),
            'year': str(datetime.now().year)[-2:],
            'fio_k': '',
            'is_repeat': True,  # Флаг что это повторный договор
            'old_client_id': old_client_id
        }
        
        # Получаем client_user_id из старого договора
        client_user_id = merged_data.get('user_id')
        if client_user_id:
            user_temp_data[agent_id]['client_user_id'] = int(client_user_id)
        
        # Спрашиваем тип обращения
        if agent_data.get('admin_value') == 'Агент':
            btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="accident_dtp")
            btn2 = types.InlineKeyboardButton("Другое", callback_data=f"otherAccident")
            keyboard.add(btn1)
            keyboard.add(btn2)
        else:
        # Спрашиваем тип обращения
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="accident_dtp")
            btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="accident_podal_zayavl")
            btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="accident_pit")
            btn4 = types.InlineKeyboardButton("❌ У виновника ДТП Нет ОСАГО", callback_data="accident_net_osago")
            
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)

        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📋 Оформление нового договора для существующего клиента\n\n"
                f"👤 ФИО: {merged_data.get('fio', 'не указано')}\n"
                f"📱 Телефон: {merged_data.get('number', 'не указан')}\n"
                f"🏙 Город: {agent_data.get('city_admin', 'не указан')}\n\n"
                f"Выберите тип обращения",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data=="otherAccident")
    @prevent_double_click(timeout=3.0)
    def handle_otherAccident(call):
        agent_id = call.from_user.id
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="accident_podal_zayavl")
        btn2 = types.InlineKeyboardButton("🕳 После ямы", callback_data="accident_pit")
        btn3 = types.InlineKeyboardButton("❌ У виновника ДТП Нет ОСАГО", callback_data="accident_net_osago")
        btn4 = types.InlineKeyboardButton("◀️ Назад", callback_data="backAccident")

        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Выберите тип обращения",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data=="backAccident")
    @prevent_double_click(timeout=3.0)
    def handle_backAccident(call):
        agent_id = call.from_user.id
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="accident_dtp")
        btn2 = types.InlineKeyboardButton("Другое", callback_data=f"otherAccident")

        keyboard.add(btn1)
        keyboard.add(btn2)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Выберите тип обращения",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("accident_"))
    @prevent_double_click(timeout=3.0)
    def handle_accident_type(call):
        """Обработка выбора типа обращения"""
        agent_id = call.from_user.id
        
        if agent_id in user_temp_data and 'contract_data' in user_temp_data[agent_id]:
            bot.delete_message(user_temp_data[agent_id]['client_user_id'], int(user_temp_data[agent_id]['contract_data']['message_id']))
        
        if call.data == 'accident_dtp':
            user_temp_data[agent_id]['contract_data']['accident'] = "ДТП"
            context = f"Вы попали в ДТП с участием двух и более автомобилей.\n\nСейчас вы находитесь на стадии оформления ДТП.\nЗаявление в страховую компанию ещё не подавали.\n\nПримерные сроки:\n\nПримерная дата первой выплаты от Страховой в случае отказа производить восстановительный ремонт {(datetime.now() + timedelta(days=20)).strftime('%d.%m.%Y')}\n\nПримерная дата завершения дела {(datetime.now() + timedelta(days=280)).strftime('%d.%m.%Y')}"
        elif call.data == 'accident_podal_zayavl':
            user_temp_data[agent_id]['contract_data']['accident'] = "Подал заявление"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nЗаявление в страховую подали самостоятельно на выплату или ремонт.\nПримерная дата завершения дела {(datetime.now() + timedelta(days=280)).strftime('%d.%m.%Y')}"
        elif call.data == 'accident_pit':
            user_temp_data[agent_id]['contract_data']['accident'] = "После ямы"
            context = f"🤖 Вы попали в ДТП по вине дорожных служб (ямы, люки, остатки ограждений и т.д.)"
        elif call.data == 'accident_net_osago':
            user_temp_data[agent_id]['contract_data']['accident'] = "Нет ОСАГО"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nНаходитесь на стадии оформления в ГИБДД.\nДанная ситуация является не страховым случаем.\nКомпенсирует убыток Виновник ДТП.\nПримерная дата завершения дела {(datetime.now() + timedelta(days=90)).strftime('%d.%m.%Y')}"

        
        msg = bot.send_message(
            chat_id=user_temp_data[agent_id]['client_user_id'],
            text=context,
            reply_markup=None
        )
        user_temp_data[agent_id]['contract_data']['message_id'] = msg.message_id

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="ev_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="ev_no")
        btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_accident_choice")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Эвакуатор вызывали?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_accident_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_accident_choice(call):
        """Возврат к выбору типа обращения"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        agent_id = call.from_user.id
        agent_data = get_admin_from_db_by_user_id(agent_id)
        
        if agent_data.get('admin_value') == 'Агент':
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="accident_dtp")
            btn2 = types.InlineKeyboardButton("Другое", callback_data=f"otherAccident")
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        else:
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="accident_dtp")
            btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="accident_podal_zayavl")
            btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="accident_pit")
            btn4 = types.InlineKeyboardButton("❌ У виновника ДТП нет ОСАГО", callback_data="accident_net_osago")
            
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите тип обращения",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["ev_yes", "ev_no"])
    @prevent_double_click(timeout=3.0)
    def handle_evacuator(call):
        """Обработка выбора эвакуатора"""
        agent_id = call.from_user.id
        
        if call.data == "ev_yes":
            user_temp_data[agent_id]['contract_data']['ev'] = "Да"
        elif call.data == "ev_no":
            user_temp_data[agent_id]['contract_data']['ev'] = "Нет"
        
        save_step_state(agent_id, 'evacuator', user_temp_data[agent_id]['contract_data'])
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_agent"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_agent"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_evacuator"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату ДТП:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_evacuator")
    @prevent_double_click(timeout=3.0)
    def back_to_evacuator(call):
        """Возврат к вопросу об эвакуаторе"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        agent_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="ev_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="ev_no")
        btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_accident_choice")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Эвакуатор вызывали?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_date_today_agent", "dtp_date_other_agent"])
    @prevent_double_click(timeout=3.0)
    def handle_dtp_date_choice(call):
        agent_id = call.from_user.id
        
        if call.data == "dtp_date_today_agent":
            # Красноярское время
            from datetime import datetime
            import pytz
            krasnoyarsk_tz = pytz.timezone('Asia/Krasnoyarsk')
            date_dtp = datetime.now(krasnoyarsk_tz).strftime("%d.%m.%Y")
            user_temp_data[agent_id]['contract_data']['date_dtp'] = date_dtp
            
            # Продолжить к следующему шагу (время ДТП)
            keyboard = create_back_keyboard("back_to_dtp_date_choice")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Дата ДТП: {date_dtp}\n\nВведите время ДТП (ЧЧ:ММ):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(call.message, process_dtp_time, agent_id, call.message.message_id)
            
        elif call.data == "dtp_date_other_agent":
            keyboard = create_back_keyboard("back_to_dtp_date_choice")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДТП (ДД.ММ.ГГГГ):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(call.message, process_dtp_date, agent_id, call.message.message_id)
    
    def process_dtp_date(message, agent_id, prev_msg_id):
        """Обработка даты ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
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
                keyboard = create_back_keyboard("back_to_evacuator")
                msg = bot.send_message(message.chat.id, "❌ Дата ДТП не может быть в будущем!\nВведите корректную дату ДТП:", reply_markup=keyboard)
                bot.register_next_step_handler(msg, process_dtp_date, agent_id, msg.message_id)
                return
            
            if input_date < three_years_ago:
                keyboard = create_back_keyboard("back_to_evacuator")
                msg = bot.send_message(message.chat.id, "❌ Прошло более трех лет!\nВведите корректную дату ДТП:", reply_markup=keyboard)
                bot.register_next_step_handler(msg, process_dtp_date, agent_id, msg.message_id)
                return
            
            user_temp_data[agent_id]['contract_data']['date_dtp'] = date_text
            save_step_state(agent_id, 'dtp_date', user_temp_data[agent_id]['contract_data'])
            
            keyboard = create_back_keyboard("back_to_dtp_date_choice")
            msg = bot.send_message(message.chat.id, "Введите время ДТП (ЧЧ:ММ):", reply_markup=keyboard)
            bot.register_next_step_handler(msg, process_dtp_time, agent_id, msg.message_id)
            
        except ValueError:
            keyboard = create_back_keyboard("back_to_evacuator")
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату ДТП в формате ДД.ММ.ГГГГ:", reply_markup=keyboard)
            bot.register_next_step_handler(msg, process_dtp_date, agent_id, msg.message_id)
            return
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dtp_date_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_dtp_date_choice(call):
        """Возврат к выбору даты ДТП"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_agent"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_agent"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_evacuator"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату ДТП:",
            reply_markup=keyboard
        )
    def process_dtp_time(message, agent_id, prev_msg_id):
        """Обработка времени ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        time_text = message.text.strip()
        
        if not re.match(r'^\d{2}:\d{2}$', time_text):
            keyboard = create_back_keyboard("back_to_dtp_date_choice")
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат времени. Введите в формате ЧЧ:ММ:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_dtp_time, agent_id, msg.message_id)
            return
        
        user_temp_data[agent_id]['contract_data']['time_dtp'] = time_text
        save_step_state(agent_id, 'dtp_time', user_temp_data[agent_id]['contract_data'])
        
        keyboard = create_back_keyboard("back_to_dtp_time")
        msg = bot.send_message(message.chat.id, "Введите адрес ДТП:", reply_markup=keyboard)
        bot.register_next_step_handler(msg, process_dtp_address, agent_id, msg.message_id)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dtp_time")
    @prevent_double_click(timeout=3.0)
    def back_to_dtp_time(call):
        """Возврат к вводу времени ДТП"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_back_keyboard("back_to_dtp_date_choice")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите время ДТП (ЧЧ:ММ):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_dtp_time, agent_id, msg.message_id)

    def process_dtp_address(message, agent_id, prev_msg_id):
        """Обработка адреса ДТП"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        user_temp_data[agent_id]['contract_data']['address_dtp'] = message.text.strip()
        save_step_state(agent_id, 'dtp_address', user_temp_data[agent_id]['contract_data'])
        
        if user_temp_data[agent_id]['contract_data']['ev'] == 'Да':
            keyboard = create_back_keyboard("back_to_dtp_address")
            msg = bot.send_message(message.chat.id, "Введите адрес местонахождения транспортного средства, где будет произведена оценка ущерба.", reply_markup=keyboard)
            bot.register_next_step_handler(msg, process_dtp_address_park, agent_id, msg.message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd"))
            keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_address"))
            msg = bot.send_message(message.chat.id, "Выберите документ фиксации ДТП", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dtp_address")
    @prevent_double_click(timeout=3.0)
    def back_to_dtp_address(call):
        """Возврат к вводу адреса ДТП"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_back_keyboard("back_to_dtp_time")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес ДТП:",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_dtp_address, agent_id, msg.message_id)

    def process_dtp_address_park(message, agent_id, prev_msg_id):
        """Обработка адреса местоположения авто"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        user_temp_data[agent_id]['contract_data']['address_park'] = message.text.strip()
        save_step_state(agent_id, 'address_park', user_temp_data[agent_id]['contract_data'])

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd"))
        keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_park"))
        msg = bot.send_message(message.chat.id, "Выберите документ фиксации ДТП", reply_markup=keyboard)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_address_park")
    @prevent_double_click(timeout=3.0)
    def back_to_address_park(call):
        """Возврат к вводу адреса стоянки"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_back_keyboard("back_to_dtp_address")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес местонахождения транспортного средства, где будет произведена оценка ущерба.",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_dtp_address_park, agent_id, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_gibdd", "dtp_evro"])
    @prevent_double_click(timeout=3.0)
    def handle_dtp_gibdd_evro_agent(call):
        agent_id = call.from_user.id
        
        if call.data == "dtp_gibdd":
            user_temp_data[agent_id]['contract_data']['who_dtp'] = "По форме ГИБДД"
        elif call.data == "dtp_evro":
            user_temp_data[agent_id]['contract_data']['who_dtp'] = "Евро-протокол"

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # СРАЗУ ПЕРЕХОДИМ К СБОРУ ДАННЫХ ОБ АВТОМОБИЛЕ (без показа итоговых данных)
        contract_data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_marks")
        msg = bot.send_message(
            call.message.chat.id,
            "Введите марку и модель авто клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, marks, contract_data, msg.message_id)
       
    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_contract_"))
    @prevent_double_click(timeout=3.0)
    def confirm_contract_by_client(call):
        """Подтверждение данных клиентом"""
        agent_id = int(call.data.replace("confirm_contract_", ""))
        client_id = call.from_user.id
        if agent_id not in user_temp_data or 'contract_data' not in user_temp_data[agent_id]:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные договора не найдены", show_alert=True)
            return
        contract_data = user_temp_data[agent_id]['contract_data']
        fields_to_remove = [
            'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
            'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
            'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back',
            'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
        ]
        
        for field in fields_to_remove:
            contract_data.pop(field, None)
        
        # СОХРАНЯЕМ В БД И ПОЛУЧАЕМ client_id
        contract_data['status'] = 'Оформлен договор'
        try:
            client_contract_id, updated_data = save_client_to_db_with_id_new(contract_data)
            contract_data['user_id'] = str(user_temp_data[agent_id].get('client_user_id'))
            contract_data.update(updated_data)
            contract_data['client_id'] = client_contract_id
            user_temp_data[agent_id]['contract_data'] = contract_data
            print(contract_data)
            print(f"Договор сохранен с client_id: {client_contract_id}")
            
            # ФОРМИРУЕМ ОБЛОЖКУ ДЕЛА
            create_fio_data_file(contract_data)
            if contract_data['accident'] == 'ДТП' or contract_data['accident'] == 'Подал заявление':
                replace_words_in_word(
                    ["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                    "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}", "{{ NКлиента }}", "{{ ФИО }}",
                    "{{ Страховая }}", "{{ винФИО }}"],
                    [str(contract_data["date_dtp"]), str(contract_data["time_dtp"]), str(contract_data["address_dtp"]), 
                    str(contract_data["marks"]), str(contract_data["car_number"]),
                    str(contract_data['year']), str(client_contract_id), str(contract_data["fio"]), 
                    str(contract_data["insurance"]), str(contract_data["fio_culp"])],
                    "Шаблоны/1. ДТП/1. На ремонт/1. Обложка дела.docx",
                    f"clients/{client_contract_id}/Документы/Обложка дела.docx"
                )
            elif contract_data['accident'] == 'Нет ОСАГО':
                replace_words_in_word(
                    ["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                    "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}", "{{ NКлиента }}", "{{ ФИО }}",
                    "{{ винФИО }}"],
                    [str(contract_data["date_dtp"]), str(contract_data["time_dtp"]), str(contract_data["address_dtp"]), 
                    str(contract_data["marks"]), str(contract_data["car_number"]),
                    str(contract_data['year']), str(client_contract_id), str(contract_data["fio"]), 
                    str(contract_data["fio_culp"])],
                    "Шаблоны/3. Деликт без ОСАГО/Деликт (без ОСАГО) 1. Обложка дела.docx",
                    f"clients/{client_contract_id}/Документы/Обложка дела.docx"
                )
            else:
                replace_words_in_word(
                    ["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                    "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}", "{{ NКлиента }}", "{{ ФИО }}",
                    "{{ Телефон }}", "{{ Город }}"],
                    [str(contract_data["date_dtp"]), str(contract_data["time_dtp"]), str(contract_data["address_dtp"]), 
                    str(contract_data["marks"]), str(contract_data["car_number"]),
                    str(contract_data['year']), str(client_contract_id), str(contract_data["fio"]), 
                    str(contract_data["number"]), str(contract_data["city"])],
                    "Шаблоны/2. Яма/Яма 1. Обложка дела.docx",
                    f"clients/{client_contract_id}/Документы/Обложка дела.docx"
                )
            
            # ФОРМИРУЕМ ЮР ДОГОВОР
            replace_words_in_word(
                ["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", "{{ Дата }}", "{{ ФИО }}", 
                "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
                "{{ Паспорт_когда }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Дата_ДТП }}", 
                "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                [str(contract_data['year']), str(client_contract_id), str(contract_data["city"]), 
                str(datetime.now().strftime("%d.%m.%Y")), str(contract_data["fio"]), 
                str(contract_data["date_of_birth"]), str(contract_data["city_birth"]), str(contract_data["seria_pasport"]), 
                str(contract_data["number_pasport"]), str(contract_data["where_pasport"]),
                str(contract_data["when_pasport"]), str(contract_data["index_postal"]), 
                str(contract_data["address"]), str(contract_data["date_dtp"]), 
                str(contract_data["time_dtp"]), str(contract_data["address_dtp"]), 
                str(contract_data['fio_k'])],
                "Шаблоны/1. ДТП/1. На ремонт/2. Юр договор.docx",
                f"clients/{client_contract_id}/Документы/Юр договор.docx"
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
            # Копируем паспортные данные
            import shutil
            import os

            fio_folder = contract_data.get('fio', '')
            source_folder = f"admins_info/{fio_folder}"
            destination_folder = f"clients/{client_contract_id}/Документы"

            files_to_copy = []

            try:
                if os.path.exists(source_folder):
                    all_files = os.listdir(source_folder)
                    
                    passport_files = [f for f in all_files if f.startswith("Паспорт_")]
                    if passport_files:
                        files_to_copy.extend(passport_files)
                    
                    propiska_files = [f for f in all_files if f.startswith("Прописка")]
                    if propiska_files:
                        files_to_copy.extend(propiska_files)
                    
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
            
            # Обновляем связь клиент-агент
            client_user_id = client_id
            if client_user_id:
                from database import update_client_agent_contract_link
                update_client_agent_contract_link(client_user_id, client_contract_id)
                print(f"✅ Связь обновлена: client={client_user_id}, contract={client_contract_id}")
            else:
                print(f"⚠️ ОШИБКА: client_user_id не найден")
                
        except Exception as e:
            print(f"Ошибка сохранения в БД: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(agent_id, "❌ Ошибка сохранения договора. Попробуйте снова.")
            return
        try:
            bot.delete_message(call.from_user.id, user_temp_data[agent_id]['contract_data']['message_id'])
        except:
            pass
        # Уведомляем агента
        msg = bot.send_message(
            chat_id=agent_id,
            text="✅ Данные подтверждены! Обложка дела и юр договор сформированы."
        )
        print(user_temp_data)
        user_temp_data[agent_id]['contract_data']['message_id'] = msg.message_id
        
        # Спрашиваем про доверенность
        keyboard = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("1", callback_data=f"not_dov_yes_{agent_id}")
        btn_no = types.InlineKeyboardButton("2", callback_data=f"not_dov_no_{agent_id}")
        btn_no2 = types.InlineKeyboardButton("3", callback_data=f"not_dov_no2_{agent_id}")
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
        user_temp_data[agent_id]['contract_data']['message_id2'] = msg.message_id

    @bot.callback_query_handler(func=lambda call: call.data.startswith("not_dov_"))
    @prevent_double_click(timeout=3.0)
    def confirm_not_dov_yes(call):
        """Подтверждение этапа доверенности"""
        if "not_dov_yes_" in call.data:
            agent_id = int(call.data.replace("not_dov_yes_", ""))
            print(user_temp_data)
            print(call.data)
            print(call.from_user.id)
            try:
                if 'contract_data' in user_temp_data[agent_id]:
                    user_temp_data[agent_id]['contract_data']['sobstvenik'] = 'С начала'
                    contract_data = user_temp_data[agent_id]['contract_data']
                else:
                    user_temp_data[agent_id]['sobstvenik'] = 'С начала'
                    user_temp_data[agent_id]['contract_data'] = user_temp_data[agent_id]
                    contract_data = user_temp_data[agent_id]
            except Exception as e:
                print(1)
                user_temp_data[agent_id] = user_temp_data[call.from_user.id]
                user_temp_data[agent_id]['contract_data']['sobstvenik'] = 'С начала'
                contract_data = user_temp_data[agent_id]['contract_data']

            context = '✅ Клиент подготовит нотариальную доверенность с начала'
        elif "not_dov_no_" in call.data:
            agent_id = int(call.data.replace("not_dov_no_", ""))

            try:
                if 'contract_data' in user_temp_data[agent_id]:
                    user_temp_data[agent_id]['contract_data']['sobstvenik'] = 'После заявления в страховую'
                    contract_data = user_temp_data[agent_id]['contract_data']
                else:
                    user_temp_data[agent_id]['sobstvenik'] = 'После заявления в страховую'
                    user_temp_data[agent_id]['contract_data'] = user_temp_data[agent_id]
                    contract_data = user_temp_data[agent_id]
            except Exception as e:
                print(1)
                user_temp_data[agent_id] = user_temp_data[call.from_user.id]
                user_temp_data[agent_id]['contract_data']['sobstvenik'] = 'После заявления в страховую'
                contract_data = user_temp_data[agent_id]['contract_data']
            context = '✅ Клиент подготовит нотариальную доверенность перед дополнительным осмотром'
        else:
            agent_id = int(call.data.replace("not_dov_no2_", ""))
            
            try:
                if 'contract_data' in user_temp_data[agent_id]:
                    user_temp_data[agent_id]['contract_data']['sobstvenik'] = 'После ответа от страховой'
                    contract_data = user_temp_data[agent_id]['contract_data']
                else:
                    user_temp_data[agent_id]['sobstvenik'] = 'После ответа от страховой'
                    user_temp_data[agent_id]['contract_data'] = user_temp_data[agent_id]
                    contract_data = user_temp_data[agent_id]
            except Exception as e:
                print(1)
                user_temp_data[agent_id] = user_temp_data[call.from_user.id]
                user_temp_data[agent_id]['contract_data']['sobstvenik'] = 'После ответа от страховой'
                contract_data = user_temp_data[agent_id]['contract_data']
            context = '✅ Клиент подготовит нотариальную доверенность после получения ответа от страховой'

        fields_to_remove = [
            'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
            'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
            'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back', 'step', 'data', 'search_fio', 'add_client_mode'
            'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
        ]
        
        for field in fields_to_remove:
            contract_data.pop(field, None)

        client_id = call.from_user.id
        try:
            bot.delete_message(call.from_user.id, user_temp_data[agent_id]['contract_data']['message_id2'])
        except:
            pass
        try:
            msg = bot.edit_message_text(
                chat_id=agent_id,
                message_id=user_temp_data[agent_id]['contract_data']['message_id'],
                text=context
            )
        except:
            print(2)
        
        
        try:
            bot.delete_message(agent_id, msg.message_id)
        except:
            pass
        
        # Отправляем клиенту юр договор
        send_legal_contract_to_client(bot, client_id, agent_id, contract_data)
        
        bot.answer_callback_query(call.id, "Ответ сохранен")
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("decline_contract_"))
    @prevent_double_click(timeout=3.0)
    def handle_decline_contract(call):
        """Обработка отклонения данных клиентом"""
        agent_id = int(call.data.replace("decline_contract_", ""))
        client_id = call.from_user.id
        
        # Уведомляем клиента
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Вы отклонили данные.\n\nАгент получил уведомление и сможет отредактировать данные.",
            parse_mode='HTML'
        )
        
        # Получаем client_id договора из user_temp_data агента
        contract_client_id = None
        if agent_id in user_temp_data and 'contract_data' in user_temp_data[agent_id]:
            contract_data = user_temp_data[agent_id]['contract_data']
            
            # Сохраняем данные для редактирования
            user_temp_data[agent_id]['editing_contract'] = {
                'data': contract_data.copy(),
                'client_user_id': client_id
            }
            
            # Находим client_id из БД если есть
            if 'client_id' in contract_data:
                contract_client_id = contract_data['client_id']
        
        # Отправляем агенту уведомление с кнопкой редактирования
        try:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("✏️ Редактировать данные", callback_data=f"start_edit_contract"))
            keyboard.add(types.InlineKeyboardButton("🔄 Заполнить заново", callback_data="start_agent_client_contract"))
            
            bot.send_message(
                agent_id,
                "❌ Клиент отклонил данные договора.\n\n"
                "Вы можете отредактировать существующие данные или заполнить договор заново.",
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Ошибка уведомления агента: {e}")
    @bot.callback_query_handler(func=lambda call: call.data == "start_edit_contract")
    @prevent_double_click(timeout=3.0)
    def start_edit_contract(call):
        """Начало редактирования отклоненного договора"""
        agent_id = call.from_user.id
        
        if agent_id not in user_temp_data or 'editing_contract' not in user_temp_data[agent_id]:
            bot.answer_callback_query(call.id, "❌ Данные для редактирования не найдены", show_alert=True)
            return
        
        # Показываем меню редактирования
        show_contract_edit_menu(bot, call.message.chat.id, call.message.message_id, agent_id, user_temp_data)


    def show_contract_edit_menu(bot, chat_id, message_id, agent_id, user_temp_data):
        """Показать меню редактирования договора"""
        if agent_id not in user_temp_data or 'editing_contract' not in user_temp_data[agent_id]:
            bot.send_message(chat_id, "❌ Ошибка: данные для редактирования не найдены")
            return
        
        contract_data = user_temp_data[agent_id]['editing_contract']['data']
        
        # Формируем текст с текущими данными
        text = "📋 <b>Текущие данные договора:</b>\n\n"
        
        # Персональные данные
        text += "<b>Персональные данные:</b>\n"
        text += f"👤 ФИО: {contract_data.get('fio', 'не указано')}\n"
        text += f"📱 Номер телефона: {contract_data.get('number', 'не указан')}\n"
        text += f"📅 Дата рождения: {contract_data.get('date_of_birth', 'не указана')}\n"
        text += f"🏙 Место рождения: {contract_data.get('city_birth', 'не указано')}\n"
        text += f"📄 Серия паспорта: {contract_data.get('seria_pasport', 'не указана')}\n"
        text += f"📄 Номер паспорта: {contract_data.get('number_pasport', 'не указан')}\n"
        text += f"📍 Кем выдан: {contract_data.get('where_pasport', 'не указано')}\n"
        text += f"📅 Дата выдачи: {contract_data.get('when_pasport', 'не указана')}\n"
        text += f"📮 Индекс: {contract_data.get('index_postal', 'не указан')}\n"
        text += f"🏠 Адрес: {contract_data.get('address', 'не указан')}\n\n"
        
        # Данные о ДТП
        text += "<b>Данные о ДТП:</b>\n"
        text += f"🚗 Дата ДТП: {contract_data.get('date_dtp', 'не указана')}\n"
        text += f"⏰ Время ДТП: {contract_data.get('time_dtp', 'не указано')}\n"
        text += f"📍 Адрес ДТП: {contract_data.get('address_dtp', 'не указан')}\n"
        text += f"🚗 Фиксация ДТП: {contract_data.get('who_dtp', 'не указан')}\n\n"
        
        # Автомобиль клиента
        text += "<b>Автомобиль клиента:</b>\n"
        text += f"🚙 Марка/модель: {contract_data.get('marks', 'не указано')}\n"
        text += f"🔢 Номер авто: {contract_data.get('car_number', 'не указан')}\n"
        text += f"📅 Год выпуска: {contract_data.get('year_auto', 'не указан')}\n\n"
        
        # Страховая компания
        text += "<b>Страховая компания:</b>\n"
        text += f"🏢 Название: {contract_data.get('insurance', 'не указано')}\n"
        text += f"📋 Серия полиса: {contract_data.get('seria_insurance', 'не указана')}\n"
        text += f"📋 Номер полиса: {contract_data.get('number_insurance', 'не указан')}\n"
        text += f"📅 Дата полиса: {contract_data.get('date_insurance', 'не указана')}\n\n"
        
        # Виновник ДТП
        text += "<b>Виновник ДТП:</b>\n"
        text += f"👤 ФИО виновника: {contract_data.get('fio_culp', 'не указано')}\n"
        text += f"🚙 Марка/модель: {contract_data.get('marks_culp', 'не указано')}\n"
        text += f"🔢 Номер авто: {contract_data.get('number_auto_culp', 'не указан')}\n\n"
        
        text += "Выберите поле для редактирования:"
        
        # Создаем клавиатуру с кнопками редактирования
        keyboard = types.InlineKeyboardMarkup()
        
        # Персональные данные
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО", callback_data="edit_field_fio"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер телефона", callback_data="edit_field_number"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата рождения", callback_data="edit_field_date_of_birth"))
        keyboard.add(types.InlineKeyboardButton("✏️ Место рождения", callback_data="edit_field_city_birth"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия паспорта", callback_data="edit_field_seria_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер паспорта", callback_data="edit_field_number_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Кем выдан паспорт", callback_data="edit_field_where_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата выдачи паспорта", callback_data="edit_field_when_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Индекс", callback_data="edit_field_index_postal"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес", callback_data="edit_field_address"))
        
        # Данные о ДТП
        keyboard.add(types.InlineKeyboardButton("✏️ Дата ДТП", callback_data="edit_field_date_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Время ДТП", callback_data="edit_field_time_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес ДТП", callback_data="edit_field_address_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Фиксация ДТП", callback_data="edit_field_who_dtp"))
        
        # Автомобиль клиента
        keyboard.add(types.InlineKeyboardButton("✏️ Марка/модель авто", callback_data="edit_field_marks"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер авто", callback_data="edit_field_car_number"))
        keyboard.add(types.InlineKeyboardButton("✏️ Год выпуска", callback_data="edit_field_year_auto"))
        
        # Страховая компания
        keyboard.add(types.InlineKeyboardButton("✏️ Название страховой", callback_data="edit_field_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия полиса", callback_data="edit_field_seria_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер полиса", callback_data="edit_field_number_insurance"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата полиса", callback_data="edit_field_date_insurance"))
        
        # Виновник ДТП
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО виновника", callback_data="edit_field_fio_culp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Марка/модель виновника", callback_data="edit_field_marks_culp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер авто виновника", callback_data="edit_field_number_auto_culp"))
        
        # Кнопки действий
        keyboard.add(types.InlineKeyboardButton("✅ Отправить на подтверждение", callback_data="submit_edited_contract"))
        keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_edit_contract"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_field_"))
    @prevent_double_click(timeout=3.0)
    def handle_field_edit(call):
        """Начало редактирования конкретного поля"""
        agent_id = call.from_user.id
        field = call.data.replace("edit_field_", "")
        
        if agent_id not in user_temp_data or 'editing_contract' not in user_temp_data[agent_id]:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        # Сохраняем какое поле редактируем
        user_temp_data[agent_id]['editing_field'] = field
        
        # Названия полей для отображения
        field_names = {
            # Персональные данные
            'fio': 'ФИО (Иванов Иван Иванович)',
            'number': 'Номер телефона (+79123456789)',
            'date_of_birth': 'Дата рождения (ДД.ММ.ГГГГ)',
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
        current_value = user_temp_data[agent_id]['editing_contract']['data'].get(field, 'не указано')
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✏️ Редактирование поля: <b>{field_display}</b>\n\n"
                f"Текущее значение: <code>{current_value}</code>\n\n"
                f"Введите новое значение:",
            parse_mode='HTML'
        )
        
        bot.register_next_step_handler(call.message, process_field_edit, agent_id, call.message.message_id, field)


    def process_field_edit(message, agent_id, prev_msg_id, field):
        """Обработка нового значения поля"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if agent_id not in user_temp_data or 'editing_contract' not in user_temp_data[agent_id]:
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
            bot.register_next_step_handler(msg, process_field_edit, agent_id, msg.message_id, field)
            return
        
        # Сохраняем новое значение
        user_temp_data[agent_id]['editing_contract']['data'][field] = new_value
        
        # Возвращаемся в меню редактирования
        msg = bot.send_message(message.chat.id, f"✅ Поле обновлено!")
        show_contract_edit_menu(bot, message.chat.id, msg.message_id, agent_id, user_temp_data)


    @bot.callback_query_handler(func=lambda call: call.data == "submit_edited_contract")
    @prevent_double_click(timeout=3.0)
    def submit_edited_contract(call):
        """Отправка отредактированного договора на подтверждение клиенту"""
        agent_id = call.from_user.id
        
        if agent_id not in user_temp_data or 'editing_contract' not in user_temp_data[agent_id]:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        contract_data = user_temp_data[agent_id]['editing_contract']['data']
        client_user_id = user_temp_data[agent_id]['editing_contract']['client_user_id']
        
        # Обновляем данные в contract_data основного процесса
        if 'contract_data' in user_temp_data[agent_id]:
            user_temp_data[agent_id]['contract_data'].update(contract_data)
        else:
            user_temp_data[agent_id]['contract_data'] = contract_data
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Данные обновлены и отправлены клиенту на подтверждение!"
        )
        user_temp_data[agent_id]['contract_data']['message_id'] = msg.message_id
        # Отправляем клиенту обновленные данные на подтверждение
        if client_user_id:
            try:
                text = "<b>Персональные данные:</b>\n"
                text += f"👤 ФИО: {contract_data.get('fio', 'не указано')}\n"
                text += f"📱 Номер телефона: {contract_data.get('number', 'не указан')}\n"
                text += f"📅 Дата рождения: {contract_data.get('date_of_birth', 'не указана')}\n"
                text += f"🏙 Место рождения: {contract_data.get('city_birth', 'не указано')}\n"
                text += f"📄 Серия паспорта: {contract_data.get('seria_pasport', 'не указана')}\n"
                text += f"📄 Номер паспорта: {contract_data.get('number_pasport', 'не указан')}\n"
                text += f"📍 Кем выдан: {contract_data.get('where_pasport', 'не указано')}\n"
                text += f"📅 Дата выдачи: {contract_data.get('when_pasport', 'не указана')}\n"
                text += f"📮 Индекс: {contract_data.get('index_postal', 'не указан')}\n"
                text += f"🏠 Адрес: {contract_data.get('address', 'не указан')}\n\n"
                
                # Данные о ДТП
                text += "<b>Данные о ДТП:</b>\n"
                text += f"🚗 Дата ДТП: {contract_data.get('date_dtp', 'не указана')}\n"
                text += f"⏰ Время ДТП: {contract_data.get('time_dtp', 'не указано')}\n"
                text += f"📍 Адрес ДТП: {contract_data.get('address_dtp', 'не указан')}\n"
                text += f"🚗 Фиксация ДТП: {contract_data.get('who_dtp', 'не указан')}\n\n"
                
                # Автомобиль клиента
                text += "<b>Автомобиль клиента:</b>\n"
                text += f"🚙 Марка/модель: {contract_data.get('marks', 'не указано')}\n"
                text += f"🔢 Номер авто: {contract_data.get('car_number', 'не указан')}\n"
                text += f"📅 Год выпуска: {contract_data.get('year_auto', 'не указан')}\n\n"
                
                # Страховая компания
                text += "<b>Страховая компания:</b>\n"
                text += f"🏢 Название: {contract_data.get('insurance', 'не указано')}\n"
                text += f"📋 Серия полиса: {contract_data.get('seria_insurance', 'не указана')}\n"
                text += f"📋 Номер полиса: {contract_data.get('number_insurance', 'не указан')}\n"
                text += f"📅 Дата полиса: {contract_data.get('date_insurance', 'не указана')}\n\n"
                
                # Виновник ДТП
                text += "<b>Виновник ДТП:</b>\n"
                text += f"👤 ФИО виновника: {contract_data.get('fio_culp', 'не указано')}\n"
                text += f"🚙 Марка/модель: {contract_data.get('marks_culp', 'не указано')}\n"
                text += f"🔢 Номер авто: {contract_data.get('number_auto_culp', 'не указан')}\n\n"
                
                keyboard = types.InlineKeyboardMarkup()
                btn_confirm = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_contract_{agent_id}")
                btn_decline = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_contract_{agent_id}")
                keyboard.add(btn_confirm)
                keyboard.add(btn_decline)
                
                bot.send_message(client_user_id, text, parse_mode='HTML', reply_markup=keyboard)
                
            except Exception as e:
                print(f"Ошибка отправки клиенту: {e}")
        
        # Очищаем временные данные редактирования
        if 'editing_contract' in user_temp_data[agent_id]:
            del user_temp_data[agent_id]['editing_contract']
        if 'editing_field' in user_temp_data[agent_id]:
            del user_temp_data[agent_id]['editing_field']
        


    @bot.callback_query_handler(func=lambda call: call.data == "cancel_edit_contract")
    @prevent_double_click(timeout=3.0)
    def cancel_edit_contract(call):
        """Отмена редактирования договора"""
        agent_id = call.from_user.id
        
        # Очищаем временные данные
        if agent_id in user_temp_data:
            if 'editing_contract' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['editing_contract']
            if 'editing_field' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['editing_field']
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Редактирование отменено"
        )
        
        # Возвращаемся в главное меню
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, agent_id)
    
    
    
    def send_legal_contract_to_client(bot, client_id, agent_id, contract_data):
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

        # Отправляем документ
        try:
            with open(document_path, 'rb') as document_file:
                bot.send_document(
                    client_id, 
                    document_file,
                    caption="📄 Юридический договор"
                )
        except Exception as e:
            print(f"Ошибка отправки документа: {e}")
            bot.send_message(client_id, "❌ Ошибка при формировании документа")
            return
        
        # Отправляем текст с кнопкой
        keyboard = types.InlineKeyboardMarkup()
        btn_sign = types.InlineKeyboardButton("✍️ Подписать Юр договор", callback_data=f"sign_legal_contract_{agent_id}")
        keyboard.add(btn_sign)
        try:
            bot.delete_message(client_id, user_temp_data[agent_id]['contract_data']['message_id'])
        except:
            pass

        bot.send_message(client_id, contract_text, parse_mode='HTML', reply_markup=keyboard)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("sign_legal_contract_"))
    @prevent_double_click(timeout=3.0)
    def sign_legal_contract(call):
        """Подписание юридического договора клиентом"""

        agent_id = int(call.data.replace("sign_legal_contract_", ""))
        client_id = call.from_user.id

        msg = bot.send_message(
            chat_id=agent_id,
            text="✅ Договор подписан!"
        )
        
        contract_data = user_temp_data.get(agent_id, {}).get('contract_data', {})
        accident_type = user_temp_data[agent_id]['contract_data']['accident']

        # Обновляем admin_value клиента с "Клиент_агент" на "Клиент"
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE admins 
                        SET admin_value = 'Клиент'
                        WHERE user_id = %s::text AND admin_value = 'Клиент_агент'
                    """, (client_id,))
                    conn.commit()
                    print(f"DEBUG: admin_value обновлен для клиента {client_id}")
        except Exception as e:
            print(f"Ошибка обновления admin_value: {e}")
        try:
            
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Обновляем связь с contract_id
                    cursor.execute("""
                        UPDATE client_agent_relationships 
                        SET client_contract_id = %s
                        WHERE agent_id = %s AND client_user_id = %s
                    """, (contract_data.get('client_id'), agent_id, client_id))
                    conn.commit()
                    print(f"DEBUG: Связь client_agent обновлена для contract_id {contract_data.get('client_id')}")
        except Exception as e:
            print(f"Ошибка обновления связи client_agent: {e}")
        # Возвращаем клиента в главное меню
        try:
            cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=5)
        except:
            pass
        
        # Проверяем тип обращения
        if accident_type == "ДТП":

            # Уведомляем агента о составлении заявления
            cleanup_messages(bot, agent_id, msg.message_id, count=5)

            msg = bot.send_message(
                agent_id,
                "✅ Клиент подписал договор!\nДоговор успешно сформирован.\n\nНапомните Клиенту:\n1. Подготовить нотариальную доверенность.\n\n2. Оплатить юридические услуги в срок не позднее 10 дней с момента получения ответа от страховой компании на заявление.\n\n3. Прислать квитанции или иные подтверждающие документы после получения страхового возмещения.\n\nНа этом этап работы с клиентом завершён.\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения",
                parse_mode='HTML',
                reply_markup = None
            )
            
            bot.register_next_step_handler(msg, process_driver_license_front_agent, agent_id, contract_data, msg.message_id)
            bot.answer_callback_query(call.id, "Договор подписан!")

        
        elif accident_type == "После ямы":
            cleanup_messages(bot, agent_id, msg.message_id, count=5)
            msg = bot.send_message(
                agent_id,
                "✅ Клиент подписал договор!\nДоговор успешно сформирован.\n\nНапомните Клиенту:\n1. Подготовить нотариальную доверенность.\n\n2. Оплатить юридические услуги\n\nНа этом этап работы с клиентом завершён.\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения",
                parse_mode='HTML',
                reply_markup = None
            )
            
            bot.register_next_step_handler(msg, process_driver_license_front_agent, agent_id, contract_data, msg.message_id)
            bot.answer_callback_query(call.id, "Договор подписан!")
            

        
        elif accident_type =="Подал заявление":
            cleanup_messages(bot, agent_id, msg.message_id, count=5)

            msg = bot.send_message(
                agent_id,
                "✅ Клиент подписал договор!\nДоговор успешно сформирован.\n\nНапомните Клиенту:\n1. Подготовить нотариальную доверенность.\n\n2. Оплатить юридические услуги в срок не позднее 10 дней с момента получения ответа от страховой компании на заявление.\n\n3. Прислать квитанции или иные подтверждающие документы после получения страхового возмещения.\n\nНа этом этап работы с клиентом завершён.\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения",
                parse_mode='HTML',
                reply_markup = None
            )
            
            bot.register_next_step_handler(msg, process_driver_license_front_agent, agent_id, contract_data, msg.message_id)
            bot.answer_callback_query(call.id, "Договор подписан!")

        elif accident_type == "Нет ОСАГО":
            cleanup_messages(bot, agent_id, msg.message_id, count=5)

            msg = bot.send_message(
                agent_id,
                "✅ Клиент подписал договор!\nДоговор успешно сформирован.\n\nНапомните Клиенту:\n1. Подготовить нотариальную доверенность.\n\n2. Оплатить юридические услуги\n\nНа этом этап работы с клиентом завершён.\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения",
                parse_mode='HTML',
                reply_markup = None
            )
            
            bot.register_next_step_handler(msg, process_driver_license_front_agent, agent_id, contract_data, msg.message_id)
            bot.answer_callback_query(call.id, "Договор подписан!")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("dtp_continue_documents_"))
    @prevent_double_click(timeout=3.0)
    def dtp_continue_documents(call):
        """Продолжение загрузки документов после подписания договора"""
        agent_id = call.from_user.id
        client_id = call.data.replace("dtp_continue_documents_", "")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.delete_message(call.message.chat.id, user_temp_data[agent_id]['message_id'])
        except:
            pass
        
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
        fields_to_remove = [
            'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
            'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
            'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back',
            'editing_contract', 'editing_field'
        ]
        
        for field in fields_to_remove:
            data.pop(field, None)
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        user_temp_data[agent_id]['contract_data'] = data
        

        try:
            with open(f"clients/{data['client_id']}/Документы/{data.get('docs', 'СТС')}.pdf", 'rb') as document_file:
                msg = bot.send_document(call.message.chat.id, document_file)   
                user_temp_data[agent_id]['message_id'] = msg.message_id
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, f"Файл не найден")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📄 Вернуться к договору", callback_data=get_contract_callback(call.from_user.id, client_id))) 
        msg = bot.send_message(
            chat_id=call.message.chat.id,
            text=f"Введите серию документа {data.get('docs', 'СТС')}",
            reply_markup = keyboard
        )
        bot.register_next_step_handler(msg, seria_docs, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("dtp_next_zayavlenie_"))
    @prevent_double_click(timeout=3.0)
    def dtp_next_zayavlenie(call):
        client_id = call.data.replace("dtp_next_zayavlenie_", "")
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
            text="Введите марку и модель авто",
            reply_markup=None
            )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, marks, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["STS", "PTS"])
    @prevent_double_click(timeout=3.0)
    def callback_docs(call):
        agent_id = call.from_user.id
        
        data = user_temp_data[agent_id]['contract_data']
        
        if call.data == "STS":
            data.update({"docs": "СТС"})
            data['dkp'] = '-'
            keyboard = create_back_keyboard("back_to_doc_choice")
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📸 Отправьте фото <b>лицевой стороны</b> СТС",
                parse_mode='HTML',
                reply_markup=keyboard 
            )

            bot.register_next_step_handler(msg, process_sts_front_agent, agent_id, data, msg.message_id)

        elif call.data == "PTS":
            data['docs'] = "ПТС"
            user_temp_data[agent_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Управляю по ДКП", callback_data="DKP")
            btn2 = types.InlineKeyboardButton("Продолжить", callback_data="DKP_next")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_doc_choice")  # ✅ Добавлена кнопка
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn_back)  # ✅ Добавлена кнопка
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите из следующих вариантов",
                reply_markup=keyboard
            )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_doc_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_doc_choice(call):
        """Возврат к выбору документа ТС"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="STS")
        btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="PTS")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_driver_license_back")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn_back)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Водительское удостоверение успешно сохранено!\nВыберите документ о регистрации ТС:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_driver_license_back")
    @prevent_double_click(timeout=3.0)
    def back_to_driver_license_back(call):
        """Возврат к загрузке обратной стороны ВУ"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        contract_data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_driver_license_front")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Фотография лицевой стороны принята.\n\n📸 Теперь отправьте фотографию обратной стороны водительского удостоверения.",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_driver_license_back_agent, agent_id, contract_data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["DKP", "DKP_next"])
    @prevent_double_click(timeout=3.0)
    def callback_agent_dkp(call):
        """Обработка выбора ДКП"""
        agent_id = call.from_user.id
        data = user_temp_data[agent_id]['contract_data']

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        if call.data == "DKP":
            data['dkp'] = 'Договор ДКП'
        else:
            data['dkp'] = '-'


        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        user_temp_data[agent_id]['pts_photos'] = []
        user_temp_data[agent_id]['contract_data'] = data
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_pts_upload_agent_{agent_id}")
        keyboard.add(btn_finish)
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_doc_choice"))
        bot.send_message(
            call.message.chat.id,
            "📸 Отправьте фото страниц ПТС\n\n"
            "Можно отправлять по одной фотографии или несколько сразу.\n"
            "Когда загрузите все страницы, нажмите кнопку ниже:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('ins_page_'))
    @prevent_double_click(timeout=3.0)
    def handle_insurance_pagination(call):
        """Обрабатывает пагинацию страховых компаний"""
        try:
            page = int(call.data.split('_')[2])
            keyboard = create_insurance_keyboard_with_back(page)
            
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error handling pagination: {e}")
    @bot.callback_query_handler(func=lambda call: call.data in ["Reco", "Ugo", "SOGAZ", "Ingo", "Ros", "Maks", "Energo", "Sovko", "Alfa", "VSK", "Soglasie", "Sber", "T-ins", "Ren", "Chul", "other"])
    @prevent_double_click(timeout=3.0)
    def callback_insurance(call):
        agent_id = call.from_user.id
        data = user_temp_data[agent_id]['contract_data']
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
            keyboard = create_back_keyboard("back_to_seria_insurance")
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию страхового полиса",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        else: 
            keyboard = create_back_keyboard("back_to_year_auto_from_insurance")
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, other_insurance, data, user_message_id)

    def marks(message, contract_data, user_message_id):
        """Обработка марки и модели авто"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        contract_data.update({"marks": message.text})
        user_temp_data[message.from_user.id]['contract_data'] = contract_data
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.send_message(message.chat.id, text="Введите номер авто клиента", reply_markup=keyboard)
        bot.register_next_step_handler(msg, number_auto, contract_data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_marks")
    @prevent_double_click(timeout=3.0)
    def back_to_marks(call):
        """Возврат к вводу марки авто"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        contract_data = user_temp_data[agent_id]['contract_data']
        
        # Определяем куда возвращаться в зависимости от контекста
        if contract_data.get('who_dtp'):
            # Если уже заполняли документ фиксации ДТП
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🚗 По форме ГИБДД", callback_data="dtp_gibdd"))
            keyboard.add(types.InlineKeyboardButton("📝 Евро-протокол", callback_data="dtp_evro"))
            
            if contract_data.get('ev') == 'Да':
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_park"))
            else:
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dtp_address"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите документ фиксации ДТП",
                reply_markup=keyboard
            )
        else:
            # Если идём от загрузки документов
            callback_back = "dtp_continue_documents_" + str(contract_data.get('client_id', ''))
            keyboard = create_back_keyboard(callback_back)
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите марку и модель авто клиента",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, marks, contract_data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_who_dtp")
    @prevent_double_click(timeout=3.0)
    def back_to_who_dtp(call):
        """Возврат к выбору документа фиксации ДТП"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        if data.get('ev') == 'Да':
            keyboard = create_back_keyboard("back_to_address_park")
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите адрес местонахождения транспортного средства, где будет произведена оценка ущерба.",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_dtp_address_park, agent_id, msg.message_id)
        else:
            keyboard = create_back_keyboard("back_to_dtp_address")
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите адрес ДТП:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_dtp_address, agent_id, msg.message_id)    
    def number_auto(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
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
            user_temp_data[message.from_user.id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n"
                "Все буквы должны быть заглавными!\n\n"
                "Введите номер авто (Пример: А123БВ77)",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, number_auto, data, msg.message_id)
            return
        
        if not match:
            user_temp_data[message.from_user.id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n\n"
                "📝 Правила ввода:\n"
                "• Формат: А123БВ77 или А123БВ777\n"
                f"• Разрешенные буквы: {', '.join(allowed_letters)}\n"
                "• Все буквы заглавные\n\n"
                "Введите номер авто:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, number_auto, data, msg.message_id)
            return
        
        # Извлекаем части номера
        letter1 = match.group(1)
        digits = match.group(2)
        letters2 = match.group(3)
        region = match.group(4)
        
        # Проверяем, что цифры не состоят только из нулей
        if digits == "000":
            user_temp_data[message.from_user.id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Основные цифры номера не могут быть 000\n\n"
                "Введите корректный номер авто (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, number_auto, data, msg.message_id)
            return
        
        # Проверяем, что код региона не состоит только из нулей
        if region == "00" or region == "000":
            user_temp_data[message.from_user.id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto")
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Код региона не может быть 00 или 000\n\n"
                "Введите корректный номер авто (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, number_auto, data, msg.message_id)
            return
        
        # Все проверки пройдены - сохраняем номер
        data['car_number'] = car_number
        save_step_state(message.from_user.id, 'number_auto', data)
        
        keyboard = create_back_keyboard("back_to_car_number")
        msg = bot.send_message(message.chat.id, "Введите год выпуска авто (например, 2025):", reply_markup=keyboard)
        bot.register_next_step_handler(msg, year_auto, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_auto")
    @prevent_double_click(timeout=3.0)
    def back_to_number_auto(call):
        """Возврат к вводу номера авто"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_marks")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку и модель авто клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, marks, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_car_number")
    @prevent_double_click(timeout=3.0)
    def back_to_car_number(call):
        """Возврат к вводу номера авто из года"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер авто клиента",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, number_auto, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "non_standart_number_car_agent")
    @prevent_double_click(timeout=3.0)
    def handle_agent_non_standart_number(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        contract_data = user_temp_data[call.from_user.id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_car_number")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер авто",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, process_agent_car_number_non_standart, msg.message_id, contract_data)

    def process_agent_car_number_non_standart(message, user_message_id, contract_data):
        """Обработка номера авто"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        contract_data['car_number'] = car_number
        
        keyboard = create_back_keyboard("back_to_car_number")
        msg = bot.send_message(message.chat.id, "Введите год выпуска авто (например, 2025):", reply_markup=keyboard)
        bot.register_next_step_handler(msg, year_auto, contract_data, msg.message_id)

    def year_auto(message, data, user_message_id):
        agent_id = message.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        text = message.text.replace(" ", "")
        
        # Проверка формата
        if len(text) != 4 or not text.isdigit():
            keyboard = create_back_keyboard("back_to_car_number")
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите корректный год выпуска авто (например, 2025):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, year_auto, data, msg.message_id)
            return
        
        year = int(text)
        current_year = datetime.now().year
        
        # Проверка диапазона
        if not (1900 < year <= current_year):
            keyboard = create_back_keyboard("back_to_car_number")
            msg = bot.send_message(
                message.chat.id, 
                f"❌ Год должен быть в диапазоне от 1901 до {current_year}!\nВведите корректный год выпуска авто:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, year_auto, data, msg.message_id)
            return
        
        # Сохраняем год
        data['year_auto'] = year
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        user_temp_data[agent_id]['contract_data'] = data
        save_step_state(agent_id, 'year_auto', data)
        
        # СРАЗУ ПЕРЕХОДИМ К ВЫБОРУ СТРАХОВОЙ (БЕЗ ЗАГРУЗКИ ВУ)
        keyboard = create_insurance_keyboard_with_back(page=0)
        msg = bot.send_message(
            message.chat.id,
            "Выберите страховую компанию:",
            reply_markup=keyboard
        )
    def create_insurance_keyboard_with_back(page=0, items_per_page=5):
        """Создает клавиатуру с пагинацией для страховых компаний с кнопкой Назад"""
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
            row_buttons.append(types.InlineKeyboardButton('◀️ Предыдущие', callback_data=f'ins_page_{page-1}'))
        
        # Кнопка "Еще" если есть следующая страница
        if end_idx < len(insurance_companies):
            row_buttons.append(types.InlineKeyboardButton('Еще ▶️', callback_data=f'ins_page_{page+1}'))
        
        if row_buttons:
            keyboard.row(*row_buttons)
        
        # Всегда добавляем кнопку "Другое"
        keyboard.add(types.InlineKeyboardButton('Другое', callback_data="other"))
        
        # Добавляем кнопку "◀️ Назад к году авто"
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_year_auto_from_insurance"))
        
        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_year_auto_from_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_year_auto_from_insurance(call):
        """Возврат к вводу года авто из выбора страховой"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_car_number")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите год выпуска авто (например, 2025):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, year_auto, data, msg.message_id)

    def process_driver_license_front_agent(message, agent_id, contract_data, user_message_id):
        """Обработка фото лицевой стороны ВУ"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:

            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
                parse_mode='HTML',
                reply_markup=None 
            )
            bot.register_next_step_handler(msg, process_driver_license_front_agent, agent_id, contract_data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем во временное хранилище
            if agent_id not in user_temp_data:
                user_temp_data[agent_id] = {}
            
            user_temp_data[agent_id]['driver_license_front'] = downloaded_file
            user_temp_data[agent_id]['contract_data'] = contract_data
            keyboard = create_back_keyboard("back_to_driver_license_front")
            # Запрашиваем обратную сторону
            msg = bot.send_message(
                message.chat.id,
                "✅ Фотография лицевой стороны принята.\n\n📸 Теперь отправьте фотографию обратной стороны водительского удостоверения.",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_driver_license_back_agent, agent_id, contract_data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при обработке фото ВУ (лицевая сторона): {e}")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:\n\n📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_driver_license_front_agent, agent_id, contract_data, msg.message_id)


    @bot.callback_query_handler(func=lambda call: call.data.startswith('agent_request_act_payment_'))
    @prevent_double_click(timeout=3.0)
    def agentrequest_act_payment_callback(call):
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
                if data['accident'] == 'ДТП' and data['sobstvenik'] != 'С начала':
                    keyboard.add(types.InlineKeyboardButton("▶️ К заявлению в страховую", callback_data=f"dtp_continue_documents_{data['client_id']}"))
                elif data['accident'] == 'Подал заявление':
                    keyboard.add(types.InlineKeyboardButton("▶️ Продолжить", callback_data=f"agent_podal_continue_documents_{data['client_id']}")) 
                elif data['accident'] == 'Нет ОСАГО':
                    keyboard.add(types.InlineKeyboardButton("▶️ Заявление о выдаче из ГИБДД", callback_data=f"agent_net_osago_continue_documents_{data['client_id']}")) 
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(user_id, data['client_id'])))   
            with open(f"clients/"+str(data['client_id'])+f"/Документы/{output_filename}", 'rb') as doc:
                bot.send_document(call.message.chat.id, doc, caption="📋 Запрос на выдачу документов", reply_markup = keyboard)
        except FileNotFoundError:
            bot.send_message(call.message.chat.id, "❌ Ошибка: файл не найден")
        
        if data['user_id'] != '8572367590':
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
    def process_driver_license_back_agent(message, agent_id, contract_data, user_message_id):
        """Обработка фото обратной стороны ВУ и создание PDF"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            keyboard = create_back_keyboard("back_to_driver_license_front")  # ✅ Добавлена кнопка
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>обратной стороны</b> водительского удостоверения:",
                parse_mode='HTML',
                reply_markup=keyboard  # ✅ Добавлена клавиатура
            )
            bot.register_next_step_handler(msg, process_driver_license_back_agent, agent_id, contract_data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Получаем лицевую сторону из временного хранилища
            front_photo = user_temp_data[agent_id]['driver_license_front']
            
            # Создаем директорию для сохранения
            client_dir = f"clients/{contract_data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/Водительское_удостоверение.pdf"
            create_pdf_from_images_agent(front_photo, downloaded_file, pdf_path)
            
            # Очищаем временные данные
            if 'driver_license_front' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['driver_license_front']
            
            # Переходим к выбору документа ТС
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="STS")
            btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="PTS")
            btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_driver_license_front")
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
            bot.register_next_step_handler(msg, process_driver_license_back_agent, agent_id, contract_data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_driver_license_front")
    @prevent_double_click(timeout=3.0)
    def back_to_driver_license_front(call):
        """Возврат к загрузке лицевой стороны ВУ"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        contract_data = user_temp_data[agent_id]['contract_data']
        
        # Очищаем временные данные лицевой стороны
        if 'driver_license_front' in user_temp_data[agent_id]:
            del user_temp_data[agent_id]['driver_license_front']
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📸 Отправьте фото <b>лицевой стороны</b> водительского удостоверения:",
            parse_mode='HTML',
            reply_markup=None
        )
        bot.register_next_step_handler(msg, process_driver_license_front_agent, agent_id, contract_data, msg.message_id)
    def create_pdf_from_images_agent(image1_bytes, image2_bytes, output_path):
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


    def seria_docs(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({"seria_docs": message.text})
        
        keyboard = create_back_keyboard("back_to_number_docs")
        message = bot.send_message(message.chat.id, text=f"Введите номер документа {data.get('docs', 'СТС')}", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_docs, data, user_message_id)

    def number_docs(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit():
            data.update({"number_docs": message.text})
            
            keyboard = create_back_keyboard("back_to_data_docs")
            message = bot.send_message(
                message.chat.id,
                text=f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_docs, data, user_message_id)
        else:
            keyboard = create_back_keyboard("back_to_number_docs")
            message = bot.send_message(
                message.chat.id,
                text=f"Неправильный формат!\nВведите номер документа {data.get('docs', 'СТС')}, он должен состоять только из цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_docs, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_number_docs(call):
        """Возврат к вводу номера документа"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📄 Вернуться к договору", callback_data=get_contract_callback(call.from_user.id, data['client_id']))) 
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите серию документа {data.get('docs', 'СТС')}",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, seria_docs, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_download_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_download_docs(call):
        """Возврат к вводу номера документа"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_data_docs")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, data_docs, data, msg.message_id)
    def data_docs(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        agent_id = message.from_user.id
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data['data_docs'] = message.text.strip()
            try:
                bot.delete_message(message.chat.id, user_temp_data[agent_id]['message_id'])
            except:
                pass

            user_temp_data[agent_id]['contract_data'] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"health_yes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"health_no"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_download_docs"))
            bot.send_message(
                agent_id, 
                "Имеется ли причинения вреда здоровья в следствии ДТП?", 
                reply_markup=keyboard
            )
                
        except ValueError:
            keyboard = create_back_keyboard("back_to_data_docs")
            message = bot.send_message(
                message.chat.id, 
                text=f"Неправильный формат ввода!\nВведите дату выдачи документа {data.get('docs', 'СТС')} в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_docs, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_data_docs")
    @prevent_double_click(timeout=3.0)
    def back_to_data_docs(call):
        """Возврат к вводу даты документа"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_number_docs")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите номер документа {data.get('docs', 'СТС')}",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, number_docs, data, msg.message_id)
        # ==================== СТС (2 стороны) ====================

    def process_sts_front_agent(message, agent_id, data, user_message_id):
        """Обработка фото лицевой стороны СТС"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            keyboard = create_back_keyboard("back_to_download_docs")  # ✅ ДОБАВЛЕНА КНОПКА
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>лицевой стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup=keyboard  # ✅ ДОБАВЛЕНА КЛАВИАТУРА
            )
            bot.register_next_step_handler(msg, process_sts_front_agent, agent_id, data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем во временное хранилище
            if agent_id not in user_temp_data:
                user_temp_data[agent_id] = {}
            
            user_temp_data[agent_id]['sts_front'] = downloaded_file
            user_temp_data[agent_id]['contract_data'] = data
            keyboard = create_back_keyboard("back_to_download_docs")
            # Запрашиваем обратную сторону
            msg = bot.send_message(
                message.chat.id,
                "✅ Лицевая сторона получена!\n\n📸 Теперь отправьте фото <b>обратной стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_sts_back_agent, agent_id, data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при обработке фото СТС (лицевая сторона): {e}")
            keyboard = create_back_keyboard("back_to_download_docs")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_sts_front_agent, agent_id, data, msg.message_id)


    def process_sts_back_agent(message, agent_id, data, user_message_id):
        """Обработка фото обратной стороны СТС и создание PDF"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.photo:
            keyboard = create_back_keyboard("back_to_download_docs")
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте фотографию!\n\n📸 Отправьте фото <b>обратной стороны</b> СТС:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_sts_back_agent, agent_id, data, msg.message_id)
            return
        
        try:
            # Получаем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Получаем лицевую сторону из временного хранилища
            front_photo = user_temp_data[agent_id]['sts_front']
            print(data)
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/СТС.pdf"
            create_pdf_from_images_agent2([front_photo, downloaded_file], pdf_path)
            
            # Очищаем временные данные
            if 'sts_front' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['sts_front']
            
            msg = bot.send_message(
                message.chat.id,
                "✅ СТС успешно сохранен!"
            )
            
            finish_document_upload_agent(message.chat.id, agent_id, data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при создании PDF СТС: {e}")
            keyboard = create_back_keyboard("back_to_download_docs")
            msg = bot.send_message(
                message.chat.id,
                "❌ Произошла ошибка при обработке фото. Попробуйте снова:",
                parse_mode='HTML',
                reply_markup = keyboard
            )
            bot.register_next_step_handler(msg, process_sts_back_agent, agent_id, data, msg.message_id)


    # ==================== ПТС (множественные фото) ====================

    @bot.message_handler(content_types=['photo'],
                         func=lambda message: (message.chat.id not in upload_sessions or 'photos' not in upload_sessions.get(message.chat.id, {})) and (message.chat.id in user_temp_data))
    def handle_pts_photos(message):
        """Обработчик фотографий ПТС (множественная загрузка)"""
        client_id = message.chat.id
        print(3)
        cleanup_messages(bot, message.chat.id, message.message_id, 3)
        
        def send_photo_confirmation(chat_id, photo_type, count):
            """Отправка отложенного подтверждения загрузки"""
            data_admin = get_admin_from_db_by_user_id(chat_id)
            data = user_temp_data[chat_id]
            keyboard = types.InlineKeyboardMarkup()
            print(1)
            if data_admin['admin_value'] == 'Клиент':
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_{photo_type}_upload_client_{chat_id}")
            elif data.get('user_id', '') == '8572367590':
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_{photo_type}_upload_admin_{chat_id}")
            else:
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_{photo_type}_upload_agent_{chat_id}")
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


    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_pts_upload_agent_'))
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
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_pts_upload_agent_{client_id}")
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_doc_choice")  # ✅ Добавлена кнопка
                keyboard.add(btn_finish)
                keyboard.add(btn_back)  # ✅ Добавлена кнопка
                
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Отправьте фото страниц ПТС:",
                    reply_markup=keyboard
                )
                return
            print(user_temp_data)
            # Создаем директорию для сохранения
            client_dir = f"clients/{data['client_id']}/Документы"
            os.makedirs(client_dir, exist_ok=True)
            
            # Создаем PDF
            pdf_path = f"{client_dir}/ПТС.pdf"
            create_pdf_from_images_agent2(photos, pdf_path)
            
            # Очищаем временные данные
            del user_temp_data[client_id]['pts_photos']
            
            msg = bot.send_message(call.message.chat.id, f"✅ ПТС успешно сохранен! (Страниц: {len(photos)})")
            print(data.get('dkp'))
            # Проверяем, нужно ли загружать ДКП
            if data.get('dkp') == 'Договор ДКП':
                start_dkp_upload_agent(call.message.chat.id, client_id, data, msg.message_id)
            else:
                finish_document_upload_agent(call.message.chat.id, client_id, data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при сохранении ПТС: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении документа.")


    # ==================== ДКП (множественные фото) ====================

    def start_dkp_upload_agent(chat_id, client_id, data, user_message_id):
        """Начало загрузки ДКП"""
        # Инициализируем хранилище для фото ДКП
        try:
            bot.delete_message(chat_id, user_message_id)
        except:
            pass
        if client_id not in user_temp_data:
            user_temp_data[client_id] = {}
        user_temp_data[client_id]['dkp_photos'] = []
        user_temp_data[client_id]['contract_data'] = data

        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dkp_upload_agent_{client_id}")
        btn_finish2 = types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_doc_choice")
        keyboard.add(btn_finish)
        keyboard.add(btn_finish2)
        bot.send_message(
            chat_id,
            "📸 Отправьте фото страниц Договора купли-продажи\n\n"
            "Можно отправлять по одной фотографии или несколько сразу.\n"
            "Когда загрузите все страницы, нажмите кнопку ниже:",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_dkp_upload_agent_'))
    @prevent_double_click(timeout=3.0)
    def finish_dkp_upload_callback(call):
        """Завершение загрузки ДКП"""
        client_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if client_id not in user_temp_data or 'dkp_photos' not in user_temp_data[client_id]:
                keyboard.add(btn_finish)
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.", rely_markup = keyboard)
                return
            
            photos = user_temp_data[client_id]['dkp_photos']
            data = user_temp_data[client_id]['contract_data']
            
            if len(photos) == 0:
                
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dkp_upload_agent_{client_id}")
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
            create_pdf_from_images_agent2(photos, pdf_path)
            
            # Очищаем временные данные
            del user_temp_data[client_id]['dkp_photos']
            
            msg = bot.send_message(call.message.chat.id, f"✅ Договор купли-продажи успешно сохранен! (Страниц: {len(photos)})")
            
            # Завершаем загрузку документов
            finish_document_upload_agent(call.message.chat.id, client_id, data, msg.message_id)
            
        except Exception as e:
            print(f"Ошибка при сохранении ДКП: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении документа.")


    # ==================== Завершение загрузки ====================
    def finish_document_upload_agent(chat_id, agent_id, data, user_message_id):
        """Завершение загрузки всех документов и переход к выбору страховой"""
        try:
            bot.delete_message(chat_id, user_message_id)
        except:
            pass
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        user_temp_data[agent_id]['protocol_photos'] = []
        user_temp_data[agent_id]['contract_data'] = data

        # Определяем текст в зависимости от типа протокола
        if data.get("who_dtp", '') == 'Евро-протокол':
            protocol_text = "Евро-протокола"
        else:
            protocol_text = "протокола ГИБДД"
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_agent_{agent_id}")
        keyboard.add(btn_finish)
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_doc_choice"))
        bot.send_message(
            chat_id, 
            f"📸 Прикрепите фото {protocol_text}\n\nФото должны быть четкими, не засвечены.\nМожно отправлять по одной фотографии или несколько сразу.\nКогда загрузите все фото, нажмите кнопку ниже:", 
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data in ['health_yes', 'health_no'])
    @prevent_double_click(timeout=3.0)
    def finish_dkp_health_callback(call):
        agent_id = call.from_user.id
        data=user_temp_data[call.from_user.id]['contract_data']
        if call.data == 'health_yes':
            if data.get('who_dtp') == "По форме ГИБДД":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"place_dtp"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_finish_document_upload"))  
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
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"agent_photo_non_gosuslugi"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_finish_document_upload"))
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, agent_number_photo, data, msg.message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"culp_have_osago_yes"))
            keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"culp_have_osago_no"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_finish_document_upload"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Есть ли у пострадавшего ОСАГО?",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ['culp_have_osago_yes', 'culp_have_osago_no'])
    @prevent_double_click(timeout=3.0)
    def finish_culp_have_osago_callback(call):
        agent_id = call.from_user.id
        data=user_temp_data[call.from_user.id]['contract_data']
        
        if call.data == 'culp_have_osago_yes':
            if data.get('who_dtp') == "По форме ГИБДД":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"place_dtp"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))  # Добавлена кнопка
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
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"agent_photo_non_gosuslugi"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))  # Добавлена кнопка
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, agent_number_photo, data, msg.message_id)
        else:
            if data.get('who_dtp') == "По форме ГИБДД":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"place_home"))
                keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"place_dtp"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))  # Добавлена кнопка
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
                keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"agent_photo_non_gosuslugi"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))  # Добавлена кнопка
                msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, agent_number_photo, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_health_question")
    @prevent_double_click(timeout=3.0)
    def back_to_health_question(call):
        """Возврат к вопросу о наличии ОСАГО"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"culp_have_osago_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"culp_have_osago_no"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_finish_document_upload"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Есть ли у пострадавшего ОСАГО?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_finish_document_upload")
    @prevent_double_click(timeout=3.0)
    def back_to_finish_document_upload(call):
        """Возврат к вопросу о вреде здоровью"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"health_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"health_no"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_download_docs"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Имеется ли причинения вреда здоровья в следствии ДТП?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_year_auto")
    @prevent_double_click(timeout=3.0)
    def back_to_year_auto(call):
        """Возврат к вводу года авто"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_car_number")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите год выпуска авто (например, 2025):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, year_auto, data, msg.message_id)
    # ==================== Функция создания PDF ====================

    def create_pdf_from_images_agent2(image_bytes_list, output_path):
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

    def other_insurance(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"insurance": message.text})
        save_step_state(message.from_user.id, 'other_insurance', data)
        
        keyboard = create_back_keyboard("back_to_seria_insurance")
        message = bot.send_message(message.chat.id, text="Введите серию страхового полиса", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_insurance_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_insurance_choice(call):
        """Возврат к выбору страховой компании"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_insurance_keyboard(page=0)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите страховую компанию:",
            reply_markup=keyboard
        )
    def seria_insurance(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"seria_insurance": message.text})
        save_step_state(message.from_user.id, 'seria_insurance', data)
        
        keyboard = create_back_keyboard("back_to_number_insurance")
        message = bot.send_message(message.chat.id, text="Введите номер страхового полиса", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_insurance, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_seria_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_seria_insurance(call):
        """Возврат к вводу серии полиса"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        # Проверяем, был ли это "Другое" или выбор из списка
        if data.get('insurance') not in [name for name, _ in insurance_companies]:
            keyboard = create_back_keyboard("back_to_insurance_choice")
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, other_insurance, data, msg.message_id)
        else:
            keyboard = create_insurance_keyboard(page=0)
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите страховую компанию:",
                reply_markup=keyboard
            )
    def number_insurance(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"number_insurance": message.text})
        save_step_state(message.from_user.id, 'number_insurance', data)
        
        keyboard = create_back_keyboard("back_to_date_insurance")
        message = bot.send_message(message.chat.id, text="Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_insurance, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_number_insurance(call):
        """Возврат к вводу номера полиса"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_seria_insurance")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите серию страхового полиса",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, seria_insurance, data, msg.message_id)
    def date_insurance(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        agent_id = message.from_user.id
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
            two_years_ago = current_date - timedelta(days=365)
            
            # Проверка: дата не в будущем
            if insurance_date > current_date:
                keyboard = create_back_keyboard("back_to_date_insurance")
                msg = bot.send_message(
                    message.chat.id, 
                    "❌ Дата не может быть в будущем!\n"
                    "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, date_insurance, data, msg.message_id)
                return
            
            # Проверка: дата не старше 1 года
            if insurance_date < two_years_ago:
                keyboard = create_back_keyboard("back_to_date_insurance")
                msg = bot.send_message(
                    message.chat.id, 
                    f"❌ Полис не может быть старше 1 года!\n"
                    f"Минимальная дата: {two_years_ago.strftime('%d.%m.%Y')}\n\n"
                    "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                    reply_markup=keyboard
                )
                bot.register_next_step_handler(msg, date_insurance, data, msg.message_id)
                return
            
            # Все проверки пройдены - сохраняем дату
            data['date_insurance'] = message.text.strip()

            if data.get('accident', '') != 'После ямы':
                keyboard = create_back_keyboard("back_to_fio_culp")
                msg = bot.send_message(message.chat.id, "Введите ФИО виновника ДТП в формате: Иванов Иван Иванович", reply_markup=keyboard)
                bot.register_next_step_handler(msg, fio_culp, data, msg.message_id)
            elif data.get('accident', '') == 'После ямы':
                send_full_contract_summary_to_client(agent_id, data)

        except ValueError:
            keyboard = create_back_keyboard("back_to_date_insurance")
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\n"
                "Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, date_insurance, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_insurance")
    @prevent_double_click(timeout=3.0)
    def back_to_date_insurance(call):
        """Возврат к вводу даты полиса"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_number_insurance")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер страхового полиса",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, number_insurance, data, msg.message_id)
    def fio_culp(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.split()) < 2:
            keyboard = create_back_keyboard("back_to_date_insurance")
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович", reply_markup=keyboard)
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():
                    keyboard = create_back_keyboard("back_to_date_insurance")
                    message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович", reply_markup=keyboard)
                    user_message_id = message.message_id
                    bot.register_next_step_handler(message, fio_culp, data, user_message_id)
                    return
            
            data.update({"fio_culp": message.text})
            save_step_state(message.from_user.id, 'fio_culp', data)
            
            keyboard = create_back_keyboard("back_to_marks_culp")
            message = bot.send_message(message.chat.id, text="Введите марку, модель виновника ДТП", reply_markup=keyboard)
            user_message_id = message.message_id
            bot.register_next_step_handler(message, marks_culp, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_fio_culp")
    @prevent_double_click(timeout=3.0)
    def back_to_fio_culp(call):
        """Возврат к вводу ФИО виновника"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_date_insurance")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату заключения договора ОСАГО (страхового полиса) в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, date_insurance, data, msg.message_id)
    def marks_culp(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"marks_culp": message.text})
        user_temp_data[message.from_user.id]['contract_data'] = data
        save_step_state(message.from_user.id, 'marks_culp', data)
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent_culp")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto_culp")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        message = bot.send_message(message.chat.id, text="Введите номер авто виновника ДТП", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_auto_culp, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_marks_culp")
    @prevent_double_click(timeout=3.0)
    def back_to_marks_culp(call):
        """Возврат к вводу марки виновника"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_fio_culp")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ФИО виновника ДТП в формате: Иванов Иван Иванович",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, fio_culp, data, msg.message_id)
    def number_auto_culp(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        
        allowed_letters = 'АВЕКМНОРСТУХ'
        pattern = r'^([АВЕКМНОРСТУХ]{1})(\d{3})([АВЕКМНОРСТУХ]{2})(\d{2,3})$'
        
        original_text = message.text.replace(" ", "")
        has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
        
        match = re.match(pattern, car_number)
        
        if has_lowercase:
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto_culp")  # ИСПРАВЛЕНО
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\n"
                "Все буквы должны быть заглавными!\n\n"
                "Введите номер авто виновника ДТП(Пример: А123БВ77)",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, number_auto_culp, data, msg.message_id)
            return
        
        if not match:
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto_culp")  # ИСПРАВЛЕНО
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
            bot.register_next_step_handler(msg, number_auto_culp, data, msg.message_id)
            return
        
        letter1 = match.group(1)
        digits = match.group(2)
        letters2 = match.group(3)
        region = match.group(4)
        
        if digits == "000":
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto_culp")  # ИСПРАВЛЕНО
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Основные цифры номера не могут быть 000\n\n"
                "Введите корректный номер авто виновника ДТП (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, number_auto_culp, data, msg.message_id)
            return
        
        if region == "00" or region == "000":
            keyboard = types.InlineKeyboardMarkup()
            btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent_culp")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto_culp")  # ИСПРАВЛЕНО
            keyboard.add(btn_finish)
            keyboard.add(btn_back)
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный номер!\n"
                "Код региона не может быть 00 или 000\n\n"
                "Введите корректный номер авто виновника ДТП (Пример: А123БВ77):",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, number_auto_culp, data, msg.message_id)
            return
        
        data['number_auto_culp'] = str(car_number)
        agent_id = message.from_user.id
        user_temp_data[agent_id]['contract_data'] = data
        save_step_state(agent_id, 'number_auto_culp', data)
        
        # Восстанавливаем client_user_id из данных
        if 'user_id' in data and 'client_user_id' not in user_temp_data[agent_id]:
            user_temp_data[agent_id]['client_user_id'] = int(data['user_id'])
        
        # ВЫЗЫВАЕМ ОТПРАВКУ ДАННЫХ КЛИЕНТУ НА ПОДТВЕРЖДЕНИЕ
        send_full_contract_summary_to_client(agent_id, data)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_non_standart_number_car_agent_culp")
    @prevent_double_click(timeout=3.0)
    def back_to_non_standart_number_car_agent_culp(call):
        """Возврат к вводу марки виновника"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("🆎 Нестандартный формат гос. номера", callback_data=f"non_standart_number_car_agent_culp")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_auto_culp")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер авто виновника ДТП",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, number_auto_culp, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_auto_culp")
    @prevent_double_click(timeout=3.0)
    def back_to_number_auto_culp(call):
        """Возврат к вводу марки виновника"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_fio_culp")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите марку, модель виновника ДТП",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, marks_culp, data, msg.message_id)
    def send_full_contract_summary_to_client(agent_id, contract_data):
        """Отправка ПОЛНЫХ данных договора клиенту на подтверждение (после сбора данных о ДТП)"""
        client_user_id = user_temp_data[agent_id]['client_user_id']
        
        # Формируем сообщение для клиента со ВСЕМИ данными
        summary = "📋 <b>Проверьте данные договора:</b>\n\n"
        summary += f"👤 ФИО: {contract_data.get('fio', '')}\n"
        summary += f"📅 Дата рождения: {contract_data.get('date_of_birth', '')}\n"
        summary += f"📍 Город: {contract_data.get('city', '')}\n"
        summary += f"📄 Паспорт: {contract_data.get('seria_pasport', '')} {contract_data.get('number_pasport', '')}\n"
        summary += f"📍 Выдан: {contract_data.get('where_pasport', '')}\n"
        summary += f"📅 Дата выдачи: {contract_data.get('when_pasport', '')}\n"
        summary += f"📮 Индекс: {contract_data.get('index_postal', '')}\n"
        summary += f"🏠 Адрес: {contract_data.get('address', '')}\n\n"
        
        summary += f"<b>Данные о ДТП:</b>\n"
        summary += f"🚗 Дата ДТП: {contract_data.get('date_dtp', '')}\n"
        summary += f"⏰ Время ДТП: {contract_data.get('time_dtp', '')}\n"
        summary += f"📍 Адрес ДТП: {contract_data.get('address_dtp', '')}\n"
        summary += f"📍 Фиксация ДТП: {contract_data.get('who_dtp', '')}\n\n"
        
        summary += f"<b>Автомобиль клиента:</b>\n"
        summary += f"🚙 Марка/модель: {contract_data.get('marks', '')}\n"
        summary += f"🔢 Номер: {contract_data.get('car_number', '')}\n"
        summary += f"📅 Год выпуска: {contract_data.get('year_auto', '')}\n\n"
        
        summary += f"<b>Страховая компания:</b>\n"
        summary += f"🏢 Название: {contract_data.get('insurance', '')}\n"
        summary += f"📋 Полис: {contract_data.get('seria_insurance', '')} {contract_data.get('number_insurance', '')}\n"
        summary += f"📅 Дата полиса: {contract_data.get('date_insurance', '')}\n\n"
        
        summary += f"<b>Виновник ДТП:</b>\n"
        summary += f"👤 ФИО: {contract_data.get('fio_culp', '')}\n"
        summary += f"🚙 Марка/модель: {contract_data.get('marks_culp', '')}\n"
        summary += f"🔢 Номер авто: {contract_data.get('number_auto_culp', '')}\n"

        keyboard = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_contract_{agent_id}")
        btn_decline = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_contract_{agent_id}")
        keyboard.add(btn_confirm)
        keyboard.add(btn_decline)
        
        try:
            bot.delete_message(client_user_id, user_temp_data[agent_id]['contract_data']['message_id'])
        except:
            pass
        
        bot.send_message(client_user_id, summary, parse_mode='HTML', reply_markup=keyboard)
        
        # Уведомление агенту
        bot.send_message(
            agent_id,
            "✅ Данные отправлены клиенту на подтверждение.\n\nОжидайте ответа..."
        )
    @bot.callback_query_handler(func=lambda call: call.data == "non_standart_number_car_agent_culp")
    @prevent_double_click(timeout=3.0)
    def handle_agent_non_standart_number_culp(call):

        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        contract_data = user_temp_data[call.from_user.id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_non_standart_number_car_agent_culp"))
        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер авто виновника ДТП",
                reply_markup=keyboard
            )
        bot.register_next_step_handler(msg, process_agent_car_number_non_standart_culp, msg.message_id, contract_data)

    def process_agent_car_number_non_standart_culp(message, user_message_id, contract_data):
        """Обработка номера авто виновника (нестандартный формат)"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        agent_id = message.from_user.id
        
        # ✅ ИСПРАВЛЕНИЕ: НЕ создаём новый словарь, а ОБНОВЛЯЕМ существующий
        user_temp_data[agent_id]['contract_data']['number_auto_culp'] = car_number
        
        # ✅ Берём полные данные из user_temp_data
        full_contract_data = user_temp_data[agent_id]['contract_data']
        
        # ✅ Восстанавливаем client_user_id если его нет
        if 'user_id' in full_contract_data and 'client_user_id' not in user_temp_data[agent_id]:
            user_temp_data[agent_id]['client_user_id'] = int(full_contract_data['user_id'])
        
        # ВЫЗЫВАЕМ ОТПРАВКУ ДАННЫХ КЛИЕНТУ НА ПОДТВЕРЖДЕНИЕ
        send_full_contract_summary_to_client(agent_id, full_contract_data)
    @bot.callback_query_handler(func=lambda call: call.data == "agent_photo_non_gosuslugi")
    @prevent_double_click(timeout=3.0)
    def handle_agent_photo_non_gosuslugi(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"next_photo_agent"))
        keyboard.add(types.InlineKeyboardButton("Я внесу фотофиксацию", callback_data=f"continue_photo_agent"))  

        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Если нет прикрепления фотофиксации в Госуслуги, то выплата ограничивается размером 100000₽",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data in ["next_photo_agent", "continue_photo_agent"])
    @prevent_double_click(timeout=3.0)
    def handle_agent_next_photo_gosuslugi(call):
        data = user_temp_data[call.from_user.id]['contract_data']
        if call.data == "next_photo_agent":
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"place_dtp"))  
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
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"agent_photo_non_gosuslugi"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, agent_number_photo, data, msg.message_id)

    def agent_number_photo(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['number_photo'] = message.text
        user_temp_data[message.from_user.id]['contract_data'] = data
        save_step_state(message.from_user.id, 'number_photo', data)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_photo"))
        
        bot.send_message(
            message.from_user.id,
            "Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_photo")
    @prevent_double_click(timeout=3.0)
    def back_to_number_photo(call):
        """Возврат к вводу номера фотофиксации"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"agent_photo_non_gosuslugi"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, agent_number_photo, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_finish_dtp_upload")
    @prevent_double_click(timeout=3.0)
    def back_to_finish_dtp_upload(call):
        """Возврат к загрузке фото ДТП"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        # Инициализируем хранилище для фото ДТП заново
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        user_temp_data[agent_id]['dtp_photos'] = []
        user_temp_data[agent_id]['contract_data'] = data

        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_upload_agent_{agent_id}")
        keyboard.add(btn_finish)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📸 Прикрепите фото с ДТП\n\n"
                "Фото должны быть четкими, не засвечены. Обзор 360 градусов.\n"
                "Можно отправлять по одной фотографии или несколько сразу.\n"
                "Когда загрузите все фото, нажмите кнопку ниже:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["place_home", "place_dtp"])
    @prevent_double_click(timeout=3.0)
    def callback_agent_place(call):
        """Обработка ремонт не более 50км от места ДТП или места жительства"""
        agent_id = call.from_user.id
        data = user_temp_data[agent_id]['contract_data']
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "place_home":
            data['place'] = "Жительства"
        else:
            data['place'] = "ДТП"

        user_temp_data[agent_id]['contract_data'] = data

        
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"agent_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"agent_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_photo_or_health"))  # ✅ ИЗМЕНЕНА КНОПКА
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_number_photo_or_health")
    @prevent_double_click(timeout=3.0)
    def back_to_number_photo_or_health(call):
        """Возврат к вопросу о фотофиксации или выбору места"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"place_home"))
        keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"place_dtp"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_place_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_place_choice(call):
        """Возврат к выбору места ремонта"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        # Проверяем откуда пришли - с фотофиксацией или без
        if data.get('who_dtp') == "По форме ГИБДД":
            # Возвращаемся сразу к выбору места без фотофиксации
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Жительства", callback_data=f"place_home"))
            keyboard.add(types.InlineKeyboardButton("ДТП", callback_data=f"place_dtp"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_health_question"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Где необходимо произвести ремонт: в пределах 50 км от места ДТП или от места жительства?",
                reply_markup=keyboard
            )
        else:
            # Возвращаемся к вводу номера фотофиксации
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Фотофиксация не прикреплена", callback_data=f"agent_photo_non_gosuslugi"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_finish_dtp_upload"))
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите номер фотофиксации\n\nЕсли фотофиксация не прикреплена в Госуслуги, нажмите кнопку ниже👇",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, agent_number_photo, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["agent_next_bank", "agent_cancel_bank"])
    @prevent_double_click(timeout=3.0)
    def callback_agent_requisites(call):
        agent_id = call.from_user.id
        data = user_temp_data[agent_id]['contract_data']
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        if call.data == "agent_next_bank":
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="<b>Заполнение банковских реквизитов</b>",
                    parse_mode='HTML'
                )
            user_temp_data[agent_id]['contract_data']['message_id'] = msg.message_id 
            keyboard = create_back_keyboard("back_to_requisites_choice")  # ✅ ИЗМЕНЕНА КНОПКА
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
            
            data['date_ins'] = str(get_next_business_date())
            data['date_ins_pod'] = str(get_next_business_date())
            data['status'] = 'Отправлен запрос в страховую'

            if data.get("who_dtp", '') == '' or data.get("who_dtp", '') == None:
                data.update({'who_dtp': 'По форме ГИБДД'})
            if data.get("ev", '') == '' or data.get("ev", '') == None:
                data.update({'ev': 'Нет'})  

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
            
            # Выбираем шаблон в зависимости от эвакуатора    
            if data.get('sobstvenik', '') != 'С начала':
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
                        [str(data.get("insurance", "")), str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("place", "")),
                        str(data.get("number_photo", "")), str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", ""))],
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
                        [str(data.get("insurance", "")), str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("place", "")),
                        str(data.get("number_photo", "")), str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", "")), str(data.get("address_park", ""))],
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
                        [str(data.get("insurance", "")), str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("place", "")),
                        str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", "")), str(data.get("address_park", ""))],
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
                        [str(data.get("insurance", "")), str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("place", "")),
                        str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", ""))],
                        "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент по форме ГИБДД.docx",
                        f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                        )
            else:
                try:
                    admin_data = get_admin_from_db_by_fio(data.get('fio_not', ''))
                except:
                    print('Ошибка при загрузки данных юриста при составлении заявления в страховую')
                if data.get("who_dtp", '') == 'Евро-протокол' and data.get("ev", '') == 'Нет':
                    replace_words_in_word(
                        ["{{ Страховая }}", "{{ Представитель }}", "{{ Паспорт_серия_юрист }}", "{{ Паспорт_номер_юрист }}", "{{ ДР_юрист }}", 
                        "{{ Паспорт_выдан_юрист }}", "{{ Паспорт_когда_юрист }}", "{{ Место_юрист }}", "{{ Индекс_юрист }}", "{{ Адрес_юрист }}",
                        "{{ ФИО }}", "{{ Паспорт_серия }}", 
                        "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                        "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                        "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                        "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                        "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                        "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Телефон_представителя }}","{{ Место_Ж_Д }}", "{{ Фотофиксация }}",
                        "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                        [str(data.get("insurance", "")), str(data.get("fio_not", "")), str(admin_data.get("seria_pasport", "")), str(admin_data.get("number_pasport", "")), str(admin_data.get("date_of_birth", "")),
                        str(admin_data.get("where_pasport", "")), str(admin_data.get("when_pasport", "")), str(admin_data.get("city_birth", "")), str(admin_data.get("index_postal", "")), str(admin_data.get("address", "")),
                        str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("number_not", "")), str(data.get("place", "")),
                        str(data.get("number_photo", "")), str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", ""))],
                        "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую представитель европротокол.docx",
                        f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                        )
                elif data.get("who_dtp", '') == 'Евро-протокол' and data.get("ev", '') == 'Да':
                    replace_words_in_word(
                        ["{{ Страховая }}", "{{ Представитель }}", "{{ Паспорт_серия_юрист }}", "{{ Паспорт_номер_юрист }}", "{{ ДР_юрист }}", 
                        "{{ Паспорт_выдан_юрист }}", "{{ Паспорт_когда_юрист }}", "{{ Место_юрист }}", "{{ Индекс_юрист }}", "{{ Адрес_юрист }}",
                        "{{ ФИО }}", "{{ Паспорт_серия }}", 
                        "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                        "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                        "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                        "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Адрес_стоянки }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                        "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                        "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Телефон_представителя }}","{{ Место_Ж_Д }}", "{{ Фотофиксация }}",
                        "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                        [str(data.get("insurance", "")), str(data.get("fio_not", "")), str(admin_data.get("seria_pasport", "")), str(admin_data.get("number_pasport", "")), str(admin_data.get("date_of_birth", "")),
                        str(admin_data.get("where_pasport", "")), str(admin_data.get("when_pasport", "")), str(admin_data.get("city_birth", "")), str(admin_data.get("index_postal", "")), str(admin_data.get("address", "")),
                        str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("address_park", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("number_not", "")), str(data.get("place", "")),
                        str(data.get("number_photo", "")), str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", ""))],
                        "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую представитель эвакуатор европротокол.docx",
                        f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                        )
                elif data.get("who_dtp", '') == 'По форме ГИБДД' and data.get("ev", '') == 'Нет':
                    replace_words_in_word(
                        ["{{ Страховая }}", "{{ Представитель }}", "{{ Паспорт_серия_юрист }}", "{{ Паспорт_номер_юрист }}", "{{ ДР_юрист }}", 
                        "{{ Паспорт_выдан_юрист }}", "{{ Паспорт_когда_юрист }}", "{{ Место_юрист }}", "{{ Индекс_юрист }}", "{{ Адрес_юрист }}",
                        "{{ ФИО }}", "{{ Паспорт_серия }}", 
                        "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                        "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                        "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                        "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                        "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                        "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Телефон_представителя }}","{{ Место_Ж_Д }}",
                        "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                        [str(data.get("insurance", "")), str(data.get("fio_not", "")), str(admin_data.get("seria_pasport", "")), str(admin_data.get("number_pasport", "")), str(admin_data.get("date_of_birth", "")),
                        str(admin_data.get("where_pasport", "")), str(admin_data.get("when_pasport", "")), str(admin_data.get("city_birth", "")), str(admin_data.get("index_postal", "")), str(admin_data.get("address", "")),
                        str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("number_not", "")), str(data.get("place", "")),
                        str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", ""))],
                        "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую представитель по форме ГИБДД.docx",
                        f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                        )
                elif data.get("who_dtp", '') == 'По форме ГИБДД' and data.get("ev", '') == 'Да':
                    replace_words_in_word(
                        ["{{ Страховая }}", "{{ Представитель }}", "{{ Паспорт_серия_юрист }}", "{{ Паспорт_номер_юрист }}", "{{ ДР_юрист }}", 
                        "{{ Паспорт_выдан_юрист }}", "{{ Паспорт_когда_юрист }}", "{{ Место_юрист }}", "{{ Индекс_юрист }}", "{{ Адрес_юрист }}",
                        "{{ ФИО }}", "{{ Паспорт_серия }}", 
                        "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Паспорт_выдан  }}",
                        "{{ Паспорт_когда }}", "{{ Место }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Документ }}",
                        "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Договор ДКП }}", "{{ Марка_модель }}", 
                        "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Адрес_стоянки }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}",
                        "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                        "{{ Номер_полиса }}", "{{ Дата_начала_полиса }}", "{{ Город }}", "{{ Телефон_представителя }}","{{ Место_Ж_Д }}",
                        "{{ Банк_получателя }}", "{{ Счет_получателя }}", "{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}","{{ Дата_заявления_форма6 }}"],
                        [str(data.get("insurance", "")), str(data.get("fio_not", "")), str(admin_data.get("seria_pasport", "")), str(admin_data.get("number_pasport", "")), str(admin_data.get("date_of_birth", "")),
                        str(admin_data.get("where_pasport", "")), str(admin_data.get("when_pasport", "")), str(admin_data.get("city_birth", "")), str(admin_data.get("index_postal", "")), str(admin_data.get("address", "")),
                        str(data.get("fio", "")), str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")),
                        str(data.get("date_of_birth", "")), str(data.get("where_pasport", "")), str(data.get("when_pasport", "")),
                        str(data.get("city_birth", "")), str(data.get("index_postal", "")), str(data.get("address", "")), str(data.get("docs", "")), 
                        str(data.get("seria_docs", "")), str(data.get("number_docs", "")), str(data.get("data_docs", "")), 
                        str(data.get("dkp", "")), str(data.get("marks", "")), str(data.get("year_auto", "")),
                        str(data.get("car_number", "")), str(data.get("address_park", "")), str(data.get("date_dtp", "")), str(data.get("time_dtp", "")),
                        str(data.get("address_dtp", "")), str(data.get("fio_culp", "")), str(data.get("marks_culp", "")), str(data.get("seria_insurance", "")),
                        str(data.get("number_insurance", "")), str(data.get("date_insurance", "")), str(data.get("city", "")), str(data.get("number_not", "")), str(data.get("place", "")),
                        str(data.get("bank", "")), str(data.get("bank_account", "")), str(data.get("bank_account_corr", "")),
                        str(data.get("BIK", "")), str(data.get("INN", "")), str(data.get("date_ins", ""))],
                        "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую представитель эвакуатор по форме ГИБДД.docx",
                        f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                        )
            try:
                with open(f"clients/{data['client_id']}/Документы/Заявление в страховую.docx", 'rb') as document_file:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))
                    if data.get('sobstvenik', '') != 'С начала':
                        bot.send_document(int(data['user_id']), document_file, reply_markup=keyboard)
                    else:
                        bot.send_document(call.message.chat.id, document_file) 
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, f"Файл не найден")

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))
            keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"agent_request_act_payment_{data['client_id']}"))
            bot.send_message(
                call.message.chat.id,
                "✅ Заявление в страховую успешно сформировано!",
                reply_markup=keyboard
            )
            
            if agent_id in user_temp_data:
                user_temp_data.pop(agent_id, None)
            

    def bank(message, data, user_message_id):
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({"bank": message.text})
        user_temp_data[message.from_user.id]['contract_data'] = data
        keyboard = create_back_keyboard("back_to_bank_account")  # ✅ Изменена кнопка
        message = bot.send_message(message.chat.id, text="Введите счет получателя, 20 цифр", reply_markup=keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, bank_account, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_requisites_choice")
    @prevent_double_click(timeout=3.0)
    def back_to_requisites_choice(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        try:
            bot.delete_message(call.message.chat.id, user_temp_data[agent_id]['contract_data']['message_id'])
        except:
            pass
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"agent_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"agent_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_place_choice"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_bank")
    @prevent_double_click(timeout=3.0)
    def back_to_bank(call):
        """Возврат к вводу банка"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        try:
            bot.delete_message(call.message.chat.id, user_temp_data[agent_id]['contract_data']['message_id'])
        except:
            pass
        # Возвращаемся к выбору: вводить реквизиты или отказаться
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"agent_next_bank"))
        keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"agent_cancel_bank"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_place_choice"))
        context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
        
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
            user_temp_data[message.from_user.id]['contract_data'] = data
            keyboard = create_back_keyboard("back_to_bank_account_corr")
            message = bot.send_message(
                message.chat.id,
                text="Введите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
        else:
            keyboard = create_back_keyboard("back_to_bank_account")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите счет получателя, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_bank_account")
    @prevent_double_click(timeout=3.0)
    def back_to_bank_account(call):
        """Возврат к вводу счета получателя"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_bank")
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
            user_temp_data[message.from_user.id]['contract_data'] = data
            keyboard = create_back_keyboard("back_to_BIK")
            message = bot.send_message(
                message.chat.id,
                text="Введите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, BIK, data, user_message_id)
        else:
            keyboard = create_back_keyboard("back_to_bank_account_corr")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, счет должен состоять только из цифр!\nВведите корреспондентский счет банка, 20 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, bank_account_corr, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_bank_account_corr")
    @prevent_double_click(timeout=3.0)
    def back_to_bank_account_corr(call):
        """Возврат к вводу корр. счета"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_bank_account")
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
            user_temp_data[message.from_user.id]['contract_data'] = data
            keyboard = create_back_keyboard("back_to_INN")
            message = bot.send_message(
                message.chat.id,
                text="Введите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)
        else:
            keyboard = create_back_keyboard("back_to_BIK")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, БИК должен состоять только из цифр!\nВведите БИК банка, 9 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, BIK, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_BIK")
    @prevent_double_click(timeout=3.0)
    def back_to_BIK(call):
        """Возврат к вводу БИК"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_bank_account_corr")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите корреспондентский счет банка, 20 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, bank_account_corr, data, msg.message_id)
    def INN(message, data, user_message_id):
        agent_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_temp_data[agent_id]['contract_data']['message_id'])
        except:
            pass
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        if message.text.isdigit() and len(message.text) == 10:
            data.update({"INN": message.text})

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
                    [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["place"]),
                    str(data["number_photo"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"])],
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
                    [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["place"]),
                    str(data["number_photo"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"]), str(data["address_park"])],
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
                    [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["place"]),
                    str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"]), str(data["address_park"])],
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
                    [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["place"]),
                    str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"])],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую клиент по форме ГИБДД.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            try:
                with open(f"clients/{data['client_id']}/Документы/Заявление в страховую.docx", 'rb') as document_file:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}")) 
                    if data.get('sobstvenik', '') != 'С начала':
                        bot.send_document(int(data['user_id']), document_file, reply_markup=keyboard)
                    else:
                        bot.send_document(message.chat.id, document_file)  
            except FileNotFoundError:
                bot.send_message(message.chat.id, f"Файл не найден")

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"agent_request_act_payment_{data['client_id']}"))
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))    
            bot.send_message(
                message.chat.id,
                "✅ Заявление в страховую успешно сформировано!",
                reply_markup=keyboard
            )
            
            if agent_id in user_temp_data:
                user_temp_data.pop(agent_id, None)
            
        else:
            keyboard = create_back_keyboard("back_to_INN")
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, INN, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_INN")
    @prevent_double_click(timeout=3.0)
    def back_to_INN(call):
        """Возврат к вводу ИНН"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        keyboard = create_back_keyboard("back_to_BIK")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите БИК банка, 9 цифр",
            reply_markup=keyboard
        )

        bot.register_next_step_handler(msg, BIK, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_protocol_photos_upload_agent_'))
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
                btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_doc_choice")  # ДОБАВЛЕНО
                keyboard.add(btn_finish)
                keyboard.add(btn_back)
                
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
            create_pdf_from_images_agent2(photos, pdf_path)
            
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
            btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_upload_agent_{agent_id}")
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_protocol_photos")  # ДОБАВЛЕНО
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
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_requisites_or_protocol")
    @prevent_double_click(timeout=3.0)
    def back_to_requisites_or_protocol(call):
        """Возврат к реквизитам или протоколу"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        # Если реквизиты не заполнены (БИК = "-"), возвращаемся к выбору
        if data.get('BIK') == '-':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"agent_next_bank"))
            keyboard.add(types.InlineKeyboardButton("Отказаться от ввода реквизитов", callback_data=f"agent_cancel_bank"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_number_photo_or_health"))
            
            context = "Укажите реквизиты банковского счёта для перечисления денежной компенсации. Они потребуются, если страховая компания не сможет организовать восстановительный ремонт.\n\nЕсли реквизиты не будут указаны, денежные средства будут автоматически направлены в почтовое отделение по месту вашей регистрации."
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=context,
                reply_markup=keyboard
            )
        else:
            # Если реквизиты заполнены, возвращаемся к ИНН
            keyboard = create_back_keyboard("back_to_BIK")
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите ИНН банка, 10 цифр",
                reply_markup=keyboard
            )
            
            save_message = msg.message_id
            bot.register_next_step_handler(msg, INN, data, msg.message_id, save_message)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_protocol_photos")
    @prevent_double_click(timeout=3.0)
    def back_to_protocol_photos(call):
        """Возврат к загрузке фото протокола"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]['contract_data']
        
        # Инициализируем хранилище для фото протокола заново
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        user_temp_data[agent_id]['protocol_photos'] = []
        user_temp_data[agent_id]['contract_data'] = data

        keyboard = types.InlineKeyboardMarkup()
        btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_protocol_photos_upload_agent_{agent_id}")
        btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_doc_choice")
        keyboard.add(btn_finish)
        keyboard.add(btn_back)

        # Определяем текст в зависимости от типа протокола
        if data.get("who_dtp", '') == 'Евро-протокол':
            protocol_text = "Евро-протокола"
        else:
            protocol_text = "протокола ГИБДД"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📸 Прикрепите фото {protocol_text}\n\n"
                "Фото должны быть четкими, не засвечены.\n"
                "Можно отправлять по одной фотографии или несколько сразу.\n"
                "Когда загрузите все фото, нажмите кнопку ниже:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_dtp_photos_upload_agent_'))
    @prevent_double_click(timeout=3.0)
    def finish_dtp_photos_upload_callback(call):
        """Завершение загрузки фото ДТП"""
        agent_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if agent_id not in user_temp_data or 'dtp_photos' not in user_temp_data[agent_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[agent_id]['dtp_photos']
            data = user_temp_data[agent_id]['contract_data']
            print(data)
            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_upload_agent_{agent_id}")
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
            create_pdf_from_images_agent2(photos, pdf_path)

            try:
                # Очищаем временные данные
                user_temp_data[agent_id].pop('dtp_photos', None)
            except:
                print(123)
                pass
            print(2)
            fields_to_remove = [
                'pts_timer', 'dkp_timer', 'protocol_timer', 'dtp_timer', 'dov_timer', 'dtp_cabinet_timer',
                'pts_photos', 'dkp_photos', 'protocol_photos', 'dtp_photos', 'dtp_photos_cabinet', 'doverennost_photos',
                'driver_license_front', 'driver_license_back', 'sts_front', 'sts_back', 'message_id2', 'message_id',
                'editing_contract', 'editing_field', 'client_user_id', 'contract_data', 'step_history', 'add_client_mode', 'search_fio'
            ]
            
            for field in fields_to_remove:
                data.pop(field, None)
            print(3)
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            client_id = data['client_id']
            keyboard = types.InlineKeyboardMarkup()
            if data['accident'] == 'ДТП':
                if data['sobstvenik'] != 'С начала':
                    keyboard.add(types.InlineKeyboardButton("Заполнить заявление в страховую ", callback_data=f"dtp_continue_documents_{client_id}"))
                keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"agent_request_act_payment_{data['client_id']}"))  
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))
            
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Выберите из следующих вариантов",
                    reply_markup=keyboard
                )
            elif data['accident'] == 'Подал заявление':
                keyboard.add(types.InlineKeyboardButton("Продолжить", callback_data=f"agent_podal_continue_documents_{client_id}"))
                keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"agent_request_act_payment_{data['client_id']}"))  
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))
            
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Готовы продолжить заполнение?",
                    reply_markup=keyboard
                )
            elif data['accident'] == 'Нет ОСАГО':
                keyboard.add(types.InlineKeyboardButton("📄 Заявление о выдаче из ГИБДД", callback_data=f"agent_net_osago_continue_documents_{client_id}"))
                keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"agent_request_act_payment_{data['client_id']}"))  
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))
            
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Готовы продолжить заполнение?",
                    reply_markup=keyboard
                )    
            else:
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))
                bot.send_message(
                    chat_id=call.message.chat.id,
                    text="Данные сохранены",
                    reply_markup=keyboard
                )
        except Exception as e:
            print(f"Ошибка при сохранении фото ДТП: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении фото.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_podal_continue_documents_"))
    @prevent_double_click(timeout=3.0)
    def agent_podal_continue_documents(call):
        """Заявление на доп осмотр от агента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        agent_id = call.from_user.id
        try:
            bot.delete_message(call.message.chat.id, user_temp_data[agent_id]['message_id'])
        except:
            pass
        client_id = call.data.replace("agent_podal_continue_documents_", "")
        keyboard = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("💰 На выплату", callback_data=f"podal_viplata_{client_id}")
        btn_no = types.InlineKeyboardButton("🛠️ На ремонт", callback_data=f"podal_rem_{client_id}")
        keyboard.add(btn_yes, btn_no)
        keyboard.add(types.InlineKeyboardButton("📄 Вернуться к договору", callback_data=get_contract_callback(agent_id, client_id)))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Было подано заявление на выплату или на ремонт?",
            reply_markup = keyboard
        )
        
    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_dop_osm_"))
    @prevent_double_click(timeout=3.0)
    def callback_agent_dop_osm(call):
        """Заявление на доп осмотр от агента"""
        agent_id = call.from_user.id
        client_id = call.data.replace("agent_dop_osm_", "")
        
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
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        
        user_temp_data[agent_id]['dop_osm_data'] = data
        user_temp_data[agent_id]['client_id'] = client_id
        user_temp_data[agent_id]['client_user_id'] = contract.get('user_id')
        
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
        bot.register_next_step_handler(msg2, agent_dop_osm_nv_ins, agent_id, user_message_id, msg.message_id)


    def agent_dop_osm_nv_ins(message, agent_id, user_message_id, message_id):
        """Обработка входящего номера"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['dop_osm_data']
        data['Nv_ins'] = message.text.strip()
        save_step_state(agent_id, 'dop_osm_nv_ins', data)
        
        keyboard = create_back_keyboard("back_to_dop_osm_start")
        msg = bot.send_message(message.chat.id, "Введите номер акта осмотра ТС", reply_markup=keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_na_ins, agent_id, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dop_osm_start")
    @prevent_double_click(timeout=3.0)
    def back_to_dop_osm_start(call):
        """Возврат к началу доп. осмотра"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🤖 Подготовьте:\n1. Принятое страховой Заявление\n2. Акт осмотра ТС\n3. Предзапись в СТО"
        )
        
        keyboard = create_back_keyboard("callback_start")
        msg2 = bot.send_message(
            chat_id=call.message.chat.id,
            text="Введите входящий номер в страховую",
            reply_markup=keyboard
        )
        user_message_id = msg2.message_id
        bot.register_next_step_handler(msg2, agent_dop_osm_nv_ins, agent_id, user_message_id, msg.message_id)

    def agent_dop_osm_na_ins(message, agent_id, user_message_id):
        """Обработка номера акта осмотра"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['dop_osm_data']
        data['Na_ins'] = message.text.strip()
        save_step_state(agent_id, 'dop_osm_na_ins', data)
        
        keyboard = create_back_keyboard("back_to_dop_osm_nv_ins")
        msg = bot.send_message(message.chat.id, "Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_date_na_ins, agent_id, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dop_osm_nv_ins")
    @prevent_double_click(timeout=3.0)
    def back_to_dop_osm_nv_ins(call):
        """Возврат к вводу входящего номера"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_back_keyboard("back_to_dop_osm_start")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите входящий номер в страховую",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_nv_ins, agent_id, user_message_id, msg.message_id)
    def agent_dop_osm_date_na_ins(message, agent_id, user_message_id):
        """Обработка даты акта осмотра"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data = user_temp_data[agent_id]['dop_osm_data']
            data['date_Na_ins'] = message.text.strip()
            save_step_state(agent_id, 'dop_osm_date_na_ins', data)
            
            keyboard = create_back_keyboard("back_to_dop_osm_na_ins")
            msg = bot.send_message(message.chat.id, "Введите адрес СТО клиента", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_address_sto, agent_id, user_message_id)
        except ValueError:
            keyboard = create_back_keyboard("back_to_dop_osm_nv_ins")
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_date_na_ins, agent_id, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dop_osm_na_ins")
    @prevent_double_click(timeout=3.0)
    def back_to_dop_osm_na_ins(call):
        """Возврат к вводу номера акта"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_back_keyboard("back_to_dop_osm_nv_ins")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер акта осмотра ТС",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_na_ins, agent_id, user_message_id)
    def agent_dop_osm_address_sto(message, agent_id, user_message_id):
        """Обработка адреса СТО"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['dop_osm_data']
        data['address_sto_main'] = message.text.strip()
        save_step_state(agent_id, 'dop_osm_address_sto', data)
        
        keyboard = create_back_keyboard("back_to_dop_osm_address_sto")
        msg = bot.send_message(message.chat.id, "Введите дату записи в СТО в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_date_sto, agent_id, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dop_osm_address_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_dop_osm_address_sto(call):
        """Возврат к вводу адреса СТО"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_back_keyboard("back_to_dop_osm_na_ins")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_date_na_ins, agent_id, user_message_id)

    def agent_dop_osm_date_sto(message, agent_id, user_message_id):
        """Обработка даты записи в СТО"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data = user_temp_data[agent_id]['dop_osm_data']
            data['date_sto_main'] = message.text.strip()
            save_step_state(agent_id, 'dop_osm_date_sto', data)
            
            keyboard = create_back_keyboard("back_to_dop_osm_date_sto")
            msg = bot.send_message(message.chat.id, "Введите время записи в СТО в формате ЧЧ:ММ", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_time_sto, agent_id, user_message_id)
        except ValueError:
            keyboard = create_back_keyboard("back_to_dop_osm_address_sto")
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату записи в СТО в формате ДД.ММ.ГГГГ", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_date_sto, agent_id, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_dop_osm_date_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_dop_osm_date_sto(call):
        """Возврат к вводу даты СТО"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        keyboard = create_back_keyboard("back_to_dop_osm_address_sto")
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес СТО клиента",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_address_sto, agent_id, user_message_id)
    def agent_dop_osm_time_sto(message, agent_id, user_message_id):
        """Обработка времени записи в СТО - ФИНАЛ для доп осмотра"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text) != 5 or message.text.count(':') != 1:
            keyboard = create_back_keyboard("back_to_dop_osm_date_sto")
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат времени!\nВведите время в формате ЧЧ:ММ (например: 14:30)", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_time_sto, agent_id, user_message_id)
            return
        
        try:
            datetime.strptime(message.text, "%H:%M")
            
            data = user_temp_data[agent_id]['dop_osm_data']
            data['time_sto_main'] = message.text.strip()
            data['dop_osm'] = "Yes"
            data['data_dop_osm'] = datetime.now().strftime("%d.%m.%Y")
            
            # Обновляем в БД
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            
            # Формируем документ
            client_id = user_temp_data[agent_id]['client_id']
            
            if data.get("N_dov_not", '') != '':
                template_path = "Шаблоны/1. ДТП/1. На ремонт/4. Заявление о проведении доп осмотра/4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx"
                output_filename = "Заявление о проведении дополнительного осмотра автомобиля представитель.docx"
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                    "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
                    "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}", 
                    "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Дата_ДТП }}", "{{ Телефон_представителя }}",
                    "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Дата_осмотра }}", "{{ Дата_свое_СТО }}", 
                    "{{ Время_свое_СТО }}", "{{ Адрес_свое_СТО }}", "{{ Телефон }}", "{{ Дата_заявления_доп_осмотр }}"],
                    [str(data.get("insurance", "")), str(data.get("city", "")), str(data.get("fio", "")), 
                    str(data.get("date_of_birth", "")), str(data.get("seria_pasport", "")), 
                    str(data.get("number_pasport", "")), str(data.get("where_pasport", "")), 
                    str(data.get("when_pasport", "")), str(data.get("N_dov_not", "")), str(data.get("data_dov_not", "")), str(data.get("fio_not", "")), 
                    str(data.get("number_not", "")), str(data.get("Na_ins", "")), str(data.get("date_ins", "")), str(data.get("date_dtp", "")), 
                    str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
                    str(data.get("date_Na_ins", "")), str(data.get("date_sto_main", "")), 
                    str(data.get("time_sto_main", "")), str(data.get("address_sto_main", "")), 
                    str(data.get("number", "")), str(data.get("data_dop_osm", ""))],
                    template_path,
                    f"clients/{client_id}/Документы/{output_filename}"
                )
            else:
                template_path = "Шаблоны/1. ДТП/1. На ремонт/4. Заявление о проведении доп осмотра/4. Заявление о проведении дополнительного осмотра автомобиля.docx"
                output_filename = "Заявление о проведении дополнительного осмотра автомобиля.docx"
            
                replace_words_in_word(
                    ["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                    "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
                    "{{ Паспорт_когда }}", "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Дата_ДТП }}", 
                    "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Дата_осмотра }}", "{{ Дата_свое_СТО }}", 
                    "{{ Время_свое_СТО }}", "{{ Адрес_свое_СТО }}", "{{ Телефон }}", "{{ Дата_заявления_доп_осмотр }}"],
                    [str(data.get("insurance", "")), str(data.get("city", "")), str(data.get("fio", "")), 
                    str(data.get("date_of_birth", "")), str(data.get("seria_pasport", "")), 
                    str(data.get("number_pasport", "")), str(data.get("where_pasport", "")), 
                    str(data.get("when_pasport", "")), str(data.get("Na_ins", "")), 
                    str(data.get("date_ins", "")), str(data.get("date_dtp", "")), 
                    str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
                    str(data.get("date_Na_ins", "")), str(data.get("date_sto_main", "")), 
                    str(data.get("time_sto_main", "")), str(data.get("address_sto_main", "")), 
                    str(data.get("number", "")), str(data.get("data_dop_osm", ""))],
                    template_path,
                    f"clients/{client_id}/Документы/{output_filename}"
                    )
            
            # Отправляем документ агенту
            try:
                with open(f"clients/{client_id}/Документы/{output_filename}", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📋 Запрос о выдаче акта и расчета", callback_data=f"agent_request_act_payment_{data['client_id']}"))  
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))
                    bot.send_document(message.chat.id, doc, caption="📋 Заявление на дополнительный осмотр", reply_markup=keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            
            # Уведомляем клиента
            client_user_id = user_temp_data[agent_id].get('client_user_id')
            if client_user_id and str(client_user_id) != '8572367590':
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    bot.send_message(
                        int(client_user_id),
                        f"✅ Заявление на дополнительный осмотр авто составлено, ознакомиться с ним можно в личном кабинете",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления клиенту: {e}")
            
            # Очищаем временные данные
            if agent_id in user_temp_data:
                if 'dop_osm_data' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['dop_osm_data']
                if 'client_id' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['client_id']
                if 'client_user_id' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['client_user_id']
        except ValueError:
            keyboard = create_back_keyboard("back_to_dop_osm_date_sto")
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат времени!\nВведите время в формате ЧЧ:ММ (например: 14:30)", reply_markup=keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_time_sto, agent_id, user_message_id)


    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_answer_insurance_"))
    @prevent_double_click(timeout=3.0)
    def callback_agent_answer_insurance(call):
        """Ответ от страховой от агента"""
        agent_id = call.from_user.id
        client_id = call.data.replace("agent_answer_insurance_", "")
        
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
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        
        user_temp_data[agent_id] = data
        user_temp_data[agent_id]['client_id'] = client_id
        user_temp_data[agent_id]['client_user_id'] = contract.get('user_id')
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("💰 Получена выплата", callback_data="agent_answer_payment"))
        keyboard.add(types.InlineKeyboardButton("🔧 Получено направление на ремонт", callback_data="agent_answer_repair"))
        keyboard.add(types.InlineKeyboardButton("📋 У виновника ДТП Нет ОСАГО", callback_data=f"NoOsago_prod_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(agent_id, client_id)))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Что получено от страховой?",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "agent_answer_payment")
    @prevent_double_click(timeout=3.0)
    def agent_answer_payment(call):
        """Получена выплата - запрашиваем сумму"""
        agent_id = call.from_user.id
        client_id = user_temp_data[agent_id]['client_id']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("💰 Тотал, выплата 400к₽", callback_data=f"agent_total_answer_insurance"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_answer_insurance_{client_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💰 Введите сумму выплаты по ОСАГО (только число):",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(call.message, process_insurance_payment_amount, agent_id, call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "agent_total_answer_insurance")
    @prevent_double_click(timeout=3.0)
    def agent_total_answer_insurance(call):
        """Получена полная выплата """
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        client_id = user_temp_data[agent_id]['client_id']
        data = user_temp_data[agent_id]
        data.update({'coin_osago': '400000'})
        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
            print(data)
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
        create_fio_data_file(data)
        # Сохраняем сумму для загрузки квитанции
        user_temp_data[agent_id] = data
        user_temp_data[agent_id]['insurance_osago_amount'] = '400000'
        user_temp_data[agent_id]['insurance_osago_total'] = '400000'
        
        # Инициализируем сессию загрузки квитанции
        chat_id = call.message.chat.id
        upload_sessions[chat_id] = {
            'client_id': agent_id,
            'photos': [],
            'message_id': None,
            'number_id': client_id,
            'type': 'insurance_payment'  # Маркер для различения типа загрузки
        }
        
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💰 Общая сумма выплат: 400000 руб.\n\n📸 Теперь загрузите квитанцию (одну или несколько фотографий):",
            reply_markup=create_upload_keyboard_insurance()
        )
        upload_sessions[chat_id]['message_id'] = msg.message_id

    @bot.callback_query_handler(func=lambda call: call.data in ["agent_total_answer_insurance_ura", "agent_total_answer_insurance_delict"])
    @prevent_double_click(timeout=3.0)
    def agent_total_answer_insurance_ura(call):
        """Получена выплата - запрашиваем сумму"""
        agent_id = call.from_user.id
        client_id = user_temp_data[agent_id]['client_id']
        data = user_temp_data[agent_id]
        if call.data == "agent_total_answer_insurance_ura":
            data.update({'status': 'Завершен'})
            context = "Поздравляем с завершением дела"
        else:
            data.update({'status': 'Деликт'})
            context = "Исковое заявление формируется, напомните клиенту о необходимости загрузки доверенности и подтверждения оплаты"

        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
            print(data)
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
        create_fio_data_file(data)

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(agent_id, client_id))) 
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )   

    def process_insurance_payment_amount(message, agent_id, prev_message_id):
        """Обработка суммы выплаты от страховой"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            amount = float(message.text.strip().replace(',', '.'))
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Введите корректное число:")
            bot.register_next_step_handler(msg, process_insurance_payment_amount, agent_id, msg.message_id)
            return
        
        client_id = user_temp_data[agent_id]['client_id']
        
        # Получаем текущее значение coin_osago
        from database import get_client_from_db_by_client_id
        client_data = get_client_from_db_by_client_id(client_id)
        
        try:
            data = json.loads(client_data.get('data_json', '{}'))
        except:
            data = client_data
        try:
            # Получаем текущую сумму (из data_json ИЛИ из основного поля)
            current_osago = float(data.get('coin_osago', 0))
            if current_osago == 0 and data.get('coin_osago'):
                try:
                    current_osago = float(data.get('coin_osago', 0))
                except:
                    current_osago = 0
                    
        except Exception as e:
            print(f"Ошибка получения текущей суммы: {e}")
            current_osago = 0
        
        # Прибавляем новую сумму
        new_total = current_osago + amount
        print(f"DEBUG: current_osago={current_osago}, amount={amount}, new_total={new_total}")
        # Обновляем в базе
        data['coin_osago'] = str(new_total)
        
        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(data)
            client_data.update(updated_data)
            print(client_data)
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
        create_fio_data_file(data)
        # Сохраняем сумму для загрузки квитанции
        user_temp_data[agent_id] = client_data
        user_temp_data[agent_id]['insurance_osago_amount'] = amount
        user_temp_data[agent_id]['insurance_osago_total'] = new_total
        
        # Инициализируем сессию загрузки квитанции
        chat_id = message.chat.id
        upload_sessions[chat_id] = {
            'client_id': agent_id,
            'photos': [],
            'message_id': None,
            'number_id': client_id,
            'type': 'insurance_payment'  # Маркер для различения типа загрузки
        }
        
        msg = bot.send_message(
            chat_id,
            f"✅ Добавлено: {amount} руб.\n"
            f"💰 Общая сумма выплат: {new_total} руб.\n\n"
            f"📸 Теперь загрузите квитанцию (одну или несколько фотографий):",
            reply_markup=create_upload_keyboard_insurance()
        )
        
        upload_sessions[chat_id]['message_id'] = msg.message_id


    def create_upload_keyboard_insurance():
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_upload_insurance_payment"))
        return keyboard


    @bot.callback_query_handler(func=lambda call: call.data == 'finish_upload_insurance_payment')
    def handle_finish_upload_insurance_payment(call):
        """Завершение загрузки квитанции после выплаты от страховой"""
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
            try:
            # Удаляем сообщение с кнопкой
                bot.delete_message(chat_id, session['message_id'])
            except:
                pass
            
            user_id = session['client_id']
            osago_amount = user_temp_data.get(user_id, {}).get('insurance_osago_amount', 0)
            osago_total = user_temp_data.get(user_id, {}).get('insurance_osago_total', 0)
            data = user_temp_data.get(user_id, {})
            print(data)
            if data['coin_osago'] == '400000':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("👌 Ура", callback_data=f"agent_total_answer_insurance_ura"))
                keyboard.add(types.InlineKeyboardButton("⚖️ Деликт", callback_data=f"agent_total_answer_insurance_delict"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_answer_payment"))

                bot.send_message(
                    chat_id,
                    "Выберите из предложенных вариантов",
                    reply_markup = keyboard
                )
                try:
                    # Очищаем сессию
                    del upload_sessions[chat_id]
                    if user_id in user_temp_data:
                        user_temp_data[user_id].pop('insurance_osago_amount', None)
                        user_temp_data[user_id].pop('insurance_osago_total', None)
                        data.pop('insurance_osago_amount', None)
                        data.pop('insurance_osago_total', None)
                except:
                    pass

            else:

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Да", callback_data="agent_docs_ins_yes"))
                keyboard.add(types.InlineKeyboardButton("Нет", callback_data="agent_docs_ins_no"))
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_answer_insurance_{client_id}"))

                bot.send_message(
                    chat_id,
                    f"✅ Квитанция успешно сохранена как '{filename}'!\n"
                    f"💰 Добавлено: {osago_amount} руб.\n"
                    f"💰 Итого выплат: {osago_total} руб.\n"
                    f"📸 Загружено фото: {len(session['photos'])}\n\n"
                    f"Необходимо заявление на выдачу документов из страховой?",
                    reply_markup = keyboard
                )
                
                try:
                    # Очищаем сессию
                    del upload_sessions[chat_id]
                    if user_id in user_temp_data:
                        user_temp_data[user_id].pop('insurance_osago_amount', None)
                        user_temp_data[user_id].pop('insurance_osago_total', None)
                        data.pop('insurance_osago_amount', None)
                        data.pop('insurance_osago_total', None)
                except:
                    pass
            
        except Exception as e:
            print(f"Error creating PDF: {e}")
            bot.send_message(chat_id, "❌ Ошибка при создании PDF файла")
        
        bot.answer_callback_query(call.id)

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

    @bot.callback_query_handler(func=lambda call: call.data == "agent_answer_repair")
    @prevent_double_click(timeout=3.0)
    def agent_answer_repair(call):
        """Получено направление на ремонт - сразу к вопросу о заявлении"""
        agent_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data="agent_docs_ins_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data="agent_docs_ins_no"))
        client_id = user_temp_data[agent_id]['client_id']
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_answer_insurance_{client_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходимо заявление на выдачу документов из страховой?",
            reply_markup=keyboard
        )

    

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_answer_insurance_question")
    @prevent_double_click(timeout=3.0)
    def back_to_answer_insurance_question(call):
        """Возврат к вопросу о том, что получено от страховой"""
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        data = user_temp_data[agent_id]
        client_id = user_temp_data[agent_id]['client_id']
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("💰 Получена выплата", callback_data="agent_answer_payment"))
        keyboard.add(types.InlineKeyboardButton("🔧 Получено направление на ремонт", callback_data="agent_answer_repair"))
        keyboard.add(types.InlineKeyboardButton("📋 У виновника ДТП Нет ОСАГО", callback_data=f"NoOsago_prod_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(agent_id, client_id))) 
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите из предложенных вариантов",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["agent_docs_ins_yes", "agent_docs_ins_no"])
    @prevent_double_click(timeout=3.0)
    def agent_docs_insurance_choice(call):
        """Выбор: нужно ли заявление на выдачу документов"""
        agent_id = call.from_user.id
        
        if call.data == "agent_docs_ins_no":
            # Без заявления на выдачу документов
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("1", callback_data="agent_vibor1"))
            keyboard.add(types.InlineKeyboardButton("2", callback_data="agent_vibor2"))
            keyboard.add(types.InlineKeyboardButton("3", callback_data="agent_vibor3"))
            keyboard.add(types.InlineKeyboardButton("4", callback_data="agent_vibor4"))
            keyboard.add(types.InlineKeyboardButton("5", callback_data="agent_vibor5"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_answer_insurance_question"))  # Добавлена кнопка
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите из предложенных вариантов:\n\n"
                    "1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n"
                    "2) Страховая компания выдала направление на ремонт, СТО отказала.\n"
                    "3) У страховой компании нет СТО.\n"
                    "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.\n"
                    "5) Страховая компания не организовала ремонт.",
                reply_markup=keyboard
            )
        else:
            # С заявлением на выдачу документов
            data = user_temp_data[agent_id]
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            client_id = user_temp_data[agent_id]['client_id']
            
            # Выбираем нужный шаблон
            if data.get("N_dov_not", '') != '':
                template_path = "Шаблоны/1. ДТП/1. На ремонт/5. Запрос в страховую о выдаче акта и расчета/5. Запрос в страховую о выдаче акта и расчёта представитель.docx"
                output_filename = "Запрос в страховую о выдаче акта и расчёта представитель.docx"
                # Заполняем шаблон
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
                    str(data.get("when_pasport", "")), str(data.get("N_dov_not", "")), str(data.get("data_dov_not", "")), 
                    str(data.get("fio_not", "")), str(data.get("number_not", "")), str(data.get("date_dtp", "")), 
                    str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
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
                with open(f"clients/"+str(data['client_id'])+f"/Документы/{output_filename}", 'rb') as doc:
                    bot.send_document(call.message.chat.id, doc, caption="📋 Запрос на выдачу документов")
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, "❌ Ошибка: файл не найден")
            
            # Уведомляем клиента
            client_user_id = user_temp_data[agent_id].get('user_id')
            if client_user_id and str(client_user_id) != '8572367590':
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    bot.send_message(
                        int(client_user_id),
                        f"✅ Запрос на выдачу документов составлен, ознакомиться с ним можно в личном кабинете",
                        reply_markup = keyboard
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления клиенту: {e}")
            
            # Показываем дальнейшие варианты
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("1", callback_data="agent_vibor1"))
            keyboard.add(types.InlineKeyboardButton("2", callback_data="agent_vibor2"))
            keyboard.add(types.InlineKeyboardButton("3", callback_data="agent_vibor3"))
            keyboard.add(types.InlineKeyboardButton("4", callback_data="agent_vibor4"))
            keyboard.add(types.InlineKeyboardButton("5", callback_data="agent_vibor5"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_answer_insurance_question"))  # Добавлена кнопка
            
            bot.send_message(
                call.message.chat.id,
                    "1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n"
                    "2) Страховая компания выдала направление на ремонт, СТО отказала.\n"
                    "3) У страховой компании нет СТО.\n"
                    "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.\n"
                    "5) Страховая компания не организовала ремонт.\n",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_vibor"))
    @prevent_double_click(timeout=3.0)
    def agent_vibor_handler(call):
        """Обработка выбора варианта развития"""
        agent_id = call.from_user.id
        data = user_temp_data[agent_id]
        client_id = user_temp_data[agent_id]['client_id']
        client_user_id = user_temp_data[agent_id].get('user_id')
        
        data.update({"vibor": call.data.replace("agent_","")})
        if call.data in ["agent_vibor1","agent_vibor3", "agent_vibor4", "agent_vibor5"]:
            # 1 и 4 - ожидание претензии
            data['status'] = "Ожидание претензии"
            
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            create_fio_data_file(data)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(agent_id, client_id)))
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ Претензия формируется.\nУбедитесь, что у клиента нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                reply_markup = keyboard
            )
            
            if client_user_id and str(client_user_id) != '8572367590':
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(client_user_id, client_id)))
                    bot.send_message(
                        int(client_user_id),
                        "✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                        reply_markup = keyboard
                    )
                except:
                    pass

        elif call.data == "agent_vibor2":
            # 2 - заявление в СТО (СТО отказала)
            if not agent_id in user_temp_data:
                user_temp_data[agent_id] = {}

            user_temp_data[agent_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_vibor")) 
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите юридическое название СТО из направления на ремонт",
                reply_markup = keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_name, agent_id, user_message_id, data)
        
        # Очищаем временные данные только для вариантов 1, 3, 4
        if call.data != "agent_vibor2":
            if agent_id in user_temp_data:
                if 'answer_insurance_data' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['answer_insurance_data']
                if 'client_id' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['client_id']
                if 'client_user_id' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['client_user_id']

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_vibor"))
    @prevent_double_click(timeout=3.0)
    def handler_back_to_vibor(call):
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[agent_id]
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
       
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data="agent_vibor1"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data="agent_vibor2"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data="agent_vibor3"))
        keyboard.add(types.InlineKeyboardButton("4", callback_data="agent_vibor4"))
        keyboard.add(types.InlineKeyboardButton("5", callback_data="agent_vibor5"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_answer_insurance_question"))  # Добавлена кнопка
        
        bot.send_message(
            call.message.chat.id,
                "1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n"
                "2) Страховая компания выдала направление на ремонт, СТО отказала.\n"
                "3) У страховой компании нет СТО.\n"
                "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.\n"
                "5) Страховая компания не организовала ремонт.",
            reply_markup=keyboard
        )
    # Обработчики для заявления в СТО от агента
    def agent_sto_refusal_name(message, agent_id, user_message_id, data):
        """Обработка названия СТО"""
        bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({'name_sto': message.text.strip()})
        user_temp_data[agent_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_name_sto"))
        msg = bot.send_message(message.chat.id, "Введите ИНН СТО, 10 цифр", reply_markup=keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_inn, agent_id, user_message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_name_sto"))
    @prevent_double_click(timeout=3.0)
    def handler_back_to_name_sto(call):
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[agent_id]
       
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_vibor")) 
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите юридическое название СТО из направления на ремонт",
            reply_markup = keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_name, agent_id, user_message_id, data)

    def agent_sto_refusal_inn(message, agent_id, user_message_id, data):
        """Обработка ИНН СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if not message.text.isdigit() and len(message.text.replace(" ", "")) != 10:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_vibor")) 
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат! ИНН должен состоять только из 10 цифр.\nВведите ИНН СТО:",
                reply_markup = keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_inn, agent_id, user_message_id, data)
            return
        
        data.update({'inn_sto': message.text.strip()})
        user_temp_data[agent_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_inn_sto")) 
        msg = bot.send_message(message.chat.id, "Введите индекс СТО (6 цифр)", reply_markup = keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_index, agent_id, user_message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_inn_sto"))
    @prevent_double_click(timeout=3.0)
    def handler_back_to_inn_sto(call):
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[agent_id]
       
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_name_sto")) 
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите ИНН СТО, 10 цифр",
            reply_markup = keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_inn, agent_id, user_message_id, data)

    def agent_sto_refusal_index(message, agent_id, user_message_id, data):
        """Обработка индекса СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_inn_sto")) 
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат! Должно быть 6 цифр.\nВведите индекс СТО:",
                reply_markup = keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_index, agent_id, user_message_id, data)
            return

        data['index_sto'] = message.text.strip()
        user_temp_data[agent_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_index_sto")) 
        msg = bot.send_message(message.chat.id, "Введите адрес СТО", reply_markup = keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_address, agent_id, user_message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_index_sto"))
    @prevent_double_click(timeout=3.0)
    def handler_back_to_index_sto(call):
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[agent_id]
       
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_inn_sto")) 
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите индекс СТО, 6 цифр",
            reply_markup = keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_index, agent_id, user_message_id, data)

    def agent_sto_refusal_address(message, agent_id, user_message_id, data):
        """Обработка адреса СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data.update({'address_sto': message.text.strip()})
        user_temp_data[agent_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_sto")) 

        msg = bot.send_message(message.chat.id, "Введите номер направления на СТО", reply_markup = keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_n_sto, agent_id, user_message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_address_sto"))
    @prevent_double_click(timeout=3.0)
    def handler_back_to_address_sto(call):
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[agent_id]
       
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_index_sto")) 
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите адрес СТО",
            reply_markup = keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_address, agent_id, user_message_id, data)

    def agent_sto_refusal_n_sto(message, agent_id, user_message_id, data):
        """Обработка номера направления СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({'N_sto': message.text.strip()})
        user_temp_data[agent_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_N_sto")) 
        msg = bot.send_message(message.chat.id, "Введите дату передачи авто на СТО (ДД.ММ.ГГГГ)", reply_markup = keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_date_pred, agent_id, user_message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_N_sto"))
    @prevent_double_click(timeout=3.0)
    def handler_back_to_N_sto(call):
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[agent_id]
       
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_address_sto")) 
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер направления на СТО",
            reply_markup = keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_n_sto, agent_id, user_message_id, data)

    def agent_sto_refusal_date_pred(message, agent_id, user_message_id, data):
        """Обработка номера направления СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_N_sto")) 
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат ввода!\nВведите дату передачи авто на СТО (ДД.ММ.ГГГГ)"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_date_pred, agent_id, user_message_id, data)
            return
        
        data.update({'date_sto': message.text.strip()})
        user_temp_data[agent_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_sto")) 
        msg = bot.send_message(message.chat.id, "Введите дату направления на СТО (ДД.ММ.ГГГГ)", reply_markup = keyboard)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_date_napr, agent_id, user_message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_date_sto"))
    @prevent_double_click(timeout=3.0)
    def handler_back_to_date_sto(call):
        agent_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[agent_id]
       
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_N_sto")) 
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату передачи авто на СТО (ДД.ММ.ГГГГ)",
            reply_markup = keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_date_pred, agent_id, user_message_id, data)

    def agent_sto_refusal_date_napr(message, agent_id, user_message_id, data):
        """Обработка даты направления - ФИНАЛ для заявления в СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_date_sto")) 
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ:",
                reply_markup = keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_date_napr, agent_id, user_message_id, data)
            return
        
        data.update({'date_napr_sto': message.text.strip()})
        data.update({'date_zayav_sto': get_next_business_date()})
        data['status'] = "Ожидание претензии"
        
        client_id = data['client_id']
        client_user_id = data['user_id']
        
        # Обновляем в БД
        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
        
        create_fio_data_file(data)
        
        # Выбираем шаблон
        if data.get("N_dov_not", '') != '':
            template_path = "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/6. Заявление в СТО представитель.docx"
            output_filename = "Заявление в СТО представитель.docx"
                # Заполняем шаблон
            replace_words_in_word(
                ["{{ СТО }}", "{{ ИНН_СТО }}", "{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ ФИО }}", 
                "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
                "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Телефон_представителя }}",
                "{{ Номер_направления_СТО }}", "{{ Страховая }}", "{{ Дата_ДТП }}", 
                "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Дата_предоставления_ТС }}", "{{ Марка_модель }}", 
                "{{ Nавто_клиента }}", "{{ Дата_Заявления_СТО }}", "{{ ФИОк }}", "{{ Дата }}", "{{ Телефон }}"],
                [str(data.get("name_sto", "")), str(data.get("inn_sto", "")), str(data.get("index_sto", "")), 
                str(data.get("address_sto", "")), str(data.get("fio", "")), str(data.get("date_of_birth", "")), 
                str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")), 
                str(data.get("where_pasport", "")), str(data.get("when_pasport", "")), 
                str(data.get("N_dov_not", "")), str(data.get("data_dov_not", "")), str(data.get("fio_not", "")), str(data.get("number_not", "")), 
                str(data.get("N_sto", "")), str(data.get("insurance", "")), str(data.get("date_dtp", "")), 
                str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
                str(data.get("date_sto", "")), str(data.get("marks", "")), str(data.get("car_number", "")), 
                str(data.get("date_zayav_sto", "")), str(data.get("fio_k", "")), 
                str(data.get("date_ins", "")), str(data.get("number", ""))],
                template_path,
                f"clients/{client_id}/Документы/{output_filename}"
            )
        else:
            template_path = "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/6. Заявление в СТО.docx"
            output_filename = "Заявление в СТО.docx"

            # Заполняем шаблон
            replace_words_in_word(
                ["{{ СТО }}", "{{ ИНН_СТО }}", "{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ ФИО }}", 
                "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
                "{{ Паспорт_когда }}", "{{ Номер_направления_СТО }}", "{{ Страховая }}", "{{ Дата_ДТП }}", 
                "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Дата_предоставления_ТС }}",  "{{ Марка_модель }}", 
                "{{ Nавто_клиента }}", "{{ Дата_Заявления_СТО }}", "{{ ФИОк }}", "{{ Дата }}", "{{ Телефон }}"],
                [str(data.get("name_sto", "")), str(data.get("inn_sto", "")), str(data.get("index_sto", "")), 
                str(data.get("address_sto", "")), str(data.get("fio", "")), str(data.get("date_of_birth", "")), 
                str(data.get("seria_pasport", "")), str(data.get("number_pasport", "")), 
                str(data.get("where_pasport", "")), str(data.get("when_pasport", "")), 
                str(data.get("N_sto", "")), str(data.get("insurance", "")), str(data.get("date_dtp", "")), 
                str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
                str(data.get("date_sto", "")), str(data.get("marks", "")), str(data.get("car_number", "")), 
                str(data.get("date_zayav_sto", "")), str(data.get("fio_k", "")), 
                str(data.get("date_ins", "")), str(data.get("number", ""))],
                template_path,
                f"clients/{client_id}/Документы/{output_filename}"
            )
        
        # Отправляем документ агенту
        try:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(agent_id, data['client_id'])))  
            with open(f"clients/{client_id}/Документы/{output_filename}", 'rb') as doc:
                bot.send_document(message.chat.id, doc, caption="📋 Заявление в СТО", reply_markup = keyboard)
        except FileNotFoundError:
            bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
        
        # Уведомляем клиента
        if client_user_id and str(client_user_id) != '8572367590':
            try:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))  
                bot.send_message(
                    int(client_user_id),
                    "✅ Заявление в СТО составлено, ознакомиться с ним можно в личном кабинете.\n\n"
                    "Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                    reply_markup = keyboard
                )
            except Exception as e:
                print(f"Ошибка отправки уведомления клиенту: {e}")
        
        # Очищаем временные данные
        if agent_id in user_temp_data:
            del user_temp_data[agent_id]

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
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_year_auto_from_insurance"))
    return keyboard

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































