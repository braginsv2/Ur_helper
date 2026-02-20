import os
import json
import requests
from PIL import Image
from pdf2image import convert_from_path
import tempfile

# Импортируем функцию распознавания паспорта
from Scan_pasport.recognize import recognize_passport


def get_gigachat_token(auth_token):
    """
    Получить access token для GigaChat API
    
    Args:
        auth_token: токен авторизации
        
    Returns:
        str: access token
    """
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': '6f0b1291-c7f3-43c6-bb2e-9f3efb2dc98e',
        'Authorization': f'Basic {auth_token}'
    }
    
    payload = {
        'scope': 'GIGACHAT_API_PERS'
    }
    
    response = requests.post(url, headers=headers, data=payload, verify=False)
    
    if response.status_code == 200:
        return response.json()['access_token']
    else:
        raise Exception(f"Ошибка получения токена: {response.text}")

def format_with_gigachat(access_token, fio, birth_place, authority):
    """
    Форматировать данные через GigaChat
    
    Args:
        access_token: токен доступа GigaChat
        fio: ФИО
        birth_place: место рождения
        authority: кем выдан
        
    Returns:
        dict: отформатированные данные
    """
    # Если все пустые - не отправляем запрос
    if not fio and not birth_place and not authority:
        return {
            'fio': '',
            'birth_place': '',
            'authority': ''
        }
    
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    # Формируем промпт только с непустыми полями
    parts = []
    
    if fio:
        parts.append(f'1. ФИО: "{fio}"\n   - Каждое слово с заглавной буквы, остальные строчные\n   - Формат: Фамилия Имя Отчество (или Фамилия Имя, если отчества нет)')
    
    if birth_place:
        parts.append(f'2. Место рождения: "{birth_place}"\n   - Правильные знаки препинания и пробелы\n   - С заглавной буквы только абревиатуры и первые буквы населенных пунктов, районов, областей, остальные маленькие\n   - Исправь слитные слова (например "ТОМСКОГОРАЙОНА" -> "Томского района") - После сокращений населенных пунктов поставить точку П->п. (поселок) гор -> г. (город) С -> с. (село) Д -> д. (деревня) и т.д')
    
    if authority:
        parts.append(f'3. Кем выдан: "{authority}"\n   - Правильные пробелы, между словами\n   - С заглавной буквы только абревиатуры и первые буквы населенных пунктов, районов, областей, остальные маленькие\n   - Исправь слитные слова (например "ТОМСКОГОРАЙОНА" -> "Томского района")\n   - Аббревиатуры нужно заглавными (РОВД, ОВД, УФМС и т.д.) - После сокращений населенных пунктов поставить точку П->п. (поселок) гор -> г. (город) С -> с. (село) Д -> д. (деревня) и т.д')
    
    prompt = "Отформатируй данные паспорта по следующим правилам:\n\n"
    prompt += "\n\n".join(parts)
    prompt += '\n\nВерни результат ТОЛЬКО в формате JSON без дополнительного текста:\n{'
    
    # Формируем структуру JSON для ответа
    json_fields = []
    if fio:
        json_fields.append('    "fio": "отформатированное ФИО"')
    if birth_place:
        json_fields.append('    "birth_place": "отформатированное место рождения"')
    if authority:
        json_fields.append('    "authority": "отформатированный орган выдачи"')
    
    prompt += '\n' + ',\n'.join(json_fields) + '\n}'
    
    payload = {
        "model": "GigaChat",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }
    
    response = requests.post(url, headers=headers, json=payload, verify=False)
    
    if response.status_code == 200:
        content = response.json()['choices'][0]['message']['content']
        
        # Извлекаем JSON из ответа
        start = content.find('{')
        end = content.rfind('}') + 1
        
        if start != -1 and end != 0:
            json_str = content[start:end]
            result = json.loads(json_str)
            
            # Заполняем пустыми строками те поля, которые не отправляли
            if not fio:
                result['fio'] = ''
            if not birth_place:
                result['birth_place'] = ''
            if not authority:
                result['authority'] = ''
            
            return result
        else:
            raise Exception("Не удалось извлечь JSON из ответа GigaChat")
    else:
        raise Exception(f"Ошибка GigaChat API: {response.text}")



