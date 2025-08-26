import telebot
from telebot import types
from config import TOKEN
import dtp
import pit
import no_osago
from word_utils import create_fio_data_file, export_clients_db_to_excel
import json
import sqlite3
import time
import os
from database import DatabaseManager, get_client_from_db_by_client_id, search_clients_by_fio_in_db
from telebot.apihelper import ApiException
from telebot.handler_backends import ContinueHandling, CancelUpdate
bot = telebot.TeleBot(TOKEN)
db = DatabaseManager()


@bot.message_handler(commands=['start'])
def start_handler(message):
    clear_chat_history_optimized(message, 50)
    keyboard = types.InlineKeyboardMarkup()
    
    btn1 = types.InlineKeyboardButton("Добавить клиента", callback_data="btn_new_client")
    btn2 = types.InlineKeyboardButton("Искать в базе", callback_data="btn_search_database")
    btn3 = types.InlineKeyboardButton("Скачать базу данных", callback_data="btn_output")
    keyboard.add(btn1)
    keyboard.add(btn2)
    keyboard.add(btn3)
    bot.send_message(
        message.chat.id, 
        "Привет! Выберите дальнейшие действия", 
        reply_markup=keyboard
    )
def callback_client_details2(message, client_id):
    """Показываем детали клиента и проверяем answer_ins"""

    print(f"DEBUG callback_client_details: client_id = {client_id}")
    try:
        user_id = message.from_user.id
        client = get_client_from_db_by_client_id(client_id)
        if not client:
            bot.send_message(message.chat.id, f"❌ Клиент не найден")
            return

        try:
            if client.get('data_json'):
                client_data = json.loads(client['data_json'])
            else:
                client_data = {}
        except (json.JSONDecodeError, TypeError):
            client_data = {}
        
        details = f"""👤 Детали клиента:

📋 ID: {client['client_id']}
👤 ФИО: {client['fio']}
📱 Телефон: {client.get('number', 'Не указан')}
🚗 Автомобиль: {client.get('car_number', 'Не указан')}
📅 Дата ДТП: {client.get('date_dtp', 'Не указана')}
🕐 Время ДТП: {client_data.get('time_dtp', 'Не указано')}
📍 Адрес ДТП: {client_data.get('address_dtp', 'Не указан')}
🏢 Страховая: {client.get('insurance', 'Не указана')}
🆔 Собственник: {'Да' if client_data.get('sobstvenik') == 'Yes' else 'Нет'}
"""
        dop_osm =client.get('dop_osm', '') or client_data.get('dop_osm', '')
        answer_ins = client.get('answer_ins', '') or client_data.get('answer_ins', '')
        analis_ins = client.get('analis_ins', '') or client_data.get('analis_ins', '')
        pret = client.get('pret', '') or client_data.get('pret', '')
        pret_sto = client.get('pret_sto', '') or client_data.get('pret_sto', '')
        ombuc = client.get('ombuc', '') or client_data.get('ombuc', '')
        keyboard = types.InlineKeyboardMarkup()
        del client['data_json']
        time.sleep(0.5)
        dtp.user_temp_data[user_id] = client
        if client['accident']=='dtp' and client['Done'] !="Yes":
            if (not dop_osm or dop_osm == '') and (not answer_ins or answer_ins == ''):
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data="dopOsm"
                ))
            elif not answer_ins or answer_ins == '':
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"continuefilling"
                ))
            elif ((analis_ins == '') or (not analis_ins)) and (answer_ins != ''):
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"next"))
            elif (pret_sto == '') or (not pret_sto):
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"nextPrSto"))
            elif ((pret == '') or (not pret)) and (answer_ins != '') and (analis_ins != ''):
    
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"nextPr"))
            elif ((ombuc == '') or (not ombuc)) and (answer_ins != '') and (analis_ins != '') and (pret != ''):
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"nextO"))
            elif answer_ins =="NOOSAGO":
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"IskNOOSAGO"))
        elif client['accident']=='pit' and client['Done'] !="Yes":
            if analis_ins =="Yes":
                user_id = message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data="pit_next"))
        keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database"))
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="btn_main_menu"))
        keyboard.add(types.InlineKeyboardButton("Редактирование данных", callback_data="edit_db"))
        keyboard.add(types.InlineKeyboardButton("Просмотр данных", callback_data="view_db"))
        keyboard.add(types.InlineKeyboardButton("Просмотр ранее созданных документов", callback_data="view_docs"))
        keyboard.add(types.InlineKeyboardButton("Загрузить документы", callback_data="download_docs"))
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=details,
            reply_markup=keyboard
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
        print(f"Ошибка получения данных клиента: {e}")
dtp.init_bot(bot, start_handler, callback_client_details2)
pit.init_bot(bot, start_handler, callback_client_details2)
no_osago.init_bot(bot, start_handler, callback_client_details2)

@bot.callback_query_handler(func=lambda call: call.data == "btn_new_client")
def callback_handler(call):
    clear_chat_history_optimized(call.message, 100)
    import dtp
    import pit
    import no_osago
    keyboard = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton("Только с ДТП", callback_data="btn_dtp")
    btn2 = types.InlineKeyboardButton("Подал заявление", callback_data="btn_podal_zayavl")
    btn3 = types.InlineKeyboardButton("После ямы", callback_data="btn_pit")
    btn4 = types.InlineKeyboardButton("Нет Осаго", callback_data="btn_net_osago")
    keyboard.add(btn1)
    keyboard.add(btn3)
    bot.send_message(
        call.message.chat.id, 
        "Выберите дальнейшие действия", 
        reply_markup=keyboard
    )
