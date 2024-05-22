import json
import locale
import os
import time
from http import HTTPStatus

import requests

from configs import log_configured
from dotenv import load_dotenv
from telegram import Bot


logger = log_configured.getLogger(__name__)
locale.setlocale(locale.LC_ALL, ('ru_RU', 'UTF-8'))

load_dotenv(override=True)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
PAYLOAD = {'from_date': 0}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens() -> None:
    """Проверяем наличие токена."""
    for token in (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID):
        if token is None:
            logger.error('Ошибка доступа к токенам.')


def get_api_answer(timestamp) -> dict:
    """Получаем ответ от API сервиса Практикум.Домашка."""
    PAYLOAD['from_date'] = timestamp
    answer_recieved = requests.get(
        ENDPOINT,
        headers=HEADERS,
        params=PAYLOAD,
    )
    if answer_recieved.status_code == HTTPStatus.OK:
        try:
            answer = json.loads(answer_recieved.text)
            return answer
        except json.JSONDecodeError as e:
            logger.error(f'Ошибка декодирования JSON: {e}.')
    else:
        logger.error(
            f'Ошибочный ответ от {ENDPOINT}: {answer_recieved.status_code}.'
        )


def check_response(response) -> None:
    """Проверяем валидность формата ответа API."""
    expected_format1 = {
        'homeworks': list,
        'current_date': int,
    }
    expected_format2 = {
        'lesson_name': str,
        'status': str,
    }

    def validate_format(data, expected_format):
        for key, expected_type in expected_format.items():
            if key not in data:
                raise KeyError(f'{key} не найден в ответе API.')
            if not isinstance(data[key], expected_type):
                raise TypeError(
                    f'{key} не ожидаемого {expected_type.__name__} типа.'
                )
    try:
        validate_format(response, expected_format1)
        homeworks = response.get('homeworks', [])
        if homeworks and isinstance(homeworks[0], dict):
            for homework in homeworks:
                validate_format(homework, expected_format2)
    except (KeyError, TypeError) as e:
        logger.error(f'Ошибка API формата: {e}')


def parse_status(homework) -> str:
    """Возвращаем статус домашней работы по инфо о ней."""
    try:
        return HOMEWORK_VERDICTS.get(homework.get('status'))
    except KeyError as e:
        logger.error(f'Ошибка {e} при поиске вердикта в словаре.')


def send_message(bot, message) -> None:
    """Отправляем сообщение в чат."""
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


def get_new_verdict(timestamp):
    """Получение нового вердикта на момент timestamp."""
    try:
        verdict = None
        new_timestamp = int(time.time())
        api_answer = get_api_answer(timestamp)
        check_response(api_answer)
        homeworks = api_answer.get('homeworks')
        if homeworks != []:
            verdict = parse_status(homeworks[0])
        return new_timestamp, verdict
    except Exception as e:
        logger.error(f'Сбой при получении или обработке ответа от API: {e}')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)

    timestamp = 0
    prev_verdict = ''

    while True:
        try:
            timestamp, new_verdict = get_new_verdict(timestamp)
            if new_verdict is not None and new_verdict != prev_verdict:
                send_message(bot, new_verdict)
                prev_verdict = new_verdict
            else:
                send_message(bot, 'same_here')
            print(timestamp)
        except Exception as e:
            logger.error(f'Сбой в работе бота: {e}')

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