def convert_image_to_jpg(input_path):
    """
    Конвертировать изображение или PDF в JPG
    
    Args:
        input_path: путь к файлу
        
    Returns:
        str: путь к JPG файлу
    """
    _, ext = os.path.splitext(input_path.lower())
    
    # Если уже JPG, возвращаем как есть
    if ext == '.jpg' or ext == '.jpeg':
        return input_path
    
    # Если PDF, конвертируем первую страницу
    if ext == '.pdf':
        images = convert_from_path(input_path, first_page=1, last_page=1)
        
        # Сохраняем во временный файл
        temp_jpg = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        images[0].save(temp_jpg.name, 'JPEG')
        return temp_jpg.name
    
    # Для других форматов изображений
    try:
        img = Image.open(input_path)
        
        # Конвертируем в RGB если нужно
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Сохраняем во временный файл
        temp_jpg = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        img.save(temp_jpg.name, 'JPEG')
        return temp_jpg.name
        
    except Exception as e:
        raise Exception(f"Ошибка конвертации изображения: {e}")


def process_passport_image(image_path, gigachat_auth_token):
    """
    Обработать изображение паспорта и вернуть отформатированные данные
    
    Args:
        image_path: путь к изображению (jpg, png, pdf и др.)
        gigachat_auth_token: токен авторизации GigaChat
        
    Returns:
        dict: словарь с данными паспорта
    """
    temp_file = None
    
    try:
        # Конвертируем в JPG если нужно
        jpg_path = convert_image_to_jpg(image_path)
        
        # Запоминаем, если создали временный файл
        if jpg_path != image_path:
            temp_file = jpg_path
        
        # Распознаем паспорт
        passport_data = recognize_passport(jpg_path)
        
        if not passport_data:
            return None
        
        # Получаем части ФИО
        surname = passport_data.get('surname') or ''
        name = passport_data.get('name') or ''
        patronymic = passport_data.get('patronymic') or ''
        
        # ЛОГИКА ФИО:
        # Если нет фамилии ИЛИ нет имени → fio = ''
        # Если есть фамилия И имя, но нет отчества → fio = Фамилия + Имя
        # Если есть всё → fio = Фамилия + Имя + Отчество
        
        if not surname or not name:
            # Нет фамилии или имени - пустая строка
            fio_raw = ''
        else:
            # Есть и фамилия и имя
            if patronymic:
                # Есть всё - ФИО
                fio_raw = f"{surname} {name} {patronymic}"
            else:
                # Нет отчества - только ФИ
                fio_raw = f"{surname} {name}"
        
        birth_place_raw = passport_data.get('birth_place') or ''
        authority_raw = passport_data.get('authority') or ''
        
        # Получаем access token для GigaChat
        access_token = get_gigachat_token(gigachat_auth_token)
        
        # Форматируем через GigaChat
        formatted = format_with_gigachat(
            access_token,
            fio_raw,
            birth_place_raw,
            authority_raw
        )
        
        # Формируем результат
        result = {
            'fio': formatted.get('fio', ''),
            'seria_pasport': str(passport_data.get('series') or ''),
            'number_pasport': str(passport_data.get('number') or ''),
            'where_pasport': formatted.get('authority', ''),
            'when_pasport': str(passport_data.get('issue_date') or ''),
            'date_of_birth': str(passport_data.get('birth_date') or ''),
            'city_birth': formatted.get('birth_place', '')
        }
        
        return result
        
    except Exception as e:
        print(f"Ошибка обработки паспорта: {e}")
        return None
        
    finally:
        # Удаляем временный файл если создавали
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except:
                pass

