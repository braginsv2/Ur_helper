from docx import Document
import os
from datetime import datetime

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
