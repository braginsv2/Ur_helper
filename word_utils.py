from docx import Document
import os
from datetime import datetime
import sqlite3
import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

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