@bot.callback_query_handler(func=lambda call: call.data == "btn_output")
def callback_output(call):
    chat_id = call.message.chat.id
    file_path = "clients_export.xlsx"
    
    try:
        # Уведомляем о начале процесса
        bot.send_message(
            chat_id,
            "⏳ База данных выгружается, подождите...",
            reply_markup=None
        )
        
        # Выполняем экспорт
        success = export_clients_db_to_excel("clients.db", file_path)
        
        if success and os.path.exists(file_path):
            # Отправляем файл
            with open(file_path, 'rb') as document_file:
                bot.send_document(
                    chat_id,
                    document_file,
                    caption="📊 Экспорт базы данных клиентов"
                )
            
            # Удаляем файл после успешной отправки
            try:
                os.remove(file_path)
                print(f"✅ Файл {file_path} успешно удален")
            except OSError as e:
                print(f"⚠️ Ошибка при удалении файла: {e}")
            

            
        else:
            bot.send_message(
                chat_id, 
                "❌ Ошибка при создании файла экспорта. Проверьте логи."
            )
    
    except Exception as e:
        # Если произошла ошибка, все равно пытаемся удалить файл
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        bot.send_message(
            chat_id,
            f"❌ Произошла ошибка при экспорте: {str(e)}"
        )
        print(f"Ошибка в callback_output: {e}")
    
    finally:
        # Возвращаемся в главное меню
        start_handler(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "btn_search_database")
def callback_search_database(call):
    message = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🔍 Введите фамилию и имя клиента для поиска:",
        reply_markup=None
    )
    
    # Регистрируем следующий обработчик для ввода поискового запроса
    bot.register_next_step_handler(message, search_clients_handler)

def search_clients_by_fio(search_term):
    """Улучшенный поиск клиентов по ФИО"""
    
    print(f"Поиск клиентов: '{search_term}'")
    
    db_manager = DatabaseManager()
    conn = sqlite3.connect(db_manager.db_path)
    cursor = conn.cursor()
    
    # Проверяем наличие записей в базе
    cursor.execute("SELECT COUNT(*) FROM clients")
    total_count = cursor.fetchone()[0]
    print(f"Всего записей в базе: {total_count}")
    
    if total_count == 0:
        conn.close()
        return []
    
    results = []
    search_term = search_term.strip()
    
    # 1. Поиск точного совпадения
    exact_patterns = [
        search_term,
        search_term.lower(),
        search_term.upper(),
        search_term.title()
    ]
    
    for pattern in exact_patterns:
        query = '''
        SELECT id, client_id, fio, number, car_number, date_dtp, created_at, 
               COALESCE(data_json, '{}') as data_json
        FROM clients 
        WHERE fio = ?
        ORDER BY id DESC
        '''
        
        try:
            cursor.execute(query, (pattern,))
            exact_results = cursor.fetchall()
            if exact_results:
                results.extend(exact_results)
                print(f"Найдено точных совпадений: {len(exact_results)}")
                break
        except Exception as e:
            print(f"Ошибка точного поиска: {e}")
            continue
    
    # 2. Если точного совпадения нет, ищем частичные совпадения
    if not results:
        partial_patterns = [
            f"%{search_term}%",
            f"%{search_term.lower()}%",
            f"%{search_term.upper()}%",
            f"%{search_term.title()}%"
        ]
        
        for pattern in partial_patterns:
            query = '''
            SELECT id, client_id, fio, number, car_number, date_dtp, created_at, 
                   COALESCE(data_json, '{}') as data_json
            FROM clients 
            WHERE fio LIKE ?
            ORDER BY id DESC
            '''
            
            try:
                cursor.execute(query, (pattern,))
                partial_results = cursor.fetchall()
                if partial_results:
                    results.extend(partial_results)
                    print(f"Найдено частичных совпадений: {len(partial_results)}")
                    break
            except Exception as e:
                print(f"Ошибка частичного поиска: {e}")
                continue
    
    # 3. Поиск по отдельным словам (фамилия + имя)
    if not results:
        search_words = search_term.split()
        if len(search_words) >= 2:
            first_word = search_words[0].strip()
            second_word = search_words[1].strip()
            
            # Различные варианты регистра для каждого слова
            word_variants = []
            for word in [first_word, second_word]:
                word_variants.append([
                    word,
                    word.lower(),
                    word.upper(),
                    word.title()
                ])
            
            # Пробуем все комбинации
            for first_variants in word_variants[0]:
                for second_variants in word_variants[1]:
                    query = '''
                    SELECT id, client_id, fio, number, car_number, date_dtp, created_at, 
                           COALESCE(data_json, '{}') as data_json
                    FROM clients 
                    WHERE fio LIKE ? AND fio LIKE ?
                    ORDER BY id DESC
                    '''
                    
                    try:
                        cursor.execute(query, (f"%{first_variants}%", f"%{second_variants}%"))
                        word_results = cursor.fetchall()
                        if word_results:
                            results.extend(word_results)
                            print(f"Найдено по словам '{first_variants}' + '{second_variants}': {len(word_results)}")
                            break
                    except Exception as e:
                        print(f"Ошибка поиска по словам: {e}")
                        continue
                
                if results:
                    break
    
    # 4. Поиск только по первому слову (фамилии)
    if not results:
        first_word = search_term.split()[0] if search_term.split() else search_term
        first_word_variants = [
            first_word,
            first_word.lower(),
            first_word.upper(),
            first_word.title()
        ]
        
        for variant in first_word_variants:
            query = '''
            SELECT id, client_id, fio, number, car_number, date_dtp, created_at, 
                   COALESCE(data_json, '{}') as data_json
            FROM clients 
            WHERE fio LIKE ?
            ORDER BY id DESC
            '''
            
            try:
                cursor.execute(query, (f"%{variant}%",))
                surname_results = cursor.fetchall()
                if surname_results:
                    results.extend(surname_results)
                    print(f"Найдено по фамилии '{variant}': {len(surname_results)}")
                    break
            except Exception as e:
                print(f"Ошибка поиска по фамилии: {e}")
                continue
    
    conn.close()
    
    # Удаляем дубликаты по client_id
    unique_results = []
    seen_client_ids = set()
    
    for result in results:
        client_id = result[1]  # client_id на позиции 1
        if client_id not in seen_client_ids:
            unique_results.append(result)
            seen_client_ids.add(client_id)
    
    print(f"Уникальных результатов: {len(unique_results)}")
    
    # Преобразуем в словари
    columns = ['id', 'client_id', 'fio', 'number', 'car_number', 'date_dtp', 'created_at', 'data_json']
    result_dicts = [dict(zip(columns, row)) for row in unique_results]
    
    return result_dicts

