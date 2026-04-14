from telebot import types
from database import get_admin_from_db_by_user_id, search_clients_by_fio_in_db
from database import DatabaseManager, get_client_from_db_by_client_id, search_clients_by_fio_in_db, search_city_clients_by_fio_in_db, search_my_clients_by_fio_in_db, get_admin_from_db_by_user_id, get_admin_from_db_by_fio
import json
import os
import threading
import time
from PIL import Image
import re
import psycopg2.extras
from word_utils import create_fio_data_file, replace_words_in_word, get_next_business_date
from functools import wraps


active_callbacks = {}
callback_lock = threading.Lock()
def cleanup_messages(bot, chat_id, message_id, count):
        """Удаляет последние N сообщений"""
        for i in range(count):
            try:
                bot.delete_message(chat_id, message_id+1 - i)
            except:
                pass
def show_main_menu(bot, message):
    cleanup_messages(bot, message.chat.id, message.message_id, count=5)
    """Показ главного меню в зависимости от роли пользователя"""
    user_id = message.from_user.id if hasattr(message, 'from_user') else message.chat.id
    print(user_id)
    data_admin = get_admin_from_db_by_user_id(user_id)
    print(data_admin)
    if not data_admin:
        keyboard = types.InlineKeyboardMarkup()
        btn_register = types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data="btn_registratsia")
        keyboard.add(btn_register)
        
        bot.send_message(
            message.chat.id,
            "❌ Вы не зарегистрированы. Пройдите регистрацию.",
            reply_markup=keyboard
        )
        return
    
    admin_value = data_admin.get('admin_value', '')
    keyboard = types.InlineKeyboardMarkup()
    
    # Меню для разных ролей
    if admin_value == "Клиент":
        btn1 = types.InlineKeyboardButton("📋 Оформить договор", callback_data="btn_client")
        btn2 = types.InlineKeyboardButton("👥 Пригласить клиента", callback_data="btn_invite_client")
        btn3 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_client")
        btn4 = types.InlineKeyboardButton("❓ У меня вопрос", callback_data="client_ask_questions")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
    
    elif admin_value == "Агент":
        btn1 = types.InlineKeyboardButton("➕ Новый договор", callback_data="btn_add_client")
        btn2 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_my_clients")
        btn3 = types.InlineKeyboardButton("💰 Финансы", callback_data="agent_finances")
        btn4 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_agent")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
    
    elif admin_value == "Администратор":
        btn1 = types.InlineKeyboardButton("➕ Новый договор", callback_data="btn_add_client")
        btn2 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_city_clients")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_export_city_clients_table")
        btn4 = types.InlineKeyboardButton("📝 На утверждение", callback_data="director_approvals")
        btn5 = types.InlineKeyboardButton("💰 Финансы", callback_data="agent_finances")
        btn6 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_agent")

        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn5)
        keyboard.add(btn6)

    elif admin_value == "Юрист":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_city_clients")
        btn2 = types.InlineKeyboardButton("📝 Исковые заявления", callback_data="director_approvals")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")

        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)


    elif admin_value == "Директор офиса":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_city_clients")
        btn2 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_export_city_clients_table")
        btn3 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_city_admins")
        btn4 = types.InlineKeyboardButton("🔄 Изменить роль", callback_data="btn_change_role_agent")
        btn5 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_city")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn5)
    
    elif admin_value == "HR отдел":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_all_admins")
        btn3 = types.InlineKeyboardButton("🔄 Добавить сотрудника", callback_data="btn_change_role_agent")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
    
    elif admin_value == "Оценщик":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database_appraiser")
        btn2 = types.InlineKeyboardButton("🏷️ Калькуляции", callback_data="appraiser_calc")
        btn3 = types.InlineKeyboardButton("💰 Финансы", callback_data="appraiser_finances")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

    elif admin_value == "Бухгалтер":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("✍️ На подпись", callback_data="director_signatures")
        btn3 = types.InlineKeyboardButton("📊 Какая-нибудь таблица", callback_data="btn_export_all_admins")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

    elif admin_value == "Исковой отдел":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("📝 Составить иск", callback_data="director_approvals")
        keyboard.add(btn1)
        keyboard.add(btn2)
    elif admin_value == "Претензионный отдел":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database_pret")
        btn2 = types.InlineKeyboardButton("📝 Составить документ", callback_data="create_docs_pret_department")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
    elif admin_value == "IT отдел":
        btn1 = types.InlineKeyboardButton("🔄 Изменить роль", callback_data="btn_change_role")
        btn2 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")
        btn4 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_all_admins")
        btn6 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn6)
    
    elif admin_value == "Генеральный директор":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")
        btn3 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_all_admins")
        btn4 = types.InlineKeyboardButton("🔄 Изменить роль", callback_data="btn_change_role")
        btn5 = types.InlineKeyboardButton("✍️ На подпись", callback_data="director_signatures")
        btn6 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn5)
        keyboard.add(btn6)
    
    else:
        bot.send_message(
            message.chat.id,
            "❌ Неизвестная роль. Обратитесь к администратору."
        )
        return
    
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {data_admin.get('fio', 'пользователь')}!\n\nВыберите действие:",
        reply_markup=keyboard
    )


def show_main_menu_by_user_id(bot, user_id):
    print(1)
    """Показ главного меню по user_id (для случаев после подтверждения регистрации)"""
    data_admin = get_admin_from_db_by_user_id(user_id)
    
    if not data_admin:
        bot.send_message(user_id, "❌ Ошибка: данные пользователя не найдены")
        return
    
    admin_value = data_admin.get('admin_value', '')
    keyboard = types.InlineKeyboardMarkup()
    
    # Меню для разных ролей (аналогично show_main_menu)
    if admin_value == "Клиент":
        btn1 = types.InlineKeyboardButton("📋 Оформить договор", callback_data="btn_client")
        btn2 = types.InlineKeyboardButton("👥 Пригласить клиента", callback_data="btn_invite_client")
        btn3 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_client")
        btn4 = types.InlineKeyboardButton("❓ У меня вопрос", callback_data="client_ask_questions")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
    
    elif admin_value == "Агент":
        btn1 = types.InlineKeyboardButton("➕ Новый договор", callback_data="btn_add_client")
        btn2 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_my_clients")
        btn3 = types.InlineKeyboardButton("💰 Финансы", callback_data="agent_finances")
        btn4 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_agent")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
    
    elif admin_value == "Администратор":
        btn1 = types.InlineKeyboardButton("➕ Новый договор", callback_data="btn_add_client")
        btn2 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_city_clients")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_export_city_clients_table")
        btn4 = types.InlineKeyboardButton("📝 На утверждение", callback_data="director_approvals")
        btn5 = types.InlineKeyboardButton("💰 Финансы", callback_data="agent_finances")
        btn6 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_agent")

        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn5)
        keyboard.add(btn6)

    elif admin_value == "Юрист":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_city_clients")
        btn2 = types.InlineKeyboardButton("📝 Исковые заявления", callback_data="director_approvals")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")

        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)


    elif admin_value == "Директор офиса":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_city_clients")
        btn2 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_export_city_clients_table")
        btn3 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_city_admins")
        btn4 = types.InlineKeyboardButton("🔄 Изменить роль", callback_data="btn_change_role_agent")
        btn5 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet_city")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn5)
    
    elif admin_value == "HR отдел":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_all_admins")
        btn3 = types.InlineKeyboardButton("🔄 Добавить сотрудника", callback_data="btn_change_role_agent")

        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

    
    elif admin_value == "Оценщик":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database_appraiser")
        btn2 = types.InlineKeyboardButton("🏷️ Калькуляции", callback_data="appraiser_calc")
        btn3 = types.InlineKeyboardButton("💰 Финансы", callback_data="appraiser_finances")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

    elif admin_value == "Бухгалтер":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("✍️ На подпись", callback_data="director_signatures")
        btn3 = types.InlineKeyboardButton("📊 Какая-нибудь таблица", callback_data="btn_export_all_admins")

        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)

    elif admin_value == "Исковой отдел":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("📝 Составить иск", callback_data="director_approvals")

        keyboard.add(btn1)
        keyboard.add(btn2)

    elif admin_value == "Претензионный отдел":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database_pret")
        btn2 = types.InlineKeyboardButton("📝 Составить документ", callback_data="create_docs_pret_department")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
    elif admin_value == "IT отдел":
        btn1 = types.InlineKeyboardButton("🔄 Изменить роль", callback_data="btn_change_role")
        btn2 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn3 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")
        btn4 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_all_admins")
        btn6 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn6)
    
    elif admin_value == "Генеральный директор":
        btn1 = types.InlineKeyboardButton("🔍 Искать в базе", callback_data="btn_search_database")
        btn2 = types.InlineKeyboardButton("📊 Скачать таблицу по клиентам", callback_data="btn_output")
        btn3 = types.InlineKeyboardButton("👨‍💼 Скачать таблицу по агентам", callback_data="btn_export_all_admins")
        btn4 = types.InlineKeyboardButton("🔄 Изменить роль", callback_data="btn_change_role")
        btn5 = types.InlineKeyboardButton("✍️ На подпись", callback_data="director_signatures")
        btn6 = types.InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_cabinet")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)
        keyboard.add(btn5)
        keyboard.add(btn6)

    bot.send_message(
        user_id,
        f"👋 Добро пожаловать, {data_admin.get('fio', 'пользователь')}!\n\nВыберите действие:",
        reply_markup=keyboard
    )


