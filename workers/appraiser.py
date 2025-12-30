from telebot import types
import psycopg2.extras
import json
import os
from PIL import Image
import logging
from datetime import datetime
from database import (
    DatabaseManager,
    get_client_from_db_by_client_id,
    get_admin_from_db_by_user_id
)
import threading
import time
from functools import wraps
from word_utils import create_fio_data_file
active_callbacks = {}
callback_lock = threading.Lock()
db = DatabaseManager()


def setup_appraiser_handlers(bot, user_temp_data, upload_sessions):
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
    @bot.callback_query_handler(func=lambda call: call.data == "btn_search_database_appraiser")
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
        bot.register_next_step_handler(message, search_all_clients_handler_appraiser, user_message_id, call.from_user.id, user_temp_data)

    def search_all_clients_handler_appraiser(message, user_message_id, user_id, user_temp_data):
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
            bot.register_next_step_handler(msg, search_all_clients_handler_appraiser, msg.message_id, user_id, user_temp_data)
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
                btn_callback = f"appraiser_view_contract_{client['client_id']}"
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
            
            if len(results) > 10:
                response += f"... и еще {len(results) - 10} клиентов"
            
            keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database_appraiser"))
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.send_message(message.chat.id, response, reply_markup=keyboard)
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка поиска: {e}")
            print(f"Ошибка поиска: {e}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("appraiser_view_contract_"))
    @prevent_double_click(timeout=3.0)
    def appraiser_view_contract_handler(call):
        """Просмотр договора администратором/директором"""
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        client_id = call.data.replace("appraiser_view_contract_", "")
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
        
        status = contract.get('status', '')
        print(contract_data.get('calculation', ''))
        if contract_data.get('calculation', '') == '' or contract_data.get('calculation', '') == None:
            keyboard.add(types.InlineKeyboardButton("💰 Загрузить калькуляцию", callback_data=f"download_calc_{client_id}"))

        keyboard.add(types.InlineKeyboardButton("📤 Загрузить документы", callback_data="download_docs"))
        keyboard.add(types.InlineKeyboardButton("📋 Просмотр данных", callback_data="view_db"))
        keyboard.add(types.InlineKeyboardButton("📂 Просмотреть документы", callback_data="view_client_documents"))
        keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database_appraiser"))

        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        bot.send_message(
            chat_id=call.message.chat.id,
            text=contract_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('download_calc_'))
    def handle_download_calc(call):
        client_id = call.data.split('_')[-1]
        chat_id = call.message.chat.id
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        data = get_client_from_db_by_client_id(client_id)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"appraiser_view_contract_{client_id}"))
        msg = bot.send_message(
            chat_id,
            "Введите дату экспертного заключения в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, date_exp, data, msg.message_id)


    def date_exp(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp": message.text})
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_exp"))
            message = bot.send_message(message.chat.id, text="Введите номер экспертного заключения", reply_markup = keyboard)
            user_message_id = message.message_id
            bot.register_next_step_handler(message, n_exp, data, user_message_id)

        except ValueError:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"appraiser_view_contract_{data['client_id']}"))
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения в формате ДД.ММ.ГГГГ", reply_markup = keyboard)
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_exp, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_date_exp'))
    def handle_back_to_date_exp(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        try:
            bot.delete_message(user_id, call.message.message_id)
        except:
            pass
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=f"appraiser_view_contract_{data['client_id']}"))
        msg = bot.send_message(
            user_id,
            "Введите дату экспертного заключения в формате ДД.ММ.ГГГГ",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, date_exp, data, msg.message_id)

    def n_exp(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({"n_exp": message.text})
        user_temp_data[user_id] = data
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_n_exp"))
        message = bot.send_message(message.chat.id, text="Введите цену по экспертизе без учета износа в рублях", reply_markup = keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_n_exp'))
    def handle_back_to_n_exp(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        try:
            bot.delete_message(user_id, call.message.message_id)
        except:
            pass
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_date_exp"))
        message = bot.send_message(user_id, text="Введите номер экспертного заключения", reply_markup = keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, n_exp, data, user_message_id)

    def coin_exp(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp"))
            data.update({"coin_exp": message.text})
            user_temp_data[user_id]=data
            msg = bot.send_message(
                message.chat.id,
                text="Введите стоимость утраты товарной стоимости в рублях", reply_markup = keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp_izn, data, user_message_id)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_n_exp"))
            msg = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену по экспертизе без учета износа в рублях",
                reply_markup = keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp, data, user_message_id)

    def coin_exp_izn(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_exp_izn": message.text})
            data_admin = get_admin_from_db_by_user_id(user_id)
            data.update({"org_exp": data_admin['org']})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                print(data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            create_fio_data_file(data)
            user_temp_data[user_id] = data
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📸 Загрузить фото", callback_data="upload_calc_photos"))
            keyboard.add(types.InlineKeyboardButton("📄 Загрузить PDF", callback_data="upload_calc_pdf"))
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp"))

            bot.send_message(
                user_id,
                "Выберите формат загрузки калькуляции:",
                reply_markup=keyboard
            )
            
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp"))
            msg = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость утраты товарной стоимости в рублях",
                reply_markup = keyboard
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, coin_exp, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_coin_exp'))
    def handle_back_to_coin_exp(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        try:
            bot.delete_message(user_id, call.message.message_id)
        except:
            pass
        data = user_temp_data[user_id]
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_n_exp"))
        message = bot.send_message(user_id, text="Введите цену по экспертизе без учета износа в рублях", reply_markup = keyboard)
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "upload_calc_photos")
    def handle_upload_calc_photos(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # Инициализация сессии загрузки
        upload_sessions[user_id] = {
            'client_id': data['client_id'],
            'photos': [],
            'message_id': None
        }
        
        # Отправляем сообщение с инструкцией
        msg = bot.send_message(
            user_id,
            "📸 Загрузите одну или несколько фотографий калькуляции\n\n"
            "После загрузки всех фото нажмите кнопку 'Завершить загрузку'",
            reply_markup=create_upload_keyboard()
        )
        
        # Сохраняем ID сообщения для последующего редактирования
        upload_sessions[user_id]['message_id'] = msg.message_id

    @bot.callback_query_handler(func=lambda call: call.data == "upload_calc_pdf")
    def handle_upload_calc_pdf(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp_format"))
        
        msg = bot.send_message(
            user_id,
            "📄 Загрузите PDF файл с калькуляцией:",
            reply_markup=keyboard
        )
        
        bot.register_next_step_handler(msg, process_calc_pdf, data, msg.message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_coin_exp_format")
    def handle_back_to_coin_exp_format(call):
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        user_id = call.from_user.id
        
        try:
            bot.delete_message(user_id, call.message.message_id)
        except:
            pass
        
        data = user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📸 Загрузить фото", callback_data="upload_calc_photos"))
        keyboard.add(types.InlineKeyboardButton("📄 Загрузить PDF", callback_data="upload_calc_pdf"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp"))
        
        bot.send_message(
            user_id,
            "Выберите формат загрузки калькуляции:",
            reply_markup=keyboard
        )    
    def process_calc_pdf(message, data, user_message_id):
        user_id = message.from_user.id
        
        try:
            bot.delete_message(message.chat.id, user_message_id)
        except:
            pass
        
        # Проверяем, что это документ
        if not message.document:
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp_format"))
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Пожалуйста, отправьте файл, а не другой тип сообщения.\n"
                "📄 Загрузите PDF файл с калькуляцией:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_calc_pdf, data, msg.message_id)
            return
        
        # Проверяем расширение файла
        file_name = message.document.file_name.lower()
        if not (file_name.endswith('.pdf') or file_name.endswith('.PDF')):
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp_format"))
            
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат файла. Требуется PDF.\n"
                "📄 Загрузите PDF файл с калькуляцией:",
                reply_markup=keyboard
            )
            bot.register_next_step_handler(msg, process_calc_pdf, data, msg.message_id)
            return
        
        try:
            # Скачиваем файл
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем PDF
            docs_path = f"clients/{data['client_id']}/Документы"
            os.makedirs(docs_path, exist_ok=True)
            pdf_path = os.path.join(docs_path, "Калькуляция.pdf")
            
            with open(pdf_path, 'wb') as pdf_file:
                pdf_file.write(downloaded_file)
            
            # Удаляем сообщение пользователя с файлом
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            # Обновляем данные в БД
            data.update({'calculation': 'Загружена'})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            create_fio_data_file(data)
            # Начисляем оценщику за калькуляцию
            try:
                db_instance = DatabaseManager()
                with db_instance.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO appraiser_finances (appraiser_id, balance, total_earned)
                            VALUES (%s, 3000, 3000)
                            ON CONFLICT (appraiser_id) DO UPDATE
                            SET balance = appraiser_finances.balance + 3000,
                                total_earned = appraiser_finances.total_earned + 3000,
                                last_updated = CURRENT_TIMESTAMP
                        """, (str(user_id),))
                        
                        cursor.execute("""
                            INSERT INTO appraiser_earnings_history (appraiser_id, client_id, amount)
                            VALUES (%s, %s, 3000)
                        """, (str(user_id), data['client_id']))
                        
                        conn.commit()
                        print(f"✅ Начислено 3000 руб оценщику {user_id} за калькуляцию {data['client_id']}")
            except Exception as e:
                print(f"❌ Ошибка начисления оценщику: {e}")
                import traceback
                traceback.print_exc()
            
            # Отправляем подтверждение
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(user_id, data['client_id'])))
            
            bot.send_message(
                message.chat.id,
                "✅ Калькуляция успешно сохранена!",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logging.error(f"Error saving PDF: {e}")
            import traceback
            traceback.print_exc()
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_coin_exp_format"))
            
            bot.send_message(
                message.chat.id,
                "❌ Ошибка при сохранении PDF файла",
                reply_markup=keyboard
            )    
    def create_upload_keyboard():
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_upload"))
        return keyboard

    @bot.callback_query_handler(func=lambda call: call.data == 'finish_upload')
    def handle_finish_upload(call):
        chat_id = call.message.chat.id
        
        if chat_id not in upload_sessions or not upload_sessions[chat_id]['photos']:
            bot.answer_callback_query(call.id, "❌ Нет загруженных фото")
            return
        
        session = upload_sessions[chat_id]
        
        try:
            # Создаем PDF из фото
            create_calculation_pdf(session['photos'], session['client_id'])
            contract = get_client_from_db_by_client_id(upload_sessions[chat_id]['client_id'])
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
            data.update({'calculation': 'Загружена'})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            create_fio_data_file(data)
            # Удаляем сообщение с кнопкой
            bot.delete_message(chat_id, session['message_id'])
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Вернуться к договору", callback_data=get_contract_callback(chat_id, upload_sessions[chat_id]['client_id'])))
            # Отправляем подтверждение
            # Начисляем оценщику за калькуляцию
            try:
                db_instance = DatabaseManager()
                with db_instance.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Проверяем/создаем запись финансов
                        cursor.execute("""
                            INSERT INTO appraiser_finances (appraiser_id, balance, total_earned)
                            VALUES (%s, 3000, 3000)
                            ON CONFLICT (appraiser_id) DO UPDATE
                            SET balance = appraiser_finances.balance + 3000,
                                total_earned = appraiser_finances.total_earned + 3000,
                                last_updated = CURRENT_TIMESTAMP
                        """, (str(call.from_user.id),))
                        
                        # Записываем в историю начислений
                        cursor.execute("""
                            INSERT INTO appraiser_earnings_history (appraiser_id, client_id, amount)
                            VALUES (%s, %s, 3000)
                        """, (str(call.from_user.id), upload_sessions[chat_id]['client_id']))
                        
                        conn.commit()
                        print(f"✅ Начислено 3000 руб оценщику {call.from_user.id} за калькуляцию {upload_sessions[chat_id]['client_id']}")
            except Exception as e:
                print(f"❌ Ошибка начисления оценщику: {e}")
                import traceback
                traceback.print_exc()

            bot.send_message(
                chat_id,
                f"✅ Калькуляция успешно сохранена!\n"
                f"Загружено фото: {len(session['photos'])}",
                reply_markup = keyboard
            )
            
        except Exception as e:
            logging.error(f"Error creating PDF: {e}")
            bot.send_message(chat_id, "❌ Ошибка при создании PDF файла")
        
        # Очищаем сессию
        del upload_sessions[chat_id]
        bot.answer_callback_query(call.id)

    # Обработчик для фото через lambda с проверкой состояния
    @bot.message_handler(
        content_types=['photo'],
        func=lambda message: message.chat.id in upload_sessions and 'photos' in upload_sessions.get(message.chat.id, {})
    )
    def handle_calc_photo(message):
        chat_id = message.chat.id
        print(1)
        # Проверяем, что сессия все еще активна
        if chat_id not in upload_sessions:
            return
            
        session = upload_sessions[chat_id]
        
        try:
            # Получаем фото максимального качества
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем фото во временную папку
            temp_path = f"temp_calc_{chat_id}_{len(session['photos'])}.jpg"
            with open(temp_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            # Добавляем путь к фото в сессию
            session['photos'].append(temp_path)
            
            # Удаляем сообщение пользователя с фото
            try:
                bot.delete_message(chat_id, message.message_id)
            except:
                pass
            
            # Обновляем сообщение бота
            try:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=session['message_id'],
                    text=f"📸 Фото загружено ({len(session['photos'])} фото)\n\n"
                        "Продолжайте загружать фото или нажмите 'Завершить загрузку'",
                    reply_markup=create_upload_keyboard()
                )
            except Exception as e:
                print(f"Ошибка обновления сообщения: {e}")
                
        except Exception as e:
            logging.error(f"Error processing photo: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(chat_id, "❌ Ошибка при загрузке фото")
    
    @bot.callback_query_handler(func=lambda call: call.data == "appraiser_finances")
    @prevent_double_click(timeout=3.0)
    def appraiser_finances_handler(call):
        """Финансы оценщика"""
        appraiser_id = call.from_user.id
        db = DatabaseManager()
        balance_data = db.get_appraiser_balance(str(appraiser_id))
        monthly_earning = db.get_appraiser_monthly_earning(str(appraiser_id))
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("💸 Заказать вывод", callback_data="request_appraiser_withdrawal"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="callback_start"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💰 Финансы\n\n"
                f"📊 Ваш заработок за месяц: {monthly_earning:.2f} руб.\n"
                f"💵 Баланс: {balance_data['balance']:.2f} руб.",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == "request_appraiser_withdrawal")
    @prevent_double_click(timeout=3.0)
    def request_appraiser_withdrawal_handler(call):
        """Запрос на вывод средств оценщиком"""
        appraiser_id = call.from_user.id
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💸 Введите сумму для вывода:"
        )
        
        bot.register_next_step_handler(call.message, process_appraiser_withdrawal_amount, appraiser_id, call.message.message_id)

    def process_appraiser_withdrawal_amount(message, appraiser_id, prev_message_id):
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
            bot.register_next_step_handler(msg, process_appraiser_withdrawal_amount, appraiser_id, msg.message_id)
            return
        
        if amount <= 0:
            msg = bot.send_message(
                message.chat.id,
                "❌ Сумма должна быть положительной. Введите снова:"
            )
            bot.register_next_step_handler(msg, process_appraiser_withdrawal_amount, appraiser_id, msg.message_id)
            return
        
        balance_data = db.get_appraiser_balance(str(appraiser_id))
        if amount > balance_data['balance']:
            msg = bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств. Ваш баланс: {balance_data['balance']:.2f} руб.\n"
                f"Введите сумму не больше баланса:"
            )
            bot.register_next_step_handler(msg, process_appraiser_withdrawal_amount, appraiser_id, msg.message_id)
            return
        
        # Создаем заявку
        appraiser_data = get_admin_from_db_by_user_id(appraiser_id)
        appraiser_fio = appraiser_data.get('fio', 'Оценщик')
        
        withdrawal_id = db.create_withdrawal_request(str(appraiser_id), appraiser_fio, amount)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
        
        if withdrawal_id:
            bot.send_message(
                message.chat.id,
                f"✅ Заявка на вывод {amount:.2f} руб. отправлена на подпись.",
                reply_markup=keyboard
            )
            
            # Уведомляем всех директоров
            notify_directors_about_withdrawal(bot, appraiser_fio, amount)
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
    @bot.callback_query_handler(func=lambda call: call.data.startswith("appraiser_calc"))
    @prevent_double_click(timeout=3.0)
    def appraiser_calc_handler(call):
        """Список договоров с подтвержденной оплатой для оценщика"""
        user_id = call.from_user.id
        
        # Парсим страницу из callback_data (например, appraiser_calc_0)
        if "_" in call.data and call.data.split("_")[-1].isdigit():
            page = int(call.data.split("_")[-1])
        else:
            page = 0
        
        # Получаем договоры с подтвержденной оплатой
        from database import DatabaseManager
        db = DatabaseManager()
        
        try:
            with db.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT DISTINCT c.client_id, c.fio, c.created_at, c.status, c.accident
                        FROM clients c
                        INNER JOIN pending_approvals pa ON c.client_id = pa.client_id
                        WHERE pa.document_type = 'payment' 
                        AND pa.status = 'approved'
                        AND (c.calculation IS NULL OR c.calculation != 'Загружена')
                        ORDER BY c.created_at DESC
                    """)
                    all_contracts = cursor.fetchall()
        except Exception as e:
            print(f"Ошибка получения договоров для оценщика: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка загрузки договоров", show_alert=True)
            return
        
        if not all_contracts:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📋 Нет договоров с подтвержденной оплатой",
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
        text = f"🏷️ <b>Ожидают калькуляции</b>\n"
        text += f"Договоров с оплатой: {total_contracts} \n\n"
        
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
                callback_data=f"appraiser_view_contract_{contract['client_id']}"
            )
            buttons.append(btn)
            
            if len(buttons) == 5 or i == start_idx + len(page_contracts):
                keyboard.row(*buttons)
                buttons = []
        
        # Навигация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("◀️ Назад", callback_data=f"appraiser_calc_{page - 1}"))
        
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("Далее ▶️", callback_data=f"appraiser_calc_{page + 1}"))
        
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
    def create_calculation_pdf(photo_paths, client_id):
        """Создает PDF файл из загруженных фото"""
        # Создаем папки если не существуют
        docs_path = f"clients/{client_id}/Документы"
        os.makedirs(docs_path, exist_ok=True)
        
        pdf_path = os.path.join(docs_path, "Калькуляция.pdf")
        
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
                logging.error(f"Error opening image {photo_path}: {e}")
        
        if images:
            # Сохраняем как PDF
            images[0].save(
                pdf_path, 
                "PDF", 
                resolution=100.0, 
                save_all=True, 
                append_images=images[1:]
            )

    def notify_pretension_department(client_id, fio):
        db_instance = DatabaseManager()
        try:
            with db_instance.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT user_id FROM admins 
                        WHERE admin_value = 'Претензионный отдел'
                    """)
                    directors = cursor.fetchall()
                    
                    notified_count = 0
                    for director in directors:
                        try:
                            keyboard = types.InlineKeyboardMarkup()
                            keyboard.add(types.InlineKeyboardButton(
                                "📄 Перейти к договору", 
                                callback_data=f"pret_view_contract_{client_id}"
                            ))
                            keyboard.add(types.InlineKeyboardButton(
                                "🏠 Главное меню", 
                                callback_data="callback_start"
                            ))
                            
                            bot.send_message(
                                int(director[0]),
                                f"✅ Калькуляция загружена\n\n"
                                f"📋 Договор: {client_id}\n"
                                f"👤 Клиент: {fio}",
                                reply_markup=keyboard
                            )
                            notified_count += 1
                            
                        except Exception as e:
                            print(f"Не удалось уведомить Претензионный отдел {director[0]}: {e}")
                    
                    print(f"Уведомлено сотрудников Претензионного отдела: {notified_count}/{len(directors)}")
        except Exception as e:
                print(f"Ошибка уведомления Претензионный отдел: {e}")
def cleanup_messages(bot, chat_id, message_id, count):
    """Удаляет последние N сообщений"""
    for i in range(count):
        try:
            bot.delete_message(chat_id, message_id - i)
        except:
            pass

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