def search_clients_handler(message):
    """Обработчик поиска клиентов по ФИО"""
    search_term = message.text.strip()
    
    if len(search_term) < 2:
        bot.send_message(message.chat.id, "❌ Введите минимум 2 символа для поиска")
        bot.register_next_step_handler(message, search_clients_handler)
        #return_to_main_menu(message)
        return
    
    try:
        print(f"=== НАЧАЛО ПОИСКА ===")
        print(f"Поисковый запрос: '{search_term}'")
        
        # Отправляем сообщение о начале поиска
        search_msg = bot.send_message(message.chat.id, "🔍 Поиск в базе данных...")
        
        # Выполняем поиск
        results = search_clients_by_fio_in_db(search_term)
        
        # Удаляем сообщение о поиске
        try:
            bot.delete_message(message.chat.id, search_msg.message_id)
        except:
            pass
        
        if not results:
            bot.send_message(message.chat.id, f"❌ Клиенты с ФИО '{search_term}' не найдены")
            return_to_main_menu(message)
            return

        show_search_results(message, results, search_term)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка поиска: {e}")
        print(f"Ошибка поиска: {e}")
        import traceback
        traceback.print_exc()
        return_to_main_menu(message)

def show_search_results(message, results, search_term):
    """Показываем результаты поиска с кнопками"""
    
    response = f"🔍 Найдено клиентов по запросу '{search_term}': {len(results)}\n\n"
    
    keyboard = types.InlineKeyboardMarkup()

    for i, client in enumerate(results[:10], 1):
        response += f"{i}. 📋 ID: {client['client_id']}\n"
        response += f"   👤 {client['fio']}\n"
        response += f"   📱 {client.get('number', 'Не указан')}\n"
        response += f"   🚗 {client.get('car_number', 'Не указан')}\n"
        response += f"   📅 ДТП: {client.get('date_dtp', 'Не указана')}\n"
        response += f"   🕐 Добавлен: {client.get('created_at', 'Не указано')}\n\n"
        
        btn_text = f"{i}. {client['fio'][:15]}..."
        btn_callback = f"client_details_{client['client_id']}"
        keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=btn_callback))
    
    if len(results) > 10:
        response += f"... и еще {len(results) - 10} клиентов"

    keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database"))
    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="btn_main_menu"))
    
    bot.send_message(message.chat.id, response, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("client_details_"))