def setup_main_menu_handlers(bot, user_temp_data, upload_sessions):
    """Регистрация обработчиков главного меню"""
    import base64
    import qrcode
    from io import BytesIO
    import re
    import config
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
    # Здесь будут обработчики кнопок главного меню
    # Пока оставляем заглушки - вы их допишете
    @bot.callback_query_handler(func=lambda call: call.data == "personal_cabinet_city")
    @prevent_double_click(timeout=3.0)
    def personal_cabinet_city_handler(call):
        """Личный кабинет с фильтром по городу (для руководителей офиса)"""
        user_id = call.from_user.id
        
        # Получаем данные из admins
        admin_data = get_admin_from_db_by_user_id(user_id)
        
        if not admin_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        admin_value = admin_data.get('admin_value', '')
        city = admin_data.get('city_admin', '')
        
        if not city:
            bot.answer_callback_query(call.id, "❌ Город не определен", show_alert=True)
            return
        
        # Получаем статистику по договорам в городе
        from database import DatabaseManager
        from datetime import datetime
        db = DatabaseManager()
        
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. Общее число клиентов в городе (у кого составлен договор)
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients
                        WHERE city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    total_clients = result[0] if result else 0
                    
                    # 2. Общее число действующих клиентов (статус != "Завершен")
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE (status != 'Завершен' AND OR status IS NULL)
                        AND city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    active_clients = result[0] if result else 0
                    
                    # 3. Общее число действующих клиентов до претензии
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE (status != 'Завершен' OR status IS NULL)
                        AND status NOT IN ('Составлено заявление к Фин.омбудсмену', 
                                        'Составлено исковое заявление', 
                                        'Составлена претензия',
                                        'Деликт')
                        AND city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    clients_before_claim = result[0] if result else 0
                    
                    # 4. Общее число действующих клиентов на стадии претензия
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Составлена претензия'
                        AND city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    clients_claim_stage = result[0] if result else 0
                    
                    # 5. Общее число действующих клиентов на стадии омбудсмен
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Составлено заявление к Фин.омбудсмену'
                        AND city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    clients_ombudsman_stage = result[0] if result else 0
                    
                    # 6. Общее число действующих клиентов на стадии иск
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Составлено исковое заявление'
                        AND city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    clients_lawsuit_stage = result[0] if result else 0
                    
                    # 7. Общее число действующих клиентов на стадии деликт
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Деликт'
                        AND city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    clients_delict_stage = result[0] if result else 0
                    
                    # 8. Финансовый поток со всех клиентов города (общее число клиентов * 25000)
                    cursor.execute("""
                        SELECT COUNT(DISTINCT c.client_id) 
                        FROM clients c
                        INNER JOIN pending_approvals pa ON c.client_id = pa.client_id
                        WHERE pa.document_type = 'payment' 
                        AND pa.status = 'approved'
                        AND c.city = %s
                    """, (city,))
                    result = cursor.fetchone()
                    paid_clients = result[0] if result else 0
                    total_income = paid_clients * 25000
                    
                    # 9. Финансовый поток на выплату за отчетный период (месяц) - зарплата
                    # Получаем текущий месяц
                    now = datetime.now()
                    start_month = now.strftime('%Y-%m-01')
                    
                    # Считаем договоры за текущий месяц в городе
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE created_at::timestamp >= %s::timestamp
                        AND city = %s
                    """, (start_month, city))
                    result = cursor.fetchone()
                    monthly_contracts = result[0] if result else 0
                    
                    # Расчет зарплаты (предположим 1000 руб за договор)
                    monthly_salary_expenses = monthly_contracts * 1000
                    
        except Exception as e:
            print(f"Ошибка получения статистики по городу: {e}")
            import traceback
            traceback.print_exc()
            total_clients = 0
            active_clients = 0
            clients_before_claim = 0
            clients_claim_stage = 0
            clients_ombudsman_stage = 0
            clients_lawsuit_stage = 0
            clients_delict_stage = 0
            total_income = 0
            monthly_contracts = 0
            monthly_salary_expenses = 0
        
        # Формируем текст личного кабинета
        cabinet_text = f"👤 <b>Личный кабинет</b>\n\n"
        cabinet_text += f"<b>Личные данные:</b>\n"
        cabinet_text += f"👤 ФИО: {admin_data.get('fio', 'Не указано')}\n"
        cabinet_text += f"📱 Телефон: {admin_data.get('number', 'Не указан')}\n"
        cabinet_text += f"🏙 Город: {city}\n"
        cabinet_text += f"👔 Роль: {admin_value}\n\n"
        
        cabinet_text += f"<b>📊 Статистика по городу {city}:</b>\n\n"
        cabinet_text += f"1️⃣ Общее число клиентов: <b>{total_clients}</b>\n"
        cabinet_text += f"2️⃣ Действующих клиентов: <b>{active_clients}</b>\n"
        cabinet_text += f"3️⃣ До претензии: <b>{clients_before_claim}</b>\n"
        cabinet_text += f"4️⃣ На стадии претензии: <b>{clients_claim_stage}</b>\n"
        cabinet_text += f"5️⃣ На стадии омбудсмен: <b>{clients_ombudsman_stage}</b>\n"
        cabinet_text += f"6️⃣ На стадии иск: <b>{clients_lawsuit_stage}</b>\n"
        cabinet_text += f"7️⃣ На стадии деликт: <b>{clients_delict_stage}</b>\n\n"
        
        cabinet_text += f"<b>💰 Финансы города {city}:</b>\n"
        cabinet_text += f"8️⃣ Общий доход: <b>{total_income:,} ₽</b>\n"
        cabinet_text += f"   (договоров за месяц: {monthly_contracts})\n"
        cabinet_text += f"9️⃣ Зарплата за месяц: <b>{monthly_salary_expenses:,} ₽</b>\n"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=cabinet_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "client_ask_questions")
    @prevent_double_click(timeout=3.0)
    def handler_ask_client(call):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📞 Заказать звонок", callback_data="callback_client_phone"))
        #keyboard.add(types.InlineKeyboardButton("💬 Написать в чат", callback_data="callback"))
        keyboard.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="callback_start"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔍 Выберите из следующих вариантов",
            reply_markup = keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "btn_change_role")
    @prevent_double_click(timeout=3.0)
    def start_change_role(call):
        """Начало процесса изменения роли - запрос ФИО для поиска"""
        user_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔍 Введите ФИО пользователя для поиска в базе администраторов:"
        )
        
        # Сохраняем состояние поиска
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['change_role_search'] = True
        
        bot.register_next_step_handler(call.message, process_search_admin, call.message.message_id)
    
    
    def process_search_admin(message, prev_message_id):
        """Обработка поиска администратора по ФИО"""
        user_id = message.from_user.id
        search_term = message.text.strip()
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
        except:
            pass
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(search_term) < 2:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="callback_start"))
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Введите минимум 2 символа для поиска.",
                reply_markup=keyboard
            )
            return
        
        # Поиск в базе администраторов
        results = search_admins_by_fio(search_term)
        
        if not results:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔄 Повторить поиск", callback_data="btn_change_role"))
            keyboard.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="callback_start"))
            
            bot.send_message(
                message.chat.id,
                f"❌ Пользователи с ФИО '{search_term}' не найдены.",
                reply_markup=keyboard
            )
            return
        
        # Показываем результаты поиска
        keyboard = types.InlineKeyboardMarkup()
        
        response = f"🔍 Найдено пользователей: {len(results)}\n\n"
        
        for i, admin in enumerate(results[:10], 1):  # Ограничиваем 10 результатами
            fio = admin.get('fio', 'Не указано')
            admin_value = admin.get('admin_value', 'Не указано')
            city = admin.get('city_admin', 'Не указан')
            number = admin.get('number', 'Не указан')
            admin_id = admin.get('id')
            
            response += f"{i}. {fio}\n"
            response += f"   📋 Роль: {admin_value}\n"
            response += f"   🏙 Город: {city}\n"
            response += f"   📱 Телефон: {number}\n\n"
            
            btn_text = f"{i}. {fio}"
            btn_callback = f"select_admin_for_role_{admin_id}"
            keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
        
        keyboard.add(types.InlineKeyboardButton("🔄 Новый поиск", callback_data="btn_change_role"))
        keyboard.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="callback_start"))
        
        bot.send_message(message.chat.id, response, reply_markup=keyboard)
    
    @bot.callback_query_handler(func=lambda call: call.data == "btn_change_role_agent")
    @prevent_double_click(timeout=3.0)
    def start_change_role_agent(call):
        """Начало процесса изменения роли агента (без ЦПР) - запрос ФИО для поиска"""
        user_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔍 Введите ФИО пользователя для поиска в базе администраторов:"
        )
        
        # Сохраняем состояние поиска
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['change_role_agent_search'] = True
        
        bot.register_next_step_handler(call.message, process_search_admin_agent, call.message.message_id)


    def process_search_admin_agent(message, prev_message_id):
        """Обработка поиска администратора по ФИО (для смены роли агента)"""
        user_id = message.from_user.id
        search_term = message.text.strip()
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
        except:
            pass
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(search_term) < 2:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="callback_start"))
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Введите минимум 2 символа для поиска.",
                reply_markup=keyboard
            )
            return
        
        # Поиск в базе администраторов
        results = search_admins_by_fio(search_term)
        
        if not results:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔄 Повторить поиск", callback_data="btn_change_role_agent"))
            keyboard.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="callback_start"))
            
            bot.send_message(
                message.chat.id,
                f"❌ Пользователи с ФИО '{search_term}' не найдены.",
                reply_markup=keyboard
            )
            return
        
        # Показываем результаты поиска
        keyboard = types.InlineKeyboardMarkup()
        
        response = f"🔍 Найдено пользователей: {len(results)}\n\n"
        
        for i, admin in enumerate(results[:10], 1):  # Ограничиваем 10 результатами
            fio = admin.get('fio', 'Не указано')
            admin_value = admin.get('admin_value', 'Не указано')
            city = admin.get('city_admin', 'Не указан')
            number = admin.get('number', 'Не указан')
            admin_id = admin.get('id')
            
            response += f"{i}. {fio}\n"
            response += f"   📋 Роль: {admin_value}\n"
            response += f"   🏙 Город: {city}\n"
            response += f"   📱 Телефон: {number}\n\n"
            
            btn_text = f"{i}. {fio}"
            btn_callback = f"select_admin_for_agent_role_{admin_id}"
            keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
        
        keyboard.add(types.InlineKeyboardButton("🔄 Новый поиск", callback_data="btn_change_role_agent"))
        keyboard.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="callback_start"))
        
        bot.send_message(message.chat.id, response, reply_markup=keyboard)


    @bot.callback_query_handler(func=lambda call: call.data.startswith("select_admin_for_agent_role_"))
    @prevent_double_click(timeout=3.0)
    def select_admin_for_agent_role_change(call):
        """Выбор администратора для изменения роли - показываем выбор типа (Агент/Клиент, без ЦПР)"""
        admin_id = call.data.replace("select_admin_for_agent_role_", "")
        user_id = call.from_user.id
        
        # Получаем данные администратора
        admin_data = get_admin_by_id(admin_id)
        
        if not admin_data:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return
        
        # Сохраняем ID администратора для изменения
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['change_role_agent_admin_id'] = admin_id
        user_temp_data[user_id]['change_role_agent_admin_data'] = admin_data
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("👨‍💼 Агент", callback_data="change_agent_role_agent")
        btn2 = types.InlineKeyboardButton("👤 Клиент", callback_data="change_agent_role_client")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="btn_change_role_agent"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"👤 Изменение роли для: {admin_data.get('fio')}\n"
                f"Текущая роль: {admin_data.get('admin_value')}\n\n"
                f"Выберите новый тип:",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data == "change_agent_role_agent")
    @prevent_double_click(timeout=3.0)
    def select_agent_role_subcategory(call):
        """Выбор конкретной роли в категории Агент (Руководитель офиса, Администратор, Агент)"""
        user_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        
        btn1 = types.InlineKeyboardButton("👨‍💼 Руководитель офиса", callback_data="set_agent_role_Руководитель офиса")
        btn2 = types.InlineKeyboardButton("📋 Администратор", callback_data="set_agent_role_Администратор")
        btn3 = types.InlineKeyboardButton("👤 Агент", callback_data="set_agent_role_Агент")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        # Получаем данные администратора
        admin_data = user_temp_data.get(user_id, {}).get('change_role_agent_admin_data', {})
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"select_admin_for_agent_role_{user_temp_data[user_id]['change_role_agent_admin_id']}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"👤 Изменение роли для: {admin_data.get('fio')}\n\n"
                f"Выберите должность:",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data == "change_agent_role_client")
    @prevent_double_click(timeout=3.0)
    def set_agent_client_role(call):
        """Установка роли Клиент (из btn_change_role_agent)"""
        user_id = call.from_user.id
        
        admin_id = user_temp_data.get(user_id, {}).get('change_role_agent_admin_id')
        admin_data = user_temp_data.get(user_id, {}).get('change_role_agent_admin_data', {})
        
        if not admin_id:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        # Обновляем роль в БД
        success = update_admin_role(admin_id, "Клиент")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        if success:
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Роль успешно изменена!\n\n"
                    f"👤 {admin_data.get('fio')}\n"
                    f"Старая роль: {admin_data.get('admin_value')}\n"
                    f"Новая роль: Клиент",
                    reply_markup = keyboard
            )
            
            # Очищаем временные данные
            if user_id in user_temp_data:
                user_temp_data[user_id].pop('change_role_agent_admin_id', None)
                user_temp_data[user_id].pop('change_role_agent_admin_data', None)
            
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении роли", show_alert=True)


    @bot.callback_query_handler(func=lambda call: call.data.startswith("set_agent_role_"))
    @prevent_double_click(timeout=3.0)
    def confirm_agent_role_change(call):
        """Подтверждение изменения роли агента"""
        user_id = call.from_user.id
        
        # Извлекаем название роли из callback_data
        new_role = call.data.replace("set_agent_role_", "")
        
        admin_id = user_temp_data.get(user_id, {}).get('change_role_agent_admin_id')
        admin_data = user_temp_data.get(user_id, {}).get('change_role_agent_admin_data', {})
        
        if not admin_id:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        # Обновляем роль в БД
        success = update_admin_role(admin_id, new_role)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        if success:
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Роль успешно изменена!\n\n"
                    f"👤 {admin_data.get('fio')}\n"
                    f"Старая роль: {admin_data.get('admin_value')}\n"
                    f"Новая роль: {new_role}",
                    reply_markup = keyboard

            )
            
            # Очищаем временные данные
            if user_id in user_temp_data:
                user_temp_data[user_id].pop('change_role_agent_admin_id', None)
                user_temp_data[user_id].pop('change_role_agent_admin_data', None)
            

        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении роли", show_alert=True)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("select_admin_for_role_"))
    @prevent_double_click(timeout=3.0)
    def select_admin_for_role_change(call):
        """Выбор администратора для изменения роли - показываем выбор типа (ЦПР/Агент/Клиент)"""
        admin_id = call.data.replace("select_admin_for_role_", "")
        user_id = call.from_user.id
        
        # Получаем данные администратора
        admin_data = get_admin_by_id(admin_id)
        
        if not admin_data:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return
        
        # Сохраняем ID администратора для изменения
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['change_role_admin_id'] = admin_id
        user_temp_data[user_id]['change_role_admin_data'] = admin_data
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🏢 ЦПР", callback_data="change_role_CPR")
        btn2 = types.InlineKeyboardButton("👨‍💼 Офис", callback_data="change_role_agent")
        btn3 = types.InlineKeyboardButton("👤 Клиент", callback_data="change_role_client")
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="btn_change_role"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"👤 Изменение роли для: {admin_data.get('fio')}\n"
                 f"Текущая роль: {admin_data.get('admin_value')}\n\n"
                 f"Выберите новый тип:",
            reply_markup=keyboard
        )
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["change_role_CPR", "change_role_agent"])
    @prevent_double_click(timeout=3.0)
    def select_role_category(call):
        """Выбор конкретной роли в категории ЦПР или Агент"""
        user_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        
        if call.data == "change_role_CPR":
            btn1 = types.InlineKeyboardButton("👔 Генеральный директор", callback_data="set_role_Генеральный директор")
            btn2 = types.InlineKeyboardButton("💻 IT отдел", callback_data="set_role_IT отдел")
            btn3 = types.InlineKeyboardButton("⚖️ Претензионный отдел", callback_data="set_role_Претензионный отдел")
            btn4 = types.InlineKeyboardButton("🔍 Исковой отдел", callback_data="set_role_Исковой отдел")
            btn5 = types.InlineKeyboardButton("📊 Бухгалтер", callback_data="set_role_Бухгалтер")
            btn6 = types.InlineKeyboardButton("🏷️ Оценщик", callback_data="set_role_Оценщик")
            btn7 = types.InlineKeyboardButton("👥 HR отдел", callback_data="set_role_HR отдел")
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)
            keyboard.add(btn5)
            keyboard.add(btn6)
            keyboard.add(btn7)
        
        elif call.data == "change_role_agent":
            btn1 = types.InlineKeyboardButton("👨‍💼 Директор офиса", callback_data="set_role_Директор офиса")
            btn2 = types.InlineKeyboardButton("📋 Администратор", callback_data="set_role_Администратор")
            btn3 = types.InlineKeyboardButton("⚖️ Юрист", callback_data="set_role_Юрист")
            btn4 = types.InlineKeyboardButton("🤝 Агент", callback_data="set_role_Агент")
            
            keyboard.add(btn1)
            keyboard.add(btn2)
            keyboard.add(btn3)
            keyboard.add(btn4)
        
        # Получаем данные администратора
        admin_data = user_temp_data.get(user_id, {}).get('change_role_admin_data', {})
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"select_admin_for_role_{user_temp_data[user_id]['change_role_admin_id']}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"👤 Изменение роли для: {admin_data.get('fio')}\n\n"
                 f"Выберите должность:",
            reply_markup=keyboard
        )
    
    
    @bot.callback_query_handler(func=lambda call: call.data == "change_role_client")
    @prevent_double_click(timeout=3.0)
    def set_client_role(call):
        """Установка роли Клиент"""
        user_id = call.from_user.id
        
        admin_id = user_temp_data.get(user_id, {}).get('change_role_admin_id')
        admin_data = user_temp_data.get(user_id, {}).get('change_role_admin_data', {})
        
        if not admin_id:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        # Обновляем роль в БД
        success = update_admin_role(admin_id, "Клиент")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        if success:
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Роль успешно изменена!\n\n"
                     f"👤 {admin_data.get('fio')}\n"
                     f"Старая роль: {admin_data.get('admin_value')}\n"
                     f"Новая роль: Клиент",
                     reply_markup = keyboard
            )
            
            # Очищаем временные данные
            if user_id in user_temp_data:
                user_temp_data[user_id].pop('change_role_admin_id', None)
                user_temp_data[user_id].pop('change_role_admin_data', None)
            
            
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении роли", show_alert=True)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("set_role_"))
    @prevent_double_click(timeout=3.0)
    def confirm_role_change(call):
        """Подтверждение изменения роли"""
        user_id = call.from_user.id
        new_role = call.data.replace("set_role_", "")
        
        admin_id = user_temp_data.get(user_id, {}).get('change_role_admin_id')
        admin_data = user_temp_data.get(user_id, {}).get('change_role_admin_data', {})
        
        if not admin_id:
            bot.answer_callback_query(call.id, "❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        # Обновляем роль в БД
        success = update_admin_role(admin_id, new_role)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        if success:
            msg=bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Роль успешно изменена!\n\n"
                     f"👤 {admin_data.get('fio')}\n"
                     f"Старая роль: {admin_data.get('admin_value')}\n"
                     f"Новая роль: {new_role}",
                     reply_markup = keyboard
            )
            try:
                bot.send_message(
                    int(admin_data.get('user_id')),
                    text=f"✅ Роль успешно изменена!\n\n"
                        f"Старая роль: {admin_data.get('admin_value')}\n"
                        f"Новая роль: {new_role}",
                        reply_markup = keyboard
                    )
            except:
                pass
            # Очищаем временные данные
            if user_id in user_temp_data:
                user_temp_data[user_id].pop('change_role_admin_id', None)
                user_temp_data[user_id].pop('change_role_admin_data', None)
            
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении роли", show_alert=True)
    # ========== КЛИЕНТ: ПРИГЛАСИТЬ КЛИЕНТА ==========

    @bot.callback_query_handler(func=lambda call: call.data == "btn_invite_client")
    @prevent_double_click(timeout=3.0)
    def btn_invite_client_handler(call):
        """Пригласить клиента - Клиент вводит ФИО"""
        user_id = call.from_user.id
        
        # Инициализируем данные для этого процесса
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['invite_process'] = 'client'
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="👤 Введите ФИО клиента, которого хотите пригласить:\n\nФормат: Иванов Иван Иванович"
        )
        
        bot.register_next_step_handler(call.message, process_invite_fio_client, user_id, call.message.message_id)


    def process_invite_fio_client(message, client_id, prev_message_id):
        """Обработка ФИО приглашаемого клиента от клиента"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        # Проверка формата ФИО
        if len(message.text.split()) < 2:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат ввода!\nВведите ФИО в формате: Иванов Иван Иванович"
            )
            bot.register_next_step_handler(msg, process_invite_fio_client, client_id, msg.message_id)
            return
        
        words = message.text.split()
        for word in words:
            if not word[0].isupper():
                msg = bot.send_message(
                    message.chat.id,
                    "❌ Каждое слово должно начинаться с заглавной буквы!\n"
                    "Введите ФИО в формате: Иванов Иван Иванович"
                )
                bot.register_next_step_handler(msg, process_invite_fio_client, client_id, msg.message_id)
                return
        
        invited_fio = message.text.strip()
        
        # Сохраняем ФИО
        if client_id not in user_temp_data:
            user_temp_data[client_id] = {}
        user_temp_data[client_id]['invite_fio'] = invited_fio
        
        # Запрашиваем номер телефона
        msg = bot.send_message(
            message.chat.id,
            f"✅ ФИО: {invited_fio}\n\n📱 Теперь введите номер телефона клиента (например, +79001234567):"
        )
        
        bot.register_next_step_handler(msg, process_invite_phone_client, client_id, msg.message_id)


    def process_invite_phone_client(message, client_id, prev_message_id):
        """Обработка номера телефона приглашаемого клиента от клиента"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        phone = message.text.strip()
        
        # Проверка формата телефона
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат номера телефона. Введите снова (например, +79001234567):"
            )
            bot.register_next_step_handler(msg, process_invite_phone_client, client_id, msg.message_id)
            return
        
        # Сохраняем номер
        user_temp_data[client_id]['invite_phone'] = phone
        
        # Показываем кнопку для формирования ссылки
        keyboard = types.InlineKeyboardMarkup()
        btn_generate = types.InlineKeyboardButton("🔗 Сформировать ссылку", callback_data="generate_invite_link_client")
        btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data="callback_start")
        keyboard.add(btn_generate)
        keyboard.add(btn_cancel)
        
        fio = user_temp_data[client_id].get('invite_fio', '')
        
        bot.send_message(
            message.chat.id,
            f"✅ Данные клиента:\n\n"
            f"👤 ФИО: {fio}\n"
            f"📱 Телефон: {phone}\n\n"
            f"Нажмите кнопку для формирования ссылки-приглашения:",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data == "generate_invite_link_client")
    @prevent_double_click(timeout=3.0)
    def generate_invite_link_client(call):
        """Генерация ссылки-приглашения от клиента"""
        client_id = call.from_user.id
        data = user_temp_data.get(client_id, {})
        
        fio = data.get('invite_fio', '')
        phone = data.get('invite_phone', '')
        
        if not fio or not phone:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        # Получаем город клиента
        client_data = get_admin_from_db_by_user_id(client_id)
        city = client_data.get('city_admin', '') if client_data else ''
        fioSplit = fio.split()[0]
        # Кодируем только ФИО
        fio_encoded = base64.urlsafe_b64encode(fioSplit.encode('utf-8')).decode('utf-8')
        
        # Формат: invclient_clientid_fioencoded
        invite_param = f"invclient_{client_id}_{fio_encoded}"
        
        # Создаем ссылку
        bot_username = config.BOT_USERNAME
        invite_link = f"https://t.me/{bot_username}?start={invite_param}"
        
        print(f"DEBUG: Сформирована ссылка от клиента:")
        print(f"  - Client ID: {client_id}")
        print(f"  - ФИО: {fio}")
        print(f"  - Телефон: {phone}")
        print(f"  - Город: {city}")
        print(f"  - Link: {invite_link}")
        
        # Генерируем QR-код
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(invite_link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Ссылка-приглашение сформирована!\n\n"
                f"👤 Клиент: {fio}\n"
                f"📱 Телефон: {phone}\n"
                f"🏙 Город: {city}"
        )
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        bot.send_photo(
            call.message.chat.id,
            photo=bio,
            caption=f"🔗 Ссылка для приглашения:\n\n`{invite_link}`\n\n"
                    f"Отправьте эту ссылку или QR-код клиенту.",
            parse_mode='Markdown',
            reply_markup = keyboard

        )
        
        # Сохраняем данные по ключу client_id + fio
        if 'pending_invites' not in user_temp_data:
            user_temp_data['pending_invites'] = {}
        
        invite_key = f"{client_id}_{fio.split()[0]}"
        user_temp_data['pending_invites'][invite_key] = {
            'phone': phone,
            'client_id': client_id,
            'city': city,
            'fio': fio
        }
        
        print(f"DEBUG: Сохранено в pending_invites с ключом: {invite_key}")
        
        # Очищаем временные данные
        if client_id in user_temp_data:
            user_temp_data[client_id].pop('invite_fio', None)
            user_temp_data[client_id].pop('invite_phone', None)
            user_temp_data[client_id].pop('invite_process', None)
        
        bot.answer_callback_query(call.id, "✅ Ссылка сформирована!")
    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_approval_"))
    @prevent_double_click(timeout=3.0)
    def view_approval_handler(call):
        """Просмотр и подтверждение/отклонение документа"""
        approval_id = int(call.data.replace("view_approval_", ""))
        director_id = call.from_user.id
        
        # Получаем данные документа из pending_approvals
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT * FROM pending_approvals 
                        WHERE id = %s
                    """, (approval_id,))
                    approval = cursor.fetchone()
                    
                    if not approval:
                        bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                        return
                    
                    approval = dict(approval)
        except Exception as e:
            print(f"Ошибка получения документа: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки документа", show_alert=True)
            return
        
        # Получаем полные данные договора
        contract_data = get_client_from_db_by_client_id(approval['client_id'])
        
        if not contract_data:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        # Формируем текст с информацией
        doc_type_name = "📄 Доверенность" if approval['document_type'] == 'doverennost' else "💳 Чек на оплату"
        
        text = f"{doc_type_name}\n\n"
        text += f"📋 Договор: {approval['client_id']}\n"
        text += f"👤 Клиент: {approval['fio']}\n"
        text += f"📅 Дата загрузки: {approval['created_at']}\n"
        text += f"📊 Статус: Ожидает подтверждения\n\n"
        
        # Добавляем основную информацию из договора
        if contract_data.get('accident'):
            text += f"🚗 Тип обращения: {contract_data['accident']}\n"
        if contract_data.get('number'):
            text += f"📱 Телефон: {contract_data['number']}\n"
        if contract_data.get('city'):
            text += f"🏙 Город: {contract_data['city']}\n"
        
        # Кнопки подтверждения/отклонения
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            "✅ Подтвердить", 
            callback_data=f"approve_document_{approval_id}"
        ))
        keyboard.add(types.InlineKeyboardButton(
            "❌ Отклонить", 
            callback_data=f"reject_document_{approval_id}"
        ))
        keyboard.add(types.InlineKeyboardButton(
            "📋 Полная карточка договора", 
            callback_data=f"view_client_{approval['client_id']}"
        ))
        keyboard.add(types.InlineKeyboardButton(
            "◀️ Назад", 
            callback_data=f"show_{approval['document_type']}_list"
        ))
        
        # Если есть URL документа, отправляем его
        if approval.get('document_url'):
            try:
                bot.send_document(
                    call.message.chat.id,
                    approval['document_url'],
                    caption=text
                )
                # Отправляем кнопки отдельным сообщением
                bot.send_message(
                    call.message.chat.id,
                    "Выберите действие:",
                    reply_markup=keyboard
                )
                # Удаляем старое сообщение
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
            except Exception as e:
                print(f"Ошибка отправки документа: {e}")
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=text,
                    reply_markup=keyboard
                )
        else:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data == "director_approvals")
    @prevent_double_click(timeout=3.0)
    def director_approvals_handler(call):
        """Обработчик кнопки 'На утверждение'"""
        db_instance = DatabaseManager()
        
        with db_instance.get_connection() as conn:
            with conn.cursor() as cursor:
                # Подсчет доверенностей
                cursor.execute("""
                    SELECT COUNT(*) FROM pending_approvals 
                    WHERE document_type = 'doverennost' AND status = 'pending'
                """)
                poa_count = cursor.fetchone()[0]
                
                # Подсчет оплат
                cursor.execute("""
                    SELECT COUNT(*) FROM pending_approvals 
                    WHERE document_type = 'payment' AND status = 'pending'
                """)
                payment_count = cursor.fetchone()[0]
        
        total = poa_count + payment_count
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(f"📄 Доверенность ({poa_count})", callback_data='director_poa_list'))
        keyboard.add(types.InlineKeyboardButton(f"💰 Оплата ({payment_count})", callback_data='director_payment_list'))
        keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data='callback_start'))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Количество документов, ожидающих подтверждения: {total}",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "director_poa_list")
    @prevent_double_click(timeout=3.0)
    def director_poa_list_handler(call):
        """Список доверенностей на утверждение"""
        db_instance = DatabaseManager()
        
        with db_instance.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM pending_approvals 
                    WHERE document_type = 'doverennost' AND status = 'pending'
                    ORDER BY created_at DESC
                """)
                approvals = cursor.fetchall()
        
        if not approvals:
            bot.answer_callback_query(call.id, "Нет доверенностей на утверждение", show_alert=True)
            return
        
        text = "📄 Доверенности, ожидающие подтверждения:\n\n"
        keyboard = types.InlineKeyboardMarkup()
        
        for approval in approvals:
            text += f"Договор №{approval['client_id']} - {approval['fio']}\n"
            keyboard.add(types.InlineKeyboardButton(
                f"№{approval['client_id']} - {approval['fio']}",
                callback_data=f"view_doverennost_approval_{approval['id']}"  # ← ИЗМЕНИТЬ НА ЭТО
            ))
        
        keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data='director_approvals'))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_doverennost_approval_"))
    @prevent_double_click(timeout=3.0)
    def view_doverennost_approval_handler(call):
        """Просмотр доверенности с файлами и кнопками подтверждения/отклонения"""
        approval_id = int(call.data.replace("view_doverennost_approval_", ""))
        director_id = call.from_user.id
        
        # Получаем данные документа из pending_approvals
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT * FROM pending_approvals 
                        WHERE id = %s
                    """, (approval_id,))
                    approval = cursor.fetchone()
                    
                    if not approval:
                        bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                        return
                    
                    approval = dict(approval)
        except Exception as e:
            print(f"Ошибка получения документа: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки документа", show_alert=True)
            return
        
        # Получаем полные данные договора
        contract_data = get_client_from_db_by_client_id(approval['client_id'])
        
        if not contract_data:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        # Удаляем предыдущее сообщение
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # Отправляем файлы доверенности
        import os
        client_id = approval['client_id']
        docs_dir = f"clients/{client_id}/Документы"
        
        
        file_path = os.path.join(docs_dir, "Доверенность.pdf")

        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as file:
                    bot.send_document(call.message.chat.id, file, caption=f"📄 Доверенность")
            except Exception as e:
                print(f"Ошибка отправки файла: {e}")
        
        # Парсим contract_data
        try:
            if contract_data.get('data_json'):
                json_data = json.loads(contract_data['data_json'])
                merged_data = {**contract_data, **json_data}
            else:
                merged_data = contract_data
        except:
            merged_data = contract_data
        
        # Формируем информацию о договоре
        text = f"📄 <b>Доверенность</b>\n\n"
        text += f"📋 Договор: {approval['client_id']}\n"
        text += f"📅 Дата создания: {contract_data.get('created_at', 'н/д')}\n\n"
        
        text += f"<b>Информация о клиенте:</b>\n"
        text += f"👤 ФИО: {approval['fio']}\n"
        if contract_data.get('number'):
            text += f"📱 Телефон: {contract_data['number']}\n\n"
        
        text += f"<b>Информация о ДТП:</b>\n"
        if contract_data.get('accident'):
            text += f"⚠️ Тип обращения: {contract_data['accident']}\n"
        if merged_data.get('date_dtp'):
            text += f"📅 Дата ДТП: {merged_data['date_dtp']}\n"
        if merged_data.get('time_dtp'):
            text += f"🕐 Время ДТП: {merged_data['time_dtp']}\n"
        if merged_data.get('address_dtp'):
            text += f"📍 Адрес ДТП: {merged_data['address_dtp']}\n"
        if merged_data.get('insurance'):
            text += f"🏢 Страховая: {merged_data['insurance']}\n"
        if contract_data.get('status'):
            text += f"📊 Статус: {contract_data['status']}\n"
        
        text += "\n⏳ Ожидает проверки доверенности"
        
        # Кнопки
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Подтвердить доверенность", callback_data=f"approve_doverennost_{approval_id}"))
        keyboard.add(types.InlineKeyboardButton("❌ Отклонить доверенность", callback_data=f"reject_doverennost_{approval_id}"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="director_poa_list"))
        
        bot.send_message(call.message.chat.id, text, reply_markup=keyboard, parse_mode='HTML')
    @bot.callback_query_handler(func=lambda call: call.data == "director_payment_list")
    @prevent_double_click(timeout=3.0)
    def director_payment_list_handler(call):
        """Список оплат на утверждение"""
        db_instance = DatabaseManager()
        
        with db_instance.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM pending_approvals 
                    WHERE document_type = 'payment' AND status = 'pending'
                    ORDER BY created_at DESC
                """)
                approvals = cursor.fetchall()
        
        if not approvals:
            bot.answer_callback_query(call.id, "Нет оплат на утверждение", show_alert=True)
            return
        
        text = "💰 Оплаты, ожидающие подтверждения:\n\n"
        keyboard = types.InlineKeyboardMarkup()
        
        for approval in approvals:
            text += f"Договор №{approval['client_id']} - {approval['fio']}\n"
            keyboard.add(types.InlineKeyboardButton(
                f"№{approval['client_id']} - {approval['fio']}",
                callback_data=f"view_payment_approval_{approval['id']}"  # ← ИЗМЕНИТЬ НА ЭТО
            ))
        
        keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data='director_approvals'))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_payment_approval_"))
    @prevent_double_click(timeout=3.0)
    def view_payment_approval_handler(call):
        """Просмотр оплаты с кнопками подтверждения/отклонения"""
        approval_id = int(call.data.replace("view_payment_approval_", ""))
        director_id = call.from_user.id
        
        # Получаем данные документа из pending_approvals
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT * FROM pending_approvals 
                        WHERE id = %s
                    """, (approval_id,))
                    approval = cursor.fetchone()
                    
                    if not approval:
                        bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                        return
                    
                    approval = dict(approval)
        except Exception as e:
            print(f"Ошибка получения документа: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки документа", show_alert=True)
            return
        
        # Получаем полные данные договора
        contract_data = get_client_from_db_by_client_id(approval['client_id'])
        
        if not contract_data:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        

        merged_data = contract_data
        
        # Формируем информацию о договоре
        text = f"💳 <b>Оплата юридических услуг</b>\n\n"
        text += f"📋 Договор: {approval['client_id']}\n"
        text += f"📅 Дата создания: {contract_data.get('created_at', 'н/д')}\n\n"
        
        text += f"<b>Информация о клиенте:</b>\n"
        text += f"👤 ФИО: {approval['fio']}\n"
        if contract_data.get('number'):
            text += f"📱 Телефон: {contract_data['number']}\n\n"
        
        text += f"<b>Информация о ДТП:</b>\n"
        if contract_data.get('accident'):
            text += f"⚠️ Тип обращения: {contract_data['accident']}\n"
        if merged_data.get('date_dtp'):
            text += f"📅 Дата ДТП: {merged_data['date_dtp']}\n"
        if merged_data.get('time_dtp'):
            text += f"🕐 Время ДТП: {merged_data['time_dtp']}\n"
        if merged_data.get('address_dtp'):
            text += f"📍 Адрес ДТП: {merged_data['address_dtp']}\n"
        if merged_data.get('insurance'):
            text += f"🏢 Страховая: {merged_data['insurance']}\n"
        if contract_data.get('status'):
            text += f"📊 Статус: {contract_data['status']}\n"
        
        text += "\n⏳ Ожидает проверки оплаты"
        text += "\n\n💡 <i>После подтверждения вам нужно будет загрузить чек об оплате</i>"
        
        # Кнопки
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_payment_{approval_id}"))
        keyboard.add(types.InlineKeyboardButton("❌ Отклонить оплату", callback_data=f"reject_payment_reason_{approval_id}"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="director_payment_list"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_payment_"))
    @prevent_double_click(timeout=3.0)
    def callback_confirm_payment_request_receipt_number(call):
        """Подтверждение оплаты - запрос номера чека"""
        director_id = call.from_user.id
        approval_id = int(call.data.replace("confirm_payment_", ""))
        
        # Получаем данные
        db = DatabaseManager()
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM pending_approvals WHERE id = %s", (approval_id,))
                approval = cursor.fetchone()
                
                if not approval:
                    bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                    return
                
                client_id = approval['client_id']
                client_user_id = approval['user_id']
                fio = approval['fio']
        
        # Сохраняем данные для следующего шага
        if director_id not in user_temp_data:
            user_temp_data[director_id] = {}
        user_temp_data[director_id]['payment_approval'] = {
            'approval_id': approval_id,
            'client_id': client_id,
            'user_id': client_user_id,
            'fio': fio
        }
        
        # СНАЧАЛА просим ввести номер чека
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💳 <b>Подтверждение оплаты</b>\n\n"
                f"Договор: {client_id}\n"
                f"Клиент: {fio}\n\n"
                f"📝 Введите номер чека:",
            parse_mode='HTML'
        )
        
        bot.register_next_step_handler(call.message, process_receipt_number, director_id, call.message.message_id)


    def process_receipt_number(message, director_id, prev_msg_id):
        """Обработка номера чека"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        receipt_number = message.text.strip()
        
        if not receipt_number or len(receipt_number) < 3:
            msg = bot.send_message(
                message.chat.id,
                "❌ Номер чека слишком короткий. Введите номер чека (минимум 3 символа):"
            )
            bot.register_next_step_handler(msg, process_receipt_number, director_id, msg.message_id)
            return
        
        # Сохраняем номер чека
        if director_id not in user_temp_data or 'payment_approval' not in user_temp_data[director_id]:
            bot.send_message(message.chat.id, "❌ Ошибка: данные не найдены")
            return
        
        user_temp_data[director_id]['payment_approval']['receipt_number'] = receipt_number
        
        approval_data = user_temp_data[director_id]['payment_approval']
        client_id = approval_data['client_id']
        fio = approval_data['fio']
        
        # Теперь просим загрузить чек
        msg = bot.send_message(
            message.chat.id,
            f"✅ Номер чека: {receipt_number}\n\n"
            f"📎 Отправьте чек об оплате для договора {client_id} ({fio})\n\n"
            f"Принимаются: фото (JPG, PNG), документы (PDF)"
        )
        
        bot.register_next_step_handler(msg, handle_director_payment_receipt, director_id, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "director_signatures")
    @prevent_double_click(timeout=3.0)
    def director_signatures_handler(call):
        """Обработчик кнопки 'На подпись'"""
        db_instance = DatabaseManager()
        
        with db_instance.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM withdrawal_requests 
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                """)
                requests = cursor.fetchall()
        
        if not requests:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Нет документов на подпись",
                reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Назад", callback_data='callback_start')]])
            )
            return
        
        text = f"Количество документов на подпись: {len(requests)}\n\n"
        keyboard = types.InlineKeyboardMarkup()
        
        for req in requests:
            text += f"{req['agent_fio']} - {req['amount']} руб.\n"
            keyboard.add(types.InlineKeyboardButton(
                f"{req['agent_fio']}",
                callback_data=f"withdrawal_review_{req['id']}"
            ))
        
        keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data='callback_start'))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "request_withdrawal")
    @prevent_double_click(timeout=3.0)
    def request_withdrawal_handler(call):
        """Запрос на вывод средств"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['withdrawal_request'] = True
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите сумму для вывода:",
            reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton("❌ Отмена", callback_data='agent_finances')]])
        )
        
        bot.register_next_step_handler(call.message, process_withdrawal_amount, user_id, call.message.message_id)

    def process_withdrawal_amount(message, user_id, prev_message_id):
        """Обработка суммы вывода"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            amount = float(message.text.replace(',', '.'))
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Введите корректную сумму")
            bot.register_next_step_handler(msg, process_withdrawal_amount, user_id, msg.message_id)
            return
        
        # Проверка баланса
        db_instance = DatabaseManager()
        with db_instance.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT balance FROM agent_finances 
                    WHERE agent_id = %s
                """, (str(user_id),))
                result = cursor.fetchone()
                balance = result[0] if result else 0
        
        if amount <= 0:
            msg = bot.send_message(message.chat.id, "❌ Сумма должна быть положительной")
            bot.register_next_step_handler(msg, process_withdrawal_amount, user_id, msg.message_id)
            return
        
        if amount > balance:
            msg = bot.send_message(message.chat.id, f"❌ Недостаточно средств. Ваш баланс: {balance} руб.")
            bot.register_next_step_handler(msg, process_withdrawal_amount, user_id, msg.message_id)
            return
        
        # Создаем заявку на вывод
        agent_data = get_admin_from_db_by_user_id(user_id)
        agent_fio = agent_data.get('fio', 'Неизвестно')
        
        with db_instance.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO withdrawal_requests (agent_id, agent_fio, amount)
                    VALUES (%s, %s, %s)
                """, (str(user_id), agent_fio, amount))
                conn.commit()
        
        # Уведомляем директоров
        with db_instance.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id FROM admins 
                    WHERE admin_value = 'Директор' AND is_active = true
                """)
                directors = cursor.fetchall()
                
                for director in directors:
                    try:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                        bot.send_message(
                            int(director[0]),
                            f"✍️ Поступил документ на подпись от агента {agent_fio}\n"
                            f"Сумма: {amount} руб.",
                            reply_markup = keyboard
                        )
                    except Exception as e:
                        print(f"Не удалось уведомить директора {director[0]}: {e}")
        
        bot.send_message(
            message.chat.id,
            "✅ Заявка на вывод отправлена на рассмотрение"
        )
        
        # Очистка временных данных
        if user_id in user_temp_data and 'withdrawal_request' in user_temp_data[user_id]:
            del user_temp_data[user_id]['withdrawal_request']
        
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, user_id)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("withdrawal_review_"))
    @prevent_double_click(timeout=3.0)
    def withdrawal_review_handler(call):
        """Просмотр заявки на вывод"""
        request_id = int(call.data.replace("withdrawal_review_", ""))
        db_instance = DatabaseManager()
        
        with db_instance.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT wr.*, af.balance 
                    FROM withdrawal_requests wr
                    LEFT JOIN agent_finances af ON wr.agent_id = af.agent_id
                    WHERE wr.id = %s
                """, (request_id,))
                request = cursor.fetchone()
        
        if not request:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена", show_alert=True)
            return
        
        text = f"📄 <b>Заявка на вывод средств</b>\n\n"
        text += f"👤 Агент: {request['agent_fio']}\n"
        text += f"💰 Баланс: {request['balance']} руб.\n"
        text += f"💸 Требуемая сумма: {request['amount']} руб.\n"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_withdrawal_{request_id}"))
        keyboard.add(types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_withdrawal_{request_id}"))
        keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data='director_signatures'))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    def handle_director_payment_receipt(message, director_id, prev_message_id):
        """Обработка загрузки чека директором"""
        import os
        from datetime import datetime
        
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if director_id not in user_temp_data or 'payment_approval' not in user_temp_data[director_id]:
            bot.send_message(message.chat.id, "❌ Ошибка: данные не найдены")
            return
        
        approval_data = user_temp_data[director_id]['payment_approval']
        approval_id = approval_data['approval_id']
        client_id = approval_data['client_id']
        client_user_id = approval_data['user_id']
        fio = approval_data['fio']
        receipt_number = approval_data.get('receipt_number', 'Не указан')
        
        client_dir = f"clients/{client_id}/Документы"
        
        uploaded_file = None
        filename = None
        
        if message.document:
            uploaded_file = message.document
            filename = f"Оплата.pdf"
        elif message.photo:
            uploaded_file = message.photo[-1]
            filename = f"Оплата.jpg"
        else:
            msg = bot.send_message(message.chat.id, "❌ Отправьте документ или фото")
            bot.register_next_step_handler(msg, handle_director_payment_receipt, director_id, msg.message_id)
            return
        
        try:
            # Сохраняем файл
            file_info = bot.get_file(uploaded_file.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            os.makedirs(client_dir, exist_ok=True)
            file_path = os.path.join(client_dir, filename)
            
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            # Получаем текущую дату и время
            receipt_uploaded_at = datetime.now()
            
            # Обновляем статус в БД
            db_instance = DatabaseManager()
            
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Обновляем pending_approvals С НОМЕРОМ ЧЕКА И ДАТОЙ
                    cursor.execute("""
                        UPDATE pending_approvals
                        SET status = 'approved',
                            reviewed_by = %s,
                            reviewed_at = NOW(),
                            document_url = %s,
                            receipt_number = %s,
                            receipt_uploaded_at = %s
                        WHERE id = %s
                    """, (str(director_id), file_path, receipt_number, receipt_uploaded_at, approval_id))
                    
                    # Обновляем clients
                    cursor.execute("""
                        UPDATE clients 
                        SET data_json = jsonb_set(
                            jsonb_set(
                                COALESCE(data_json::jsonb, '{}'::jsonb),
                                '{payment_confirmed}',
                                '"Yes"'
                            ),
                            '{payment_pending}',
                            '"No"'
                        )
                        WHERE client_id = %s
                    """, (client_id,))
                    
                    # Получаем данные договора для начисления
                    cursor.execute("""
                        SELECT data_json FROM clients WHERE client_id = %s
                    """, (client_id,))
                    result = cursor.fetchone()
                    
                    if result and result[0]:
                        try:
                            data_json = json.loads(result[0]) if isinstance(result[0], str) else result[0]
                            creator_user_id = data_json.get('creator_user_id')
                            
                            if creator_user_id and str(creator_user_id) != str(client_user_id):
                                cursor.execute("""
                                    SELECT admin_value FROM admins WHERE user_id = %s
                                """, (str(creator_user_id),))
                                creator_role_result = cursor.fetchone()
                                
                                if creator_role_result:
                                    creator_role = creator_role_result[0]
                                    
                                    if creator_role in ['Агент', 'Администратор']:
                                        cursor.execute("""
                                            SELECT balance FROM agent_finances 
                                            WHERE agent_id = %s
                                        """, (str(creator_user_id),))
                                        balance_result = cursor.fetchone()
                                        
                                        if balance_result:
                                            cursor.execute("""
                                                UPDATE agent_finances 
                                                SET balance = balance + 1000, 
                                                    total_earned = total_earned + 1000,
                                                    last_updated = CURRENT_TIMESTAMP
                                                WHERE agent_id = %s
                                            """, (str(creator_user_id),))
                                        else:
                                            cursor.execute("""
                                                INSERT INTO agent_finances (agent_id, balance, total_earned)
                                                VALUES (%s, 1000, 1000)
                                            """, (str(creator_user_id),))
                                        
                                        cursor.execute("""
                                            INSERT INTO agent_earnings_history 
                                            (agent_id, client_id, amount, payment_confirmed_at)
                                            VALUES (%s, %s, 1000, NOW())
                                        """, (str(creator_user_id), client_id))
                                        
                                        print(f"✅ Начислено 1000 руб агенту/администратору {creator_user_id} за договор {client_id}")
                        except Exception as e:
                            print(f"❌ Ошибка начисления агенту: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # РЕФЕРАЛЬНАЯ СИСТЕМА: Проверяем, был ли клиент приглашен другим клиентом
                    cursor.execute("""
                        SELECT invited_by_user_id, invited_by_type
                        FROM admins
                        WHERE user_id = %s AND invited_by_type = 'client'
                    """, (str(client_user_id),))
                    
                    inviter_result = cursor.fetchone()
                    print(inviter_result)
                    if inviter_result and inviter_result[0]:
                        inviter_user_id = inviter_result[0]
                        
                        # Проверяем, первый ли это договор приглашенного клиента
                        cursor.execute("""
                            SELECT COUNT(*) FROM clients 
                            WHERE user_id = %s
                        """, (str(client_user_id),))
                        
                        contract_count = cursor.fetchone()[0]
                        print(contract_count)
                        # Начисляем только за первый договор
                        if contract_count == 1:
                            # Начисляем 300р пригласившему клиенту
                            cursor.execute("""
                                SELECT balance FROM client_finances 
                                WHERE client_id = %s
                            """, (str(inviter_user_id),))
                            
                            balance_result = cursor.fetchone()
                            
                            if balance_result:
                                cursor.execute("""
                                    UPDATE client_finances 
                                    SET balance = balance + 300, 
                                        total_earned = total_earned + 300,
                                        last_updated = CURRENT_TIMESTAMP
                                    WHERE client_id = %s
                                """, (str(inviter_user_id),))
                            else:
                                cursor.execute("""
                                    INSERT INTO client_finances (client_id, balance, total_earned)
                                    VALUES (%s, 300, 300)
                                """, (str(inviter_user_id),))
                            
                            cursor.execute("""
                                INSERT INTO client_earnings_history 
                                (client_id, referred_client_id, amount, earned_at)
                                VALUES (%s, %s, 300, NOW())
                            """, (str(inviter_user_id), client_id))
                            
                            print(f"✅ Начислено 300 руб. клиенту {inviter_user_id} за реферала {client_id}")
                            
                            # Уведомляем пригласившего клиента
                            try:
                                inviter_data = get_admin_from_db_by_user_id(inviter_user_id)
                                if inviter_data:
                                    keyboard_ref = types.InlineKeyboardMarkup()
                                    keyboard_ref.add(types.InlineKeyboardButton("💰 Личный кабинет", callback_data="personal_cabinet_client"))
                                    bot.send_message(
                                        int(inviter_user_id),
                                        f"💰 Вам начислено 300 руб. за приглашение клиента!\n\n"
                                        f"📄 Договор: {client_id}\n"
                                        f"👤 Приглашенный: {fio}",
                                        reply_markup=keyboard_ref
                                    )
                            except Exception as e:
                                print(f"Не удалось уведомить приглашающего клиента: {e}")
                    
                    conn.commit()
            
            # Очищаем временные данные
            del user_temp_data[director_id]['payment_approval']
            
            if client_user_id != "8572367590":
                # Уведомляем клиента
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{client_id}"))
                    bot.send_message(
                        int(client_user_id),
                        f"✅ Оплата по договору {client_id} подтверждена!\n\n"
                        f"📝 Номер чека: {receipt_number}",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    print(f"Не удалось уведомить клиента: {e}")
            
            notify_appraisers_about_payment(bot, client_id, fio)
            
            # Сообщаем директору с кнопкой "На утверждение"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📝 На утверждение", callback_data="director_approvals"))
            
            bot.send_message(
                director_id,
                f"✅ Чек загружен и оплата подтверждена!\n\n"
                f"Договор: {client_id}\n"
                f"Клиент: {fio}\n"
                f"📝 Номер чека: {receipt_number}\n"
                f"📅 Дата загрузки: {receipt_uploaded_at.strftime('%d.%m.%Y %H:%M:%S')}",
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Ошибка загрузки чека: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_payment_reason_"))
    @prevent_double_click(timeout=3.0)
    def callback_reject_payment_request_reason(call):
        """Запрос причины отклонения оплаты"""
        user_id = call.from_user.id
        approval_id = int(call.data.replace("reject_payment_reason_", ""))
        
        # Сохраняем approval_id для следующего шага
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['reject_payment_approval_id'] = approval_id
        
        # Просим ввести причину
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ <b>Отклонение оплаты</b>\n\nВведите причину отклонения:",
            parse_mode='HTML'
        )
        
        bot.register_next_step_handler(call.message, process_payment_rejection_reason, user_id, call.message.message_id)


    def process_payment_rejection_reason(message, user_id, prev_msg_id):
        """Обработка причины отклонения оплаты"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        reason = message.text.strip()
        
        if not reason or len(reason) < 3:
            msg = bot.send_message(
                message.chat.id,
                "❌ Причина слишком короткая. Введите причину отклонения (минимум 3 символа):"
            )
            bot.register_next_step_handler(msg, process_payment_rejection_reason, user_id, msg.message_id)
            return
        
        # Получаем approval_id
        approval_id = user_temp_data[user_id].get('reject_payment_approval_id')
        if not approval_id:
            bot.send_message(message.chat.id, "❌ Ошибка: данные не найдены")
            return
        
        # Обновляем статус с причиной
        db = DatabaseManager()
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM pending_approvals WHERE id = %s", (approval_id,))
                approval = cursor.fetchone()
                
                if not approval:
                    bot.send_message(message.chat.id, "❌ Документ не найден")
                    return
                
                client_id = approval['client_id']
                client_user_id = approval['user_id']
                
                # Обновляем со статусом rejected и причиной
                cursor.execute("""
                    UPDATE pending_approvals 
                    SET status = 'rejected', 
                        reviewed_by = %s, 
                        reviewed_at = NOW(),
                        rejection_reason = %s
                    WHERE id = %s
                """, (str(user_id), reason, approval_id))
                
                # Сбрасываем флаг оплаты
                cursor.execute("""
                    UPDATE clients 
                    SET data_json = jsonb_set(
                        COALESCE(data_json::jsonb, '{}'::jsonb),
                        '{payment_pending}',
                        '"No"'
                    )
                    WHERE client_id = %s
                """, (client_id,))
                
                conn.commit()
        
        # Уведомляем клиента с причиной
        if client_user_id:
            try:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📄 К договору", callback_data=f"view_contract_{client_id}"))
                bot.send_message(
                    int(client_user_id),
                    f"❌ Ваша оплата по договору {client_id} отклонена.\n\n"
                    f"<b>Причина:</b> {reason}\n\n"
                    f"Пожалуйста, проверьте действительно ли была произведена оплата.",
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Ошибка уведомления клиента: {e}")
        
        # Очищаем временные данные
        if user_id in user_temp_data:
            user_temp_data[user_id].pop('reject_payment_approval_id', None)
        
        # Сообщение администратору с кнопкой "На утверждение"
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📝 На утверждение", callback_data="director_approvals"))
        
        bot.send_message(
            message.chat.id,
            f"❌ Оплата по договору {client_id} отклонена.\n\n"
            f"<b>Причина:</b> {reason}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_document_"))
    @prevent_double_click(timeout=3.0)
    def reject_document_handler(call):
        """Отклонение документа"""
        approval_id = int(call.data.replace("reject_document_", ""))
        director_id = call.from_user.id
        
        db_instance = DatabaseManager()
        
        # Получаем данные документа
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT * FROM pending_approvals 
                        WHERE id = %s
                    """, (approval_id,))
                    approval = cursor.fetchone()
                    
                    if not approval:
                        bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                        return
                    
                    approval = dict(approval)
        except Exception as e:
            print(f"Ошибка получения документа: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)
            return
        
        # Обновляем статус
        success = db_instance.update_approval_status(approval_id, 'rejected', str(director_id))
        
        if success:
            # Уведомляем клиента
            doc_type_name = "Доверенность" if approval['document_type'] == 'doverennost' else "Чек на оплату"
            try:
                bot.send_message(
                    approval['user_id'],
                    f"❌ {doc_type_name} по договору {approval['client_id']} отклонена. "
                    f"Пожалуйста, загрузите корректный документ."
                )
            except Exception as e:
                print(f"Не удалось уведомить клиента: {e}")
            
            bot.answer_callback_query(call.id, "❌ Документ отклонен", show_alert=True)
            
            # Возвращаемся к списку
            if approval['document_type'] == 'doverennost':
                show_doverennost_list_handler(call)
            else:
                show_payment_list_handler(call)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка обработки", show_alert=True)
    @bot.callback_query_handler(func=lambda call: call.data == "director_signatures")
    @prevent_double_click(timeout=3.0)
    def director_signatures_handler(call):
        """Показать документы на подпись"""
        db = DatabaseManager()
        withdrawals = db.get_pending_withdrawals()
        count = len(withdrawals)
        
        if count == 0:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ Нет документов на подпись",
                reply_markup=keyboard
            )
            return
        
        text = f"✍️ Количество документов на подпись: {count}\n\n"
        keyboard = types.InlineKeyboardMarkup()
        
        for w in withdrawals:
            text += f"• {w['agent_fio']} - {w['amount']:.2f} руб.\n"
            keyboard.add(types.InlineKeyboardButton(
                f"{w['agent_fio']} - {w['amount']:.2f} руб.", 
                callback_data=f"view_withdrawal_{w['id']}"
            ))
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_withdrawal_"))
    @prevent_double_click(timeout=3.0)
    def view_withdrawal_handler(call):
        """Просмотр заявки на вывод"""
        db = DatabaseManager()
        withdrawal_id = int(call.data.replace("view_withdrawal_", ""))
        withdrawals = db.get_pending_withdrawals()
        withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
        
        if not withdrawal:
            bot.answer_callback_query(call.id, "Заявка не найдена", show_alert=True)
            return
        
        agent_balance = db.get_agent_balance(withdrawal['agent_id'])
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            "✅ Подтвердить", 
            callback_data=f"approve_withdrawal_{withdrawal_id}"
        ))
        keyboard.add(types.InlineKeyboardButton(
            "❌ Отклонить", 
            callback_data=f"reject_withdrawal_{withdrawal_id}"
        ))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="director_signatures"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💰 Заявка на вывод средств\n\n"
                f"👤 Агент: {withdrawal['agent_fio']}\n"
                f"💵 Текущий баланс: {agent_balance['balance']:.2f} руб.\n"
                f"💸 Запрошенная сумма: {withdrawal['amount']:.2f} руб.\n"
                f"📅 Дата заявки: {withdrawal['created_at']}",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("approve_withdrawal_"))
    @prevent_double_click(timeout=3.0)
    def approve_withdrawal_handler(call):
        """Подтверждение вывода"""
        db = DatabaseManager()
        withdrawal_id = int(call.data.replace("approve_withdrawal_", ""))
        director_id = call.from_user.id
        
        withdrawals = db.get_pending_withdrawals()
        withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
        
        if not withdrawal:
            bot.answer_callback_query(call.id, "Заявка не найдена", show_alert=True)
            return
        
        success = db.process_withdrawal(
            withdrawal_id, 
            'approved', 
            str(director_id), 
            withdrawal['agent_id'], 
            withdrawal['amount']
        )
        
        if success:
            # Уведомляем агента
            bot.send_message(
                withdrawal['agent_id'],
                f"✅ Ваша заявка на вывод {withdrawal['amount']:.2f} руб. подтверждена!"
            )
            
            bot.answer_callback_query(call.id, "✅ Заявка подтверждена", show_alert=True)
            director_signatures_handler(call)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка обработки", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_withdrawal_"))
    @prevent_double_click(timeout=3.0)
    def reject_withdrawal_handler(call):
        """Отклонение вывода"""
        db = DatabaseManager()
        withdrawal_id = int(call.data.replace("reject_withdrawal_", ""))
        director_id = call.from_user.id
        
        withdrawals = db.get_pending_withdrawals()
        withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
        
        if not withdrawal:
            bot.answer_callback_query(call.id, "Заявка не найдена", show_alert=True)
            return
        
        success = db.process_withdrawal(
            withdrawal_id, 
            'rejected', 
            str(director_id), 
            withdrawal['agent_id'], 
            withdrawal['amount']
        )
        
        if success:
            # Уведомляем агента
            bot.send_message(
                withdrawal['agent_id'],
                f"❌ Ваша заявка на вывод {withdrawal['amount']:.2f} руб. отклонена."
            )
            
            bot.answer_callback_query(call.id, "❌ Заявка отклонена", show_alert=True)
            director_signatures_handler(call)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка обработки", show_alert=True)

    # ========== АГЕНТ: ФИНАНСЫ ==========
    @bot.callback_query_handler(func=lambda call: call.data == "agent_finances")
    @prevent_double_click(timeout=3.0)
    def agent_finances_handler(call):
        """Финансы агента"""
        agent_id = call.from_user.id
        db = DatabaseManager()
        balance_data = db.get_agent_balance(str(agent_id))
        monthly_earning = db.get_agent_monthly_earning(str(agent_id))
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("💸 Заказать вывод", callback_data="request_withdrawal"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💰 Финансы\n\n"
                f"📊 Ваш заработок за месяц: {monthly_earning:.2f} руб.\n"
                f"💵 Баланс : {balance_data['balance']:.2f} руб.",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "request_withdrawal")
    @prevent_double_click(timeout=3.0)
    def request_withdrawal_handler(call):
        """Запрос на вывод средств"""
        agent_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💸 Введите сумму для вывода:"
        )
        
        bot.register_next_step_handler(call.message, process_withdrawal_amount, agent_id, call.message.message_id)

    def process_withdrawal_amount(message, agent_id, prev_message_id):
        """Обработка суммы вывода"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        db = DatabaseManager()
        try:
            amount = float(message.text.strip())
        except ValueError:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат. Введите число:"
            )
            bot.register_next_step_handler(msg, process_withdrawal_amount, agent_id, msg.message_id)
            return
        
        if amount <= 0:
            msg = bot.send_message(
                message.chat.id,
                "❌ Сумма должна быть положительной. Введите снова:"
            )
            bot.register_next_step_handler(msg, process_withdrawal_amount, agent_id, msg.message_id)
            return
        
        balance_data = db.get_agent_balance(str(agent_id))
        if amount > balance_data['balance']:
            msg = bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств. Ваш баланс: {balance_data['balance']:.2f} руб.\n"
                f"Введите сумму не больше баланса:"
            )
            bot.register_next_step_handler(msg, process_withdrawal_amount, agent_id, msg.message_id)
            return
        
        # Создаем заявку
        agent_data = get_admin_from_db_by_user_id(agent_id)
        agent_fio = agent_data.get('fio', 'Агент')
        
        withdrawal_id = db.create_withdrawal_request(str(agent_id), agent_fio, amount)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        if withdrawal_id:
            msg = bot.send_message(
                message.chat.id,
                f"✅ Заявка на вывод {amount:.2f} руб. отправлена на подпись директору.",
                reply_markup = keyboard
            )
            
            # Уведомляем всех директоров
            notify_directors_about_withdrawal(bot, agent_fio, amount)
            
            # Возвращаемся в меню финансов
            

        else:
            bot.send_message(
                message.chat.id,
                "❌ Ошибка создания заявки. Попробуйте позже."
            )

    @bot.callback_query_handler(func=lambda call: call.data == "director_approvals")
    @prevent_double_click(timeout=3.0)
    def director_approvals_handler(call):
        """Показать документы на утверждение"""
        db = DatabaseManager()
        dov_count = db.get_pending_approvals_count('doverennost')
        payment_count = db.get_pending_approvals_count('payment')
        total_count = dov_count + payment_count
        
        keyboard = types.InlineKeyboardMarkup()
        if dov_count > 0:
            keyboard.add(types.InlineKeyboardButton(
                f"📄 Доверенность ({dov_count})", 
                callback_data="show_doverennost_list"
            ))
        if payment_count > 0:
            keyboard.add(types.InlineKeyboardButton(
                f"💳 Оплата ({payment_count})", 
                callback_data="show_payment_list"
            ))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📝 Количество документов, ожидающих подтверждения: {total_count}",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "show_doverennost_list")
    @prevent_double_click(timeout=3.0)
    def show_doverennost_list_handler(call):
        """Показать список доверенностей"""
        db = DatabaseManager()
        approvals = db.get_pending_approvals_list('doverennost')
        
        if not approvals:
            bot.answer_callback_query(call.id, "Нет доверенностей на подтверждение", show_alert=True)
            return
        
        text = "📄 Доверенности, ожидающие подтверждения:\n\n"
        keyboard = types.InlineKeyboardMarkup()
        
        for approval in approvals:
            text += f"• Договор {approval['client_id']}, {approval['fio']}\n"
            keyboard.add(types.InlineKeyboardButton(
                f"{approval['client_id']} - {approval['fio']}", 
                callback_data=f"view_approval_{approval['id']}"
            ))
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="director_approvals"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "show_payment_list")
    @prevent_double_click(timeout=3.0)
    def show_payment_list_handler(call):
        """Показать список чеков на оплату"""
        db = DatabaseManager()
        approvals = db.get_pending_approvals_list('payment')
        
        if not approvals:
            bot.answer_callback_query(call.id, "Нет чеков на подтверждение", show_alert=True)
            return
        
        text = "💳 Чеки на оплату, ожидающие подтверждения:\n\n"
        keyboard = types.InlineKeyboardMarkup()
        
        for approval in approvals:
            text += f"• Договор {approval['client_id']}, {approval['fio']}\n"
            keyboard.add(types.InlineKeyboardButton(
                f"{approval['client_id']} - {approval['fio']}", 
                callback_data=f"view_approval_{approval['id']}"
            ))
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="director_approvals"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    # ========== АГЕНТ: ДОБАВИТЬ НОВОГО КЛИЕНТА ==========

    @bot.callback_query_handler(func=lambda call: call.data == "btn_add_client")
    @prevent_double_click(timeout=3.0)
    def btn_add_client_handler(call):
        """Новый клиент - Агент вводит ФИО клиента С ПРОВЕРКОЙ"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("👤 Зарегистрировать клиента", callback_data="callback_registr_client"))
        keyboard.add(types.InlineKeyboardButton("📋 У клиента нет ТГ", callback_data="callback_registr_alone"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите из следующих вариантов",
            reply_markup=keyboard
        )
        

    @bot.callback_query_handler(func=lambda call: call.data == "callback_registr_client")
    @prevent_double_click(timeout=3.0)
    def btn_add_client_handler(call):
        """Новый клиент - Агент вводит ФИО клиента С ПРОВЕРКОЙ"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['add_client_mode'] = 'check_existing'  # Новый флаг
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="👤 Введите ФИО клиента в формате: Иванов Иван Иванович",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(call.message, process_add_client_fio_check, user_id, call.message.message_id)

    def process_add_client_fio_check(message, agent_id, prev_message_id):
        """Обработка ФИО с проверкой зарегистрированных клиентов в admins"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        # Проверка формата ФИО
        if len(message.text.split()) < 2:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат ввода!\nВведите ФИО в формате: Иванов Иван Иванович"
            )
            bot.register_next_step_handler(msg, process_add_client_fio_check, agent_id, msg.message_id)
            return
        
        words = message.text.split()
        for word in words:
            if not word[0].isupper():
                msg = bot.send_message(
                    message.chat.id,
                    "❌ Каждое слово должно начинаться с заглавной буквы!\n"
                    "Введите ФИО в формате: Иванов Иван Иванович"
                )
                bot.register_next_step_handler(msg, process_add_client_fio_check, agent_id, msg.message_id)
                return
        
        client_fio = message.text.strip()
        db = DatabaseManager()
        # ИЩЕМ ЗАРЕГИСТРИРОВАННЫХ КЛИЕНТОВ В ТАБЛИЦЕ ADMINS
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT user_id, fio, number, admin_value, city_admin
                        FROM admins 
                        WHERE LOWER(fio) LIKE LOWER(%s) 
                        ORDER BY fio
                    """, (f'%{client_fio}%',))
                    
                    registered_clients = cursor.fetchall()
        except Exception as e:
            print(f"Ошибка поиска клиентов: {e}")
            registered_clients = []
        
        if registered_clients:
            # Нашли зарегистрированных клиентов
            keyboard = types.InlineKeyboardMarkup()
            
            response = f"✅ Найдены зарегистрированные клиенты по запросу '{client_fio}':\n\n"
            
            for i, client in enumerate(registered_clients[:5], 1):
                user_id, fio, number, admin_value, city = client
                response += f"{i}. {fio}\n"
                response += f"   📱 {number or 'не указан'}\n"
                response += f"   🏙 {city or 'не указан'}\n\n"
                
                btn_text = f"{i}. {fio}"
                btn_callback = f"agent_select_registered_{user_id}"
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
            
            keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="callback_start"))
            
            # Сохраняем ФИО для возможного создания нового приглашения
            user_temp_data[agent_id]['search_fio'] = client_fio
            
            bot.send_message(message.chat.id, response, reply_markup=keyboard)
            return
        
        # Если клиент не найден - переходим к созданию ссылки-приглашения
        user_temp_data[agent_id]['invite_fio'] = client_fio
        
        msg = bot.send_message(
            message.chat.id,
            f"❌ Клиент с ФИО '{client_fio}' не найден в системе.\n\n"
            f"📱 Введите номер телефона клиента для создания приглашения (например, +79001234567):"
        )
        
        bot.register_next_step_handler(msg, process_invite_phone_agent, agent_id, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_select_registered_"))
    @prevent_double_click(timeout=3.0)
    def agent_select_registered_client(call):
        """Агент выбрал зарегистрированного клиента для создания договора"""
        agent_id = call.from_user.id
        client_user_id = int(call.data.replace("agent_select_registered_", ""))

        agent_data = get_admin_from_db_by_user_id(agent_id)

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"request_personal_data_{agent_id}"))
        keyboard.add(types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_personal_data_{agent_id}"))

        msg = bot.edit_message_text(
            chat_id = call.message.chat.id,
            message_id = call.message.message_id,
            text = f"ℹ️ Отправлен запрос на получение персональных данных клиента."
        )
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}

        user_temp_data[agent_id].update({'message_id': msg.message_id})

        msg2 = bot.send_message(
            client_user_id,
            f"🔔 Агент {agent_data.get('fio', '')} запрашивает ваши персональные данные для формирования договора.",
            reply_markup = keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("request_personal_data_"))
    @prevent_double_click(timeout=3.0)
    def request_personal_data_client(call):
        """Агент выбрал зарегистрированного клиента для создания договора"""
        client_user_id = call.from_user.id
        agent_id = int(call.data.replace("request_personal_data_", ""))
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        # Получаем данные клиента из БД
        client_data = get_admin_from_db_by_user_id(client_user_id)
        
        if not client_data:
            bot.answer_callback_query(call.id, "❌ Данные клиента не найдены", show_alert=True)
            return
        
        # Получаем данные агента
        agent_data = get_admin_from_db_by_user_id(agent_id)
        
        if not agent_data:
            bot.answer_callback_query(call.id, "❌ Данные агента не найдены", show_alert=True)
            return
        db = DatabaseManager()
        # Сохраняем связь клиент-агент в БД
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
                    print(f"✅ Связь сохранена: client={client_user_id}, agent={agent_id}")
        except Exception as e:
            print(f"Ошибка сохранения связи: {e}")
        
        # Инициализируем данные для создания договора
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        from datetime import datetime
        # ЗАГРУЖАЕМ ВСЕ ДАННЫЕ КЛИЕНТА ИЗ БД
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
        
        print(f"✅ Загружены данные клиента {client_user_id} для агента {agent_id}")
        
        # Показываем кнопку для начала заполнения
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            "📋 Начать заполнение договора", 
            callback_data="start_agent_client_contract"
        ))
        keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="callback_start"))
        try:
            bot.delete_message(agent_id, user_temp_data[agent_id]['message_id'])
        except:
            pass

        bot.send_message(
            chat_id=agent_id,
            text=f"✅ Выбран клиент:\n\n"
                f"👤 ФИО: {client_data.get('fio', '')}\n"
                f"📱 Телефон: {client_data.get('number', '')}\n"
                f"🏙 Город: {agent_data.get('city_admin', '')}\n"
                f"📄 Паспорт: {client_data.get('seria_pasport', '')} {client_data.get('number_pasport', '')}\n\n"
                f"Нажмите кнопку для начала заполнения договора:",
            reply_markup=keyboard
        )
        if agent_id in user_temp_data:
            user_temp_data[agent_id].pop('message_id', None)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_personal_data_"))
    @prevent_double_click(timeout=3.0)
    def reject_personal_data_client(call):
        """Отклонение запроса о передачи персональных данных"""
        client_user_id = call.from_user.id
        agent_id = int(call.data.replace("reject_personal_data_", ""))
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        bot.edit_message_text(
            chat_id=agent_id,
            message_id=user_temp_data[agent_id]['message_id'],
            text=f"❌ Клиент отклонил запрос на получение персональных данных",
            reply_markup = keyboard
        )
        if agent_id in user_temp_data:
            user_temp_data[agent_id].pop('message_id', None)
    def process_reinvite_phone_agent(message, agent_id, prev_msg_id):
        """Обработка номера телефона при повторном приглашении"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        phone = message.text.strip()
        
        # Проверка формата телефона
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат номера телефона. Введите снова (например, +79001234567):"
            )
            bot.register_next_step_handler(msg, process_reinvite_phone_agent, agent_id, msg.message_id)
            return
        
        # Получаем сохраненные данные
        reinvite_data = user_temp_data[agent_id].get('reinvite_data', {})
        fio = reinvite_data.get('fio', '')
        
        # Получаем город агента
        agent_data = get_admin_from_db_by_user_id(agent_id)
        city = agent_data.get('city_admin', '') if agent_data else ''
        
        # Генерируем ссылку
        import base64
        fioSplit = fio.split()[0]
        fio_encoded = base64.urlsafe_b64encode(fioSplit.encode('utf-8')).decode('utf-8')
        
        invite_param = f"invagent_{agent_id}_{fio_encoded}"
        
        import config
        bot_username = config.BOT_USERNAME
        invite_link = f"https://t.me/{bot_username}?start={invite_param}"
        
        # Генерируем QR-код
        import qrcode
        from io import BytesIO
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(invite_link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.send_message(
            message.chat.id,
            f"✅ Ссылка-приглашение сформирована!\n\n"
            f"👤 Клиент: {fio}\n"
            f"📱 Телефон: {phone}\n"
            f"🏙 Город: {city}"
        )
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        bot.send_photo(
            message.chat.id,
            photo=bio,
            caption=f"🔗 Ссылка для приглашения:\n\n`{invite_link}`\n\n"
                    f"Отправьте эту ссылку или QR-код клиенту.",
            parse_mode='Markdown',
            reply_markup = keyboard
        )
        
        # Сохраняем в pending_invites с ПОЛНЫМИ данными
        if 'pending_invites' not in user_temp_data:
            user_temp_data['pending_invites'] = {}
        
        invite_key = f"{agent_id}_{fio.split()[0]}"
        user_temp_data['pending_invites'][invite_key] = {
            'phone': phone,
            'agent_id': agent_id,
            'city': city,
            'fio': fio,
            # Добавляем все паспортные данные
            'date_of_birth': reinvite_data.get('date_of_birth', ''),
            'city_birth': reinvite_data.get('city_birth', ''),
            'seria_pasport': reinvite_data.get('seria_pasport', ''),
            'number_pasport': reinvite_data.get('number_pasport', ''),
            'where_pasport': reinvite_data.get('where_pasport', ''),
            'when_pasport': reinvite_data.get('when_pasport', ''),
            'index_postal': reinvite_data.get('index_postal', ''),
            'address': reinvite_data.get('address', '')
        }
        
        print(f"DEBUG: Сохранены данные реинвайта с ключом {invite_key}")
        
        # Очищаем временные данные
        if agent_id in user_temp_data:
            user_temp_data[agent_id].pop('reinvite_data', None)
        
    def process_invite_phone_agent(message, agent_id, prev_msg_id):
        """Обработка номера телефона приглашаемого клиента от агента"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        phone = message.text.strip()
        
        # Проверка формата телефона
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат номера телефона. Введите снова (например, +79001234567):"
            )
            bot.register_next_step_handler(msg, process_invite_phone_agent, agent_id, msg.message_id)
            return
        
        # Сохраняем номер
        user_temp_data[agent_id]['invite_phone'] = phone
        
        # Показываем кнопку для формирования ссылки
        keyboard = types.InlineKeyboardMarkup()
        btn_generate = types.InlineKeyboardButton("🔗 Сформировать ссылку", callback_data="generate_invite_link_agent")
        btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data="callback_start")
        keyboard.add(btn_generate)
        keyboard.add(btn_cancel)
        
        fio = user_temp_data[agent_id].get('invite_fio', '')
        
        bot.send_message(
            message.chat.id,
            f"✅ Данные клиента:\n\n"
            f"👤 ФИО: {fio}\n"
            f"📱 Телефон: {phone}\n\n"
            f"Нажмите кнопку для формирования ссылки-приглашения:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data == "generate_invite_link_agent")
    @prevent_double_click(timeout=3.0)
    def generate_invite_link_agent(call):
        """Генерация ссылки-приглашения от агента"""
        agent_id = call.from_user.id
        data = user_temp_data.get(agent_id, {})
        
        fio = data.get('invite_fio', '')
        phone = data.get('invite_phone', '')
        
        if not fio or not phone:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        # Получаем город агента
        agent_data = get_admin_from_db_by_user_id(agent_id)
        city = agent_data.get('city_admin', '') if agent_data else ''
        fioSplit = fio.split()[0]
        # Кодируем только ФИО
        fio_encoded = base64.urlsafe_b64encode(fioSplit.encode('utf-8')).decode('utf-8')
        
        # Формат: invagent_agentid_fioencoded
        if agent_data.get('admin_value', '') == 'Администратор':
            invite_param = f"invadmin_{agent_id}_{fio_encoded}"
        else:
            invite_param = f"invagent_{agent_id}_{fio_encoded}"
        
        # Создаем ссылку
        bot_username = config.BOT_USERNAME
        invite_link = f"https://t.me/{bot_username}?start={invite_param}"
        
        print(f"DEBUG: Сформирована ссылка от агента:")
        print(f"  - Agent ID: {agent_id}")
        print(f"  - ФИО клиента: {fio}")
        print(f"  - Телефон: {phone}")
        print(f"  - Город: {city}")
        print(f"  - Link: {invite_link}")
        
        # Генерируем QR-код
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(invite_link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Ссылка-приглашение сформирована!\n\n"
                f"👤 Клиент: {fio}\n"
                f"📱 Телефон: {phone}\n"
                f"🏙 Город: {city}"
        )
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        bot.send_photo(
            call.message.chat.id,
            photo=bio,
            caption=f"🔗 Ссылка для приглашения:\n\n`{invite_link}`\n\n"
                    f"Отправьте эту ссылку или QR-код клиенту.",
            parse_mode='Markdown',
            reply_markup = keyboard
        )
        
        # ВАЖНО: Сохраняем данные по ключу agent_id + fio для надежности
        if 'pending_invites' not in user_temp_data:
            user_temp_data['pending_invites'] = {}
        
        # Используем уникальный ключ: agent_id_fio
        invite_key = f"{agent_id}_{fio.split()[0]}"
        user_temp_data['pending_invites'][invite_key] = {
            'phone': phone,
            'agent_id': agent_id,
            'city': city,
            'fio': fio
        }
        
        print(f"DEBUG: Сохранено в pending_invites с ключом: {invite_key}")
        print(f"DEBUG: pending_invites = {user_temp_data['pending_invites']}")
        print(user_temp_data)
        # Очищаем временные данные
        if agent_id in user_temp_data:
            user_temp_data[agent_id].pop('invite_fio', None)
            user_temp_data[agent_id].pop('invite_phone', None)
            user_temp_data[agent_id].pop('invite_process', None)
        print(user_temp_data)
        bot.answer_callback_query(call.id, "✅ Ссылка сформирована!")

    @bot.callback_query_handler(func=lambda call: call.data == "personal_cabinet_client")
    @prevent_double_click(timeout=3.0)
    def personal_cabinet_client_handler(call):
        """Личный кабинет клиента"""
        user_id = call.from_user.id
        
        # Получаем данные клиента из admins
        admin_data = get_admin_from_db_by_user_id(user_id)
        
        if not admin_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        # Получаем список договоров клиента
        from database import get_client_contracts_list
        contracts = get_client_contracts_list(str(user_id))

        # Формируем текст личного кабинета
        cabinet_text = f"👤 <b>Личный кабинет</b>\n\n"
        cabinet_text += f"<b>Личные данные:</b>\n"
        cabinet_text += f"👤 ФИО: {admin_data.get('fio', 'Не указано')}\n"
        cabinet_text += f"👤 Дата рождения: {admin_data.get('date_of_birth', 'Не указано')}\n"
        cabinet_text += f"📱 Телефон: {admin_data.get('number', 'Не указан')}\n"
        cabinet_text += f"🏙 Город: {admin_data.get('city_admin', 'Не указан')}\n\n"

        seria = admin_data.get('seria_pasport', '')
        number = admin_data.get('number_pasport', '')
        # Паспортные данные (если есть)
        if seria and number and seria != '0000' and number != '000000':
            cabinet_text += f"<b>Паспортные данные:</b>\n"
            cabinet_text += f"Серия и номер: {seria} {number}\n"
            if admin_data.get('when_pasport') and admin_data.get('when_pasport') != '-':
                cabinet_text += f"Дата выдачи: {admin_data.get('when_pasport')}\n"
            if admin_data.get('where_pasport') and admin_data.get('where_pasport') != '-':
                cabinet_text += f"Кем выдан: {admin_data.get('where_pasport')}\n"
            if admin_data.get('city_birth') and admin_data.get('city_birth') != '-':
                cabinet_text += f"Город рождения: {admin_data.get('city_birth')}\n"
            if admin_data.get('address') and admin_data.get('address') != '-':
                cabinet_text += f"Адрес прописки: {admin_data.get('address')}\n"
            if admin_data.get('index_postal') and admin_data.get('index_postal') != '-':
                cabinet_text += f"Почтовый индекс: {admin_data.get('index_postal')}\n"
            cabinet_text += "\n"
        
        # Дополнительные данные из последнего договора (если есть)
        if contracts:
            last_contract = contracts[0]
            try:
                contract_data = json.loads(last_contract.get('data_json', '{}'))
            except:
                contract_data = {}
            
            additional_info = []
            
            if contract_data.get('date_of_birth'):
                additional_info.append(f"Дата рождения: {contract_data.get('date_of_birth')}")
            if contract_data.get('city'):
                additional_info.append(f"Город: {contract_data.get('city')}")
            if contract_data.get('address'):
                additional_info.append(f"Адрес: {contract_data.get('address')}")
            if contract_data.get('index_postal'):
                additional_info.append(f"Индекс: {contract_data.get('index_postal')}")
            if contract_data.get('marks'):
                additional_info.append(f"Марка авто: {contract_data.get('marks')}")
            if contract_data.get('car_number'):
                additional_info.append(f"Номер авто: {contract_data.get('car_number')}")
            
            if additional_info:
                cabinet_text += "<b>Дополнительная информация:</b>\n"
                cabinet_text += "\n".join(additional_info)
                cabinet_text += "\n\n"
        db = DatabaseManager()
        balance_data = db.get_client_balance(str(user_id))

        if balance_data['balance'] > 0 or balance_data['total_earned'] > 0:
            cabinet_text += f"\n💰 <b>Реферальный баланс:</b>\n"
            cabinet_text += f"Доступно: {balance_data['balance']:.2f} руб.\n"
            cabinet_text += f"Всего заработано: {balance_data['total_earned']:.2f} руб.\n\n"
        # Список договоров
        cabinet_text += f"<b>📋 Ваши договоры ({len(contracts)}):</b>\n"
        
        keyboard = types.InlineKeyboardMarkup()
        
        if contracts:
            for contract in contracts:
                contract_id = contract.get('client_id', 'Неизвестно')
                created_at = contract.get('created_at', 'Неизвестно')
                status = contract.get('status', 'В обработке')
                
                btn_text = f"📄 Договор {contract_id} от {created_at}"
                callback_data = f"view_contract_{contract_id}"
                
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
        else:
            cabinet_text += "\n❌ Не оформлено ни одного договора"
        keyboard.add(types.InlineKeyboardButton("✏️ Изменить данные", callback_data="change_data"))
        if balance_data['balance'] > 0:
            keyboard.add(types.InlineKeyboardButton("💸 Вывести средства", callback_data="request_client_withdrawal"))
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=cabinet_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "request_client_withdrawal")
    @prevent_double_click(timeout=3.0)
    def request_appraiser_withdrawal_handler(call):
        """Запрос на вывод средств оценщиком"""
        client_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💸 Введите сумму для вывода:"
        )
        
        bot.register_next_step_handler(call.message, process_client_withdrawal_amount, client_id, call.message.message_id)

    def process_client_withdrawal_amount(message, client_id, prev_message_id):
        """Обработка суммы вывода оценщика"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        db = DatabaseManager()
        try:
            amount = float(message.text.strip())
        except ValueError:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат. Введите число:"
            )
            bot.register_next_step_handler(msg, process_client_withdrawal_amount, client_id, msg.message_id)
            return
        
        if amount <= 0:
            msg = bot.send_message(
                message.chat.id,
                "❌ Сумма должна быть положительной. Введите снова:"
            )
            bot.register_next_step_handler(msg, process_client_withdrawal_amount, client_id, msg.message_id)
            return
        
        balance_data = db.get_client_balance(str(client_id))
        if amount > balance_data['balance']:
            msg = bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств. Ваш баланс: {balance_data['balance']:.2f} руб.\n"
                f"Введите сумму не больше баланса:"
            )
            bot.register_next_step_handler(msg, process_client_withdrawal_amount, client_id, msg.message_id)
            return
        
        # Создаем заявку
        client_data = get_admin_from_db_by_user_id(client_id)
        client_fio = client_data.get('fio', 'Оценщик')
        
        withdrawal_id = db.create_withdrawal_request(str(client_id), client_fio, amount)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        if withdrawal_id:
            bot.send_message(
                message.chat.id,
                f"✅ Заявка на вывод {amount:.2f} руб. отправлена на подпись.",
                reply_markup=keyboard
            )
            
            # Уведомляем всех директоров
            notify_directors_about_withdrawal(bot, client_fio, amount)
        else:
            bot.send_message(
                message.chat.id,
                "❌ Ошибка создания заявки. Попробуйте позже.",
                reply_markup=keyboard
            )

    def notify_directors_about_withdrawal(bot, employee_fio, amount):
        """Уведомить всех директоров о заявке на вывод"""
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT user_id FROM admins 
                        WHERE admin_value = 'Бухгалтер'
                    """)
                    directors = cursor.fetchall()
                    
                    for director in directors:
                        try:
                            keyboard = types.InlineKeyboardMarkup()
                            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                            bot.send_message(
                                director[0],
                                f"📝 Поступил документ на подпись от {employee_fio}\n"
                                f"💰 Сумма: {amount:.2f} руб.",
                                reply_markup=keyboard
                            )
                        except Exception as e:
                            print(f"Не удалось уведомить директора {director[0]}: {e}")
        except Exception as e:
            print(f"Ошибка уведомления директоров: {e}")
    @bot.callback_query_handler(func=lambda call: call.data == "change_data")
    @prevent_double_click(timeout=3.0)
    def change_registration_data_handler(call):
        """Показ кнопок для изменения конкретных полей"""
        user_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("👤 ФИО", callback_data="edit_fio_client"))
        keyboard.add(types.InlineKeyboardButton("📱 Номер телефона", callback_data="edit_phone_client"))
        keyboard.add(types.InlineKeyboardButton("🏙 Город", callback_data="edit_city_client"))
        keyboard.add(types.InlineKeyboardButton("📅 Дата рождения", callback_data="edit_birth_date_client"))
        keyboard.add(types.InlineKeyboardButton("🏙 Город рождения", callback_data="edit_birth_city_client"))
        keyboard.add(types.InlineKeyboardButton("📄 Серия паспорта", callback_data="edit_passport_series_client"))
        keyboard.add(types.InlineKeyboardButton("📄 Номер паспорта", callback_data="edit_passport_number_client"))
        keyboard.add(types.InlineKeyboardButton("🏢 Кем выдан", callback_data="edit_passport_issued_client"))
        keyboard.add(types.InlineKeyboardButton("📅 Когда выдан", callback_data="edit_passport_date_client"))
        keyboard.add(types.InlineKeyboardButton("🏠 Адрес прописки", callback_data="edit_address_client"))
        keyboard.add(types.InlineKeyboardButton("📮 Почтовый индекс", callback_data="edit_postal_client"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к личному кабинету", callback_data="personal_cabinet_client"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите поле для изменения:",
            reply_markup=keyboard
        )
    # ========== ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ ПОЛЕЙ ==========
    @bot.callback_query_handler(func=lambda call: call.data == "edit_fio_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
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
        
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_phone_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        phone = message.text.strip()
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            msg = bot.send_message(message.chat.id, "❌ Неверный формат. Введите заново:")
            bot.register_next_step_handler(msg, update_phone, data, msg.message_id)
            return
        
        data['number'] = phone
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_city_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['city_admin'] = message.text.strip()
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_birth_date_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['date_of_birth'] = date_text
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_birth_city_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['city_birth'] = message.text.strip()
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_series_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['seria_pasport'] = series
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_number_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['number_pasport'] = number
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_issued_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['where_pasport'] = message.text.strip()
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_passport_date_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['when_pasport'] = date_text
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "edit_address_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['address'] = message.text.strip()
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)
    @bot.callback_query_handler(func=lambda call: call.data == "edit_postal_client")
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
        data = get_admin_from_db_by_user_id(message.from_user.id)
        data['index_postal'] = index
        try:
            db = DatabaseManager()
            db.update_admin(data)
        except Exception as e:
            print(f"❌ Ошибка сохранения в БД: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
            bot.send_message(message.from_user.id, "❌ Ошибка при сохранении данных. Попробуйте позже.", reply_markup = keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        bot.send_message(message.from_user.id, "✅ Данные сохранены", reply_markup = keyboard)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_contract_"))
    @prevent_double_click(timeout=3.0)
    def view_contract_handler(call):
        """Просмотр конкретного договора"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        client_id = call.data.replace("view_contract_", "")
        cleanup_messages(bot, call.message.chat.id, call.message.message_id-1, count=5)
        # Получаем данные договора
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
        
        # Формируем текст с информацией о договоре
        contract_text = f"📄 <b>Договор {client_id}</b>\n\n"
        
        if contract.get('created_at'):
            contract_text += f"📅 Дата создания: {contract.get('created_at')}\n\n"
        
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

        payment_pending = contract_data.get('payment_pending', '') == 'Yes'
        payment_confirmed = contract_data.get('payment_confirmed', '') == 'Yes'
        doverennost_pending = contract_data.get('doverennost_pending', '') == 'Yes'
        doverennost_confirmed = contract_data.get('doverennost_confirmed', '') == 'Yes'


        if doverennost_pending and not doverennost_confirmed:
            contract_text += "\n⏳ Доверенность ожидает проверки"
        elif doverennost_confirmed:
            contract_text += "\n📜 Доверенность подтверждена"
        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id] = contract
        user_temp_data[user_id]['client_id'] = client_id

        keyboard = types.InlineKeyboardMarkup()

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
            keyboard.add(types.InlineKeyboardButton("📥 Скачать шаблон доверенности", callback_data=f"download_shablon_dov_{client_id}"))
        
        if contract_data.get('accident') == 'ДТП' and contract_data.get('sobstvenik', '') == 'После ответа от страховой':
            if contract_data.get('dop_osm') != 'Yes' and contract_data.get('vibor', '') == '':
                keyboard.add(types.InlineKeyboardButton("📋 Заявление на доп. осмотр", callback_data=f"dop_osm_yes_{client_id}"))
            # Кнопка "Ответ от страховой" - только если еще не заполнялась
            if contract_data.get('vibor', '') == '':
                keyboard.add(types.InlineKeyboardButton("❓ Ответ от страховой", callback_data=f"client_answer_insurance_{client_id}"))
        
                
        if contract_data.get('accident', '') != 'После ямы':
            keyboard.add(types.InlineKeyboardButton("📤 Добавить выплату от страховой", callback_data="add_osago_payment"))
        keyboard.add(types.InlineKeyboardButton("📸 Загрузить фото ДТП", callback_data="download_foto"))
        keyboard.add(types.InlineKeyboardButton("📤 Загрузить документы", callback_data="download_docs"))
        keyboard.add(types.InlineKeyboardButton("📋 Просмотр данных", callback_data="view_db"))
        keyboard.add(types.InlineKeyboardButton("✏️ Редактировать данные", callback_data=f"edit_contract_data_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("📂 Просмотреть документы", callback_data="view_client_documents"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="personal_cabinet_client"))
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))

        bot.send_message(
            chat_id=call.message.chat.id,
            text=contract_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "add_osago_payment")
    @prevent_double_click(timeout=3.0)
    def handle_add_osago_payment(call):
        """Запрос суммы выплаты ОСАГО"""
        user_id = call.from_user.id
        client_id = user_temp_data[user_id]['client_id']
        
        keyboard = types.InlineKeyboardMarkup()
        callback_data = get_contract_callback(user_id, client_id)
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=callback_data))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💰 Введите сумму выплаты по ОСАГО (только число):",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(call.message, process_osago_amount, user_id, call.message.message_id)
    def process_osago_amount(message, user_id, prev_message_id):
        """Обработка суммы выплаты ОСАГО"""
        try:
            bot.delete_message(message.chat.id, prev_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            amount = float(message.text.strip().replace(',', '.'))
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Введите корректное число:")
            bot.register_next_step_handler(msg, process_osago_amount, user_id, msg.message_id)
            return
        
        client_id = user_temp_data[user_id]['client_id']
        
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
        
        data['coin_osago'] = str(new_total)  # В основном поле тоже

        
        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(data)
            client_data.update(updated_data)
            print(client_data)
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
        create_fio_data_file(data)
        # Сохраняем сумму для загрузки квитанции
        user_temp_data[user_id]['osago_amount'] = amount
        user_temp_data[user_id]['osago_total'] = new_total
        
        # Инициализируем сессию загрузки квитанции
        upload_sessions[message.chat.id] = {
            'client_id': user_id,
            'photos': [],
            'message_id': None,
            'number_id': client_id
        }
        
        msg = bot.send_message(
            message.chat.id,
            f"✅ Добавлено: {amount} руб.\n"
            f"💰 Общая сумма выплат: {new_total} руб.\n\n"
            f"📸 Теперь загрузите квитанцию (одну или несколько фотографий):",
            reply_markup=create_upload_keyboard_osago()
        )
        
        upload_sessions[message.chat.id]['message_id'] = msg.message_id

    def create_upload_keyboard_osago():
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_upload_osago"))
        return keyboard    
    

    @bot.callback_query_handler(func=lambda call: call.data == 'finish_upload_osago')
    def handle_finish_upload_osago(call):
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
            
            keyboard = types.InlineKeyboardMarkup()
            user_id = session['client_id']
            callback_data = get_contract_callback(user_id, client_id)
            keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=callback_data))
            
            osago_amount = user_temp_data.get(user_id, {}).get('osago_amount', 0)
            osago_total = user_temp_data.get(user_id, {}).get('osago_total', 0)
            
            bot.send_message(
                chat_id,
                f"✅ Квитанция успешно сохранена как '{filename}'!\n"
                f"💰 Добавлено: {osago_amount} руб.\n"
                f"💰 Итого выплат: {osago_total} руб.\n"
                f"📸 Загружено фото: {len(session['photos'])}",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Error creating PDF: {e}")
            bot.send_message(chat_id, "❌ Ошибка при создании PDF файла")
        
        # Очищаем сессию
        del upload_sessions[chat_id]
        if user_id in user_temp_data:
            user_temp_data[user_id].pop('osago_amount', None)
            user_temp_data[user_id].pop('osago_total', None)
        
        bot.answer_callback_query(call.id)

    # Обработчик для фото через lambda с проверкой состояния
    @bot.message_handler(
        content_types=['photo'],
        func=lambda message: message.chat.id in upload_sessions and 'number_id' in upload_sessions.get(message.chat.id, {})
    )
    def handle_calc_photo(message):
        chat_id = message.chat.id
        session = upload_sessions[chat_id]
        print(4)
        try:
            # Получаем фото максимального качества
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем фото во временную папку
            temp_path = f"temp_{chat_id}_{len(session['photos'])}.jpg"
            with open(temp_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            # Добавляем путь к фото в сессию
            session['photos'].append(temp_path)
            
            # Удаляем сообщение пользователя с фото
            bot.delete_message(chat_id, message.message_id)
            if upload_sessions[chat_id].get('type', '') == 'insurance_payment':
                bot.edit_message_text(
                chat_id=chat_id,
                message_id=session['message_id'],
                text=f"📸 Фото загружено ({len(session['photos'])} фото)\n\n"
                    "Продолжайте загружать фото или нажмите 'Завершить загрузку'",
                reply_markup=create_upload_keyboard_insurance()
            )
            elif upload_sessions[chat_id].get('type', '') == 'client_insurance_payment':
                bot.edit_message_text(
                chat_id=chat_id,
                message_id=session['message_id'],
                text=f"📸 Фото загружено ({len(session['photos'])} фото)\n\n"
                    "Продолжайте загружать фото или нажмите 'Завершить загрузку'",
                reply_markup=create_upload_keyboard_client_insurance()
            )
            else:
                # Обновляем сообщение бота
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=session['message_id'],
                    text=f"📸 Фото загружено ({len(session['photos'])} фото)\n\n"
                        "Продолжайте загружать фото или нажмите 'Завершить загрузку'",
                    reply_markup=create_upload_keyboard_osago()
                )
            
        except Exception as e:
            print(f"Error processing photo: {e}")
            bot.send_message(chat_id, "❌ Ошибка при загрузке фото")
    def create_upload_keyboard_client_insurance():
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_upload_client_insurance_payment"))
        return keyboard
    def create_upload_keyboard_insurance():
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_upload_insurance_payment"))
        return keyboard
    
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
    @bot.callback_query_handler(func=lambda call: call.data.startswith("download_shablon_dov_"))
    @prevent_double_click(timeout=3.0)
    def callback_download_shablon_dov(call):
        """Отправка шаблона доверенности"""
        try:
            client_id = call.data.replace("download_shablon_dov_", "")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            file_path = "Шаблон доверенности.pdf"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"view_contract_{client_id}"))
            # Проверяем существование файла
            if os.path.exists(file_path):
                # Открываем и отправляем файл
                with open(file_path, 'rb') as file:
                    bot.send_document(
                        chat_id=call.message.chat.id,
                        document=file
                    )
                bot.send_message(call.message.chat.id, "✅ Файл отправлен", reply_markup = keyboard)
            else:
                bot.send_message(call.message.chat.id, "❌ Файл не найден", reply_markup = keyboard)
                
        except Exception as e:
            print(f"❌ Ошибка при отправке файла: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при отправке файла", show_alert=True)
    @bot.callback_query_handler(func=lambda call: call.data == "btn_search_database")
    @prevent_double_click(timeout=3.0)
    def callback_search_database(call):
        """Поиск клиентов по ФИО для всех ролей"""
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔍 Введите фамилию и имя клиента для поиска:",
            reply_markup=keyboard
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, search_all_clients_handler, user_message_id, call.from_user.id, user_temp_data)

    def search_all_clients_handler(message, user_message_id, user_id, user_temp_data):
        """Обработчик поиска всех клиентов по ФИО"""
        import time
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        search_term = message.text.strip()
        
        if len(search_term) < 2:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
            msg = bot.send_message(message.chat.id, "❌ Введите минимум 2 символа для поиска", reply_markup = keyboard)
            bot.register_next_step_handler(msg, search_all_clients_handler, msg.message_id, user_id, user_temp_data)
            return
        
        try:
            from database import search_clients_by_fio_in_db
            
            search_msg = bot.send_message(message.chat.id, "🔍 Поиск в базе данных...")
            results = search_clients_by_fio_in_db(search_term)
            
            try:
                bot.delete_message(message.chat.id, search_msg.message_id)
            except:
                pass
            
            if not results:
                msg = bot.send_message(message.chat.id, f"❌ Клиенты с ФИО '{search_term}' не найдены")
                time.sleep(1)
                bot.delete_message(msg.chat.id, msg.message_id)
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                bot.send_message(message.chat.id, "Возврат в главное меню", reply_markup=keyboard)
                return
            
            # Показываем результаты поиска
            response = f"🔍 Найдено клиентов по запросу '{search_term}': {len(results)}\n\n"
            keyboard = types.InlineKeyboardMarkup()
            
            for i, client in enumerate(results[:10], 1):
                response += f"{i}. 📋 ID: {client['client_id']}\n"
                response += f"   👤 {client['fio']}\n"
                response += f"   📱 {client.get('number', 'Не указан')}\n"
                response += f"   📅 ДТП: {client.get('date_dtp', 'Не указана')}\n\n"
                
                btn_text = f"{i}. {client['fio'][:20]}..."
                btn_callback = get_contract_callback(user_id, client['client_id'])
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
            
            if len(results) > 10:
                response += f"... и еще {len(results) - 10} клиентов"
            
            keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database"))
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.send_message(message.chat.id, response, reply_markup=keyboard)
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка поиска: {e}")
            print(f"Ошибка поиска: {e}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_view_contract_"))
    @prevent_double_click(timeout=3.0)
    def admin_view_contract_handler(call):
        """Просмотр договора администратором/директором"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        client_id = call.data.replace("admin_view_contract_", "")
        cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=7)
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
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id] = contract
        user_temp_data[user_id]['client_id'] = client_id
        
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
        
        # Проверяем статус оплаты
        payment_confirmed = contract_data.get('payment_confirmed', '') == 'Yes'
        payment_pending = contract_data.get('payment_pending', '') == 'Yes'
        
        if payment_pending and not payment_confirmed:
            contract_text += "\n⏳ Ожидает проверки оплаты"
            approval_id = None
            try:
                db = DatabaseManager()
                with db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT id FROM pending_approvals 
                            WHERE client_id = %s AND document_type = 'payment' AND status = 'pending'
                            ORDER BY created_at DESC
                            LIMIT 1
                        """, (client_id,))
                        result = cursor.fetchone()
                        if result:
                            approval_id = result[0]
            except Exception as e:
                print(f"Ошибка получения approval_id: {e}")
            keyboard.add(types.InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"approve_document_{approval_id}"))
            keyboard.add(types.InlineKeyboardButton("❌ Отклонить оплату", callback_data=f"reject_payment_{client_id}"))
        elif payment_confirmed:
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
        # Проверяем статус доверенности
        doverennost_confirmed = contract_data.get('doverennost_confirmed', '') == 'Yes'
        doverennost_pending = contract_data.get('doverennost_pending', '') == 'Yes'
        
        if doverennost_pending and not doverennost_confirmed:
            contract_text += "\n⏳ Ожидает проверки доверенности"
            keyboard.add(types.InlineKeyboardButton("✅ Подтвердить доверенность", callback_data=f"approve_doverennost_{client_id}"))
            keyboard.add(types.InlineKeyboardButton("❌ Отклонить доверенность", callback_data=f"reject_doverennost_{client_id}"))
        elif doverennost_confirmed:
            contract_text += "\n📜 Доверенность подтверждена"
        
        status = contract.get('status', '')
        if contract.get('accident', '') == 'ДТП':
            if status == "Ожидание претензии" and doverennost_confirmed and payment_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Составить претензию", callback_data=f"create_pretenziya_{client_id}"))
            elif status == "Составлена претензия" and doverennost_confirmed and payment_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Заявление Фин.омбудсмену", callback_data=f"create_ombudsmen_{client_id}"))
            # elif status == "Составлено заявление к Фин.омбудсмену":
            #     keyboard.add(types.InlineKeyboardButton("📝 Исковое заявление", callback_data=f"create_isk_{client_id}"))
        elif contract.get('accident', '') == 'Нет ОСАГО':
            if status == "Деликт" and doverennost_confirmed and payment_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Исковое заявление", callback_data=f"create_delict_{client_id}"))
        elif contract.get('accident', '') == 'Подал заявление':
            if status == "Деликт" and doverennost_confirmed and payment_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Исковое заявление", callback_data=f"create_delictViplat_{client_id}"))
            elif contract.get('viborRem', '') == 'Цессия' and status == 'Составлено заявление о выдаче документов ГИБДД' and doverennost_confirmed and payment_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Договор Цессии", callback_data=f"create_cecciaDogovor_{client_id}"))
            elif contract.get('viborRem', '') == 'Цессия' and status == 'Составлен договор Цессии'and doverennost_confirmed and payment_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Иск в суд", callback_data=f"create_cecciaIsk_{client_id}"))
            elif contract.get('viborRem', '') == 'Заявление' and status == "Ожидание претензии":
                keyboard.add(types.InlineKeyboardButton("📝 Составить претензию", callback_data=f"create_pretenziya_zayavlenie_{client_id}"))
            elif contract.get('viborRem', '') == 'Заявление' and status == "Составлена претензия":
                keyboard.add(types.InlineKeyboardButton("📝 Заявление Фин.омбудсмену", callback_data=f"create_ombudsmen_zayavlenie_{client_id}"))
                
        keyboard.add(types.InlineKeyboardButton("📸 Загрузить фото ДТП", callback_data="download_foto"))
        keyboard.add(types.InlineKeyboardButton("📤 Загрузить документы", callback_data="download_docs"))
        keyboard.add(types.InlineKeyboardButton("📋 Просмотр данных", callback_data="view_db"))
        keyboard.add(types.InlineKeyboardButton("✏️ Редактировать данные", callback_data=f"edit_contract_data_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("📂 Просмотреть документы", callback_data="view_client_documents"))
        keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database"))

        from database import get_admin_from_db_by_user_id
        admin_data = get_admin_from_db_by_user_id(user_id)
        if admin_data and admin_data.get('admin_value') == 'Директор':
            if status != 'Завершен':
                keyboard.add(types.InlineKeyboardButton("🔒 Закрыть дело", callback_data=f"close_case_{client_id}"))

        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.send_message(
            chat_id=call.message.chat.id,
            text=contract_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("close_case_"))
    @prevent_double_click(timeout=3.0)
    def close_case_handler(call):
        """Директор инициирует закрытие дела - показываем подтверждение"""
        client_id = call.data.replace("close_case_", "")
        
        from database import get_client_from_db_by_client_id
        contract = get_client_from_db_by_client_id(client_id)
        
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        fio = contract.get('fio', 'клиент')
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_close_case_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=f"back_to_contract_{client_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔒 <b>Закрытие дела</b>\n\n"
                f"📋 Договор: {client_id}\n"
                f"👤 Клиент: {fio}\n\n"
                f"⚠️ Вы уверены, что хотите закрыть дело?\n"
                f"Статус договора будет изменен на 'Завершен'.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_close_case_"))
    @prevent_double_click(timeout=3.0)
    def confirm_close_case_handler(call):
        """Подтверждение закрытия дела - обновляем статус"""
        client_id = call.data.replace("confirm_close_case_", "")
        director_id = call.from_user.id
        
        from database import DatabaseManager
        db_instance = DatabaseManager()
        
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Обновляем статус договора на "Завершен"
                    cursor.execute("""
                        UPDATE clients 
                        SET status = 'Завершен'
                        WHERE client_id = %s
                    """, (client_id,))
                    conn.commit()
            
            print(f"✅ Дело {client_id} закрыто директором {director_id}")
            
            # Уведомляем об успехе
            bot.answer_callback_query(call.id, "✅ Дело закрыто", show_alert=True)
            
            # Возвращаемся к просмотру договора
            call.data = f"admin_view_contract_{client_id}"
            admin_view_contract_handler(call)
            
        except Exception as e:
            print(f"❌ Ошибка закрытия дела: {e}")
            import traceback
            traceback.print_exc()
            bot.answer_callback_query(call.id, "❌ Ошибка при закрытии дела", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_contract_"))
    @prevent_double_click(timeout=3.0)
    def back_to_contract_handler(call):
        """Возврат к просмотру договора без изменений"""
        client_id = call.data.replace("back_to_contract_", "")
        
        # Переходим обратно к просмотру договора
        call.data = get_contract_callback(call.from_user.id, client_id)
        admin_view_contract_handler(call)
    @bot.callback_query_handler(func=lambda call: call.data == "view_db")
    @prevent_double_click(timeout=3.0)
    def callback_view_data(call):
        """Просмотр данных клиента из файла"""
        import os
        
        try:
            user_id = call.from_user.id
            
            client_data = None
            if user_id in user_temp_data:
                client_data = user_temp_data[user_id]
            
            if not client_data or 'client_id' not in client_data:
                bot.answer_callback_query(call.id, "Ошибка: данные клиента не найдены")
                return
            
            client_id = client_data['client_id']
            
            from database import get_client_from_db_by_client_id
            full_client_data = get_client_from_db_by_client_id(client_id)
            
            if not full_client_data:
                bot.answer_callback_query(call.id, "Клиент не найден в базе данных")
                return
            
            fio = full_client_data.get('fio', '')
            
            try:
                if full_client_data.get('data_json'):
                    json_data = json.loads(full_client_data['data_json'])
                    merged_data = {**full_client_data, **json_data}
                else:
                    merged_data = full_client_data
            except (json.JSONDecodeError, TypeError):
                merged_data = full_client_data
            
            if 'data_json' in merged_data:
                del merged_data['data_json']
            if 'id' in merged_data:
                del merged_data['id']
            
            fio_file_path = os.path.join(f"clients/{client_id}", f"{fio}_data.txt")
            
            if not os.path.exists(fio_file_path):
                try:
                    from word_utils import create_fio_data_file
                    create_fio_data_file(merged_data)
                except Exception as e:
                    bot.answer_callback_query(call.id, f"Ошибка создания файла данных: {e}")
                    return
            
            try:
                with open(fio_file_path, 'r', encoding='utf-8') as file:
                    file_content = file.read()
            except Exception as e:
                bot.answer_callback_query(call.id, f"Ошибка чтения файла: {e}")
                return
            
            message_text = f"📋 <b>Текущие данные клиента {fio}:</b>\n\n<pre>{file_content}</pre>"
            
            keyboard = types.InlineKeyboardMarkup()
            
            # Проверяем, откуда пришел пользователь
            from database import get_admin_from_db_by_user_id
            admin_data = get_admin_from_db_by_user_id(user_id)
            
            callback_data = get_contract_callback(user_id, client_id)
            btn_back = types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data)
            
            keyboard.add(btn_back)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}")
            print(f"Ошибка в callback_view_data: {e}")
            import traceback
            traceback.print_exc()

    

    @bot.callback_query_handler(func=lambda call: call.data.startswith("approve_doverennost_"))
    @prevent_double_click(timeout=3.0)
    def callback_approve_doverennost(call):
        """Подтверждение оплаты директором"""
        user_id = call.from_user.id
        approval_id = call.data.replace("approve_doverennost_", "")
        
        db = DatabaseManager()
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM pending_approvals WHERE id = %s", (approval_id,))
                approval = cursor.fetchone()
                
                if not approval:
                    bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                    return
                
                client_id = approval['client_id']
                client_user_id = approval['user_id']
                
                # Обновляем статус
                cursor.execute("""
                    UPDATE pending_approvals 
                    SET status = 'approved', reviewed_by = %s, reviewed_at = NOW()
                    WHERE id = %s
                """, (str(user_id), approval_id))
                
                cursor.execute("""
                    UPDATE clients 
                    SET data_json = jsonb_set(
                        jsonb_set(
                            COALESCE(data_json::jsonb, '{}'::jsonb),
                            '{doverennost_confirmed}',
                            '"Yes"'
                        ),
                        '{doverennost_pending}',
                        '"No"'
                    )
                    WHERE client_id = %s
                """, (client_id,))
                
                conn.commit()
        
        # Удаляем все сообщения из процесса проверки (файлы + инфо)
        try:
            # Удаляем последние 5 сообщений (2 файла + текст + возможные другие)
            for i in range(5):
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id - i)
                except:
                    pass
        except:
            pass
        
        # Уведомление клиента
        if client_user_id:
            try:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📄 К договору", callback_data=get_contract_callback(client_user_id, client_id)))
                bot.send_message(
                    int(client_user_id),
                    "✅ Ваша доверенность подтверждена администратором",
                    reply_markup=keyboard
                )
            except Exception as e:
                print(f"Ошибка уведомления клиента: {e}")
        
        # Сообщение администратору с кнопкой "На утверждение"
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📝 На утверждение", callback_data="director_approvals"))
        
        bot.send_message(
            call.message.chat.id,
            f"✅ Доверенность по договору {client_id} подтверждена!",
            reply_markup=keyboard
        )
        


    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_doverennost_"))
    @prevent_double_click(timeout=3.0)
    def callback_reject_doverennost_request_reason(call):
        """Запрос причины отклонения доверенности"""
        user_id = call.from_user.id
        approval_id = int(call.data.replace("reject_doverennost_", ""))
        
        # Сохраняем approval_id для следующего шага
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]['reject_doverennost_approval_id'] = approval_id
        
        # Удаляем предыдущее сообщение
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # Запрашиваем причину
        msg = bot.send_message(
            call.message.chat.id,
            "❌ <b>Отклонение доверенности</b>\n\nВведите причину отклонения:",
            parse_mode='HTML'
        )
        
        bot.register_next_step_handler(msg, process_doverennost_rejection_reason, user_id, msg.message_id)


    def process_doverennost_rejection_reason(message, user_id, prev_msg_id):
        """Обработка причины отклонения доверенности"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        reason = message.text.strip()
        
        if not reason or len(reason) < 3:
            msg = bot.send_message(
                message.chat.id,
                "❌ Причина слишком короткая. Введите причину отклонения (минимум 3 символа):"
            )
            bot.register_next_step_handler(msg, process_doverennost_rejection_reason, user_id, msg.message_id)
            return
        
        # Получаем approval_id
        approval_id = user_temp_data[user_id].get('reject_doverennost_approval_id')
        if not approval_id:
            bot.send_message(message.chat.id, "❌ Ошибка: данные не найдены")
            return
        
        # Обновляем статус с причиной
        db = DatabaseManager()
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM pending_approvals WHERE id = %s", (approval_id,))
                approval = cursor.fetchone()
                
                if not approval:
                    bot.send_message(message.chat.id, "❌ Документ не найден")
                    return
                
                client_id = approval['client_id']
                client_user_id = approval['user_id']
                
                # Обновляем со статусом rejected и причиной
                cursor.execute("""
                    UPDATE pending_approvals 
                    SET status = 'rejected', 
                        reviewed_by = %s, 
                        reviewed_at = NOW(),
                        rejection_reason = %s
                    WHERE id = %s
                """, (str(user_id), reason, approval_id))
                
                # Сбрасываем флаг
                cursor.execute("""
                    UPDATE clients 
                    SET data_json = jsonb_set(
                        jsonb_set(
                            COALESCE(data_json::jsonb, '{}'::jsonb),
                            '{doverennost_pending}',
                            '"No"'
                        ),
                        '{doverennost_provided}',
                        '"No"'
                    )
                    WHERE client_id = %s
                """, (client_id,))
                
                conn.commit()
        
        # Удаляем все сообщения из процесса проверки
        try:
            for i in range(5):
                try:
                    bot.delete_message(message.chat.id, message.message_id - i)
                except:
                    pass
        except:
            pass
        
        # Уведомляем клиента с причиной
        if client_user_id:
            try:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("📄 К договору", callback_data=f"view_contract_{client_id}"))
                bot.send_message(
                    int(client_user_id),
                    f"❌ Ваша доверенность по договору {client_id} отклонена.\n\n"
                    f"<b>Причина:</b> {reason}\n\n"
                    f"Пожалуйста, загрузите корректный документ.",
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Ошибка уведомления клиента: {e}")
        
        # Очищаем временные данные
        if user_id in user_temp_data:
            user_temp_data[user_id].pop('reject_doverennost_approval_id', None)
        
        # Сообщение администратору с кнопкой "На утверждение"
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📝 На утверждение", callback_data="director_approvals"))
        
        bot.send_message(
            message.chat.id,
            f"❌ Доверенность по договору {client_id} отклонена.\n\n"
            f"<b>Причина:</b> {reason}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    # ========== ОБРАБОТЧИКИ ЛИЧНОГО КАБИНЕТА КЛИЕНТА ==========

    @bot.callback_query_handler(func=lambda call: call.data == "btn_search_city_clients")
    @prevent_double_click(timeout=3.0)
    def callback_search_city_clients(call):
        """Поиск клиентов по ФИО в рамках города администратора"""
        user_id = call.from_user.id
        
        # Получаем город администратора
        admin_data = get_admin_from_db_by_user_id(user_id)
        if not admin_data or not admin_data.get('city_admin'):
            bot.answer_callback_query(call.id, "❌ Город не определен", show_alert=True)
            return
        
        city = admin_data['city_admin']
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"callback_start"))
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔍 Поиск клиентов в городе: {city}\n\nВведите фамилию и имя клиента:",
            reply_markup=keyboard
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, search_city_clients_handler, user_message_id, user_id, city, user_temp_data)

    def search_city_clients_handler(message, user_message_id, user_id, city, user_temp_data):
        """Обработчик поиска клиентов по ФИО в городе с учетом ё/е"""
        import time
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        search_term = message.text.strip()
        
        if len(search_term) < 2:
            msg = bot.send_message(message.chat.id, "❌ Введите минимум 2 символа для поиска")
            bot.register_next_step_handler(msg, search_city_clients_handler, msg.message_id, user_id, city, user_temp_data)
            return
        
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            
            search_msg = bot.send_message(message.chat.id, f"🔍 Поиск в базе данных по городу {city}...")
            
            # Функция для замены ё на е и наоборот
            def get_e_yo_variants(text):
                variants = set()
                variants.add(text)  # оригинал
                
                # Замена ё на е
                if 'ё' in text.lower():
                    variants.add(text.replace('ё', 'е').replace('Ё', 'Е'))
                
                # Замена е на ё
                if 'е' in text.lower():
                    variants.add(text.replace('е', 'ё').replace('Е', 'Ё'))
                
                return list(variants)
            
            # Генерируем варианты поиска с учетом ё/е
            search_variants = get_e_yo_variants(search_term)
            print(f"Варианты поиска с ё/е: {search_variants}")
            
            # Создаем все возможные паттерны для поиска
            search_patterns = set()
            for variant in search_variants:
                search_patterns.add(f"%{variant}%")
                search_patterns.add(f"%{variant.lower()}%")
                search_patterns.add(f"%{variant.upper()}%")
                search_patterns.add(f"%{variant.title()}%")
            
            # Преобразуем в список для использования в запросе
            search_patterns = list(search_patterns)
            
            # Поиск клиентов с фильтром по городу
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Создаем динамический запрос с несколькими условиями OR
                    placeholders = ', '.join(['%s'] * len(search_patterns))
                    query = f'''
                    SELECT id, client_id, fio, number, car_number, date_dtp, created_at
                    FROM clients 
                    WHERE city = %s AND (
                        {' OR '.join(['fio ILIKE %s'] * len(search_patterns))}
                    )
                    ORDER BY id DESC
                    '''
                    
                    # Параметры: сначала город, потом все паттерны
                    params = [city] + search_patterns
                    
                    print(f"Выполняем запрос с {len(search_patterns)} вариантами поиска")
                    cursor.execute(query, params)
                    results = cursor.fetchall()
            
            try:
                bot.delete_message(message.chat.id, search_msg.message_id)
            except:
                pass
            
            if not results:
                # Дополнительный поиск по отдельным словам с учетом ё/е
                if len(search_term.split()) >= 2:
                    search_words = search_term.split()
                    first_word = search_words[0].strip()
                    second_word = search_words[1].strip()
                    
                    # Варианты с ё/е для каждого слова
                    first_word_variants = get_e_yo_variants(first_word)
                    second_word_variants = get_e_yo_variants(second_word)
                    
                    with db.get_connection() as conn:
                        with conn.cursor() as cursor:
                            # Пробуем комбинации слов
                            for first_variant in first_word_variants:
                                for second_variant in second_word_variants:
                                    query = '''
                                    SELECT id, client_id, fio, number, car_number, date_dtp, created_at
                                    FROM clients 
                                    WHERE city = %s 
                                    AND fio ILIKE %s 
                                    AND fio ILIKE %s
                                    ORDER BY id DESC
                                    '''
                                    
                                    cursor.execute(query, (
                                        city, 
                                        f"%{first_variant}%", 
                                        f"%{second_variant}%"
                                    ))
                                    word_results = cursor.fetchall()
                                    if word_results:
                                        results.extend(word_results)
                                        break
                                
                                if results:
                                    break
                
                if not results:
                    msg = bot.send_message(message.chat.id, f"❌ Клиенты с ФИО '{search_term}' в городе {city} не найдены")
                    time.sleep(1)
                    bot.delete_message(msg.chat.id, msg.message_id)
                    
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    bot.send_message(message.chat.id, "Возврат в главное меню", reply_markup=keyboard)
                    return
            
            # Удаляем дубликаты по client_id
            unique_results = []
            seen_client_ids = set()
            
            for client in results:
                client_id = client[1]  # client_id находится на позиции 1
                if client_id not in seen_client_ids:
                    unique_results.append(client)
                    seen_client_ids.add(client_id)
            
            # Показываем результаты поиска
            response = f"🔍 Найдено клиентов по запросу '{search_term}' в городе {city}: {len(unique_results)}\n\n"
            keyboard = types.InlineKeyboardMarkup()
            
            for i, client in enumerate(unique_results[:10], 1):
                response += f"{i}. 📋 ID: {client[1]}\n"  # client_id
                response += f"   👤 {client[2]}\n"  # fio
                response += f"   📱 {client[3] if client[3] else 'Не указан'}\n"  # number
                response += f"   📅 ДТП: {client[5] if client[5] else 'Не указана'}\n\n"  # date_dtp
                
                btn_text = f"{i}. {client[2][:20]}..."
                btn_callback = get_contract_callback(user_id, client[1])
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
            
            if len(unique_results) > 10:
                response += f"⚠️ Показаны первые 10 из {len(unique_results)} результатов"
            
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.send_message(
                message.chat.id,
                response,
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка поиска клиентов по городу: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(message.chat.id, f"❌ Ошибка при поиске: {e}")


    @bot.callback_query_handler(func=lambda call: call.data == "btn_export_city_clients_table")
    @prevent_double_click(timeout=3.0)
    def callback_btn_export_city_clients_table(call):
        """Скачать таблицу по клиентам города"""
        user_id = call.from_user.id
        
        # Получаем город администратора
        admin_data = get_admin_from_db_by_user_id(user_id)
        if not admin_data or not admin_data.get('city_admin'):
            bot.answer_callback_query(call.id, "❌ Город не определен", show_alert=True)
            return
        
        city = admin_data['city_admin']
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"⏳ Формирование таблицы с клиентами города {city}...\n\nЭто может занять некоторое время."
        )
        
        try:
            import tempfile
            import os
            from database import export_city_clients_to_excel_table
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(mode='w+b', suffix='.xlsx', delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Экспортируем данные с фильтром по городу
            success = export_city_clients_to_excel_table(temp_path, city)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            if success and os.path.exists(temp_path):
                # Отправляем файл
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="✅ Таблица успешно сформирована и отправлена!",
                    reply_markup = None
                )
                with open(temp_path, 'rb') as file:
                    bot.send_document(
                        call.message.chat.id,
                        document=file,
                        caption=f"📊 Таблица с клиентами города {city}",
                        visible_file_name=f"Клиенты_{city}.xlsx",
                        reply_markup = keyboard
                    )
                
                # Удаляем временный файл
                os.unlink(temp_path)
                

            else:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Ошибка при формировании таблицы",
                    reply_markup = keyboard
                )
        
        except Exception as e:
            print(f"Ошибка экспорта клиентов города: {e}")
            import traceback
            traceback.print_exc()
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ Ошибка: {e}"
            )



    @bot.callback_query_handler(func=lambda call: call.data == "btn_export_city_admins")
    @prevent_double_click(timeout=3.0)
    def callback_btn_export_city_admins(call):
        """Скачать таблицу по агентам города"""
        user_id = call.from_user.id
        
        # Получаем город администратора
        admin_data = get_admin_from_db_by_user_id(user_id)
        if not admin_data or not admin_data.get('city_admin'):
            bot.answer_callback_query(call.id, "❌ Город не определен", show_alert=True)
            return
        
        city = admin_data['city_admin']
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"⏳ Формирование таблицы с агентами города {city}...\n\nЭто может занять некоторое время."
        )
        
        try:
            import tempfile
            import os
            from database import export_city_admins_to_excel
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(mode='w+b', suffix='.xlsx', delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Экспортируем данные с фильтром по городу
            success = export_city_admins_to_excel(temp_path, city)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            if success and os.path.exists(temp_path):
                # Отправляем файл
                with open(temp_path, 'rb') as file:
                    bot.send_document(
                        call.message.chat.id,
                        document=file,
                        caption=f"👨‍💼 Таблица с агентами города {city}",
                        visible_file_name=f"Агенты_{city}.xlsx"
                    )
                
                # Удаляем временный файл
                os.unlink(temp_path)
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="✅ Таблица успешно сформирована и отправлена!",
                    reply_markup = keyboard
                )
            else:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Ошибка при формировании таблицы",
                    reply_markup = keyboard
                )
        
        except Exception as e:
            print(f"Ошибка экспорта агентов города: {e}")
            import traceback
            traceback.print_exc()
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ Ошибка: {e}"
            )
        

    @bot.callback_query_handler(func=lambda call: call.data == "download_dov_not")
    @prevent_double_click(timeout=3.0)
    def callback_download_dov_not(call):
        """Загрузка нотариальной доверенности"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        client_data = user_temp_data.get(user_id)
        if not client_data or 'client_id' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
            return
        
        client_id = client_data['client_id']
        
        # Инициализируем процесс загрузки доверенности
        user_temp_data[user_id]['dov_not_process'] = {
            'client_id': client_id,
            'step': 'number',  # Текущий шаг процесса
            'data': {}
        }
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📋 Введите номер доверенности:"
        )
        
        bot.register_next_step_handler(message, process_dov_not_number, user_id, message.message_id)


    def process_dov_not_number(message, user_id, prev_msg_id):
        """Обработка номера доверенности"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not message.text:
            msg = bot.send_message(
                message.chat.id, 
                "❌ Пожалуйста, введите текстовый номер доверенности. Попробуйте еще раз:"
            )
            bot.register_next_step_handler(msg, process_dov_not_number, user_id, msg.message_id)
            return
        dov_not_number = message.text.strip()
        
        if not dov_not_number:
            msg = bot.send_message(message.chat.id, "❌ Номер не может быть пустым. Введите номер доверенности:")
            bot.register_next_step_handler(msg, process_dov_not_number, user_id, msg.message_id)
            return
        
        # Сохраняем номер
        user_temp_data[user_id]['dov_not_process']['data']['N_dov_not'] = dov_not_number
        user_temp_data[user_id]['dov_not_process']['step'] = 'date'
        
        msg = bot.send_message(
            message.chat.id,
            f"✅ Номер: {dov_not_number}\n\n"
            f"📅 Введите дату доверенности (ДД.ММ.ГГГГ):"
        )
        
        bot.register_next_step_handler(msg, process_dov_not_date, user_id, msg.message_id)


    def process_dov_not_date(message, user_id, prev_msg_id):
        """Обработка даты доверенности"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        import re
        date_text = message.text.strip()
        
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат даты. Введите в формате ДД.ММ.ГГГГ:"
            )
            bot.register_next_step_handler(msg, process_dov_not_date, user_id, msg.message_id)
            return
        
        # Сохраняем дату
        user_temp_data[user_id]['dov_not_process']['data']['data_dov_not'] = date_text
        user_temp_data[user_id]['dov_not_process']['step'] = 'fio'
        
        # Получаем город из договора клиента
        client_id = user_temp_data[user_id]['dov_not_process']['client_id']
        from database import get_client_from_db_by_client_id
        contract = get_client_from_db_by_client_id(client_id)
        
        if not contract:
            msg = bot.send_message(message.chat.id, "❌ Ошибка: договор не найден")
            return
        
        client_city = contract.get('city', '')
        
        # Получаем юристов из того же города
        db_instance = DatabaseManager()
        lawyers = []
        
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT fio, number, user_id FROM admins 
                        WHERE admin_value = 'Юрист' 
                        AND city_admin = %s 
                        ORDER BY fio
                    """, (client_city,))
                    lawyers = cursor.fetchall()
        except Exception as e:
            print(f"Ошибка получения юристов: {e}")
        
        keyboard = types.InlineKeyboardMarkup()
        
        # Всегда добавляем Рогалева
        btn_rogalev = types.InlineKeyboardButton(
            "Рогалев Семен Иннокентьевич", 
            callback_data="not_rogalev"
        )
        keyboard.add(btn_rogalev)
        
        # Добавляем юристов из города (ИСПРАВЛЕННАЯ ЧАСТЬ)
        for idx, lawyer in enumerate(lawyers):
            lawyer_fio = lawyer['fio']
            lawyer_user_id = lawyer['user_id']  # Используем user_id вместо номера
            
            # Используем только user_id для callback_data
            btn_lawyer = types.InlineKeyboardButton(
                lawyer_fio,
                callback_data=f"not_law_{lawyer_user_id}"  # Короткий callback
            )
            keyboard.add(btn_lawyer)
        
        # Кнопка "Другое"
        btn_other = types.InlineKeyboardButton("Другое", callback_data="not_other")
        keyboard.add(btn_other)
        
        msg = bot.send_message(
            message.chat.id,
            f"✅ Дата: {date_text}\n\n"
            f"👤 Выберите ФИО представителя:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("not_law_"))
    @prevent_double_click(timeout=3.0)
    def callback_notarius_lawyer(call):
        """Обработка выбора юриста из списка"""
        user_id = call.from_user.id
        
        # Получаем user_id юриста из callback_data
        lawyer_user_id = call.data.replace("not_law_", "")
        
        # Находим данные юриста в базе данных
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT fio, number FROM admins 
                        WHERE user_id = %s
                    """, (lawyer_user_id,))
                    lawyer = cursor.fetchone()
                    
            if not lawyer:
                bot.answer_callback_query(call.id, "❌ Юрист не найден", show_alert=True)
                return
                
            lawyer_fio = lawyer['fio']
            lawyer_number = lawyer['number']
            
        except Exception as e:
            print(f"Ошибка получения данных юриста: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка обработки данных", show_alert=True)
            return
        
        # Сохраняем данные юриста
        user_temp_data[user_id]['dov_not_process']['data']['fio_not'] = lawyer_fio
        user_temp_data[user_id]['dov_not_process']['data']['number_not'] = lawyer_number
        user_temp_data[user_id]['dov_not_process']['step'] = 'file'
        
        # Инициализируем хранилище для фото доверенности
        user_temp_data[user_id]['doverennost_photos'] = []
        
        # Показываем итоговые данные и просим загрузить файлы
        dov_data = user_temp_data[user_id]['dov_not_process']['data']
        
        summary = f"✅ <b>Данные доверенности:</b>\n\n"
        summary += f"📋 Номер: {dov_data.get('N_dov_not', '')}\n"
        summary += f"📅 Дата: {dov_data.get('data_dov_not', '')}\n"
        summary += f"👤 ФИО представителя: {lawyer_fio}\n"
        summary += f"📱 Телефон: {lawyer_number}\n\n"
        summary += f"📄 Теперь отправьте фотографии всех страниц доверенности\n\n"
        summary += f"Можно отправлять по одной или несколько сразу."
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_doverennost_photos_client_{user_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=summary, 
            parse_mode='HTML',
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["not_rogalev","not_other"])
    @prevent_double_click(timeout=3.0)
    def callback_notarius(call):
        user_id = call.from_user.id
        if call.data == "not_rogalev":
            user_temp_data[user_id]['dov_not_process']['data']['fio_not'] = "Рогалев Семен Иннокентьевич"
            user_temp_data[user_id]['dov_not_process']['data']['number_not'] = "+79966368941"
            user_temp_data[user_id]['dov_not_process']['step'] = 'file'
            
            # Инициализируем хранилище для фото доверенности
            user_temp_data[user_id]['doverennost_photos'] = []
            
            # Показываем итоговые данные и просим загрузить файлы
            dov_data = user_temp_data[user_id]['dov_not_process']['data']
            
            summary = f"✅ <b>Данные доверенности:</b>\n\n"
            summary += f"📋 Номер: {dov_data.get('N_dov_not', '')}\n"
            summary += f"📅 Дата: {dov_data.get('data_dov_not', '')}\n"
            summary += f"👤 ФИО представителя: {dov_data.get('fio_not', '')}\n"
            summary += f"📱 Телефон: +79966368941\n\n"
            summary += f"📄 Теперь отправьте фотографии всех страниц доверенности\n\n"
            summary += f"Можно отправлять по одной или несколько сразу."
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_doverennost_photos_client_{user_id}"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=summary, 
                parse_mode='HTML',
                reply_markup=keyboard
            )
            
        else:
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="👤 Введите ФИО представителя (Иванов Иван Иванович)"
            )
            bot.register_next_step_handler(msg, process_dov_not_fio, user_id, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["number_rogalev","number_not_other"])
    @prevent_double_click(timeout=3.0)
    def callback_notarius_number(call):
        user_id = call.from_user.id
        if call.data == "number_rogalev":
            user_temp_data[user_id]['dov_not_process']['data']['number_not'] = "+79966368941"
            user_temp_data[user_id]['dov_not_process']['step'] = 'file'
            
            # Инициализируем хранилище для фото доверенности
            user_temp_data[user_id]['doverennost_photos'] = []
            
            # Показываем итоговые данные и просим загрузить файлы
            dov_data = user_temp_data[user_id]['dov_not_process']['data']
            
            summary = f"✅ <b>Данные доверенности:</b>\n\n"
            summary += f"📋 Номер: {dov_data.get('N_dov_not', '')}\n"
            summary += f"📅 Дата: {dov_data.get('data_dov_not', '')}\n"
            summary += f"👤 ФИО представителя: {dov_data.get('fio_not', '')}\n"
            summary += f"📱 Телефон: +79966368941\n\n"
            summary += f"📄 Теперь отправьте фотографии всех страниц доверенности\n\n"
            summary += f"Можно отправлять по одной или несколько сразу."
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_doverennost_photos_{user_id}"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=summary, 
                parse_mode='HTML',
                reply_markup=keyboard
            )
        else:
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📱 Введите номер телефона представителя (+79ХХХХХХХХХ)"
            )
            
            bot.register_next_step_handler(msg, process_dov_not_phone, user_id, msg.message_id)
    def process_dov_not_fio(message, user_id, prev_msg_id):
        """Обработка ФИО представителя"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        fio = message.text.strip()
        
        # Проверка формата ФИО
        if len(fio.split()) < 2:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат ввода!\nВведите ФИО в формате: Иванов Иван Иванович"
            )
            bot.register_next_step_handler(msg, process_dov_not_fio, user_id, msg.message_id)
            return
        
        words = fio.split()
        for word in words:
            if not word[0].isupper():
                msg = bot.send_message(
                    message.chat.id,
                    "❌ Каждое слово должно начинаться с заглавной буквы!\n"
                    "Введите ФИО в формате: Иванов Иван Иванович"
                )
                bot.register_next_step_handler(msg, process_dov_not_fio, user_id, msg.message_id)
                return
        
        # Сохраняем ФИО
        user_temp_data[user_id]['dov_not_process']['data']['fio_not'] = fio
        user_temp_data[user_id]['dov_not_process']['step'] = 'phone'
        
        msg = bot.send_message(
            message.chat.id,
            f"✅ ФИО: {fio}\n\n"
            f"📱 Введите номер телефона представителя (например, +79001234567):"
        )
        
        bot.register_next_step_handler(msg, process_dov_not_phone, user_id, msg.message_id)


    def process_dov_not_phone(message, user_id, prev_msg_id):
        """Обработка телефона представителя"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        import re
        phone = message.text.strip()
        
        # Проверка формата телефона
        clean_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not re.match(r'^\+?[78]?\d{10,11}$', clean_phone):
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат номера телефона. Введите снова (например, +79001234567):"
            )
            bot.register_next_step_handler(msg, process_dov_not_phone, user_id, msg.message_id)
            return
        
        # Сохраняем телефон
        user_temp_data[user_id]['dov_not_process']['data']['number_not'] = phone
        user_temp_data[user_id]['dov_not_process']['step'] = 'file'
        
        # Инициализируем хранилище для фото доверенности
        user_temp_data[user_id]['doverennost_photos'] = []
        
        # Показываем итоговые данные
        dov_data = user_temp_data[user_id]['dov_not_process']['data']
        
        summary = f"✅ <b>Данные доверенности:</b>\n\n"
        summary += f"📋 Номер: {dov_data.get('N_dov_not', '')}\n"
        summary += f"📅 Дата: {dov_data.get('data_dov_not', '')}\n"
        summary += f"👤 ФИО представителя: {dov_data.get('fio_not', '')}\n"
        summary += f"📱 Телефон: {phone}\n\n"
        summary += f"📄 Теперь отправьте фотографии всех страниц доверенности\n\n"
        summary += f"Можно отправлять по одной или несколько сразу."
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_doverennost_photos_{user_id}"))
        
        bot.send_message(message.chat.id, summary, parse_mode='HTML', reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_doverennost_photos_'))
    @prevent_double_click(timeout=3.0)
    def finish_doverennost_photos_callback(call):
        """Завершение загрузки доверенности"""
        user_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if user_id not in user_temp_data or 'doverennost_photos' not in user_temp_data[user_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[user_id]['doverennost_photos']
            
            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_doverennost_photos_{user_id}"))
                
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Отправьте фото доверенности:",
                    reply_markup=keyboard
                )
                return
            
            process_data = user_temp_data[user_id]['dov_not_process']
            client_id = process_data['client_id']
            dov_data = process_data['data']
            
            client_dir = f"clients/{client_id}/Документы"
            import os
            if not os.path.exists(client_dir):
                os.makedirs(client_dir)
            
            # Создаем PDF из всех фото
            pdf_path = os.path.join(client_dir, "Доверенность.pdf")
            from PIL import Image
            from io import BytesIO
            
            images = []
            for img_bytes in photos:
                img = Image.open(BytesIO(img_bytes))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                max_size = (1920, 1920)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                images.append(img)
            
            if len(images) == 1:
                images[0].save(pdf_path, "PDF", resolution=100.0)
            else:
                images[0].save(
                    pdf_path,
                    "PDF",
                    resolution=100.0,
                    save_all=True,
                    append_images=images[1:]
                )
            
            # Сохраняем все данные в БД (существующий код)
            from database import DatabaseManager
            import json
            from datetime import datetime
            
            db = DatabaseManager()
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT data_json FROM clients WHERE client_id = %s", (client_id,))
                    result = cursor.fetchone()
                    
                    try:
                        current_data = json.loads(result[0]) if result[0] else {}
                    except:
                        current_data = {}
                    
                    current_data.update(dov_data)
                    current_data['doverennost_provided'] = 'Yes'
                    current_data['doverennost_provided_date'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                    current_data['doverennost_pending'] = 'Yes'
                    
                    cursor.execute("""
                        UPDATE clients 
                        SET data_json = %s,
                            "N_dov_not" = %s,
                            "data_dov_not" = %s,
                            fio_not = %s,
                            number_not = %s
                        WHERE client_id = %s
                    """, (
                        json.dumps(current_data, ensure_ascii=False),
                        dov_data.get('N_dov_not'),
                        dov_data.get('data_dov_not'),
                        dov_data.get('fio_not'),
                        dov_data.get('number_not'),
                        client_id
                    ))
                    conn.commit()
            
            from database import get_client_from_db_by_client_id
            contract = get_client_from_db_by_client_id(client_id)
            
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO pending_approvals (client_id, user_id, document_type, document_url, fio)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (client_id, contract['user_id'], 'doverennost', pdf_path, contract['fio']))
                    conn.commit()
            data_admin = get_admin_from_db_by_user_id(user_id)
            if data_admin['admin_value'] != 'Администратор':
                # Уведомить всех директоров
                notify_directors_about_document(bot, client_id, contract['fio'], 'Доверенность')
            
            # Очищаем временные данные
            del user_temp_data[user_id]['dov_not_process']
            del user_temp_data[user_id]['doverennost_photos']
            if 'dov_timer' in user_temp_data[user_id]:
                user_temp_data[user_id]['dov_timer'].cancel()
                del user_temp_data[user_id]['dov_timer']
            
            keyboard = types.InlineKeyboardMarkup()
            callback_data = get_contract_callback(user_id, client_id)
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))
            
            bot.send_message(
                call.message.chat.id,
                "✅ Нотариальная доверенность загружена!\n\n"
                "📋 Данные сохранены:\n"
                f"   Номер: {dov_data.get('N_dov_not')}\n"
                f"   Дата: {dov_data.get('data_dov_not')}\n"
                f"   ФИО представителя: {dov_data.get('fio_not')}\n"
                f"   Телефон: {dov_data.get('number_not')}\n"
                f"   Страниц: {len(photos)}\n\n"
                "⏳ Ожидает проверки администратором",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка при сохранении доверенности: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(call.message.chat.id, f"❌ Ошибка: {e}")
    
    
    @bot.callback_query_handler(func=lambda call: call.data == "download_foto")
    def callback_download_foto(call):
        user_id = call.from_user.id
        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        client_data = user_temp_data.get(user_id)
        if not client_data or 'client_id' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
            return
        
        client_id = client_data['client_id']
        client_dir = f"clients/{client_id}/Документы"
        
        import os
        if not os.path.exists(client_dir):
            os.makedirs(client_dir)
        
        # Инициализируем хранилище для фото ДТП
        user_temp_data[user_id]['dtp_photos_cabinet'] = []
        user_temp_data[user_id]['cabinet_client_id'] = client_id
        user_temp_data[user_id]['cabinet_client_dir'] = client_dir
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_cabinet_{user_id}"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📸 Отправьте фотографии с места ДТП\n\n"
                "Можно отправлять по одной фотографии или несколько сразу.\n"
                "Когда загрузите все фото, нажмите кнопку ниже:",
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "download_docs")
    def callback_download_docs_client(call):
        """Загрузка документов"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        client_data = user_temp_data.get(user_id)
        if not client_data or 'client_id' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
            return
        
        client_id = client_data['client_id']
        client_dir = f"clients/{client_id}/Документы"
        
        import os
        if not os.path.exists(client_dir):
            os.makedirs(client_dir)
        
        user_temp_data[user_id]['docs_upload'] = {
            'active': True,
            'client_dir': client_dir,
            'client_id': client_id,
            'uploaded_count': 0,
            'uploaded_files': []
        }
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_docs_upload"))
        keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_docs_upload"))
        
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📁 Отправьте документы.\n\nМожно отправить несколько документов/фото по одному.\nКогда закончите, нажмите 'Завершить загрузку'",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(message, handle_docs_upload, user_id, message.message_id, user_temp_data)
    
    @bot.callback_query_handler(func=lambda call: call.data == "view_docs")
    @prevent_double_click(timeout=3.0)
    def callback_view_docs_choice(call):
        """Выбор: документы или фото"""
        keyboard = types.InlineKeyboardMarkup()
        btn_docs = types.InlineKeyboardButton("📄 Документы", callback_data="view_client_documents")
        btn_foto = types.InlineKeyboardButton("📸 Фото ДТП", callback_data="view_client_foto")
        
        user_id = call.from_user.id
        client_data = user_temp_data.get(user_id)
        if client_data and 'client_id' in client_data:
            callback_data = get_contract_callback(user_id, client_data['client_id'])
            btn_back = types.InlineKeyboardButton("◀️ Назад", callback_data=callback_data)
        else:
            btn_back = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
        
        keyboard.add(btn_docs)
        keyboard.add(btn_foto)
        keyboard.add(btn_back)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Что вы хотите посмотреть?",
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "view_client_foto")
    @prevent_double_click(timeout=3.0)
    def callback_view_client_foto(call):
        """Показать все фото ДТП"""
        import os
        import time
        
        user_id = call.from_user.id
        client_data = user_temp_data.get(user_id)
        
        if not client_data or 'client_id' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
            return
        
        client_id = client_data['client_id']
        foto_dir = f"clients/{client_id}/Фото"
        
        if not os.path.exists(foto_dir):
            bot.answer_callback_query(call.id, "📸 Фотографии не найдены", show_alert=True)
            return
        
        files = [f for f in os.listdir(foto_dir) if os.path.isfile(os.path.join(foto_dir, f))]
        
        if not files:
            bot.answer_callback_query(call.id, "📸 Фотографии не найдены", show_alert=True)
            return
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📸 Отправка {len(files)} фотографий..."
        )
        
        for filename in files:
            try:
                file_path = os.path.join(foto_dir, filename)
                with open(file_path, 'rb') as photo:
                    bot.send_photo(call.message.chat.id, photo, caption=filename)
                time.sleep(0.3)
            except Exception as e:
                print(f"Ошибка отправки фото {filename}: {e}")
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        bot.send_message(call.message.chat.id, "✅ Все фотографии отправлены", reply_markup=keyboard)
    
    @bot.callback_query_handler(func=lambda call: call.data == "view_client_documents")
    @prevent_double_click(timeout=3.0)
    def callback_view_client_documents(call):
        """Показать список документов с кнопками"""
        import os
        
        user_id = call.from_user.id
        client_data = user_temp_data.get(user_id)
        
        if not client_data or 'client_id' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
            return
        
        client_id = client_data['client_id']
        docs_dir = f"clients/{client_id}/Документы"
        
        if not os.path.exists(docs_dir):
            bot.answer_callback_query(call.id, "📄 Документы не найдены", show_alert=True)
            return
        
        files = [f for f in os.listdir(docs_dir) if os.path.isfile(os.path.join(docs_dir, f))]

# Получаем роль пользователя
        from database import get_admin_from_db_by_user_id
        admin_data = get_admin_from_db_by_user_id(user_id)
        user_role = admin_data.get('admin_value', '') if admin_data else ''

        # Фильтруем файлы по ролям
        allowed_roles_for_cover = ['Клиент', 'Агент']
        if user_role in allowed_roles_for_cover:
            files = [f for f in files if f != "Обложка дела.docx"]
        
        if not files:
            bot.answer_callback_query(call.id, "📄 Документы не найдены", show_alert=True)
            return
        
        # Сортируем по времени изменения
        files_with_time = [(f, os.path.getmtime(os.path.join(docs_dir, f))) for f in files]
        files_with_time.sort(key=lambda x: x[1], reverse=True)
        sorted_files = [f[0] for f in files_with_time]
        
        message_text = f"📄 Документы ({len(sorted_files)}):\n\n"
        for i, filename in enumerate(sorted_files, 1):
            message_text += f"{i}. {filename}\n"
        
        message_text += "\nВыберите номер документа:"
        
        keyboard = types.InlineKeyboardMarkup()
        buttons_per_row = 5
        
        for i in range(0, len(sorted_files), buttons_per_row):
            row_buttons = []
            for j in range(i, min(i + buttons_per_row, len(sorted_files))):
                row_buttons.append(types.InlineKeyboardButton(str(j + 1), callback_data=f"send_client_doc_{j}"))
            keyboard.row(*row_buttons)
        
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        
        user_temp_data[user_id]['client_files_list'] = sorted_files
        user_temp_data[user_id]['client_docs_dir'] = docs_dir
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("send_client_doc_"))
    @prevent_double_click(timeout=3.0)
    def callback_send_client_doc(call):
        """Отправка выбранного документа"""
        user_id = call.from_user.id
        file_index = int(call.data.replace("send_client_doc_", ""))
        
        if (user_id not in user_temp_data or 
            'client_files_list' not in user_temp_data[user_id]):
            bot.answer_callback_query(call.id, "Ошибка: список файлов не найден")
            return
        
        files_list = user_temp_data[user_id]['client_files_list']
        docs_dir = user_temp_data[user_id]['client_docs_dir']
        
        if file_index >= len(files_list):
            bot.answer_callback_query(call.id, "Файл не найден")
            return
        
        filename = files_list[file_index]
        import os
        file_path = os.path.join(docs_dir, filename)
        
        try:
            with open(file_path, 'rb') as file:
                bot.send_document(call.message.chat.id, file, caption=f"📄 {filename}")
            bot.answer_callback_query(call.id, f"✅ Отправлен: {filename}")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('finish_dtp_photos_cabinet_'))
    @prevent_double_click(timeout=3.0)
    def finish_dtp_photos_cabinet_callback(call):
        """Завершение загрузки фото ДТП из личного кабинета"""
        user_id = int(call.data.split('_')[-1])
        
        try:
            bot.answer_callback_query(call.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
            if user_id not in user_temp_data or 'dtp_photos_cabinet' not in user_temp_data[user_id]:
                bot.send_message(call.message.chat.id, "❌ Ошибка: фотографии не найдены.")
                return
            
            photos = user_temp_data[user_id]['dtp_photos_cabinet']
            client_id = user_temp_data[user_id]['cabinet_client_id']
            client_dir = user_temp_data[user_id]['cabinet_client_dir']
            
            if len(photos) == 0:
                keyboard = types.InlineKeyboardMarkup()
                btn_finish = types.InlineKeyboardButton("✅ Завершить загрузку", callback_data=f"finish_dtp_photos_cabinet_{user_id}")
                keyboard.add(btn_finish)
                
                bot.send_message(
                    call.message.chat.id,
                    "❌ Необходимо загрузить хотя бы одно фото!\n\n📸 Отправьте фото с места ДТП:",
                    reply_markup=keyboard
                )
                return
            
            import os
            from PIL import Image
            import glob
            
            # Сохраняем фото как отдельные файлы
            temp_photo_paths = []
            for idx, photo_bytes in enumerate(photos, 1):
                file_path = os.path.join(client_dir, f"foto_dtp_temp_{idx}.jpg")
                with open(file_path, 'wb') as f:
                    f.write(photo_bytes)
                temp_photo_paths.append(file_path)
            
            # Путь к PDF файлу
            pdf_path = os.path.join(client_dir, "Фото_ДТП.pdf")
            
            if os.path.exists(pdf_path):
                # Если PDF существует - добавляем фото в конец
                add_photos_to_existing_pdf(pdf_path, temp_photo_paths)
                action_text = "добавлены в существующий PDF файл"
            else:
                # Если PDF не существует - создаем новый
                create_pdf_from_photos(temp_photo_paths, pdf_path)
                action_text = "сохранены в новый PDF файл"
            
            # Очищаем временные файлы
            for temp_path in temp_photo_paths:
                try:
                    os.remove(temp_path)
                except:
                    pass
            
            # Очищаем временные данные
            del user_temp_data[user_id]['dtp_photos_cabinet']
            if 'dtp_cabinet_timer' in user_temp_data[user_id]:
                user_temp_data[user_id]['dtp_cabinet_timer'].cancel()
                del user_temp_data[user_id]['dtp_cabinet_timer']
            
            keyboard = types.InlineKeyboardMarkup()
            callback_data = get_contract_callback(user_id, client_id)
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))
            
            bot.send_message(
                call.message.chat.id,
                f"✅ Фото ДТП успешно {action_text}! (Загружено: {len(photos)})",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка при сохранении фото ДТП: {e}")
            bot.send_message(call.message.chat.id, "❌ Произошла ошибка при сохранении фото.")

    def add_photos_to_existing_pdf(pdf_path, new_photo_paths):
        """Добавляет новые фото в конец существующего PDF файла"""
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        import io
        from PIL import Image
        
        # Создаем временный PDF с новыми фото
        temp_pdf_path = pdf_path + ".temp"
        
        # Создаем новый PDF с фото
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=A4)
        
        for photo_path in new_photo_paths:
            try:
                # Открываем и обрабатываем изображение
                img = Image.open(photo_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Получаем размеры изображения и страницы
                img_width, img_height = img.size
                page_width, page_height = A4
                
                # Масштабируем изображение чтобы поместиться на странице
                scale = min(page_width * 0.9 / img_width, page_height * 0.9 / img_height)
                new_width = img_width * scale
                new_height = img_height * scale
                
                # Центрируем изображение на странице
                x = (page_width - new_width) / 2
                y = (page_height - new_height) / 2
                
                # Добавляем изображение на страницу
                can.drawImage(ImageReader(img), x, y, new_width, new_height)
                can.showPage()
                
            except Exception as e:
                print(f"Ошибка при обработке фото {photo_path}: {e}")
                continue
        
        can.save()
        
        # Перемещаемся в начало потока
        packet.seek(0)
        new_pdf = PdfReader(packet)
        
        # Читаем существующий PDF
        existing_pdf = PdfReader(pdf_path)
        pdf_writer = PdfWriter()
        
        # Добавляем все страницы из существующего PDF
        for page in existing_pdf.pages:
            pdf_writer.add_page(page)
        
        # Добавляем все страницы из нового PDF
        for page in new_pdf.pages:
            pdf_writer.add_page(page)
        
        # Сохраняем объединенный PDF
        with open(temp_pdf_path, 'wb') as output_file:
            pdf_writer.write(output_file)
        
        # Заменяем старый файл новым
        os.replace(temp_pdf_path, pdf_path)

    def create_pdf_from_photos(photo_paths, pdf_path):
        """Создает новый PDF файл из фото"""
        from PIL import Image
        
        images = []
        for photo_path in photo_paths:
            try:
                img = Image.open(photo_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                images.append(img)
            except Exception as e:
                print(f"Ошибка при открытии фото {photo_path}: {e}")
                continue
        
        if images:
            # Сохраняем как PDF
            images[0].save(
                pdf_path, 
                "PDF", 
                resolution=100.0, 
                save_all=True, 
                append_images=images[1:]
            )
    
    @bot.callback_query_handler(func=lambda call: call.data == "cancel_foto_upload")
    @prevent_double_click(timeout=3.0)
    def callback_cancel_foto_upload(call):
        """Отмена загрузки фото"""
        user_id = call.from_user.id
        
        if user_id in user_temp_data and 'foto_upload' in user_temp_data[user_id]:
            client_id = user_temp_data[user_id]['foto_upload']['client_id']
            del user_temp_data[user_id]['foto_upload']
        else:
            client_id = user_temp_data[user_id].get('client_id', '')
        
        keyboard = types.InlineKeyboardMarkup()
        if client_id:
            callback_data = get_contract_callback(user_id, client_id)
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))
        else:
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Загрузка фотографий отменена",
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "finish_docs_upload")
    @prevent_double_click(timeout=3.0)
    def callback_finish_docs_upload(call):
        """Завершение загрузки документов"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data or 'docs_upload' not in user_temp_data[user_id]:
            bot.answer_callback_query(call.id, "Сессия загрузки не найдена")
            return
        
        upload_data = user_temp_data[user_id]['docs_upload']
        uploaded_count = upload_data.get('uploaded_count', 0)
        client_id = upload_data['client_id']
        
        del user_temp_data[user_id]['docs_upload']
        
        keyboard = types.InlineKeyboardMarkup()
        callback_data = get_contract_callback(user_id, client_id)
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Загрузка завершена!\n\nЗагружено документов: {uploaded_count}",
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "cancel_docs_upload")
    @prevent_double_click(timeout=3.0)
    def callback_cancel_docs_upload(call):
        """Отмена загрузки документов"""
        user_id = call.from_user.id
        
        if user_id in user_temp_data and 'docs_upload' in user_temp_data[user_id]:
            client_id = user_temp_data[user_id]['docs_upload']['client_id']
            del user_temp_data[user_id]['docs_upload']
        else:
            client_id = user_temp_data[user_id].get('client_id', '')
        
        keyboard = types.InlineKeyboardMarkup()
        if client_id:
            callback_data = get_contract_callback(user_id, client_id)
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))
        else:
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Загрузка документов отменена",
            reply_markup=keyboard
        )


    def handle_docs_upload(message, user_id, user_message_id, user_temp_data):
        """Обработка загрузки документов"""
        import os
        
        if user_id not in user_temp_data or 'docs_upload' not in user_temp_data[user_id]:
            return
        
        upload_data = user_temp_data[user_id]['docs_upload']
        client_dir = upload_data['client_dir']
        
        uploaded_file = None
        filename = None
        
        if message.document:
            uploaded_file = message.document
            filename = uploaded_file.file_name or f"{uploaded_file.file_id}.pdf"
        elif message.photo:
            uploaded_file = message.photo[-1]
            filename = f"{uploaded_file.file_id}.jpg"
        else:
            if message.text in ["✅ Завершить загрузку", "❌ Отмена"]:
                return
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            msg = bot.send_message(message.chat.id, "❌ Отправьте документ или фото")
            bot.register_next_step_handler(msg, handle_docs_upload, user_id, user_message_id, user_temp_data)
            return
        
        try:
            file_info = bot.get_file(uploaded_file.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Проверяем уникальность имени
            original_filename = filename
            counter = 1
            while os.path.exists(os.path.join(client_dir, filename)):
                name, ext = os.path.splitext(original_filename)
                filename = f"{name}_{counter}{ext}"
                counter += 1
            
            file_path = os.path.join(client_dir, filename)
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            upload_data['uploaded_count'] += 1
            upload_data['uploaded_files'].append(filename)
            
            try:
                bot.delete_message(message.chat.id, user_message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_docs_upload"))
            keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_docs_upload"))
            
            new_msg = bot.send_message(
                message.chat.id,
                f"✅ Документ загружен!\n\nВсего загружено: {upload_data['uploaded_count']}\n\nМожете отправить еще или завершить загрузку",
                reply_markup=keyboard
            )
            
            bot.register_next_step_handler(new_msg, handle_docs_upload, user_id, new_msg.message_id, user_temp_data)
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
            bot.register_next_step_handler(message, handle_docs_upload, user_id, user_message_id, user_temp_data)
    

 
    @bot.callback_query_handler(func=lambda call: call.data == "load_payment")
    @prevent_double_click(timeout=3.0)
    def callback_load_payment(call):
        """Кнопка 'Оплатить Юр.услуги'"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data or 'client_id' not in user_temp_data[user_id]:
            bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
            return
        
        client_id = user_temp_data[user_id]['client_id']
        
        # Показываем реквизиты
        requisites_text = (
            "💳 <b>Реквизиты для оплаты:</b>\n\n"
            "Здесь будут реквизиты\n\n"
            "После оплаты нажмите кнопку 'Оплатил'"
        )
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Оплатил", callback_data="payment_confirm"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=get_contract_callback(user_id, client_id)))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=requisites_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "payment_confirm")
    @prevent_double_click(timeout=3.0)
    def payment_confirm_handler(call):
        """Обработчик кнопки 'Оплатил' - создание записи на проверку"""
        user_id = call.from_user.id
        
        if user_id not in user_temp_data or 'client_id' not in user_temp_data[user_id]:
            bot.answer_callback_query(call.id, "Ошибка: данные не найдены")
            return
        
        client_id = user_temp_data[user_id]['client_id']
        
        # Добавляем запись в pending_approvals без чека (его загрузит директор)
        from database import DatabaseManager, get_client_from_db_by_client_id
        db_instance = DatabaseManager()
        contract = get_client_from_db_by_client_id(client_id)
        
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO pending_approvals (client_id, user_id, document_type, document_url, fio)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (client_id, contract['user_id'], 'payment', '', contract['fio']))
                    cursor.execute("""
                        UPDATE clients 
                        SET data_json = jsonb_set(
                            COALESCE(data_json::jsonb, '{}'::jsonb),
                            '{payment_pending}',
                            '"Yes"'
                        )
                        WHERE client_id = %s
                    """, (client_id,))
                    conn.commit()
            data_admin = get_admin_from_db_by_user_id(user_id)
            if data_admin['admin_value'] != 'Администратор':
                # Уведомить всех директоров
                notify_directors_about_document(bot, client_id, contract['fio'], 'Оплата')
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=get_contract_callback(call.message.chat.id, client_id)))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="⏳ Оплата ожидает проверки",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка создания записи оплаты: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)
    
    @bot.callback_query_handler(func=lambda call: call.data == "btn_search_my_clients")
    @prevent_double_click(timeout=3.0)
    def callback_search_my_clients(call):
        """Поиск своих клиентов по ФИО для агента"""
        agent_id = call.from_user.id
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔍 Введите фамилию и имя клиента для поиска:",
            reply_markup=None
        )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, search_agent_clients_handler, user_message_id, agent_id, user_temp_data)

    def search_agent_clients_handler(message, user_message_id, agent_id, user_temp_data):
        """Обработчик поиска своих клиентов агентом по ФИО"""
        import time
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        search_term = message.text.strip()
        
        if len(search_term) < 2:
            msg = bot.send_message(message.chat.id, "❌ Введите минимум 2 символа для поиска")
            bot.register_next_step_handler(msg, search_agent_clients_handler, msg.message_id, agent_id, user_temp_data)
            return
        
        try:
            from database import search_my_clients_by_fio_in_db
            
            search_msg = bot.send_message(message.chat.id, "🔍 Поиск в базе данных...")
            results = search_my_clients_by_fio_in_db(search_term, agent_id)
            
            try:
                bot.delete_message(message.chat.id, search_msg.message_id)
            except:
                pass
            
            if not results:
                msg = bot.send_message(message.chat.id, f"❌ Клиенты с ФИО '{search_term}' не найдены")
                time.sleep(1)
                bot.delete_message(msg.chat.id, msg.message_id)
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                bot.send_message(message.chat.id, "Возврат в главное меню", reply_markup=keyboard)
                return
            
            # Показываем результаты поиска
            response = f"🔍 Найдено клиентов по запросу '{search_term}': {len(results)}\n\n"
            keyboard = types.InlineKeyboardMarkup()
            
            for i, client in enumerate(results[:10], 1):
                response += f"{i}. 📋 ID: {client['client_id']}\n"
                response += f"   👤 {client['fio']}\n"
                response += f"   📱 {client.get('number', 'Не указан')}\n"
                response += f"   📅 ДТП: {client.get('date_dtp', 'Не указана')}\n\n"
                
                btn_text = f"{i}. {client['fio'][:20]}..."
                btn_callback = get_contract_callback(user_id, client['client_id'])
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
            
            if len(results) > 10:
                response += f"... и еще {len(results) - 10} клиентов"
            
            keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_my_clients"))
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.send_message(message.chat.id, response, reply_markup=keyboard)
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка поиска: {e}")
            print(f"Ошибка поиска: {e}")
    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_view_contract_"))
    @prevent_double_click(timeout=3.0)
    def agent_view_contract_handler(call):
        """Просмотр договора агентом своего клиента"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=5)
        agent_id = call.from_user.id
        client_id = call.data.replace("agent_view_contract_", "")
        
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
        if agent_id not in user_temp_data:
            user_temp_data[agent_id] = {}
        user_temp_data[agent_id].update(contract)
        user_temp_data[agent_id]['client_id'] = client_id
        
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
        
        # Кнопки для загрузки
        keyboard.add(types.InlineKeyboardButton("📸 Загрузить фото ДТП", callback_data="download_foto"))
        keyboard.add(types.InlineKeyboardButton("📤 Загрузить документы", callback_data="download_docs"))
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
                    keyboard.add(types.InlineKeyboardButton("❓ Ответ от страховой", callback_data=f"agent_net_osago_continue_documents_{client_id}"))
        elif contract_data.get('accident', '') == "Нет ОСАГО" and contract_data.get('status', '') == "Оформлен договор":
            keyboard.add(types.InlineKeyboardButton("👮 Заполнить запрос в ГИБДД", callback_data=f"NoOsago_yes_{contract_data['client_id']}"))
        elif contract_data.get('accident', '') == "Подал заявление":
            if contract_data.get('status', '') == "Оформлен договор":
                keyboard.add(types.InlineKeyboardButton("📋 Заявление в страховую", callback_data=f"agent_podal_continue_documents_{client_id}"))

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
    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_contract_data_"))
    @prevent_double_click(timeout=3.0)
    def callback_edit_contract_data(call):
        try:
            user_id = call.from_user.id
            client_id = call.data.replace("edit_contract_data_", "")
            
            # Получаем данные клиента
            from database import get_client_from_db_by_client_id
            full_client_data = get_client_from_db_by_client_id(client_id)
            admin_data = get_admin_from_db_by_user_id(user_id)
            if not full_client_data:
                bot.answer_callback_query(call.id, "Клиент не найден в базе данных")
                return
            
            fio = full_client_data.get('fio', '')
            
            try:
                if full_client_data.get('data_json'):
                    json_data = json.loads(full_client_data['data_json'])
                    merged_data = {**full_client_data, **json_data}
                else:
                    merged_data = full_client_data
            except (json.JSONDecodeError, TypeError):
                merged_data = full_client_data
            
            if 'data_json' in merged_data:
                del merged_data['data_json']
            if 'id' in merged_data:
                del merged_data['id']
            
            fio_file_path = os.path.join(f"clients/{client_id}", f"{fio}_data.txt")
            
            if not os.path.exists(fio_file_path):
                try:
                    from word_utils import create_fio_data_file
                    create_fio_data_file(merged_data)
                except Exception as e:
                    bot.answer_callback_query(call.id, f"Ошибка создания файла данных: {e}")
                    return
            
            try:
                with open(fio_file_path, 'r', encoding='utf-8') as file:
                    file_content = file.read()
            except Exception as e:
                bot.answer_callback_query(call.id, f"Ошибка чтения файла: {e}")
                return
            
            message_text = f"Текущие данные клиента {fio}:\n\n{file_content}\n\nВведите название параметра точно как в файле data.txt (например: 'Паспорт серия клиента'):"
            
            if user_id not in user_temp_data:
                user_temp_data[user_id] = {}
            user_temp_data[user_id]['editing_client'] = {
                'client_id': client_id,
                'fio': fio,
                'file_path': fio_file_path,
                'step': 'parameter',
                'client_data': merged_data
            }
            if admin_data and admin_data.get('admin_value') in ['Директор', 'Технический директор', 'Руководитель офиса', 'Юрист', 'Эксперт']:
                callback_data = f"admin_view_contract_{client_id}"
            elif admin_data and admin_data.get('admin_value') in ['Клиент']:
                callback_data = f"view_contract_{client_id}"
            else:
                callback_data = get_contract_callback(user_id, client_id)
            
            # Создаем клавиатуру для возврата
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))

            new_message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=message_text,
                reply_markup = keyboard
            )
            user_message_id = call.message.message_id
            bot.register_next_step_handler(new_message, handle_parameter_input_contract, user_id, user_message_id)
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}")
            print(f"Ошибка в callback_edit_contract_data: {e}")

    def handle_parameter_input_contract(message, user_id, user_message_id):
        """Обработка ввода названия параметра для редактирования договора"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if user_id not in user_temp_data or 'editing_client' not in user_temp_data[user_id]:
            print("DEBUG: Данные редактирования не найдены")
            bot.send_message(message.chat.id, "Ошибка: данные редактирования не найдены")
            return_to_main_menu_contract(message, user_id)
            return
        
        parameter_name = message.text.strip()
        
        # Загружаем маппинг полей
        from word_utils import load_field_mapping_from_data_file
        field_mapping = load_field_mapping_from_data_file()
        
        db_field = None
        parameter_lower = parameter_name.lower()
        
        if parameter_lower in field_mapping:
            db_field = field_mapping[parameter_lower]
        else:
            for rus_name, field_name in field_mapping.items():
                if parameter_lower == rus_name:
                    db_field = field_name
                    break
        
        if not db_field:
            msg = bot.send_message(
                message.chat.id,
                f"Параметр '{parameter_name}' не найден в базе."
            )
            time.sleep(1.5)
            bot.delete_message(message.chat.id, msg.message_id)
            
            # Возвращаем к просмотру договора
            from database import get_admin_from_db_by_user_id
            admin_data = get_admin_from_db_by_user_id(user_id)
            if admin_data and admin_data.get('admin_value') in ['Директор', 'Технический директор', 'Руководитель офиса', 'Юрист', 'Эксперт']:
                callback_data = f"admin_view_contract_{user_temp_data[user_id]['editing_client']['client_id']}"
            else:
                callback_data = get_contract_callback(user_id, user_temp_data[user_id]['editing_client']['client_id'])
            
            bot.send_message(message.chat.id, "Возврат к просмотру договора...")
            return
        
        user_temp_data[user_id]['editing_client']['parameter'] = parameter_name
        user_temp_data[user_id]['editing_client']['db_field'] = db_field
        user_temp_data[user_id]['editing_client']['step'] = 'value'
        
        response_message = bot.send_message(
            message.chat.id,
            f"Введите новое значение для параметра '{parameter_name}':"
        )
        user_message_id = response_message.message_id
        bot.register_next_step_handler(response_message, handle_value_input_contract, user_id, user_message_id)

    def handle_value_input_contract(message, user_id, user_message_id):
        """Обработка ввода нового значения параметра для договора"""
        # Не пытаемся удалять сообщения - это может вызывать ошибки
        # Вместо этого просто работаем с текущим сообщением
        
        if user_id not in user_temp_data or 'editing_client' not in user_temp_data[user_id]:
            bot.send_message(message.chat.id, "Ошибка: данные редактирования не найдены")
            return_to_main_menu_contract(message, user_id)
            return
        
        editing_data = user_temp_data[user_id]['editing_client']
        parameter_name = editing_data['parameter']
        db_field = editing_data['db_field']
        new_value = message.text.strip()
        client_id = editing_data['client_id']
        client_data = editing_data['client_data']
        
        try:
            # Обновляем данные в структуре
            client_data[db_field] = new_value
            
            # Сохраняем в файл
            from word_utils import create_fio_data_file
            create_fio_data_file(client_data)
            
            # Обновляем в базе данных

            update_client_in_database(client_id, db_field, new_value)
            
            msg = bot.send_message(
                message.chat.id,
                f"Параметр '{parameter_name}' успешно обновлен на значение '{new_value}'. Подождите, документы редактируются..."
            )
            
            # Редактируем документы
            fio = client_data['fio']
            client_dir = f"clients/{client_id}/Документы"
            
            files = []
            try:
                from word_utils import edit_files
                for filename in os.listdir(client_dir):
                    if os.path.isfile(os.path.join(client_dir, filename)):
                        files.append(filename)
                print(f"Редактируем файлы: {files}")
                edit_files(files, client_data)
            except Exception as e:
                print(f"Ошибка при редактировании файлов: {e}")
            
            time.sleep(2)
            
            try:
                bot.delete_message(message.chat.id, msg.message_id)
            except:
                pass  # Игнорируем ошибку удаления сообщения
            
            # Очищаем временные данные
            if user_id in user_temp_data and 'editing_client' in user_temp_data[user_id]:
                del user_temp_data[user_id]['editing_client']

            # Обновляем данные в user_temp_data
            from database import get_client_from_db_by_client_id
            updated_client = get_client_from_db_by_client_id(client_id)
            if updated_client:
                user_temp_data[user_id] = updated_client
            
            # Возвращаем к соответствующему просмотру договора через кнопку
            from database import get_admin_from_db_by_user_id
            admin_data = get_admin_from_db_by_user_id(user_id)
            
            if admin_data and admin_data.get('admin_value') in ['Директор', 'Технический директор', 'Руководитель офиса', 'Юрист', 'Эксперт']:
                callback_data = f"admin_view_contract_{client_id}"
            elif admin_data and admin_data.get('admin_value') in ['Клиент']:
                callback_data = f"view_contract_{client_id}"
            else:
                callback_data = get_contract_callback(user_id, client_id)
            
            # Создаем клавиатуру для возврата
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.send_message(
                message.chat.id,
                "✅ Данные успешно обновлены! Документы отредактированы.\n\nВыберите действие:",
                reply_markup=keyboard
            )
            
        except Exception as e:
            error_msg = f"Ошибка при обновлении: {e}"
            print(error_msg)
            
            # Отправляем сообщение об ошибке
            bot.send_message(message.chat.id, error_msg)
            
            # Предлагаем вернуться к договору
            keyboard = types.InlineKeyboardMarkup()
            if admin_data and admin_data.get('admin_value') in ['Директор', 'Технический директор', 'Руководитель офиса', 'Юрист', 'Эксперт']:
                callback_data = f"admin_view_contract_{client_id}"
            else:
                callback_data = get_contract_callback(user_id, client_id)
            
            keyboard.add(types.InlineKeyboardButton("◀️ Назад к договору", callback_data=callback_data))
            bot.send_message(message.chat.id, "Возврат к просмотру договора...", reply_markup=keyboard)
    def notify_appraisers_about_payment(bot, client_id, fio):
        """Уведомить всех оценщиков о подтвержденной оплате"""
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT user_id FROM admins 
                        WHERE admin_value = 'Оценщик' AND is_active = true
                    """)
                    appraisers = cursor.fetchall()
                    
                    for appraiser in appraisers:
                        try:
                            keyboard = types.InlineKeyboardMarkup()
                            keyboard.add(types.InlineKeyboardButton(
                                "🏷️ Перейти к калькуляциям", 
                                callback_data="appraiser_calc"
                            ))
                            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                            
                            bot.send_message(
                                int(appraiser[0]),
                                f"🏷️ Необходимо сделать калькуляцию по авто\n\n"
                                f"👤 ФИО: {fio}\n"
                                f"📋 Номер договора: {client_id}",
                                reply_markup=keyboard
                            )
                        except Exception as e:
                            print(f"Не удалось уведомить оценщика {appraiser[0]}: {e}")
        except Exception as e:
            print(f"Ошибка уведомления оценщиков: {e}")
    def return_to_main_menu_contract(message, user_id):
        """Возврат в главное меню для договора"""
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        bot.send_message(message.chat.id, "Возврат в главное меню", reply_markup=keyboard)
    def update_client_in_database(client_id, db_field, new_value):
        """Обновление данных клиента в базе данных"""
        try:
            db = DatabaseManager()
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    client = get_client_from_db_by_client_id(client_id)
                    if not client:
                        raise Exception(f"Клиент с ID {client_id} не найден в базе")
                    
                    try:
                        if client.get('data_json'):
                            data_json = json.loads(client['data_json'])
                        else:
                            data_json = {}
                    except (json.JSONDecodeError, TypeError):
                        data_json = {}
                    
                    data_json[db_field] = new_value
                    
                    # Проверяем существование столбца в таблице
                    cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'clients' AND column_name = %s
                    """, (db_field,))
                    
                    column_exists = cursor.fetchone()
                    
                    if column_exists:
                        update_query = f"UPDATE clients SET \"{db_field}\" = %s, data_json = %s WHERE client_id = %s"
                        cursor.execute(update_query, (new_value, json.dumps(data_json, ensure_ascii=False), client_id))
                        print(f"Обновлено основное поле {db_field}")
                    else:
                        update_query = "UPDATE clients SET data_json = %s WHERE client_id = %s"
                        cursor.execute(update_query, (json.dumps(data_json, ensure_ascii=False), client_id))
                        print(f"Обновлено поле {db_field} в JSON")
                    
                    conn.commit()
                    print(f"База данных успешно обновлена для клиента {client_id}")
            
        except Exception as e:
            print(f"Ошибка обновления базы данных: {e}")
            raise e
    @bot.callback_query_handler(func=lambda call: call.data == "btn_output")
    @prevent_double_click(timeout=3.0)
    def callback_btn_output(call):
        """Скачать таблицу по всем клиентам"""
        user_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="⏳ Формирование таблицы со всеми клиентами...\n\nЭто может занять некоторое время."
        )
        
        try:
            import tempfile
            import os
            from word_utils import export_clients_db_to_excel
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(mode='w+b', suffix='.xlsx', delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Экспортируем данные
            success = export_clients_db_to_excel(output_path=temp_path)
            
            if success and os.path.exists(temp_path):
                # Отправляем файл
                with open(temp_path, 'rb') as file:
                    bot.send_document(
                        call.message.chat.id,
                        document=file,
                        caption="📊 Таблица со всеми клиентами",
                        visible_file_name="Все_клиенты.xlsx"
                    )
                
                # Удаляем временный файл
                os.unlink(temp_path)
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="✅ Таблица успешно сформирована и отправлена!",
                    reply_markup = keyboard
                )
            else:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Ошибка при формировании таблицы",
                    reply_markup = keyboard
                )
        
        except Exception as e:
            print(f"Ошибка экспорта всех клиентов: {e}")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ Ошибка: {e}"
            )


    @bot.callback_query_handler(func=lambda call: call.data == "btn_export_all_admins")
    @prevent_double_click(timeout=3.0)
    def callback_btn_export_all_admins(call):
        """Скачать таблицу по всем агентам/администраторам"""
        user_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="⏳ Формирование таблицы со всеми агентами...\n\nЭто может занять некоторое время."
        )
        
        try:
            import tempfile
            import os
            from database import export_all_admins_to_excel
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(mode='w+b', suffix='.xlsx', delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Экспортируем данные
            success = export_all_admins_to_excel(temp_path)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            if success and os.path.exists(temp_path):
                # Отправляем файл
                with open(temp_path, 'rb') as file:
                    bot.send_document(
                        call.message.chat.id,
                        document=file,
                        caption="👨‍💼 Таблица со всеми агентами и администраторами",
                        visible_file_name="Все_агенты.xlsx",
                        reply_markup = keyboard
                    )
                
                # Удаляем временный файл
                os.unlink(temp_path)
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="✅ Таблица успешно сформирована и отправлена!",
                    reply_markup = None
                )
            else:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Ошибка при формировании таблицы",
                    reply_markup = keyboard
                )
        
        except Exception as e:
            print(f"Ошибка экспорта всех агентов: {e}")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ Ошибка: {e}"
            )
       
    @bot.callback_query_handler(func=lambda call: call.data == "personal_cabinet_agent")
    @prevent_double_click(timeout=3.0)
    def personal_cabinet_agent_handler(call):
        """Личный кабинет агента"""
        user_id = call.from_user.id
        
        # Получаем данные агента из admins
        admin_data = get_admin_from_db_by_user_id(user_id)
        
        if not admin_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        # Получаем статистику по договорам агента
        from database import DatabaseManager
        db = DatabaseManager()
        
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Количество активных договоров (agent_id совпадает и status != "Завершен")
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE agent_id = %s::text 
                        AND (status != 'Завершен' OR status IS NULL)
                    """, (user_id,))
                    active_contracts = cursor.fetchone()[0]
                    
                    # Количество завершенных договоров (agent_id совпадает и status == "Завершен")
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE agent_id = %s::text 
                        AND status = 'Завершен'
                    """, (user_id,))
                    completed_contracts = cursor.fetchone()[0]
                    
                    # Общее количество договоров
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE agent_id = %s::text
                    """, (user_id,))
                    total_contracts = cursor.fetchone()[0]
        except Exception as e:
            print(f"Ошибка получения статистики агента: {e}")
            active_contracts = 0
            completed_contracts = 0
            total_contracts = 0
        
        # Формируем текст личного кабинета
        cabinet_text = f"👤 <b>Личный кабинет агента</b>\n\n"
        cabinet_text += f"<b>Личные данные:</b>\n"
        cabinet_text += f"👤 ФИО: {admin_data.get('fio', 'Не указано')}\n"
        cabinet_text += f"📱 Телефон: {admin_data.get('number', 'Не указан')}\n\n"
        
        cabinet_text += f"<b>📊 Статистика договоров:</b>\n"
        cabinet_text += f"📋 Активные договоры: {active_contracts}\n"
        cabinet_text += f"✅ Завершенные договоры: {completed_contracts}\n"
        cabinet_text += f"📊 Всего договоров: {total_contracts}\n"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📋 Просмотреть договоры", callback_data="agent_view_all_contracts_0"))
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=cabinet_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_view_all_contracts_"))
    @prevent_double_click(timeout=3.0)
    def agent_view_all_contracts_handler(call):
        """Просмотр всех договоров агента с пагинацией"""
        agent_id = call.from_user.id
        page = int(call.data.replace("agent_view_all_contracts_", ""))
        
        # Получаем все договоры агента
        from database import DatabaseManager
        db = DatabaseManager()
        
        try:
            with db.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    # Получаем все договоры агента, отсортированные по дате создания (новые первыми)
                    cursor.execute("""
                        SELECT client_id, fio, created_at, status, accident,
                            COALESCE(data_json, '{}') as data_json
                        FROM clients 
                        WHERE agent_id = %s::text
                        ORDER BY created_at DESC
                    """, (agent_id,))
                    
                    all_contracts = cursor.fetchall()
        except Exception as e:
            print(f"Ошибка получения договоров агента: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки договоров", show_alert=True)
            return
        
        if not all_contracts:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📋 У вас пока нет оформленных договоров"
            )
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="personal_cabinet_agent"))
            
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard
            )
            return
        
        # Пагинация
        contracts_per_page = 10
        total_contracts = len(all_contracts)
        total_pages = (total_contracts + contracts_per_page - 1) // contracts_per_page
        
        # Проверяем валидность страницы
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        
        start_idx = page * contracts_per_page
        end_idx = start_idx + contracts_per_page
        page_contracts = all_contracts[start_idx:end_idx]
        
        # Формируем текст
        text = f"📋 <b>Ваши договоры</b>\n"
        text += f"Всего: {total_contracts} | Страница {page + 1} из {total_pages}\n\n"
        
        for i, contract in enumerate(page_contracts, start=start_idx + 1):
            client_id = contract['client_id']
            fio = contract['fio']
            created_at = contract['created_at'][:10] if contract['created_at'] else 'н/д'
            status = contract.get('status', 'В обработке')
            accident = contract.get('accident', 'н/д')
            
            text += f"<b>{i}. Договор {client_id}</b>\n"
            text += f"   👤 {fio}\n"
            text += f"   📅 {created_at}\n"
            text += f"   📊 {status}\n"
            text += f"   ⚠️ {accident}\n\n"
        
        # Создаем клавиатуру с кнопками договоров
        keyboard = types.InlineKeyboardMarkup()
        
        # Кнопки для выбора договора (по 2 в ряд)
        buttons = []
        for i, contract in enumerate(page_contracts, start=start_idx + 1):
            btn = types.InlineKeyboardButton(
                f"{i}",
                callback_data=get_contract_callback(agent_id, contract['client_id'])
            )
            buttons.append(btn)
            
            # Добавляем по 5 кнопок в ряд
            if len(buttons) == 5 or i == start_idx + len(page_contracts):
                keyboard.row(*buttons)
                buttons = []
        
        # Навигация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("◀️ Назад", callback_data=f"agent_view_all_contracts_{page - 1}"))
        
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("Далее ▶️", callback_data=f"agent_view_all_contracts_{page + 1}"))
        
        if nav_buttons:
            keyboard.row(*nav_buttons)
        
        # Кнопка возврата
        keyboard.add(types.InlineKeyboardButton("◀️ Личный кабинет", callback_data="personal_cabinet_agent"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    
    @bot.callback_query_handler(func=lambda call: call.data == "personal_cabinet")
    @prevent_double_click(timeout=3.0)
    def personal_cabinet_handler(call):
        """Личный кабинет директора/руководителя"""
        user_id = call.from_user.id
        
        # Получаем данные из admins
        admin_data = get_admin_from_db_by_user_id(user_id)
        
        if not admin_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        admin_value = admin_data.get('admin_value', '')
        
        # Получаем статистику по ВСЕМ договорам в базе
        from database import DatabaseManager
        from datetime import datetime
        db = DatabaseManager()
        
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. Общее число клиентов (у кого составлен договор)
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients
                    """)
                    result = cursor.fetchone()
                    total_clients = result[0] if result else 0
                    
                    # 2. Общее число действующих клиентов (статус != "Завершен")
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status != 'Завершен' OR status IS NULL
                    """)
                    result = cursor.fetchone()
                    active_clients = result[0] if result else 0
                    
                    # 3. Общее число действующих клиентов до претензии
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE (status != 'Завершен' OR status IS NULL)
                        AND status NOT IN ('Составлено заявление к Фин.омбудсмену', 
                                        'Составлено исковое заявление', 
                                        'Составлена претензия')
                    """)
                    result = cursor.fetchone()
                    clients_before_claim = result[0] if result else 0
                    
                    # 4. Общее число действующих клиентов на стадии претензия
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Составлена претензия'
                    """)
                    result = cursor.fetchone()
                    clients_claim_stage = result[0] if result else 0
                    
                    # 5. Общее число действующих клиентов на стадии омбудсмен
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Составлено заявление к Фин.омбудсмену'
                    """)
                    result = cursor.fetchone()
                    clients_ombudsman_stage = result[0] if result else 0
                    
                    # 6. Общее число действующих клиентов на стадии иск
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Составлено исковое заявление'
                    """)
                    result = cursor.fetchone()
                    clients_lawsuit_stage = result[0] if result else 0
                    
                    # 7. Общее число действующих клиентов на стадии деликт
                    cursor.execute("""
                        SELECT COUNT(*) FROM clients 
                        WHERE status = 'Деликт'
                    """)
                    result = cursor.fetchone()
                    clients_delict_stage = result[0] if result else 0
                    
                    # 8. Общий доход за месяц (оплаченные договоры за месяц * 25000)
                    now = datetime.now()
                    start_month = now.strftime('%Y-%m-01')

                    cursor.execute("""
                        SELECT COUNT(DISTINCT c.client_id) 
                        FROM clients c
                        INNER JOIN pending_approvals pa ON c.client_id = pa.client_id
                        WHERE pa.document_type = 'payment' 
                        AND pa.status = 'approved'
                        AND pa.reviewed_at >= %s::timestamp
                    """, (start_month,))
                    result = cursor.fetchone()
                    monthly_paid_contracts = result[0] if result else 0
                    monthly_total_income = monthly_paid_contracts * 25000

                    # 9. Зарплата за месяц (оплаченные договоры за месяц, созданные агентом/админом * 1000)
                    # Используем таблицу agent_earnings_history для точного подсчета
                    cursor.execute("""
                        SELECT COALESCE(SUM(amount), 0)
                        FROM agent_earnings_history
                        WHERE payment_confirmed_at >= %s::timestamp
                    """, (start_month,))
                    result = cursor.fetchone()
                    monthly_salary_expenses = float(result[0]) if result else 0.0

                    # Альтернативный способ (если нужно именно количество договоров):
                    # cursor.execute("""
                    #     SELECT COUNT(*)
                    #     FROM agent_earnings_history
                    #     WHERE payment_confirmed_at >= %s::timestamp
                    # """, (start_month,))
                    # result = cursor.fetchone()
                    # monthly_agent_contracts = result[0] if result else 0
                    # monthly_salary_expenses = monthly_agent_contracts * 1000

                    # 10. Чистая прибыль за год (сумма по всем месяцам: доход - зарплата)
                    # Получаем начало года
                    start_year = f"{now.year}-01-01"

                    # Считаем общий доход за год (оплаченные договоры * 25000)
                    cursor.execute("""
                        SELECT COUNT(DISTINCT c.client_id) 
                        FROM clients c
                        INNER JOIN pending_approvals pa ON c.client_id = pa.client_id
                        WHERE pa.document_type = 'payment' 
                        AND pa.status = 'approved'
                        AND pa.reviewed_at >= %s::timestamp
                    """, (start_year,))
                    result = cursor.fetchone()
                    yearly_paid_contracts = result[0] if result else 0
                    yearly_total_income = yearly_paid_contracts * 25000

                    # Считаем зарплату за год (начисления агентам/админам)
                    cursor.execute("""
                        SELECT COALESCE(SUM(amount), 0)
                        FROM agent_earnings_history
                        WHERE payment_confirmed_at >= %s::timestamp
                    """, (start_year,))
                    result = cursor.fetchone()
                    yearly_salary_expenses = float(result[0]) if result else 0.0

                    # Чистая прибыль за год
                    net_profit = yearly_total_income - yearly_salary_expenses
                    
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            import traceback
            traceback.print_exc()
            total_income = 0
            monthly_paid_contracts = 0
            monthly_total_income = 0
            monthly_salary_expenses = 0
            yearly_paid_contracts = 0
            yearly_total_income = 0
            yearly_salary_expenses = 0
            net_profit = 0
        
        # Формируем текст личного кабинета
        cabinet_text = f"👤 <b>Личный кабинет</b>\n\n"
        cabinet_text += f"<b>Личные данные:</b>\n"
        cabinet_text += f"👤 ФИО: {admin_data.get('fio', 'Не указано')}\n"
        cabinet_text += f"📱 Телефон: {admin_data.get('number', 'Не указан')}\n"
        cabinet_text += f"🏙 Город: {admin_data.get('city_admin', 'Не указан')}\n"
        cabinet_text += f"👔 Роль: {admin_value}\n\n"
        
        # Для директора показываем подробную статистику
        if admin_value == 'Директор':
            cabinet_text += f"<b>📊 Детальная статистика:</b>\n\n"
            cabinet_text += f"1️⃣ Общее число клиентов: <b>{total_clients}</b>\n"
            cabinet_text += f"2️⃣ Действующих клиентов: <b>{active_clients}</b>\n"
            cabinet_text += f"3️⃣ До претензии: <b>{clients_before_claim}</b>\n"
            cabinet_text += f"4️⃣ На стадии претензии: <b>{clients_claim_stage}</b>\n"
            cabinet_text += f"5️⃣ На стадии омбудсмен: <b>{clients_ombudsman_stage}</b>\n"
            cabinet_text += f"6️⃣ На стадии иск: <b>{clients_lawsuit_stage}</b>\n"
            cabinet_text += f"7️⃣ На стадии деликт: <b>{clients_delict_stage}</b>\n\n"
            
            cabinet_text += f"<b>💰 Финансы:</b>\n"
            cabinet_text += f"8️⃣ Общий доход за месяц: <b>{monthly_total_income:,} ₽</b>\n"
            cabinet_text += f"   (оплачено договоров: {monthly_paid_contracts})\n"
            cabinet_text += f"9️⃣ Зарплата за месяц: <b>{int(monthly_salary_expenses):,} ₽</b>\n"
            cabinet_text += f"🔟 Чистая прибыль за год: <b>{int(net_profit):,} ₽</b>\n"
        else:
            # Для остальных ролей показываем базовую статистику
            cabinet_text += f"<b>📊 Общая статистика:</b>\n"
            cabinet_text += f"📋 Активные договоры: {active_clients}\n"
            cabinet_text += f"📊 Всего договоров: {total_clients}\n"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=cabinet_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "callback_client_phone")
    @prevent_double_click(timeout=3.0)
    def handle_client_phone_request(call):
        """Обработка запроса на звонок от клиента"""
        user_id = call.from_user.id
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📝 Кратко опишите свой вопрос:"
        )
        
        bot.register_next_step_handler(msg, process_phone_request_description, user_id, msg.message_id)


    def process_phone_request_description(message, user_id, prev_msg_id):
        """Обработка описания вопроса и отправка уведомлений администраторам"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        description = message.text.strip()
        
        # Получаем данные клиента
        client_data = get_admin_from_db_by_user_id(user_id)
        
        if not client_data:
            bot.send_message(message.chat.id, "❌ Ошибка: данные пользователя не найдены")
            return
        
        client_fio = client_data.get('fio', 'Не указано')
        client_number = client_data.get('number', 'Не указан')
        client_city = client_data.get('city_admin', '')
        
        # Получаем администраторов из того же города
        db_instance = DatabaseManager()
        administrators = []
        
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT user_id FROM admins 
                        WHERE admin_value = 'Администратор' 
                        AND city_admin = %s 
                        AND is_active = true
                    """, (client_city,))
                    administrators = cursor.fetchall()
        except Exception as e:
            print(f"Ошибка получения администраторов: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка при отправке запроса")
            return
        
        if not administrators:
            bot.send_message(
                message.chat.id, 
                "⚠️ К сожалению, в данный момент нет доступных администраторов в вашем городе.\n"
                "Попробуйте позже или свяжитесь с нами другим способом."
            )
            return
        
        # Формируем сообщение для администраторов
        admin_message = (
            f"📞 <b>Запрос на звонок</b>\n\n"
            f"👤 <b>Клиент:</b> {client_fio}\n"
            f"📱 <b>Телефон:</b> {client_number}\n"
            f"🏙 <b>Город:</b> {client_city}\n\n"
            f"📝 <b>Описание вопроса:</b>\n{description}"
        )
        
        # Отправляем уведомления всем администраторам
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        sent_count = 0
        for admin in administrators:
            try:
                bot.send_message(admin[0], admin_message, parse_mode='HTML', reply_markup = keyboard)
                sent_count += 1
            except Exception as e:
                print(f"Не удалось уведомить администратора {admin[0]}: {e}")
        
        # Уведомляем клиента
        if sent_count > 0:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.send_message(
                message.chat.id,
                f"✅ Ваш запрос отправлен!\n\n"
                f"Администратор свяжется с вами в ближайшее время по номеру:\n"
                f"📱 {client_number}",
                reply_markup=keyboard
            )
        else:
            bot.send_message(
                message.chat.id,
                "❌ К сожалению, не удалось отправить запрос.\n"
                "Попробуйте позже или свяжитесь с нами другим способом."
            )
    def zayavlenie_predstavitel_insurance(call, data):
        admin_data = get_admin_from_db_by_fio(data['fio_not'])
        if data['sobstvenik'] == 'С начала':
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
                    [str(data["insurance"]), str(data["fio_not"]), str(admin_data["seria_pasport"]), str(admin_data["number_pasport"]), str(admin_data["date_of_birth"]),
                    str(admin_data["where_pasport"]), str(admin_data["when_pasport"]), str(admin_data["city_birth"]), str(admin_data["index_postal"]), str(admin_data["address"]),
                    str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["number_not"]), str(data["place"]),
                    str(data["number_photo"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"])],
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
                    [str(data["insurance"]), str(data["fio_not"]), str(admin_data["seria_pasport"]), str(admin_data["number_pasport"]), str(admin_data["date_of_birth"]),
                    str(admin_data["where_pasport"]), str(admin_data["when_pasport"]), str(admin_data["city_birth"]), str(admin_data["index_postal"]), str(admin_data["address"]),
                    str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["address_park"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["number_not"]), str(data["place"]),
                    str(data["number_photo"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"])],
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
                    [str(data["insurance"]), str(data["fio_not"]), str(admin_data["seria_pasport"]), str(admin_data["number_pasport"]), str(admin_data["date_of_birth"]),
                    str(admin_data["where_pasport"]), str(admin_data["when_pasport"]), str(admin_data["city_birth"]), str(admin_data["index_postal"]), str(admin_data["address"]),
                    str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["number_not"]), str(data["place"]),
                    str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"])],
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
                    [str(data["insurance"]), str(data["fio_not"]), str(admin_data["seria_pasport"]), str(admin_data["number_pasport"]), str(admin_data["date_of_birth"]),
                    str(admin_data["where_pasport"]), str(admin_data["when_pasport"]), str(admin_data["city_birth"]), str(admin_data["index_postal"]), str(admin_data["address"]),
                    str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                    str(data["date_of_birth"]), str(data["where_pasport"]), str(data["when_pasport"]),
                    str(data["city_birth"]), str(data["index_postal"]), str(data["address"]), str(data["docs"]), 
                    str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                    str(data["dkp"]), str(data["marks"]), str(data["year_auto"]),
                    str(data["car_number"]), str(data["address_park"]), str(data["date_dtp"]), str(data["time_dtp"]),
                    str(data["address_dtp"]), str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                    str(data["number_insurance"]), str(data["date_insurance"]), str(data["city"]), str(data["number_not"]), str(data["place"]),
                    str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                    str(data["BIK"]), str(data["INN"]), str(data["date_ins"])],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление в страховую представитель эвакуатор по форме ГИБДД.docx",
                    f"clients/{data['client_id']}/Документы/Заявление в страховую.docx"
                    )
            try:
                with open(f"clients/{data['client_id']}/Документы/Заявление в страховую.docx", 'rb') as document_file:
                    bot.send_document(call.message.chat.id, document_file)   
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, f"Файл не найден")

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))    
            bot.send_message(
                data['user_id'],
                "✅ Заявление в страховую успешно сформировано!",
                reply_markup=keyboard
            )

            replace_words_in_word(
                    ["{{ Страховая }}", "{{ Город }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}", 
                    "{{ Паспорт_серия_юрист }}", "{{ Паспорт_номер_юрист }}", "{{ ДР_юрист }}", "{{ Паспорт_выдан_юрист }}", "{{ Паспорт_когда_юрист }}",
                    "{{ Телефон_представителя }}", "{{ ФИОк_юрист }}"],
                    [str(data["insurance"]), str(data["city"]), str(data["N_dov_not"]), str(data["data_dov_not"]), str(admin_data["fio"]),
                    str(admin_data["seria_pasport"]), str(admin_data["number_pasport"]), str(admin_data["date_of_birth"]), str(admin_data["where_pasport"]), str(admin_data["when_pasport"]),
                    str(data["number_not"]), str(admin_data["fio_k"])],
                    "Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Заявление возврат доверенности.docx",
                    f"clients/{data['client_id']}/Документы/Заявление возврат доверенности.docx"
                    )
            try:
                with open(f"clients/{data['client_id']}/Документы/Заявление возврат доверенности.docx", 'rb') as document_file:
                    bot.send_document(call.message.chat.id, document_file)   
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, f"Файл не найден")
            try:
                with open(f"Шаблоны/1. ДТП/1. На ремонт/3. Заявление в страховую после ДТП/Опись документов.docx", 'rb') as document_file:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=get_contract_callback(call.message.chat.id, data['client_id'])))
                    keyboard.add(types.InlineKeyboardButton("📋 Получить документы из страховой", callback_data=f"agent_request_act_payment_{data['client_id']}"))    
                    bot.send_document(call.message.chat.id, document_file, reply_markup = keyboard)   
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, f"Файл не найден")

