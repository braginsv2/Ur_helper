import threading
import time
from datetime import datetime, timedelta
from database import DatabaseManager, get_admin_from_db_by_user_id

db = DatabaseManager()

def check_time_based_messages(bot):
    """Фоновый процесс для проверки времени и отправки сообщений"""
    while True:
        try:
            check_2_weeks_after_application(bot)
            check_20_days_after_application(bot)
            time.sleep(3600)  # Проверяем каждый час
        except Exception as e:
            print(f"Ошибка в scheduler: {e}")
            time.sleep(3600)

def check_2_weeks_after_application(bot):
    """Проверка 2 недели после заполнения заявления в страховую"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Ищем договоры, где заявление заполнено 14+ дней назад
                cursor.execute("""
    SELECT client_id, user_id, date_ins_pod 
    FROM clients 
    WHERE date_ins_pod IS NOT NULL 
    AND date_ins_pod != ''
    AND status = 'Отправлен запрос в страховую'
    AND (data_json::jsonb->>'dop_osm_14_days_asked' IS NULL 
         OR data_json::jsonb->>'dop_osm_14_days_asked' = 'No')
""")
                
                contracts = cursor.fetchall()
                
                for contract in contracts:
                    client_id, user_id, date_ins_pod = contract
                    
                    try:
                        # Парсим дату
                        date_obj = datetime.strptime(date_ins_pod, "%d.%m.%Y")
                        print(date_obj)
                        days_passed = (datetime.now() - date_obj).days
                        print(days_passed)
                        # Если прошло 14+ дней
                        if days_passed >= 14:
                            # Получаем информацию о клиенте и агенте
                            cursor.execute("""
                                SELECT agent_id, fio 
                                FROM clients 
                                WHERE client_id = %s
                            """, (client_id,))
                            client_info = cursor.fetchone()
                            
                            agent_id = client_info[0] if client_info else None
                            client_fio = client_info[1] if client_info else "клиента"
                            
                            # Если есть agent_id и он отличается от user_id - значит регистрировал агент
                            if agent_id and str(agent_id) != str(user_id):
                                # Отправляем сообщение агенту (без вопроса)
                                from telebot import types
                                keyboard = types.InlineKeyboardMarkup()
                                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                                try:
                                    bot.send_message(
                                        int(agent_id),
                                        f"ℹ️ Прошло 14 дней после составления заявления в страховую по договору номер {client_id} для {client_fio}",
                                        reply_markup=keyboard
                                    )
                                except:
                                    pass    
                            else:
                                # Клиент сам зарегистрировался - отправляем вопрос клиенту
                                from telebot import types
                                keyboard = types.InlineKeyboardMarkup()
                                btn_yes = types.InlineKeyboardButton("✅ Да", callback_data=f"dop_osm_yes_{client_id}")
                                btn_no = types.InlineKeyboardButton("❌ Нет", callback_data=f"dop_osm_no_{client_id}")
                                keyboard.add(btn_yes, btn_no)
                                try:
                                    bot.send_message(
                                        int(user_id),
                                        f"❓ Прошло 2 недели после подачи заявления в страховую.\n\n"
                                        f"Необходим ли доп осмотр автомобиля?",
                                        reply_markup=keyboard
                                    )
                                    print(f"Отправлено сообщение о доп осмотре клиенту {user_id}")
                                except:
                                    pass
                            
                            # Отмечаем что спросили
                            cursor.execute("""
                                UPDATE clients 
                                SET data_json = jsonb_set(
                                    COALESCE(data_json::jsonb, '{}'::jsonb),
                                    '{dop_osm_14_days_asked}',
                                    '"Yes"'
                                )
                                WHERE client_id = %s
                            """, (client_id,))
                            conn.commit()
                            
                            print(f"Отправлено сообщение о доп осмотре клиенту {user_id}")
                    except Exception as e:
                        print(f"Ошибка обработки договора {client_id}: {e}")
    except Exception as e:
        print(f"Ошибка в check_2_weeks_after_application: {e}")

def check_20_days_after_application(bot):
    """Проверка 20 дней после заполнения заявления в страховую"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Ищем договоры, где заявление заполнено 20+ дней назад
                cursor.execute("""
                    SELECT client_id, user_id, date_ins_pod 
                    FROM clients 
                    WHERE date_ins_pod IS NOT NULL 
                    AND date_ins_pod != ''
                    AND status = 'Отправлен запрос в страховую'
                    AND (data_json::jsonb->>'answer_20_days_asked' IS NULL 
                         OR data_json::jsonb->>'answer_20_days_asked' = 'No')
                """)
                
                contracts = cursor.fetchall()
                
                for contract in contracts:
                    client_id, user_id, date_ins_pod = contract
                    
                    try:
                        # Парсим дату
                        date_obj = datetime.strptime(date_ins_pod, "%d.%m.%Y")
                        days_passed = (datetime.now() - date_obj).days
                        
                        # Если прошло 20+ дней
                        if days_passed >= 20:
                            # Получаем информацию о клиенте и агенте
                            cursor.execute("""
                                SELECT agent_id, fio 
                                FROM clients 
                                WHERE client_id = %s
                            """, (client_id,))
                            client_info = cursor.fetchone()
                            
                            agent_id = client_info[0] if client_info else None
                            client_fio = client_info[1] if client_info else "клиента"
                            
                            # Если есть agent_id и он отличается от user_id - значит регистрировал агент
                            if agent_id and str(agent_id) != str(user_id):
                                # Отправляем сообщение агенту (без вопроса)
                                from telebot import types
                                keyboard = types.InlineKeyboardMarkup()
                                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                                try:
                                    bot.send_message(
                                        int(agent_id),
                                        f"ℹ️ Прошло 20 дней после составления заявления в страховую по договору номер {client_id} для {client_fio}",
                                        reply_markup=keyboard
                                    )
                                except:
                                    pass
                            else:
                                # Клиент сам зарегистрировался - отправляем вопрос клиенту
                                from telebot import types
                                keyboard = types.InlineKeyboardMarkup()
                                btn_yes = types.InlineKeyboardButton("✅ Есть ответ", callback_data=f"answer_yes_{client_id}")
                                btn_no = types.InlineKeyboardButton("❌ Нет ответа", callback_data=f"answer_no_{client_id}")
                                btn_net_osago = types.InlineKeyboardButton("📋 У виновника ДТП Нет ОСАГО", callback_data=f"NoOsago_prod_{client_id}")
                                keyboard.add(btn_yes, btn_no)
                                keyboard.add(btn_net_osago)
                                try:
                                    bot.send_message(
                                        int(user_id),
                                        f"❓ Прошло 20 дней после подачи заявления в страховую.\n\n"
                                        f"Есть ли ответ от страховой?",
                                        reply_markup=keyboard
                                    )
                                except:
                                    pass
                                print(f"Отправлено сообщение об ответе страховой клиенту {user_id}")
                            
                            # Отмечаем что спросили
                            cursor.execute("""
                                UPDATE clients 
                                SET data_json = jsonb_set(
                                    COALESCE(data_json::jsonb, '{}'::jsonb),
                                    '{answer_20_days_asked}',
                                    '"Yes"'
                                )
                                WHERE client_id = %s
                            """, (client_id,))
                            conn.commit()
                            
                            print(f"Отправлено сообщение об ответе страховой клиенту {user_id}")
                    except Exception as e:
                        print(f"Ошибка обработки договора {client_id}: {e}")
    except Exception as e:
        print(f"Ошибка в check_20_days_after_application: {e}")

def start_scheduler(bot):
    """Запуск scheduler в отдельном потоке"""
    scheduler_thread = threading.Thread(target=check_time_based_messages, args=(bot,), daemon=True)
    scheduler_thread.start()
    print("✅ Scheduler запущен")