def callback_client_details(call):
    """Показываем детали клиента и проверяем answer_ins"""
    user_id = call.message.from_user.id
    client_id = call.data.replace("client_details_", "")
    print(f"DEBUG callback_client_details: user_id = {user_id}")
    print(f"DEBUG callback_client_details: client_id = {client_id}")
    try:
        client = get_client_from_db_by_client_id(client_id)
        
        if not client:
            bot.answer_callback_query(call.id, "❌ Клиент не найден")
            return

        try:
            if client.get('data_json'):
                client_data = json.loads(client['data_json'])
            else:
                client_data = {}
        except (json.JSONDecodeError, TypeError):
            client_data = {}
        
        details = f"""👤 Детали клиента:

📋 ID: {client['client_id']}
👤 ФИО: {client['fio']}
📱 Телефон: {client.get('number', 'Не указан')}
🚗 Автомобиль: {client.get('car_number', 'Не указан')}
📅 Дата ДТП: {client.get('date_dtp', 'Не указана')}
🕐 Время ДТП: {client_data.get('time_dtp', 'Не указано')}
📍 Адрес ДТП: {client_data.get('address_dtp', 'Не указан')}
🏢 Страховая: {client.get('insurance', 'Не указана')}
🆔 Собственник: {'Да' if client_data.get('sobstvenik') == 'Yes' else 'Нет'}
"""
        dop_osm =client.get('dop_osm', '') or client_data.get('dop_osm', '')
        answer_ins = client.get('answer_ins', '') or client_data.get('answer_ins', '')
        analis_ins = client.get('analis_ins', '') or client_data.get('analis_ins', '')
        pret = client.get('pret', '') or client_data.get('pret', '')
        pret_sto = client.get('pret_sto', '') or client_data.get('pret_sto', '')
        ombuc = client.get('ombuc', '') or client_data.get('ombuc', '')
        keyboard = types.InlineKeyboardMarkup()
        del client['data_json']
        time.sleep(0.5)
        dtp.user_temp_data[user_id] = client
        if client['accident']=='dtp' and client['Done'] !="Yes":
            if (not dop_osm or dop_osm == '') and (not answer_ins or answer_ins == ''):
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data="dopOsm"
                ))
            elif not answer_ins or answer_ins == '':
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"continuefilling"
                ))
            elif ((analis_ins == '') or (not analis_ins)) and (answer_ins != ''):
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"next"))
            elif (pret_sto == '') or (not pret_sto):
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"nextPrSto"))
            elif ((pret == '') or (not pret)) and (answer_ins != '') and (analis_ins != ''):
    
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"nextPr"))
            elif ((ombuc == '') or (not ombuc)) and (answer_ins != '') and (analis_ins != '') and (pret != ''):
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"nextO"))
            elif answer_ins =="NOOSAGO":
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data=f"IskNOOSAGO"))
        elif client['accident']=='pit' and client['Done'] !="Yes":
            if analis_ins =="Yes":
                user_id = call.message.from_user.id
                dtp.user_temp_data[user_id] = client
                time.sleep(0.5)
                details += "\n⚠️ Данные не полностью заполнены"
                keyboard.add(types.InlineKeyboardButton(
                    "📝 Продолжить заполнение", 
                    callback_data="pit_next"))
        keyboard.add(types.InlineKeyboardButton("🔍 Новый поиск", callback_data="btn_search_database"))
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="btn_main_menu"))
        keyboard.add(types.InlineKeyboardButton("Редактирование данных", callback_data="edit_db"))
        keyboard.add(types.InlineKeyboardButton("Просмотр данных", callback_data="view_db"))
        keyboard.add(types.InlineKeyboardButton("Просмотр ранее созданных документов", callback_data="view_docs"))
        keyboard.add(types.InlineKeyboardButton("Загрузить документы", callback_data="download_docs"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=details,
            reply_markup=keyboard
        )
        return CancelUpdate()
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
        print(f"Ошибка получения данных клиента: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "btn_main_menu")
def callback_main_menu(call):
    """Возврат в главное меню"""
    user_id = call.message.from_user.id
    if user_id in dtp.user_temp_data:
        del dtp.user_temp_data[user_id]
    keyboard = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton("Добавить клиента", callback_data="btn_new_client")
    btn2 = types.InlineKeyboardButton("Искать в базе", callback_data="btn_search_database")
    keyboard.add(btn1)
    keyboard.add(btn2)
    clear_chat_history_optimized(call.message, 30)
    bot.send_message(
        call.message.chat.id,
        "Выберите дальнейшие действия",
        reply_markup=keyboard
    )

def return_to_main_menu(message):
    """Возврат в главное меню через новое сообщение"""
    clear_chat_history_optimized(message, 30)
    user_id = message.from_user.id
    if user_id in dtp.user_temp_data:
        del dtp.user_temp_data[user_id]
    keyboard = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton("Добавить клиента", callback_data="btn_new_client")
    btn2 = types.InlineKeyboardButton("Искать в базе", callback_data="btn_search_database")
    keyboard.add(btn1)
    keyboard.add(btn2)
    bot.send_message(
        message.chat.id,
        "Выберите дальнейшие действия",
        reply_markup=keyboard
    )
@bot.callback_query_handler(func=lambda call: call.data == "edit_db")
def callback_edit_data(call):
    """Обработчик кнопки редактирования данных"""
    try:
        user_id = call.message.from_user.id
        
        # Получаем client_id из temp_data
        client_data = None
        if user_id in dtp.user_temp_data:
            client_data = dtp.user_temp_data[user_id]
        
        if not client_data or 'client_id' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные клиента не найдены")
            return
        
        client_id = client_data['client_id']
        
        # Получаем полные данные клиента из базы данных
        full_client_data = get_client_from_db_by_client_id(client_id)
        
        if not full_client_data:
            bot.answer_callback_query(call.id, "Клиент не найден в базе данных")
            return
        
        fio = full_client_data.get('fio', '')
        
        # Парсим JSON данные если они есть
        try:
            if full_client_data.get('data_json'):
                json_data = json.loads(full_client_data['data_json'])
                # Объединяем основные данные с JSON данными
                merged_data = {**full_client_data, **json_data}
            else:
                merged_data = full_client_data
        except (json.JSONDecodeError, TypeError):
            merged_data = full_client_data
        
        # Удаляем служебные поля
        if 'data_json' in merged_data:
            del merged_data['data_json']
        if 'id' in merged_data:
            del merged_data['id']
        
        # Проверяем существование файла fio_data.txt
        fio_file_path = os.path.join(str(fio), f"{fio}_data.txt")
        
        if not os.path.exists(fio_file_path):
            # Если файла нет, создаем его на основе данных из БД
            try:
                create_fio_data_file(merged_data)
            except Exception as e:
                bot.answer_callback_query(call.id, f"Ошибка создания файла данных: {e}")
                return
        
        # Читаем содержимое файла
        try:
            with open(fio_file_path, 'r', encoding='utf-8') as file:
                file_content = file.read()
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка чтения файла: {e}")
            return
        
        # Формируем сообщение с содержимым файла
        message_text = f"Текущие данные клиента {fio}:\n\n{file_content}\n\nВведите название параметра точно как в файле data.txt (например: 'Паспорт серия клиента'):"
        
        # Сохраняем данные для следующего шага
        if user_id not in dtp.user_temp_data:
            dtp.user_temp_data[user_id] = {}
        dtp.user_temp_data[user_id]['editing_client'] = {
            'client_id': client_id,
            'fio': fio,
            'file_path': fio_file_path,
            'step': 'parameter',
            'client_data': merged_data
        }

        # Отправляем сообщение и регистрируем обработчик
        new_message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
        )

        bot.register_next_step_handler(new_message, handle_parameter_input, user_id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_edit_data: {e}")
@bot.callback_query_handler(func=lambda call: call.data == "view_db")
def callback_view_data(call):
    """Обработчик кнопки редактирования данных"""
    try:
        user_id = call.message.from_user.id
        
        # Получаем client_id из temp_data
        client_data = None
        if user_id in dtp.user_temp_data:
            client_data = dtp.user_temp_data[user_id]
        
        if not client_data or 'client_id' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные клиента не найдены")
            return
        
        client_id = client_data['client_id']
        
        # Получаем полные данные клиента из базы данных
        full_client_data = get_client_from_db_by_client_id(client_id)
        
        if not full_client_data:
            bot.answer_callback_query(call.id, "Клиент не найден в базе данных")
            return
        
        fio = full_client_data.get('fio', '')
        
        # Парсим JSON данные если они есть
        try:
            if full_client_data.get('data_json'):
                json_data = json.loads(full_client_data['data_json'])
                # Объединяем основные данные с JSON данными
                merged_data = {**full_client_data, **json_data}
            else:
                merged_data = full_client_data
        except (json.JSONDecodeError, TypeError):
            merged_data = full_client_data
        
        # Удаляем служебные поля
        if 'data_json' in merged_data:
            del merged_data['data_json']
        if 'id' in merged_data:
            del merged_data['id']
        
        # Проверяем существование файла fio_data.txt
        fio_file_path = os.path.join(str(fio), f"{fio}_data.txt")
        
        if not os.path.exists(fio_file_path):
            # Если файла нет, создаем его на основе данных из БД
            try:
                create_fio_data_file(merged_data)
            except Exception as e:
                bot.answer_callback_query(call.id, f"Ошибка создания файла данных: {e}")
                return
        
        # Читаем содержимое файла
        try:
            with open(fio_file_path, 'r', encoding='utf-8') as file:
                file_content = file.read()
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка чтения файла: {e}")
            return
        
        # Формируем сообщение с содержимым файла
        message_text = f"Текущие данные клиента {fio}:\n\n{file_content}"
        

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Назад", callback_data=f"client_details_{client_id}")
        keyboard.add(btn1)
        # Отправляем сообщение и регистрируем обработчик
        new_message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_view_data: {e}")


def handle_parameter_input(message, user_id):
    """Обработка ввода названия параметра"""
    
    print(f"DEBUG: user_id = {user_id}")
    print(f"DEBUG: user_temp_data keys = {list(dtp.user_temp_data.keys())}")
    print(f"DEBUG: user in user_temp_data = {user_id in dtp.user_temp_data}")

    if user_id not in dtp.user_temp_data or 'editing_client' not in dtp.user_temp_data[user_id]:
        print("DEBUG: Данные редактирования не найдены")
        bot.send_message(message.chat.id, "Ошибка: данные редактирования не найдены")
        return_to_main_menu(message)
        return
    
    parameter_name = message.text.strip()
    
    # Проверяем существование параметра в data.txt и получаем переменную
    field_mapping = load_field_mapping_from_data_file()
    
    db_field = None
    parameter_lower = parameter_name.lower()
    
    # Ищем точное совпадение
    if parameter_lower in field_mapping:
        db_field = field_mapping[parameter_lower]
    else:
        # Ищем частичное совпадение
        for rus_name, field_name in field_mapping.items():
            if parameter_lower == rus_name:
                db_field = field_name
                break
    
    if not db_field:
        bot.send_message(
            message.chat.id,
            f"Параметр '{parameter_name}' не найден в файле data.txt. Введите название точно как в файле."
        )
        bot.register_next_step_handler(message, handle_parameter_input, user_id)
        return
    
    # Сохраняем название параметра и соответствующую переменную
    dtp.user_temp_data[user_id]['editing_client']['parameter'] = parameter_name
    dtp.user_temp_data[user_id]['editing_client']['db_field'] = db_field
    dtp.user_temp_data[user_id]['editing_client']['step'] = 'value'
    
    # Запрашиваем новое значение
    response_message = bot.send_message(
        message.chat.id,
        f"Введите новое значение для параметра '{parameter_name}':"
    )
    
    bot.register_next_step_handler(response_message, handle_value_input, user_id)

def handle_value_input(message, user_id):
    """Обработка ввода нового значения параметра"""

    
    if user_id not in dtp.user_temp_data or 'editing_client' not in dtp.user_temp_data[user_id]:
        bot.send_message(message.chat.id, "Ошибка: данные редактирования не найдены")
        return_to_main_menu(message)
        return
    
    editing_data = dtp.user_temp_data[user_id]['editing_client']
    parameter_name = editing_data['parameter']
    db_field = editing_data['db_field']
    new_value = message.text.strip()
    client_id = editing_data['client_id']
    client_data = editing_data['client_data']
    
    try:
        # Обновляем данные клиента
        client_data[db_field] = new_value
        
        # Пересоздаем файл fio_data.txt с обновленными данными
        create_fio_data_file(client_data)
        
        # Обновляем базу данных
        update_client_in_database(client_id, db_field, new_value)
        
        bot.send_message(
            message.chat.id,
            f"Параметр '{parameter_name}' успешно обновлен на значение '{new_value}'"
        )
        
        # Очищаем временные данные
        if user_id in dtp.user_temp_data and 'editing_client' in dtp.user_temp_data[user_id]:
            del dtp.user_temp_data[user_id]['editing_client']
        
        # Возвращаемся в главное меню
        return_to_main_menu(message)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при обновлении: {e}")
        print(f"Ошибка при обновлении данных: {e}")
        return_to_main_menu(message)

@bot.callback_query_handler(func=lambda call: call.data == "view_docs")
def callback_view_docs(call):
    """Обработчик кнопки просмотра ранее созданных документов"""
    try:
        user_id = call.message.from_user.id
        
        # Получаем ФИО клиента из temp_data
        client_data = None
        if user_id in dtp.user_temp_data:
            client_data = dtp.user_temp_data[user_id]
        
        if not client_data or 'fio' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные клиента не найдены")
            return
        
        fio = client_data['fio']
        client_dir = fio  # Папка с именем клиента
        
        if not os.path.exists(client_dir):
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"Папка документов клиента '{fio}' не найдена",
                reply_markup=types.InlineKeyboardMarkup([
                    [types.InlineKeyboardButton("🏠 Главное меню", callback_data="btn_main_menu")]
                ])
            )
            return
        
        # Получаем список файлов в папке клиента
        files = []
        try:
            for filename in os.listdir(client_dir):
                if os.path.isfile(os.path.join(client_dir, filename)):
                    files.append(filename)
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка чтения папки: {e}")
            return
        
        if not files:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"В папке документов клиента '{fio}' нет файлов",
                reply_markup=types.InlineKeyboardMarkup([
                    [types.InlineKeyboardButton("🏠 Главное меню", callback_data="btn_main_menu")]
                ])
            )
            return
        
        # Сортируем файлы по дате изменения (новые сверху)
        files_with_time = []
        for filename in files:
            file_path = os.path.join(client_dir, filename)
            try:
                mtime = os.path.getmtime(file_path)
                files_with_time.append((filename, mtime))
            except:
                files_with_time.append((filename, 0))
        
        files_with_time.sort(key=lambda x: x[1], reverse=True)
        sorted_files = [f[0] for f in files_with_time]
        
        # Создаем клавиатуру с кнопками файлов
        keyboard = types.InlineKeyboardMarkup()

        # Формируем текст со списком файлов
        message_text = f"Документы клиента '{fio}': {len(sorted_files)}\n\n"
        for i, filename in enumerate(sorted_files, 1):
            message_text += f"{i}. {filename}\n"

        message_text += "\nВыберите номер файла для отправки:"

        # Создаем кнопки с номерами (по 5 кнопок в ряд)
        buttons_per_row = 5
        for i in range(0, len(sorted_files), buttons_per_row):
            row_buttons = []
            for j in range(i, min(i + buttons_per_row, len(sorted_files))):
                button_text = str(j + 1)
                callback_data = f"send_file_{j}"
                row_buttons.append(types.InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard.row(*row_buttons)

        # Кнопка главного меню
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="btn_main_menu"))

        # Сохраняем список файлов и путь к папке для последующей отправки
        if user_id not in dtp.user_temp_data:
            dtp.user_temp_data[user_id] = {}
        dtp.user_temp_data[user_id]['files_list'] = sorted_files
        dtp.user_temp_data[user_id]['client_dir'] = client_dir

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_view_docs: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("send_file_"))
def callback_send_file(call):
    """Обработчик отправки выбранного файла"""
    try:
        user_id = call.message.from_user.id
        
        # Получаем индекс файла
        file_index = int(call.data.replace("send_file_", ""))
        
        # Получаем список файлов и путь к папке из temp_data
        if (user_id not in dtp.user_temp_data or 
            'files_list' not in dtp.user_temp_data[user_id] or 
            'client_dir' not in dtp.user_temp_data[user_id] or
            file_index >= len(dtp.user_temp_data[user_id]['files_list'])):
            bot.answer_callback_query(call.id, "Ошибка: файл не найден")
            return
        
        filename = dtp.user_temp_data[user_id]['files_list'][file_index]
        client_dir = dtp.user_temp_data[user_id]['client_dir']
        file_path = os.path.join(client_dir, filename)
        
        # Проверяем существование файла
        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, "Файл не найден")
            return
        
        # Отправляем файл
        try:
            with open(file_path, 'rb') as file:
                bot.send_document(
                    call.message.chat.id,
                    file,
                    caption=f"Документ: {filename}"
                )
            
            bot.answer_callback_query(call.id, f"Файл {filename} отправлен")
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка отправки файла: {e}")
            print(f"Ошибка отправки файла {filename}: {e}")
        

        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_send_file: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "download_docs")
