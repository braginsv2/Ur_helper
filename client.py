from telebot import types
import re
import json
import time
from datetime import datetime, timedelta
from database import (
    DatabaseManager,
    save_client_to_db_with_id_new,
    get_admin_from_db_by_user_id,
    search_clients_by_fio_in_db,
    get_client_from_db_by_client_id,
    get_client_contracts_list
)
from word_utils import create_fio_data_file, replace_words_in_word, get_next_business_date

db = DatabaseManager()


insurance_companies = [
    ('АО "Согаз"', "SOGAZ_client"),
    ('ПАО СК "Росгосстрах"', "Ros_client"),
    ('САО "Ресо-Гарантия"', "Reco_client"),
    ('АО "АльфаСтрахование"', "Alfa_client"),
    ('СПАО "Ингосстрах"', "Ingo_client"),
    ('САО "ВСК"', "VSK_client"),
    ('ПАО «САК «Энергогарант»', "Energo_client"),
    ('АО "ГСК "Югория"', "Ugo_client"),
    ('ООО СК "Согласие"', "Soglasie_client"),
    ('АО «Совкомбанк страхование»', "Sovko_client"),
    ('АО "Макс"', "Maks_client"),
    ('ООО СК "Сбербанк страхование"', "Sber_client"),
    ('АО "Т-Страхование"', "T-ins_client"),
    ('ПАО "Группа Ренессанс Страхование"', "Ren_client"),
    ('АО СК "Чулпан"', "Chul_client")
]

def create_insurance_keyboard(page=0, items_per_page=5):
    """Создает клавиатуру с пагинацией для страховых компаний"""
    keyboard = types.InlineKeyboardMarkup()
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    for name, callback_data in insurance_companies[start_idx:end_idx]:
        keyboard.add(types.InlineKeyboardButton(name, callback_data=callback_data))
    
    row_buttons = []
    
    if page > 0:
        row_buttons.append(types.InlineKeyboardButton('◀️ Назад', callback_data=f'client_ins_page_{page-1}'))
    
    if end_idx < len(insurance_companies):
        row_buttons.append(types.InlineKeyboardButton('Еще ▶️', callback_data=f'client_ins_page_{page+1}'))
    
    if row_buttons:
        keyboard.row(*row_buttons)
    
    keyboard.add(types.InlineKeyboardButton('Другое', callback_data="other_client"))
    
    return keyboard


