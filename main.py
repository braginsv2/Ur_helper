import telebot
from telebot import types
import config
import json
import zlib
from database import DatabaseManager, get_admin_from_db_by_user_id, get_agent_fio_by_id
import base64
from client_agent import setup_client_agent_handlers
from client import setup_client_handlers
import threading
import time
from functools import wraps
import sys
import logging
from datetime import datetime

# Настройка логирования в файл
log_filename = f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

# Создаем папку для логов, если её нет
import os
os.makedirs('logs', exist_ok=True)


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/{log_filename}', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)  # Дублируем в терминал
    ]
)

# Перенаправляем print в файл
class Logger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, 'a', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger(f'logs/{log_filename}')
sys.stderr = Logger(f'logs/{log_filename}')
# Словарь для отслеживания активных обработок
active_callbacks = {}
callback_lock = threading.Lock()
upload_sessions = {}
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
            bot.delete_message(chat_id, message_id+1 - i)
        except:
            pass
@bot.message_handler(commands=['start'])
def start_handler(message):
    """Обработчик команды /start с параметрами и без"""
    user_id = message.from_user.id
    
    # Проверяем наличие параметров в команде
    command_args = message.text.split()
    
    if len(command_args) > 1:
        param = command_args[1]
        print(f"DEBUG START: Получен параметр: {param}")
        
        # Проверяем, что это ссылка-приглашение
        if param.startswith('invagent_') or param.startswith('invclient_') or param.startswith('invadmin_'):
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
                
                if invite_type == 'invagent' or invite_type == 'invadmin':
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
                    if invite_type == 'invagent':
                        inviter_type = 'agent'
                    elif invite_type == 'invadmin':
                        inviter_type = 'admin'
                    else:
                        inviter_type = 'client'
         
                    
                    print(f"DEBUG START: Обработка приглашения")
                    print(f"  - Inviter type: {inviter_type}")
                    print(f"  - Inviter ID: {inviter_id}")
                    print(f"  - Client FIO: {client_fio}")
                    print(f"  - Client phone: {client_phone}")
                    print(f"  - City: {city}")
                    if len(client_fio.split()) == 2:
                        client_fio_k = client_fio.split()[0] + " " + list(client_fio.split()[1])[0] + "."
                    else:
                        client_fio_k = client_fio.split()[0] + " " + list(client_fio.split()[1])[0] + "." + list(client_fio.split()[2])[0] + "."
                    # Сохраняем данные приглашения
                    user_temp_data[user_id] = {
                        'fio': client_fio,
                        'fio_k': client_fio_k,
                        'number': client_phone,
                        'city_admin': city,
                        'invited_by_user_id': inviter_id,
                        'invited_by_type': inviter_type,
                        'is_invited': True
                    }
                    
                    print(f"DEBUG START: Данные сохранены в user_temp_data для user_id={user_id}")
                    
                    # Показываем согласие на обработку данных
                    keyboard = types.InlineKeyboardMarkup()
                    btn_yes = types.InlineKeyboardButton("✅ Подтвердить", callback_data="consent_invited_yes")
                    btn_no = types.InlineKeyboardButton("❌ Отклонить", callback_data="consent_invited_no")
                    keyboard.add(btn_yes, btn_no)
                    agent_fio = get_agent_fio_by_id(inviter_id)
                    if inviter_type == 'agent':
                        invite_text = f"Вас пригласил агент {agent_fio}.\n\n"
                    elif inviter_type == 'admin':
                        invite_text = f"Вас пригласил администратор {agent_fio}.\n\n"
                    else:
                        invite_text = f"Вас пригласил клиент {agent_fio}.\n\n"
                    invite_text += f"👤 ФИО: {client_fio}\n"
                    if client_phone:
                        invite_text += f"📱 Телефон: {client_phone}\n"
                    if city:
                        invite_text += f"🌆 Город: {city}\n\n"

                    invite_text += f"Моя задача — собрать ваши личные данные для передачи команде Юристов.\n\nСейчас Вам поступит предложение подписать «Согласие на обработку персональных данных». Ознакомьтесь с документом и подтвердите его."
                    # Отправляем PDF документ
                    try:
                        with open("Согласие на обработку персональных данных.pdf", "rb") as pdf_file:
                            bot.send_document(message.chat.id, pdf_file, caption=invite_text, reply_markup=keyboard)
                        bot.delete_message(message.chat.id, message.message_id)
                    except FileNotFoundError:
                        bot.send_message(message.chat.id, invite_text + "\n\n⚠️ Файл соглашения не найден", reply_markup=keyboard)
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
        "Сейчас Вы находитесь в боте «Помощник юриста», который поможет:\n- Заключить договор на полное сопровождение - от подачи заявления в страховую компанию (СК) до получения полной компенсации согласно Федеральному закону № 40 «Об ОСАГО».\n- Сформировать заявления по форме страховой компании.\n- Освободить ваше личное время, взяв на себя напоминания, формирование документов и связь с юристами.\nБот будет направлять Вас и подсказывать дальнейшие шаги при выборе определённых параметров.\n\nПорядок работы:\n1. Регистрация в боте (мы строго соблюдаем конфиденциальность ваших паспортных данных).\n2. Сбор информации (вы вносите данные сами или с помощью нашего аварийного комиссара).\n3. Разработка стратегии (после ответа от страховой компании мы определяем лучший путь действий).\n4. Работа юриста (подготовка всех документов и взаимодействие с инстанциями).\n5. Защита ваших интересов в суде (если это потребуется).\n\nУсловия работы:\n- Стоимость услуг — 25 000 ₽ + 50% от суммы взысканных судом неустойки и штрафа.\n- Для представления ваших интересов потребуется нотариальная доверенность.\n- Мы гарантируем успешный результат при условии следования нашим рекомендациям.\n- В случае суда все расходы (наши услуги, эвакуатор, экспертиза) взыскиваются со страховой компании.\n\nВы можете стать нашим клиентом.",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "callback_start")
def callback_start_handler(call):
    """Возврат в начало"""
    cleanup_messages(bot, call.message.chat.id, call.message.message_id, count=5)
    user_id = call.from_user.id
    bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
    
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
@prevent_double_click(timeout=3.0)
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
    if message.chat.type != 'private':
        return
    bot.send_message(
        message.chat.id,
        "❓ Неизвестная команда. Используйте /start для вызова главного меню."
    )


if __name__ == '__main__':
    print("🤖 Бот запущен...")

    from scheduler import start_scheduler
    start_scheduler(bot)
    
    # Импортируем и регистрируем обработчики из других модулей
    from registr import setup_registration_handlers
    from main_menu import setup_main_menu_handlers

    from net_osago import setup_net_osago_handlers
    from podal_z import setup_podal_z_handlers
    from workers.appraiser import setup_appraiser_handlers
    from workers.pret_department import setup_pret_department_handlers
    from workers.admin import setup_admin_handlers

    setup_admin_handlers(bot, user_temp_data, upload_sessions)
    setup_podal_z_handlers(bot, user_temp_data)
    setup_registration_handlers(bot, user_temp_data)
    setup_main_menu_handlers(bot, user_temp_data, upload_sessions)
    setup_client_agent_handlers(bot, user_temp_data, upload_sessions)
    setup_client_handlers(bot, user_temp_data, upload_sessions)
    setup_appraiser_handlers(bot, user_temp_data, upload_sessions)
    setup_pret_department_handlers(bot, user_temp_data)
    setup_net_osago_handlers(bot, user_temp_data)
    try:
        bot.infinity_polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"❌ Ошибка при работе бота: {e}")


