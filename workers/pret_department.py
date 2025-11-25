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
    save_client_to_db_with_id
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
        if contract.get('accident', '') == 'ДТП':
            if status == "Ожидание претензии" and doverennost_confirmed and payment_confirmed:
                keyboard.add(types.InlineKeyboardButton("📝 Составить претензию", callback_data=f"create_pretenziya_{client_id}"))
            elif status == "Составлена претензия" and doverennost_confirmed and payment_confirmed:
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
        
        if not payment_confirmed or not doverennost_confirmed:
            missing = []
            if not payment_confirmed:
                missing.append("документ об оплате")
            if not doverennost_confirmed:
                missing.append("нотариальная доверенность")
            
            bot.answer_callback_query(
                call.id, 
                f"❌ Для составления претензии необходимо загрузить: {', '.join(missing)}", 
                show_alert=True
            )
            return
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['pretenziya_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')
        if data["vibor"] == "vibor1":
            if data.get("Nv_ins", '') != '':
                msg = bot.send_message(call.message.chat.id, text="Введите дату экспертного заключения")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_exp, data, user_message_id)
            else:
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)
        elif data["vibor"] == "vibor2":
            if data.get("Nv_ins", '') != '':
                msg = bot.send_message(call.message.chat.id, text="Введите дату направления на СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
            else:
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)
        elif data["vibor"] == "vibor4":
            if data.get("Nv_ins", '') != '':
                msg = bot.send_message(call.message.chat.id, text="Введите дату направления на СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
            else:
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)

    def Nv_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({"Nv_ins": message.text})
        msg = bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

    def Na_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"Na_ins": message.text})
        msg = bot.send_message(message.chat.id, text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)
    
    def date_Na_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_Na_ins": message.text})
            if data["vibor"] == "vibor1":
                msg = bot.send_message(message.chat.id, text="Введите дату экспертного заключения (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_exp, data, user_message_id)
            elif data["vibor"] == "vibor2" or data["vibor"] == "vibor4":
                msg = bot.send_message(message.chat.id, text="Введите дату направления на СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)

    def date_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp": message.text})
            message = bot.send_message(message.chat.id, text="Введите организацию, сделавшую экспертизу".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, org_exp, data, user_message_id)

        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id)

    def org_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"org_exp": message.text})
        message = bot.send_message(message.chat.id, text="Введите цену по экспертизе без учета износа".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp, data, user_message_id)
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
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            if data.get("vibor",'') == "vibor2":
                data.update({"coin_exp_izn": message.text})
                data.update({"date_ombuc": str(get_next_business_date())})
                data.update({"status": "Составлено заявление к Фин.омбудсмену"})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
                replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}", "{{ ФИО }}", 
                        "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                        "{{ Паспорт_когда }}", "{{ Адрес }}", "{{ Телефон }}","{{ Серия_полиса }}","{{ Номер_полиса }}",
                        "{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                        "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                        "{{ Nв_страховую }}", "{{ Дата_направления_ремонт }}","{{ Номер_направления_СТО }}", "{{ СТО }}",
                        "{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ Дата_предоставления_ТС }}", "{{ Дата_принятия_претензии }}", "{{ Nпринятой_претензии }}",
                        "{{ Дата_претензии }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}","{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}",
                        "{{ ФИОк }}","{{ Организация }}", "{{ Nэкспертизы }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Город }}" ],
                        [str(data["date_ombuc"]), str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["city_birth"]),
                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                            str(data["address"]), str(data["number"]), str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_insurance"]), 
                            str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                            str(data["date_ins_pod"]), str(data["Nv_ins"]), str(data["date_napr_sto"]),str(data["N_sto"]),
                            str(data["name_sto"]), str(data["index_sto"]),str(data["address_sto"]), str(data["date_sto"]),
                            str(data["data_pret_prin"]),str(data["N_pret_prin"]),str(data["date_pret"]),str(data["bank"]),str(data["bank_account"]),
                            str(data["bank_account_corr"]),str(data["BIK"]),str(data["INN"]),str(data["fio_k"]), str(data["org_exp"]),str(data["Na_ins"]),
                            str(data["date_exp"]), str(data["coin_exp"]), str(data["coin_exp_izn"]), str(data["city"])],
                            "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/8. Заявление фин. омбуцмену СТО отказала.docx",
                            "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбуцмену СТО отказала.docx")
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбуцмену СТО отказала.docx", 'rb') as doc:
                        bot.send_document(message.chat.id, doc, caption="📋 Заявление финансовому омбудсмену", reply_markup = keyboard)
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
                notify_isk_department(data["client_id"], data["fio"])
                client_user_id = user_temp_data[user_id].get('client_user_id')
                if client_user_id:
                    try:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
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

            elif data.get("vibor",'') == "vibor4":
                data.update({"coin_exp_izn": message.text})
                data.update({"date_ombuc": str(get_next_business_date())})
                data.update({"status": "Составлено заявление к Фин.омбудсмену"})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
                replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}", "{{ ФИО }}", 
                        "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                        "{{ Паспорт_когда }}", "{{ Адрес }}", "{{ Телефон }}","{{ Серия_полиса }}","{{ Номер_полиса }}",
                        "{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                        "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                        "{{ Nв_страховую }}", "{{ Дата_направления_ремонт }}","{{ Номер_направления_СТО }}", "{{ СТО }}",
                        "{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ Дата_предоставления_ТС }}", "{{ Дата_принятия_претензии }}", "{{ Nпринятой_претензии }}",
                        "{{ Дата_претензии }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}","{{ Кор_счет_получателя }}", "{{ БИК_Банка }}", "{{ ИНН_Банка }}",
                        "{{ ФИОк }}","{{ Организация }}", "{{ Nэкспертизы }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}", "{{ С_учетом_износа }}",
                        "{{ Город }}","{{ Город_СТО }}"],
                        [str(data["date_ombuc"]), str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["city_birth"]),
                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                            str(data["address"]), str(data["number"]), str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_insurance"]), 
                            str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                            str(data["date_ins_pod"]), str(data["Nv_ins"]), str(data["date_napr_sto"]),str(data["N_sto"]),
                            str(data["name_sto"]), str(data["index_sto"]),str(data["address_sto"]), str(data["date_sto"]),
                            str(data["data_pret_prin"]),str(data["N_pret_prin"]),str(data["date_pret"]),str(data["bank"]),str(data["bank_account"]),
                            str(data["bank_account_corr"]),str(data["BIK"]),str(data["INN"]),str(data["fio_k"]), str(data["org_exp"]),str(data["Na_ins"]),
                            str(data["date_exp"]), str(data["coin_exp"]), str(data["coin_exp_izn"]), str(data["city"]), str(data["city_sto"])],
                            "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО свыше 50км/7. Заявление фин. омбудсмену СТО свыше 50 км.docx",
                            "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену СТО свыше 50 км.docx")
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену СТО свыше 50 км.docx", 'rb') as doc:
                        bot.send_document(message.chat.id, doc, caption="📋 Заявление финансовому омбудсмену", reply_markup = keyboard)
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
                notify_isk_department(data["client_id"], data["fio"])
                client_user_id = user_temp_data[user_id].get('client_user_id')
                if client_user_id:
                    try:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
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

            else:
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
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_osago": message.text})
            if data["vibor"] == "vibor1":
                data.update({"date_pret": str(get_next_business_date())})
                data.update({"status": 'Составлена претензия'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)

                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Организация }}", "{{ Дата_экспертизы }}", "{{ Без_учета_износа }}",
                                            "{{ С_учетом_износа }}", "{{ Выплата_ОСАГО }}","{{ Дата_претензии }}"],
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["org_exp"]), str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]),
                                                str(data["coin_osago"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                                "Шаблоны/1. ДТП/1. На ремонт/Выплата без согласования/6. Претензия в страховую Выплата без согласования.docx",
                                                "clients/"+str(data["client_id"])+"/Документы/"+"6. Претензия в страховую Выплата без согласования.docx")
                try:
                    with open(f"clients/"+str(data["client_id"])+"/Документы/"+"6. Претензия в страховую Выплата без согласования.docx", 'rb') as doc:
                        keyboard = types.InlineKeyboardMarkup()
                        btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
                        keyboard.add(btn1) 
                        bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
                keyboard = types.InlineKeyboardMarkup()
                btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
                keyboard.add(btn1)   
                bot.send_message(
                    int(data['user_id']),
                    "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                    reply_markup = keyboard
                    )

        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите сумму выплаты по ОСАГО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_osago, data, user_message_id)
    
    def date_napr_sto(message, data, user_message_id):
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
                msg = bot.send_message(message.chat.id, text="Введите название СТО")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, name_sto, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
    def data_otkaz_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_otkaz_sto": message.text})
            msg = bot.send_message(message.chat.id, text="Введите город СТО")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, city_sto, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату отказа СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
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
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)

            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}", "{{ Дата_предоставления_ТС }}",
                                            "{{ СТО }}", "{{ Дата_отказа_СТО }}","{{ Дата_претензии }}","{{ Город_СТО }}","{{ Марка_модель }}", "{{ Nавто_клиента }}"],
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["date_napr_sto"]), str(data["N_sto"]), str(data["date_sto"]),str(data["name_sto"]),
                                                str(data["data_otkaz_sto"]), str(data["date_pret"]), str(data["city"]), str(data["marks"]),str(data["car_number"])],
                                                "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО отказала/7. Претензия в страховую СТО отказала.docx",
                                                "clients/"+str(data["client_id"])+"/Документы/"+"7. Претензия в страховую СТО отказала.docx")
            try:
                with open(f"clients/"+str(data["client_id"])+"/Документы/"+"7. Претензия в страховую СТО отказала.docx", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
                    keyboard.add(btn1)
                    bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
            keyboard.add(btn1)   
            bot.send_message(
                int(data['user_id']),
                "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                reply_markup = keyboard
                )

        elif data["vibor"] == "vibor4":
            message = bot.send_message(message.chat.id, text="Введите номер направления на СТО".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, N_sto, data, user_message_id)

    def name_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"name_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите индекс СТО".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index_sto, data, user_message_id)
    def index_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите индекс СТО, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_sto, data, user_message_id)
        else:
            data.update({"index_sto": message.text})
            message = bot.send_message(message.chat.id, text="Введите адрес СТО".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_sto, data, user_message_id) 
    def address_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"address_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите город СТО".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, city_sto, data, user_message_id)
    def N_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"N_sto": message.text})
        data.update({"date_pret": str(get_next_business_date())})
        data.update({"status": 'Составлена претензия'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
        replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                            "{{ Паспорт_когда }}", "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Nакта_осмотра }}", "{{ Дата }}", "{{ Nв_страховую }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                            "{{ Адрес_ДТП }}", "{{ Дата_направления_ремонт }}", "{{ Номер_направления_СТО }}",
                                            "{{ СТО }}", "{{ Индекс_СТО }}","{{ Адрес_СТО }}","{{ Город_СТО }}","{{ Номер_направления_на_ремонт }}","{{ Дата_направления }}",
                                            "{{ Марка_модель }}", "{{ Nавто_клиента }}","{{ Дата_претензии }}"],
                                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),str(data["Na_ins"]), 
                                                str(data["date_ins"]), str(data["Nv_ins"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                                str(data["date_napr_sto"]), str(data["N_sto"]), str(data["name_sto"]),str(data["index_sto"]),str(data["address_sto"]),
                                                str(data["city_sto"]), str(data["N_sto"]), str(data["date_napr_sto"]), str(data["marks"]),str(data["car_number"]), str(data["date_pret"])],
                                                "Шаблоны/1. ДТП/1. На ремонт/Ремонт не произведен СТО свыше 50км/6. Претензия в страховую  СТО свыше 50 км.docx",
                                                "clients/"+str(data["client_id"])+"/Документы/"+"6. Претензия в страховую  СТО свыше 50 км.docx")
        try:
            with open(f"clients/"+str(data["client_id"])+"/Документы/"+"6. Претензия в страховую  СТО свыше 50 км.docx", 'rb') as doc:
                keyboard = types.InlineKeyboardMarkup()
                btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
                keyboard.add(btn1)
                bot.send_document(message.chat.id, doc, caption="📋 Претензия", reply_markup = keyboard)
        except FileNotFoundError:
            bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
        keyboard.add(btn1)   
        bot.send_message(
            int(data['user_id']),
            "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
            reply_markup = keyboard
            )

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
        if data["vibor"] == "vibor1":
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"YESprRem")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"NOprV1")
            keyboard.add(btn1)
            keyboard.add(btn2)
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Удовлетворена ли претензия?",
                reply_markup=keyboard
                )
        elif data["vibor"] == "vibor2" or data.get("vibor", "") == "vibor4":
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"YESprRem")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"NOprV2")
            keyboard.add(btn1)
            keyboard.add(btn2)
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="СТО была заменена?",
                reply_markup=keyboard
                )
    @bot.callback_query_handler(func=lambda call: call.data == "NOprV2")
    @prevent_double_click(timeout=3.0)
    def callback_ombudsmen_noV2(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]['ombudsmen_data']
        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату экспертного заключения (ДД.ММ.ГГГГ)"
                )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_exp, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "YESprRem")
    @prevent_double_click(timeout=3.0)
    def callback_ombudsmen_yes(call):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data=f"vibor2"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data=f"vibor3"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data=f"vibor4"))
        bot.edit_message_text(call.message.chat.id, call.message.message_id, "Выберите из предложенных вариантов:\n" \
        "1) Страховая компания выдала направление на ремонт, СТО отказала.\n" \
        "2) Страховая выдала направление на ремонт и ремонт произведен.\n" \
        "3) Страховая компания выдала направление на ремонт, СТО дальше 50 км.",
        reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "NOprV1")
    @prevent_double_click(timeout=3.0)
    def callback_ombudsmen_no(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]['ombudsmen_data']
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату ответа на претензию (ДД.ММ.ГГГГ)"
            )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, data_pret_otv, data, user_message_id)
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
            replace_words_in_word(["{{ Дата_обуцмен }}", "{{ Страховая }}","{{ Город }}", "{{ ФИО }}", 
                            "{{ ДР }}", "{{ Место }}","{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                            "{{ Паспорт_когда }}", "{{ Адрес }}", "{{ Телефон }}","{{ Серия_полиса }}","{{ Номер_полиса }}",
                            "{{ Дата_полиса }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                            "{{ Адрес_ДТП }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Дата }}",
                            "{{ Организация }}", "{{ Nэкспертизы }}","{{ Дата_экспертизы }}", "{{ Без_учета_износа }}",
                            "{{ С_учетом_износа }}", "{{ Дата_претензии }}", "{{ Дата_ответа_на_претензию }}", "{{ Выплата_ОСАГО }}", "{{ ФИОк }}", "{{ Nв_страховую }}"],
                            [str(data["date_ombuc"]), str(data["insurance"]),str(data["city"]), str(data["fio"]), str(data["date_of_birth"]), str(data["city_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["address"]), str(data["number"]), str(data["seria_insurance"]), str(data["number_insurance"]),str(data["date_insurance"]), 
                                str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                str(data["date_ins_pod"]), str(data["org_exp"]), str(data["Na_ins"]),str(data["date_exp"]),
                                str(data["coin_exp"]), str(data["coin_exp_izn"]),str(data["date_pret"]),
                                str(data["data_pret_otv"]), str(data["coin_osago"]),str(data["fio_k"]), str(data["Nv_ins"])],
                                "Шаблоны/1. ДТП/1. На ремонт/Выплата без согласования/7. Заявление фин. омбудсмену при выплате без согласования.docx",
                                "clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену при выплате без согласования.docx")
            try:
                with open(f"clients/"+str(data["client_id"])+"/Документы/"+"Заявление фин. омбудсмену при выплате без согласования.docx", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    bot.send_document(message.chat.id, doc, caption="📋 Заявление финансовому омбудсмену", reply_markup = keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")

            notify_isk_department(data["client_id"], data["fio"])
            client_user_id = user_temp_data[user_id].get('client_user_id')
            if client_user_id:
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
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
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ответа на претензию в формате ДД.ММ.ГГГГ".format(message.from_user))
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