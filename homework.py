import json
import locale
import os
import time
from http import HTTPStatus

import requests

from configs import log_configured
from exceptions import APIException, ServiceException
from dotenv import load_dotenv
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext


logger = log_configured.getLogger(__name__)
locale.setlocale(locale.LC_ALL, ('ru_RU', 'UTF-8'))

load_dotenv(override=True)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_PERIOD = 60  # Retry_period = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
PAYLOAD = {'from_date': 0}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

prev_status = {
    'homework_name': None,
    'status': None,
}


def check_tokens() -> None:
    """Проверяем наличие токена."""
    for token in (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID):
        if token is None:
            # logger.error('Проблема с доступом к токенам.')
            raise APIException('Ошибка доступа к токенам.')


def get_api_answer() -> dict:
    """Получаем ответ от API сервиса Практикум.Домашка."""
    # PAYLOAD['from_date'] = timestamp
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
            # logger.error(f'Ошибка при декодировании JSON: {e}')
            raise ServiceException(f'Ошибка декодирования JSON: {e}')
    else:
        # logger.error(
        #    f'Ошибочный ответ от сервиса: {answer_recieved.status_code}'
        # )
        raise ServiceException(
            f'Ошибка ответа от {ENDPOINT}: {answer_recieved.status_code}'
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

    def validate_format(data, expected_format, logger):
        for key, expected_type in expected_format.items():
            if key not in data:
                raise KeyError(f'Error: {key} is missing in the dictionary.')
            if not isinstance(data[key], expected_type):
                raise TypeError(
                    f'Error: {key} should be of type {expected_type.__name__}.'
                )
    try:
        validate_format(response, expected_format1, logger)
        homeworks = response.get('homeworks', [])
        if homeworks and isinstance(homeworks[0], dict):
            for homework in homeworks:
                validate_format(homework, expected_format2, logger)
    except (KeyError, TypeError) as e:
        error_message = f'Ошибка API формата: {e}'
        # logger.error(error_message)
        raise ServiceException(error_message)


def parse_status(homework) -> str:
    """Возвращаем статус домашней работы по инфо о ней."""
    try:
        homework_name, status = homework.get('lesson_name'), homework.get('status')
        if homework_name != prev_status['homework_name']:
            prev_status['homework_name'], prev_status['status'] = homework_name, status
        else:
            prev_status['status'] = status
            return 'same here'
        return HOMEWORK_VERDICTS.get(status)
    except KeyError as e:
        error_message = f'Ошибка {e} в функции parse_status'
        # logger.error(error_message)
        raise ServiceException(error_message)


def send_message(bot, message) -> None:
    """Отправляем сообщение в чат."""
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


def start_command(update, context: CallbackContext):
    """Логика комманды /start."""
    chat = update.effective_chat
    if chat is not None:
        message: str = (
            f'Привет, {chat.first_name}!\n'
            'Я тут, чтобы проверить статус твоей последней домашки '
            'и держать тебя в курсе, если будут какие-то апдейты.\n'
            '*ушёл проверять статус*\n'
        )
        send_message(context.bot, message)
        api_answer = get_api_answer()
        status = parse_status(api_answer.get('homeworks')[0])
        send_message(context.bot, status)
    else:
        # logger.error('Ошибка доступа к чату при запросе /start.')
        raise ServiceException('Ошибка доступа к чату при запросе /start.')


def help_command(update, context: CallbackContext) -> None:
    """Логика команды /help."""
    if update.effective_chat is not None:
        message: str = (
            'Этот бот не поможет выполнить домашку, но пришлёт статус '
            'последней отправленной работы и обязательно напишет, '
            'если он изменится. Stay tuned!\n\n'
            '* если кажется, что что-то идет не так, попробуй '
            'перезапустить бота /start'
        )
        send_message(context.bot, message)
    else:
        # logger.error('Ошибка доступа к чату при запросе /help.')
        raise ServiceException('Ошибка доступа к чату при запросе /help.')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)

    updater = Updater(bot=bot, use_context=True)
    updater.dispatcher.add_handler(CommandHandler('start', start_command))
    updater.dispatcher.add_handler(CommandHandler('help', help_command))

    updater.start_polling()

    timestamp = int(time.time())

    while True:
        try:
            # timestamp = int(time.time())
            api_answer = get_api_answer()
            status = parse_status(api_answer.get('homeworks')[0])
            # if status != prev_status:send_message(bot, status) prev_status = status
            send_message(bot, status)
        except Exception as e:
            print(f'Сбой в работе программы: {e}')

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