def callback_download_docs(call):
    """Обработчик кнопки загрузки документов"""
    try:
        user_id = call.message.from_user.id
        print(f"DEBUG callback_download_docs: user_id = {user_id}")
        print(f"DEBUG: user_id in dtp.user_temp_data = {user_id in dtp.user_temp_data}")
        print(f"DEBUG: dtp.user_temp_data keys = {list(dtp.user_temp_data.keys())}")
        # Получаем ФИО клиента из temp_data
        client_data = None
        if user_id in dtp.user_temp_data:
            client_data = dtp.user_temp_data[user_id]
            print(f"DEBUG: client_data keys = {list(client_data.keys()) if client_data else 'None'}")
        else:
            print("DEBUG: Пользователь не найден в temp_data")
        
        if not client_data or 'fio' not in client_data:
            bot.answer_callback_query(call.id, "Ошибка: данные клиента не найдены")
            return
        
        fio = client_data['fio']
        client_dir = fio  # Папка с именем клиента
        
        # Создаем папку клиента если она не существует
        if not os.path.exists(client_dir):
            os.makedirs(client_dir)
        
        # Инициализируем состояние загрузки для пользователя
        if user_id not in dtp.user_temp_data:
            dtp.user_temp_data[user_id] = {}
        
        dtp.user_temp_data[user_id]['uploading_docs'] = {
            'active': True,
            'uploaded_count': 0,
            'uploaded_files': [],
            'client_dir': client_dir,
            'fio': fio
        }
        
        # Создаем клавиатуру с кнопкой завершения
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Завершить загрузку", callback_data="finish_upload"))
        keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel_upload"))
        
        message_text = f"""📁 Загрузка документов для клиента '{fio}'

Отправьте один или несколько документов (В одном сообщении должен быть один документ, файлы любого типа).
Все отправленные файлы будут сохранены в папку клиента.

Когда закончите отправку файлов, нажмите "Завершить загрузку"."""
        
        new_message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            reply_markup=keyboard
        )
        
        # Регистрируем обработчик для получения документов
        bot.register_next_step_handler(new_message, handle_document_upload, user_id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_download_docs: {e}")

def handle_document_upload(message, user_id=None):
    """Обработка загружаемых документов"""
    if user_id is None:
        user_id = message.from_user.id
    
    print(f"DEBUG handle_document_upload: переданный user_id = {user_id}")
    print(f"DEBUG handle_document_upload: message.from_user.id = {message.from_user.id}")
    print(f"DEBUG handle_document_upload: user_id = {user_id}")
    print(f"DEBUG: Получено сообщение, тип: {type(message)}")
    # Проверяем, активна ли загрузка
    if (user_id not in dtp.user_temp_data or 
        'uploading_docs' not in dtp.user_temp_data[user_id] or 
        not dtp.user_temp_data[user_id]['uploading_docs']['active']):
        print(f"DEBUG: Загрузка неактивна для user_id {user_id}")
        print(f"DEBUG: user_id in dtp.user_temp_data = {user_id in dtp.user_temp_data}")
        if user_id in dtp.user_temp_data:
            print(f"DEBUG: ключи пользователя = {list(dtp.user_temp_data[user_id].keys())}")
        return


    client_dir = dtp.user_temp_data[user_id]['uploading_docs']['client_dir']
    print(f"DEBUG: Папка клиента: {client_dir}")
    print(f"DEBUG: Папка существует: {os.path.exists(client_dir)}")
    # Убеждаемся, что папка существует
    if not os.path.exists(client_dir):
        os.makedirs(client_dir)
        print(f"DEBUG: Создана папка: {client_dir}")

    try:
        uploaded_file = None
        filename = None
        
        # Определяем тип отправленного файла
        if message.document:
            uploaded_file = message.document
            filename = uploaded_file.file_name or f"document_{uploaded_file.file_id}.bin"
        elif message.photo:
            # Берем фото с максимальным разрешением
            uploaded_file = message.photo[-1]
            filename = f"photo_{uploaded_file.file_id}.jpg"
        elif message.video:
            uploaded_file = message.video
            filename = uploaded_file.file_name or f"video_{uploaded_file.file_id}.mp4"
        elif message.audio:
            uploaded_file = message.audio
            filename = uploaded_file.file_name or f"audio_{uploaded_file.file_id}.mp3"
        elif message.voice:
            uploaded_file = message.voice
            filename = f"voice_{uploaded_file.file_id}.ogg"
        elif message.video_note:
            uploaded_file = message.video_note
            filename = f"video_note_{uploaded_file.file_id}.mp4"
        else:
            # Проверяем кнопки завершения/отмены
            if message.text in ["Завершить загрузку", "Отмена"]:
                return
            
            bot.send_message(
                message.chat.id,
                "Неподдерживаемый тип файла. Пожалуйста, отправьте документ, фото, видео или аудио."
            )
            # Продолжаем ожидать следующий файл
            bot.register_next_step_handler(message, handle_document_upload, user_id)
            return
        
        # Получаем информацию о файле
        file_info = bot.get_file(uploaded_file.file_id)
        
        # Скачиваем файл
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Получаем папку клиента
        client_dir = dtp.user_temp_data[user_id]['uploading_docs']['client_dir']
        
        # Проверяем, не существует ли уже файл с таким именем
        original_filename = filename
        counter = 1
        while os.path.exists(os.path.join(client_dir, filename)):
            name, ext = os.path.splitext(original_filename)
            filename = f"{name}_{counter}{ext}"
            counter += 1
        
        # Сохраняем файл в папку клиента
        file_path = os.path.join(client_dir, filename)
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Обновляем счетчик загруженных файлов
        dtp.user_temp_data[user_id]['uploading_docs']['uploaded_count'] += 1
        dtp.user_temp_data[user_id]['uploading_docs']['uploaded_files'].append(filename)
        
        uploaded_count = dtp.user_temp_data[user_id]['uploading_docs']['uploaded_count']
        
        # Создаем клавиатуру с кнопками
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Завершить загрузку", callback_data="finish_upload"))
        keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel_upload"))
        
        response_text = f"✅ Файл '{filename}' успешно загружен!\n\nЗагружено файлов: {uploaded_count}\n\nМожете отправить еще файлы или завершить загрузку."
        
        response_message = bot.send_message(
            message.chat.id,
            response_text,
            reply_markup=keyboard
        )
        
        # Продолжаем ожидать следующие файлы
        bot.register_next_step_handler(response_message, handle_document_upload, user_id)
        
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"Ошибка при сохранении файла: {e}"
        )
        print(f"Ошибка сохранения файла: {e}")
        
        # Продолжаем ожидать следующие файлы даже при ошибке
        bot.register_next_step_handler(message, handle_document_upload, user_id)
