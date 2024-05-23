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
from exceptions import TokenError, APIException

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

locale.setlocale(locale.LC_ALL, ('ru_RU', 'UTF-8'))

load_dotenv(override=True)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_PERIOD = 10  # gjf 600
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
            raise TokenError(token_name)


def get_api_answer(timestamp) -> dict:
    """Получаем ответ от API сервиса Практикум.Домашка."""
    PAYLOAD['from_date'] = timestamp
    try:
        answer_recieved = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=PAYLOAD,
        )
        # answer_recieved.raise_for_status()
        if answer_recieved.status_code != HTTPStatus.OK:
            raise APIException(
                message=f'Ошибка ответа от API: {answer_recieved.status_code}',
            )
    except Exception as e:
        raise APIException(
            message=f'Нет доступа к API: {e}.',
        )

    try:
        answer = answer_recieved.json()  # json.loads(answer_recieved.text)
        return answer
    except json.JSONDecodeError as e:
        raise APIException(
            message=f'Ошибка декодирования JSON: {str(e)}',
        )


def check_response(response) -> None:
    """Проверяем валидность формата ответа API."""
    try:
        if not isinstance(response, dict):
            raise TypeError(
                f'получен объект {type(response).__name__} типа '
                f'вместо ожидаемого типа dict.'
            )
        if 'homeworks' not in response:
            raise KeyError('ключ homeworks не найден.')
        homeworks = response.get('homeworks')
        if not isinstance(homeworks, list):
            raise TypeError(
                f'получен объект {type(response).__name__} типа '
                f'вместо ожидаемого типа list.'
            )
        if homeworks:
            for homework in homeworks:
                if 'lesson_name' not in homework:
                    raise KeyError('не найден ключ lessons_name.')
                if 'status' not in homework:
                    raise KeyError('не найден ключ status.')
                if not isinstance(homeworks['lesson_name'], str):
                    raise TypeError('lessons_name не ожидаемого str типа.')
                if not isinstance(homeworks['status'], str):
                    raise TypeError('status не ожидаемого str типа.')
        return homeworks
    except (KeyError, TypeError) as e:
        raise APIException(
            message=f'Ошибка при проверке формата ответа API: {e}.',
        )
'''
    expected_format_for_response = {
        'homeworks': list,
        'current_date': int,
    }
    expected_format_for_homework = {
        'lesson_name': str,
        'status': str,
    }

    def validate_format(data, expected_format):
        if not isinstance(expected_format, dict):
            if not isinstance(data, expected_format):
                raise TypeError(
                    f'В ответе API получен объект {type(data).__name__} типа '
                    f'вместо ожидаемого {expected_format.__name__} типа.'
                )
        else:
            for key, expected_type in expected_format.items():
                if key not in data:
                    raise KeyError(f'Ключ {key} не найден.')
                if not isinstance(data[key], expected_type):
                    raise TypeError(
                        f'Ключ {key} не ожидаемого '
                        '{expected_type.__name__} типа.'
                    )

    try:
        validate_format(response, dict)
        validate_format(response, expected_format_for_response)
        homeworks = response.get('homeworks')
        validate_format(homeworks, list)
        if homeworks:
            for homework in homeworks:
                validate_format(homework, expected_format_for_homework)
        return response
    except (KeyError, TypeError) as e:
        raise APIException(
            message=f'Ошибка ключей в ответе API: {e}',
        )
'''


def parse_status(homework) -> str:
    """Возвращаем статус домашней работы и инфо о ней."""
    try:
        homework_name = homework.get('lesson_name')
        if homework_name is None:
            raise APIException(
                message='Инфо домашней работы не содержит ее имени.',
            )

        status = homework.get('status')
        if status is None:
            raise APIException(
                message='Не получен статус домашней работы.',
            )
        if status not in HOMEWORK_VERDICTS:
            raise APIException(
                message=f'Неизвестный статус домашней работы: {status}.',
            )

        message = (
            f'Изменился статус проверки работы "{homework_name}". '
            f'{HOMEWORK_VERDICTS.get(status)}'
        )
        return message
    except Exception as e:
        raise APIException(
            message=f'Ошибка при получении инфо о домашней работе: {e}.',
        )


def send_message(bot, message) -> None:
    """Отправляем сообщение в чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение успешно отправлено.')
    except Exception as e:
        logger.error(
            f'Что-то пошло не так при отправке сообщения: {e}.'
        )


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
        logger.debug('Токены проверены.')
        bot = Bot(token=TELEGRAM_TOKEN)
        logger.debug('Бот активирован.')
    except TokenError as e:
        logger.critical(str(e))
        sys.exit('Программа принудительно остановлена.')
    except Exception as e:
        logger.critical(f'Ошибка при запуске бота: {e}.')
        sys.exit('Программа принудительно остановлена.')

    timestamp = 0
    prev_verdict = ''

    while True:
        try:
            new_timestamp = int(time.time())
            new_verdict = None

            api_answer = get_api_answer(timestamp)
            logger.debug(f'Получен ответ от API на момент {timestamp}.')
            homeworks = check_response(api_answer).get('homeworks')
            logger.debug('Проверка валидности формата ответа API пройдена.')
            # homeworks = api_answer.get('homeworks')
            if homeworks:
                logger.debug('Получены обновления.')
                new_verdict = parse_status(homeworks[0])
                logger.debug('Обновления распарсены.')
                if new_verdict != prev_verdict:
                    send_message(bot, new_verdict)
                    logger.debug('Полученный вердикт отправлен.')
                    prev_verdict = new_verdict
                    logger.debug('Новый вердикт перезаписан вместо старого.')
                    timestamp = new_timestamp
                    logger.debug('Обновлена точка отсчета для обновлений.')
                else:
                    logger.warning('Новый вердикт идентичен предыдущему.')
            else:
                logger.debug('Обновлений нет.')
        except APIException as e:
            logger.error(e)
        except Exception as e:
            logger.error(f'Неожиданный сбой в работе бота: {e}')

        finally:
            time.sleep(RETRY_PERIOD)
            logger.debug(f'Бот уснул на {RETRY_PERIOD} секунд.')


if __name__ == '__main__':
    main()
