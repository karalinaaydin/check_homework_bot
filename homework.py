import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import (APIResponseError, MissingTokensError,
                        ProgramError, SendMessageError)

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


REQUIRED_TOKENS = ['TELEGRAM_TOKEN', 'PRACTICUM_TOKEN', 'TELEGRAM_CHAT_ID']
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)

MISSING_TOKENS_ERROR = 'Отсутствуют переменные: {missing_tokens}'
API_REQUEST_ERROR = (
    'Ошибка при запросе к API: {error}. Параметры запроса: {params}'
)
API_RESPONSE_ERROR = (
    'Ошибка при запросе к API: Код ответа {status_code}. Параметры запроса: '
    '{params}'
)
API_RETURNED_ERROR = (
    'API вернул ошибку: {error_message}. Параметры запроса: {params}'
)
API_DICT_TYPE_ERROR = (
    'Ответ API должен быть словарем, получен тип: {actual_type}'
)
MISSING_KEY_ERROR = 'Отсутствует ключ "{key}" в ответе API: {homework}'
MISSING_HOMEWORKS_KEY_ERROR = 'В ответе API отсутствует ключ "homeworks"'
HOMEWORKS_LIST_TYPE_ERROR = (
    'Значение по ключу "homeworks" должно быть списком, но был получен тип: '
    '{actual_type}'
)
UNEXPECTED_STATUS_ERROR = 'Неожиданный статус домашней работы: {status}'
STATUS_MESSAGE = 'Изменился статус проверки работы "{name}". {verdict}'
MESSAGE_SENT = ('Сообщение отправлено: {message}')
SEND_MESSAGE_ERROR = (
    'Ошибка при отправке сообщения: {error}. Сообщение: "{message}"'
)
PROGRAM_STOPPED_ERROR = (
    'Программа завершена из-за отсутствия необходимых переменных окружения.'
)
NO_NEW_STATUSES = 'Новых статусов нет'
PROGRAM_ERROR = 'Сбой в работе программы: {error}'


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения."""
    missing_tokens = [
        name for name in REQUIRED_TOKENS if not globals().get(name)]
    if missing_tokens:
        logger.critical(
            MISSING_TOKENS_ERROR.format(missing_tokens=missing_tokens))
        raise MissingTokensError


def get_api_answer(timestamp):
    """Делает запрос к API сервиса Практикум Домашка."""
    params = {'from_date': timestamp}
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': params
    }
    try:
        response = requests.get(**request_params)
    except requests.RequestException as req_err:
        raise OSError(
            API_REQUEST_ERROR.format(error=req_err, params=request_params)
        )
    if response.status_code != HTTPStatus.OK:
        raise OSError(
            API_RESPONSE_ERROR.format(
                status_code=response.status_code, params=request_params))
    response_json = response.json()
    if 'code' in response_json or 'error' in response_json:
        error_message = response_json.get('error', 'Неизвестная ошибка')
        logger.error(
            API_RETURNED_ERROR.format(
                error_message=error_message, params=params))
        raise APIResponseError(
            API_RETURNED_ERROR.format(
                error_message=error_message, params=params))
    response_json = response.json()
    found_key = None
    if 'code' in response_json:
        found_key = 'code'
    elif 'error' in response_json:
        found_key = 'error'
    if found_key:
        error_message = response_json.get(found_key, 'Неизвестная ошибка')
        raise APIResponseError(
            API_RETURNED_ERROR.format(
                error_message=error_message, params=request_params,
                key=found_key, value=response_json[found_key]))
    return response_json


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        raise TypeError(
            API_DICT_TYPE_ERROR.format(actual_type=type(response).__name__))
    if 'homeworks' not in response:
        raise KeyError(MISSING_HOMEWORKS_KEY_ERROR)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            HOMEWORKS_LIST_TYPE_ERROR.format(
                actual_type=type(homeworks).__name__))
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError(
            MISSING_KEY_ERROR.format(key='homework_name', homework=homework))
    if 'status' not in homework:
        raise KeyError(
            MISSING_KEY_ERROR.format(key='status', homework=homework))
    status = homework['status']
    name = homework['homework_name']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(UNEXPECTED_STATUS_ERROR.format(status=status))
    return STATUS_MESSAGE.format(name=name, verdict=HOMEWORK_VERDICTS[status])


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(MESSAGE_SENT.format(message=message))
    except Exception as e:
        logger.error(SEND_MESSAGE_ERROR.format(error=e, message=message))
        raise SendMessageError(
            SEND_MESSAGE_ERROR.format(error=e, message=message))


def handle_homework_response(bot, homeworks, last_message, timestamp,
                             response):
    """Обрабатывает успешный ответ от API и отправляет сообщение."""
    if homeworks:
        message = parse_status(homeworks[0])
        if message != last_message:
            try:
                send_message(bot, message)
                last_message = message
            except SendMessageError as e:
                logger.error(
                    SEND_MESSAGE_ERROR.format(error=e, message=message))
            timestamp = response.get('current_date', timestamp)
    else:
        logger.debug(NO_NEW_STATUSES)
    return last_message, timestamp


def handle_program_error(bot, error, last_message):
    """Обрабатывает ошибки программы и отправляет сообщение об ошибке."""
    message = PROGRAM_ERROR.format(error=error)
    if message != last_message:
        try:
            send_message(bot, message)
            last_message = message
        except SendMessageError as e:
            logger.error(
                SEND_MESSAGE_ERROR.format(error=e, message=message))
    return last_message


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except MissingTokensError:
        return

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            last_message, timestamp = handle_homework_response(
                bot, homeworks, last_message, timestamp, response)
        except ProgramError as error:
            last_message = handle_program_error(bot, error, last_message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s [%(levelname)s] [%(funcName)s:%(lineno)d] %(message)s'
        ),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f'{__file__}.log', encoding='utf-8')
        ]
    )
    main()