def update_client_in_database(client_id, db_field, new_value):
    """Обновление данных клиента в базе данных"""
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        
        # Получаем текущие данные клиента
        client = get_client_from_db_by_client_id(client_id)
        if not client:
            raise Exception(f"Клиент с ID {client_id} не найден в базе")
        
        # Парсим JSON данные
        try:
            if client.get('data_json'):
                data_json = json.loads(client['data_json'])
            else:
                data_json = {}
        except (json.JSONDecodeError, TypeError):
            data_json = {}
        
        # Обновляем данные
        data_json[db_field] = new_value
        
        # Проверяем, есть ли поле в основной структуре таблицы
        cursor.execute("PRAGMA table_info(clients)")
        columns_info = cursor.fetchall()
        table_columns = [col[1] for col in columns_info]
        
        if db_field in table_columns:
            # Обновляем основное поле
            update_query = f"UPDATE clients SET {db_field} = ?, data_json = ? WHERE client_id = ?"
            cursor.execute(update_query, (new_value, json.dumps(data_json, ensure_ascii=False), client_id))
            print(f"Обновлено основное поле {db_field}")
        else:
            # Обновляем только JSON
            update_query = "UPDATE clients SET data_json = ? WHERE client_id = ?"
            cursor.execute(update_query, (json.dumps(data_json, ensure_ascii=False), client_id))
            print(f"Обновлено поле {db_field} в JSON")
        
        conn.commit()
        conn.close()
        
        print(f"База данных успешно обновлена для клиента {client_id}")
        
    except Exception as e:
        print(f"Ошибка обновления базы данных: {e}")
        raise e
