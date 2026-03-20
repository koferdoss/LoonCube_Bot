import telebot
from telebot import types
import os

# ========================================
# НАСТРОЙКИ БОТА — ИЗМЕНИТЕ ЭТИ ЗНАЧЕНИЯ
# ========================================

# Токен бота от @BotFather
TOKEN = '8429625508:AAGti63T98hE4vnOwRB6oCr-8DntH8pYHaM'  # ← Вставьте сюда новый токен (старый мог утечь!)

# ID чата куда приходят заявки и жалобы (ваш личный ID или ID группы)
STAFF_CHAT_ID = -1003783529047

# ID чата куда приходят запросы в тех. поддержку
SUPPORT_CHAT_ID = -1003783529047

# Список ID администраторов (могут использовать /reply и др. команды)
ADMIN_IDS = [-1003783529047, 1006488779]

STAFF_THREAD_ID = 85      # топик для заявок/жалоб (из вашей ссылки)
SUPPORT_THREAD_ID = 85    # если техподдержка идёт в тот же топик, или укажите другой

# Информация о сервере (отображается в разделе "Помощь")
SERVER_IP = 'looncube.fun'          # ← Замените на IP вашего сервера
SERVER_VERSION = '1.16.5-1.20.1'            # ← Замените на версию сервера
SERVER_DISCORD = 'discord.gg/looncube'  # ← Замените на ссылку Discord
ADMIN_USERNAME = '@koferdo'     # ← Замените на username админа

# ========================================

bot = telebot.TeleBot(TOKEN)

# Хранение состояний пользователей
user_states = {}

# Все тексты кнопок главного меню — для фильтрации в handle_requests
MENU_BUTTONS = {
    '🛠 Тех.поддержка',
    '❓ Помощь',
    '🔙 Назад',
    '👨‍💼 Админ-панель',
}


# ========================================
# СТАТИСТИКА
# ========================================

USERS_FILE = 'users.txt'                # файл со списком ID пользователей
APPS_COUNT_FILE = 'applications_count.txt'  # файл со счётчиком заявок

all_users = set()        # множество ID всех пользователей бота
total_applications = 0   # общее количество поданных заявок

def load_users():
    """Загружает список пользователей из файла."""
    global all_users
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and line.isdigit():
                    all_users.add(int(line))

