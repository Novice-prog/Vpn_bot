import get_api_token
import yookassa_link
import database

import logging
import json
import asyncio
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta, timezone

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=get_api_token.TOKEN)
dp = Dispatcher(bot)

# Класс для работы с Marzban API
class MarzbanBackend:

    def __init__(self, token: str = None):
        self.base_url = get_api_token.Marzban_url
        self.headers = {"accept": "application/json"}
        self.session = aiohttp.ClientSession()
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        else:
            asyncio.create_task(self.authorize())

    async def _get(self, path: str) -> dict:
        url = f"{self.base_url}/{path}"
        async with self.session.get(url, headers=self.headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                logging.error(f"GET request failed with status {response.status}: {url}")
                return {}

    async def _post(self, path: str, data=None) -> dict:
        url = f"{self.base_url}/{path}"
        async with self.session.post(url, headers=self.headers, json=data) as response:
            if response.status in {200, 201}:
                return await response.json()
            else:
                logging.error(f"POST request failed with status {response.status}: {url}")
                return {}

    async def _put(self, path: str, data=None) -> dict:
        url = f"{self.base_url}/{path}"
        async with self.session.put(url, headers=self.headers, json=data) as response:
            if response.status == 200:
                logging.info(f"cmd xray PUT {path}, data: {data}")
                return await response.json()
            else:
                logging.error(f"cmd xray PUT failed with status {response.status} for {path}")
                return {}

    async def authorize(self) -> None:
        data = {
            "username": get_api_token.Auth_name,
            "password": get_api_token.Auth_password
        }

        token = get_api_token.Marzban_Api_Token
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        else:
            logging.error("Authorization failed, no token received")

    async def create_user(self, name: str) -> dict:
        data = {
            "username": name,
            "proxies": {"shadowsocks": {"method": "chacha20-ietf-poly1305"}},
            "inbounds": {"shadowsocks": ["Shadowsocks TCP"]},
            "data_limit": 15 * 1024 * 1024 * 1024,
            "data_limit_reset_strategy": "day",
        }
        response = await self._post("api/user", data=data)
        if not response:
            logging.error(f"Failed to create user {name}")
            return {}
        return response

    async def get_user(self, name: str) -> dict:
        response = await self._get(f"api/user/{name}")
        if response:
            user = response.get("username")
            status = response.get("status")
            logging.info(f"Get user: {user}, status: {status}")
        else:
            logging.warning(f"User {name} not found")
        return response

    async def disable_user(self, name: str) -> dict:
        data = {"status": "disabled"}
        response = await self._put(f"api/user/{name}", data=data)
        if response:
            logging.info(f"Disable xray user: {name} success, {response.get('username', 'unknown username')}")
            check = await self.get_user(name)
            await asyncio.sleep(0.25)  # Используйте асинхронный sleep
            if check.get("status") != data.get("status"):
                logging.error(f"After disabling user {name}, user is not disabled!")
            return response
        else:
            logging.warning(f"xray user {name} not found")
            return {}

    async def enable_user(self, name: str) -> dict:
        data = {"status": "active"}
        response = await self._put(f"api/user/{name}", data=data)
        if response:
            logging.info(f"Enable xray user: {name} success, {response.get('username', 'unknown username')}")
            return response
        else:
            logging.warning(f"xray user {name} not found")
            return {}

    async def close(self):
        await self.session.close()

# Инициализация Marzban API клиента с токеном
marzban = MarzbanBackend(token=get_api_token.Marzban_Api_Token)

# Функция для работы с БД при старте
async def on_startup(_):
    await database.db_start()
    asyncio.create_task(check_expired_subscriptions())  # Запускаем проверку истекших подписок ежедневно
    print("Бот успешно запущен!")

# Фоновая задача для ежедневной проверки истекших подписок
async def check_expired_subscriptions():
    while True:
        async with aiosqlite.connect('tg.db') as db:
            cursor = await db.execute('''
                SELECT user_id, end_date FROM accounts
            ''')

            async for row in cursor:
                user_id, end_date = row

                # Проверяем наличие и корректность end_date
                if not end_date:
                    logging.warning(f"Пустая дата для user_id {user_id}")
                    continue

                try:
                    end_date = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
                except ValueError as e:
                    logging.error(f"Некорректный формат даты для user_id {user_id}: {end_date}. Ошибка: {e}")
                    continue

                # Если подписка истекла, отключаем доступ
                if datetime.now(timezone.utc) > end_date:
                    await marzban.disable_user(f"user_{user_id}")
                    # Удаляем запись из базы данных или обновляем статус
                    await db.execute('''
                        UPDATE accounts
                        SET access_key = NULL, end_date = NULL
                        WHERE user_id = ?
                    ''', (user_id,))
                    await db.commit()
                    logging.info(f"Доступ для пользователя {user_id} отключен, подписка истекла.")

        # Ждем 24 часа до следующей проверки
        await asyncio.sleep(86400)  # 86400 секунд = 24 часа


# Стартовая команда
@dp.message_handler(commands=['start'])
async def menu_vpn(message: types.Message):
    user_id = message.from_user.id
    inline_kb = ReplyKeyboardMarkup(resize_keyboard=True)
    buy_button = KeyboardButton("Купить VPN")
    status_button = KeyboardButton("Мои подписки")
    info_button = KeyboardButton("Инфо")
    inline_kb.add(buy_button, status_button, info_button)
    await message.answer("Выберите действие:", reply_markup=inline_kb)

    # Подключаемся к базе данных и добавляем пользователя
    async with aiosqlite.connect('tg.db') as db:
        # Проверяем, существует ли пользователь в базе данных
        cursor = await db.execute('SELECT user_id FROM accounts WHERE user_id = ?', (user_id,))
        result = await cursor.fetchone()

        if result is None:
            # Если пользователя нет, добавляем его
            await db.execute('''
                INSERT INTO accounts (user_id)
                VALUES (?)
            ''', (user_id,))
            await db.commit()


@dp.message_handler(lambda message: message.text == "Инфо")
async def info_message(callback_query: types.CallbackQuery):
    info_text = (
        "*Как пользоваться ботом?* \n"
        "1. Запустите бота в Telegram, отправив команду /start \n"
        "2. Выберите *Купить VPN* в меню \n"
        "3. Выберите период подписки (1 месяц, 3 месяца, 6 месяцев) из предложенных вариантов.\n"
        "4. Бот отправит ссылку на оплату — нажмите на кнопку *Оплатить*\n"
        "5. После оплаты нужно проверить статус платежа, нажав на кнопку Проверить оплату \n"
        "6. По завершении оплаты бот предоставит вам *ключ доступа* к VPN \n \n \n"
        "*Как воспользоваться ключом?*, \n"
        "1. Установите приложение Outline на ваше устройство.\n"
        "2. Откройте приложение и нажмите на кнопку *Добавить сервер*.\n"
        "3. Введите или вставьте ваш ключ доступа в соответствующее поле.\n"
        "4. Сохраните настройки и подключитесь к серверу.\n\n"
    )

    await bot.send_message(
        chat_id=callback_query.from_user.id,
        text=info_text,
        parse_mode = 'Markdown'
    )
    await bot.send_message(
        chat_id=callback_query.from_user.id,
        text="В случае проблем пишите сюда: @JustSL",
    )

# Проверка статуса подписки
@dp.message_handler(lambda message: message.text == "Мои подписки")
async def show_subscription_info(message: types.Message):
    user_id = message.from_user.id


    # Подключаемся к базе данных и извлекаем информацию о подписке
    async with aiosqlite.connect('tg.db') as db:
        cursor = await db.execute('''
            SELECT end_date FROM accounts WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()

    if result and result[0]:
        # Если у пользователя есть активная подписка

        end_date = datetime.fromisoformat(result[0]).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        remaining_time = end_date - now
        remaining_days = remaining_time.days

        if remaining_time.total_seconds() > 0:
            # Если подписка еще активна, извлекаем ключ
            async with aiosqlite.connect('tg.db') as db:
                cursor = await db.execute('''
                    SELECT access_key FROM accounts WHERE user_id = ?
                ''', (user_id,))
                key_result = await cursor.fetchone()

            if key_result:
                access_key = key_result[0]

                # Отправляем пользователю информацию о действующей подписке
                await message.answer(
                    f"Ваша подписка активна до {end_date.strftime('%Y-%m-%d')}.\n\n"
                    f"Ваш ключ доступа:\n\n"
                    f"<code>{access_key}</code>", parse_mode='HTML'
                )
            else:
                await message.answer("Ошибка: ключ доступа не найден.")
        else:
            # Если подписка истекла
            await message.answer("Ваша подписка истекла.")
    else:
        # Если подписка не найдена
        await message.answer("У вас нет активной подписки.")

# кнопка Назад
@dp.callback_query_handler(lambda c: c.data == 'back_to_duration_selection')
async def back_to_duration_selection(callback_query: types.CallbackQuery):
    # Возвращаем пользователя к выбору сроков подписки
    inline_kb = InlineKeyboardMarkup(row_width=1)

    # VPN на 1 месяц
    pay_button_1m = InlineKeyboardButton("VPN на 1 месяц - 100 руб", callback_data='1month')

    # VPN на 3 месяца
    pay_button_3m = InlineKeyboardButton("VPN на 3 месяца - 250 руб", callback_data='3month')

    # VPN на 6 месяцев
    pay_button_6m = InlineKeyboardButton("VPN на 6 месяцев - 450 руб", callback_data='6month')

    # Добавляем кнопки в разметку
    inline_kb.add(pay_button_1m, pay_button_3m, pay_button_6m)

    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text="Выберите срок подписки и перейдите по ссылке для оплаты:",
        reply_markup=inline_kb
    )

# Кнопка покупки VPN
@dp.message_handler(lambda message: message.text == "Купить VPN")
async def process_buy_vpn(message: types.Message):
    user_id = message.from_user.id

    inline_kb = InlineKeyboardMarkup(row_width=1)

    # VPN на 1 месяц
    pay_button_1m = InlineKeyboardButton("VPN на 1 месяц - 100 руб",callback_data='1month' )

    # VPN на 3 месяца
    pay_button_3m = InlineKeyboardButton("VPN на 3 месяца - 250 руб", callback_data='3month')

    # VPN на 6 месяцев
    pay_button_6m = InlineKeyboardButton("VPN на 6 месяцев - 450 руб", callback_data='6month')

    # Добавляем кнопки в разметку
    inline_kb.add(pay_button_1m, pay_button_3m, pay_button_6m)

    await message.answer('Выберите срок подписки и перейдите по ссылке для оплаты:', reply_markup=inline_kb)

# Обработчик для выбранного периода подписки
@dp.callback_query_handler(lambda c: c.data in ['1month', '3month', '6month'])
async def handle_subscription_choice(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    # Определяем срок подписки и цену
    if callback_query.data == '1month':
        duration = '1 месяц'
        price = 100
    elif callback_query.data == '3month':
        duration = '3 месяца'
        price = 250
    elif callback_query.data == '6month':
        duration = '6 месяцев'
        price = 450

    # Генерация ссылки на оплату
    payment_url = await yookassa_link.create_payment(user_id, callback_query.data)

    # Инлайн-клавиатура для оплаты и проверки оплаты
    inline_kb = InlineKeyboardMarkup(row_width=1)
    pay_button = InlineKeyboardButton(f"Оплатить {duration} - {price} руб", url=payment_url)
    check_payment_button = InlineKeyboardButton(f"Проверить оплату за {duration}", callback_data=f'check_payment_{duration}')
    back_button = InlineKeyboardButton("Назад", callback_data='back_to_duration_selection')

    # Добавляем кнопки в разметку
    inline_kb.add(pay_button, check_payment_button, back_button)

    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text=f"Оплата за VPN на {duration}. После оплаты нажмите Проверить оплату! :",
        reply_markup=inline_kb
    )


# Обработка оплаты
@dp.pre_checkout_query_handler()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# Проверка статуса оплаты
@dp.callback_query_handler(lambda c: c.data.startswith("check_payment_"))
async def check_payment_status_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    # Извлекаем срок подписки из callback_data (например, "1month", "3 месяца", "6 месяцев")
    duration = callback_query.data.split('_')[-1]

    # Определяем количество дней для подписки (поддержка как английских, так и русских вариантов)
    days = 0
    if duration in ["1month", "1 месяц"]:
        days = 30
    elif duration in ["3month", "3 месяца"]:
        days = 90
    elif duration in ["6month", "6 месяцев"]:
        days = 180
    else:
        logging.error(f"Unexpected duration value: {duration}")

    # Проверяем статус платежа
    payment_success = await yookassa_link.check_payment_status(user_id)

    if payment_success and days > 0:
        now = datetime.utcnow()

        # Получаем текущую дату окончания подписки и ключ доступа из базы данных
        async with aiosqlite.connect('tg.db') as db:
            cursor = await db.execute('''
                SELECT end_date, access_key FROM accounts WHERE user_id = ?
            ''', (user_id,))
            result = await cursor.fetchone()

        end_date = None
        access_key = None

        if result:
            end_date_str = result[0]
            access_key = result[1]

            # Проверяем, является ли дата окончания подписки строкой и преобразуем её
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str).replace(tzinfo=timezone.utc)
                except ValueError:
                    logging.error(f"Некорректный формат даты в базе данных для пользователя {user_id}: {end_date_str}")
                    end_date = now  # Если формат некорректен, начинаем отсчет с текущей даты
            else:
                end_date = now



        # Если подписка уже активна, прибавляем к ней дни
        if end_date and end_date.replace(tzinfo=None) > now.replace(tzinfo=None):
            new_end_date = end_date + timedelta(days=days)
        else:
            new_end_date = now + timedelta(days=days)

        # Если ключ отсутствует или не был найден, создаем нового пользователя в системе Marzban
        if access_key is None or access_key == "":
            create_response = await marzban.create_user(f"user_{user_id}")

            if create_response is None or "error" in create_response:
                await bot.send_message(chat_id=callback_query.from_user.id,
                                       text="Ошибка при создании пользователя. Пожалуйста, свяжитесь с поддержкой.")
                return

            key_list = create_response.get("links", [])
            if key_list:
                access_key = key_list[0] +'\n' + key_list[1] # Получаем ключ доступа

            else:
                await bot.send_message(
                    chat_id=callback_query.from_user.id,
                    text="Не удалось получить ключ доступа. Пожалуйста, свяжитесь с поддержкой."
                )
                return

        # Сохраняем обновленную подписку и ключ в БД
        async with aiosqlite.connect('tg.db') as db:
            await db.execute('''
                INSERT OR REPLACE INTO accounts (user_id, end_date, access_key)
                VALUES (?, ?, ?)
            ''', (user_id, new_end_date.isoformat(), access_key))
            await db.commit()

        # Отправляем сообщение о завершении оплаты и ключе
        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text=f"Оплата прошла успешно! Ваша подписка на {duration} активирована до {new_end_date.strftime('%Y-%m-%d')}.\n\n"
                 f"Ваш ключ доступа (его нужно ввести в Outline):\n\n"
                 f"<code>{access_key}</code>", parse_mode='HTML'
        )
    else:
        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text="Сначала нужно оплатить!"
        )







if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
