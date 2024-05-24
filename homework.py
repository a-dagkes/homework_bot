import json
import os
import sys
import time
from http import HTTPStatus
import logging

import requests
from dotenv import load_dotenv
from telegram import Bot, TelegramError

from exceptions import APIException

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
logging.getLogger('telegram.bot').setLevel(logging.WARNING)

# locale.setlocale(locale.LC_ALL, ('ru_RU', 'UTF-8'))

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
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }.items():
        if token_value is None:
            logger.critical(f'Ошибка доступа к токену {token_name}.')
            sys.exit('Программа принудительно остановлена.')


def get_api_answer(timestamp: int) -> dict:
    """Получаем ответ от API сервиса Практикум.Домашка."""
    PAYLOAD['from_date'] = timestamp
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=PAYLOAD,
        )
        if response.status_code != HTTPStatus.OK:
            raise APIException(
                message=f'Ошибка ответа от API: {response.status_code}',
            )
        return response.json()
    except requests.RequestException as e:
        raise APIException(
            message=f'Нет доступа к API: {e}.',
        )
    except json.JSONDecodeError as e:
        raise APIException(
            message=f'Ошибка декодирования JSON: {e}',
        )


def check_response(response: dict) -> None:
    """Проверяем валидность формата ответа API."""
    try:
        if not response:
            raise KeyError('не получен объект response.')
        if not isinstance(response, dict):
            raise ValueError(
                f'получен объект {type(response).__name__} типа '
                'вместо ожидаемого типа dict.'
            )
        if 'homeworks' not in response:
            raise KeyError('ключ homeworks не найден.')
        if not isinstance(response.get('homeworks'), list):
            raise ValueError('значение по ключу homeworks не типа list.')
        if 'current_date' not in response:
            raise KeyError('ключ current_date не найден.')
        if not isinstance(response.get('current_date'), int):
            raise TypeError('значение по ключу current_date не типа int.')
        return response.get('homeworks')
    except (KeyError, TypeError) as e:
        raise APIException(
            message=f'Ошибка при проверке формата ответа API: {e}',
        )
    except ValueError as e:
        raise TypeError(str(e))


def parse_status(homework: dict) -> str:
    """Возвращаем статус домашней работы и инфо о ней."""
    try:
        '''
        if 'lesson_name' not in homework:
            raise KeyError('не найден ключ lessons_name.')
        homework_name = homework.get('lesson_name')
        if not isinstance(homework_name, str):
            raise TypeError('lessons_name не ожидаемого str типа.')
        '''
        if 'homework_name' not in homework:
            raise KeyError('не найден ключ homework_name.')
        homework_name = homework.get('homework_name')
        if not isinstance(homework_name, str):
            raise TypeError('homework_name не ожидаемого str типа.')
        if 'status' not in homework:
            raise KeyError('не найден ключ status.')
        status = homework.get('status')
        if not isinstance(status, str):
            raise TypeError('status не ожидаемого str типа.')
        if status not in HOMEWORK_VERDICTS:
            raise KeyError(f'неизвестный статус домашней работы: {status}.')

        message = (
            f'Изменился статус проверки работы "{homework_name}". '
            f'{HOMEWORK_VERDICTS.get(status)}'
        )
        return message

    except (KeyError, TypeError) as e:
        raise APIException(
            message=f'Ошибка при получении инфо о домашней работе: {e}.',
        )


def send_message(bot: Bot, message: str) -> None:
    """Отправляем сообщение в чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except TelegramError as e:
        logger.error(f'Ошибка при отправке сообщения: {e}.')
    else:
        logger.debug(f'Сообщение успешно отправлено: {message}.')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)

    timestamp = 0
    prev_verdict = ''

    while True:
        try:
            new_verdict = None
            api_answer = get_api_answer(timestamp)
            logger.debug(f'Получен ответ от API на момент {timestamp}.')
            check_response(api_answer)
            logger.debug('Проверка валидности формата ответа API пройдена.')
            homeworks = api_answer.get('homeworks')
            if homeworks:
                logger.debug('Получены обновления.')
                new_verdict = parse_status(homeworks[0])
                logger.debug('Обновления распарсены.')
                if new_verdict != prev_verdict:
                    send_message(bot, new_verdict)
                    logger.debug('Полученный вердикт отправлен.')
                    prev_verdict = new_verdict
                    logger.debug('Новый вердикт перезаписан вместо старого.')
                    timestamp = api_answer.get('current_date', timestamp)
                    logger.debug('Обновлена точка отсчета для обновлений.')
                else:
                    logger.warning('Новый вердикт идентичен предыдущему.')
            else:
                logger.debug('Обновлений нет.')
        except TypeError as e:
            logger.error(f'Ошибка при проверке формата ответа API: {e}')
            continue
        except APIException as e:
            logger.error(e)
            continue
        except Exception as e:
            logger.error(f'Сбой в работе бота: {e}')
            check_tokens()
            try:
                bot = Bot(token=TELEGRAM_TOKEN)
            except Exception as e:
                logger.critical(f'Ошибка при перезапуске бота: {e}')
                sys.exit('Программа принудительно остановлена.')
            continue
        finally:
            time.sleep(RETRY_PERIOD)
            logger.debug(f'Бот уснул на {RETRY_PERIOD} секунд.')


if __name__ == '__main__':
    main()
