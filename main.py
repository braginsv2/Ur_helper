import telebot
from telebot import types
import config
import json
import zlib
from database import DatabaseManager, get_admin_from_db_by_user_id, get_agent_fio_by_id
import base64
from client_agent import setup_client_agent_handlers
from client import setup_client_handlers
# Инициализация бота
bot = telebot.TeleBot(config.TOKEN)

# Глобальный словарь для временных данных пользователей
user_temp_data = {}

# Инициализация БД
db = DatabaseManager()
def cleanup_messages(bot, chat_id, message_id, count):
    """Удаляет последние N сообщений"""
    for i in range(count):
        try:
            bot.delete_message(chat_id, message_id - i)
        except:
            pass
@bot.message_handler(commands=['start'])
def start_handler(message):
    """Обработчик команды /start с параметрами и без"""
    user_id = message.from_user.id
    
    # Очищаем старые данные пользователя
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    # Проверяем наличие параметров в команде
    command_args = message.text.split()
    
    if len(command_args) > 1:
        param = command_args[1]
        print(f"DEBUG START: Получен параметр: {param}")
        
        # Проверяем, что это ссылка-приглашение
        if param.startswith('invagent_') or param.startswith('invclient_'):
            print(f"DEBUG START: Это ссылка-приглашение!")
            is_registered = db.check_admin_exists(user_id)

            if is_registered:
                # Пользователь уже зарегистрирован
                print(f"DEBUG: Пользователь {user_id} уже зарегистрирован, загружаем данные из БД")
                
                # Парсим параметры приглашения
                parts = param.split('_', 2)
                if len(parts) < 3:
                    show_registration_button(bot, message)
                    return
                
                invite_type = parts[0]  # 'invagent' или 'invclient'
                inviter_id = parts[1]
                
                # ЗАГРУЖАЕМ ДАННЫЕ КЛИЕНТА ИЗ БД
                client_data = get_admin_from_db_by_user_id(user_id)
                
                if not client_data:
                    bot.send_message(user_id, "❌ Ошибка: данные не найдены в базе")
                    return
                
                if invite_type == 'invagent':
                    # Проверяем, не привязан ли уже клиент к другому агенту
                    with db.get_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                SELECT agent_id FROM client_agent_relationships 
                                WHERE client_user_id = %s
                            """, (user_id,))
                            existing_relationship = cursor.fetchone()
                            
                            if existing_relationship and str(existing_relationship[0]) != str(inviter_id):
                                bot.send_message(
                                    user_id,
                                    "⚠️ Вы уже привязаны к другому агенту!"
                                )
                                return
                            
                            # Сохраняем/обновляем связь клиент-агент
                            cursor.execute("""
                                INSERT INTO client_agent_relationships (client_user_id, agent_id)
                                VALUES (%s, %s)
                                ON CONFLICT (client_user_id) DO UPDATE SET agent_id = %s
                            """, (user_id, inviter_id, inviter_id))
                            conn.commit()
                    
                    # ЗАГРУЖАЕМ ВСЕ ДАННЫЕ КЛИЕНТА В user_temp_data для агента
                    agent_temp_data = {
                        'client_user_id': user_id,
                        'fio': client_data.get('fio'),
                        'fio_k': client_data.get('fio_k'),
                        'number': client_data.get('number'),
                        'city_admin': client_data.get('city_admin'),
                        'seria_pasport': client_data.get('seria_pasport'),
                        'number_pasport': client_data.get('number_pasport'),
                        'where_pasport': client_data.get('where_pasport'),
                        'when_pasport': client_data.get('when_pasport'),
                        'date_of_birth': client_data.get('date_of_birth'),
                        'city_birth': client_data.get('city_birth'),
                        'address': client_data.get('address'),
                        'index_postal': client_data.get('index_postal'),
                        'admin_value': 'Клиент_агент'
                    }
                    
                    # Сохраняем данные для агента
                    user_temp_data[int(inviter_id)] = agent_temp_data
                    
                    print(f"✅ Данные клиента загружены в user_temp_data для агента {inviter_id}")
                    print(f"   ФИО: {agent_temp_data['fio']}")
                    print(f"   Телефон: {agent_temp_data['number']}")
                    print(f"   Паспорт: {agent_temp_data['seria_pasport']} {agent_temp_data['number_pasport']}")
                    
                    # Уведомляем клиента
                    bot.send_message(
                        user_id,
                        "✅ Вы успешно привязаны к агенту!\n\n"
                        "Агент начнет заполнение договора с использованием ваших данных из профиля."
                    )
                    
                    # Уведомляем агента и даем кнопку начать заполнение
                    keyboard = types.InlineKeyboardMarkup()
                    btn_start = types.InlineKeyboardButton(
                        "📋 Начать заполнение договора", 
                        callback_data="start_agent_client_contract"
                    )
                    keyboard.add(btn_start)
                    
                    agent_fio = get_agent_fio_by_id(inviter_id)
                    bot.send_message(
                        int(inviter_id),
                        f"✅ Клиент {client_data.get('fio', 'клиент')} перешел по вашей ссылке!\n\n"
                        f"📋 Данные клиента загружены из профиля:\n"
                        f"• ФИО: {client_data.get('fio')}\n"
                        f"• Телефон: {client_data.get('number')}\n"
                        f"• Город: {client_data.get('city_admin')}\n\n"
                        f"Теперь можете начать заполнение договора.",
                        reply_markup=keyboard
                    )
                    
                    return
                
                elif invite_type == 'invclient':
                    # Клиент приглашает клиента - просто уведомляем
                    bot.send_message(
                        user_id,
                        f"✅ Вы уже зарегистрированы в системе!"
                    )
                    
                    bot.send_message(
                        int(inviter_id),
                        f"✅ Клиент {client_data.get('fio', 'клиент')} перешел по вашей ссылке приглашения!"
                    )
                    
                    from main_menu import show_main_menu
                    show_main_menu(bot, message)
                    return
            else:
                try:
                    # Формат: invagent_agentid_fioencoded или invclient_clientid_fioencoded
                    parts = param.split('_', 2)  # Разделяем только на 3 части
                    
                    print(f"DEBUG START: parts = {parts}")
                    print(f"DEBUG START: len(parts) = {len(parts)}")
                    
                    if len(parts) < 3:
                        print(f"❌ Неверный формат приглашения: {param}")
                        show_registration_button(bot, message)
                        return
                    
                    invite_type = parts[0]  # 'invagent' или 'invclient'
                    inviter_id = parts[1]
                    fio_encoded = parts[2]
                    
                    print(f"DEBUG START: invite_type = {invite_type}")
                    print(f"DEBUG START: inviter_id = {inviter_id}")
                    print(f"DEBUG START: fio_encoded = {fio_encoded}")
                    
                    # Декодируем ФИО
                    client_fio = base64.urlsafe_b64decode(fio_encoded.encode('utf-8')).decode('utf-8')
                    
                    print(f"DEBUG START: invite_type={invite_type}, inviter_id={inviter_id}, fio={client_fio}")
                    
                    # Ищем в pending_invites по ключу inviter_id_fio
                    invite_key = f"{inviter_id}_{client_fio}"
                    print(f"DEBUG START: Ищем ключ: {invite_key}")
                    print(f"DEBUG START: pending_invites keys: {user_temp_data.get('pending_invites', {}).keys()}")
                    print(invite_key)
                    print(user_temp_data)
                    pending_data = user_temp_data.get('pending_invites', {}).get(invite_key)
                    
                    if pending_data:
                        client_fio = pending_data.get('fio', '')
                        client_phone = pending_data.get('phone', '')
                        city = pending_data.get('city', '')
                        print(f"DEBUG START: Найдены данные в pending_invites:")
                        print(f"  - Телефон: {client_phone}")
                        print(f"  - Город: {city}")
                    else:
                        print(f"DEBUG START: Данные НЕ найдены в pending_invites, берем из БД")
                        # Если не нашли в pending, берем из БД приглашающего
                        inviter_data = get_admin_from_db_by_user_id(inviter_id)
                        if inviter_data:
                            city = inviter_data.get('city_admin', '')
                            print(f"DEBUG START: Город из БД приглашающего: {city}")
                        else:
                            city = ''
                        client_phone = ''
                    
                    inviter_type = 'agent' if invite_type == 'invagent' else 'client'
                    
                    print(f"DEBUG START: Обработка приглашения")
                    print(f"  - Inviter type: {inviter_type}")
                    print(f"  - Inviter ID: {inviter_id}")
                    print(f"  - Client FIO: {client_fio}")
                    print(f"  - Client phone: {client_phone}")
                    print(f"  - City: {city}")
                    
                    # Сохраняем данные приглашения
                    user_temp_data[user_id] = {
                        'fio': client_fio,
                        'number': client_phone,
                        'city_admin': city,
                        'invited_by_user_id': inviter_id,
                        'invited_by_type': inviter_type,
                        'is_invited': True
                    }
                    
                    print(f"DEBUG START: Данные сохранены в user_temp_data для user_id={user_id}")
                    
                    # Показываем согласие на обработку данных
                    keyboard = types.InlineKeyboardMarkup()
                    btn_yes = types.InlineKeyboardButton("✅ Да", callback_data="consent_invited_yes")
                    btn_no = types.InlineKeyboardButton("❌ Нет", callback_data="consent_invited_no")
                    keyboard.add(btn_yes, btn_no)
                    agent_fio = get_agent_fio_by_id(inviter_id)
                    invite_text = f"Вас приветствует Помощник Юриста👋\n\nЯ бот-проводник по Вашим правам.\n\nПопали в ДТП? Я и моя команда профессиональных Юристов помогут Вам получить полную компенсацию восстановления Вашего автомобиля.\n\n"
                    if inviter_type == 'agent':
                        invite_text += f"Вас пригласил агент {agent_fio}.\n"
                    elif inviter_type == 'admin':
                        invite_text += f"Вас пригласил администратор {agent_fio}.\n"
                    else:
                        invite_text += f"Вас пригласил клиент {agent_fio}.\n"
                    invite_text += f"👤 ФИО: {client_fio}\n"
                    if client_phone:
                        invite_text += f"📱 Телефон: {client_phone}\n"
                    if city:
                        invite_text += f"🏙 Город: {city}\n"
                    invite_text += f"\nВы даете согласие на обработку персональных данных?"
                    
                    bot.send_message(
                        message.chat.id,
                        invite_text,
                        reply_markup=keyboard
                    )
                    print(f"DEBUG START: Сообщение с согласием отправлено!")
                    return
                    
                except Exception as e:
                    print(f"Ошибка обработки приглашения: {e}")
                    import traceback
                    traceback.print_exc()
                    bot.send_message(
                        message.chat.id,
                        "❌ Ошибка обработки ссылки-приглашения. Попробуйте зарегистрироваться самостоятельно."
                    )
                    show_registration_button(bot, message)
                    return
    
    # Обычный вход - проверяем регистрацию
    is_admin = db.check_admin_exists(user_id)
    
    if is_admin:
        from main_menu import show_main_menu
        show_main_menu(bot, message)
    else:
        show_registration_button(bot, message)

def show_registration_button(bot, message):
    """Показ кнопки регистрации"""
    keyboard = types.InlineKeyboardMarkup()
    btn_register = types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data="btn_registratsia")
    keyboard.add(btn_register)
    
    bot.send_message(
        message.chat.id,
        "Вас приветствует Помощник Юриста👋\n\nЯ бот-проводник по Вашим правам.\n\nПопали в ДТП? Я и моя команда профессиональных Юристов помогут Вам получить полную компенсацию восстановления Вашего автомобиля.\n\nДля дальнейшей работы с Помощником необходимо зарегистрироваться👇",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data == "callback_start")
def callback_start_handler(call):
    """Возврат в начало"""
    cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=5)
    user_id = call.from_user.id
    bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
    
    # Очищаем данные
    if user_id in user_temp_data:
        del user_temp_data[user_id]
        print(f"Очищены временные данные для user_id={user_id}")
    
    # Проверяем регистрацию
    admin_data = get_admin_from_db_by_user_id(user_id)
    
    print(f"admin_data: {admin_data}")
    
    if admin_data:
        print(f"✅ Пользователь найден, показываем меню")
        
        # Удаляем старое сообщение
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            print(f"Старое сообщение удалено")
        except Exception as e:
            print(f"Не удалось удалить сообщение: {e}")
        
        # ИСПРАВЛЕНИЕ: Создаем правильный объект Message
        from main_menu import show_main_menu
        
        # Используем существующий объект call.message, но "подменяем" from_user
        original_from_user = call.message.from_user if hasattr(call.message, 'from_user') else None
        
        # Создаем искусственный from_user
        class User:
            def __init__(self, user_id):
                self.id = user_id
        
        call.message.from_user = User(user_id)
        
        try:
            show_main_menu(bot, call.message)
        except Exception as e:
            print(f"Ошибка в show_main_menu: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Восстанавливаем оригинальный from_user
            if original_from_user:
                call.message.from_user = original_from_user
    else:
        print(f"❌ Пользователь НЕ найден в БД")
        
        try:
            bot.send_message(
                chat_id=call.message.chat.id,
                text="👋 Привет! Для работы с помощником Юриста необходимо зарегистрироваться."
            )
        except:
            bot.send_message(
                call.message.chat.id,
                "👋 Привет! Для работы с помощником Юриста необходимо зарегистрироваться."
            )
        
        show_registration_button(bot, call.message)
    


@bot.message_handler(commands=['clear'])
def clear_handler(message):
    """Очистка временных данных пользователя"""
    user_id = message.from_user.id
    if user_id in user_temp_data:
        del user_temp_data[user_id]
        bot.send_message(message.chat.id, "✅ Ваши временные данные очищены")
    else:
        bot.send_message(message.chat.id, "ℹ️ Нет данных для очистки")


@bot.message_handler(commands=['help'])
def help_handler(message):
    """Справка по командам"""
    help_text = """
