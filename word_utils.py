from docx import Document
import os
from datetime import datetime
import sqlite3
import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
import num2words
def replace_words_in_word(search_words, replace_words, input_path, output_path):
    """
    Функция для замены и создания файла
    arg[0] = ["Список слов, которые нужно заменить"]
    arg[1] = ["Список слов, которые нужно вставить"]
    arg[2] ="Путь к шаблону"
    arg[3]= "Путь к создаваемому файлу"
    """
    
    try:
        if len(search_words) != len(replace_words):
            print("Количество слов не совпадает!")
            return False
        
        if not os.path.exists(input_path):
            print(f"Файл не найден: {input_path}")
            return False
        
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        doc = Document(input_path)
        replacements = dict(zip(search_words, replace_words))
        replacement_count = 0
        
        def replace_preserving_format(paragraph):
            nonlocal replacement_count
            
            # Собираем информацию о форматировании каждого символа
            char_formatting = []
            text_parts = []
            
            for run in paragraph.runs:
                for char in run.text:
                    char_formatting.append({
                        'font_name': run.font.name,
                        'font_size': run.font.size,
                        'bold': run.font.bold,
                        'italic': run.font.italic,
                        'underline': run.font.underline,
                        'color': run.font.color.rgb
                    })
                text_parts.append(run.text)
            
            full_text = ''.join(text_parts)
            new_text = full_text
            
            # Применяем замены
            for search_word, replace_word in replacements.items():
                if search_word in new_text:
                    new_text = new_text.replace(search_word, replace_word)
                    replacement_count += 1
            
            if new_text != full_text:
                paragraph.clear()
                
                if char_formatting and len(char_formatting) >= len(full_text):
                    current_format = None
                    current_run = None
                    
                    for i, char in enumerate(new_text):

                        if i < len(char_formatting):
                            char_format = char_formatting[min(i, len(char_formatting) - 1)]
                        else:
                            char_format = char_formatting[-1] if char_formatting else {}
                        
                        if current_format != char_format:
                            current_run = paragraph.add_run()
                            if char_format.get('font_name'):
                                current_run.font.name = char_format['font_name']
                            if char_format.get('font_size'):
                                current_run.font.size = char_format['font_size']
                            if char_format.get('bold'):
                                current_run.font.bold = char_format['bold']
                            if char_format.get('italic'):
                                current_run.font.italic = char_format['italic']
                            if char_format.get('underline'):
                                current_run.font.underline = char_format['underline']
                            if char_format.get('color'):
                                current_run.font.color.rgb = char_format['color']
                            current_format = char_format
                        
                        current_run.text += char
                else:
                    paragraph.add_run(new_text)
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                replace_preserving_format(paragraph)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if paragraph.text.strip():
                            replace_preserving_format(paragraph)
        

        
        doc.save(output_path)
        print(f"✅ Документ сохранен: {output_path}")
        print(f"📊 Замен выполнено: {replacement_count}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return False

def create_fio_data_file(data_dict):
    """
    Создает персонализированный файл данных на основе словаря с учетом пустых значений.
    """
    if 'fio' not in data_dict:
        return "Ошибка: В словаре отсутствует обязательный ключ 'fio'"
    
    fio = data_dict['fio']
    
    # Создаем папку fio, если она не существует
    fio_dir = str(fio)
    if not os.path.exists(fio_dir):
        os.makedirs(fio_dir)
    
    # Путь к файлу
    file_path = os.path.join(fio_dir, f"{fio}_data.txt")
    
    # Если файл существует, удаляем его
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # Читаем шаблон из data.txt
    template_path = 'data.txt'
    if not os.path.exists(template_path):
        return "Ошибка: Файл data.txt не найден в корневой директории"
    
    try:
        with open(template_path, 'r', encoding='utf-8') as template_file:
            lines = template_file.readlines()
        
        # Обрабатываем каждую строку
        result_lines = []
        for line in lines:
            line = line.strip()
            if ':' in line:
                # Разделяем название поля и переменную
                field_name, variable = line.split(':', 1)
                field_name = field_name.strip()
                variable = variable.strip()
                
                # Если переменная есть в словаре и значение не пустое/None
                if variable in data_dict:
                    value = data_dict[variable]
                    # Проверяем, что значение не пустое, не None и не равно 0 для числовых полей
                    if value is not None and str(value).strip() != '' and value != 0:
                        result_lines.append(f"{field_name}: {value}")
                # Иначе пропускаем эту строку (удаляем)
            else:
                # Если в строке нет двоеточия, оставляем как есть
                if line:  # Пропускаем пустые строки
                    result_lines.append(line)
        
        # Записываем результат в новый файл
        with open(file_path, 'w', encoding='utf-8') as output_file:
            for line in result_lines:
                output_file.write(line + '\n')
        
        return f"Файл успешно создан: {file_path}"
        
    except Exception as e:
        return f"Ошибка при обработке файла: {str(e)}"

def export_clients_db_to_excel(db_path='clients.db', output_path='clients_export.xlsx'):
    """
    Экспортирует данные из базы данных clients.db в Excel файл
    
    Args:
        db_path (str): Путь к файлу базы данных SQLite
        output_path (str): Путь для сохранения Excel файла
    """
    
    # Словарь соответствия: русское название -> название поля в БД
    column_mapping = {
        '№ Клиента': 'client_id',
        'Статус': 'status',
        'Город': 'city',
        'Клиент ФИО': 'fio',
        'Дата ДТП': 'date_dtp',
        'Марка, модель клиента': 'marks',
        'Номер авто клиента': 'car_number',
        'Страховая компания': 'insurance',
        'Виновник ФИО Полностью': 'fio_culp',
        'Марка, модель виновника': 'marks_culp',
        'Номер авто виновника': 'number_auto_culp',
        'Дата заявления в страховую': 'date_ins',
        'Дата заявления в СТО': 'date_zayav_sto',
        'Дата Составления претензии': 'date_pret',
        'Дата составления заявления омбуцмену': 'date_ombuc',
        'Дата искового заявления': 'date_isk',
        'Суд': 'sud',

    }
    
    try:
        # Проверяем существование файла базы данных
        if not os.path.exists(db_path):
            print(f"Ошибка: Файл базы данных '{db_path}' не найден!")
            return False
            
        # Подключение к базе данных SQLite
        conn = sqlite3.connect(db_path)
        
        # Получаем список всех таблиц
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if not tables:
            print("В базе данных не найдено таблиц!")
            conn.close()
            return False
            
        print(f"Найдены таблицы: {[table[0] for table in tables]}")
        
        # Предполагаем, что данные находятся в первой таблице или ищем таблицу 'clients'
        table_name = None
        for table in tables:
            if 'client' in table[0].lower():
                table_name = table[0]
                break
        
        if not table_name:
            table_name = tables[0][0]  # Берем первую таблицу
            
        print(f"Используется таблица: {table_name}")
        
        # Получаем структуру таблицы
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_info = cursor.fetchall()
        available_columns = [col[1] for col in columns_info]
        
        print(f"Доступные поля в таблице: {available_columns}")
        
        # Создаем список полей для выборки (только те, что есть в БД)
        select_columns = []
        russian_headers = []
        
        for rus_name, db_name in column_mapping.items():
            if db_name in available_columns:
                select_columns.append(db_name)
                russian_headers.append(rus_name)
            else:
                print(f"Поле '{db_name}' ({rus_name}) не найдено в таблице")
        
        if not select_columns:
            print("Не найдено ни одного совпадающего поля!")
            conn.close()
            return False
        
        # Выполняем запрос к базе данных
        query = f"SELECT {', '.join(select_columns)} FROM {table_name}"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Переименовываем колонки на русские названия
        df.columns = russian_headers
        
        print(f"Загружено {len(df)} записей с {len(df.columns)} полями")
        
        # Создаем Excel файл с форматированием
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Клиенты"
        
        # Добавляем данные в лист
        for r in dataframe_to_rows(df, index=False, header=True):
            ws.append(r)
        
        # Форматирование заголовков
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        for col in range(1, len(russian_headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # Автоматическая ширина колонок
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            adjusted_width = min(max_length + 2, 50)  # Максимальная ширина 50
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Замораживаем первую строку
        ws.freeze_panes = "A2"
        
        # Сохраняем файл
        wb.save(output_path)
        
        print(f"✅ Экспорт завершен успешно!")
        print(f"📁 Файл сохранен: {output_path}")
        print(f"📊 Экспортировано записей: {len(df)}")
        print(f"📋 Количество полей: {len(df.columns)}")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Ошибка при работе с базой данных: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

def edit_files(files, data):
    for i in files:
        if "1. Обложка дела.docx" == i:
            try:
                replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                    "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                    "{{ Страховая }}", "{{ винФИО }}"],
                                    [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                        str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"])],
                                        "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела.docx",
                                        data["fio"]+"\\Документы\\"+"1. Обложка дела.docx")
            except Exception as e:
                print(e)
                print(i)
                print("1. Обложка дела.docx")
        elif "1.cd Обложка дела.docx" == i:
            replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                    "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                    "{{ Страховая }}", "{{ винФИО }}", "{{ собТС_ФИО }}"],
                                    [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                        str(data['year']),str(data['client_id']), str(data["fio"]), str(data["insurance"]), str(data["fio_culp"]), str(data["fio_sobs"])],
                                        "Шаблоны\\1. ДТП\\1. На ремонт\\1. Обложка дела\\1.cd Обложка дела.docx",
                                        data["fio"]+"\\Документы\\"+"1.cd Обложка дела.docx")
        elif "2. Юр договор.docx" == i:
            try:
                replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", 
                            "{{ Дата }}", "{{ ФИО }}","{{ ДР }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}",
                            "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", "{{ Индекс }}","{{ Адрес }}","{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                            [str(data['year']), str(data['client_id']), str(data["city"]), str(datetime.now().strftime("%d.%m.%Y")),
                                str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),str(data["number_pasport"]), str(data["where_pasport"]),
                                str(data["when_pasport"]), str(data["index_postal"]), str(data["address"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                                str(data["address_dtp"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\1. На ремонт\\2. Юр договор.docx",
                                data["fio"]+"\\Документы\\"+"2. Юр договор.docx")
            except Exception as e:
                print(e)
                print(i)
                print("2. Юр договор.docx")
        elif "3a Заявление в Страховую ФЛ собственник с эвакуатором.docx" == i:
            try:
                replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3a Заявление в Страховую ФЛ собственник с эвакуатором.docx",
                                    data["fio"]+"\\Документы\\"+"3a Заявление в Страховую ФЛ собственник с эвакуатором.docx")
            except Exception as e:
                print(e)
                print(i)
                print("3a Заявление в Страховую ФЛ собственник с эвакуатором.docx")
        elif "3b Заявление в Страховую ФЛ собственник без эвакуатора.docx" == i:
            try:
                replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3b Заявление в Страховую ФЛ собственник без эвакуатора.docx",
                                    data["fio"]+"\\Документы\\"+"3b Заявление в Страховую ФЛ собственник без эвакуатора.docx")
            except Exception as e:
                print(e)
                print(i)
                print("3b Заявление в Страховую ФЛ собственник без эвакуатора.docx")
        elif "3c Заявление в Страховую ФЛ представитель с эвакуатором.docx" == i:
            try:
                replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3c Заявление в Страховую ФЛ представитель с эвакуатором.docx",
                                    data["fio"]+"\\Документы\\"+"3c Заявление в Страховую ФЛ представитель с эвакуатором.docx")
            except Exception as e:
                print(e)
                print(i)
                print("3c Заявление в Страховую ФЛ представитель с эвакуатором.docx")
        elif "3d Заявление в Страховую ФЛ представитель без эвакуатора.docx" == i:
            try:
                replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ Паспорт_серия }}", 
                                "{{ Паспорт_номер }}", "{{ ДР }}","{{ Место }}", "{{ Индекс }}",
                                "{{ Адрес }}", "{{ Марка_модель }}", "{{ Год_авто }}","{{ Nавто_клиента }}","{{ Документ }}",
                                "{{ Док_серия }}", "{{ Док_номер }}", "{{ Док_когда }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Адрес_ДТП }}", "{{ винФИО }}", "{{ Марка_модель_виновника }}", "{{ Серия_полиса }}",
                                "{{ Номер_полиса }}", "{{ Город }}","{{ Телефон }}", "{{ Банк_получателя }}", "{{ Счет_получателя }}",
                                "{{ Кор_счет_получателя }}","{{ БИК_Банка }}", "{{ ИНН_Банка }}", "{{ Дата }}"],
                                [str(data["insurance"]), str(data["fio"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                    str(data["date_of_birth"]), str(data["city_birth"]),str(data["index_postal"]), str(data["address"]),
                                    str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["docs"]),str(data["seria_docs"]), 
                                    str(data["number_docs"]), str(data["data_docs"]), str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["fio_culp"]), str(data["marks_culp"]), str(data["seria_insurance"]),str(data["number_insurance"]),
                                    str(data["city"]), str(data["number"]), str(data["bank"]), str(data["bank_account"]), str(data["bank_account_corr"]),
                                    str(data["BIK"]), str(data["INN"]), str(datetime.now().strftime("%d.%m.%Y"))],
                                    "Шаблоны\\1. ДТП\\1. На ремонт\\3. Заявление в страховую после ДТП\\3d Заявление в Страховую ФЛ представитель без эвакуатора.docx",
                                    data["fio"]+"\\Документы\\"+"3d Заявление в Страховую ФЛ представитель без эвакуатора.docx")
            except Exception as e:
                print(e)
                print(i)
                print("3d Заявление в Страховую ФЛ представитель с эвакуатором.docx")
        elif "4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx" == i:
            try:
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
                                    data["fio"]+"\\Документы\\"+"4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx")
            except Exception as e:
                print(e)
                print(i)
                print("4. Заявление о проведении дополнительного осмотра автомобиля представитель.docx")
        elif "5. Запрос в страховую о выдаче акта и расчёта представитель.docx" == i:
            try:
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
                                data["fio"]+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx")
            except Exception as e:
                print(e)
                print(i)
                print("5. Запрос в страховую о выдаче акта и расчёта представитель.docx")
        elif "6. Заявление в СТО представитель.docx" == i:
            try:
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
                                    data["fio"]+"\\Документы\\"+"6. Заявление в СТО представитель.docx")
            except Exception as e:
                print(e)
                print(i)
                print("6. Заявление в СТО представитель.docx")
        elif "Деликт 3. Заявление о выдаче копии справки участников ДТП.docx" == i:
            try:
                replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                            [str(data["fio"]), str(data["date_of_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["number"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 3. Заявление о выдаче копии справки участников ДТП.docx",
                                data["fio"]+"\\Документы\\"+"Деликт 3. Заявление о выдаче копии справки участников ДТП.docx")
            except Exception as e:
                print(e)
                print(i)
                print("Деликт 3. Заявление о выдаче копии справки участников ДТП.docx")
        elif "Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx" == i:
            try:
                replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}","{{ Адрес_ДТП }}",
                            "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}", "{{ Телефон }}","{{ ФИОк }}" ],
                            [str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["number"]),str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx",
                                data["fio"]+"\\Документы\\"+"Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx")
            except Exception as e:
                print(e)
                print(i)
                print("Деликт 4. Запрос в страховую о выдаче акта и расчёта.docx")
        elif "6. Претензия в страховую Выплата без согласования.docx" == i:
            try:
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
                                            "Шаблоны\\1. ДТП\\1. На ремонт\\Выплата без согласования\\6. Претензия в страховую Выплата без согласования.docx",
                                            data["fio"]+"\\Документы\\"+"6. Претензия в страховую Выплата без согласования.docx")
            except Exception as e:
                print(e)
                print(i)
                print("6. Претензия в страховую Выплата без согласования.docx")
        elif "7. Претензия в страховую СТО отказала.docx" == i:
            try:
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
                                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\7. Претензия в страховую СТО отказала.docx",
                                            data["fio"]+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx")
            except Exception as e:
                print(e)
                print(i)
                print("7. Претензия в страховую СТО отказала.docx")
        elif "6. Претензия в страховую  СТО свыше 50 км.docx" == i:
            try:
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
                                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\6. Претензия в страховую  СТО свыше 50 км.docx",
                                            data["fio"]+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx")
            except Exception as e:
                print(e)
                print(i)
                print("6. Претензия в страховую  СТО свыше 50 км.docx")
        elif "5. Запрос в страховую о выдаче акта и расчёта.docx" == i:
            try:
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
                                data["fio"]+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта.docx")
            except Exception as e:
                print(e)
                print(i)
                print("5. Запрос в страховую о выдаче акта и расчёта.docx")
        elif "5. Запрос в страховую о выдаче акта и расчёта представитель.docx" == i:
            try:
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
                                data["fio"]+"\\Документы\\"+"5. Запрос в страховую о выдаче акта и расчёта представитель.docx")
            except Exception as e:
                print(e)
                print(i)
                print("5. Запрос в страховую о выдаче акта и расчёта представитель.docx")
        elif "7. Заявление фин. омбудсмену при выплате без согласования.docx" == i:
            try:
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
                                "Шаблоны\\1. ДТП\\1. На ремонт\\Выплата без согласования\\7. Заявление фин. омбудсмену при выплате без согласования.docx",
                                data["fio"]+"\\Документы\\"+"7. Заявление фин. омбудсмену при выплате без согласования.docx")
            except Exception as e:
                print(e)
                print(i)
                print("7. Заявление фин. омбудсмену при выплате без согласования.docx")
        elif "8. Заявление фин. омбуцмену СТО отказала.docx" == i:
            try:
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
                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО отказала\\8. Заявление фин. омбуцмену СТО отказала.docx",
                            data["fio"]+"\\Документы\\"+"8. Заявление фин. омбуцмену СТО отказала.docx")
            except Exception as e:
                print(e)
                print(i)
                print("8. Заявление фин. омбуцмену СТО отказала.docx")
        elif "7. Заявление фин. омбудсмену СТО свыше 50 км.docx" == i:
            try:
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
                            "Шаблоны\\1. ДТП\\1. На ремонт\\Ремонт не произведен СТО свыше 50км\\7. Заявление фин. омбудсмену СТО свыше 50 км.docx",
                            data["fio"]+"\\Документы\\"+"7. Заявление фин. омбудсмену СТО свыше 50 км.docx")
            except Exception as e:
                print(e)
                print(i)
                print("7. Заявление фин. омбудсмену СТО свыше 50 км.docx")
        elif "6. Заявление в СТО.docx" == i:
            try:
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
                                    data["fio"]+"\\Документы\\"+"6. Заявление в СТО.docx")
            except Exception as e:
                print(e)
                print(i)
                print("6. Заявление в СТО.docx")
        elif "Деликт 5.  Исковое заявление.docx" == i:
            try:
                replace_words_in_word(["{{ Суд }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Индекс }}",
                            "{{ Адрес }}", "{{ Телефон }}", "{{ Представитель }}","{{ NДоверенности }}","{{ Дата_доверенности }}",
                            "{{ винФИО }}", "{{ ДР_Виновника }}", "{{ Серия_ВУвин }}", 
                            "{{ Номер_ВУвин }}", "{{ Дата_ВУвин }}", "{{ Индекс_Виновника }}", "{{ Адрес_Виновника }}",
                            "{{ Телефон_Виновника }}", "{{ Страховая }}","{{ Разница }}", "{{ Выплата_ОСАГО }}",
                            "{{ Экспертиза }}", "{{ Дата_выплаты }}", "{{ Цена_пошлины }}", "{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}", "{{ Nавто_виновник }}",
                            "{{ Выплата_ОСАГО }}", "{{ Nвыплатного_дела }}","{{ Дата_выплатного_дела }}", "{{ Nплатежного_поручения }}",
                            "{{ Дата_поручения }}","{{ Стоимость_экспертизы }}","{{ NКлиента }}", "{{ Дата_экспертизы }}",
                            "{{ Дата }}","{{ Документ }}","{{ Док_серия }}", "{{ Док_номер }}","{{ Дата_извещения }}", "{{ Дата_искового_заявления }}", "{{ Год }}"],
                            [str(data["sud"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                str(data["where_pasport"]), str(data["when_pasport"]),str(data["index_postal"]), str(data["address"]), str(data["number"]),
                                str(data["fio_not"]), str(data["N_dov_not"]), str(data["data_dov_not"]), str(data["fio_culp"]), str(data["date_of_birth_culp"]),str(data["seria_vu_culp"]), 
                                str(data["number_vu_culp"]), str(data["data_vu_culp"]), str(data["index_culp"]), str(data["address_culp"]), str(data["number_culp"]),
                                str(data["insurance"]), str(float(data["coin_exp"])-float(data["coin_osago"])), str(data["coin_osago"]),str(data["coin_exp_izn"]),
                                str(data["date_coin_ins"]), str(data["gos_money"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                str(data["address_dtp"]),str(data["marks"]),str(data["car_number"]),str(data["marks_culp"]),str(data["number_auto_culp"]),
                                str(data["coin_osago"]),str(data["N_viplat_work"]),str(data["date_viplat_work"]),str(data["N_plat_por"]),
                                str(data["date_plat_por"]),str(data["coin_exp"]),str(data["client_id"]),str(data["date_exp"]),
                                str(data["date_ins"]),str(data["docs"]),str(data["seria_docs"]),str(data["number_docs"]),
                                str(data["date_izvesh_dtp"]), str(data["date_isk"]), str(data['year'])],
                                "Шаблоны\\1. ДТП\\Деликт\\Деликт 5.  Исковое заявление.docx",
                                data["fio"]+"\\Документы\\"+"Деликт 5.  Исковое заявление.docx")
            except Exception as e:
                print(e)
                print(i)
                print("Деликт 5.  Исковое заявление.docx")
        elif "Яма 1. Обложка дела.docx" == i:
            replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                "{{ Телефон }}", "{{ Город }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data["year"]),str(data['client_id']), str(data["fio"]), str(data["number"]), str(data["city"])],
                                    "Шаблоны\\2. Яма\\Яма 1. Обложка дела.docx",
                                    data["fio"]+"\\Документы\\"+"Яма 1. Обложка дела.docx")
        elif "Яма 2. Юр договор.docx" == i:
            replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", 
                            "{{ Дата }}", "{{ ФИО }}","{{ ДР }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}",
                            "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", "{{ Индекс }}","{{ Адрес }}","{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                            [str(data['year']), str(data['client_id']), str(data["city"]), str(datetime.now().strftime("%d.%m.%Y")),
                                str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),str(data["number_pasport"]), str(data["where_pasport"]),
                                str(data["when_pasport"]), str(data["index_postal"]), str(data["address"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                                str(data["address_dtp"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\1. На ремонт\\2. Юр договор.docx",
                                data["fio"]+"\\Документы\\"+"2. Юр договор.docx")
        elif "Яма 3.  Анализ ДТП.docx" == i:
            replace_words_in_word(["{{ Дата_ДТП }}", "{{ Марка_модель }}", "{{ Год_авто }}", 
                            "{{ Nавто_клиента }}", "{{ ФИО }}", "{{ Адрес_ДТП }}","{{ Город }}", "{{ ФИОк }}",
                            "{{ Nопределения }}", "{{ Дата_определения }}", "{{ Дата_протокола }}", "{{ Nпротокола }}",
                            "{{ Улица }}","{{ Дата_обследования }}", "{{ Год }}","{{ NКлиента }}", "{{ Дата_экспертизы }}", 
                            "{{ Дата_осмотра }}","{{ Перечень_ущерба }}", "{{ Экспертиза }}", "{{ Экспертиза_текст }}",
                            "{{ NДоверенности }}", "{{ Дата_доверенности }}", "{{ Представитель }}"],
                            [str(data["date_dtp"]), str(data["marks"]), str(data["year_auto"]), str(data["car_number"]), str(data["fio"]),
                                str(data["address_dtp"]),str(data['city']), str(data["fio_k"]), str(data["N_gui"]), str(data["date_gui"]),
                                str(data["date_prot"]),str(data['N_prot']), str(data["street"]), str(data["date_road"]),
                                str(data["year"]),str(data['client_id']), str(data["date_exp"]),str(data["date_sto"]), str(data["coin_exp_izn"]),str(data["coin_exp"]),
                                str(num2words(data["coin_exp"], lang ='ru')),str(data['N_dov_not']), str(data["data_dov_not"]), str(data["fio_not"])],
                                "Шаблоны\\2. Яма\\Яма 3.  Анализ ДТП.docx",
                                data["fio"]+"\\Документы\\"+"Яма 3.  Анализ ДТП.docx")
        elif "Яма 4. Иск к администрации.docx" == i:
            replace_words_in_word(["{{ Суд }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Индекс }}", "{{ Адрес }}","{{ Телефон }}","{{ Представитель }}",
                            "{{ NДоверенности }} ", "{{ Дата_доверенности }}", "{{ Экспертиза }}",
                            "{{ Экспертиза_текст }}", "{{ Цена_пошлины }}","{{ Марка_модель }}", "{{ Nавто_клиента }}",
                            "{{ Документ }}", "{{ Док_серия }}", "{{ Док_номер }}","{{ Док_когда }}","{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Перечень_ущерба }}", "{{ Сотрудник }}",
                            "{{ Nопределения }}", "{{ Дата_определения }}", "{{ Улица }}","{{ Nпротокола }}","{{ Дата_протокола }}",
                            "{{ Дата_обследования }}", "{{ Год }}","{{ NКлиента }}", "{{ Дата_экспертизы }}",
                            "{{ Цена_пошлины_текст }}","{{ Чек_экспертизы }}",
                            "{{ Nчека_юр }}", "{{ Дата_чека_юр }}", "{{ Цена_нотариус }}","{{ Цена_нотариус_текст }}","{{ Nчека_нотариус }}",
                            "{{ Дата_чека_нотариус }}", "{{ Дата_искового_заявления }}"],
                            [str(data["sud"]), str(data['fio']), str(data['date_of_birth']), str(data['seria_pasport']),
                            str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["index_postal"]),
                            str(data["address"]), str(data["number"]), str(data["fio_not"]), str(data["N_dov_not"]), str(data["data_dov_not"]), 
                            str(data["coin_exp"]), str(num2words(data["coin_exp"], lang ='ru')),str(data["gos_money"]), str(data['marks']), str(data['car_number']),
                            str(data['docs']), str(data["seria_docs"]), str(data['number_docs']), str(data['data_docs']), str(data['date_dtp']),
                            str(data["time_dtp"]), str(data["address_dtp"]),str(data["coin_exp_izn"]), str(data["who_dtp"]),
                            str(data["N_gui"]), str(data["date_gui"]), str(data["street"]), str(data["N_prot"]), str(data["date_prot"]), 
                            str(data["date_road"]), str(data["year"]),str(data["client_id"]), str(data['date_exp']), str(num2words(data["gos_money"], lang ='ru')),
                            str(data['N_kv_exp']), str(data["N_kv_ur"]), str(data['date_kv_ur']),str(data['coin_not']), str(num2words(data["coin_not"], lang ='ru')),
                            str(data['N_kv_not']), str(data['date_kv_not']), str(data['date_isk'])],
                            "Шаблоны\\2. Яма\\Яма 4. Иск к администрации.docx",
                                data["fio"]+"\\Документы\\"+"Яма 4. Иск к администрации.docx")
        elif "Деликт (без ОСАГО) 1. Обложка дела.docx" == i:
            try:
                replace_words_in_word(["{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", 
                                "{{ Марка_модель }}", "{{ Nавто_клиента }}", "{{ Год }}","{{ NКлиента }}", "{{ ФИО }}",
                                "{{ винФИО }}"],
                                [str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data["year"]),str(data['client_id']), str(data["fio"]), str(data["fio_culp"])],
                                    "Шаблоны\\3. Деликт без ОСАГО\\Деликт (без ОСАГО) 1. Обложка дела.docx",
                                    data["fio"]+"\\Документы\\"+"Деликт (без ОСАГО) 1. Обложка дела.docx")
            except Exception as e:
                print(e)
                print(i)
                print("Деликт (без ОСАГО) 1. Обложка дела.docx")
        elif "Деликт (без ОСАГО) 2. Юр договор.docx" == i:
            replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Город }}", 
                            "{{ Дата }}", "{{ ФИО }}","{{ ДР }}","{{ Паспорт_серия }}", "{{ Паспорт_номер }}",
                            "{{ Паспорт_выдан }}", "{{ Паспорт_когда }}", "{{ Индекс }}","{{ Адрес }}","{{ Дата_ДТП }}",
                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ ФИОк }}"],
                            [str(data['year']), str(data['client_id']), str(data["city"]), str(datetime.now().strftime("%d.%m.%Y")),
                                str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),str(data["number_pasport"]), str(data["where_pasport"]),
                                str(data["when_pasport"]), str(data["index_postal"]), str(data["address"]), str(data["date_dtp"]), str(data["time_dtp"]), 
                                str(data["address_dtp"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\1. На ремонт\\2. Юр договор.docx",
                                data["fio"]+"\\Документы\\"+"2. Юр договор.docx")
        elif "Цессия 5. Соглашение о замене стороны Цессия.docx" == i:
            replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Дата }}", 
                                        "{{ Город }}", "{{ ЦФИО }}","{{ ЦДР }}", "{{ ЦМесто }}",
                                        "{{ ЦПаспорт_серия }}", "{{ ЦПаспорт_номер }}", "{{ ЦПаспорт_выдан }}","{{ ЦПаспорт_когда }}","{{ ЦИндекс }}",
                                        "{{ ЦАдрес }}", "{{ ФИО }}","{{ ДР }}", "{{ Место }}",
                                        "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Индекс }}",
                                        "{{ Адрес }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}"],
                                        [str(data["year"]), str(data["client_id"]), str(data["pret"]), str(data["city"]),
                                            str(data["fio_c"]), str(data["date_of_birth_c"]),str(data["city_birth_с"]), str(data["seria_pasport_c"]),
                                            str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                            str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                            str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                            str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"])],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 5. Соглашение о замене стороны Цессия.docx",
                                            data["fio"]+"\\Документы\\"+"Цессия 5. Соглашение о замене стороны Цессия.docx")
        elif "Цессия 6. Договор цессии.docx" == i:
            if len(data['fio_culp'].split())==2:
                    fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."
            else:
                    fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."+list(data['fio_culp'].split()[2])[0]+"."
            replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Дата }}", 
                                        "{{ Город }}", "{{ ЦФИО }}","{{ ЦДР }}", "{{ ЦМесто }}",
                                        "{{ ЦПаспорт_серия }}", "{{ ЦПаспорт_номер }}", "{{ ЦПаспорт_выдан }}","{{ ЦПаспорт_когда }}","{{ ЦИндекс }}",
                                        "{{ ЦАдрес }}", "{{ ФИО }}","{{ ДР }}", "{{ Место }}",
                                        "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Индекс }}",
                                        "{{ Адрес }}", "{{ винФИО }}", "{{ ДР_Виновника }}", "{{ Индекс_Виновника }}","{{ Адрес_Виновника }}","{{ Разница }}",
                                        "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}",
                                        "{{ Nавто_виновник }}", "{{ винФИОкор }}", "{{ Экспертиза }}", "{{ Выплата_ОСАГО }}","{{ Стоимость_экспертизы }}","{{ Дата_экспертизы }}",
                                        "{{ Дата_уведомления }}","{{ Цена_цессии }}", " {{ Телефон }}", "{{ ФИОк }}","{{ ЦТелефон }}", "{{ ЦФИОк }}"],
                                        [str(data["year"]), str(data["client_id"]), str(data["pret"]), str(data["city"]),
                                            str(data["fio_c"]), str(data["date_of_birth_c"]),str(data["city_birth_с"]), str(data["seria_pasport_c"]),
                                            str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                            str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                            str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                            str(data["fio_culp"]), str(data["date_of_birth_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(float(data["coin_exp"])-float(data['coin_osago'])), 
                                            str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),
                                            str(data["number_auto_culp"]), str(fio_culp_k), str(data["coin_exp"]), str(data["coin_osago"]),str(data["money_exp"]),
                                            str(data["date_exp"]), str(data["date_pret"]), str(data["coin_c"]), str(data["number"]), str(data["fio_k"]), str(data["number_c"]),str(data["fio_c_k"])],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 6. Договор цессии.docx",
                                            data["fio"]+"\\Документы\\"+"Цессия 6. Договор цессии.docx")
        elif "Деликт (без ОСАГО) 4.  Исковое заявление.docx" == i:
            replace_words_in_word(["{{ Суд }}","{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ Индекс }}", "{{ Адрес }}", "{{ Телефон }}","{{ Представитель }}","{{ NДоверенности }}","{{ Дата_доверенности }}", "{{ Телефон_представителя }}",
                                "{{ винФИО }}", "{{ ДР_Виновника }}","{{ Серия_ВУвин }}", "{{ Номер_ВУвин }}", "{{ Дата_ВУвин }}","{{ Индекс_Виновника }}","{{ Адрес_Виновника }}",
                                "{{ Телефон_Виновника }}",
                                "{{ Экспертиза }}","{{ Цена_пошлины }}",
                                "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}",
                                "{{ Nавто_виновник }}", "{{ Стоимость_экспертизы }}", "{{ Год }}","{{ NКлиента }}","{{ Дата_экспертизы }}",
                                "{{ Дата }}","{{ Цена_нотариус }}", "{{ Документ }}", "{{ Док_серия }}","{{ Док_номер }}","{{ Док_когда }}", "{{ Дата_извещения }}", "{{ Дата_искового_заявления }}"],
                                [str(data["sud"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["index_postal"]),
                                    str(data["address"]), str(data["number"]), str(data["fio_not"]), str(data["N_dov_not"]),str(data["data_dov_not"]), str(data["number_not"]),
                                    str(data["fio_culp"]),str(data["date_of_birth_culp"]), str(data["seria_vu_culp"]),
                                    str(data["number_vu_culp"]), str(data["data_vu_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(data["number_culp"]), 
                                    str(data["coin_exp"]),
                                    str(data["gos_money"]), str(data["date_dtp"]),str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data["marks_culp"]),str(data["number_auto_culp"]), str(data["money_exp"]), str(data["year"]), str(data["client_id"]),str(data["date_exp"]),
                                    str(data["date_ins"]), str(data["coin_not"]), str(data["docs"]), str(data["seria_docs"]), str(data["number_docs"]), str(data["data_docs"]),
                                    str(data["date_izvesh_dtp"]), str(data["date_isk"])],
                                    "Шаблоны\\3. Деликт без ОСАГО\\Деликт (без ОСАГО) 4.  Исковое заявление.docx",
                                    data["fio"]+"\\Документы\\"+"Деликт (без ОСАГО) 4.  Исковое заявление.docx")   
        elif "Цессия 7. Предложение о досудебном урегулировании спора.docx" == i:
            replace_words_in_word(["{{ винФИО }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                        "{{ Разница }}", "{{ ФИО }}","{{ Год }}", "{{ NКлиента }}",
                                        "{{ Дата }}", "{{ ЦФИО }}"],
                                        [str(data["fio_culp"]), str(data["date_dtp"]), str(data["time_dtp"]), str(float(data["coin_exp"])-float(data['coin_osago'])),
                                            str(data["fio"]), str(data["year"]),str(data["client_id"]), str(data["pret"]),
                                            str(data["fio_c"])],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 7. Предложение о досудебном урегулировании спора.docx",
                                            data["fio"]+"\\Документы\\"+"Цессия 7. Предложение о досудебном урегулировании спора.docx")
        elif "6. Претензия о замене способа возмещения.docx" == i:
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}","{{ ДР }}", 
                                        "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                        "{{ NДоверенности }}","{{ Дата_доверенности }}", "{{ Представитель }}",
                                        "{{ Nакта_осмотра }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}",
                                        "{{ Nавто_клиента }}", "{{ Дата_подачи_заявления }}","{{ Организация }}", "{{ Дата_экспертизы }}",
                                        "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Дата }}","{{ Номер_заявления_изменения }}", "{{ ФИОк }}", "{{ Выплата_ОСАГО }}",
                                        "{{ Дата_претензии }}"],
                                        [str(data["insurance"]), str(data["city"]),str(data["fio"]), str(data["date_of_birth"]),
                                            str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), 
                                            str(data["Na_ins"]),str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                            str(data["marks"]), str(data["car_number"]),str(data["date_insurance"]), str(data["org_exp"]),
                                            str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]), str(data["pret"]),
                                            str(data["Nv_ins"]), str(data["fio_k"]),str(data["coin_osago"]), str(data["date_pret"]),],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\6. Претензия о замене способа возмещения.docx",
                                            data["fio"]+"\\Документы\\"+"6. Претензия о замене способа возмещения.docx")
        elif "5. Заявление в страховую об изменении формы страхового возмещения выплатили.docx" == i:
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                                    "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                    "{{ Nакта_осмотра }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}",
                                    "{{ Nавто_клиента }}", "{{ Дата_подачи_заявления }}","{{ Организация }}", "{{ Дата_экспертизы }}",
                                    "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Город }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}",
                                    "{{ Дата }}", "{{ ФИОк }}"],
                                    [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]),
                                        str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                        str(data["Na_ins"]),str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                        str(data["marks"]), str(data["car_number"]),str(data["date_insurance"]), str(data["org_exp"]),
                                        str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]), str(data["city"]),
                                        str(data["seria_insurance"]), str(data["number_insurance"]),str(data["pret"]), str(data["fio_k"]),],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\5. Заявление в страховую об изменении формы страхового возмещения выплатили.docx",
                                        data["fio"]+"\\Документы\\"+"5. Заявление в страховую об изменении формы страхового возмещения выплатили.docx")
        elif "7. Заявление фин. омбуцмену изменение способа возмещения.docx" == i:
            replace_words_in_word(["{{ Дата_обуцмен }}","{{ Страховая }}", "{{ Город }}","{{ ФИО }}", "{{ ДР }}", "{{ Место }}",
                                "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ Адрес }}", "{{ Телефон }}","{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Дата_полиса }}",
                                "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}",
                                "{{ Nавто_клиента }}","{{ Дата }}", "{{ Nв_страховую }}","{{ Организация }}", "{{ Nэкспертизы }}", "{{ Дата_экспертизы }}",
                                "{{ Без_учета_износа }}", "{{ С_учетом_износа }}", "{{ Дата_заявления_изменения }}", "{{ Номер_заявления_изменения }}", "{{ ФИОк }}",
                                "{{ Дата_претензии }}", "{{ Выплата_ОСАГО }}"],
                                [str(data["date_ombuc"]), str(data["insurance"]), str(data["city"]), str(data["fio"]), str(data["date_of_birth"]),
                                    str(data["city_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),str(data["where_pasport"]), str(data["when_pasport"]),
                                    str(data["address"]), str(data["number"]), str(data["seria_insurance"]), str(data["number_insurance"]), str(data["date_insurance"]),
                                    str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]),
                                    str(data["marks"]), str(data["car_number"]), str(data["date_ins_pod"]), str(data["Nv_ins"]),str(data["org_exp"]),str(data["Na_ins"]),
                                    str(data["date_exp"]), str(data["coin_exp"]),str(data["coin_exp_izn"]), str(data["date_pret"]),
                                    str(data["Nv_ins"]), str(data["fio_k"]),str(data["date_pret"]), str(data["coin_osago"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\7. Заявление фин. омбуцмену изменение способа возмещения.docx",
                                    data["fio"]+"\\Документы\\"+"7. Заявление фин. омбуцмену изменение способа возмещения.docx")
        elif "Цессия 8. Исковое заявление Цессия.docx" == i:
            if len(data['fio_culp'].split())==2:
                    fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."
            else:
                    fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."+list(data['fio_culp'].split()[2])[0]+"."
            replace_words_in_word(["{{ Суд }}", "{{ ЦФИО }}", "{{ ЦДР }}", 
                                    "{{ Цпаспорт_серия }}", "{{ Цпаспорт_номер }}","{{ Цпаспорт_выдан }}", "{{ Цпаспорт_когда }}",
                                    "{{ ЦИндекс }}", "{{ ЦАдрес }}", "{{ ЦТелефон }}","{{ Представитель }}","{{ NДоверенности }}",
                                    "{{ Дата_доверенности }}", "{{ Телефон_представителя }}","{{ винФИО }}", "{{ ДР_Виновника }}",
                                    "{{ Серия_ВУвин }}", "{{ Номер_ВУвин }}", "{{ Дата_ВУвин }}","{{ Индекс_Виновника }}","{{ Адрес_Виновника }}",
                                    "{{ Телефон_Виновника }}",
                                    "{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                    "{{ Индекс }}", "{{ Адрес }}", "{{ Телефон }}", "{{ Страховая }}","{{ Разница }}","{{ Цена_пошлины }}",
                                    "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}",
                                    "{{ Nавто_виновник }}", "{{ винФИОкор }}", "{{ Экспертиза }}", "{{ Выплата_ОСАГО }}","{{ Nвыплатного_дела }}","{{ Дата_выплатного_дела }}",
                                    "{{ Nплатежного_поручения }}","{{ Дата_поручения }}", "{{ Год }}", "{{ NКлиента }}","{{ Дата }}", "{{ Стоимость_экспертизы }}",
                                    "{{ Цена_нотариус }}","{{ Город }}", "{{ Дата_искового_заявления }}"],
                                    [str(data["sud"]), str(data["fio_c"]), str(data["date_of_birth_c"]), str(data["seria_pasport_c"]),
                                        str(data["number_pasport_c"]), str(data["where_pasport_c"]),str(data["when_pasport_c"]), str(data["index_postal_c"]),
                                        str(data["address_c"]), str(data["number_c"]), str(data["fio_not"]), str(data["N_dov_not"]),str(data["data_dov_not"]), 
                                        str(data["number_not"]), str(data["fio_culp"]),str(data["date_of_birth_culp"]), str(data["seria_vu_culp"]),
                                        str(data["number_vu_culp"]), str(data["data_vu_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(data["number_culp"]), 
                                        str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                        str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["index_postal"]),
                                        str(data["address"]), str(data["number"]),str(data["insurance"]), str(float(data["coin_exp"])-float(data['coin_osago'])), 
                                        str(data["gos_money"]), str(data["date_dtp"]),str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                        str(data["marks_culp"]),str(data["number_auto_culp"]), str(fio_culp_k), str(data["coin_exp"]), str(data["coin_osago"]),str(data["N_viplat_work"]),
                                        str(data["date_viplat_work"]), str(data["N_plat_por"]), str(data["date_plat_por"]), str(data["year"]), str(data["client_id"]), str(data["pret"]),
                                        str(data["money_exp"]), str(data["coin_c"]), str(data["city"]), str(data["date_isk"])],
                                        "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 8. Исковое заявление Цессия.docx",
                                        data["fio"]+"\\Документы\\"+"Цессия 8. Исковое заявление Цессия.docx")
        elif "3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx" == i:
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                            "{{ ФИОк }}"],
                            [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["date_dtp"]),
                                str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),str(data["date_ins_pod"]), 
                                str(data["seria_docs"]), str(data["number_docs"]), str(data["city"]), str(data["date_ins"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx",
                                data["fio"]+"\\Документы\\"+"3. Заявление в страховую об изменении формы страхового возмещения не выплатили.docx")
        elif "3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx" == i:
            replace_words_in_word(["{{ Страховая }}", "{{ ФИО }}", "{{ ДР }}", 
                            "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                            "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}", "{{ Телефон_представителя }}",
                            "{{ Дата_ДТП }}", "{{ Время_ДТП }}", "{{ Адрес_ДТП }}","{{ Марка_модель }}","{{ Nавто_клиента }}",
                            "{{ Дата_подачи_заявления }}", "{{ Серия_полиса }}", "{{ Номер_полиса }}", "{{ Город }}", "{{ Дата_заявления_изменения }}", 
                            "{{ ФИОк }}"],
                            [str(data["insurance"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]),
                                str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), str(data["number_not"]), str(data["date_dtp"]),
                                str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),str(data["date_ins_pod"]), 
                                str(data["seria_docs"]), str(data["number_docs"]), str(data["city"]), str(data["date_ins"]), str(data["fio_k"])],
                                "Шаблоны\\1. ДТП\\2. На выплату\\2. заявление на выплату - не выплатили\\3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx",
                                data["fio"]+"\\Документы\\"+"3. Заявление в страховую об изменении формы страхового возмещения не выплатили представитель.docx")
        elif "4. Заявление о выдаче копии справки участников ДТП.docx" == i:
            replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                            "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                            [str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                                str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                                str(data["number"]), str(data["fio_k"])],
                                                "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\4. Заявление в ГИБДД\\4. Заявление о выдаче копии справки участников ДТП.docx",
                                                data["fio"]+"\\Документы\\"+"4. Заявление о выдаче копии справки участников ДТП.docx")
        elif "4. Заявление о выдаче копии справки участников ДТП представитель.docx" == i:
            replace_words_in_word(["{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}", 
                                            "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}",
                                            "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                            "{{ Дата_ДТП }}",
                                            "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                            "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                            [str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                                str(data["where_pasport"]), str(data["when_pasport"]),
                                                str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), str(data["number_not"]),
                                                str(data["date_dtp"]), str(data["time_dtp"]),
                                                str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                                str(data["number"]), str(data["fio_k"])],
                                                "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\4. Заявление в ГИБДД\\4. Заявление о выдаче копии справки участников ДТП представитель.docx",
                                                data["fio"]+"\\Документы\\"+"4. Заявление о выдаче копии справки участников ДТП представитель.docx")
        elif "3. Запрос в страховую о выдаче акта и расчёта.docx" == i:
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}",
                                        "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", "{{ Дата_ДТП }}",
                                        "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                        "{{ Nавто_виновник }}", "{{ Телефон }}", "{{ ФИОк }}"],
                                        [str(data["insurance"]),str(data["city"]),str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                            str(data["where_pasport"]), str(data["when_pasport"]),str(data["date_dtp"]), str(data["time_dtp"]),
                                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                            str(data["number"]), str(data["fio_k"])],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\3. заявление в страховую о выдаче документов\\3. Запрос в страховую о выдаче акта и расчёта.docx",
                                            data["fio"]+"\\Документы\\"+"3. Запрос в страховую о выдаче акта и расчёта.docx")
        elif "3. Запрос в страховую о выдаче акта и расчёта представитель.docx" == i:
            replace_words_in_word(["{{ Страховая }}", "{{ Город }}", "{{ ФИО }}", "{{ ДР }}", "{{ Паспорт_серия }}",
                                        "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}", 
                                        "{{ NДоверенности }}", "{{ Дата_доверенности }}","{{ Представитель }}","{{ Телефон_представителя }}",
                                        "{{ Дата_ДТП }}",
                                        "{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}","{{ Марка_модель_виновника }}",
                                        "{{ Nавто_виновник }}", "{{ Телефон }}"],
                                        [str(data["insurance"]),str(data["city"]),str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]), str(data["number_pasport"]),
                                            str(data["where_pasport"]), str(data["when_pasport"]),
                                            str(data["N_dov_not"]), str(data["data_dov_not"]),str(data["fio_not"]), str(data["number_not"]),
                                            str(data["date_dtp"]), str(data["time_dtp"]),
                                            str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),str(data["number_auto_culp"]), 
                                            str(data["number"])],
                                            "Шаблоны\\1. ДТП\\2. На выплату\\1. заявление на выплату - выплатили\\3. заявление в страховую о выдаче документов\\3. Запрос в страховую о выдаче акта и расчёта представитель.docx",
                                            data["fio"]+"\\Документы\\"+"3. Запрос в страховую о выдаче акта и расчёта представитель.docx")