def load_field_mapping_from_data_file():
    """Загружает маппинг полей из файла data.txt"""
    field_mapping = {}
    
    try:
        with open('data.txt', 'r', encoding='utf-8') as file:
            lines = file.readlines()
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                field_name, variable = line.split(':', 1)
                field_name = field_name.strip()
                variable = variable.strip()
                
                # Создаем маппинг: русское название -> английская переменная
                field_mapping[field_name.lower()] = variable
        
        print(f"Загружено {len(field_mapping)} полей из data.txt")
        return field_mapping
        
    except Exception as e:
        print(f"Ошибка загрузки маппинга полей: {e}")
        return {}
@bot.callback_query_handler(func=lambda call: call.data == "finish_upload")
def callback_finish_upload(call):
    """Завершение загрузки документов"""
    try:
        user_id = call.message.from_user.id
        
        if (user_id not in dtp.user_temp_data or 
            'uploading_docs' not in dtp.user_temp_data[user_id]):
            bot.answer_callback_query(call.id, "Сессия загрузки не найдена")
            return_to_main_menu_from_call(call)
            return
        
        upload_data = dtp.user_temp_data[user_id]['uploading_docs']
        uploaded_count = upload_data['uploaded_count']
        uploaded_files = upload_data['uploaded_files']
        
        # Деактивируем загрузку
        dtp.user_temp_data[user_id]['uploading_docs']['active'] = False
        
        if uploaded_count > 0:
            files_list = '\n'.join([f"• {filename}" for filename in uploaded_files])
            message_text = f"Загрузка завершена!\n\nУспешно загружено файлов: {uploaded_count}\n\nФайлы:\n{files_list}"
        else:
            message_text = "Файлы не были загружены."
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text
        )
        
        # Очищаем временные данные
        if 'uploading_docs' in dtp.user_temp_data[user_id]:
            del dtp.user_temp_data[user_id]['uploading_docs']
        
        # Небольшая задержка перед возвратом в главное меню
        time.sleep(2)
        return_to_main_menu_from_call(call)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_finish_upload: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_upload")
