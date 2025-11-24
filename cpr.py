from telebot import types
import re
import json
from datetime import datetime
from database import (
    DatabaseManager,
    get_client_from_db_by_client_id,
    save_client_to_db_with_id
)
from word_utils import create_fio_data_file, replace_words_in_word, get_next_business_date


db = DatabaseManager()

def setup_pretenziya_handlers(bot, user_temp_data):
    """Регистрация обработчиков для претензий, заявлений к омбудсмену и исков"""
    
    # ========== СОСТАВЛЕНИЕ ПРЕТЕНЗИИ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_pretenziya_"))
    def callback_create_pretenziya(call):
        """Начало составления претензии"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_pretenziya_", "")
        
        # Загружаем данные клиента
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
        
        # Проверяем наличие необходимых документов
        payment_confirmed = data.get('payment_confirmed', '') == 'Yes'
        doverennost_confirmed = data.get('doverennost_confirmed', '') == 'Yes'
        
        if not payment_confirmed or not doverennost_confirmed:
            missing = []
            if not payment_confirmed:
                missing.append("документ об оплате")
            if not doverennost_confirmed:
                missing.append("нотариальная доверенность")
            
            bot.answer_callback_query(
                call.id, 
                f"❌ Для составления претензии необходимо загрузить: {', '.join(missing)}", 
                show_alert=True
            )
            return
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['pretenziya_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')
        if data["vibor"] == "vibor1":
            if data.get("Nv_ins", '') != '':
                msg = bot.send_message(call.message.chat.id, text="Введите дату экспертного заключения")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_exp, data, user_message_id)
            else:
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)
        elif data["vibor"] == "vibor2":
            if data.get("Nv_ins", '') != '':
                msg = bot.send_message(call.message.chat.id, text="Введите дату направления на СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
            else:
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)
        elif data["vibor"] == "vibor4":
            if data.get("Nv_ins", '') != '':
                msg = bot.send_message(call.message.chat.id, text="Введите дату направления на СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
            else:
                msg = bot.send_message(call.message.chat.id, text="Введите входящий номер в страховую")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, Nv_ins, data, user_message_id)

        
    
    # ========== ЗАЯВЛЕНИЕ К ФИН.ОМБУДСМЕНУ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_ombudsmen_"))
    def callback_create_ombudsmen(call):
        """Начало составления заявления к фин.омбудсмену"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_ombudsmen_", "")
        
        # Загружаем данные клиента
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
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['ombudsmen_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')
        if data["vibor"] == "vibor1":
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"YESprRem")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"NOprV1")
            keyboard.add(btn1)
            keyboard.add(btn2)
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Удовлетворена ли претензия?",
                reply_markup=keyboard
                )
        elif data["vibor"] == "vibor2" or data.get("vibor", "") == "vibor4":
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("Да", callback_data=f"YESprRem")
            btn2 = types.InlineKeyboardButton("Нет", callback_data=f"NOprV2")
            keyboard.add(btn1)
            keyboard.add(btn2)
            
            msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="СТО была заменена?",
                reply_markup=keyboard
                )
    @bot.callback_query_handler(func=lambda call: call.data == "NOprV2")
    def callback_ombudsmen_noV2(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]['ombudsmen_data']
        msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите дату экспертного заключения (ДД.ММ.ГГГГ)"
                )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_exp, data, user_message_id)
    @bot.callback_query_handler(func=lambda call: call.data == "YESprRem")
    def callback_ombudsmen_yes(call):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("1", callback_data=f"vibor2"))
        keyboard.add(types.InlineKeyboardButton("2", callback_data=f"vibor3"))
        keyboard.add(types.InlineKeyboardButton("3", callback_data=f"vibor4"))
        bot.edit_message_text(call.message.chat.id, call.message.message_id, "Выберите из предложенных вариантов:\n" \
        "1) Страховая компания выдала направление на ремонт, СТО отказала.\n" \
        "2) Страховая выдала направление на ремонт и ремонт произведен.\n" \
        "3) Страховая компания выдала направление на ремонт, СТО дальше 50 км.",
        reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "NOprV1")
    def callback_ombudsmen_no(call):
        user_id = call.from_user.id
        data = user_temp_data[user_id]['ombudsmen_data']
        msg = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите дату ответа на претензию (ДД.ММ.ГГГГ)"
            )
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, data_pret_otv, data, user_message_id)
    def data_pret_otv(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_pret_otv": message.text})
            data.update({"date_ombuc": str(get_next_business_date())})
            data.update({"status": "Составлено заявление к Фин.омбудсмену"})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
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
                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"7. Заявление фин. омбудсмену при выплате без согласования.docx")
            try:
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"7. Заявление фин. омбудсмену при выплате без согласования.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Заявление финансовому омбудсмену")
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")

            client_user_id = user_temp_data[user_id].get('client_user_id')
            if client_user_id:
                try:
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                    bot.send_message(
                        int(client_user_id),
                        "✅ Заявление к Фин.омбудсмену составлено, ознакомиться с ним можно в личном кабинете",
                        reply_markup = keyboard
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления клиенту: {e}")
            if user_id in user_temp_data:
                if 'ombudsmen_data' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['ombudsmen_data']
                if 'client_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_id']
                if 'client_user_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_user_id']
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ответа на претензию в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_pret_otv, data, user_message_id)

    
    
    # ========== ИСКОВОЕ ЗАЯВЛЕНИЕ ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_isk_"))
    def callback_create_isk(call):
        """Начало составления искового заявления"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_isk_", "")
        
        # Загружаем данные клиента
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
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['isk_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Удовлетворил", callback_data=f"Ombuc_udov"))
        keyboard.add(types.InlineKeyboardButton("Частично", callback_data=f"Ombuc_chast_udov"))
        keyboard.add(types.InlineKeyboardButton("Не удовлетворил", callback_data=f"Ombuc_No_udov"))
        bot.edit_message_text(call.message.chat.id, call.message.message_id, "Омбуцмен удовлетворил?",
        reply_markup = keyboard)

    @bot.callback_query_handler(func=lambda call: call.data =="Ombuc_udov")
    def callback_Ombuc_udov(call):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Ура", callback_data=f"Ura"))
        keyboard.add(types.InlineKeyboardButton("Деликт", callback_data=f"Delict"))
        bot.edit_message_text(call.message.chat.id, call.message.message_id, "Выберите из предложенных вариантов",
        reply_markup = keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["Ura", "Delict"])
    def callback_Ura_Delict(call):
        data = user_temp_data[call.from_user.id]['isk_data']
        if call.data == "Ura":
            data.update({"status": 'Завершен'})
        elif call.data == "Delict":
            data.update({"status": 'Деликт'})
        
        save_client_to_db_with_id(data)

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📄 Перейти к договору", callback_data=f"admin_view_contract_{data['client_id']}"))
        bot.edit_message_text(call.message.chat.id, call.message.message_id, "Вернуться к договору?",
        reply_markup = keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["Ombuc_No_udov", "Ombuc_chast_udov"])
    def callback_Ombuc_No_udov(call):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"Nezav_exp_Yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"Nezav_exp_No"))
        bot.edit_message_text(call.message.chat.id, call.message.message_id, "Заказать независимую экспертизу?",
        reply_markup = keyboard)
    @bot.callback_query_handler(func=lambda call: call.data in ["Nezav_exp_Yes", "Nezav_exp_No"])
    def callback_Ombuc_Nezav_exp_Yes(call):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Да", callback_data=f"Nezav_exp_Yes"))
        keyboard.add(types.InlineKeyboardButton("Нет", callback_data=f"Nezav_exp_No"))
        bot.edit_message_text(call.message.chat.id, call.message.message_id, "Заказать независимую экспертизу?",
        reply_markup = keyboard)
    
    
    def Nv_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({"Nv_ins": message.text})
        msg = bot.send_message(message.chat.id, text="Введите номер акта осмотра ТС")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, Na_ins, data, user_message_id)

    def Na_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"Na_ins": message.text})
        msg = bot.send_message(message.chat.id, text="Введите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)
    
    def date_Na_ins(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_Na_ins": message.text})
            if data["vibor"] == "vibor1":
                msg = bot.send_message(message.chat.id, text="Введите дату экспертного заключения (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_exp, data, user_message_id)
            elif data["vibor"] == "vibor2" or data["vibor"] == "vibor4":
                msg = bot.send_message(message.chat.id, text="Введите дату направления на СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, date_napr_sto, data, user_message_id)
        except ValueError:
            msg = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату акта осмотра ТС в формате ДД.ММ.ГГГГ")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, date_Na_ins, data, user_message_id)

    def date_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp": message.text})
            message = bot.send_message(message.chat.id, text="Введите организацию, сделавшую экспертизу".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, org_exp, data, user_message_id)

        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_exp, data, user_message_id, user_message_id)

    def org_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"org_exp": message.text})
        message = bot.send_message(message.chat.id, text="Введите цену по экспертизе без учета износа".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_exp, data, user_message_id)
    def coin_exp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_exp": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите цену по экспертизе с учетом износа"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_exp_izn, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену по экспертизе без учета износа"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_exp, data, user_message_id)
    def coin_exp_izn(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            if data.get("vibor",'') == "vibor2":
                data.update({"coin_exp_izn": message.text})
                data.update({"date_ombuc": str(get_next_business_date())})
                data.update({"status": "Составлено заявление к Фин.омбудсмену"})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
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
                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"8. Заявление фин. омбуцмену СТО отказала.docx")
                try:
                    with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"8. Заявление фин. омбуцмену СТО отказала.docx", 'rb') as doc:
                        bot.send_document(message.chat.id, doc, caption="📋 Заявление финансовому омбудсмену")
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")

                client_user_id = user_temp_data[user_id].get('client_user_id')
                if client_user_id:
                    try:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                        bot.send_message(
                            int(client_user_id),
                            "✅ Заявление к Фин.омбудсмену составлено, ознакомиться с ним можно в личном кабинете",
                            reply_markup = keyboard
                        )
                    except Exception as e:
                        print(f"Ошибка отправки уведомления клиенту: {e}")
                if user_id in user_temp_data:
                    if 'ombudsmen_data' in user_temp_data[user_id]:
                        del user_temp_data[user_id]['ombudsmen_data']
                    if 'client_id' in user_temp_data[user_id]:
                        del user_temp_data[user_id]['client_id']
                    if 'client_user_id' in user_temp_data[user_id]:
                        del user_temp_data[user_id]['client_user_id']
                from main_menu import show_main_menu_by_user_id
                show_main_menu_by_user_id(bot, user_id)
            elif data.get("vibor",'') == "vibor4":
                data.update({"coin_exp_izn": message.text})
                data.update({"date_ombuc": str(get_next_business_date())})
                data.update({"status": "Составлено заявление к Фин.омбудсмену"})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)
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
                            "clients\\"+str(data["client_id"])+"\\Документы\\"+"7. Заявление фин. омбудсмену СТО свыше 50 км.docx")
                try:
                    with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"7. Заявление фин. омбудсмену СТО свыше 50 км.docx", 'rb') as doc:
                        bot.send_document(message.chat.id, doc, caption="📋 Заявление финансовому омбудсмену")
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")

                client_user_id = user_temp_data[user_id].get('client_user_id')
                if client_user_id:
                    try:
                        keyboard = types.InlineKeyboardMarkup()
                        keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start"))
                        bot.send_message(
                            int(client_user_id),
                            "✅ Заявление к Фин.омбудсмену составлено, ознакомиться с ним можно в личном кабинете",
                            reply_markup = keyboard
                        )
                    except Exception as e:
                        print(f"Ошибка отправки уведомления клиенту: {e}")
                if user_id in user_temp_data:
                    if 'ombudsmen_data' in user_temp_data[user_id]:
                        del user_temp_data[user_id]['ombudsmen_data']
                    if 'client_id' in user_temp_data[user_id]:
                        del user_temp_data[user_id]['client_id']
                    if 'client_user_id' in user_temp_data[user_id]:
                        del user_temp_data[user_id]['client_user_id']
                from main_menu import show_main_menu_by_user_id
                show_main_menu_by_user_id(bot, user_id)
            else:
                data.update({"coin_exp_izn": message.text})
                message = bot.send_message(
                    message.chat.id,
                    text="Введите сумму выплаты по ОСАГО"
                )
                user_message_id = message.message_id
                bot.register_next_step_handler(message, coin_osago, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену по экспертизе с учетом износа"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_exp_izn, data, user_message_id)
    def coin_osago(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_osago": message.text})
            if data["vibor"] == "vibor1":
                data.update({"date_pret": str(get_next_business_date())})
                data.update({"status": 'Составлена претензия'})
                try:
                    client_id, updated_data = save_client_to_db_with_id(data)
                    data.update(updated_data)
                except Exception as e:
                    print(f"Ошибка базы данных: {e}")
                create_fio_data_file(data)

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
                                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Претензия в страховую Выплата без согласования.docx")
                try:
                    with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Претензия в страховую Выплата без согласования.docx", 'rb') as doc:
                        bot.send_document(message.chat.id, doc, caption="📋 Претензия")
                except FileNotFoundError:
                    bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
                keyboard = types.InlineKeyboardMarkup()
                btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
                keyboard.add(btn1)   
                bot.send_message(
                    int(data['user_id']),
                    "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                    reply_markup = keyboard
                    )

                from main_menu import show_main_menu_by_user_id
                show_main_menu_by_user_id(bot, user_id)
    
    def date_napr_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_napr_sto": message.text})
            if data["vibor"] == "vibor2":
                msg = bot.send_message(message.chat.id, text="Введите дату отказа СТО (ДД.ММ.ГГГГ)")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, data_otkaz_sto, data, user_message_id)
            elif data["vibor"] == "vibor4":
                msg = bot.send_message(message.chat.id, text="Введите название СТО")
                user_message_id = msg.message_id
                bot.register_next_step_handler(msg, name_sto, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату направления на СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_napr_sto, data, user_message_id)
    def data_otkaz_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_otkaz_sto": message.text})
            msg = bot.send_message(message.chat.id, text="Введите город СТО")
            user_message_id = msg.message_id
            bot.register_next_step_handler(msg, city_sto, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату отказа СТО в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_otkaz_sto, data, user_message_id, user_message_id)
    def city_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"city_sto": message.text})
        if data["vibor"] == "vibor2":
            data.update({"date_pret": str(get_next_business_date())})
            data.update({"status": 'Составлена претензия'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)

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
                                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx")
            try:
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"7. Претензия в страховую СТО отказала.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Претензия")
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
            keyboard.add(btn1)   
            bot.send_message(
                int(data['user_id']),
                "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
                reply_markup = keyboard
                )
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
        elif data["vibor"] == "vibor4":
            message = bot.send_message(message.chat.id, text="Введите номер направления на СТО".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, N_sto, data, user_message_id)

    def name_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"name_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите индекс СТО".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index_sto, data, user_message_id)
    def index_sto(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
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
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"address_sto": message.text})
        message = bot.send_message(message.chat.id, text="Введите город СТО".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, city_sto, data, user_message_id)
    def N_sto(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"N_sto": message.text})
        data.update({"date_pret": str(get_next_business_date())})
        data.update({"status": 'Составлена претензия'})
        try:
            client_id, updated_data = save_client_to_db_with_id(data)
            data.update(updated_data)
        except Exception as e:
            print(f"Ошибка базы данных: {e}")
        create_fio_data_file(data)
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
                                                "clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx")
        try:
            with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"6. Претензия в страховую  СТО свыше 50 км.docx", 'rb') as doc:
                bot.send_document(message.chat.id, doc, caption="📋 Претензия")
        except FileNotFoundError:
            bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
        keyboard.add(btn1)   
        bot.send_message(
            int(data['user_id']),
            "✅ Претензия составлена, ознакомиться с ней можно в личном кабинете.",
            reply_markup = keyboard
            )
        from main_menu import show_main_menu_by_user_id
        show_main_menu_by_user_id(bot, user_id)

    # ========== Деликт ==========
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_delict_"))
    def callback_delict(call):
        """Начало составления искового заявления"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_delict_", "")
        
        # Загружаем данные клиента
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
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['isk_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("1", callback_data="sud1_noosago")
        btn2 = types.InlineKeyboardButton("2", callback_data="sud2_noosago")
        btn3 = types.InlineKeyboardButton("3", callback_data="sud3_noosago")
        btn4 = types.InlineKeyboardButton("4", callback_data="sud4_noosago")
        btn5 = types.InlineKeyboardButton("5", callback_data="sud5_noosago")
        btn6 = types.InlineKeyboardButton("6", callback_data="sud6_noosago")
        btn7 = types.InlineKeyboardButton("Другое", callback_data="sudOther_noosago")
        keyboard.add(btn1, btn2, btn3)
        keyboard.add(btn4, btn5, btn6)
        keyboard.add(btn7)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="""
1. Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58
2. Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45
3. Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21
4. Томский областной суд, 634003, г. Томск, пер. Макушина, 8
5. Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6
6. Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8""",
        reply_markup = keyboard)
    
    @bot.callback_query_handler(func=lambda call: call.data in ["sud1_noosago", "sud2_noosago", "sud3_noosago", "sud4_noosago", "sud5_noosago", "sud6_noosago", "sudOther_noosago"])
    def callback_insurance(call):

        user_id = call.from_user.id
        data = user_temp_data[user_id]['isk_data']
         
        user_message_id = []  
        if call.data == "sud1_noosago":
            data.update({"sud": 'Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyD, data, user_message_id)
        elif call.data == "sud2_noosago":
            data.update({"sud": 'Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyD, data, user_message_id)
        elif call.data == "sud3_noosago":
            data.update({"sud": 'Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyD, data, user_message_id)
        elif call.data == "sud4_noosago":
            data.update({"sud": 'Томский областной суд, 634003, г. Томск, пер. Макушина, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyD, data, user_message_id)
        elif call.data == "sud5_noosago":
            data.update({"sud": 'Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyD, data, user_message_id)
        elif call.data == "sud6_noosago":
            data.update({"sud": 'Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyD, data, user_message_id)
        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название суда",
            reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, sud_otherD, data, user_message_id)

    def sud_otherD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"sud": message.text})
        message = bot.send_message(message.chat.id, text="Введите стоимость государственной пошлины".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, gos_moneyD, data, user_message_id)

    def gos_moneyD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"gos_money": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите стоимость нотариальных услуг"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_notD, data, user_message_id) 
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, стоимость должна состоять только из цифр в рублях, например: 50000!\nВведите стоимость государственной пошлины"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyD, data, user_message_id) 

    def coin_notD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_not": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите стоимость услуг по оценке ущерба"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, money_expD, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость нотариальных услуг"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_notD, data, user_message_id)

    def money_expD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"money_exp": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_expD, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость услуг по оценке ущерба"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, money_expD, data, user_message_id)
    
    def date_expD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp": message.text})
            message = bot.send_message(message.chat.id, text="Введите стоимость востановительного ремонта по экспертизе без учета износа".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_expD, data, user_message_id)

        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_expD, data, user_message_id)
    
    def coin_expD(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_exp": message.text})
            if data.get('docs', '') != '':
                message = bot.send_message(
                    message.chat.id, 
                    "Введите серию ВУ виновника ДТП"
                )
                user_message_id = message.message_id
                bot.register_next_step_handler(message, seria_vu_culpD, data, user_message_id)
            else:
                user_temp_data[user_id]['isk_data'] = data
                keyboard = types.InlineKeyboardMarkup()
                btn1 = types.InlineKeyboardButton("Свидетельство о регистрации ТС", callback_data="noosago_STS")
                btn2 = types.InlineKeyboardButton("Паспорт ТС", callback_data="noosago_PTS")
                keyboard.add(btn1)
                keyboard.add(btn2)

                bot.send_message(
                    message.chat.id, 
                    "Выберите документ о регистрации ТС клиента:", 
                    reply_markup=keyboard
                )
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость востановительного ремонта по экспертизе без учета износа"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_expD, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["noosago_STS", "noosago_PTS", "noosago_DKP"])
    def callback_client_docs(call):
        """Обработка выбора документа о регистрации ТС"""
        client_id = call.from_user.id
        data = user_temp_data[client_id]['isk_data']
        
        if call.data == "noosago_STS":
            data['docs'] = "СТС"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_docsD, data, user_message_id)

        elif call.data == "noosago_PTS":
            data['docs'] = "ПТС"
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите серию документа о регистрации ТС",
                reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_docsD, data, user_message_id)
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
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_docsD, data, user_message_id)

    def seria_docsD(message, data, user_message_id):
        """Обработка серии документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        data['seria_docs'] = message.text.strip()
        msg = bot.send_message(message.chat.id, "Введите номер документа о регистрации ТС:")
        bot.register_next_step_handler(msg, number_docsD, data, msg.message_id)
    
    
    def number_docsD(message, data, user_message_id):
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
            bot.register_next_step_handler(msg, data_docsD, data, msg.message_id)
        else:
            msg = bot.send_message(
                message.chat.id,
                "❌ Неправильный формат!\nВведите номер документа о регистрации ТС (только цифры):"
            )
            bot.register_next_step_handler(msg, number_docsD, data, msg.message_id)
    
    
    def data_docsD(message, data, user_message_id):
        """Обработка даты выдачи документа"""
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data['data_docs'] = message.text.strip()
            
            msg = bot.send_message(
                message.chat.id, 
                "Введите серию ВУ виновника ДТП"
                )
            bot.register_next_step_handler(msg, seria_vu_culpD, data, msg.message_id)
        except ValueError:
            msg = bot.send_message(
                message.chat.id, 
                "❌ Неправильный формат ввода!\nВведите дату выдачи документа о регистрации ТС в формате ДД.ММ.ГГГГ:"
            )
            bot.register_next_step_handler(msg, data_docsD, data, msg.message_id)

    def seria_vu_culpD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({"seria_vu_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер ВУ виновника ДТП".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_vu_culpD, data, user_message_id)
    def number_vu_culpD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"number_vu_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату ВУ виновника ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_vu_culpD, data, user_message_id)
    def data_vu_culpD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_vu_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите дату рождения виновника ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_culpD, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ВУ виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_vu_culpD, data, user_message_id)

    def date_of_birth_culpD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_of_birth_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите почтовый индекс виновника ДТП, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_culpD, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_culpD, data, user_message_id)
    def index_culpD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите почтовый индекс виновника, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_culpD, data, user_message_id)
        else:
            data.update({"index_culp": int(message.text.replace(" ", ""))})
            message = bot.send_message(message.chat.id, text="Введите адрес проживания виновника ДТП".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_culpD, data, user_message_id)  
    def address_culpD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"address_culp": message.text})
        message =bot.send_message(message.chat.id, text="Введите номер телефона виновника ДТП в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_culpD, data, user_message_id)
    def number_culpD(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона виновника ДТП в формате +79XXXXXXXXX".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_culpD, data, user_message_id)
        else:
            data.update({"number_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите дату извещения ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_izvesh_dtpD, data, user_message_id)
    def date_izvesh_dtpD(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_izvesh_dtp": message.text})
            data.update({"date_isk": str(get_next_business_date())})
            data.update({"status": 'Составлено исковое заявление'})
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            print(data)
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
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт (без ОСАГО) 4.  Исковое заявление.docx")
            try:
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт (без ОСАГО) 4.  Исковое заявление.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Исковое заявление")
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
            keyboard.add(btn1)   
            bot.send_message(
                int(data['user_id']),
                "✅ Исковое заявление составлено. Ознакомиться с ним можно в личном кабинете.",
                reply_markup = keyboard
                )
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
            if user_id in user_temp_data:
                if 'isk_data' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['isk_data']
                if 'client_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_id']
                if 'client_user_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_user_id']   
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату извещения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_izvesh_dtpD, data, user_message_id)


# ========== Деликт Выплата ==========
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_delictViplat_"))
    def callback_create_delictViplat(call):
        """Начало составления искового заявления"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_delictViplat_", "")
        
        # Загружаем данные клиента
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
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        user_temp_data[user_id]['isk_data'] = data
        user_temp_data[user_id]['client_id'] = client_id
        user_temp_data[user_id]['client_user_id'] = data.get('user_id')

        keyboard = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("1", callback_data="sud1_viplata")
        btn2 = types.InlineKeyboardButton("2", callback_data="sud2_viplata")
        btn3 = types.InlineKeyboardButton("3", callback_data="sud3_viplata")
        btn4 = types.InlineKeyboardButton("4", callback_data="sud4_viplata")
        btn5 = types.InlineKeyboardButton("5", callback_data="sud5_viplata")
        btn6 = types.InlineKeyboardButton("6", callback_data="sud6_viplata")
        btn7 = types.InlineKeyboardButton("Другое", callback_data="sudOther_viplata")
        keyboard.add(btn1, btn2, btn3)
        keyboard.add(btn4, btn5, btn6)
        keyboard.add(btn7)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="""
1. Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58
2. Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45
3. Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21
4. Томский областной суд, 634003, г. Томск, пер. Макушина, 8
5. Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6
6. Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8""",
        reply_markup = keyboard)
    
    @bot.callback_query_handler(func=lambda call: call.data in ["sud1_viplata", "sud2_viplata", "sud3_viplata", "sud4_viplata", "sud5_viplata", "sud6_viplata", "sudOther_viplata"])
    def callback_insurance(call):

        user_id = call.from_user.id
        data = user_temp_data[user_id]['isk_data']
         
        user_message_id = []  
        if call.data == "sud1_viplata":
            data.update({"sud": 'Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id)
        elif call.data == "sud2_viplata":
            data.update({"sud": 'Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id)
        elif call.data == "sud3_viplata":
            data.update({"sud": 'Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id)
        elif call.data == "sud4_viplata":
            data.update({"sud": 'Томский областной суд, 634003, г. Томск, пер. Макушина, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id)
        elif call.data == "sud5_viplata":
            data.update({"sud": 'Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id)
        elif call.data == "sud6_viplata":
            data.update({"sud": 'Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id)
        else: 
            message = bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Введите название суда",
            reply_markup=None
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, sud_otherDV, data, user_message_id)

    def sud_otherDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"sud": message.text})
        message = bot.send_message(message.chat.id, text="Введите стоимость государственной пошлины".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id)

    def gos_moneyDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"gos_money": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите стоимость нотариальных услуг"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_notDV, data, user_message_id) 
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, стоимость должна состоять только из цифр в рублях, например: 50000!\nВведите стоимость государственной пошлины"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyDV, data, user_message_id) 

    def coin_notDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_not": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите стоимость услуг по оценке ущерба"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, money_expDV, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость нотариальных услуг"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_notDV, data, user_message_id)

    def money_expDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"money_exp": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите дату экспертного заключения в формате ДД.ММ.ГГГГ"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_expDV, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость услуг по оценке ущерба"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, money_expDV, data, user_message_id)
    
    def date_expDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp": message.text})
            message = bot.send_message(message.chat.id, text="Введите стоимость востановительного ремонта по экспертизе без учета износа".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_expDV, data, user_message_id)

        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату экспертного заключения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_expDV, data, user_message_id)
    
    def coin_expDV(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_exp": message.text})
            
            message = bot.send_message(
                message.chat.id, 
                "Введите сумму выплаты по ОСАГО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_OSAGODV, data, user_message_id)
            
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость востановительного ремонта по экспертизе без учета износа"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_expDV, data, user_message_id)

    def coin_OSAGODV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_osago": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите номер выплатного дела"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, N_viplat_workDV, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите сумму выплаты по ОСАГО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_OSAGODV, data, user_message_id)

    def N_viplat_workDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"N_viplat_work": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату выплатного дела в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_viplat_workDV, data, user_message_id)
    def date_viplat_workDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_viplat_work": message.text})
            message = bot.send_message(message.chat.id, text="Введите номер платежного поручения".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, N_plat_porDV, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выплатного дела в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_viplat_workDV, data, user_message_id)
    def N_plat_porDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"N_plat_por": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату платежного поручения в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_plat_porDV, data, user_message_id)
    def date_plat_porDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:   
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_plat_por": message.text})
            message = bot.send_message(message.chat.id, text="Введите серию ВУ виновника ДТП".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_vu_culpDV, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату платежного поручения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_plat_porDV, data, user_message_id)
    def seria_vu_culpDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        data.update({"seria_vu_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер ВУ виновника ДТП".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_vu_culpDV, data, user_message_id)
    def number_vu_culpDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"number_vu_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату ВУ виновника ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_vu_culpDV, data, user_message_id)
    def data_vu_culpDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_vu_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите дату рождения виновника ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_culpDV, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ВУ виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_vu_culpDV, data, user_message_id)

    def date_of_birth_culpDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_of_birth_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите почтовый индекс виновника ДТП, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_culpDV, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения виновника в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_culpDV, data, user_message_id)
    def index_culpDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите почтовый индекс виновника, например, 123456".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_culpDV, data, user_message_id)
        else:
            data.update({"index_culp": int(message.text.replace(" ", ""))})
            message = bot.send_message(message.chat.id, text="Введите адрес проживания виновника ДТП".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_culpDV, data, user_message_id)  
    def address_culpDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"address_culp": message.text})
        message =bot.send_message(message.chat.id, text="Введите номер телефона виновника ДТП в формате +79XXXXXXXXX".format(message.from_user))
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_culpDV, data, user_message_id)
    def number_culpDV(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона виновника ДТП в формате +79XXXXXXXXX".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_culpDV, data, user_message_id)
        else:
            data.update({"number_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите дату извещения ДТП в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_izvesh_dtpDV, data, user_message_id)
    def date_izvesh_dtpDV(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_izvesh_dtp": message.text})
            data.update({"date_isk": str(get_next_business_date())})
            data.update({"status": 'Составлено исковое заявление'})
            fio_parts = data['fio_culp'].split()
            if len(fio_parts) == 2:
                fio_culp_k = f"{fio_parts[0]} {fio_parts[1][0]}."
            else:
                fio_culp_k= f"{fio_parts[0]} {fio_parts[1][0]}.{fio_parts[2][0]}."
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            print(data)
            replace_words_in_word(["{{ Суд }}","{{ ФИО }}","{{ ДР }}", "{{ Паспорт_серия }}", "{{ Паспорт_номер }}","{{ Паспорт_выдан }}", "{{ Паспорт_когда }}",
                                "{{ Индекс }}", "{{ Адрес }}", "{{ Телефон }}","{{ Представитель }}","{{ NДоверенности }}","{{ Дата_доверенности }}", 
                                "{{ винФИО }}", "{{ ДР_Виновника }}","{{ Серия_ВУвин }}", "{{ Номер_ВУвин }}", "{{ Дата_ВУвин }}","{{ Индекс_Виновника }}","{{ Адрес_Виновника }}",
                                "{{ Телефон_Виновника }}",
                                "{{ Страховая }}","{{ Разница }}","{{ Цена_пошлины }}",
                                "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}", "{{ Марка_модель }}","{{ Nавто_клиента }}", "{{ Марка_модель_виновника }}",
                                "{{ Nавто_виновник }}", "{{ винФИОкор }}", "{{ Экспертиза }}", "{{ Выплата_ОСАГО }}","{{ Nвыплатного_дела }}","{{ Дата_выплатного_дела }}",
                                "{{ Nплатежного_поручения }}","{{ Дата_поручения }}", "{{ Год }}", "{{ NКлиента }}","{{ Дата }}", "{{ Стоимость_экспертизы }}", "{{ Дата_экспертизы }}",
                                "{{ Документ }}", "{{ Док_серия }}","{{ Док_номер }}","{{ Дата_извещения }}","{{ Дата_искового_заявления }}"],
                                [str(data["sud"]), str(data["fio"]), str(data["date_of_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]),str(data["when_pasport"]), str(data["index_postal"]),
                                    str(data["address"]), str(data["number"]), str(data["fio_not"]), str(data["N_dov_not"]),str(data["data_dov_not"]), 
                                    str(data["fio_culp"]),str(data["date_of_birth_culp"]), str(data["seria_vu_culp"]),
                                    str(data["number_vu_culp"]), str(data["data_vu_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(data["number_culp"]), 
                                    str(data["insurance"]), str(float(data["coin_exp"])-float(data['coin_osago'])), 
                                    str(data["gos_money"]), str(data["date_dtp"]),str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]),
                                    str(data["marks_culp"]),str(data["number_auto_culp"]), str(fio_culp_k), str(data["coin_exp"]), str(data["coin_osago"]),str(data["N_viplat_work"]),
                                    str(data["date_viplat_work"]), str(data["N_plat_por"]), str(data["date_plat_por"]), str(data["year"]), str(data["client_id"]), str(data["pret"]),
                                    str(data["money_exp"]), str(data["date_exp"]), str(data["docs"]), str(data["seria_docs"]), str(data["number_docs"]),str(data["date_izvesh_dtp"]),
                                    str(data["date_isk"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\4. Деликт\\Деликт 5.  Исковое заявление.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 5.  Исковое заявление.docx") 
            try:
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Деликт 5.  Исковое заявление.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Исковое заявление")
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
            keyboard.add(btn1)   
            bot.send_message(
                int(data['user_id']),
                "✅ Исковое заявление составлено. Ознакомиться с ним можно в личном кабинете.",
                reply_markup = keyboard
                )
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
            if user_id in user_temp_data:
                if 'isk_data' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['isk_data']
                if 'client_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_id']
                if 'client_user_id' in user_temp_data[user_id]:
                    del user_temp_data[user_id]['client_user_id']   
        except ValueError as e:
            print(e)
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату извещения в формате ДД.ММ.ГГГГ".format(message.from_user))
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_izvesh_dtpDV, data, user_message_id)

    # ========== Цессия ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_cecciaDogovor_"))
    def callback_create_cecciaDogovor(call):
        """Начало составления договора Цессии"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_cecciaDogovor_", "")
        
        # Загружаем данные клиента
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
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        msg = bot.edit_message_text(chat_id = user_id, message_id = call.message.message_id,text = "Введите ФИО цессионария в формате Иванов Иван Иванович", reply_markup = None)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, FIO_c, data, user_message_id)

    def FIO_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.split())<2:
                message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите ФИО Цессионария в формате Иванов Иван Иванович")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, FIO_c, data, user_message_id)
        else:
            words = message.text.split()
            for word in words:
                if not word[0].isupper():  # Проверяем, что первая буква заглавная
                    message = bot.send_message(message.chat.id, text="Каждое слово должно начинаться с заглавной буквы!\nВведите ФИО Цессионария в формате Иванов Иван Иванович")
                    user_message_id = message.message_id
                    bot.register_next_step_handler(message, FIO_c, data, user_message_id)
                    return
            data.update({"fio_c": message.text})
            if len(message.text.split())==2:
                data.update({"fio_c_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."})
            else:
                data.update({"fio_c_k": message.text.split()[0]+" "+list(message.text.split()[1])[0]+"."+list(message.text.split()[2])[0]+"."})
            message = bot.send_message(message.chat.id, text="Введите серию паспорта Цессионария, например, 1234")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_pasport_c, data, user_message_id)

    def seria_pasport_c(message, data, user_message_id):
            try:
                bot.delete_message(message.chat.id, user_message_id)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            if len(message.text.replace(" ", "")) != 4 or not message.text.replace(" ", "").isdigit():
                message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 4 цифры!\nВведите серию паспорта Цессионария, например, 1234.")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, seria_pasport_c, data, user_message_id)
            else:
                data.update({"seria_pasport_c": int(message.text.replace(" ", ""))})
                message = bot.send_message(message.chat.id, text="Введите номер паспорта Цессионария, например, 123456")
                user_message_id = message.message_id
                bot.register_next_step_handler(message, number_pasport_c, data, user_message_id)

    def number_pasport_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите номер паспорта Цессионария, например, 123456")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_pasport_c, data, user_message_id)
        else:
            data.update({"number_pasport_c": int(message.text.replace(" ", ""))})
            message = bot.send_message(message.chat.id, text="Кем выдан паспорт Цессионария?")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, where_pasport_c, data, user_message_id)

    def where_pasport_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"where_pasport_c": message.text})
        message = bot.send_message(message.chat.id, text="Когда выдан паспорт Цессионария? Введите в формате ДД.ММ.ГГГГ")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, when_pasport_c, data, user_message_id)

    def when_pasport_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"when_pasport_c": message.text})
            message = bot.send_message(message.chat.id, text="Введите адрес проживания Цессионария")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_c, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выдачи паспорта Цессионария в формате ДД.ММ.ГГГГ.")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, when_pasport_c, data, user_message_id)

    def address_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"address_c": message.text})
        message = bot.send_message(message.chat.id, text="Введите почтовый индекс Цессионария")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, index_c, data, user_message_id)
    def index_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите почтовый индекс Цессионария, например, 123456")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_c, data, user_message_id)
        else:
            data.update({"index_postal_c": int(message.text.replace(" ", ""))})
            message = bot.send_message(message.chat.id, text="Дату рождения Цессионария в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_с, data, user_message_id)   
    def date_of_birth_с(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_of_birth_с": message.text})
            message = bot.send_message(message.chat.id, text="Введите город рождения Цессионария")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, city_birth_c, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения Цессионария в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_с, data, user_message_id)
    def city_birth_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"city_birth_c": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер телефона Цессионария в формате +79XXXXXXXXX")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_c, data, user_message_id)

    def number_c(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона Цессионария в формате +79XXXXXXXXX")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_c, data, user_message_id)
        else:
            data.update({"number_c": message.text})
            message = bot.send_message(message.chat.id, text="Введите серию ВУ виновника ДТП")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, seria_vu_culp, data, user_message_id)

    def seria_vu_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"seria_vu_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите номер ВУ виновника")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_vu_culp, data, user_message_id)

    def number_vu_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"number_vu_culp": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату ВУ виновника в формате ДД.ММ.ГГГГ")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, data_vu_culp, data, user_message_id)
    def data_vu_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"data_vu_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите дату рождения виновника в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_culp, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату ВУ виновника в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, data_vu_culp, data, user_message_id)
    def date_of_birth_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_of_birth_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите почтовый индекс виновника, например, 123456")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_culp, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату рождения виновника в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_of_birth_culp, data, user_message_id)
    def index_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text.replace(" ", "")) != 6 or not message.text.replace(" ", "").isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода, должно быть 6 цифр!\nВведите почтовый индекс виновника, например, 123456")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, index_culp, data, user_message_id)
        else:
            data.update({"index_culp": int(message.text.replace(" ", ""))})
            message = bot.send_message(message.chat.id, text="Введите адрес виновника")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, address_culp, data, user_message_id)  
    def address_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"address_culp": message.text})
        message =bot.send_message(message.chat.id, text="Введите номер телефона виновника ДТП в формате +79XXXXXXXXX")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, number_culp, data, user_message_id)
    def number_culp(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if len(message.text) != 12 or not message.text.startswith('+79') or not message.text[3:].isdigit():
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите номер телефона виновника ДТП в формате +79XXXXXXXXX")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, number_culp, data, user_message_id)
        else:
            data.update({"number_culp": message.text})
            message = bot.send_message(message.chat.id, text="Введите дату независимой экспертизы в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_expC, data, user_message_id)

    def date_expC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_exp": message.text})
            message = bot.send_message(message.chat.id, text="Введите организацию, сделавшую экспетризу")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, org_expC, data, user_message_id)

        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату независимой экспертизы в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_expC, data, user_message_id)
    def org_expC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"org_exp": message.text})
        message = bot.send_message(message.chat.id, text="Введите цену по независимой экспертизе без учета износа")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, coin_expC, data, user_message_id)
    def coin_expC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_exp": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите стоимость экспертизы"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, money_expC, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену по независимой экспертизе без учета износа"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_expC, data, user_message_id)

    def money_expC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"money_exp": message.text})
            message = bot.send_message(
                message.chat.id,
                text="Введите сумму выплаты по ОСАГО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_osagoC, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите стоимость экспертизы"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, money_expC, data, user_message_id)
    def coin_osagoC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_osago": message.text})
            
            message = bot.send_message(
            message.chat.id,
            text="Введите стоимость услуг нотариуса"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_notC, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите сумму выплаты по ОСАГО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_osagoC, data, user_message_id)
    def coin_notC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"coin_not": message.text})

            message = bot.send_message(
            message.chat.id,
            text="Введите цену Цессии"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_c, data, user_message_id)
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите сумму выплаты по ОСАГО"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_notC, data, user_message_id)
    def coin_c(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"pret": str(get_next_business_date())})
            data.update({"status": 'Составлен договор Цессии'})
            if len(data['fio_culp'].split())==2:
                fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."
            else:
                fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."+list(data['fio_culp'].split()[2])[0]+"."
            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            print(data)
            replace_words_in_word(["{{ Год }}", "{{ NКлиента }}", "{{ Дата }}", 
                                "{{ Город }}", "{{ ЦФИО }}","{{ ЦДР }}", "{{ ЦМесто }}",
                                "{{ ЦПаспорт_серия }}", "{{ ЦПаспорт_номер }}", "{{ ЦПаспорт_выдан }}","{{ ЦПаспорт_когда }}","{{ ЦИндекс }}",
                                "{{ ЦАдрес }}", "{{ ФИО }}","{{ ДР }}", "{{ Место }}",
                                "{{ Паспорт_серия }}", "{{ Паспорт_номер }}", "{{ Паспорт_выдан }}","{{ Паспорт_когда }}","{{ Индекс }}",
                                "{{ Адрес }}", "{{ Дата_ДТП }}","{{ Время_ДТП }}", "{{ Адрес_ДТП }}"],
                                [str(data["year"]), str(data["client_id"]), str(data["pret"]), str(data["city"]),
                                    str(data["fio_c"]), str(data["date_of_birth_c"]), str(data["city_birth_c"]), str(data["seria_pasport_c"]),
                                    str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                    str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                    str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 5. Соглашение о замене стороны Цессия.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 5. Соглашение о замене стороны Цессия.docx")
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
                                    str(data["fio_c"]), str(data["date_of_birth_c"]),str(data["city_birth_c"]), str(data["seria_pasport_c"]),
                                    str(data["number_pasport_c"]), str(data["where_pasport_c"]), str(data["when_pasport_c"]), str(data["index_postal_c"]),str(data["address_c"]), 
                                    str(data["fio"]), str(data["date_of_birth"]),str(data["city_birth"]), str(data["seria_pasport"]),
                                    str(data["number_pasport"]), str(data["where_pasport"]), str(data["when_pasport"]), str(data["index_postal"]),str(data["address"]), 
                                    str(data["fio_culp"]), str(data["date_of_birth_culp"]), str(data["index_culp"]), str(data["address_culp"]),str(float(data["coin_exp"])-float(data['coin_osago'])), 
                                    str(data["date_dtp"]), str(data["time_dtp"]), str(data["address_dtp"]), str(data["marks"]), str(data["car_number"]), str(data["marks_culp"]),
                                    str(data["number_auto_culp"]), str(fio_culp_k), str(data["coin_exp"]), str(data["coin_osago"]),str(data["money_exp"]),
                                    str(data["date_exp"]), str(data["date_pret"]), str(data["coin_c"]), str(data["number"]), str(data["fio_k"]), str(data["number_c"]),str(data["fio_c_k"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 6. Договор цессии.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 6. Договор цессии.docx")
            replace_words_in_word(["{{ винФИО }}", "{{ Дата_ДТП }}", "{{ Время_ДТП }}", 
                                "{{ Разница }}", "{{ ФИО }}","{{ Год }}", "{{ NКлиента }}",
                                "{{ Дата }}", "{{ ЦФИО }}"],
                                [str(data["fio_culp"]), str(data["date_dtp"]), str(data["time_dtp"]), str(float(data["coin_exp"])-float(data['coin_osago'])),
                                    str(data["fio"]), str(data["year"]),str(data["client_id"]), str(data["pret"]),
                                    str(data["fio_c"])],
                                    "Шаблоны\\1. ДТП\\2. На выплату\\3. Цессия\\Цессия 7. Предложение о досудебном урегулировании спора.docx",
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 7. Предложение о досудебном урегулировании спора.docx")
            try:
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 5. Соглашение о замене стороны Цессия.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Соглашение о замене стороны Цессия")
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 6. Договор цессии.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Договор цессии")
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 7. Предложение о досудебном урегулировании спора.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Предложение о досудебном урегулировании спора")
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
            keyboard.add(btn1)   
            bot.send_message(
                int(data['user_id']),
                "✅ Составлен договор Цессии. Ознакомиться с ним можно в личном кабинете.",
                reply_markup = keyboard
                )
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
            if user_id in user_temp_data:
                del user_temp_data[user_id]
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, цена должна состоять только из цифр в рублях!\nВведите цену цессии"
            )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, coin_c, data, user_message_id)

    # ========== Цессия Иск ==========
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("create_cecciaIsk_"))
    def callback_create_cecciaIsk(call):
        """Начало составления договора Цессии"""
        user_id = call.from_user.id
        client_id = call.data.replace("create_cecciaIsk_", "")
        
        # Загружаем данные клиента
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
        
        # Сохраняем данные в user_temp_data
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        
        msg = bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = "Введите номер выплатного дела", reply_markup = None)
        user_message_id = msg.message_id
        bot.register_next_step_handler(msg, N_viplat_workС, data, user_message_id)

    def N_viplat_workС(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"N_viplat_work": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату выплатного дела в формате ДД.ММ.ГГГГ")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_viplat_workC, data, user_message_id)
    def date_viplat_workC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_viplat_work": message.text})
            message = bot.send_message(message.chat.id, text="Введите номер платежного поручения")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, N_plat_porC, data, user_message_id)
        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату выплатного дела в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_viplat_workC, data, user_message_id)
    def N_plat_porC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"N_plat_por": message.text})
        message = bot.send_message(message.chat.id, text="Введите дату платежного поручения в формате ДД.ММ.ГГГГ")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, date_plat_porC, data, user_message_id)
    def date_plat_porC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:   
            datetime.strptime(message.text, "%d.%m.%Y")
            data.update({"date_plat_por": message.text})

            user_id = message.from_user.id
            user_temp_data[user_id] = data
            
            keyboard = types.InlineKeyboardMarkup()

            btn1 = types.InlineKeyboardButton("1", callback_data="sud1_ceccia")
            btn2 = types.InlineKeyboardButton("2", callback_data="sud2_ceccia")
            btn3 = types.InlineKeyboardButton("3", callback_data="sud3_ceccia")
            btn4 = types.InlineKeyboardButton("4", callback_data="sud4_ceccia")
            btn5 = types.InlineKeyboardButton("5", callback_data="sud5_ceccia")
            btn6 = types.InlineKeyboardButton("6", callback_data="sud6_ceccia")
            btn7 = types.InlineKeyboardButton("Другое", callback_data="sudOther_ceccia")
            keyboard.add(btn1, btn2, btn3)
            keyboard.add(btn4, btn5, btn6)
            keyboard.add(btn7)

            bot.send_message(message.chat.id, text="""
    1. Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58
    2. Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45
    3. Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21
    4. Томский областной суд, 634003, г. Томск, пер. Макушина, 8
    5. Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6
    6. Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8""", reply_markup=keyboard)


        except ValueError:
            message = bot.send_message(message.chat.id, text="Неправильный формат ввода!\nВведите дату платежного поручения в формате ДД.ММ.ГГГГ")
            user_message_id = message.message_id
            bot.register_next_step_handler(message, date_plat_porC, data, user_message_id)

    @bot.callback_query_handler(func=lambda call: call.data in ["sud1_ceccia", "sud2_ceccia", "sud3_ceccia", "sud4_ceccia", "sud5_ceccia", "sud6_ceccia", "sudOther_ceccia"])
    def callback_insurance(call):

        user_id = call.from_user.id
        
        data = user_temp_data[user_id]
         
        user_message_id = []  
        if call.data == "sud1_ceccia":
            data.update({"sud": 'Кировский районный суд г. Томска,  634050, г. Томск, ул. Дзержинского, д.58'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)
        elif call.data == "sud2_ceccia":
            data.update({"sud": 'Советский районный суд г. Томска, 634050, г. Томск, ул. Карташова, д. 45'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)
        elif call.data == "sud3_ceccia":
            data.update({"sud": 'Октябрьский районный суд г. Томска, 634050, г. Томск, пр. Ленина, д. 21'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)
        elif call.data == "sud4_ceccia":
            data.update({"sud": 'Томский областной суд, 634003, г. Томск, пер. Макушина, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)
        elif call.data == "sud5_ceccia":
            data.update({"sud": 'Ленинский районный суд г. Томска, 634050, г. Томск, пер. Батенькова, 6'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            ) 
            user_message_id = message.message_id
            bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)
        elif call.data == "sud6_ceccia":
            data.update({"sud": 'Томский Районный Суд Томской Области, 634050, г. Томск, ул. Обруб, 8'})
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите стоимость государственной пошлины",
                reply_markup=None
            )
            user_message_id = message.message_id 
            bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)
        else: 
            message = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="Введите название суда",
                reply_markup=None
                )
            user_message_id = message.message_id
            bot.register_next_step_handler(message, sud_otherC, data, user_message_id)
    def sud_otherC(message, data, user_message_id):
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        data.update({"sud": message.text})
        message = bot.send_message(message.chat.id, text="Введите стоимость государственной пошлины")
        user_message_id = message.message_id
        bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)
    def gos_moneyC(message, data, user_message_id):
        user_id = message.from_user.id
        try:
            bot.delete_message(message.chat.id, user_message_id)
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if message.text.isdigit():  # Проверяем, что текст состоит только из цифр
            data.update({"gos_money": message.text})
            data.update({"date_isk": str((datetime.now()).strftime("%d.%m.%Y"))})
            data.update({"status": 'Отправлено исковое заявление'})
            if len(data['fio_culp'].split())==2:
                fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."
            else:
                fio_culp_k = data['fio_culp'].split()[0]+" "+list(data['fio_culp'].split()[1])[0]+"."+list(data['fio_culp'].split()[2])[0]+"."

            try:
                client_id, updated_data = save_client_to_db_with_id(data)
                data.update(updated_data)
            except Exception as e:
                print(f"Ошибка базы данных: {e}")
            create_fio_data_file(data)
            print(data)
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
                                    "clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 8. Исковое заявление Цессия.docx")

            try:
                with open(f"clients\\"+str(data["client_id"])+"\\Документы\\"+"Цессия 8. Исковое заявление Цессия.docx", 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📋 Исковое заявление Цессия")
            except FileNotFoundError:
                bot.send_message(message.chat.id, "❌ Ошибка: файл не найден")
            keyboard = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("🏠 Главное меню", callback_data="callback_start")
            keyboard.add(btn1)   
            bot.send_message(
                int(data['user_id']),
                "✅ Составлен договор Цессии. Ознакомиться с ним можно в личном кабинете.",
                reply_markup = keyboard
                )
            from main_menu import show_main_menu_by_user_id
            show_main_menu_by_user_id(bot, user_id)
            if user_id in user_temp_data:
                del user_temp_data[user_id]
        else:
            message = bot.send_message(
                message.chat.id,
                text="Неправильный формат, стоимость должна состоять только из цифр в рублях, например: 5000!\nВведите стоимость государственной пошлины"
            )
            user_message_id = message.message_id

            bot.register_next_step_handler(message, gos_moneyC, data, user_message_id)