def save_user(user_id):
    """Добавляет нового пользователя в файл (если его там ещё нет)."""
    if user_id not in all_users:
        all_users.add(user_id)
        with open(USERS_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{user_id}\n")

def load_app_count():
    """Загружает общее количество заявок из файла."""
    global total_applications
    if os.path.exists(APPS_COUNT_FILE):
        with open(APPS_COUNT_FILE, 'r', encoding='utf-8') as f:
            data = f.read().strip()
            if data.isdigit():
                total_applications = int(data)

def save_app_count():
    """Сохраняет общее количество заявок в файл."""
    with open(APPS_COUNT_FILE, 'w', encoding='utf-8') as f:
        f.write(str(total_applications))

def increment_app_count():
    """Увеличивает счётчик заявок на 1 и сохраняет."""
    global total_applications
    total_applications += 1
    save_app_count()

# Загружаем данные при старте
load_users()
load_app_count()


# ─── ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: главное меню ───────────────────────────────────

def show_main_menu(message):
    """Показывает главное меню пользователю."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('🛠 Тех.поддержка'),
               types.KeyboardButton('❓ Помощь'))

    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в бот LoonCube!\n\n"
        "Выберите опцию ниже:",
        reply_markup=markup
    )


# ─── /start ───────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.chat.id

    # Проверка на бан
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ Вы забанены в боте и не можете пользоваться его функциями.")
        return

    # Регистрируем пользователя
    save_user(user_id)

    if user_id in ADMIN_IDS:
        # Создаем специальную клавиатуру для администратора
        admin_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        admin_markup.add(types.KeyboardButton('🛠 Тех.поддержка'),
                        types.KeyboardButton('❓ Помощь'))
        admin_markup.add(types.KeyboardButton('👨‍💼 Админ-панель'))

        admin_text = (
            "👨‍💼 *АДМИН ПАНЕЛЬ*\n\n"
            "📝 `/reply <user_id> <текст>`\n"
            "Ответить конкретному пользователю\n\n"
            "🔨 `/ban <user_id> [причина]`\n"
            "Заблокировать пользователя\n\n"
            "⏳ `/tempban <user_id> <длительность> [причина]`\n"
            "Временный бан (пример: 30m, 2h, 5d)\n\n"
            "🔓 `/unban <user_id>`\n"
            "Разблокировать пользователя\n\n"
            "📢 `/broadcast <текст>`\n"
            "Массовая рассылка (в разработке)\n\n"
            "ℹ️ `/help`\n"
            "Показать эту справку\n\n"
            "💡 *Совет:* ID пользователя есть в каждом пересланном запросе!"
        )
        bot.send_message(user_id, admin_text, parse_mode='Markdown', reply_markup=admin_markup)
        return

    show_main_menu(message)

# ========================================
# СИСТЕМА БАНОВ (с поддержкой временных)
# ========================================

import time
import re

BAN_LIST_FILE = 'banned_users.txt'
# Структура: {user_id: expiry_timestamp} где expiry_timestamp = None (постоянный) или число (время окончания)
banned_users = {}

def parse_duration(duration_str):
    """
    Преобразует строку длительности (например, '1h', '30m', '2d') в секунды.
    Поддерживает: s (секунды), m (минуты), h (часы), d (дни), w (недели).
    Возвращает количество секунд или None, если формат неверен.
    """
    match = re.match(r'^(\d+)([smhdw]?)$', duration_str.lower())
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    elif unit == 'w':
        return value * 604800
    else:  # без единицы — считаем часами (для обратной совместимости, можно настроить)
        return value * 3600

def load_banned_users():
    """Загружает список забаненных пользователей из файла."""
    global banned_users
    banned_users.clear()
    if os.path.exists(BAN_LIST_FILE):
        with open(BAN_LIST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|')
                if len(parts) == 2:
                    user_id, expiry = parts
                    try:
                        user_id = int(user_id)
                        if expiry == 'permanent':
                            banned_users[user_id] = None
                        else:
                            banned_users[user_id] = float(expiry)
                    except:
                        pass

def save_banned_users():
    """Сохраняет список забаненных пользователей в файл."""
    with open(BAN_LIST_FILE, 'w', encoding='utf-8') as f:
        for uid, expiry in banned_users.items():
            if expiry is None:
                f.write(f"{uid}|permanent\n")
            else:
                f.write(f"{uid}|{expiry}\n")

# Загружаем бан-лист при старте
load_banned_users()

def is_banned(user_id):
    """
    Проверяет, забанен ли пользователь.
    Если бан истёк — автоматически удаляет из списка.
    """
    if user_id not in banned_users:
        return False
    expiry = banned_users[user_id]
    if expiry is None:
        return True  # постоянный бан
    if time.time() < expiry:
        return True  # временный бан ещё действует
    else:
        # бан истёк — удаляем
        del banned_users[user_id]
        save_banned_users()
        return False

# ─── КОМАНДЫ АДМИНИСТРАТОРА ───────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == '👨‍💼 Админ-панель')
def admin_panel(message):
    if message.chat.id not in ADMIN_IDS:
        return

    stats_text = (
        f"📊 *СТАТИСТИКА БОТА*\n\n"
        f"👥 Всего пользователей: `{len(all_users)}`\n"
        f"📩 Всего заявок: `{total_applications}`\n"
        f"🔨 Активных банов: `{len(banned_users)}`\n\n"
    )

    admin_text = (
        "👨‍💼 *АДМИН КОМАНДЫ*\n\n"
        "📝 `/reply <user_id> <текст>`\n"
        "Ответить конкретному пользователю\n\n"
        "🔨 `/ban <user_id> [причина]`\n"
        "Заблокировать пользователя\n\n"
        "⏳ `/tempban <user_id> <длительность> [причина]`\n"
        "Временный бан (пример: 30m, 2h, 5d)\n\n"
        "🔓 `/unban <user_id>`\n"
        "Разблокировать пользователя\n\n"
        "📢 `/broadcast <текст>`\n"
        "Массовая рассылка (в разработке)\n\n"
        "ℹ️ `/help`\n"
        "Показать эту справку\n\n"
        "💡 *Совет:* ID пользователя есть в каждом пересланном запросе!"
    )

    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')
    bot.send_message(message.chat.id, admin_text, parse_mode='Markdown')

@bot.message_handler(commands=['reply'])
def reply_to_user(message):
    if message.chat.id not in ADMIN_IDS:
        return

    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.send_message(
                message.chat.id,
                "❌ Формат: `/reply <user_id> <сообщение>`",
                parse_mode='Markdown'
            )
            return

        user_id = int(parts[1])
        reply_text = parts[2]

        bot.send_message(
            user_id,
            f"📨 *Ответ от администрации:*\n\n{reply_text}",
            parse_mode='Markdown'
        )
        bot.send_message(
            message.chat.id,
            f"✅ Сообщение успешно отправлено пользователю {user_id}"
        )

    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный ID пользователя. Убедитесь, что ID — это число."
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при отправке: {e}")


@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.chat.id not in ADMIN_IDS:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "❌ Формат: `/broadcast <сообщение>`",
            parse_mode='Markdown'
        )
        return

    bot.send_message(
        message.chat.id,
        "⚠️ Функция массовой рассылки требует базы данных пользователей.\n"
        "Используйте `/reply <user_id> <текст>` для ответа конкретному пользователю.",
        parse_mode='Markdown'
    )


@bot.message_handler(commands=['ban'])
def ban_user(message):
    """Постоянный бан пользователя по ID."""
    if message.chat.id not in ADMIN_IDS:
        return

    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            bot.send_message(
                message.chat.id,
                "❌ Формат: `/ban <user_id> [причина]`",
                parse_mode='Markdown'
            )
            return

        user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "Не указана"

        if user_id in ADMIN_IDS:
            bot.send_message(message.chat.id, "❌ Нельзя забанить администратора!")
            return

        if is_banned(user_id):
            bot.send_message(message.chat.id, f"⚠️ Пользователь {user_id} уже забанен.")
            return

        banned_users[user_id] = None  # постоянный бан
        save_banned_users()

        user_states.pop(user_id, None)

        bot.send_message(
            message.chat.id,
            f"✅ Пользователь {user_id} забанен (постоянно).\nПричина: {reason}"
        )

        try:
            bot.send_message(
                user_id,
                f"⛔ Вы забанены в боте (постоянно).\nПричина: {reason}\n\nЕсли считаете это ошибкой, свяжитесь с администрацией."
            )
        except:
            pass

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный ID пользователя. Убедитесь, что ID — это число.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")


@bot.message_handler(commands=['unban'])
def unban_user(message):
    """Разблокирует пользователя по ID."""
    if message.chat.id not in ADMIN_IDS:
        return

    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.send_message(
                message.chat.id,
                "❌ Формат: `/unban <user_id>`",
                parse_mode='Markdown'
            )
            return

        user_id = int(parts[1])

        if not is_banned(user_id):  # is_banned автоматически удалит истекшие, но если пользователя нет в словаре — вернёт False
            # Проверим напрямую в словаре, может он есть но истекший? Но is_banned уже удалил бы.
            if user_id not in banned_users:
                bot.send_message(message.chat.id, f"⚠️ Пользователь {user_id} не в бане.")
            else:
                # Если is_banned вернул False, значит бан истек и уже удалён. Сообщим.
                bot.send_message(message.chat.id, f"⚠️ Пользователь {user_id} не в бане (возможно, срок истёк).")
            return

        del banned_users[user_id]
        save_banned_users()

        bot.send_message(message.chat.id, f"✅ Пользователь {user_id} разбанен.")

        try:
            bot.send_message(
                user_id,
                "✅ Вы были разблокированы в боте. Теперь вы снова можете пользоваться функциями."
            )
        except:
            pass

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный ID пользователя. Убедитесь, что ID — это число.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")


@bot.message_handler(commands=['help'])
def help_admin(message):
    if message.chat.id not in ADMIN_IDS:
        return
    admin_text = (
    "👨‍💼 *АДМИН КОМАНДЫ*\n\n"
    "📝 `/reply <user_id> <текст>`\n"
    "Ответить конкретному пользователю\n\n"
    "🔨 `/ban <user_id> [причина]`\n"
    "Заблокировать пользователя\n\n"
    "⏳ `/tempban <user_id> <длительность> [причина]`\n"
    "Временный бан (пример: 30m, 2h, 5d)\n\n"
    "🔓 `/unban <user_id>`\n"
    "Разблокировать пользователя\n\n"
    "📢 `/broadcast <текст>`\n"
    "Массовая рассылка (в разработке)\n\n"
    "ℹ️ `/help`\n"
    "Показать эту справку\n\n"
    "💡 *Совет:* ID пользователя есть в каждом пересланном запросе!"
)

    bot.send_message(message.chat.id, admin_text, parse_mode='Markdown')

@bot.message_handler(commands=['tempban'])
def tempban_user(message):
    """Временный бан пользователя по ID."""
    if message.chat.id not in ADMIN_IDS:
        return

    try:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 3:
            bot.send_message(
                message.chat.id,
                "❌ Формат: `/tempban <user_id> <длительность> [причина]`\n"
                "Длительность: число с единицей (s, m, h, d, w), например: 30m, 2h, 5d",
                parse_mode='Markdown'
            )
            return

        user_id = int(parts[1])
        duration_str = parts[2]
        reason = parts[3] if len(parts) > 3 else "Не указана"

        if user_id in ADMIN_IDS:
            bot.send_message(message.chat.id, "❌ Нельзя забанить администратора!")
            return

        # Проверяем, не забанен ли уже
        if is_banned(user_id):
            bot.send_message(message.chat.id, f"⚠️ Пользователь {user_id} уже забанен.")
            return

        # Парсим длительность
        seconds = parse_duration(duration_str)
        if seconds is None:
            bot.send_message(
                message.chat.id,
                "❌ Неверный формат длительности. Используйте: 30m, 2h, 5d, 1w и т.п."
            )
            return

        expiry = time.time() + seconds
        banned_users[user_id] = expiry
        save_banned_users()

        # Очищаем состояние пользователя
        user_states.pop(user_id, None)

        # Форматируем человекочитаемое время окончания
        expiry_readable = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry))

        bot.send_message(
            message.chat.id,
            f"✅ Пользователь {user_id} забанен до {expiry_readable}.\nПричина: {reason}"
        )

        # Уведомляем пользователя
        try:
            bot.send_message(
                user_id,
                f"⛔ Вы забанены в боте до {expiry_readable}.\nПричина: {reason}\n\nЕсли считаете это ошибкой, свяжитесь с администрацией."
            )
        except:
            pass

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный ID пользователя. Убедитесь, что ID — это число.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")



# ─── АНКЕТЫ ───────────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == '📋 Команда проекта')
def project_team_request(message):
    if is_banned(message.chat.id):
        bot.send_message(message.chat.id, "⛔ Вы забанены в боте.")
        return    
    user_states[message.chat.id] = 'awaiting_project_application'
    application_text = (
        "📋 *АНКЕТА ДЛЯ КОМАНДЫ ПРОЕКТА*\n\n"
        "Советуем ознакомиться с требованиями!\n\n"
        "✅ Свободное владение русским языком.\n"
        "✅ Умение эффективно взаимодействовать с сообществом игроков.\n"
        "✅ Базовые знания команд помощника.\n"
        "✅ Возраст от 14 лет (возможны исключения).\n"
        "✅ Отсутствие жалоб и нарушений на игровом аккаунте.\n"
        "✅ Готовность серьёзно относиться к выполнению обязанностей.\n"
        "✅ Понимание основных команд сервера.\n\n"
        "📌 *Формат подачи заявок строго регламентирован:*\n\n"
        "1️⃣ Игровой никнейм.\n"
        "2️⃣ Текущая игровая привилегия.\n"
        "3️⃣ Полных лет.\n"
        "4️⃣ Длительность знакомства с нашим проектом.\n"
        "5️⃣ Сколько времени в сутки вы готовы уделять проекту?\n"
        "6️⃣ Перечислите предыдущие игровые проекты, где вы приобрели опыт модерирования.\n"
        "7️⃣ Кратко опишите себя минимум в 40 словах.\n"
        "⭐ Оценка уровня владения правилами сервера по пятибалльной шкале. (1/5)\n\n"
        "🔍 Все заявки внимательно изучаются командой ежедневно. Отбор проходят только самые достойные кандидаты.\n\n"
        "🛑 Запрещено писать личное сообщение администраторам относительно статуса заявки. Несоблюдение приведёт к автоматическому отказу.\n\n"
        "➡️ Теперь отправьте вашу заявку в соответствии с форматом выше:"
    )
    bot.send_message(message.chat.id, application_text, parse_mode='Markdown')


@bot.message_handler(func=lambda m: m.text == '🎥 YT / Медиа')
def youtube_application(message):
    if is_banned(message.chat.id):
        bot.send_message(message.chat.id, "⛔ Вы забанены в боте.")
        return    
    user_states[message.chat.id] = 'awaiting_youtube_application'
    youtube_text = (
        "🎥 *АНКЕТА ДЛЯ YOUTUBE*\n\n"
        "✅ *Критерии для категории MEDIA:*\n\n"
        "👉 Минимум 50 подписчиков на твоём YouTube-канале. Исключения возможны.\n"
        "👉 От 50 просмотров за каждые полные сутки.\n"
        "👉 Тематика роликов должна соответствовать игре MINECRAFT.\n"
        "👉 Нет проблем с каналом со стороны администрации.\n"
        "👉 Наличие хотя бы одного видеоролика, записанного на нашем сервере.\n\n"
        "✅ *Критерии для категории MEDIA+:*\n\n"
        "👉 Минимум 250 подписчиков на твоём YouTube-канале. Возможны исключения.\n"
        "👉 Ежедневно должно быть не менее 150 просмотров.\n"
        "👉 Обязательная тематика роликов — игра MINECRAFT.\n"
        "👉 Канал должен быть чист перед администрацией.\n"
        "👉 Обязательно наличие видео, отснятых на нашем проекте.\n\n"
        "Если вы подходите по критериям, можете уверенно писать заявку!\n\n"
        "📋 *Форма заявки:*\n\n"
        "🎯 Игровой никнейм:\n"
        "🧑‍🤝‍🧑 Желаемый уровень: YT / YT+\n"
        "🌐 Ссылка на ваш YouTube-канал:\n"
        "📹 Ссылка на примеры ваших работ:\n\n"
        "❗ *ВАЖНО:* Если ты перестанешь выкладывать контент четыре дня подряд, права участника будут отозваны.\n\n"
        "➡️ Теперь отправьте вашу заявку:"
    )
    bot.send_message(message.chat.id, youtube_text, parse_mode='Markdown')


@bot.message_handler(func=lambda m: m.text == '📱 TT / TT+')
def tiktok_application(message):
    if is_banned(message.chat.id):
        bot.send_message(message.chat.id, "⛔ Вы забанены в боте.")
        return    
    user_states[message.chat.id] = 'awaiting_tiktok_application'
    tiktok_text = (
        "📱 *АНКЕТА ДЛЯ TIKTOK*\n\n"
        "🌟 *КРИТЕРИИ ДЛЯ УЧАСТИЯ:*\n\n"
        "🎬 *Категория TIKTOK:*\n\n"
        "📍 Адекватность поведения, ответственность и умение общаться.\n"
        "📍 Каждый ролик должен получать минимум 150 просмотров.\n"
        "📍 Количество подписчиков — от 80+.\n"
        "📍 Наличие ролика, снятого на нашем сервере.\n\n"
        "🌟 *Категория TIKTOK PLUS+:*\n\n"
        "📍 Такие же требования по адекватности и качеству общения.\n"
        "📍 Ролики обязаны собирать не меньше 550 просмотров.\n"
        "📍 Подписчиков должно быть не менее 300+.\n"
        "📍 Необходим хотя бы один качественный ролик, сделанный на нашем сервере.\n\n"
        "📋 *ФОРМА ЗАЯВКИ:*\n\n"
        "🖼️ Игровой никнейм:\n"
        "📊 Желаемый уровень: TT / TT+\n"
        "🏷️ Ссылка на ваш аккаунт TikTok:\n"
        "📱 Ссылка на видео с нашим сервером:\n"
        "🔗 Профиль в TikTok (IP в описании):\n\n"
        "📌 *Важно:* запрет на спамирование сообщений администраторам. Нарушение приведёт к автоматической отмене заявки.\n\n"
        "➡️ Теперь отправьте вашу заявку:"
    )
    bot.send_message(message.chat.id, tiktok_text, parse_mode='Markdown')


# ─── ЖАЛОБЫ ───────────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == '⚠️ Жалоба')
def complaint_handler(message):
    if is_banned(message.chat.id):
        bot.send_message(message.chat.id, "⛔ Вы забанены в боте.")
        return    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('👤 Жалоба на игрока'))
    markup.add(types.KeyboardButton('👮 Жалоба на персонал'))
    markup.add(types.KeyboardButton('🔙 Назад'))

    bot.send_message(
        message.chat.id,
        "⚠️ *ПОДАЧА ЖАЛОБЫ*\n\nВыберите тип жалобы:",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.message_handler(func=lambda m: m.text == '👤 Жалоба на игрока')
def player_complaint(message):
    if is_banned(message.chat.id):
        bot.send_message(message.chat.id, "⛔ Вы забанены в боте.")
        return    
    user_states[message.chat.id] = 'awaiting_player_complaint'
    complaint_text = (
        "👤 *ЖАЛОБА НА ИГРОКА*\n\n"
        "Жалоба должна заполняться СТРОГО по форме ниже.\n\n"
        "📋 *ФОРМА:*\n\n"
        "🔹 Ваш никнейм на сервере\n"
        "🔹 Никнейм нарушителя\n"
        "🔹 Пункт правил, по которому было нарушение\n"
        "🔹 Описание нарушения\n"
        "🔹 Доказательства (Видео/скриншот)\n\n"
        "⚠️ Принимаются доказательства, загруженные в ВК, YouTube, Imgur.\n"
        "❌ Доказательства со сторонних ресурсов не рассматриваются!\n\n"
        "➡️ Теперь отправьте вашу жалобу:"
    )
    bot.send_message(message.chat.id, complaint_text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '👮 Жалоба на персонал')
def staff_complaint(message):
    if is_banned(message.chat.id):
        bot.send_message(message.chat.id, "⛔ Вы забанены в боте.")
        return
    user_states[message.chat.id] = 'awaiting_staff_complaint'
    complaint_text = (
        "👮 *ЖАЛОБА НА ПЕРСОНАЛ*\n\n"
        "▪ *Форма подачи жалобы:*\n\n"
        "🔹 Ваш никнейм.\n"
        "🔹 Никнейм нарушителя с должностью (Хелпер, ст.Хелпер, Модератор, ст.Модератор).\n"
        "🔹 Суть нарушения.\n"
        "🔹 Пункт правил, который нарушили.\n"
        "🔹 Доказательства нарушения.\n\n"
        "⚠️ Заявка подаётся строго по форме выше.\n"
        "⚠️ Если после момента нарушения прошло более 3-х дней, жалоба будет отклонена.\n\n"
        "➡️ Теперь отправьте вашу жалобу:"
    )
    bot.send_message(message.chat.id, complaint_text, parse_mode='Markdown')


# ─── ТЕХ. ПОДДЕРЖКА И ПОМОЩЬ ─────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == '🛠 Тех.поддержка')
def tech_support_request(message):
    user_states[message.chat.id] = 'awaiting_support_request'
    bot.send_message(
        message.chat.id,
        "🛠 *Техническая поддержка*\n\n"
        "Пожалуйста, опишите вашу проблему.\n"
        "Укажите:\n"
        "• Ваш игровой никнейм\n"
        "• Что именно произошло\n"
        "• Когда это произошло",
        parse_mode='Markdown'
    )


@bot.message_handler(func=lambda m: m.text == '❓ Помощь')
def help_command(message):
    help_text = (
        "🎮 *Помощь по боту Minecraft сервера*\n\n"
        "🛠 *Техническая поддержка* — сообщить о баге или проблеме\n\n"
        "❓ *Помощь* — показать это сообщение\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "*Информация о сервере:*\n"
        f"• IP: `{SERVER_IP}`\n"
        f"• Версия: {SERVER_VERSION}\n"
        f"• Discord: {SERVER_DISCORD}\n\n"
        f"Нужна дополнительная помощь? Свяжитесь с {ADMIN_USERNAME}"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '🔙 Назад')
def back_to_menu(message):
    user_states.pop(message.chat.id, None)
    show_main_menu(message)


# ─── ОБРАБОТКА ВХОДЯЩИХ ЗАЯВОК/ЖАЛОБ ─────────────────────────────────────────

@bot.message_handler(content_types=['text', 'photo', 'video', 'document'])
def handle_requests(message):
    user_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name

    if message.content_type == 'text' and message.text in MENU_BUTTONS:
        return

    if is_banned(user_id):
        bot.send_message(user_id, "⛔ Вы забанены в боте. Ваши сообщения не обрабатываются.")
        return

    state = user_states[user_id]

    state_labels = {
        'awaiting_project_application': '📋 Команда проекта',
        'awaiting_youtube_application': '🎥 YT / Медиа',
        'awaiting_tiktok_application':  '📱 TT / TT+',
        'awaiting_player_complaint':    '👤 Жалоба на игрока',
        'awaiting_staff_complaint':     '👮 Жалоба на персонал',
        'awaiting_support_request':     '🛠 Тех.поддержка',
    }

    is_support = (state == 'awaiting_support_request')
    target_chat = SUPPORT_CHAT_ID if is_support else STAFF_CHAT_ID
    thread_id = SUPPORT_THREAD_ID if is_support else STAFF_THREAD_ID   # <-- добавили

    request_header = (
        f"📩 *Новый запрос*\n"
        f"От: @{username} (ID: `{user_id}`)\n"
        f"Тип: {state_labels.get(state, 'Неизвестно')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Для ответа:\n"
        f"`/reply {user_id} Ваш ответ здесь`\n\n"
    )

    try:
        if message.content_type == 'text':
            bot.send_message(target_chat, request_header + message.text,
                             parse_mode='Markdown', message_thread_id=thread_id)   # <-- добавили thread_id
        elif message.content_type == 'photo':
            bot.send_photo(target_chat, message.photo[-1].file_id,
                           caption=request_header + (message.caption or ''),
                           parse_mode='Markdown', message_thread_id=thread_id)
        elif message.content_type == 'video':
            bot.send_video(target_chat, message.video.file_id,
                           caption=request_header + (message.caption or ''),
                           parse_mode='Markdown', message_thread_id=thread_id)
        elif message.content_type == 'document':
            bot.send_document(target_chat, message.document.file_id,
                              caption=request_header + (message.caption or ''),
                              parse_mode='Markdown', message_thread_id=thread_id)

        confirm = (
            "✅ Ваш запрос в поддержку отправлен! Наша команда скоро ответит."
            if is_support else
            "✅ Ваша заявка/жалоба отправлена! Ожидайте ответа."
        )
        bot.send_message(user_id, confirm)
        increment_app_count()

    except Exception as e:
        bot.send_message(user_id, f"❌ Ошибка при отправке: {e}\n\nПожалуйста, свяжитесь с администратором.")
    finally:
        user_states.pop(user_id, None)


# ─── ЗАПУСК ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("🤖 Бот успешно запущен! Нажмите Ctrl+C для остановки.")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)