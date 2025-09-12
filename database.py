import sqlite3
import json
from datetime import datetime
import os

class DatabaseManager:
    def __init__(self, db_path="clients.db"):
        """Инициализация базы данных"""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Создание таблицы если она не существует"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accident TEXT,           
            client_id TEXT UNIQUE NOT NULL,
            fio TEXT NOT NULL,
            seria_pasport INTEGER,
            number_pasport INTEGER,
            where_pasport TEXT,
            when_pasport TEXT,
            address TEXT,
            index_postal INTEGER,
            number TEXT,
            date_of_birth TEXT,
            city_birth TEXT,
            date_dtp TEXT,
            time_dtp TEXT,
            address_dtp TEXT,
            who_dtp TEXT,
            marks TEXT,
            car_number TEXT,
            year_auto INTEGER,
            docs TEXT,
            seria_docs TEXT,
            number_docs TEXT,
            data_docs TEXT,
            insurance TEXT,
            seria_insurance TEXT,
            number_insurance TEXT,
            date_insurance TEXT,
            fio_culp TEXT,
            marks_culp TEXT,
            number_auto_culp TEXT,
            bank TEXT,
            bank_account TEXT,
            bank_account_corr TEXT,
            BIK TEXT,
            INN TEXT,
            created_at TEXT,
            data_json TEXT,
            sobstvenik TEXT,
            fio_sobs TEXT,
            date_of_birth_sobs TEXT,
            answer_ins TEXT,
            analis_ins TEXT,
            vibor TEXT,
            vibor1 TEXT,
            Nv_ins TEXT,
            date_coin_ins TEXT,
            Na_ins TEXT,
            date_Na_ins TEXT,
            date_exp TEXT,
            org_exp TEXT,
            coin_exp TEXT,
            date_sto TEXT,
            time_sto TEXT,
            address_sto TEXT,
            coin_exp_izn TEXT,
            coin_osago TEXT,
            coin_not TEXT,
            N_dov_not TEXT,
            data_dov_not TEXT,
            fio_not TEXT,
            number_not TEXT,
            date_ins TEXT,
            date_pret TEXT,
            pret TEXT,
            ombuc Text,
            data_pret_prin TEXT,
            data_pret_otv TEXT,
            N_pret_prin TEXT,
            date_ombuc TEXT,
            date_ins_pod TEXT,
            seria_vu_culp TEXT,
            number_vu_culp TEXT,
            data_vu_culp TEXT,
            date_of_birth_culp TEXT,
            index_culp TEXT,
            address_culp TEXT,
            number_culp TEXT,
            N_viplat_work TEXT,
            date_viplat_work TEXT,
            N_plat_por TEXT,
            date_plat_por TEXT,
            sud TEXT,
            gos_money TEXT,
            date_izvesh_dtp TEXT,
            date_isk TEXT,
            dop_osm TEXT,
            ev TEXT,
            fio_k TEXT,
            data_dop_osm TEXT,
            viborRem TEXT,
            date_zayav_sto TEXT,
            pret_sto TEXT,
            data_otkaz_sto TEXT,
            date_napr_sto TEXT,
            address_sto_main TEXT,
            data_sto_main TEXT,
            time_sto_main TEXT,
            city_sto TEXT,
            Done TEXT,
            city TEXT,
            year TEXT,
            street TEXT,
            N_gui TEXT,
            date_gui TEXT,
            N_prot TEXT,
            date_prot TEXT,
            date_road TEXT,
            N_kv_not TEXT,
            date_kv_not TEXT,
            N_kv_ur TEXT,
            date_kv_ur TEXT,
            N_kv_exp TEXT,
            status TEXT,
            fio_c TEXT,
            fio_c_k TEXT,
            seria_pasport_c TEXT,
            number_pasport_c TEXT,
            where_pasport_c TEXT,
            when_pasport_c TEXT,
            address_c TEXT,
            date_of_birth_c TEXT,
            coin_c TEXT,
            city_birth_с TEXT,
            index_postal_c TEXT,
            number_c TEXT,
            money_exp TEXT
                     
        )
        ''')
        
        # Создаем индекс для быстрого поиска по client_id
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_id ON clients(client_id)')
        # Добавляем индекс для поиска по ФИО
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fio ON clients(fio)')
        
        conn.commit()
        conn.close()
        print("База данных инициализирована")
    
    def generate_next_client_id(self):
        """Генерация следующего client_id в формате 70XXX"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Ищем максимальный client_id, который начинается с "70"
        cursor.execute('''
        SELECT client_id FROM clients 
        WHERE client_id LIKE '70%' 
        ORDER BY CAST(client_id AS INTEGER) DESC 
        LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            # Если есть клиенты, увеличиваем номер на 1
            last_id = int(result[0])
            next_id = last_id + 1
        else:
            # Если клиентов нет, начинаем с 70001
            next_id = 70001
        
        return str(next_id)
    
    def save_client_data_with_generated_id(self, data):
        """Генерирует client_id, добавляет в data и сохраняет в базу ИЛИ обновляет существующего клиента"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Текущая дата и время
        created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        # Проверяем, существует ли клиент с таким ФИО
        fio_to_check = data.get('fio', '').strip()
        cursor.execute("SELECT client_id, data_json FROM clients WHERE fio = ?", (fio_to_check,))
        existing_client = cursor.fetchone()
        
        if existing_client:
            # Клиент существует - обновляем его данные
            existing_client_id = existing_client[0]
            existing_data_json = existing_client[1]
            
            # Парсим существующие данные из JSON
            try:
                existing_data = json.loads(existing_data_json) if existing_data_json else {}
            except (json.JSONDecodeError, TypeError):
                existing_data = {}
            
            # Объединяем существующие данные с новыми (новые имеют приоритет)
            merged_data = {**existing_data, **data}
            merged_data['client_id'] = existing_client_id  # Сохраняем существующий client_id
            
            print(f"Обновляем существующего клиента с client_id: {existing_client_id}")
            
            # Подготовка данных для обновления
            update_data = {
                'accident': merged_data.get('accident',''),
                'client_id': existing_client_id,
                'fio': merged_data.get('fio', ''),
                'seria_pasport': merged_data.get('seria_pasport', 0),
                'number_pasport': merged_data.get('number_pasport', 0),
                'where_pasport': merged_data.get('where_pasport', ''),
                'when_pasport': merged_data.get('when_pasport', ''),
                'address': merged_data.get('address', ''),
                'index_postal': merged_data.get('index_postal', 0),
                'number': merged_data.get('number', ''),
                'date_of_birth': merged_data.get('date_of_birth', ''),
                'city_birth': merged_data.get('city_birth', ''),
                'date_dtp': merged_data.get('date_dtp', ''),
                'time_dtp': merged_data.get('time_dtp', ''),
                'address_dtp': merged_data.get('address_dtp', ''),
                'who_dtp': merged_data.get('who_dtp', ''),
                'marks': merged_data.get('marks', ''),
                'car_number': merged_data.get('car_number', ''),
                'year_auto': merged_data.get('year_auto', 0),
                'docs': merged_data.get('docs', ''),
                'seria_docs': merged_data.get('seria_docs', ''),
                'number_docs': merged_data.get('number_docs', ''),
                'data_docs': merged_data.get('data_docs', ''),
                'insurance': merged_data.get('insurance', ''),
                'seria_insurance': merged_data.get('seria_insurance', ''),
                'number_insurance': merged_data.get('number_insurance', ''),
                'date_insurance': merged_data.get('date_insurance', ''),
                'fio_culp': merged_data.get('fio_culp', ''),
                'marks_culp': merged_data.get('marks_culp', ''),
                'number_auto_culp': merged_data.get('number_auto_culp', ''),
                'bank': merged_data.get('bank', ''),
                'bank_account': merged_data.get('bank_account', ''),
                'bank_account_corr': merged_data.get('bank_account_corr', ''),
                'BIK': merged_data.get('BIK', ''),
                'INN': merged_data.get('INN', ''),
                'created_at': created_at,
                'data_json': json.dumps(merged_data, ensure_ascii=False),
                'sobstvenik': merged_data.get('sobstvenik', ''),
                'fio_sobs': merged_data.get('fio_sobs', ''),
                'date_of_birth_sobs': merged_data.get('date_of_birth_sobs',''),
                'answer_ins': merged_data.get('answer_ins', ''),
                'analis_ins': merged_data.get('analis_ins', ''),
                'vibor': merged_data.get('vibor', ''),
                'vibor1': merged_data.get('vibor1', ''),
                'Nv_ins': merged_data.get('Nv_ins', ''),
                'date_coin_ins': merged_data.get('date_coin_ins', ''),
                'Na_ins': merged_data.get('Na_ins', ''),
                'date_Na_ins': merged_data.get('date_Na_ins', ''),
                'date_exp': merged_data.get('date_exp', ''),
                'org_exp': merged_data.get('org_exp', ''),
                'coin_exp': merged_data.get('coin_exp', ''),
                'date_sto': merged_data.get('date_sto', ''),
                'time_sto': merged_data.get('time_sto', ''),
                'address_sto': merged_data.get('address_sto', ''), 
                'coin_exp_izn': merged_data.get('coin_exp_izn', ''), 
                'coin_osago': merged_data.get('coin_osago', ''), 
                'coin_not': merged_data.get('coin_not', ''), 
                'N_dov_not': merged_data.get('N_dov_not', ''), 
                'data_dov_not': merged_data.get('data_dov_not', ''), 
                'fio_not': merged_data.get('fio_not', ''), 
                'number_not': merged_data.get('number_not', ''),
                'date_ins': merged_data.get('date_ins', ''),
                'date_pret': merged_data.get('date_pret', ''),
                'pret': merged_data.get('pret', ''),
                'ombuc': merged_data.get('ombuc', ''),
                'data_pret_prin': merged_data.get('data_pret_prin', ''),
                'data_pret_otv': merged_data.get('data_pret_otv', ''),
                'N_pret_prin': merged_data.get('N_pret_prin', ''),
                'date_ombuc': merged_data.get('date_ombuc', ''),
                'date_ins_pod': merged_data.get('date_ins_pod', ''),
                'seria_vu_culp': merged_data.get('seria_vu_culp', ''),
                'number_vu_culp': merged_data.get('number_vu_culp', ''),
                'data_vu_culp': merged_data.get('data_vu_culp', ''),
                'date_of_birth_culp': merged_data.get('date_of_birth_culp', ''),
                'index_culp': merged_data.get('index_culp', ''),
                'address_culp': merged_data.get('address_culp', ''),
                'number_culp': merged_data.get('number_culp', ''),
                'N_viplat_work': merged_data.get('N_viplat_work', ''),
                'date_viplat_work': merged_data.get('date_viplat_work', ''),
                'N_plat_por': merged_data.get('N_plat_por', ''),
                'date_plat_por': merged_data.get('date_plat_por', ''),
                'sud': merged_data.get('sud', ''),
                'gos_money': merged_data.get('gos_money', ''),
                'date_izvesh_dtp': merged_data.get('date_izvesh_dtp', ''),
                'date_isk': merged_data.get('date_isk', ''),
                'dop_osm': merged_data.get('dop_osm', ''),
                'ev': merged_data.get('ev', ''),
                'fio_k':merged_data.get('fio_k', ''),
                'data_dop_osm': merged_data.get('data_dop_osm', ''),
                'viborRem': merged_data.get('viborRem', ''),
                'date_zayav_sto':merged_data.get('date_zayav_sto', ''),
                'pret_sto':merged_data.get('pret_sto', ''),
                'data_otkaz_sto':merged_data.get('data_otkaz_sto', ''),
                'date_napr_sto':merged_data.get('date_napr_sto', ''),
                'address_sto_main':merged_data.get('address_sto_main', ''),
                'data_sto_main':merged_data.get('data_sto_main', ''),
                'time_sto_main':merged_data.get('time_sto_main', ''),
                'city_sto':merged_data.get('city_sto', ''),
                'Done':merged_data.get('Done', ''),
                'city':merged_data.get('city', ''),
                'year':merged_data.get('year', ''),
                'street':merged_data.get('street', ''),
                'N_gui':merged_data.get('N_gui', ''),
                'date_gui':merged_data.get('date_gui', ''),
                'N_prot':merged_data.get('N_prot', ''),
                'date_prot':merged_data.get('date_prot', ''),
                'date_road':merged_data.get('date_road', ''),
                'N_kv_not':merged_data.get('N_kv_not', ''),
                'date_kv_not':merged_data.get('date_kv_not', ''),
                'N_kv_ur':merged_data.get('N_kv_ur', ''),
                'date_kv_ur':merged_data.get('date_kv_ur', ''),
                'N_kv_exp': merged_data.get('N_kv_exp', ''),
                'status': merged_data.get('status', ''),
                'fio_c': merged_data.get('fio_c', ''),
                'fio_c_k': merged_data.get('fio_c_k', ''),
                'seria_pasport_c': merged_data.get('seria_pasport_c', 0),
                'number_pasport_c': merged_data.get('number_pasport_c', 0),
                'where_pasport_c': merged_data.get('where_pasport_c', ''),
                'when_pasport_c': merged_data.get('when_pasport_c', ''),
                'address_c': merged_data.get('address_c', ''),
                'date_of_birth_c': merged_data.get('date_of_birth_c', ''),
                'coin_c': merged_data.get('coin_c', ''),
                'city_birth_с': merged_data.get('city_birth_с', ''),
                'index_postal_c':merged_data.get('index_postal_c', ''),
                'number_c':merged_data.get('number_c', ''),
                'money_exp':merged_data.get('money_exp', ''),
            }
            
            # SQL запрос для обновления
            update_query = '''
            UPDATE clients SET 
                accident=?, client_id=?, fio=?, seria_pasport=?, number_pasport=?, where_pasport=?, when_pasport=?,
                address=?, index_postal=?, number=?, date_of_birth=?, city_birth=?,
                date_dtp=?, time_dtp=?, address_dtp=?, who_dtp=?, marks=?, car_number=?,
                year_auto=?, docs=?, seria_docs=?, number_docs=?, data_docs=?,
                insurance=?, seria_insurance=?, number_insurance=?, date_insurance=?,
                fio_culp=?, marks_culp=?, number_auto_culp=?,
                bank=?, bank_account=?, bank_account_corr=?, BIK=?, INN=?,
                created_at=?, data_json=?, sobstvenik=?, fio_sobs=?, date_of_birth_sobs=?, answer_ins=?, analis_ins=?,
                vibor=?, vibor1=?, Nv_ins=?, date_coin_ins=?,Na_ins=?, date_Na_ins=?, date_exp=?, org_exp=?, coin_exp=?, 
                date_sto=?, time_sto=?, address_sto=?, coin_exp_izn=?, coin_osago=?, coin_not=?, 
                N_dov_not=?, data_dov_not=?, fio_not=?, number_not=?, date_ins=?, date_pret=?, pret=?, ombuc=?,data_pret_prin=?,
                data_pret_otv=?,N_pret_prin=?, date_ombuc=?,date_ins_pod=?,seria_vu_culp=?,number_vu_culp=?,data_vu_culp=?, date_of_birth_culp=?,
                index_culp=?,address_culp=?,number_culp=?, N_viplat_work=?,date_viplat_work=?, N_plat_por=?,date_plat_por=?,sud=?,gos_money=?,
                date_izvesh_dtp=?, date_isk=?, dop_osm=?, ev=?, fio_k=?, data_dop_osm=?, viborRem=?,date_zayav_sto=?, pret_sto=?,data_otkaz_sto=?,date_napr_sto=?,
                address_sto_main=?,data_sto_main=?, time_sto_main=?, city_sto=?, Done=?, city=?, year=?, street=?, N_gui=?, date_gui=?, N_prot=?, date_prot=?,
                date_road=?, N_kv_not=?, date_kv_not=?, N_kv_ur=?, date_kv_ur=?,N_kv_exp=?, status=?, fio_c=?, fio_c_k=?, seria_pasport_c=?,number_pasport_c=?,
                where_pasport_c=?, when_pasport_c=?, address_c=?, date_of_birth_c=?, coin_c=?, city_birth_с=?, index_postal_c=?, number_c=?, money_exp=?
            WHERE client_id=?
            '''
            
            try:
                # Добавляем client_id в конец для WHERE условия
                update_values = list(update_data.values()) + [existing_client_id]
                cursor.execute(update_query, update_values)
                
                conn.commit()
                conn.close()
                
                print(f"Клиент обновлен в базе с client_id: {existing_client_id}")
                
                # Возвращаем существующий client_id и обновленные данные
                return existing_client_id, merged_data
                
            except Exception as e:
                conn.close()
                print(f"Ошибка обновления клиента: {e}")
                raise e
        
        else:
            # Клиент не существует - создаем нового
            print("Создаем нового клиента")
            
            # 1. Генерируем client_id
            client_id = self.generate_next_client_id()
            
            # 2. Добавляем client_id в данные
            data['client_id'] = client_id
            
            # Подготовка данных для базы
            client_data = {
                'accident': data.get('accident',''),
                'client_id': client_id,
                'fio': data.get('fio', ''),
                'seria_pasport': data.get('seria_pasport', 0),
                'number_pasport': data.get('number_pasport', 0),
                'where_pasport': data.get('where_pasport', ''),
                'when_pasport': data.get('when_pasport', ''),
                'address': data.get('address', ''),
                'index_postal': data.get('index_postal', 0),
                'number': data.get('number', ''),
                'date_of_birth': data.get('date_of_birth', ''),
                'city_birth': data.get('city_birth', ''),
                'date_dtp': data.get('date_dtp', ''),
                'time_dtp': data.get('time_dtp', ''),
                'address_dtp': data.get('address_dtp', ''),
                'who_dtp': data.get('who_dtp', ''),
                'marks': data.get('marks', ''),
                'car_number': data.get('car_number', ''),
                'year_auto': data.get('year_auto', 0),
                'docs': data.get('docs', ''),
                'seria_docs': data.get('seria_docs', ''),
                'number_docs': data.get('number_docs', ''),
                'data_docs': data.get('data_docs', ''),
                'insurance': data.get('insurance', ''),
                'seria_insurance': data.get('seria_insurance', ''),
                'number_insurance': data.get('number_insurance', ''),
                'date_insurance': data.get('date_insurance', ''),
                'fio_culp': data.get('fio_culp', ''),
                'marks_culp': data.get('marks_culp', ''),
                'number_auto_culp': data.get('number_auto_culp', ''),
                'bank': data.get('bank', ''),
                'bank_account': data.get('bank_account', ''),
                'bank_account_corr': data.get('bank_account_corr', ''),
                'BIK': data.get('BIK', ''),
                'INN': data.get('INN', ''),
                'created_at': created_at,
                'data_json': json.dumps(data, ensure_ascii=False),
                'sobstvenik': data.get('sobstvenik', ''),
                'fio_sobs': data.get('fio_sobs', ''),
                'date_of_birth_sobs': data.get('date_of_birth_sobs',''),
                'answer_ins': data.get('answer_ins', ''),
                'analis_ins': data.get('analis_ins', ''),
                'vibor': data.get('vibor', ''),
                'vibor1': data.get('vibor1', ''),
                'Nv_ins': data.get('Nv_ins', ''),
                'date_coin_ins': data.get('date_coin_ins', ''),
                'Na_ins': data.get('Na_ins', ''),
                'date_Na_ins': data.get('date_Na_ins', ''),
                'date_exp': data.get('date_exp', ''),
                'org_exp': data.get('org_exp', ''),
                'coin_exp': data.get('coin_exp', ''),
                'date_sto': data.get('date_sto', ''),
                'time_sto': data.get('time_sto', ''),
                'address_sto': data.get('address_sto', ''), 
                'coin_exp_izn': data.get('coin_exp_izn', ''), 
                'coin_osago': data.get('coin_osago', ''), 
                'coin_not': data.get('coin_not', ''), 
                'N_dov_not': data.get('N_dov_not', ''), 
                'data_dov_not': data.get('data_dov_not', ''), 
                'fio_not': data.get('fio_not', ''), 
                'number_not': data.get('number_not', ''),
                'date_ins': data.get('date_ins', ''),
                'date_pret': data.get('date_pret', ''),
                'pret': data.get('pret', ''),
                'ombuc': data.get('ombuc', ''),
                'data_pret_prin': data.get('data_pret_prin', ''),
                'data_pret_otv': data.get('data_pret_otv', ''),
                'N_pret_prin': data.get('N_pret_prin', ''),
                'date_ombuc': data.get('date_ombuc', ''),
                'date_ins_pod': data.get('date_ins_pod', ''),
                'seria_vu_culp': data.get('seria_vu_culp', ''),
                'number_vu_culp': data.get('number_vu_culp', ''),
                'data_vu_culp': data.get('data_vu_culp', ''),
                'date_of_birth_culp': data.get('date_of_birth_culp', ''),
                'index_culp': data.get('index_culp', ''),
                'address_culp': data.get('address_culp', ''),
                'number_culp': data.get('number_culp', ''),
                'N_viplat_work': data.get('N_viplat_work', ''),
                'date_viplat_work': data.get('date_viplat_work', ''),
                'N_plat_por': data.get('N_plat_por', ''),
                'date_plat_por': data.get('date_plat_por', ''),
                'sud': data.get('sud', ''),
                'gos_money': data.get('gos_money', ''),
                'date_izvesh_dtp': data.get('date_izvesh_dtp', ''),
                'date_isk': data.get('date_isk', ''),
                'dop_osm': data.get('dop_osm', ''),
                'ev': data.get('ev', ''),
                'fio_k':data.get('fio_k', ''),
                'data_dop_osm': data.get('data_dop_osm', ''),
                'viborRem': data.get('viborRem', ''),
                'date_zayav_sto':data.get('date_zayav_sto', ''),
                'pret_sto':data.get('pret_sto', ''),
                'data_otkaz_sto':data.get('data_otkaz_sto', ''),
                'date_napr_sto': data.get('date_napr_sto', ''),
                'address_sto_main': data.get('address_sto_main', ''),
                'data_sto_main': data.get('data_sto_main', ''),
                'time_sto_main': data.get('time_sto_main', ''),
                'city_sto': data.get('city_sto', ''),
                'Done': data.get('Done', ''),
                'city': data.get('city', ''),
                'year': data.get('year', ''),
                'street': data.get('street', ''),
                'N_gui': data.get('N_gui', ''),
                'date_gui': data.get('date_gui', ''),
                'N_prot': data.get('N_prot', ''),
                'date_prot': data.get('date_prot', ''),
                'date_road': data.get('date_road', ''),
                'N_kv_not': data.get('N_kv_not', ''),
                'date_kv_not': data.get('date_kv_not', ''),
                'N_kv_ur': data.get('N_kv_ur', ''),
                'date_kv_ur': data.get('date_kv_ur', ''),
                'N_kv_exp': data.get('N_kv_exp', ''),
                'status': data.get('status', ''),
                'fio_c': data.get('fio_c', ''),
                'fio_c_k': data.get('fio_c_k', ''),
                'seria_pasport_c': data.get('seria_pasport_c', 0),
                'number_pasport_c': data.get('number_pasport_c', 0),
                'where_pasport_c': data.get('where_pasport_c', ''),
                'when_pasport_c': data.get('when_pasport_c', ''),
                'address_c': data.get('address_c', ''),
                'date_of_birth_c': data.get('date_of_birth_c', ''),
                'coin_c': data.get('coin_c', ''),
                'city_birth_с': data.get('city_birth_с', ''),
                'index_postal_c': data.get('index_postal_c', ''),
                'number_c': data.get('number_c', ''),
                'money_exp': data.get('money_exp', ''),
            }
            
            # SQL запрос для вставки
            insert_query = '''
            INSERT INTO clients (
                accident, client_id, fio, seria_pasport, number_pasport, where_pasport, when_pasport,
                address ,  index_postal, number , date_of_birth , city_birth ,
                date_dtp , time_dtp , address_dtp , who_dtp , marks , car_number ,
                year_auto , docs , seria_docs , number_docs , data_docs ,
                insurance , seria_insurance , number_insurance , date_insurance ,
                fio_culp , marks_culp , number_auto_culp ,
                bank , bank_account , bank_account_corr , BIK , INN ,
                created_at, data_json , sobstvenik , fio_sobs , date_of_birth_sobs , answer_ins , analis_ins ,
                vibor , vibor1 , Nv_ins , date_coin_ins , Na_ins , date_Na_ins , date_exp , org_exp , coin_exp , 
                date_sto , time_sto , address_sto , coin_exp_izn , coin_osago , coin_not , 
                N_dov_not , data_dov_not , fio_not , number_not , date_ins , date_pret, pret, ombuc,data_pret_prin, data_pret_otv,N_pret_prin,date_ombuc,
                date_ins_pod,seria_vu_culp ,number_vu_culp ,data_vu_culp , date_of_birth_culp ,
                index_culp ,address_culp ,number_culp , N_viplat_work ,date_viplat_work , N_plat_por ,date_plat_por ,sud ,gos_money ,
                date_izvesh_dtp , date_isk,dop_osm, ev, fio_k,data_dop_osm, viborRem,date_zayav_sto,pret_sto, data_otkaz_sto,date_napr_sto,
                address_sto_main,data_sto_main,time_sto_main, city_sto, Done, city,year, street, N_gui, date_gui, N_prot,date_prot, date_road,
                N_kv_not, date_kv_not, N_kv_ur, date_kv_ur,N_kv_exp, status,fio_c,fio_c_k, seria_pasport_c,number_pasport_c,where_pasport_c,when_pasport_c, 
                address_c, date_of_birth_c,coin_c, city_birth_с, index_postal_c, number_c, money_exp    
            ) VALUES (?, ?, ?, ?, ?, ?, ?,?, ?, ?, ?,?,?,?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?,?,?, ?,?,?,?, ?, ?,?,?,?, ?,?,?,?,?,?,?,?, ?, ?, ?,?,?,?,?,?,?,?, ?, ?, ?, ?, ?,?, ?, ?, ?, ?, ?, ?, ?,?, ?, ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            '''
            
            try:
                cursor.execute(insert_query, tuple(client_data.values()))
                db_id = cursor.lastrowid
                
                conn.commit()
                conn.close()
                
                print(f"Новый клиент сохранен в базу с client_id: {client_id}, db_id: {db_id}")
                
                # 4. Возвращаем client_id и обновленный data
                return client_id, data
                
            except sqlite3.IntegrityError as e:
                # В случае конфликта client_id, пробуем еще раз
                conn.close()
                print(f"Конфликт client_id, генерируем новый: {e}")
                return self.save_client_data_with_generated_id(data)
    
    def get_client_by_client_id(self, client_id):
        """Получение клиента по client_id"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clients WHERE client_id = ?", (client_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, result))
        return None
    
    def search_clients(self, search_term):
        """Улучшенный поиск клиентов по ФИО, номеру телефона, номеру авто или client_id"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        search_term = search_term.strip()
        results = []
        
        # 1. Поиск точного совпадения по всем полям
        exact_patterns = [
            search_term,
            search_term.lower(),
            search_term.upper(),
            search_term.title()
        ]
        
        for pattern in exact_patterns:
            search_query = '''
            SELECT id, client_id, fio, number, car_number, date_dtp, created_at, 
                   COALESCE(data_json, '{}') as data_json
            FROM clients 
            WHERE fio = ? OR number = ? OR car_number = ? OR client_id = ?
            ORDER BY created_at DESC
            '''
            
            try:
                cursor.execute(search_query, (pattern, pattern, pattern, pattern))
                exact_results = cursor.fetchall()
                if exact_results:
                    results.extend(exact_results)
                    break
            except Exception as e:
                print(f"Ошибка точного поиска: {e}")
                continue
        
        # 2. Поиск частичного совпадения
        if not results:
            partial_patterns = [
                f"%{search_term}%",
                f"%{search_term.lower()}%",
                f"%{search_term.upper()}%",
                f"%{search_term.title()}%"
            ]
            
            for pattern in partial_patterns:
                search_query = '''
                SELECT id, client_id, fio, number, car_number, date_dtp, created_at, 
                       COALESCE(data_json, '{}') as data_json
                FROM clients 
                WHERE fio LIKE ? OR number LIKE ? OR car_number LIKE ? OR client_id LIKE ?
                ORDER BY created_at DESC
                '''
                
                try:
                    cursor.execute(search_query, (pattern, pattern, pattern, pattern))
                    partial_results = cursor.fetchall()
                    if partial_results:
                        results.extend(partial_results)
                        break
                except Exception as e:
                    print(f"Ошибка частичного поиска: {e}")
                    continue
        
        # 3. Поиск по отдельным словам (для ФИО)
        if not results:
            search_words = search_term.split()
            if len(search_words) >= 2:
                first_word = search_words[0].strip()
                second_word = search_words[1].strip()
                
                # Различные варианты регистра
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
                        search_query = '''
                        SELECT id, client_id, fio, number, car_number, date_dtp, created_at, 
                               COALESCE(data_json, '{}') as data_json
                        FROM clients 
                        WHERE fio LIKE ? AND fio LIKE ?
                        ORDER BY created_at DESC
                        '''
                        
                        try:
                            cursor.execute(search_query, (f"%{first_variants}%", f"%{second_variants}%"))
                            word_results = cursor.fetchall()
                            if word_results:
                                results.extend(word_results)
                                break
                        except Exception as e:
                            print(f"Ошибка поиска по словам: {e}")
                            continue
                    
                    if results:
                        break
        
        conn.close()
        
        # Удаляем дубликаты по client_id
        unique_results = []
        seen_client_ids = set()
        
        for result in results:
            client_id = result[1]  # client_id на позиции 1
            if client_id not in seen_client_ids:
                unique_results.append(result)
                seen_client_ids.add(client_id)
        
        columns = ['id', 'client_id', 'fio', 'number', 'car_number', 'date_dtp', 'created_at', 'data_json']
        return [dict(zip(columns, row)) for row in unique_results]
    
    def search_clients_by_fio(self, search_term):
        """Специализированный поиск только по ФИО с расширенными возможностями"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        search_term = search_term.strip()
        results = []
        
        print(f"Поиск по ФИО: '{search_term}'")
        
        # 1. Точное совпадение
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
                print(f"Ошибка точного поиска по ФИО: {e}")
                continue
        
        # 2. Частичное совпадение
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
                    print(f"Ошибка частичного поиска по ФИО: {e}")
                    continue
        
        # 3. Поиск по отдельным словам
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
        
        print(f"Уникальных результатов поиска по ФИО: {len(unique_results)}")
        
        columns = ['id', 'client_id', 'fio', 'number', 'car_number', 'date_dtp', 'created_at', 'data_json']
        return [dict(zip(columns, row)) for row in unique_results]
    
    def get_database_stats(self):
        """Статистика базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Общее количество клиентов
        cursor.execute("SELECT COUNT(*) FROM clients")
        total_clients = cursor.fetchone()[0]
        
        # Последний client_id
        cursor.execute('''
        SELECT client_id FROM clients 
        WHERE client_id LIKE '70%' 
        ORDER BY CAST(client_id AS INTEGER) DESC 
        LIMIT 1
        ''')
        last_client_id = cursor.fetchone()
        last_client_id = last_client_id[0] if last_client_id else "Нет клиентов"
        
        # Размер базы данных
        db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        
        conn.close()
        
        return {
            'total_clients': total_clients,
            'last_client_id': last_client_id,
            'db_size_mb': round(db_size / (1024 * 1024), 2)
        }


# Обновленные функции для интеграции с ботом
def save_client_to_db_with_id(data):
    """Сохранение данных клиента в базу с генерацией client_id"""
    db = DatabaseManager()
    return db.save_client_data_with_generated_id(data)

def search_clients_in_db(search_term):
    """Поиск клиентов в базе (универсальный)"""
    db = DatabaseManager()
    return db.search_clients(search_term)

def search_clients_by_fio_in_db(search_term):
    """Поиск клиентов в базе только по ФИО"""
    db = DatabaseManager()
    return db.search_clients_by_fio(search_term)

def get_client_from_db_by_client_id(client_id):
    """Получение клиента по client_id"""
    db = DatabaseManager()
    return db.get_client_by_client_id(client_id)

def get_db_stats():
    """Получение статистики базы данных"""
    db = DatabaseManager()
    return db.get_database_stats()