from telebot import types
import re
from datetime import datetime, timedelta
from database import (
    DatabaseManager,
    save_client_to_db_with_id_new,
    get_admin_from_db_by_user_id,
    get_client_from_db_by_client_id
)
from word_utils import create_fio_data_file, export_clients_db_to_excel, edit_files, replace_words_in_word, get_next_business_date
import json
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
def setup_client_agent_handlers(bot, user_temp_data):
    """Регистрация обработчиков для работы агента с клиентом"""
    
    # ========== НАЧАЛО ЗАПОЛНЕНИЯ ДОГОВОРА ==========
    
    @bot.callback_query_handler(func=lambda call: call.data == "start_agent_client_contract")
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
                "📋 Агент начал заполнение договора.\n\n"
                "После заполнения вам придет запрос на подтверждение данных.",
                reply_markup=keyboard_client
            )
            user_temp_data[agent_id]['contract_data'].update({'message_id': msg.message_id})
        except Exception as e:
            print(f"Ошибка уведомления клиента: {e}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("use_existing_contract_"))
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
    def handle_accident_type(call):
        """Обработка выбора типа обращения"""
        agent_id = call.from_user.id
        
        if call.data == 'accident_dtp':
            user_temp_data[agent_id]['contract_data']['accident'] = "ДТП"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nНаходитесь на стадии оформления в ГИБДД.\nЗаявление в страховую ещё не подавали.\nПримерная дата первой выплаты (дата через 20 дней)\nПримерная дата завершения дела (дата через 280 дней)\n\nЭвакуатор вызывали?"

        elif call.data == 'accident_podal_zayavl':
            user_temp_data[agent_id]['contract_data']['accident'] = "Подал заявление"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nЗаявление в страховую подали самостоятельно на выплату или ремонт.\nПримерная дата завершения дела (дата через 280 дней)\n\nЭвакуатор вызывали?"

        elif call.data == 'accident_pit':
            user_temp_data[agent_id]['contract_data']['accident'] = "После ямы"
            context = f"🤖 Вы попали в ДТП по вине дорожных служб (ямы, люки, остатки ограждений и т.д.)\n\nЭвакуатор вызывали?"
        elif call.data == 'accident_net_osago':
            user_temp_data[agent_id]['contract_data']['accident'] = "Нет ОСАГО"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nНаходитесь на стадии оформления в ГИБДД.\nДанная ситуация является не страховым случаем.\nКомпенсирует убыток Виновник ДТП.\nПримерная дата завершения дела (дата через 90 дней)\n\nЭвакуатор вызывали?"
        else:
            context = f"Эвакуатор вызывали?"
        

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="ev_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="ev_no")
        btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="start_agent_client_contract")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data in ["ev_yes", "ev_no"])
    def handle_evacuator(call):
        """Обработка выбора эвакуатора"""
        agent_id = call.from_user.id
        
        if call.data == "ev_yes":
            user_temp_data[agent_id]['contract_data']['ev'] = "Да"
        elif call.data == "ev_no":
            user_temp_data[agent_id]['contract_data']['ev'] = "Нет"
        
        # СРАЗУ ПЕРЕХОДИМ К ДАТЕ ДТП (паспортные данные уже есть из БД)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_agent"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_agent"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="start_agent_client_contract"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату ДТП:",
            reply_markup=keyboard
        )
    
    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_date_today_agent", "dtp_date_other_agent"])
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
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Дата ДТП: {date_dtp}\n\nВведите время ДТП (ЧЧ:ММ):"
            )
            bot.register_next_step_handler(call.message, process_dtp_time, agent_id, call.message.message_id)
            
        elif call.data == "dtp_date_other_agent":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДТП (ДД.ММ.ГГГГ):"
            )
            bot.register_next_step_handler(call.message, process_dtp_date, agent_id, call.message.message_id)
    
    def process_dtp_date(message, agent_id, prev_msg_id):
        """Обработка даты ДТП"""
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
                msg = bot.send_message(message.chat.id, "❌ Дата ДТП не может быть в будущем!\nВведите корректную дату ДТП:")
                bot.register_next_step_handler(msg, process_dtp_date, agent_id, msg.message_id)
                return
            
            if input_date < three_years_ago:
                msg = bot.send_message(message.chat.id, "❌ Прошло более трех лет!\nВведите корректную дату ДТП:")
                bot.register_next_step_handler(msg, process_dtp_date, agent_id, msg.message_id)
                return
            
            user_temp_data[agent_id]['contract_data']['date_dtp'] = date_text
            msg = bot.send_message(message.chat.id, "Введите время ДТП (ЧЧ:ММ):")
            bot.register_next_step_handler(msg, process_dtp_time, agent_id, msg.message_id)
            
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату ДТП в формате ДД.ММ.ГГГГ:")
            bot.register_next_step_handler(msg, process_dtp_date, agent_id, msg.message_id)
            return
    
    
    def process_dtp_time(message, agent_id, prev_msg_id):
        """Обработка времени ДТП"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        time_text = message.text.strip()
        
        if not re.match(r'^\d{2}:\d{2}$', time_text):
            msg = bot.send_message(
                message.chat.id,
                "❌ Неверный формат времени. Введите в формате ЧЧ:ММ:"
            )
            bot.register_next_step_handler(msg, process_dtp_time, agent_id, msg.message_id)
            return
        
        user_temp_data[agent_id]['contract_data']['time_dtp'] = time_text
        
        msg = bot.send_message(message.chat.id, "Введите адрес ДТП:")
        bot.register_next_step_handler(msg, process_dtp_address, agent_id, msg.message_id)
    
    
    def process_dtp_address(message, agent_id, prev_msg_id):
        """Обработка адреса ДТП"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        user_temp_data[agent_id]['contract_data']['address_dtp'] = message.text.strip()
        
        # Показываем итоговые данные агенту
        show_contract_summary_to_agent(bot, message.chat.id, agent_id, user_temp_data)
    
    
    def show_contract_summary_to_agent(bot, chat_id, agent_id, user_temp_data):
        """Показ итоговых данных агенту"""
        contract_data = user_temp_data[agent_id]['contract_data']
        
        summary = "📋 <b>Данные договора:</b>\n\n"
        summary += f"👤 ФИО: {contract_data.get('fio', '')}\n"
        summary += f"📅 Дата рождения: {contract_data.get('date_of_birth', '')}\n"
        summary += f"📍 Город: {contract_data.get('city', '')}\n"
        summary += f"📄 Паспорт: {contract_data.get('seria_pasport', '')} {contract_data.get('number_pasport', '')}\n"
        summary += f"📍 Выдан: {contract_data.get('where_pasport', '')}\n"
        summary += f"📅 Дата выдачи: {contract_data.get('when_pasport', '')}\n"
        summary += f"📮 Индекс: {contract_data.get('index_postal', '')}\n"
        summary += f"🏠 Адрес: {contract_data.get('address', '')}\n"
        summary += f"🚗 Дата ДТП: {contract_data.get('date_dtp', '')}\n"
        summary += f"⏰ Время ДТП: {contract_data.get('time_dtp', '')}\n"
        summary += f"📍 Адрес ДТП: {contract_data.get('address_dtp', '')}\n"
        
        keyboard = types.InlineKeyboardMarkup()
        btn_send = types.InlineKeyboardButton("📤 Отправить на подтверждение", callback_data="send_contract_to_client")
        btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data="callback_start")
        keyboard.add(btn_send)
        keyboard.add(btn_cancel)
        
        bot.send_message(chat_id, summary, parse_mode='HTML', reply_markup=keyboard)
    
    
    @bot.callback_query_handler(func=lambda call: call.data == "send_contract_to_client")
    def send_contract_to_client(call):
        """Отправка данных договора клиенту на подтверждение"""
        agent_id = call.from_user.id
        contract_data = user_temp_data[agent_id]['contract_data']
        client_user_id = user_temp_data[agent_id]['client_user_id']
        
        # Формируем сообщение для клиента
        summary = "📋 <b>Проверьте данные договора:</b>\n\n"
        summary += f"👤 ФИО: {contract_data.get('fio', '')}\n"
        summary += f"📅 Дата рождения: {contract_data.get('date_of_birth', '')}\n"
        summary += f"📍 Город: {contract_data.get('city', '')}\n"
        summary += f"📄 Паспорт: {contract_data.get('seria_pasport', '')} {contract_data.get('number_pasport', '')}\n"
        summary += f"📍 Выдан: {contract_data.get('where_pasport', '')}\n"
        summary += f"📅 Дата выдачи: {contract_data.get('when_pasport', '')}\n"
        summary += f"📮 Индекс: {contract_data.get('index_postal', '')}\n"
        summary += f"🏠 Адрес: {contract_data.get('address', '')}\n"
        summary += f"🚗 Дата ДТП: {contract_data.get('date_dtp', '')}\n"
        summary += f"⏰ Время ДТП: {contract_data.get('time_dtp', '')}\n"
        summary += f"📍 Адрес ДТП: {contract_data.get('address_dtp', '')}\n"
        
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
        
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Данные отправлены клиенту на подтверждение.\n\nОжидайте ответа..."
        )
        user_temp_data[agent_id]['contract_data']['message_id'] = msg.message_id
        bot.answer_callback_query(call.id, "Данные отправлены клиенту")
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_contract_"))
    def confirm_contract_by_client(call):
        """Подтверждение данных клиентом"""
        agent_id = int(call.data.replace("confirm_contract_", ""))
        client_id = call.from_user.id
        
        msg = bot.edit_message_text(
            chat_id=agent_id,
            message_id=user_temp_data[agent_id]['contract_data']['message_id'],
            text="✅ Данные подтверждены!"
        )
        user_temp_data[agent_id]['contract_data']['message_id'] = msg.message_id
        contract_data = user_temp_data[agent_id]['contract_data']
        try:
            client_contract_id, updated_data = save_client_to_db_with_id_new(contract_data)
            contract_data['user_id'] = str(user_temp_data[agent_id].get('client_user_id'))
            contract_data.update(updated_data)
            contract_data['client_id'] = client_contract_id
            
            print(f"Договор сохранен с client_id: {client_contract_id}")
            print(contract_data)
            # Создаем файл с данными
            create_fio_data_file(contract_data)
            
            # Заполняем шаблон юр договора
            replace_words_in_word(
                ["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", "{{ Дата }}", "{{ ФИО }}", 
                 "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
                 "{{ Паспорт_когда }}", "{{ Индекс }}", "{{ Адрес }}", "{{ Дата_ДТП }}", 
                 "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                [str(contract_data['year']), str(client_contract_id), str(contract_data["city"]), 
                 str(datetime.now().strftime("%d.%m.%Y")), str(contract_data["fio"]), 
                 str(contract_data["date_of_birth"]), str(contract_data["seria_pasport"]), 
                 str(contract_data["number_pasport"]), str(contract_data["where_pasport"]),
                 str(contract_data["when_pasport"]), str(contract_data["index_postal"]), 
                 str(contract_data["address"]), str(contract_data["date_dtp"]), 
                 str(contract_data["time_dtp"]), str(contract_data["address_dtp"]), 
                 str(contract_data['fio_k'])],
                "Шаблоны\\1. ДТП\\1. На ремонт\\2. Юр договор.docx",
                f"clients\\{client_contract_id}\\Документы\\2. Юр договор.docx"
            )
            import shutil
            import os

            fio_folder = contract_data.get('fio', '')
            source_folder = f"admins_info\\{fio_folder}"
            destination_folder = f"clients\\{client_contract_id}\\Документы"

            # Список файлов для копирования (ищем файлы начинающиеся с этих имен)
            files_to_copy = []

            try:
                if os.path.exists(source_folder):
                    all_files = os.listdir(source_folder)
                    print
                    # Ищем файлы паспорта (начинаются с "Паспорт_")
                    passport_files = [f for f in all_files if f.startswith("Паспорт_")]
                    if passport_files:
                        files_to_copy.extend(passport_files)
                    
                    # Ищем файл прописки
                    propiska_files = [f for f in all_files if f.startswith("Прописка")]
                    if propiska_files:
                        files_to_copy.extend(propiska_files)
                    
                    # Копируем найденные файлы
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
            # Обновляем связь клиент-агент с contract_id
            
            client_user_id = user_temp_data[agent_id].get('client_user_id')

            if client_user_id:
                from database import update_client_agent_contract_link
                update_client_agent_contract_link(client_user_id, client_contract_id)
                print(f"✅ Связь обновлена в handle_power_attorney: client={client_user_id}, contract={client_contract_id}")
            else:
                print(f"⚠️ ОШИБКА: client_user_id не найден в user_temp_data для agent_id={agent_id}")
            
        except Exception as e:
            print(f"Ошибка сохранения в БД: {e}")
            import traceback
            traceback.print_exc()
            bot.send_message(agent_id, "❌ Ошибка сохранения договора. Попробуйте снова.")
            return
        try:
            bot.delete_message(agent_id, msg.message_id)
        except:
            pass
        # Отправляем клиенту юр договор
        send_legal_contract_to_client(bot, client_id, agent_id, contract_data)
        
        bot.answer_callback_query(call.id, "Ответ сохранен")
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("decline_contract_"))
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
        text += f"👤 ФИО: {contract_data.get('fio', 'не указано')}\n"
        text += f"📱 Номер телефона: {contract_data.get('number', 'не указан')}\n"
        text += f"📅 Дата рождения: {contract_data.get('date_of_birth', 'не указана')}\n"
        text += f"🏙 Место рождения: {contract_data.get('city_birth', 'не указано')}\n"
        text += f"📄 Серия паспорта: {contract_data.get('seria_pasport', 'не указана')}\n"
        text += f"📄 Номер паспорта: {contract_data.get('number_pasport', 'не указан')}\n"
        text += f"📍 Кем выдан: {contract_data.get('where_pasport', 'не указано')}\n"
        text += f"📅 Дата выдачи: {contract_data.get('when_pasport', 'не указана')}\n"
        text += f"📮 Индекс: {contract_data.get('index_postal', 'не указан')}\n"
        text += f"🏠 Адрес: {contract_data.get('address', 'не указан')}\n"
        text += f"🚗 Дата ДТП: {contract_data.get('date_dtp', 'не указана')}\n"
        text += f"⏰ Время ДТП: {contract_data.get('time_dtp', 'не указано')}\n"
        text += f"📍 Адрес ДТП: {contract_data.get('address_dtp', 'не указан')}\n\n"
        text += "Выберите поле для редактирования:"
        
        # Создаем клавиатуру с кнопками редактирования
        keyboard = types.InlineKeyboardMarkup()
        
        # Поля для редактирования
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО", callback_data="edit_field_fio"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер телефона", callback_data="edit_field_number"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата рождения", callback_data="edit_field_date_of_birth"))
        keyboard.add(types.InlineKeyboardButton("✏️ Город", callback_data="edit_field_city"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия паспорта", callback_data="edit_field_seria_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер паспорта", callback_data="edit_field_number_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Кем выдан паспорт", callback_data="edit_field_where_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата выдачи паспорта", callback_data="edit_field_when_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Индекс", callback_data="edit_field_index_postal"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес", callback_data="edit_field_address"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата ДТП", callback_data="edit_field_date_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Время ДТП", callback_data="edit_field_time_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес ДТП", callback_data="edit_field_address_dtp"))
        
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
            'fio': 'ФИО (Иванов Иван Иванович)',
            'number': 'Номер телефона (+79123456789)',
            'date_of_birth': 'Дата рождения (ДД.ММ.ГГГГ)',
            'city': 'Город',
            'seria_pasport': 'Серия паспорта (4 цифры)',
            'number_pasport': 'Номер паспорта (6 цифр)',
            'when_pasport': 'Дата выдачи паспорта (ДД.ММ.ГГГГ)',
            'where_pasport': 'Кем выдан паспорт',
            'index_postal': 'Индекс (6 цифр)',
            'address': 'Адрес проживания',
            'date_dtp': 'Дата ДТП (ДД.ММ.ГГГГ)',
            'time_dtp': 'Время ДТП (ЧЧ:ММ)',
            'address_dtp': 'Адрес ДТП'
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
        
        if field in ['date_of_birth', 'when_pasport', 'date_dtp']:
            # Проверка даты
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', new_value):
                validation_error = "❌ Неверный формат даты! Используйте ДД.ММ.ГГГГ"
            else:
                try:
                    datetime.strptime(new_value, "%d.%m.%Y")
                except ValueError:
                    validation_error = "❌ Некорректная дата!"
        
        elif field == 'time_dtp':
            # Проверка времени
            if not re.match(r'^\d{2}:\d{2}$', new_value):
                validation_error = "❌ Неверный формат времени! Используйте ЧЧ:ММ"
        
        elif field == 'number_pasport':
            # Проверка номера паспорта
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Номер паспорта должен содержать 6 цифр"
        
        elif field == 'seria_pasport':
            # Проверка серии паспорта
            if not new_value.isdigit() or len(new_value) != 4:
                validation_error = "❌ Серия паспорта должна содержать 4 цифры"
        
        elif field == 'index_postal':
            # Проверка индекса
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Индекс должен содержать 6 цифр"
        elif field == 'fio':
            if len(new_value.split()) < 2:
                validation_error = "❌ Неправильный формат! Введите ФИО (минимум Фамилия Имя):"
            else:
                words = new_value.split()
                for word in words:
                    if not word[0].isupper():
                        validation_error = "❌ Каждое слово должно начинаться с заглавной буквы!"
                        break

        elif field == 'number':
            # Очищаем номер от пробелов и символов
            clean_number = ''.join(filter(str.isdigit, new_value))
            if len(clean_number) != 11:
                validation_error = "❌ Номер телефона должен содержать 11 цифр (например: +79123456789)"
        
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
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Данные обновлены и отправлены клиенту на подтверждение!"
        )
        
        # Отправляем клиенту обновленные данные на подтверждение
        if client_user_id:
            try:
                summary = "📋 <b>Агент обновил данные. Проверьте их:</b>\n\n"
                summary += f"👤 ФИО: {contract_data.get('fio', '')}\n"
                summary += f"📱 Номер телефона: {contract_data.get('number', '')}\n"
                summary += f"📅 Дата рождения: {contract_data.get('date_of_birth', '')}\n"
                summary += f"🏙 Место рождения: {contract_data.get('city_birth', '')}\n"
                summary += f"📄 Паспорт: {contract_data.get('seria_pasport', '')} {contract_data.get('number_pasport', '')}\n"
                summary += f"📍 Выдан: {contract_data.get('where_pasport', '')}\n"
                summary += f"📅 Дата выдачи: {contract_data.get('when_pasport', '')}\n"
                summary += f"📮 Индекс: {contract_data.get('index_postal', '')}\n"
                summary += f"🏠 Адрес: {contract_data.get('address', '')}\n"
                summary += f"🚗 Дата ДТП: {contract_data.get('date_dtp', '')}\n"
                summary += f"⏰ Время ДТП: {contract_data.get('time_dtp', '')}\n"
                summary += f"📍 Адрес ДТП: {contract_data.get('address_dtp', '')}\n"
                
                keyboard = types.InlineKeyboardMarkup()
                btn_confirm = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_contract_{agent_id}")
                btn_decline = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_contract_{agent_id}")
                keyboard.add(btn_confirm)
                keyboard.add(btn_decline)
                
                bot.send_message(client_user_id, summary, parse_mode='HTML', reply_markup=keyboard)
                
            except Exception as e:
                print(f"Ошибка отправки клиенту: {e}")
        
        # Очищаем временные данные редактирования
        if 'editing_contract' in user_temp_data[agent_id]:
            del user_temp_data[agent_id]['editing_contract']
        if 'editing_field' in user_temp_data[agent_id]:
            del user_temp_data[agent_id]['editing_field']
        
        # Возвращаемся в главное меню
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, agent_id)


    @bot.callback_query_handler(func=lambda call: call.data == "cancel_edit_contract")
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
        document_path = f"clients\\{client_contract_id}\\Документы\\2. Юр договор.docx"
        
        contract_text = """
📄 <b>Договор оказания юридических услуг</b>

🤖 Этот договор регулирует оказание юридической помощи Вам в суде по вопросам возмещения ущерба после ДТП. Юрист обязуется защищать Ваши права, а Вы обязуетесь оплатить его работу. Вот основные моменты:

- Вы поручаете Юристу подготовить материалы по ДТП, добиться компенсации нанесенного ущерба, а в случае отказа, вести Ваше дело в суде.
- Оплата, в размере 25 000₽, производится в срок не позднее 10 дней с момента получения ответа от Страховой. 
- Дополнительно предусмотрен бонус Юристу («гонорар успеха»), в размере 50% от начисленных пени и штрафов Судом.
- Все судебные расходы оплачиваются Вами.
- Ваш Юрист не гарантирует успех дела, но приложит максимум усилий.
- От Вас потребуется своевременная передача всей важной информации и документов.
- Работа Юриста заканчивается после принятия судом решения по делу.

Обязательно прочитайте договор внимательно и убедитесь, что все понятно.

Подпишите договор👇
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
        print(accident_type)
        print(11)
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
        
        
        print(13)
        # Проверяем тип обращения
        if accident_type == "ДТП":
            print(14)
            # Уведомляем агента о составлении заявления
            cleanup_messages(bot, agent_id, msg.message_id, count=5)
            msg = bot.send_message(
                agent_id,
                "✅ Клиент подписал договор!\nДоговор успешно сформирован.\nСоставляем заявление в страховую.\n\nВведите марку и модель авто"
            )
            
            bot.answer_callback_query(call.id, "Договор подписан!")
            bot.register_next_step_handler(msg, marks, agent_id, msg.message_id, contract_data)
        
        elif accident_type == "После ямы":
            #cleanup_messages(bot, agent_id, msg.message_id, count=5)
            bot.send_message(
                agent_id,
                "✅ Клиент подписал договор!\nДоговор успешно сформирован.\n\n"
                "Тип обращения: После ямы\n"
            )
            
            # Очищаем данные
            if agent_id in user_temp_data:
                user_temp_data[agent_id].pop('contract_data', None)
                user_temp_data[agent_id].pop('client_user_id', None)
            from main_menu import show_main_menu_by_user_id
            # Возвращаем агента в главное меню
            show_main_menu_by_user_id(bot, agent_id)
            
            bot.answer_callback_query(call.id, "Договор подписан!")
        
        elif accident_type =="Подал заявление":
            #cleanup_messages(bot, agent_id, msg.message_id, count=5)
            keyboard = types.InlineKeyboardMarkup()
            btn_yes = types.InlineKeyboardButton("💰 На выплату", callback_data=f"podal_viplata_{contract_data['client_id']}")
            btn_no = types.InlineKeyboardButton("🛠️ На ремонт", callback_data=f"podal_rem_{contract_data['client_id']}")
            keyboard.add(btn_yes, btn_no)
            bot.send_message(
                chat_id=call.message.chat.id,
                text = f"✅ Договор успешно оформлен!\n\n"
                       f"Тип обращения: Подал заявление\nБыло подано заявление на выплату или на ремонт?",
                reply_markup = keyboard
            )
            
            bot.answer_callback_query(call.id, "Договор подписан!")
        elif accident_type =="Нет ОСАГО":
            #cleanup_messages(bot, agent_id, msg.message_id, count=5)
            keyboard = types.InlineKeyboardMarkup()
            btn_yes = types.InlineKeyboardButton("✅ Да", callback_data=f"NoOsago_yes_{contract_data['client_id']}")
            btn_no = types.InlineKeyboardButton("❌ Заполнить позже", callback_data=f"NoOsago_no_{contract_data['client_id']}")
            keyboard.add(btn_yes, btn_no)
            bot.send_message(
                chat_id=call.message.chat.id,
                text = f"✅ Договор успешно оформлен!\n\n"
                       f"Тип обращения: Нет ОСАГО у виновника ДТП\nЗаполнить заявление в ГИБДД?",
                reply_markup = keyboard
            )
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, client_id)
    @bot.callback_query_handler(func=lambda call: call.data in ["STS", "PTS", "DKP"])
    def callback_docs(call):
        user_id = call.from_user.id
        
        data = user_temp_data[user_id]
        user_message_id = [] 
          
        if call.data == "STS":
            data.update({"docs": "СТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_docs, data, user_message_id)

        elif call.data == "PTS":
            data.update({"docs": "ПТС"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
                )
            user_message_id = message.message_id

            bot.register_next_step_handler(message, seria_docs, data, user_message_id)
        else: 
            data.update({"docs": "ДКП"})
            data.update({"seria_docs": "-"})
            data.update({"number_docs": "-"})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДКП",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, data_docs, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('ins_page_'))
    def handle_insurance_pagination(call):
        """Обрабатывает пагинацию страховых компаний"""
        try:
            page = int(call.data.split('_')[2])
            keyboard = create_insurance_keyboard(page)
            
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error handling pagination: {e}")
    @bot.callback_query_handler(func=lambda call: call.data in ["Reco", "Ugo", "SOGAZ", "Ingo", "Ros", "Maks", "Energo", "Sovko", "Alfa", "VSK", "Soglasie", "Sber", "T-ins", "Ren", "Chul", "other"])
    def callback_insurance(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]
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
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию страхового полиса",
                reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
        else: 
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании",
                reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, other_insurance, data, user_message_id)

    def marks(message, agent_id, user_message_id, contract_data):
        """Обработка марки и модели авто"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        contract_data.update({"marks": message.text})
        
        msg = bot.send_message(message.chat.id, text="Введите номер авто клиента")
        bot.register_next_step_handler(msg, number_auto, contract_data, msg.message_id)
    def number_auto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
        
        original_text = message.text.replace(" ", "")
        has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
        
        if not has_lowercase and re.match(pattern, car_number) and len(car_number) in [8, 9]:
            data.update({"car_number": car_number})
            msg = bot.send_message(message.chat.id, "Введите год выпуска авто клиента, например, 2025")
            bot.register_next_step_handler(msg, year_auto, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "Неправильный формат!\nВведите номер авто клиента\n"
                "Пример: А123БВ77 или А123БВ777\n"
                "Все буквы должны быть заглавными!"
            )
            bot.register_next_step_handler(msg, number_auto, data, msg.message_id)
    def year_auto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите корректный год выпуска авто.\nНапример: 2025")
            bot.register_next_step_handler(msg, year_auto, data, msg.message_id)
        else:
            data.update({"year_auto": int(message.text.replace(" ", ""))})
            
            user_id = message.from_user.id
            user_temp_data[user_id] = data
            
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="STS")
            btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="PTS")
            keyboard.add(btn1)
            keyboard.add(btn2)

            bot.send_message(
                message.chat.id, 
                "Выберите документ о регистрации ТС", 
                reply_markup=keyboard
            )



    def seria_docs(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"seria_docs": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер документа о регистрации ТС".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_docs, data, user_message_id)
    def number_docs(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"number_docs": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_docs, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат!\nВведите номер документа о регистрации ТС, он должен состоять только из цифр"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_docs, data, user_message_id) 

    def data_docs(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_docs": message.text})
            
            user_id = message.from_user.id
            user_temp_data[user_id] = data
            
            # Создаем клавиатуру с пагинацией (первая страница)
            keyboard = create_insurance_keyboard(page=0)
            
            bot.send_message(
                message.chat.id, 
                text="Выберите страховую компанию".format(message.from_user), 
                reply_markup=keyboard
            )
            
        except ValueError:
            message = bot.send_message(
                message.chat.id, 
                text="Неправильный формат ввода!\nВведите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ".format(message.from_user)
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_docs, data, user_message_id)

    def other_insurance(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"insurance": message.text})
        message = bot.send_message(message.chat.id, text="Введите серию страхового полиса".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, seria_insurance, data, user_message_id)
    def seria_insurance(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"seria_insurance": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер страхового полиса".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_insurance, data, user_message_id)

    def number_insurance(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"number_insurance": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату страхового полиса в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_insurance, data,user_message_id)
    def date_insurance(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_insurance": message.text})
            message = bot.send_message(message.chat.id, text="Введите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату страхового полиса в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_insurance, data, user_message_id)
    def fio_culp(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        if len(message.text.split())<2:
                message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович".format(message.from_user))
                user_message_id = message.message_id
                bot.register_next_step_handler(message, fio_culp, data, user_message_id)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():  # Проверяем, что первая буква заглавная
                    message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО виновника ДТП в формате Иванов Иван Иванович")
                    user_message_id = message.message_id
                    bot.register_next_step_handler(message, fio_culp, data, user_message_id)
                    return
            data.update({"fio_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите марку, модель виновника ДТП".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, marks_culp, data, user_message_id)

    def marks_culp(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"marks_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер авто виновника ДТП".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_auto_culp, data, user_message_id)
    def number_auto_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        car_number = message.text.replace(" ", "").upper()
        pattern = r'^[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}$'
        
        original_text = message.text.replace(" ", "")
        has_lowercase = any(c.isalpha() and c.islower() for c in original_text)
        
        if not has_lowercase and re.match(pattern, car_number) and len(car_number) in [8, 9]:
            agent_id = message.from_user.id
            data.update({"number_auto_culp": str(car_number)})
            data.update({"date_ins": str(get_next_business_date())})
            data.update({"date_ins_pod": str(get_next_business_date())})
            data.update({"status": 'Отправлен запрос в страховую'})
            
            # Получаем client_user_id из временных данных агента
            client_user_id = user_temp_data.get(agent_id, {}).get('client_user_id')
            
            client_contract_id = data.get('client_id')

            if not client_contract_id:
                bot.send_message(message.chat.id, "❌ Ошибка: ID договора не найден")
                return

            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                
                # ВАЖНО: обновляем связь ПОСЛЕ успешного сохранения
                agent_id = message.from_user.id
                if client_user_id:
                    with db.get_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE client_agent_relationships 
                                SET contract_id = %s
                                WHERE agent_id = %s AND client_user_id = %s
                            """, (client_contract_id, agent_id, client_user_id))
                            conn.commit()
                            print(f"✅ Связь обновлена: agent={agent_id}, client={client_user_id}, contract={client_contract_id}")
                if updated_data:
                    data.update(updated_data)
                    print(f"✅ Заявление добавлено к договору {client_contract_id}")
                else:
                    print(f"⚠️ Договор {client_contract_id} не найден, используем текущие данные")
                    
            except Exception as e:
                print(f"⚠️ Ошибка обновления данных: {e}")
            create_fio_data_file(updated_data)
            # Выбираем шаблон в зависимости от эвакуатора
            if data.get("ev") == "Да":
                template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3a Заявление в Страховую ФЛ собственник с эвакуатором.docx"
                output_filename = "3a Заявление в Страховую ФЛ собственник с эвакуатором.docx"
            else:
                template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3b Заявление в Страховую ФЛ собственник без эвакуатора.docx"
                output_filename = "3b Заявление в Страховую ФЛ собственник без эвакуатора.docx"

            replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                "{{ Страховая }}", "{{ винФИО }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"1. Обложка дела.docx")
            # Заполняем шаблон заявления
            replace_words_in_word(
                ["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                "{{ Паспорт_номер }}", "{{ ДР }}", "{{ Индекс }}",
                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}", "{{ Nавто_клиента }}", "{{ Документ }}",
                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата }}", "{{ Место }}"],
                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                str(data["date_of_birth"]), str(data["index_postal"]), str(data["address"]),
                str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]), 
                str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]), 
                str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),
                str(data["number_insurance"]), str(data["city"]), str(datetime.now().strftime("%d.%m.%Y")), str(data["city_birth"])],
                template_path,
                f"clients\\{data['client_id']}\\Документы\\{output_filename}"
            )
            try:
                with open(f"clients\\{data['client_id']}\\Документы\\{output_filename}", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Заявление в страховую")
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            # Уведомляем клиента
            try:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                bot.send_message(
                    int(data['user_id']),
                    "✅ Заполнено заявление в страховую!\n\n"
                    "📄 Ознакомиться с ним можно в личном кабинете.",
                    reply_markup = keyboard
                )
            except Exception as e:
                print(f"Ошибка отправки уведомления клиенту: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"agent_view_contract_{data['client_id']}"))   
            bot.send_message(
                agent_id,
                "✅ Заявление в страховую успешно сформировано! Загрузите фото с ДТП в личном кабинете.",
                reply_markup=keyboard
            )

            
            # Очищаем временные данные агента
            if agent_id in user_temp_data:
                user_temp_data.pop(agent_id, None)
            
            
        else:
            msg = bot.send_message(
                message.chat.id,
                "Неправильный формат!\nВведите номер авто виновника ДТП\n"
                "Пример: А123БВ77 или А123БВ777\n"
                "Все буквы должны быть заглавными!"
            )
            bot.register_next_step_handler(msg, number_auto_culp, data, msg.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_dop_osm_"))
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
        try:
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['dop_osm_data']
        data['Nv_ins'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите номер акта осмотра ТС")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_na_ins, agent_id, user_message_id)


    def agent_dop_osm_na_ins(message, agent_id, user_message_id):
        """Обработка номера акта осмотра"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['dop_osm_data']
        data['Na_ins'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_date_na_ins, agent_id, user_message_id)


    def agent_dop_osm_date_na_ins(message, agent_id, user_message_id):
        """Обработка даты акта осмотра"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data = user_temp_data[agent_id]['dop_osm_data']
            data['date_Na_ins'] = message.text.strip()
            
            msg = bot.send_message(message.chat.id, "Введите адрес СТО клиента")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_address_sto, agent_id, user_message_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_date_na_ins, agent_id, user_message_id)


    def agent_dop_osm_address_sto(message, agent_id, user_message_id):
        """Обработка адреса СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['dop_osm_data']
        data['address_sto_main'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите дату записи в СТО в формате ДД.ММ.ГГГГ")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_dop_osm_date_sto, agent_id, user_message_id)


    def agent_dop_osm_date_sto(message, agent_id, user_message_id):
        """Обработка даты записи в СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data = user_temp_data[agent_id]['dop_osm_data']
            data['date_sto_main'] = message.text.strip()
            
            msg = bot.send_message(message.chat.id, "Введите время записи в СТО в формате ЧЧ:ММ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_time_sto, agent_id, user_message_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату записи в СТО в формате ДД.ММ.ГГГГ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_date_sto, agent_id, user_message_id)


    def agent_dop_osm_time_sto(message, agent_id, user_message_id):
        """Обработка времени записи в СТО - ФИНАЛ для доп осмотра"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text) != 5 or message.text.count(':') != 1:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат времени!\nВведите время в формате ЧЧ:ММ (например: 14:30)")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_time_sto, agent_id, user_message_id)
            return
        
        try:
            datetime.strptime(message.text, "%H:%M")
            
            data = user_temp_data[agent_id]['dop_osm_data']
            data['time_sto_main'] = message.text.strip()
            data['dop_osm'] = "Yes"
            data['data_dop_osm'] = datetime.now().strftime("%d.%m.%Y")

            if data.get('status', '') not in ['Ожидание претензии', 'Составлена претензия', 'Составлено заявление к Фин.омбудсмену', 'Деликт', 'Завершен', 'Составлено исковое заявление']: 
                data.update({"status": "Подано заявление на дополнительный осмотр"})
            
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
                template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\4. Заявление о проведении доп осмотра\\4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx"
                output_filename = "4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx"
            else:
                template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\4. Заявление о проведении доп осмотра\\4. Заявление о проведении дополнительного осмотра автомобиля.docx"
                output_filename = "4. Заявление о проведении дополнительного осмотра автомобиля.docx"
            
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
                f"clients\\{client_id}\\Документы\\{output_filename}"
            )
            
            # Отправляем документ агенту
            try:
                with open(f"clients\\{client_id}\\Документы\\{output_filename}", 'rb') as doc:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    bot.send_document(message.chat.id, doc, caption="📋 Заявление на дополнительный осмотр", reply_markup = keyboard)
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            
            # Уведомляем клиента
            client_user_id = user_temp_data[agent_id].get('client_user_id')
            if client_user_id:
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    bot.send_message(
                        int(client_user_id),
                        f"✅ Заявление на дополнительный осмотр авто составлено, ознакомиться с ним можно в личном кабинете",
                        reply_markup = keyboard
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
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат времени!\nВведите время в формате ЧЧ:ММ (например: 14:30)")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_dop_osm_time_sto, agent_id, user_message_id)


    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_answer_insurance_"))
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
        
        user_temp_data[agent_id]['answer_insurance_data'] = data
        user_temp_data[agent_id]['client_id'] = client_id
        user_temp_data[agent_id]['client_user_id'] = contract.get('user_id')
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✅ Да", callback_data="agent_answer_yes"))
        keyboard.add(types.InlineKeyboardButton("❌ Нет", callback_data="agent_answer_no"))
        keyboard.add(types.InlineKeyboardButton("📋 У виновника ДТП Нет ОСАГО", callback_data=f"NoOsago_prod_{client_id}"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Есть ли ответ от страховой?",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data == "agent_answer_yes")
    def agent_answer_yes(call):
        """Агент подтвердил ответ от страховой"""
        agent_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data="agent_docs_ins_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data="agent_docs_ins_no"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходимо заявление на выдачу документов из страховой?",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data == "agent_answer_no")
    def agent_answer_no(call):
        """Агент сообщил об отсутствии ответа"""
        agent_id = call.from_user.id
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data="agent_docs_ins_yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data="agent_docs_ins_no"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходимо заявление на выдачу документов из страховой?",
            reply_markup=keyboard
        )


    @bot.callback_query_handler(func=lambda call: call.data in ["agent_docs_ins_yes", "agent_docs_ins_no"])
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
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Выберите из предложенных вариантов:\n\n"
                    "1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n"
                    "2) Страховая компания выдала направление на ремонт, СТО отказала.\n"
                    "3) Страховая выдала направление на ремонт и ремонт произведен.\n"
                    "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.",
                reply_markup=keyboard
            )
        else:
            # С заявлением на выдачу документов
            data = user_temp_data[agent_id]['answer_insurance_data']
            
            data['status'] = "Подано заявление на выдачу документов из страховой"
            
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
                template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\5. Запрос в страховую о выдаче акта и расчета\\5. Запрос в страховую о выдаче акта и расчёта представитель.docx"
                output_filename = "5. Запрос в страховую о выдаче акта и расчёта представитель.docx"
            else:
                template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\5. Запрос в страховую о выдаче акта и расчета\\5. Запрос в страховую о выдаче акта и расчёта.docx"
                output_filename = "5. Запрос в страховую о выдаче акта и расчёта.docx"

            # Заполняем шаблон
            replace_words_in_word(
                ["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", 
                "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}", 
                "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", 
                "{{ Телефон }}"],
                [str(data.get("insurance", "")), str(data.get("city", "")), str(data.get("fio", "")), 
                str(data.get("date_of_birth", "")), str(data.get("seria_pasport", "")), 
                str(data.get("number_pasport", "")), str(data.get("where_pasport", "")), 
                str(data.get("when_pasport", "")), str(data.get("date_dtp", "")), 
                str(data.get("time_dtp", "")), str(data.get("address_dtp", "")), 
                str(data.get("marks", "")), str(data.get("car_number", "")), 
                str(data.get("marks_culp", "")), str(data.get("number_auto_culp", "")), 
                str(data.get("number", ""))],
                template_path,
                f"clients\\"+str(data['client_id'])+f"\\Документы\\{output_filename}"
            )
            
            # Отправляем документ агенту
            try:
                with open(f"clients\\"+str(data['client_id'])+"\\Документы\\{output_filename}", 'rb') as doc:
                    bot.send_document(call.message.chat.id, doc, caption="📋 Запрос на выдачу документов")
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, "❌ Ошибка: файл не найден")
            
            # Уведомляем клиента
            client_user_id = user_temp_data[agent_id].get('client_user_id')
            if client_user_id:
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
            
            bot.send_message(
                call.message.chat.id,
                "Выберите из предложенных вариантов:\n\n"
                "1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n"
                "2) Страховая компания выдала направление на ремонт, СТО отказала.\n"
                "3) Страховая выдала направление на ремонт и ремонт произведен.\n"
                "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.",
                reply_markup=keyboard
            )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("agent_vibor"))
    def agent_vibor_handler(call):
        """Обработка выбора варианта развития"""
        agent_id = call.from_user.id
        data = user_temp_data[agent_id]['answer_insurance_data']
        client_id = user_temp_data[agent_id]['client_id']
        client_user_id = user_temp_data[agent_id].get('client_user_id')
        
        data.update({"vibor": call.data.replace("agent_","")})
        if call.data in ["agent_vibor1", "agent_vibor4"]:
            # 1 и 4 - ожидание претензии
            data['status'] = "Ожидание претензии"
            
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                reply_markup = keyboard
            )
            
            if client_user_id:
                try:
                    bot.send_message(
                        int(client_user_id),
                        "✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                        reply_markup = keyboard
                    )
                except:
                    pass

        elif call.data == "agent_vibor2":
            # 2 - заявление в СТО (СТО отказала)
            if agent_id not in user_temp_data:
                user_temp_data[agent_id] = {}
            
            user_temp_data[agent_id]['sto_refusal_data'] = data
            user_temp_data[agent_id]['client_id'] = client_id
            user_temp_data[agent_id]['client_user_id'] = client_user_id
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название СТО"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_name, agent_id, user_message_id)
        
        elif call.data == "agent_vibor3":
            # 3 - ремонт произведен - дело завершено
            data['status'] = "Завершен"
            
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="🎉 Поздравляем с завершением дела!"
            )
            
            if client_user_id:
                try:
                    bot.send_message(int(client_user_id), "🎉 Ваше дело успешно завершено!")
                except:
                    pass
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, agent_id)
        # Очищаем временные данные только для вариантов 1, 3, 4
        if call.data != "agent_vibor2":
            if agent_id in user_temp_data:
                if 'answer_insurance_data' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['answer_insurance_data']
                if 'client_id' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['client_id']
                if 'client_user_id' in user_temp_data[agent_id]:
                    del user_temp_data[agent_id]['client_user_id']


    # Обработчики для заявления в СТО от агента
    def agent_sto_refusal_name(message, agent_id, user_message_id):
        """Обработка названия СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['sto_refusal_data']
        data['name_sto'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите ИНН СТО")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_inn, agent_id, user_message_id)


    def agent_sto_refusal_inn(message, agent_id, user_message_id):
        """Обработка ИНН СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if not message.text.isdigit():
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат! ИНН должен состоять только из цифр.\nВведите ИНН СТО:"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_inn, agent_id, user_message_id)
            return
        
        data = user_temp_data[agent_id]['sto_refusal_data']
        data['inn_sto'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите индекс СТО (6 цифр)")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_index, agent_id, user_message_id)


    def agent_sto_refusal_index(message, agent_id, user_message_id):
        """Обработка индекса СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат! Должно быть 6 цифр.\nВведите индекс СТО:"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_index, agent_id, user_message_id)
            return
        
        data = user_temp_data[agent_id]['sto_refusal_data']
        data['index_sto'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите адрес СТО")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_address, agent_id, user_message_id)


    def agent_sto_refusal_address(message, agent_id, user_message_id):
        """Обработка адреса СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['sto_refusal_data']
        data['address_sto'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите номер направления на СТО")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_n_sto, agent_id, user_message_id)


    def agent_sto_refusal_n_sto(message, agent_id, user_message_id):
        """Обработка номера направления СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data = user_temp_data[agent_id]['sto_refusal_data']
        data['N_sto'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите дату направления на СТО (ДД.ММ.ГГГГ)")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, agent_sto_refusal_date_napr, agent_id, user_message_id)


    def agent_sto_refusal_date_napr(message, agent_id, user_message_id):
        """Обработка даты направления - ФИНАЛ для заявления в СТО"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
        except ValueError:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ:"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, agent_sto_refusal_date_napr, agent_id, user_message_id)
            return
        
        data = user_temp_data[agent_id]['sto_refusal_data']
        data['date_napr_sto'] = message.text.strip()
        data['date_zayav_sto'] = datetime.now().strftime("%d.%m.%Y")
        data['status'] = "Ожидание претензии"
        
        client_id = user_temp_data[agent_id]['client_id']
        client_user_id = user_temp_data[agent_id]['client_user_id']
        
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
            template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\6. Заявление в СТО представитель.docx"
            output_filename = "6. Заявление в СТО представитель.docx"
        else:
            template_path = "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\6. Заявление в СТО.docx"
            output_filename = "6. Заявление в СТО.docx"
        
        # Заполняем шаблон
        replace_words_in_word(
            ["{{ СТО }}", "{{ ИНН_СТО }}", "{{ Индекс_СТО }}", "{{ Адрес_СТО }}", "{{ ФИО }}", 
            "{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", 
            "{{ Паспорт_когда }}", "{{ Номер_направления_СТО }}", "{{ Страховая }}", "{{ Дата_ДТП }}", 
            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Дата_предоставления_ТС }}", "{{ Марка_модель }}", 
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
            f"clients\\{client_id}\\Документы\\{output_filename}"
        )
        
        # Отправляем документ агенту
        try:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            with open(f"clients\\{client_id}\\Документы\\{output_filename}", 'rb') as doc:
                bot.send_document(message.chat.id, doc, caption="📋 Заявление в СТО", reply_markup = keyboard)
        except FileNotFoundError:
            bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
        
        # Уведомляем клиента
        if client_user_id:
            try:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
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
            if 'sto_refusal_data' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['sto_refusal_data']
            if 'client_id' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['client_id']
            if 'client_user_id' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['client_user_id']
            if 'answer_insurance_data' in user_temp_data[agent_id]:
                del user_temp_data[agent_id]['answer_insurance_data']

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
