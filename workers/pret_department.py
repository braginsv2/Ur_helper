from telebot import types
import re
import psycopg2.extras
import json
import os
from PIL import Image
import logging
from datetime import datetime
from database import (
    DatabaseManager,
    get_client_from_db_by_client_id,
    save_client_to_db_with_id,
    get_admin_from_db_by_user_id
)
from word_utils import create_fio_data_file, replace_words_in_word, get_next_business_date
import threading
import time
from functools import wraps

active_callbacks = {}
callback_lock = threading.Lock()
db = DatabaseManager()
upload_sessions = {}

def setup_pret_department_handlers(bot, user_temp_data):
    """Регистрация обработчиков для претензий, заявлений к омбудсмену и исков"""
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
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_docs_pret_department"))
    @prevent_double_click(timeout=3.0)
    def pret_department_contracts_handler(call):
        """Список договоров для претензионного отдела"""
        user_id = call.from_user.id
        
        # Парсим страницу из callback_data (например, create_docs_pret_department_0)
        if "_" in call.data and call.data.split("_")[-1].isdigit():
            page = int(call.data.split("_")[-1])
        else:
            page = 0
        
        # Получаем договоры со статусом "Ожидание претензии" или "Составлена претензия"
        from database import DatabaseManager
        db = DatabaseManager()
        
        try:
            with db.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT client_id, fio, created_at, status, accident
                        FROM clients
                        WHERE status IN ('Ожидание претензии', 'Составлена претензия')
                        AND calculation = 'Загружена'
                        AND data_json::jsonb->>'payment_confirmed' = 'Yes'
                        AND data_json::jsonb->>'doverennost_confirmed' = 'Yes'
                        ORDER BY created_at DESC
                    """)
                    all_contracts = cursor.fetchall()
        except Exception as e:
            print(f"Ошибка получения договоров для претензионного отдела: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки договоров", show_alert=True)
            return
        
        if not all_contracts:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📋 Нет договоров для работы претензионного отдела",
                reply_markup=keyboard
            )
            return
        
        # Пагинация
        contracts_per_page = 5
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
        text = f"📝 <b>Договоры для претензионного отдела</b>\n"
        text += f"Всего договоров: {total_contracts}\n\n"
        
        for i, contract in enumerate(page_contracts, start=start_idx + 1):
            client_id = contract['client_id']
            fio = contract['fio']
            created_at = contract['created_at'][:10] if contract['created_at'] else 'н/д'
            status = contract.get('status', 'В обработке')
            
            text += f"<b>{i}. Договор {client_id}</b>\n"
            text += f"   👤 {fio}\n"
            text += f"   📅 {created_at}\n"
            text += f"   📊 {status}\n\n"
        
        # Создаем клавиатуру
        keyboard = types.InlineKeyboardMarkup()
        
        # Кнопки для выбора договора (по 5 в ряд)
        buttons = []
        for i, contract in enumerate(page_contracts, start=start_idx + 1):
            btn = types.InlineKeyboardButton(
                f"{i}",
                callback_data=f"pret_view_contract_{contract['client_id']}"
            )
            buttons.append(btn)
            
            if len(buttons) == 5 or i == start_idx + len(page_contracts):
                keyboard.row(*buttons)
                buttons = []
        
        # Навигация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_docs_pret_department_{page - 1}"))
        
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("Далее ▶️", callback_data=f"create_docs_pret_department_{page + 1}"))
        
        if nav_buttons:
            keyboard.row(*nav_buttons)
        
        # Кнопка главного меню
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "btn_search_database_pret")
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
        bot.register_next_step_handler(message, search_all_clients_handler_pret, user_message_id, call.from_user.id, user_temp_data)

    def search_all_clients_handler_pret(message, user_message_id, user_id, user_temp_data):
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
            bot.register_next_step_handler(msg, search_all_clients_handler_pret, msg.message_id, user_id, user_temp_data)
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
                btn_callback = f"pret_view_contract_{client['client_id']}"
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
            
            if len(results) > 10:
                response += f"... и еще {len(results) - 10} клиентов"
            
            keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database_pret"))
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.send_message(message.chat.id, response, reply_markup=keyboard)
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка поиска: {e}")
            print(f"Ошибка поиска: {e}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("pret_view_contract_"))
    @prevent_double_click(timeout=3.0)
    def pret_view_contract_handler(call):
        """Просмотр договора администратором/директором"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        client_id = call.data.replace("pret_view_contract_", "")
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
        calc_confirmed = contract_data.get('calculation', '') == 'Загружена'
        if payment_pending and not payment_confirmed:
            contract_text += "\n⏳ Ожидает проверки оплаты"
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

        elif doverennost_confirmed:
            contract_text += "\n📜 Доверенность подтверждена"
        
        if calc_confirmed:
            contract_text += "\n📄 Калькуляция загружена"
        else:
            contract_text += "\n📄 Калькуляция не загружена"
        status = contract.get('status', '')
        if contract.get('accident', '') == 'ДТП':
            if status == "Ожидание претензии" and doverennost_confirmed and payment_confirmed and calc_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Составить претензию", callback_data=f"create_pretenziya_{client_id}"))
            elif status == "Составлена претензия" and doverennost_confirmed and payment_confirmed and calc_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Заявление Фин.омбудсмену", callback_data=f"create_ombudsmen_{client_id}"))

        keyboard.add(types.InlineKeyboardButton("📤 Загрузить документы", callback_data="download_docs"))
        keyboard.add(types.InlineKeyboardButton("📋 Просмотр данных", callback_data="view_db"))
        keyboard.add(types.InlineKeyboardButton("📂 Просмотреть документы", callback_data="view_client_documents"))
        keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database_pret"))

        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.send_message(
            chat_id=call.message.chat.id,
            text=contract_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    # ========== СОСТАВЛЕНИЕ ПРЕТЕНЗИИ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_pretenziya_"))
    @prevent_double_click(timeout=3.0)
    def callback_create_pretenziya(call):
        """Начало составления претензии"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_pretenziya_", "")
        # Загружаем данные клиента
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
        
        # Проверяем наличие необходимых документов
        payment_confirmed = data.get('payment_confirmed', '') == 'Yes'
        doverennost_confirmed = data.get('doverennost_confirmed', '') == 'Yes'
        calc_confirmed = data.get('calculation', '') == 'Загружена'
        if not payment_confirmed or not doverennost_confirmed or not calc_confirmed:
            missing = []
            if not payment_confirmed:
                missing.append("документ об оплате")
            if not doverennost_confirmed:
                missing.append("нотариальная доверенность")
            if not calc_confirmed:
                missing.append("калькуляцию")
            bot.answer_callback_query(
                call.id, 
                f"❌ Для составления претензии необходимо загрузить: {', '.join(missing)}", 
                show_alert=True
            )
            return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        user_temp_data[user_id]['pretenziya_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')
        if data.get('coin_osago', '0') == '' or data.get('coin_osago', '0') == None:
            data.update({'coin_osago': '0'})

        if data["vibor"] == "vibor1":
            if data.get("dop_osm", '') == 'Yes':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите дату ответа от страховой", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)
        elif data["vibor"] == "vibor2":
            if data.get("dop_osm", '') == 'Yes':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите дату отказа СТО (ДД.ММ.ГГГГ)", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, data_otkaz_sto, data, user_message_id)
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)


        elif data["vibor"] == "vibor3":
            if data.get("dop_osm", '') == 'Yes':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                message = bot.send_message(
                    message.chat.id,
                    "Введите дату ответа от страховой в формате ДД.ММ.ГГГГ", reply_markup = keyboard
                    )
                user_message_id = message.message_id
                bot.register_next_step_handler(message, date_ins_otv, data, user_message_id)
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите номер акта осмотра ТС", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

        elif data["vibor"] == "vibor4":
            if data.get("dop_osm", '') == 'Yes':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите дату ответа страховой в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите номер акта осмотра ТС", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

        elif data["vibor"] == "vibor5":
            if data.get("dop_osm", '') == 'Yes':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                message = bot.send_message(
                    message.chat.id,
                    "Введите дату ответа от страховой в формате ДД.ММ.ГГГГ", reply_markup = keyboard
                    )
                user_message_id = message.message_id
                bot.register_next_step_handler(message, date_ins_otv, data, user_message_id)
            else:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(call.message.chat.id, text="Введите номер акта осмотра ТС", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

    def Nv_ins(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"Nv_ins": message.text})
        if data['vibor'] == 'vibor4':
            if not user_id in user_temp_data:
                user_temp_data[user_id] = {}
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_Nv_ins")) 
            msg = bot.send_message(message.chat.id, text="Введите дату ответа страховой в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)
        elif data['vibor'] in ['vibor1', 'vibor2']:
            if not user_id in user_temp_data:
                user_temp_data[user_id] = {}
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}")) 
            msg = bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_Nv_ins")
    @prevent_double_click(timeout=3.0)
    def back_to_Nv_ins(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите номер акта осмотра ТС",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

    def Na_ins(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"Na_ins": message.text})
        if data['vibor'] in ['vibor3', 'vibor5']:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
            message = bot.send_message(
                    message.chat.id,
                    "Введите дату ответа от страховой в формате ДД.ММ.ГГГГ", reply_markup = keyboard
                    )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_ins_otv, data, user_message_id)
        elif data['vibor'] == 'vibor4':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
            msg = bot.send_message(message.chat.id, text="Введите входящий номер в страховую", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)
        elif data['vibor'] in ['vibor1', 'vibor2']:
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_Nv_ins"))
            msg = bot.send_message(message.chat.id, text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_Na_ins")
    @prevent_double_click(timeout=3.0)
    def back_to_Na_ins(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
        
        message = bot.send_message(
            message.chat.id,
            "Введите дату ответа от страховой в формате ДД.ММ.ГГГГ", reply_markup = keyboard
            )
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_ins_otv, data, user_message_id)

    def date_Na_ins(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_Na_ins": message.text})
            if data["vibor"] == "vibor1":
                user_temp_data[user_id] = data
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_Na_ins"))
                msg = bot.send_message(message.chat.id, text="Введите дату ответа страховой в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)
            elif data["vibor"] == "vibor4":
                msg = bot.send_message(message.chat.id, text="Введите дату направления на СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
            elif data["vibor"] == "vibor2":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                msg = bot.send_message(message.chat.id, text="Введите дату отказа СТО (ДД.ММ.ГГГГ)", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, data_otkaz_sto, data, user_message_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_Na_ins")
    @prevent_double_click(timeout=3.0)
    def back_to_Na_ins(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_Nv_ins"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)

    def date_ins_otv(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_ins_otv": message.text})
            if data["vibor"] == "vibor1":
                user_temp_data[user_id] = data
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_ins_otv"))
                msg = bot.send_message(message.chat.id, text="Введите дату экспертного заключения страховой компании в фомате ДД.ММ.ГГГГ", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_exp_ins, data, user_message_id)
            elif data["vibor"] == "vibor2":
                user_temp_data[user_id] = data
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_ins_otv"))
                msg = bot.send_message(message.chat.id, text="Введите город СТО", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, city_sto, data, user_message_id)
            elif data["vibor"] == "vibor3":
                data.update({"data_pret": str(get_next_business_date())})
                data.update({"status": 'Составлена претензия'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)

                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                                "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                                "{{ Дата_заявления_форма6 }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Nакта_осмотра }}", "{{ Выплата_ОСАГО }}", 
                                                "{{ Дата_ответ_страховой }}", "{{ Организация }}", "{{ Номер_экспертизы }}", "{{ Дата_экспертизы }}",
                                                "{{ Без_учета_износа }}", "{{ Утрата_стоимости }}","{{ Разница }}","{{ Дата_претензии }}"],
                                                [str(data.get("insurance", '')), str(data.get("city", '')), str(data.get("fio", '')), str(data.get("date_of_birth", '')),
                                                    str(data.get("seria_pasport", '')), str(data.get("number_pasport", '')),str(data.get("where_pasport", '')), str(data.get("when_pasport", '')),
                                                    str(data.get("N_dov_not", '')), str(data.get("data_dov_not", '')), str(data.get("fio_not", '')), str(data.get("number_not", '')),
                                                    str(data.get("date_ins", '')), str(data.get("seria_insurance", '')), str(data.get("number_insurance", '')), str(data.get("Na_ins", '')), str(data.get('coin_osago') or '0'),
                                                    str(data.get("date_ins_otv", '')), str(data.get("org_exp", '')), str(data.get("n_exp", '')),str(data.get("date_exp", '')),
                                                    str(data.get("coin_exp", '')), str(data.get("coin_exp_izn", '')), str(float(data.get("coin_exp", ''))+float(data.get("coin_exp_izn", ''))-float(data.get('coin_osago') or '0')), 
                                                    str(data.get("data_pret", ''))],
                                                    "Шаблоны/1. ДТП/1. На ремонт/У страховой нет СТО/Претензия у страховой нет СТО.docx",
                                                    "clients/"+str(data["client_id"])+"/Документы/"+"Претензия у страховой нет СТО.docx")
                try:
                    with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Претензия у страховой нет СТО.docx", 'rb') as doc:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                        bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
                    
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))
                if data['user_id'] != '8572367590': 
                    bot.send_message(
                        int(data['user_id']),
                        "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                        reply_markup = keyboard
                        )
            elif data["vibor"] == "vibor4":
                keyboard = types.InlineKeyboardMarkup()
                if not user_id in user_temp_data:
                    user_temp_data[user_id] = {}
                user_temp_data[user_id] = data
                if data.get('dop_osm', '') == 'Yes':
                    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
                else:
                    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_ins_otv"))
                msg = bot.send_message(
                    message.chat.id,
                    "Введите номер направления на ремонт", reply_markup = keyboard
                    )
                bot.register_next_step_handler(msg, N_sto, data, msg.message_id)
            elif data["vibor"] == "vibor5":
                keyboard = types.InlineKeyboardMarkup()
                if not user_id in user_temp_data:
                    user_temp_data[user_id] = {}
                user_temp_data[user_id] = data
                if data.get('dop_osm', '') == 'Yes':
                    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
                else:
                    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_Na_ins"))
                msg = bot.send_message(
                    message.chat.id,
                    "Введите юридическое название СТО, в которое направление на ремонт", reply_markup = keyboard
                    )
                bot.register_next_step_handler(msg, name_sto, data, msg.message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ответа от страховой в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_ins_otv, data, user_message_id)

    def date_exp_ins(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp_ins": message.text})
            if data["vibor"] == "vibor1":
                user_temp_data[user_id] = data
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_date_exp"))
                msg = bot.send_message(message.chat.id, text="Введите организацию, сделавшую экспертизу от страховой", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, org_exp_ins, data, user_message_id)

        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_ins_otv"))
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения страховой компании в формате ДД.ММ.ГГГГ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_exp_ins, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_ins_date_exp")
    @prevent_double_click(timeout=3.0)
    def back_to_Na_ins(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_ins_otv"))
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату экспертного заключения страховой компании в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_exp_ins, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_ins_otv")
    @prevent_double_click(timeout=3.0)
    def back_to_date_ins_otv(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor1':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_Na_ins"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ответа от страховой в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)
        elif data['vibor'] == 'vibor2':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ответа от страховой в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)
        elif data['vibor'] == 'vibor4':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_Nv_ins"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите входящий номер в страховую",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)
        elif data['vibor'] == 'vibor5':    
            if data.get('dop_osm', '') == 'Yes':
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
            else:
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_Na_ins"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ответа от страховой в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)

    def org_exp_ins(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"org_exp_ins": message.text})
        if data['vibor'] == 'vibor1':
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_org_exp")) 
            msg = bot.send_message(message.chat.id, text="Введите цену по экспертизе страховой без учета износа в рублях", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp_ins, data, user_message_id)
    
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_ins_org_exp")
    @prevent_double_click(timeout=3.0)
    def back_to_ins_org_exp(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor1':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_date_exp"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите организацию, сделавшую экспертизу от страховой",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, org_exp_ins, data, user_message_id)

    def coin_exp_ins(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"coin_exp_ins": message.text})
        if message.text.isdigit():
            if data['vibor'] == 'vibor1':
                user_temp_data[user_id] = data
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_coin_exp")) 
                msg = bot.send_message(message.chat.id, text="Введите цену по экспертизе страховой c учетом износа в рублях", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, coin_exp_ins_izn, data, user_message_id)
        else:
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_org_exp")) 
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода! Введите цену по экспертизе страховой без учета износа в рублях", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp_ins, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_ins_coin_exp")
    @prevent_double_click(timeout=3.0)
    def back_to_ins_coin_exp(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor1':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_org_exp"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите цену по экспертизе страховой без учета износа в рублях",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp_ins, data, user_message_id)

    def coin_exp_ins_izn(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"coin_exp_ins_izn": message.text})
        if message.text.isdigit():
            if data['vibor'] == 'vibor1':
                data.update({"date_pret": str(get_next_business_date())})
                data.update({"status": 'Составлена претензия'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)

                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата_заявления_форма6 }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Организация_страховой }}", "{{ Дата_экспертизы_страховой }}", "{{ Без_учета_износа_страховой }}",
                                            "{{ С_учетом_износа_страховой }}", "{{ Выплата_ОСАГО }}", "{{ Организация }}", "{{ Номер_экспертизы }}",
                                            "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}","{{ Утрата_стоимости }}", "{{ Разница }}","{{ Дата_претензии }}"],
                                            [str(data.get("insurance", '')), str(data.get("city", '')), str(data.get("fio", '')), str(data.get("date_of_birth", '')),
                                                str(data.get("seria_pasport", '')), str(data.get("number_pasport", '')),str(data.get("where_pasport", '')), str(data.get("when_pasport", '')),
                                                str(data.get("N_dov_not", '')), str(data.get("data_dov_not", '')), str(data.get("fio_not", '')), str(data.get("number_not", '')),str(data.get("Na_ins", '')), 
                                                str(data.get("date_ins", '')), str(data.get("Nv_ins", '')), str(data.get("date_dtp", '')), str(data.get("time_dtp", '')), str(data.get("address_dtp", '')),
                                                str(data.get("org_exp_ins", '')), str(data.get("date_exp_ins", '')), str(data.get("coin_exp_ins", '')),str(data.get("coin_exp_ins_izn", '')),
                                                str(data.get('coin_osago') or '0'), str(data.get("org_exp", '')), str(data.get("n_exp", '')), str(data.get("date_exp", '')),
                                                str(data.get("coin_exp", '')), str(data.get("coin_exp_izn", '')), str(float(data.get("coin_exp", '0'))+float(data.get("coin_exp_izn", '0'))-float(data.get('coin_osago') or '0')), str(data.get("date_pret", ''))],
                                                "Шаблоны/1. ДТП/1. На ремонт/Выплата без согласования/6. Претензия в страховую Выплата без согласования.docx",
                                                "clients/"+str(data["client_id"])+"/Документы/"+"Претензия в страховую Выплата без согласования.docx")
                try:
                    with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Претензия в страховую Выплата без согласования.docx", 'rb') as doc:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                        bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"view_contract_{data['client_id']}")) 
                if data['user_id'] != '8572367590': 
                    bot.send_message(
                        int(data['user_id']),
                        "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                        reply_markup = keyboard
                        )
        else:
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_coin_exp")) 
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода! Введите цену по экспертизе страховой с учетом износа в рублях", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp_ins_izn, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_ins_coin_exp_izn")
    @prevent_double_click(timeout=3.0)
    def back_to_ins_coin_exp_izn(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor1':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_ins_coin_exp"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите цену по экспертизе страховой с учетом износа в рублях",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp_ins_izn, data, user_message_id)
    def date_napr_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_napr_sto": message.text})
            if data["vibor"] == "vibor2":
                msg = bot.send_message(message.chat.id, text="Введите дату отказа СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, data_otkaz_sto, data, user_message_id)
            elif data["vibor"] == "vibor4":
                user_temp_data[user_id] = data
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_napr_sto"))
                msg = bot.send_message(message.chat.id, text="Введите юридическое название СТО, в которое направление на ремонт", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, name_sto, data, user_message_id)
        except ValueError:
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_N_sto"))
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ", reply_markup = keyboard )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_date_napr_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_date_napr_sto(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor4':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_N_sto"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату направления на СТО в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
    def data_otkaz_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            if not user_id in user_temp_data:
                user_temp_data[user_id] = {}
            data.update({"data_otkaz_sto": message.text})    
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}")) 
            msg = bot.send_message(message.chat.id, text="Введите дату ответа страховой", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_ins_otv, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату отказа СТО в формате ДД.ММ.ГГГГ" )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_otkaz_sto, data, user_message_id, user_message_id)
    def city_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"city_sto": message.text})
        if data["vibor"] == "vibor2":
            data.update({"date_pret": str(get_next_business_date())})
            data.update({"status": 'Составлена претензия'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)

            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ СТО }}","{{ Дата_предоставления_ТС }}",
                                            "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Дата_отказа_СТО }}","{{ Дата_претензии }}", "{{ Город_СТО }}"],
                                            [str(data.get("insurance",'')), str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),
                                                str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                                str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')), str(data.get("fio_not",'')), str(data.get("number_not",'')),str(data.get("Na_ins",'')), 
                                                str(data.get("date_ins",'')), str(data.get("Nv_ins",'')), str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')),
                                                str(data.get("date_napr_sto",'')), str(data.get("N_sto",'')), str(data.get("name_sto",'')), str(data.get("date_sto",'')),str(data.get("marks",'')),str(data.get("car_number",'')),
                                                str(data.get("data_otkaz_sto",'')), str(data.get("date_pret",'')), str(data.get("city_sto",'')) ],
                                                "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/7. Претензия в страховую СТО отказала.docx",
                                                "clients/"+str(data["client_id"])+"/Документы/"+"Претензия в страховую СТО отказала.docx")
            try:
                with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Претензия в страховую СТО отказала.docx", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                    bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))
            if data['user_id'] != '8572367590':  
                bot.send_message(
                    int(data['user_id']),
                    "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                    reply_markup = keyboard
                    )

        elif data["vibor"] == "vibor4":
            data.update({"date_pret": str(get_next_business_date())})
            data.update({"status": 'Составлена претензия'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)

            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                    "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                    "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                    "{{ Nакта_осмотра }}", "{{ Дата_заявления_форма6 }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}","{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                    "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ Название_СТО }}","{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ Город_СТО }}", "{{ Организация }}",
                                    "{{ Номер_экспертизы }}", "{{ Дата_экспертизы }}","{{ Без_учета_износа }}","{{ Утрата_стоимости }}","{{ Разница }}", "{{ Дата_претензии }}"],
                                    [str(data.get("insurance",'')), str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),
                                        str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                        str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')), str(data.get("fio_not",'')), str(data.get("number_not",'')),str(data.get("Na_ins",'')), 
                                        str(data.get("date_ins",'')), str(data.get("seria_insurance",'')), str(data.get("number_insurance",'')), str(data.get("Nv_ins",'')), 
                                        str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')),
                                        str(data.get("date_napr_sto",'')), str(data.get("N_sto",'')), str(data.get("name_sto",'')),str(data.get("index_sto",'')),str(data.get("address_sto",'')),
                                        str(data.get("city_sto",'')), str(data.get("org_exp",'')), str(data.get("n_exp",'')), str(data.get("date_exp",'')), str(data.get("coin_exp",'')),
                                        str(data.get("coin_exp_izn",'')), str(float(data.get("coin_exp",''))+float(data.get('coin_exp_izn',''))), str(data.get("date_pret",''))],
                                        "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО свыше 50км/6. Претензия в страховую  СТО свыше 50 км.docx",
                                        "clients/"+str(data["client_id"])+"/Документы/"+"Претензия в страховую  СТО свыше 50 км.docx")
            try:
                with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Претензия в страховую  СТО свыше 50 км.docx", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                    bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))
            if data['user_id'] != '8572367590':  
                bot.send_message(
                    int(data['user_id']),
                    "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                    reply_markup = keyboard
                    )

    def name_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        data.update({"name_sto": message.text})
        user_temp_data[user_id] = data
        if data['vibor'] == 'vibor4':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_name_sto"))
            msg = bot.send_message(
                message.chat.id,
                "Введите индекс СТО, 6 цифр", reply_markup = keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, index_sto, data, user_message_id)
        elif data['vibor'] == 'vibor5':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_name_sto"))
            msg = bot.send_message(
                message.chat.id,
                "Введите адрес СТО, в котором направление на ремонт", reply_markup = keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, address_sto, data, user_message_id)
        else:
            message = bot.send_message(message.chat.id, text="Введите индекс СТО")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_sto, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_pret_name_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_pret_name_sto(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        if data["vibor"] == 'vibor4':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_napr_sto"))
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите юридическое название СТО, в которое направление на ремонт",
                    reply_markup=keyboard
                    )
            bot.register_next_step_handler(msg, name_sto, data, msg.message_id)
        elif data["vibor"] == 'vibor5':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_ins_otv"))
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите юридическое название СТО, в которое направление на ремонт",
                    reply_markup=keyboard
                    )
            bot.register_next_step_handler(msg, name_sto, data, msg.message_id)

    def index_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_name_sto"))
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите индекс СТО, например, 123456", reply_markup = keyboard )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_sto, data, user_message_id)
        else:
            data.update({"index_sto": message.text})
            user_temp_data[user_id] = data
            if data['vibor'] == 'vibor4':
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_index_sto"))
                msg = bot.send_message(
                    message.chat.id,
                    "Введите адрес СТО", reply_markup = keyboard
                    )
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, address_sto, data, user_message_id)
            else:
                message = bot.send_message(message.chat.id, text="Введите адрес СТО" )
                user_message_id = message.message_id
                bot.register_next_step_handler(message, address_sto, data, user_message_id) 

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_pret_index_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_pret_index_sto(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        if data["vibor"] == 'vibor4':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_name_sto"))
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите индекс СТО, 6 цифр",
                    reply_markup=keyboard
                    )
            bot.register_next_step_handler(msg, index_sto, data, msg.message_id)

    def address_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"address_sto": message.text})
        user_temp_data[user_id] = data
        if data['vibor'] == 'vibor4':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_address_sto"))
            msg = bot.send_message(
                message.chat.id,
                "Введите город СТО", reply_markup = keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, city_sto, data, user_message_id)
        elif data['vibor'] == 'vibor5':
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_address_sto"))
            msg = bot.send_message(
                message.chat.id,
                "Введите дату, когда предоставили автомобиль на ремонт в формате ДД.ММ.ГГГГ", reply_markup = keyboard
                )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_sto, data, user_message_id)
        else:
            message = bot.send_message(message.chat.id, text="Введите город СТО")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, city_sto, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_pret_address_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_pret_address_sto(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor4':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_index_sto"))
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите адрес СТО, в котором направление на ремонт",
                    reply_markup=keyboard
                    )
            bot.register_next_step_handler(msg, address_sto, data, msg.message_id)
        elif data['vibor'] == 'vibor5':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_name_sto"))
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите адрес СТО, в котором направление на ремонт",
                    reply_markup=keyboard
                    )
            bot.register_next_step_handler(msg, address_sto, data, msg.message_id)

    def date_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_sto": message.text})
            user_temp_data[user_id] = data
            if data["vibor"] == "vibor5":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_date_sto"))
                msg = bot.send_message(message.chat.id, text="Введите ФИО лица, поставивший отметку о представлении ТС", reply_markup = keyboard)
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, fio_sto, data, user_message_id)

        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_address_sto"))
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату, когда предоставили автомобиль на ремонт в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_sto, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_pret_date_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_pret_date_sto(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_address_sto"))
        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату, когда предоставили автомобиль на ремонт в формате ДД.ММ.ГГГГ",
                reply_markup=keyboard
                )
        bot.register_next_step_handler(msg, date_sto, data, msg.message_id)

    def fio_sto(message, data, user_message_id):
        """Обновление ФИО"""
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        keyboard = types.InlineKeyboardMarkup()
        if len(message.text.split()) < 2:
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_date_sto"))
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат! Введите ФИО лица, поставивший отметку о представлении ТС", reply_markup = keyboard)
            bot.register_next_step_handler(msg, fio_sto, data, msg.message_id)
            return
        
        words = message.text.split()
        for word in words:
            if not word[0].isupper():
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_date_sto"))
                msg = bot.send_message(message.chat.id, "❌ Каждое слово должно начинаться с заглавной буквы! Введите ФИО лица, поставивший отметку о представлении ТС", reply_markup = keyboard)
                bot.register_next_step_handler(msg, fio_sto, data, msg.message_id)
                return
        data.update({'fio_sto': message.text.strip()}) 
        user_temp_data[user_id] = data
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_fio_sto"))
        msg = bot.send_message(message.chat.id, "Введите дату истечения срока ремонта в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
        bot.register_next_step_handler(msg, date_istch_rem, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_fio_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_fio_sto(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_date_sto"))
        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите ФИО лица, поставивший отметку о представлении ТС",
                reply_markup=keyboard
                )
        bot.register_next_step_handler(msg, fio_sto, data, msg.message_id)

    def date_istch_rem(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_istch_rem": message.text})
            user_temp_data[user_id] = data
            if data["vibor"] == "vibor5":
                data.update({"date_pret": str(get_next_business_date())})
                data.update({"status": 'Составлена претензия'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                    print(data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)

                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Дата_заявления_форма6 }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Nакта_осмотра }}", "{{ Название_СТО }}", 
                                            "{{ Адрес_СТО }}", "{{ Дата_СТО }}", "{{ ФИО_СТО }}", "{{ Дата_СТО_30 }}",
                                            "{{ Организация }}", "{{ Номер_экспертизы }}","{{ Дата_экспертизы }}", 
                                            "{{ Без_учета_износа }}", "{{ Утрата_стоимости }}","{{ Разница }}", "{{ Дата_претензии }}"],
                                            [str(data.get("insurance",'')), str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),
                                                str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                                str(data.get("N_dov_not",'')), str(data.get("data_dov_not",'')), str(data.get("fio_not",'')), str(data.get("number_not",'')),str(data.get("date_ins",'')), 
                                                str(data.get("seria_insurance",'')), str(data.get("number_insurance",'')), str(data.get("Na_ins",'')), str(data.get("name_sto",'')), str(data.get("address_sto",'')),
                                                str(data.get("date_sto",'')), str(data.get("fio_sto",'')), str(data.get("date_istch_rem",'')),str(data.get("org_exp",'')),
                                                str(data.get("n_exp",'')), str(data.get("date_exp",'')), str(data.get("coin_exp",'')), str(data.get("coin_exp_izn",'')),
                                                str(float(data.get("coin_exp",'0'))+float(data.get("coin_exp_izn",'0'))-float(data.get('coin_osago') or '0')), str(data.get("date_pret",''))],
                                                "Шаблоны/1. ДТП/1. На ремонт/Страховая не организовала ремонт/6. претензия Страховаяя не организовала ремонт.docx",
                                                "clients/"+str(data["client_id"])+"/Документы/"+"Претензия Страховая не организовала ремонт.docx")
                try:
                    with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Претензия Страховая не организовала ремонт.docx", 'rb') as doc:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                        bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))
                if data['user_id'] != '8572367590':  
                    bot.send_message(
                        int(data['user_id']),
                        "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                        reply_markup = keyboard
                        )

        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_fio_sto"))
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату истечения срока ремонта в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_istch_rem, data, user_message_id)

    def N_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"N_sto": message.text})
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor4':
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_pret_N_sto"))
            msg = bot.send_message(message.chat.id, text="Введите дату направления на ремонт", reply_markup = keyboard)
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_pret_N_sto")
    @prevent_double_click(timeout=3.0)
    def back_to_pret_N_sto(call):
        """Возврат к выбору: вводить реквизиты или нет"""
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        if data['vibor'] == 'vibor4':
            if data.get('dop_osm', '') == 'Yes':
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"create_pretenziya_{data['client_id']}"))
            else:
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_ins_otv"))
            msg = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Введите номер направления на ремонт",
                    reply_markup=keyboard
                    )
        bot.register_next_step_handler(msg, N_sto, data, msg.message_id)    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_ombudsmen_"))
    @prevent_double_click(timeout=3.0)
    def callback_create_ombudsmen(call):
        """Начало составления заявления к фин.омбудсмену"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_ombudsmen_", "")
        
        # Загружаем данные клиента
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
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['ombudsmen_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 

        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату ответа на претензию в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
            )
        bot.register_next_step_handler(msg, data_pret_otv, data, msg.message_id)

    def data_pret_otv(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_pret_otv": message.text})
            data.update({"date_ombuc": str(get_next_business_date())})
            data.update({"status": "Составлено заявление к Фин.омбудсмену"})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            if data['vibor'] == 'vibor1':
                replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}","{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", "{{ Телефон_представителя }}","{{ Серия_полиса }}", "{{ Номер_полиса }}","{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата_заявления_форма6 }}",
                                "{{ Nв_страховую }}", "{{ Организация_страховой }}","{{ Дата_экспертизы_страховой }}", "{{ Без_учета_износа_страховой }}",
                                "{{ С_учетом_износа_страховой }}", "{{ Дата_претензии }}", "{{ Дата_ответа_на_претензию }}", "{{ Выплата_ОСАГО }}", "{{ Разница }}", "{{ ФИОк }}"],
                                [str(data.get("date_ombuc",'')), str(data.get("insurance",'')),str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),
                                    str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                    str(data.get("number_not",'')), str(data.get("seria_insurance",'')), str(data.get("number_insurance",'')), str(data.get("date_insurance",'')),
                                    str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),
                                    str(data.get("date_ins_pod",'')), str(data.get("Nv_ins",'')), str(data.get("org_exp_ins",'')),str(data.get("date_exp_ins",'')),
                                    str(data.get("coin_exp_ins",'')), str(data.get("coin_exp_ins_izn",'')),str(data.get("date_pret",'')),
                                    str(data.get("data_pret_otv",'')), str(data.get('coin_osago') or '0'), str(float(data.get("coin_exp",'0'))+float(data.get("coin_exp_izn",'0'))-float(data.get('coin_osago') or '0')), str(data.get("fio_k",''))],
                                    "Шаблоны/1. ДТП/1. На ремонт/Выплата без согласования/7. Заявление фин. омбудсмену при выплате без согласования.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену.docx")
            elif data['vibor'] == 'vibor2':
                replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}","{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}",  "{{ Адрес }}", "{{ Телефон }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}","{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                                "{{ Nв_страховую }}", "{{ Организация }}","{{ Nэкспертизы }}", "{{ Дата_экспертизы }}",
                                "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ СТО }}", "{{ Дата_предоставления_ТС }}",
                                "{{ Дата_претензии }}", "{{ ФИОк }}"],
                                [str(data.get("date_ombuc",'')), str(data.get("insurance",'')),str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),str(data.get("city_birth",'')),
                                    str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                    str(data.get("address",'')), str(data.get("number",'')), str(data.get("seria_insurance",'')), str(data.get("number_insurance",'')), str(data.get("date_insurance",'')),
                                    str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),
                                    str(data.get("date_ins_pod",'')), str(data.get("Nv_ins",'')), str(data.get("org_exp",'')), str(data.get("n_exp",'')), str(data.get("date_exp",'')),
                                    str(data.get("coin_exp",'')), str(data.get("coin_exp_izn",'')), str(data.get("date_napr_sto",'')), str(data.get("N_sto",'')),str(data.get("name_sto",'')),
                                    str(data.get("date_sto",'')), str(data.get("date_pret",'')), str(data.get("fio_k",''))],
                                    "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/8. Заявление фин. омбуцмену СТО отказала.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену.docx")
            elif data['vibor'] == 'vibor3':
                replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}","{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", "{{ Телефон_представителя }}","{{ Серия_полиса }}", "{{ Номер_полиса }}","{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата_заявления_форма6 }}",
                                "{{ Nакта_осмотра }}", "{{ Выплата_ОСАГО }}","{{ Дата_ответ_страховой }}", "{{ Организация }}",
                                "{{ Номер_экспертизы }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}", "{{ Утрата_стоимости }}", "{{ Разница }}", "{{ Дата_претензии }}","{{ ФИОк }}"],
                                [str(data.get("date_ombuc",'')), str(data.get("insurance",'')),str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),
                                    str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                    str(data.get("number_not",'')), str(data.get("seria_insurance",'')), str(data.get("number_insurance",'')), str(data.get("date_insurance",'')),
                                    str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),
                                    str(data.get("date_ins_pod",'')), str(data.get("Na_ins",'')), str(data.get('coin_osago') or '0'),str(data.get("date_ins_otv",'')),
                                    str(data.get("org_exp",'')), str(data.get("n_exp",'')),str(data.get("date_exp",'')),
                                    str(data.get("coin_exp",'0')), str(data.get("coin_exp_izn",'0')), str(float(data.get("coin_exp",'0'))+float(data.get("coin_exp_izn",'0'))), str(data.get("date_pret",'')), str(data.get("fio_k",''))],
                                    "Шаблоны/1. ДТП/1. На ремонт/У страховой нет СТО/Омбуцмен у страховой нет СТО.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену.docx")
            elif data['vibor'] == 'vibor4':
                replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}","{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", "{{ Телефон_представителя }}","{{ Серия_полиса }}", "{{ Номер_полиса }}","{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                                "{{ Nв_страховую }}", "{{ Организация }}","{{ Nэкспертизы }}", "{{ Дата_экспертизы }}",
                                "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ Название_СТО }}",
                                "{{ Дата_претензии }}", "{{ Город_СТО }}", "{{ Разница }}", "{{ ФИОк }}"],
                                [str(data.get("date_ombuc",'')), str(data.get("insurance",'')),str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),
                                    str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                    str(data.get("number_not",'')), str(data.get("seria_insurance",'')), str(data.get("number_insurance",'')), str(data.get("date_insurance",'')),
                                    str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),
                                    str(data.get("date_ins_pod",'')), str(data.get("Nv_ins",'')), str(data.get("org_exp",'')), str(data.get("n_exp",'')), str(data.get("date_exp",'')),
                                    str(data.get("coin_exp",'')), str(data.get("coin_exp_ins",'')),str(data.get("date_napr_sto",'')),str(data.get("N_sto",'')),str(data.get("name_sto",'')),
                                    str(data.get("date_pret",'')), str(data.get("city_sto",'')), str(float(data.get("coin_exp",'0'))+float(data.get("coin_exp_izn",'0'))), str(data.get("fio_k",''))],
                                    "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО свыше 50км/7. Заявление фин. омбудсмену СТО свыше 50 км.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену.docx")
            elif data['vibor'] == 'vibor5':
                replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}","{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", "{{ Телефон_представителя }}","{{ Серия_полиса }}", "{{ Номер_полиса }}","{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата_заявления_форма6 }}",
                                "{{ Nв_страховую }}", "{{ Дата_СТО_30 }}","{{ Nакта_осмотра }}", "{{ Выплата_ОСАГО }}",
                                "{{ Организация }}", "{{ Номер_экспертизы }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}",
                                "{{ Утрата_стоимости }}", "{{ Разница }}", "{{ ФИОк }}"],
                                [str(data.get("date_ombuc",'')), str(data.get("insurance",'')),str(data.get("city",'')), str(data.get("fio",'')), str(data.get("date_of_birth",'')),
                                    str(data.get("seria_pasport",'')), str(data.get("number_pasport",'')),str(data.get("where_pasport",'')), str(data.get("when_pasport",'')),
                                    str(data.get("number_not",'')), str(data.get("seria_insurance",'')), str(data.get("number_insurance",'')), str(data.get("date_insurance",'')),
                                    str(data.get("date_dtp",'')), str(data.get("time_dtp",'')), str(data.get("address_dtp",'')), str(data.get("marks",'')), str(data.get("car_number",'')),
                                    str(data.get("date_ins_pod",'')), str(data.get("Nv_ins",'')), str(data.get("date_istch_rem",'')),str(data.get("Na_ins",'')),
                                    str(data.get('coin_osago') or '0'), str(data.get("org_exp",'')),str(data.get("n_exp",'')),str(data.get("date_exp",'')),
                                    str(data.get("coin_exp",'0')), str(data.get("coin_exp_izn",'0')), str(float(data.get("coin_exp",'0'))+float(data.get("coin_exp_izn",'0'))-float(data.get('coin_osago') or '0')), str(data.get("fio_k",''))],
                                    "Шаблоны/1. ДТП/1. На ремонт/Страховая не организовала ремонт/7. Заявление фин. омбудсмену не организовали ремонт.docx",
                                    "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену.docx")
            try:
                with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену.docx", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
                    bot.send_document(message.chat.id, doc, caption="📋 Заявление финансовому омбудсмену", reply_markup = keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")

            notify_isk_department(data["client_id"], data["fio"])
            client_user_id = user_temp_data[user_id].get('client_user_id')
            if client_user_id and str(client_user_id) != '8572367590':
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("◀️ Перейти к договору", callback_data=f"view_contract_{data['client_id']}")) 
                    bot.send_message(
                        int(client_user_id),
                        "✅ Заявление к Фин.омбудсмену составлено, ознакомиться с ним можно в личном кабинете",
                        reply_markup = keyboard
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления клиенту: {e}")
            if user_id in user_temp_data:
                if 'ombudsmen_data' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['ombudsmen_data']
                if 'client_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_id']
                if 'client_user_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_user_id']

        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"pret_view_contract_{data['client_id']}")) 
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ответа на претензию в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_pret_otv, data, user_message_id)

    def notify_isk_department(client_id, fio):
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT user_id FROM admins 
                        WHERE admin_value = 'Исковой отдел'
                    """)
                    directors = cursor.fetchall()
                    
                    notified_count = 0
                    for director in directors:
                        try:
                            keyboard = types.InlineKeyboardMarkup()
                            keyboard.add(types.InlineKeyboardButton(
                                "📄 Перейти к договору", 
                                callback_data=f"isk_view_contract_{client_id}"
                            ))
                            keyboard.add(types.InlineKeyboardButton(
                                "🏠 Главное меню", 
                                callback_data="callback_start"
                            ))
                            
                            bot.send_message(
                                int(director[0]),
                                f"✅ Заявление к финансовому омбуцмену составлено\n\n"
                                f"📋 Договор: {client_id}\n"
                                f"👤 Клиент: {fio}",
                                reply_markup=keyboard
                            )
                            notified_count += 1
                            
                        except Exception as e:
                            print(f"Не удалось уведомить Исковой отдел {director[0]}: {e}")
                    
                    print(f"Уведомлено сотрудников Искового отдела: {notified_count}/{len(directors)}")
        except Exception as e:
                print(f"Ошибка уведомления Претензионный отдел: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "pret_finances")
    @prevent_double_click(timeout=3.0)
    def pret_finances_handler(call):
        """Финансы претензионного отдела"""
        pret_id = call.from_user.id
        db = DatabaseManager()
        balance_data = db.get_pret_balance(str(pret_id))
        monthly_earning = db.get_pret_monthly_earning(str(pret_id))
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("💸 Заказать вывод", callback_data="request_pret_withdrawal"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💰 Финансы\n\n"
                f"📊 Ваш заработок за месяц: {monthly_earning:.2f} руб.\n"
                f"💵 Баланс: {balance_data['balance']:.2f} руб.",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "request_pret_withdrawal")
    @prevent_double_click(timeout=3.0)
    def request_pret_withdrawal_handler(call):
        """Запрос на вывод средств претензионным отделом"""
        pret_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💸 Введите сумму для вывода:"
        )
        
        bot.register_next_step_handler(call.message, process_pret_withdrawal_amount, pret_id, call.message.message_id)

    def process_pret_withdrawal_amount(message, pret_id, prev_message_id):
        """Обработка суммы вывода претензионного отдела"""
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
            bot.register_next_step_handler(msg, process_pret_withdrawal_amount, pret_id, msg.message_id)
            return
        
        if amount <= 0:
            msg = bot.send_message(
                message.chat.id,
                "❌ Сумма должна быть положительной. Введите снова:"
            )
            bot.register_next_step_handler(msg, process_pret_withdrawal_amount, pret_id, msg.message_id)
            return
        
        balance_data = db.get_pret_balance(str(pret_id))
        if amount > balance_data['balance']:
            msg = bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств. Ваш баланс: {balance_data['balance']:.2f} руб.\n"
                f"Введите сумму не больше баланса:"
            )
            bot.register_next_step_handler(msg, process_pret_withdrawal_amount, pret_id, msg.message_id)
            return
        
        # Создаем заявку
        pret_data = get_admin_from_db_by_user_id(pret_id)
        pret_fio = pret_data.get('fio', 'Претензионный отдел')
        
        withdrawal_id = db.create_withdrawal_request(str(pret_id), pret_fio, amount)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        if withdrawal_id:
            bot.send_message(
                message.chat.id,
                f"✅ Заявка на вывод {amount:.2f} руб. отправлена на подпись.",
                reply_markup=keyboard
            )
            
            # Уведомляем всех бухгалтеров
            notify_directors_about_withdrawal(bot, pret_fio, amount)
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

def cleanup_messages(bot, chat_id, message_id, count):
    """Удаляет последние N сообщений"""
    for i in range(count):
        try:
            bot.delete_message(chat_id, message_id - i)
        except:
            pass