def callback_cancel_upload(call):
    try:
        user_id = call.message.from_user.id
        
        # Деактивируем загрузку
        if (user_id in dtp.user_temp_data and 
            'uploading_docs' in dtp.user_temp_data[user_id]):
            dtp.user_temp_data[user_id]['uploading_docs']['active'] = False
            del dtp.user_temp_data[user_id]['uploading_docs']
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Загрузка документов отменена."
        )
        
        time.sleep(1)
        return_to_main_menu_from_call(call)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_cancel_upload: {e}")

def return_to_main_menu_from_call(call):
    clear_chat_history_optimized(call.message, 30)
    """Возврат в главное меню из callback"""
    try:
        user_id = call.message.from_user.id
        if user_id in dtp.user_temp_data:
            del dtp.user_temp_data[user_id]
        
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Добавить клиента", callback_data="btn_new_client")
        btn2 = types.InlineKeyboardButton("Искать в базе", callback_data="btn_search_database")
        keyboard.add(btn1)
        keyboard.add(btn2)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дальнейшие действия",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Ошибка возврата в главное меню: {e}")
        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("Добавить клиента", callback_data="btn_new_client")
        btn2 = types.InlineKeyboardButton("Искать в базе", callback_data="btn_search_database")
        keyboard.add(btn1)
        keyboard.add(btn2)
        
        bot.send_message(
            call.message.chat.id,
            "Выберите дальнейшие действия",
            reply_markup=keyboard
        )
@bot.callback_query_handler(func=lambda call: call.data == "show_more_files")
def callback_show_more_files(call):
    """Показать больше файлов"""
    try:
        user_id = call.message.from_user.id
        
        if (user_id not in dtp.user_temp_data or 
            'files_list' not in dtp.user_temp_data[user_id]):
            bot.answer_callback_query(call.id, "Ошибка: список файлов не найден")
            return
        
        files_list = dtp.user_temp_data[user_id]['files_list']
        client_dir = dtp.user_temp_data[user_id]['client_dir']
        
        # Создаем клавиатуру со всеми файлами
        keyboard = types.InlineKeyboardMarkup()
        
        for i, filename in enumerate(files_list):
            display_name = filename
            if len(display_name) > 30:
                display_name = display_name[:27] + "..."
            
            callback_data = f"send_file_{i}"
            keyboard.add(types.InlineKeyboardButton(display_name, callback_data=callback_data))
        
        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="btn_main_menu"))
        
        message_text = f"Все документы ({len(files_list)}):\n\nВыберите файл для отправки:"
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}")
        print(f"Ошибка в callback_show_more_files: {e}")

def clear_chat_history_optimized(message, count):
    """
    Быстрое удаление последних N сообщений
    """
    chat_id = message.chat.id
    current_message_id = message.message_id
    deleted_count = 0
    # Удаляем последние N сообщений без статусных сообщений для максимальной скорости
    for message_id in range(current_message_id, max(1, current_message_id - count), -1):
        try:
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            deleted_count += 1
        except ApiException as e:
            # Пропускаем ошибки и продолжаем
            if "message to delete not found" in str(e).lower():
                continue
            elif "message can't be deleted" in str(e).lower():
                continue
            elif "too many requests" in str(e).lower():
                time.sleep(0.3)  # Короткая пауза при превышении лимитов
                continue
        except Exception:
            continue
        


if __name__ == '__main__':
    bot.infinity_polling()