import yookassa
import get_api_token
import aiosqlite
import logging


async def create_payment(user_id, duration):
    try:
        # Настройка конфигурации YooKassa
        yookassa.Configuration.account_id = get_api_token.Yoo_Api_id
        yookassa.Configuration.secret_key = get_api_token.Yoo_Api_key

        # Определение суммы и описания на основе выбранного срока
        if duration == '1month':
            amount_value = 100
            description = f'Подписка на 1 месяц для user_{user_id}'
        elif duration == '3month':
            amount_value = 250
            description = f'Подписка на 3 месяца для user_{user_id}'
        elif duration == '6month':
            amount_value = 450
            description = f'Подписка на 6 месяцев для user_{user_id}'
        else:
            logging.error(f"Неизвестная длительность подписки: {duration}")
            return None

        # Создание платежа
        payment = yookassa.Payment.create({
            "amount": {
                "value": amount_value,
                "currency": "RUB"
            },
            "confirmation": {
                "type": 'redirect',
                "return_url": f'https://t.me/UmbraVPN_bot?start={user_id}'
            },
            'description': description,
            'capture': True
        })

        # Сохранение идентификатора платежа в БД
        async with aiosqlite.connect('tg.db') as db:
            await db.execute('''
                UPDATE accounts
                SET payment_id = ?
                WHERE user_id = ?
            ''', (payment.id, user_id))
            await db.commit()


        # Возврат ссылки для подтверждения платежа
        url = payment.confirmation.confirmation_url
        return url

    except Exception as e:
        logging.error(f"Ошибка при создании платежа для пользователя {user_id}: {str(e)}")
        return None




async def check_payment_status(user_id):
    try:
        yookassa.Configuration.account_id = get_api_token.Yoo_Api_id
        yookassa.Configuration.secret_key = get_api_token.Yoo_Api_key

        async with aiosqlite.connect('tg.db') as db:
            async with db.execute('SELECT payment_id FROM accounts WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()

        if row:
            payment_id = row[0]
            payment = yookassa.Payment.find_one(payment_id)
            status = payment.status

            if status == 'succeeded':
                return True
            else:
                return False
        else:
            logging.warning(f"No payment_id found for user {user_id}")
            return False

    except Exception as e:
        logging.error(f"Ошибка при проверке статуса платежа для пользователя {user_id}: {str(e)}")
        return False