def notify_directors_about_document(bot, client_id, fio, doc_type):
    """Уведомить всех директоров о новом документе"""
    db_instance = DatabaseManager()
    try:
        with db_instance.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id FROM admins 
                    WHERE admin_value = 'Администратор' AND is_active = true
                """)
                directors = cursor.fetchall()
                
                # Получаем approval_id для доверенности или оплаты
                approval_id = None
                if doc_type == "Доверенность":
                    cursor.execute("""
                        SELECT id FROM pending_approvals 
                        WHERE client_id = %s AND document_type = 'doverennost' AND status = 'pending'
                        ORDER BY created_at DESC LIMIT 1
                    """, (client_id,))
                    result = cursor.fetchone()
                    if result:
                        approval_id = result[0]
                elif doc_type == "Оплата":  # ДОБАВИТЬ
                    cursor.execute("""
                        SELECT id FROM pending_approvals 
                        WHERE client_id = %s AND document_type = 'payment' AND status = 'pending'
                        ORDER BY created_at DESC LIMIT 1
                    """, (client_id,))
                    result = cursor.fetchone()
                    if result:
                        approval_id = result[0]
                
                for director in directors:
                    try:
                        keyboard = types.InlineKeyboardMarkup()
                        
                        # Для доверенности - кнопка прямого перехода к просмотру
                        if doc_type == "Доверенность" and approval_id:
                            keyboard.add(types.InlineKeyboardButton(
                                "📄 Проверить доверенность", 
                                callback_data=f"view_doverennost_approval_{approval_id}"
                            ))
                        # ДЛЯ ОПЛАТЫ - кнопка прямого перехода
                        elif doc_type == "Оплата" and approval_id:
                            keyboard.add(types.InlineKeyboardButton(
                                "💳 Проверить оплату", 
                                callback_data=f"view_payment_approval_{approval_id}"
                            ))
                        
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                        
                        bot.send_message(
                            int(director[0]),
                            f"📄 {doc_type} ожидает подтверждения\n\n"
                            f"📋 Договор: {client_id}\n"
                            f"👤 Клиент: {fio}",
                            reply_markup=keyboard
                        )
                    except Exception as e:
                        print(f"Не удалось уведомить Администратора {director[0]}: {e}")
    except Exception as e:
        print(f"Ошибка уведомления Администраторов: {e}")

def search_admins_by_fio(search_term, connection_params=None):
    """Поиск администраторов по ФИО"""
    try:
        db = DatabaseManager(connection_params)
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                search_term = search_term.strip()
                
                print(f"Поиск администраторов по ФИО: '{search_term}'")
                
                results = []
                
                # 1. Точное совпадение
                exact_patterns = [
                    search_term,
                    search_term.lower(),
                    search_term.upper(),
                    search_term.title()
                ]
                
                for pattern in exact_patterns:
                    query = '''
                    SELECT id, user_id, fio, number, admin_value, city_admin, is_active
                    FROM admins 
                    WHERE fio = %s AND is_active = true
                    ORDER BY id DESC
                    '''
                    
                    cursor.execute(query, (pattern,))
                    exact_results = cursor.fetchall()
                    if exact_results:
                        results.extend(exact_results)
                        print(f"Найдено точных совпадений: {len(exact_results)}")
                        break
                
                # 2. Частичное совпадение
                if not results:
                    partial_patterns = [
                        f"%{search_term}%",
                        f"%{search_term.lower()}%", 
                        f"%{search_term.upper()}%",
                        f"%{search_term.title()}%"
                    ]
                    
                    for pattern in partial_patterns:
                        query = '''
                        SELECT id, user_id, fio, number, admin_value, city_admin, is_active
                        FROM admins 
                        WHERE fio ILIKE %s AND is_active = true
                        ORDER BY id DESC
                        '''
                        
                        cursor.execute(query, (pattern,))
                        partial_results = cursor.fetchall()
                        if partial_results:
                            results.extend(partial_results)
                            print(f"Найдено частичных совпадений: {len(partial_results)}")
                            break
                
                # 3. Поиск по отдельным словам
                if not results:
                    search_words = search_term.split()
                    if len(search_words) >= 2:
                        first_word = search_words[0].strip()
                        second_word = search_words[1].strip()
                        
                        query = '''
                        SELECT id, user_id, fio, number, admin_value, city_admin, is_active
                        FROM admins 
                        WHERE fio ILIKE %s AND fio ILIKE %s AND is_active = true
                        ORDER BY id DESC
                        '''
                        
                        cursor.execute(query, (f"%{first_word}%", f"%{second_word}%"))
                        word_results = cursor.fetchall()
                        if word_results:
                            results.extend(word_results)
                            print(f"Найдено по словам '{first_word}' + '{second_word}': {len(word_results)}")
                
                # Удаляем дубликаты по id
                unique_results = []
                seen_ids = set()
                
                for result in results:
                    admin_id = result['id']
                    if admin_id not in seen_ids:
                        unique_results.append(dict(result))
                        seen_ids.add(admin_id)
                
                print(f"Уникальных результатов поиска администраторов: {len(unique_results)}")
                
                return unique_results
    except Exception as e:
        print(f"Ошибка поиска администраторов по ФИО: {e}")
        return []


def get_admin_by_id(admin_id, connection_params=None):
    """Получение данных администратора по ID"""
    try:
        db = DatabaseManager(connection_params)
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                query = '''
                SELECT * FROM admins 
                WHERE id = %s AND is_active = true
                '''
                
                cursor.execute(query, (admin_id,))
                result = cursor.fetchone()
                
                if result:
                    return dict(result)
                return None
    except Exception as e:
        print(f"Ошибка получения данных администратора: {e}")
        return None


def update_admin_role(admin_id, new_role, connection_params=None):
    """Обновление роли администратора"""
    try:
        db = DatabaseManager(connection_params)
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                query = '''
                UPDATE admins 
                SET admin_value = %s
                WHERE id = %s
                '''
                
                cursor.execute(query, (new_role, admin_id))
                conn.commit()
                
                print(f"✅ Роль администратора ID {admin_id} обновлена на '{new_role}'")
                return True
    except Exception as e:
        print(f"Ошибка обновления роли администратора: {e}")
        return False
    
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




