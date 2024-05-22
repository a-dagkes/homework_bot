import json
import locale
import os
import sys
import time
from http import HTTPStatus

import requests

import logging
from dotenv import load_dotenv
from telegram import Bot

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('send_message').setLevel(logging.WARNING)

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
    """Проверяем наличие токенов."""
    for token_name, token_value in {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }.items():
        if token_value is None:
            logger.critical(f'Ошибка доступа к токену {token_name}.')
            sys.exit('Программа принудительно остановлена.')


def get_api_answer(timestamp) -> dict:
    """Получаем ответ от API сервиса Практикум.Домашка."""
    PAYLOAD['from_date'] = timestamp
    try:
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
                return {}
        else:
            logger.error(
                f'Недоступность {ENDPOINT}: {answer_recieved.status_code}.'
            )
            return {}
    except requests.RequestException as e:
        logger.error(f'Ошибка при выполнении запроса к API: {e}.')


def check_response(response) -> None:
    """Проверяем валидность формата ответа API."""
    if not response:
        raise KeyError('В check_responce не передан ответ API.')

    expected_format1 = {
        'homeworks': list,
        'current_date': int,
    }
    expected_format2 = {
        'lesson_name': str,
        'status': str,
    }

    def validate_format(data, expected_format):
        if not isinstance(data, dict):
            raise TypeError(
                'В функцию validate_format попал объект не <dict> типа.'
            )
        for key, expected_type in expected_format.items():
            if key not in data:
                raise KeyError(f'Ключ {key} не найден.')
            if not isinstance(data[key], expected_type):
                raise TypeError(
                    f'Ключ {key} не ожидаемого {expected_type.__name__} типа.'
                )
    try:
        if not isinstance(response, dict):
            raise TypeError('Полученный ответ API не <dict> типа.')
        validate_format(response, expected_format1)
        homeworks = response.get('homeworks')
        if not isinstance(homeworks, list):
            raise TypeError(
                'В ответе API под ключом homeworks не <list> типа.'
            )
        for homework in homeworks:
            validate_format(homework, expected_format2)
        return response
    except (KeyError, TypeError) as e:
        logger.error(f'Ошибка ключей в ответе API: {e}')
        return {}


def parse_status(homework) -> str:
    """Возвращаем статус домашней работы по инфо о ней."""
    try:
        homework_name = homework.get('lesson_name')
        status = homework.get('status')    
        message = (
            f'Изменился статус проверки работы {homework_name}. '
            f'{HOMEWORK_VERDICTS.get(status)}'
        )
        return message
    except KeyError:
        logger.error('Неизвестный статус или имя домашней работы.')


def send_message(bot, message) -> None:
    """Отправляем сообщение в чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение успешно отправлено.')
    except Exception as e:
        logger.error(
            f'Что-то пошло не так при отправке сообщения: {e}.'
        )


def get_new_verdict(timestamp, prev_verdict):
    """Проверка обновлений на момент timestamp."""
    try:
        new_timestamp = int(time.time())
        api_answer = check_response(get_api_answer(timestamp))
        if api_answer == {}:
            return timestamp, None
        homeworks = api_answer.get('homeworks')
        if homeworks != []:
            new_verdict = parse_status(homeworks[0])
            if new_verdict == prev_verdict:
                logger.warning('Новый вердикт идентичен предыдущему.')
            return new_timestamp, new_verdict
        logger.debug('Обновлений нет.')
        return new_timestamp, None
    except Exception as e:
        logger.error(f'Сбой при получении или обработке ответа от API: {e}')
        return timestamp, None


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)

    timestamp = 0
    prev_verdict = ''

    while True:
        try:
            timestamp, new_verdict = get_new_verdict(timestamp, prev_verdict)
            logger.debug('Обновлена временная точка отсчета timestamp.')
            if new_verdict is not None:
                send_message(bot, new_verdict)
                logger.debug('Полученный вердикт отправлен.')
                prev_verdict = new_verdict
                logger.debug('Новый вердикт перезаписан вместо старого.')
        except Exception as e:
            logger.error(f'Сбой в работе бота: {e}')

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