def setup_client_handlers(bot, user_temp_data):
    """Регистрация обработчиков для самостоятельного оформления клиентом"""
    
    # ========== НАЧАЛО ОФОРМЛЕНИЯ ДОГОВОРА КЛИЕНТОМ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data == "btn_client")
    def btn_client_handler(call):
        """Оформить договор - Клиент проверяет существующие договоры"""
        client_id = call.from_user.id
        # Получаем данные клиента
        client_data = get_admin_from_db_by_user_id(client_id)
        
        if not client_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        start_new_contract_for_client(bot, call, client_id, user_temp_data)
    
    
    @bot.callback_query_handler(func=lambda call: call.data == "client_new_contract")
    def client_new_contract_handler(call):
        """Новый договор с нуля"""
        client_id = call.from_user.id
        start_new_contract_for_client(bot, call, client_id, user_temp_data)
    
    
    def start_new_contract_for_client(bot, call, client_id, user_temp_data):
        """Начало заполнения нового договора с нуля"""
        client_data = get_admin_from_db_by_user_id(client_id)
        print(client_data)
        if not client_data:
            bot.answer_callback_query(call.id, "❌ Данные не найдены", show_alert=True)
            return
        
        # Инициализируем данные
        if client_id not in user_temp_data:
            user_temp_data[client_id] = {}
        
        user_temp_data[client_id]['contract_data'] = {
            'fio': client_data.get('fio', ''),
            'fio_k': client_data.get('fio_k', ''),
            'number': client_data.get('number', ''),
            'city': client_data.get('city_admin', ''),
            'year': str(datetime.now().year)[-2:],
            'user_id': str(client_id),
            'creator_user_id': str(client_id),
            # ПАСПОРТНЫЕ ДАННЫЕ ИЗ БД
            'date_of_birth': client_data.get('date_of_birth', ''),
            'city_birth': client_data.get('city_birth', ''),
            'seria_pasport': client_data.get('seria_pasport', ''),
            'number_pasport': client_data.get('number_pasport', ''),
            'where_pasport': client_data.get('where_pasport', ''),
            'when_pasport': client_data.get('when_pasport', ''),
            'index_postal': client_data.get('index_postal', ''),
            'address': client_data.get('address', '')
        }
        
        ask_accident_type(bot, call, client_id, user_temp_data)
    
    
    def ask_accident_type(bot, call, client_id, user_temp_data):
        """Спросить тип обращения"""
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🚗 Только с ДТП", callback_data="client_accident_dtp")
        btn2 = types.InlineKeyboardButton("📝 Подал заявление", callback_data="client_accident_podal_zayavl")
        btn3 = types.InlineKeyboardButton("🕳 После ямы", callback_data="client_accident_pit")
        btn4 = types.InlineKeyboardButton("❌ У виновника ДТП Нет ОСАГО", callback_data="client_accident_net_osago")
        
        
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        keyboard.add(btn4)

        keyboard.add(types.InlineKeyboardButton("🔄 Назад", callback_data="callback_start"))

        contract_data = user_temp_data[client_id]['contract_data']
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📋 Оформление нового договора\n\n"
                f"👤 ФИО: {contract_data.get('fio', '')}\n"
                f"📱 Телефон: {contract_data.get('number', '')}\n\n"
                f"Выберите тип обращения",
            reply_markup=keyboard
        )
    
    # ========== ОБРАБОТЧИКИ ТИПА ОБРАЩЕНИЯ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("client_accident_"))
    def handle_client_accident_type(call):
        """Обработка выбора типа обращения клиентом"""
        client_id = call.from_user.id
        if call.data == 'client_accident_dtp':
            user_temp_data[client_id]['contract_data']['accident'] = "ДТП"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nНаходитесь на стадии оформления в ГИБДД.\nЗаявление в страховую ещё не подавали.\nПримерная дата первой выплаты (дата через 20 дней)\nПримерная дата завершения дела (дата через 280 дней)\n\nЭвакуатор вызывали?"
        elif call.data == 'client_accident_podal_zayavl':
            user_temp_data[client_id]['contract_data']['accident'] = "Подал заявление"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nЗаявление в страховую подали самостоятельно на выплату или ремонт.\nПримерная дата завершения дела (дата через 280 дней)\n\nЭвакуатор вызывали?"
        elif call.data == 'client_accident_pit':
            user_temp_data[client_id]['contract_data']['accident'] = "После ямы"
            context = f"🤖 Вы попали в ДТП по вине дорожных служб (ямы, люки, остатки ограждений и т.д.)\n\nЭвакуатор вызывали?"
        elif call.data == 'client_accident_net_osago':
            user_temp_data[client_id]['contract_data']['accident'] = "Нет ОСАГО"
            context = f"🤖 Вы попали в ДТП с участием двух и более автомобилей.\nНаходитесь на стадии оформления в ГИБДД.\nДанная ситуация является не страховым случаем.\nКомпенсирует убыток Виновник ДТП.\nПримерная дата завершения дела (дата через 90 дней)\n\nЭвакуатор вызывали?"
        else:
            context = f"Эвакуатор вызывали?"
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Да", callback_data="client_ev_yes")
        btn2 = types.InlineKeyboardButton("Нет", callback_data="client_ev_no")
        btn3 = types.InlineKeyboardButton("◀️ Назад", callback_data="client_new_contract")
        keyboard.add(btn1)
        keyboard.add(btn2)
        keyboard.add(btn3)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=context,
            reply_markup=keyboard
        )
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["client_ev_yes", "client_ev_no"])
    def handle_client_evacuator(call):
        """Обработка эвакуатора"""
        client_id = call.from_user.id

        if call.data == "client_ev_yes":
            user_temp_data[client_id]['contract_data']['ev'] = "Да"
        elif call.data == "client_ev_no":
            user_temp_data[client_id]['contract_data']['ev'] = "Нет"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="dtp_date_today_client"))
        keyboard.add(types.InlineKeyboardButton("📝 Другая дата", callback_data="dtp_date_other_client"))
        keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="client_new_contract"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату ДТП:",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["dtp_date_today_client", "dtp_date_other_client"])
    def handle_dtp_date_choice(call):
        agent_id = call.from_user.id
        
        if call.data == "dtp_date_today_client":
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
            bot.register_next_step_handler(call.message, process_client_dtp_time, agent_id, call.message.message_id)
            
        elif call.data == "dtp_date_other_client":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДТП (ДД.ММ.ГГГГ):"
            )
            bot.register_next_step_handler(call.message, process_client_dtp_date, agent_id, call.message.message_id)    
    
    
    def process_client_dtp_date(message, client_id, prev_msg_id):
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
                bot.register_next_step_handler(msg, process_client_dtp_date, client_id, msg.message_id)
                return
            
            if input_date < three_years_ago:
                msg = bot.send_message(message.chat.id, "❌ Прошло более трех лет!\nВведите корректную дату ДТП:")
                bot.register_next_step_handler(msg, process_client_dtp_date, client_id, msg.message_id)
                return
            
            user_temp_data[client_id]['contract_data']['date_dtp'] = date_text
            msg = bot.send_message(message.chat.id, "Введите время ДТП (ЧЧ:ММ):")
            bot.register_next_step_handler(msg, process_client_dtp_time, client_id, msg.message_id)
            
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату ДТП в формате ДД.ММ.ГГГГ:")
            bot.register_next_step_handler(msg, process_client_dtp_date, client_id, msg.message_id)
            return
    
    
    def process_client_dtp_time(message, client_id, prev_msg_id):
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
            bot.register_next_step_handler(msg, process_client_dtp_time, client_id, msg.message_id)
            return
        
        user_temp_data[client_id]['contract_data']['time_dtp'] = time_text
        
        msg = bot.send_message(message.chat.id, "Введите адрес ДТП:")
        bot.register_next_step_handler(msg, process_client_dtp_address, client_id, msg.message_id)
    
    
    def process_client_dtp_address(message, client_id, prev_msg_id):
        """Обработка адреса ДТП"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        user_temp_data[client_id]['contract_data']['address_dtp'] = message.text.strip()
        
        # Показываем итоговые данные и спрашиваем про доверенность
        show_client_contract_summary(bot, message.chat.id, client_id, user_temp_data)
    
    
    def show_client_contract_summary(bot, chat_id, client_id, user_temp_data):
        """Показ итоговых данных клиенту"""
        # ДОБАВЛЕНО: Проверка и инициализация
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.send_message(chat_id, "❌ Ошибка: данные потеряны")
            return
        
        contract_data = user_temp_data[client_id]['contract_data']
        
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
        btn_yes = types.InlineKeyboardButton("✅ Подтвердить", callback_data="client_power_attorney_yes")
        btn_no = types.InlineKeyboardButton("❌ Отклонить", callback_data="client_power_attorney_no")
        keyboard.add(btn_yes, btn_no)
        
        bot.send_message(chat_id, summary, parse_mode='HTML', reply_markup=keyboard)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("client_power_attorney_"))
    def handle_client_power_attorney(call):
        """Обработка ответа про нотариальную доверенность"""
        client_id = call.from_user.id
        
        # КРИТИЧЕСКИ ВАЖНО: проверяем наличие данных
        if client_id not in user_temp_data:
            bot.answer_callback_query(call.id, "❌ Данные потеряны (сессия истекла)", show_alert=True)
            return
        
        if 'contract_data' not in user_temp_data[client_id]:
            bot.answer_callback_query(call.id, "❌ Данные договора не найдены", show_alert=True)
            return
        
        contract_data = user_temp_data[client_id]['contract_data']
        
        # ОТЛАДКА
        print(f"DEBUG handle_client_power_attorney: client_id={client_id}")
        print(f"DEBUG contract_data keys: {contract_data.keys()}")
        
        if call.data == "client_power_attorney_yes":
            contract_data['status'] = 'Оформлен договор'
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"📝 Данные подтверджены\n\n⏳ Сохраняем договор..."
            )
            
            # Сохраняем в БД и получаем client_id
            try:
                client_contract_id, updated_data = save_client_to_db_with_id_new(contract_data)
                contract_data.update(updated_data)
                contract_data['client_id'] = client_contract_id
                
                # ВАЖНО: обновляем в user_temp_data
                user_temp_data[client_id]['contract_data'] = contract_data
                
                print(f"Договор сохранен клиентом с client_id: {client_contract_id}")
                
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
            except Exception as e:
                print(f"Ошибка сохранения в БД: {e}")
                import traceback
                traceback.print_exc()
                bot.send_message(client_id, "❌ Ошибка сохранения договора. Попробуйте снова.")
                return
            
            # Отправляем клиенту юр договор
            send_legal_contract_to_client(bot, client_id, msg.message_id, contract_data)
            
        else:  # client_power_attorney_no
            try:
                # КРИТИЧЕСКИ ВАЖНО: НЕ изменяем contract_data, работаем с тем что есть
                # Данные УЖЕ в user_temp_data[client_id]['contract_data']
                user_temp_data[client_id]['contract_data'] = contract_data
                # ОТЛАДКА
                print(f"DEBUG Отклонение: contract_data сохранен с ключами: {contract_data.keys()}")
                print(f"DEBUG user_temp_data[{client_id}] содержит: {user_temp_data[client_id].keys()}")
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("✏️ Редактировать данные", callback_data=f"start_edit_contract_client"))
                keyboard.add(types.InlineKeyboardButton("🔄 Назад", callback_data="back_client_contract"))
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Вы отклонили данные договора.\n\nВы можете отредактировать существующие данные.",
                    reply_markup=keyboard
                )

            except Exception as e:
                print(f"Ошибка отклонения данных: {e}")
                import traceback
                traceback.print_exc()
    @bot.callback_query_handler(func=lambda call: call.data == "back_client_contract")
    def show_client_contract_summary_back(call):
        """Показ итоговых данных клиенту"""
        client_id = call.from_user.id
        
        # ДОБАВЛЕНО: проверка данных
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.answer_callback_query(call.id, "❌ Данные потеряны", show_alert=True)
            return
        
        # Удаляем старое сообщение
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # Показываем итоговые данные
        show_client_contract_summary(bot, call.message.chat.id, client_id, user_temp_data)
    @bot.callback_query_handler(func=lambda call: call.data == "start_edit_contract_client")
    def start_edit_contract(call):
        """Начало редактирования отклоненного договора"""
        client_id = call.from_user.id
        
        # Показываем меню редактирования
        show_contract_edit_menu(bot, call.message.chat.id, call.message.message_id, client_id, user_temp_data)


    def show_contract_edit_menu(bot, chat_id, message_id, client_id, user_temp_data):
        """Показать меню редактирования договора"""
        print(f"DEBUG show_contract_edit_menu: client_id={client_id}")
        print(f"DEBUG user_temp_data keys: {user_temp_data.get(client_id, {}).keys()}")
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.send_message(chat_id, "❌ Ошибка: данные для редактирования не найдены")
            return
        
        contract_data = user_temp_data[client_id]['contract_data']
        
        # Формируем текст с текущими данными
        text = "📋 <b>Текущие данные договора:</b>\n\n"
        text += f"👤 ФИО: {contract_data.get('fio', 'не указано')}\n"
        text += f"📅 Дата рождения: {contract_data.get('date_of_birth', 'не указана')}\n"
        text += f"🏙 Город: {contract_data.get('city', 'не указано')}\n"
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
        keyboard.add(types.InlineKeyboardButton("✏️ ФИО", callback_data="edit_client_field_fio"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата рождения", callback_data="edit_client_field_date_of_birth"))
        keyboard.add(types.InlineKeyboardButton("✏️ Город", callback_data="edit_client_field_city"))
        keyboard.add(types.InlineKeyboardButton("✏️ Серия паспорта", callback_data="edit_client_field_seria_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Номер паспорта", callback_data="edit_client_field_number_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Кем выдан паспорт", callback_data="edit_client_field_where_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата выдачи паспорта", callback_data="edit_client_field_when_pasport"))
        keyboard.add(types.InlineKeyboardButton("✏️ Индекс", callback_data="edit_client_field_index_postal"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес", callback_data="edit_client_field_address"))
        keyboard.add(types.InlineKeyboardButton("✏️ Дата ДТП", callback_data="edit_client_field_date_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Время ДТП", callback_data="edit_client_field_time_dtp"))
        keyboard.add(types.InlineKeyboardButton("✏️ Адрес ДТП", callback_data="edit_client_field_address_dtp"))
        
        # Кнопки действий
        keyboard.add(types.InlineKeyboardButton("✅ Редактирование завершено", callback_data="submit_edited_client_contract"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    @bot.callback_query_handler(func=lambda call: call.data == "submit_edited_client_contract")
    def submit_edited_contract(call):
        """Отправка отредактированного договора на подтверждение"""
        client_id = call.from_user.id
        
        if client_id not in user_temp_data or 'contract_data' not in user_temp_data[client_id]:
            bot.answer_callback_query(call.id, "❌ Данные потеряны", show_alert=True)
            return
        
        # Возвращаемся к показу итоговых данных
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_client_contract_summary(bot, call.message.chat.id, client_id, user_temp_data)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_client_field_"))
    def handle_field_edit(call):
        """Начало редактирования конкретного поля"""
        client_id = call.from_user.id
        field = call.data.replace("edit_client_field_", "")
        
        # КРИТИЧЕСКИ ВАЖНО: сначала проверяем наличие user_temp_data[client_id]
        if client_id not in user_temp_data:
            print(f"DEBUG ERROR: client_id={client_id} НЕ НАЙДЕН в user_temp_data")
            print(f"DEBUG user_temp_data содержит ключи: {user_temp_data.keys()}")
            bot.answer_callback_query(call.id, "❌ Ошибка: данные потеряны", show_alert=True)
            return
        
        # Теперь проверяем contract_data
        if 'contract_data' not in user_temp_data[client_id]:
            print(f"DEBUG ERROR: contract_data НЕ НАЙДЕН для client_id={client_id}")
            print(f"DEBUG user_temp_data[{client_id}] содержит: {user_temp_data[client_id].keys()}")
            bot.answer_callback_query(call.id, "❌ Ошибка: данные договора потеряны", show_alert=True)
            return
        
        # Сохраняем какое поле редактируем
        user_temp_data[client_id]['editing_field'] = field
        
        # Названия полей для отображения
        field_names = {
            'fio': 'ФИО (Иванов Иван Иванович)',
            'date_of_birth': 'Дата рождения (ДД.ММ.ГГГГ)',
            'city': 'Место рождения',
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
        current_value = user_temp_data[client_id]['contract_data'].get(field, 'не указано')
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✏️ Редактирование поля: <b>{field_display}</b>\n\n"
                f"Текущее значение: <code>{current_value}</code>\n\n"
                f"Введите новое значение:",
            parse_mode='HTML'
        )
        
        bot.register_next_step_handler(call.message, process_field_edit, client_id, call.message.message_id, field)


    def process_field_edit(message, agent_id, prev_msg_id, field):
        """Обработка нового значения поля"""
        try:
            bot.delete_message(message.chat.id, prev_msg_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if agent_id not in user_temp_data or 'contract_data' not in user_temp_data[agent_id]:
            bot.send_message(message.chat.id, "❌ Ошибка: сессия редактирования потеряна")
            return
        
        new_value = message.text.strip()
        
        # Валидация в зависимости от типа поля
        validation_error = None
        
        if field in ['date_of_birth', 'when_pasport', 'date_dtp']:
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', new_value):
                validation_error = "❌ Неверный формат даты! Используйте ДД.ММ.ГГГГ"
            else:
                try:
                    datetime.strptime(new_value, "%d.%m.%Y")
                except ValueError:
                    validation_error = "❌ Некорректная дата!"
        
        elif field == 'time_dtp':
            if not re.match(r'^\d{2}:\d{2}$', new_value):
                validation_error = "❌ Неверный формат времени! Используйте ЧЧ:ММ"
        
        elif field == 'number_pasport':
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Номер паспорта должен содержать 6 цифр"
        
        elif field == 'seria_pasport':
            if not new_value.isdigit() or len(new_value) != 4:
                validation_error = "❌ Серия паспорта должна содержать 4 цифры"
        
        elif field == 'index_postal':
            if not new_value.isdigit() or len(new_value) != 6:
                validation_error = "❌ Индекс должен содержать 6 цифр"
        
        elif field == 'fio':
            if len(new_value.split()) < 2:
                validation_error = "❌ Неправильный формат! Введите ФИО заново:"
            else:
                words = new_value.split()
                for word in words:
                    if not word[0].isupper():
                        validation_error = "❌ Каждое слово должно начинаться с заглавной буквы!"
                        break
        
        # Если есть ошибка валидации - запрашиваем снова
        if validation_error:
            msg = bot.send_message(message.chat.id, validation_error + "\n\nВведите значение снова:")
            bot.register_next_step_handler(msg, process_field_edit, agent_id, msg.message_id, field)
            return
        
        # Сохраняем новое значение
        user_temp_data[agent_id]['contract_data'][field] = new_value  # ← ИСПРАВЛЕНО (убрали ['data'])
        
        # Возвращаемся в меню редактирования
        msg = bot.send_message(message.chat.id, f"✅ Поле обновлено!")
        show_contract_edit_menu(bot, message.chat.id, msg.message_id, agent_id, user_temp_data)
    def send_legal_contract_to_client(bot, client_id, message_id, contract_data):
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
        keyboard = types.InlineKeyboardMarkup()
        btn_sign = types.InlineKeyboardButton("✍️ Подписать Юр договор", callback_data="client_sign_legal_contract")
        keyboard.add(btn_sign)

        # Отправляем документ
        try:
            with open(document_path, 'rb') as document_file:
                msg = bot.send_document(
                    client_id, 
                    document_file,
                    caption=contract_text, 
                    parse_mode='HTML', 
                    reply_markup=keyboard
                )
        except Exception as e:
            print(f"Ошибка отправки документа: {e}")
            bot.send_message(client_id, "❌ Ошибка при формировании документа")
            return
        
        # Отправляем текст с кнопкой
        
        bot.delete_message(msg.chat.id, message_id)
    
    @bot.callback_query_handler(func=lambda call: call.data == "client_sign_legal_contract")
    def client_sign_legal_contract(call):
        """Подписание юридического договора клиентом"""
        client_id = call.from_user.id
        
        contract_data = user_temp_data.get(client_id, {}).get('contract_data', {})
        accident_type = contract_data.get('accident', '')
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
        # Проверяем тип обращения
        if accident_type == "ДТП":
            # Переходим к заполнению заявления в страховую
            msg = bot.send_message(
                chat_id=call.message.chat.id,
                text="✅ Договор успешно оформлен!\nТеперь заполним заявление в страховую.\n\nВведите марку и модель авто:"
            )
            
            bot.register_next_step_handler_by_chat_id(client_id, process_client_car_marks, client_id, msg.message_id, contract_data)
        
        elif accident_type == "После ямы":
            bot.send_message(
                client_id,
                "✅ Договор успешно оформлен!\n\n"
                "Тип обращения: После ямы\n"
            )
            
            # Очищаем данные
            if client_id in user_temp_data:
                user_temp_data.pop(client_id, None)
            
            # Возвращаем в главное меню
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, client_id)
        
        elif accident_type =="Нет ОСАГО":
            keyboard = types.InlineKeyboardMarkup()
            btn_yes = types.InlineKeyboardButton("✅ Да", callback_data=f"NoOsago_yes_{contract_data['client_id']}")
            btn_no = types.InlineKeyboardButton("❌ Заполнить позже", callback_data=f"NoOsago_no_{client_id}")
            keyboard.add(btn_yes, btn_no)
            bot.send_message(
                chat_id=call.message.chat.id,
                text = f"✅ Договор успешно оформлен!\n\n"
                       f"Тип обращения: Нет ОСАГО у виновника ДТП\nЗаполнить заявление в ГИБДД?",
                reply_markup = keyboard
            )
        elif accident_type =="Подал заявление":
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
    
    
    # ========== ЗАПОЛНЕНИЕ ЗАЯВЛЕНИЯ В СТРАХОВУЮ ==========
    
    def process_client_car_marks(message, client_id, user_message_id, contract_data):
        """Обработка марки и модели авто"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        contract_data['marks'] = message.text.strip()
        
        msg = bot.send_message(message.chat.id, "Введите номер авто (например, А123БВ77):")
        bot.register_next_step_handler(msg, process_client_car_number, client_id, msg.message_id, contract_data)
    
    
    def process_client_car_number(message, client_id, user_message_id, contract_data):
        """Обработка номера авто"""
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
            contract_data['car_number'] = car_number
            msg = bot.send_message(message.chat.id, "Введите год выпуска авто (например, 2025):")
            bot.register_next_step_handler(msg, process_client_car_year, client_id, msg.message_id, contract_data)
        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер авто\n"
                "Пример: А123БВ77 или А123БВ777\n"
                "Все буквы должны быть заглавными!"
            )
            bot.register_next_step_handler(msg, process_client_car_number, client_id, msg.message_id, contract_data)
    
    
    def process_client_car_year(message, client_id, user_message_id, contract_data):
        """Обработка года выпуска авто"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите корректный год выпуска авто (например, 2025):")
            bot.register_next_step_handler(msg, process_client_car_year, client_id, msg.message_id, contract_data)
        else:
            contract_data['year_auto'] = int(message.text.replace(" ", ""))
            
            user_temp_data[client_id]['contract_data'] = contract_data
            
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="client_STS")
            btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="client_PTS")
            keyboard.add(btn1)
            keyboard.add(btn2)

            bot.send_message(
                message.chat.id, 
                "Выберите документ о регистрации ТС:", 
                reply_markup=keyboard
            )
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["client_STS", "client_PTS", "client_DKP"])
    def callback_client_docs(call):
        """Обработка выбора документа о регистрации ТС"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']
        
        if call.data == "client_STS":
            data['docs'] = "СТС"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_seria_docs, client_id, message.message_id, data)

        elif call.data == "client_PTS":
            data['docs'] = "ПТС"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_seria_docs, client_id, message.message_id, data)
        else: 
            data['docs'] = "ДКП"
            data['seria_docs'] = "-"
            data['number_docs'] = "-"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату ДКП (ДД.ММ.ГГГГ):",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_data_docs, client_id, message.message_id, data)
    
    
    def process_client_seria_docs(message, client_id, user_message_id, data):
        """Обработка серии документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['seria_docs'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите номер документа о регистрации ТС:")
        bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)
    
    
    def process_client_number_docs(message, client_id, user_message_id, data):
        """Обработка номера документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if message.text.isdigit():
            data['number_docs'] = message.text.strip()
            msg = bot.send_message(
                message.chat.id,
                "Введите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ:"
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер документа о регистрации ТС (только цифры):"
            )
            bot.register_next_step_handler(msg, process_client_number_docs, client_id, msg.message_id, data)
    
    
    def process_client_data_docs(message, client_id, user_message_id, data):
        """Обработка даты выдачи документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data['data_docs'] = message.text.strip()
            
            user_temp_data[client_id]['contract_data'] = data
            
            # Создаем клавиатуру с пагинацией (первая страница)
            keyboard = create_insurance_keyboard(page=0)
            
            bot.send_message(
                message.chat.id, 
                "Выберите страховую компанию:", 
                reply_markup=keyboard
            )
            
        except ValueError:
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ:"
            )
            bot.register_next_step_handler(msg, process_client_data_docs, client_id, msg.message_id, data)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('client_ins_page_'))
    def handle_client_insurance_pagination(call):
        """Обрабатывает пагинацию страховых компаний для клиента"""
        try:
            page = int(call.data.split('_')[3])
            keyboard = create_insurance_keyboard(page)
            
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error handling pagination: {e}")
    
    
    @bot.callback_query_handler(func=lambda call: call.data in ["Reco_client", "Ugo_client", "SOGAZ_client", "Ingo_client", "Ros_client", "Maks_client", "Energo_client", "Sovko_client", "Alfa_client", "VSK_client", "Soglasie_client", "Sber_client", "T-ins_client", "Ren_client", "Chul_client", "other_client"] and call.from_user.id in user_temp_data and 'contract_data' in user_temp_data[call.from_user.id])
    def callback_client_insurance(call):
        """Обработка выбора страховой компании клиентом"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['contract_data']
        insurance_mapping = {
            "SOGAZ_client": 'АО "Согаз"',
            "Ros_client": 'ПАО СК "Росгосстрах"',
            "Reco_client": 'САО "Ресо-Гарантия"',
            "Alfa_client": 'АО "АльфаСтрахование"',
            "Ingo_client": 'СПАО "Ингосстрах"',
            "VSK_client": 'САО "ВСК"',
            "Energo_client": 'ПАО «САК «Энергогарант»',
            "Ugo_client": 'АО "ГСК "Югория"',
            "Soglasie_client": 'ООО СК "Согласие"',
            "Sovko_client": 'АО «Совкомбанк страхование»',
            "Maks_client": 'АО "Макс"',
            "Sber_client": 'ООО СК "Сбербанк страхование"',
            "T-ins_client": 'АО "Т-Страхование"',
            "Ren_client": 'ПАО "Группа Ренессанс Страхование"',
            "Chul_client": 'АО СК "Чулпан"'
        }
        
        if call.data in insurance_mapping:
            data['insurance'] = insurance_mapping[call.data]
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию страхового полиса:",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_seria_insurance, client_id, message.message_id, data)
        else: 
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название страховой компании:",
                reply_markup=None
            )
            bot.register_next_step_handler(message, process_client_other_insurance, client_id, message.message_id, data)
    
    
    def process_client_other_insurance(message, client_id, user_message_id, data):
        """Обработка другой страховой компании"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['insurance'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите серию страхового полиса:")
        bot.register_next_step_handler(msg, process_client_seria_insurance, client_id, msg.message_id, data)
    
    
    def process_client_seria_insurance(message, client_id, user_message_id, data):
        """Обработка серии страхового полиса"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['seria_insurance'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите номер страхового полиса:")
        bot.register_next_step_handler(msg, process_client_number_insurance, client_id, msg.message_id, data)
    
    
    def process_client_number_insurance(message, client_id, user_message_id, data):
        """Обработка номера страхового полиса"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['number_insurance'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите дату страхового полиса в формате ДД.ММ.ГГГГ:")
        bot.register_next_step_handler(msg, process_client_date_insurance, client_id, msg.message_id, data)
    
    
    def process_client_date_insurance(message, client_id, user_message_id, data):
        """Обработка даты страхового полиса"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data['date_insurance'] = message.text.strip()
            msg = bot.send_message(message.chat.id, "Введите ФИО виновника ДТП в формате: Иванов Иван Иванович")
            bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите дату страхового полиса в формате ДД.ММ.ГГГГ:")
            bot.register_next_step_handler(msg, process_client_date_insurance, client_id, msg.message_id, data)
    
    
    def process_client_fio_culp(message, client_id, user_message_id, data):
        """Обработка ФИО виновника"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        if len(message.text.split()) < 2:
            msg = bot.send_message(message.chat.id, "❌ Неправильный формат ввода!\nВведите ФИО виновника ДТП в формате: Иванов Иван Иванович")
            bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():
                    msg = bot.send_message(message.chat.id, "❌ Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО виновника ДТП в формате: Иванов Иван Иванович")
                    bot.register_next_step_handler(msg, process_client_fio_culp, client_id, msg.message_id, data)
                    return
            
            data['fio_culp'] = message.text.strip()
            msg = bot.send_message(message.chat.id, "Введите марку, модель авто виновника ДТП:")
            bot.register_next_step_handler(msg, process_client_marks_culp, client_id, msg.message_id, data)
    
    
    def process_client_marks_culp(message, client_id, user_message_id, data):
        """Обработка марки авто виновника"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['marks_culp'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите номер авто виновника ДТП:")
        bot.register_next_step_handler(msg, process_client_number_auto_culp, client_id, msg.message_id, data)
    
    
    def process_client_number_auto_culp(message, client_id, user_message_id, data):
        """Обработка номера авто виновника - ФИНАЛ"""
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
            data['number_auto_culp'] = str(car_number)
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
                # Продолжаем с текущими данными
            
            create_fio_data_file(data)
            
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
                with open(f"clients\\{data['client_id']}\\Документы\\{output_filename}", 'rb') as document_file:
                    bot.send_document(
                        message.chat.id, 
                        document_file,
                    )   
            except FileNotFoundError:
                bot.send_message(message.chat.id, f"Файл не найден")

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"view_contract_{data['client_id']}"))    
            bot.send_message(
                client_id,
                "✅ Заявление в страховую успешно сформировано! Загрузите фото с ДТП в личном кабинете.",
                reply_markup=keyboard
            )
            
            # Очищаем временные данные
            if client_id in user_temp_data:
                user_temp_data.pop(client_id, None)
            
        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер авто виновника ДТП\n"
                "Пример: А123БВ77 или А123БВ777\n"
                "Все буквы должны быть заглавными!"
            )
            bot.register_next_step_handler(msg, process_client_number_auto_culp, client_id, msg.message_id, data)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("dop_osm_yes_"))
    def handle_dop_osm_yes(call):
        """Клиент согласен на доп осмотр"""
        client_id = call.data.replace("dop_osm_yes_", "")

        contract = get_client_from_db_by_client_id(client_id)
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
        
        # Сохраняем в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}

        user_temp_data[user_id]['dop_osm_data'] = data
        user_temp_data[user_id]['client_id'] = client_id

        # Обновляем статус в БД
        from database import DatabaseManager
        db = DatabaseManager()
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE clients 
                    SET data_json = jsonb_set(
                        COALESCE(data_json::jsonb, '{}'::jsonb),
                        '{dop_osm_answer}',
                        '"Yes"'
                    )
                    WHERE client_id = %s
                """, (client_id,))
                conn.commit()
        
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
        bot.register_next_step_handler(msg2, Nv_ins, data, user_message_id, msg.message_id)

    def Nv_ins(message, data, user_message_id, message_id):
        try:
            bot.delete_message(message.chat.id, message_id)
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"Nv_ins": message.text})
        msg = bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

    def Na_ins(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"Na_ins": message.text})
        msg = bot.send_message(message.chat.id, text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)
    
    def date_Na_ins(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_Na_ins": message.text})

            msg = bot.send_message(message.chat.id, text="Введите адрес своего СТО")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, address_sto_main, data, user_message_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)

    def address_sto_main(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"address_sto_main": message.text})
        msg = bot.send_message(message.chat.id, text="Введите дату записи в свое СТО для дополнительного осмотра в формате ДД.ММ.ГГГГ")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_sto_main, data, user_message_id)

    def date_sto_main(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_sto_main": message.text})
            msg = bot.send_message(message.chat.id, text="Введите время записи в свое СТО для дополнительного осмотра в формате ЧЧ:ММ".format(message.from_user))
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, time_sto_main, data, user_message_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату записи в свое СТО для дополнительного осмотра в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_sto_main, data, user_message_id)

    def time_sto_main(message, data, user_message_id):
        user_id = message.from_user.id
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        if len(message.text) != 5 or message.text.count(':') != 1:
            msg = bot.send_message(
                message.chat.id,
                "Неправильный формат времени!\n"
                "Введите время записи в свое СТО для дополнительного осмотра в формате ЧЧ:ММ (например: 14:30)"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, time_sto_main, data, user_message_id)
            return
        try:
    
            datetime.strptime(message.text, "%H:%M")

            data.update({"time_sto_main": message.text})
            data.update({"dop_osm": "Yes"})
            data.update({"data_dop_osm": str(datetime.now().strftime("%d.%m.%Y"))})
            if data.get('status', '') not in ['Ожидание претензии', 'Составлена претензия', 'Составлено заявление к Фин.омбудсмену', 'Деликт', 'Завершен', 'Составлено исковое заявление']: 
                data.update({"status": "Подано заявление на дополнительный осмотр"})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                           
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            
            create_fio_data_file(data)
            if data.get("N_dov_not", '') != '':
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", 
                                "{{ NДоверенности }} ", "{{ Дата_доверенности }}", "{{ Представитель }}", "{{ Телефон_представителя }}",
                                "{{ Nакта_осмотра }}", "{{ Дата }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_осмотра }}",
                                "{{ Дата_свое_СТО }}","{{ Время_свое_СТО }}","{{ Адрес_свое_СТО }}", "{{ Телефон }}", 
                                "{{ Дата_заявления_доп_осмотр }}"],
                                [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_not"]), str(data["number_not"]),
                                    str(data["Na_ins"]), str(data["date_ins"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_Na_ins"]), str(data["date_sto_main"]),
                                    str(data["time_sto_main"]), str(data["address_sto_main"]), str(data["number"]),
                                    str(data["data_dop_osm"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\4. Заявление о проведении доп осмотра\\4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx")
                try:
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            else:
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                                "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}",
                                "{{ Паспорт_когда }}", "{{ Nакта_осмотра }}", "{{ Дата }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_осмотра }}",
                                "{{ Дата_свое_СТО }}","{{ Время_свое_СТО }}","{{ Адрес_свое_СТО }}", "{{ Телефон }}",
                                "{{ Дата_заявления_доп_осмотр }}"],
                                [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["Na_ins"]), str(data["date_ins"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_Na_ins"]), str(data["date_sto_main"]),
                                    str(data["time_sto_main"]), str(data["address_sto_main"]), str(data["number"]),
                                    str(data["data_dop_osm"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\4. Заявление о проведении доп осмотра\\4. Заявление о проведении дополнительного осмотра автомобиля.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля.docx")
                try:
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
        except ValueError:
            msg = bot.send_message(
                message.chat.id, 
                "Неправильный формат времени!\n"
                "Введите время записи в свое СТО в формате ЧЧ:ММ (например: 14:30)"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, time_sto_main, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("dop_osm_no_"))
    def handle_dop_osm_no(call):
        """Клиент не согласен на доп осмотр"""
        client_id = call.data.replace("dop_osm_no_", "")
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Спасибо за ответ! Если передумаете, в личном кабинете можно составить заявление."
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("client_answer_insurance_"))
    def callback_client_answer_insurance(call):
        """Ответ от страховой от агента"""
        agent_id = call.from_user.id
        client_id = call.data.replace("client_answer_insurance_", "")
        
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
        keyboard.add(types.InlineKeyboardButton("✅ Да", callback_data=f"answer_yes_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("❌ Нет", callback_data=f"answer_no_{client_id}"))
        keyboard.add(types.InlineKeyboardButton("📋 У виновника ДТП Нет ОСАГО", callback_data=f"NoOsago_prod_{client_id}"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Есть ли ответ от страховой?",
            reply_markup=keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data.startswith("answer_yes_"))
    def handle_answer_yes(call):
        """Клиент получил ответ от страховой"""
        client_id = call.data.replace("answer_yes_", "")
        user_id = call.from_user.id
        user_temp_data[user_id] ={'client_id': client_id}
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"docsInsYes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"docsInsNo"))
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходимо заявление на выдачу документов из страховой?",
            reply_markup = keyboard
        )
    @bot.callback_query_handler(func=lambda call: call.data in ["docsInsNo"])
    def handle_answer_docs_no(call):
        user_id = call.from_user.id
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data=f"vibor1"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data=f"vibor2"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data=f"vibor3"))
        keyboard.add(types.InlineKeyboardButton("4", callback_data=f"vibor4"))
        bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = "Выберите из предложенных вариантов:\n\n1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n" \
        "2) Страховая компания выдала направление на ремонт, СТО отказала.\n" \
        "3) Страховая выдала направление на ремонт и ремонт произведен.\n" \
        "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.",
        reply_markup = keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["docsInsYes"])
    def handle_answer_docs_yes(call):
        user_id = call.from_user.id
        print(user_temp_data)
        client_id = user_temp_data[user_id]['client_id']
        contract = get_client_from_db_by_client_id(client_id)

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
        data.update({"status": "Подано заяление на выдачу документов из страховой"})
        try:
            from database import save_client_to_db_with_id
            updated_client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
                        
        except Exception as e:
            print(f"⚠️ Ошибка обновления: {e}")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        create_fio_data_file(data)
        if data.get("N_dov_not", '') != '':
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ NДоверенности }}","{{ Дата_доверенности }}", "{{ Представитель }}","{{ Телефон_представителя }}",
                            "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}"],
                            [str(data['insurance']), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                            str(data["number_pasport"]), str(data["where_pasport"]),
                            str(data["when_pasport"]),str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]),str(data["number_not"]),
                            str(data["date_dtp"]), str(data["time_dtp"]), 
                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), 
                            str(data["marks_culp"]), str(data["number_auto_culp"]), str(data["number"])],
                            "Шаблоны\\1. ДТП\\1. На ремонт\\5. Запрос в страховую о выдаче акта и расчета\\5. Запрос в страховую о выдаче акта и расчёта представитель.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx")
            try:
                with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx", 'rb') as document_file:
                    bot.send_document(
                        call.message.chat.id, 
                        document_file,
                    )   
            except FileNotFoundError:
                bot.send_message(call.message.chat.id, f"Файл не найден")
        else:
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", 
                            "{{ ДР }}", "{{ Паспорт_серия }}","{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}","{{ ФИОк }}", "{{ Телефон }}"],
                            [str(data['insurance']), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                            str(data["number_pasport"]), str(data["where_pasport"]),
                            str(data["when_pasport"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), 
                            str(data["marks_culp"]), str(data["number_auto_culp"]), str(data["fio_k"]), str(data["number"])],
                            "Шаблоны\\1. ДТП\\1. На ремонт\\5. Запрос в страховую о выдаче акта и расчета\\5. Запрос в страховую о выдаче акта и расчёта.docx",
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта.docx")
            try:
                with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта.docx", 'rb') as document_file:
                    bot.send_document(
                        call.message.chat.id, 
                        document_file,
                    )   
            except FileNotFoundError:

                bot.send_message(call.message.chat.id, f"Файл не найден")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data=f"vibor1"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data=f"vibor2"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data=f"vibor3"))
        keyboard.add(types.InlineKeyboardButton("4", callback_data=f"vibor4"))
        bot.send_message(call.message.chat.id, "Выберите из предложенных вариантов:\n\n1) Страховая компания без согласования произвела выплату. Направление на ремонт не выдавалось.\n" \
        "2) Страховая компания выдала направление на ремонт, СТО отказала.\n" \
        "3) Страховая выдала направление на ремонт и ремонт произведен.\n" \
        "4) Страховая компания выдала направление на ремонт, СТО дальше 50 км.",
        reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data in ["vibor1","vibor2","vibor3","vibor4"])
    def handle_vibor(call):
        user_id = call.from_user.id
        client_id = user_temp_data[user_id]['client_id']
        
        if call.data in ["vibor1", "vibor4"]:
            contract = get_client_from_db_by_client_id(client_id)

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
            data.update({"vibor": call.data})
            data.update({"status": "Ожидание претензии"})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)              
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                reply_markup = keyboard
            )

        elif call.data == "vibor3":
            contract = get_client_from_db_by_client_id(client_id)

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
            data.update({"status": "Завершен"})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)              
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Поздравляю с завершением дела!"
            )
            time.sleep(1)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
        elif call.data == "vibor2":

            contract = get_client_from_db_by_client_id(client_id)
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
            data.update({"vibor": call.data})
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название СТО"
            )
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, name_sto, data, user_message_id)
    
    def name_sto(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
  
        data.update({"name_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите ИНН СТО".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, inn_sto, data, user_message_id)
    def inn_sto(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"inn_sto": message.text})
            message = bot.send_message(message.chat.id, text="Введите индекс СТО, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_sto, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, ИНН должен состоять только из цифр!\nВведите ИНН СТО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, inn_sto, data, user_message_id)
    def index_sto(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
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
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"address_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер направления СТО".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, N_sto, data, user_message_id)
    def N_sto(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        data.update({"N_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату предоставления авто на СТО в формате ДД.ММ.ГГГГ")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_sto, data, user_message_id)
    def date_sto(message, data, user_message_id):
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_sto": message.text})
            message = bot.send_message(message.chat.id, text="Введите дату направления на СТО в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату предоставления авто на СТО в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
    def date_napr_sto(message, data, user_message_id):
        user_id = message.from_user.id
        bot.delete_message(message.chat.id, user_message_id)
        bot.delete_message(message.chat.id, message.message_id)
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_napr_sto": message.text})
            data.update({"date_zayav_sto": str(datetime.now().strftime("%d.%m.%Y"))})
            data.update({"status": "Ожидание претензии"})
            try:
                from database import save_client_to_db_with_id
                updated_client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
                            
            except Exception as e:
                print(f"⚠️ Ошибка обновления: {e}")

            create_fio_data_file(data)
            if data.get("N_dov_not", '') != '':
                replace_words_in_word(["{{ СТО }}", "{{ ИНН_СТО }}", "{{ Индекс_СТО }}", 
                                "{{ Адрес_СТО }}", "{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}",
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}","{{ Телефон_представителя }}",
                                "{{ Номер_направления_СТО }}",
                                "{{ Страховая }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_предоставления_ТС }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}",
                                "{{ Дата_Заявления_СТО }}", "{{ ФИОк }}", "{{ Дата }}", "{{ Телефон }}"],
                                [str(data["name_sto"]), str(data["inn_sto"]), str(data["index_sto"]),
                                    str(data["address_sto"]), str(data["fio"]),str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), str(data["number_not"]),
                                    str(data["N_sto"]),
                                    str(data["insurance"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_sto"]), str(data["marks"]), str(data["car_number"]), str(data["date_zayav_sto"]),str(data["fio_k"]),
                                    str(data["date_ins"]), str(data["number"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\6. Заявление в СТО представитель.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Заявление в СТО представитель.docx")
                try:
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Заявление в СТО представитель.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            else:
                replace_words_in_word(["{{ СТО }}", "{{ ИНН_СТО }}", "{{ Индекс_СТО }}", 
                                "{{ Адрес_СТО }}", "{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}",
                                "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}","{{ Номер_направления_СТО }}",
                                "{{ Страховая }}","{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ Дата_предоставления_ТС }}", "{{ Марка_модель }}", "{{ Nавто_клиента }}",
                                "{{ Дата_Заявления_СТО }}", "{{ ФИОк }}", "{{ Дата }}", "{{ Телефон }}"],
                                [str(data["name_sto"]), str(data["inn_sto"]), str(data["index_sto"]),
                                    str(data["address_sto"]), str(data["fio"]),str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["N_sto"]),
                                    str(data["insurance"]), str(data["date_dtp"]), str(data["time_dtp"]),str(data["address_dtp"]), 
                                    str(data["date_sto"]), str(data["marks"]), str(data["car_number"]), str(data["date_zayav_sto"]),str(data["fio_k"]),
                                    str(data["date_ins"]), str(data["number"])],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\6. Заявление в СТО.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Заявление в СТО.docx")
                try:
                    with open("clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Заявление в СТО.docx", 'rb') as document_file:
                        bot.send_document(
                            message.chat.id, 
                            document_file,
                        )   
                except FileNotFoundError:
                    bot.send_message(message.chat.id, f"Файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
            bot.send_message(message.chat.id, "✅ Ваша претензия формируется. Мы сообщим вам, когда она будет готова!\nУбедитесь, что нотариальная доверенность загружена, а юридические услуги оплачены в личном кабинете.",
                             reply_markup = keyboard)

        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("answer_no_"))
    def handle_answer_no(call):
        """Клиент не получил ответ от страховой"""
        client_id = call.data.replace("answer_no_", "")
        user_id = call.from_user.id
        user_temp_data[user_id] ={'client_id': client_id}
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"docsInsYes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"docsInsNo"))
        message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Необходимо заявление на выдачу документов из страховой?",
            reply_markup = keyboard
        )
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