🤖 <b>Доступные команды:</b>

/start - Начать работу с ботом


Для работы с ботом необходимо пройти регистрацию.
    """
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')


# Обработчик для неизвестных команд и сообщений
@bot.message_handler(func=lambda message: True, content_types=['text'])
def unknown_message_handler(message):
    """Обработчик неизвестных сообщений"""
    bot.send_message(
        message.chat.id,
        "❓ Неизвестная команда. Используйте /help для просмотра доступных команд."
    )


if __name__ == '__main__':
    print("🤖 Бот запущен...")

    from scheduler import start_scheduler
    start_scheduler(bot)
    
    # Импортируем и регистрируем обработчики из других модулей
    from registr import setup_registration_handlers
    from main_menu import setup_main_menu_handlers
    from cpr import setup_pretenziya_handlers
    from net_osago import setup_net_osago_handlers
    from podal_z import setup_podal_z_handlers

    setup_podal_z_handlers(bot, user_temp_data)
    setup_registration_handlers(bot, user_temp_data)
    setup_main_menu_handlers(bot, user_temp_data)
    setup_client_agent_handlers(bot, user_temp_data)
    setup_client_handlers(bot, user_temp_data)
    setup_pretenziya_handlers(bot, user_temp_data)
    setup_net_osago_handlers(bot, user_temp_data)
    try:
        bot.infinity_polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"❌ Ошибка при работе бота: {e}")

