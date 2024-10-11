import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import APIResponseError

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

log_file_path = __file__ + '.log'
logger = logging.getLogger(__name__)

MISSING_TOKENS_ERROR = ('Отсутствуют переменные: {missing_tokens}')
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
MISSING_HOMEWORKS_KEY_ERROR = ('В ответе API отсутствует ключ "homeworks"')
HOMEWORKS_LIST_TYPE_ERROR = (
    'Значение по ключу "homeworks" должно быть списком, но был получен тип: '
    '{actual_type}'
)
MISSING_KEYS_ERROR = (
    'Отсутствуют ключи "status" или "homework_name" в ответе API.'
)
UNEXPECTED_STATUS_ERROR = ('Неожиданный статус домашней работы: {status}')
STATUS_MESSAGE = ('Изменился статус проверки работы "{name}". {verdict}')
MESSAGE_SENT = ('Сообщение отправлено: {message}')
SEND_MESSAGE_ERROR = (
    'Ошибка при отправке сообщения: {error}. Сообщение: "{message}"'
)
PROGRAM_STOPPED_ERROR = (
    'Программа завершена из-за отсутствия необходимых переменных окружения.'
)
NO_NEW_STATUSES = ('Новых статусов нет')
PROGRAM_ERROR = ('Сбой в работе программы: {error}')


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения."""
    missing_tokens = [
        name for name in REQUIRED_TOKENS if not globals().get(name)]

    if missing_tokens:
        logger.critical(
            MISSING_TOKENS_ERROR.format(missing_tokens=missing_tokens))
        return False


def get_api_answer(timestamp):
    """Делает запрос к API сервиса Практикум Домашка."""
    params = {'from_date': timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException as req_err:
        logger.error(API_REQUEST_ERROR.format(error=req_err, params=params))
        raise APIResponseError

    if response.status_code != HTTPStatus.OK:
        logger.error(
            API_RESPONSE_ERROR.format(
                status_code=response.status_code, params=params))
        raise requests.exceptions.HTTPError(
            API_RESPONSE_ERROR.format(
                status_code=response.status_code, params=params))

    response_json = response.json()

    if 'code' in response_json or 'error' in response_json:
        error_message = response_json.get('error', 'Неизвестная ошибка')
        logger.error(
            API_RETURNED_ERROR.format(
                error_message=error_message, params=params))
        raise APIResponseError(
            API_RETURNED_ERROR.format(
                error_message=error_message, params=params))

    return response_json


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        actual_type = type(response).__name__
        logger.error(API_DICT_TYPE_ERROR.format(actual_type=actual_type))
        raise TypeError(API_DICT_TYPE_ERROR.format(actual_type=actual_type))

    if 'homeworks' not in response:
        logger.error(MISSING_HOMEWORKS_KEY_ERROR)
        raise KeyError(MISSING_HOMEWORKS_KEY_ERROR)

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        actual_type = type(homeworks).__name__
        logger.error(HOMEWORKS_LIST_TYPE_ERROR.format(actual_type=actual_type))
        raise TypeError(
            HOMEWORKS_LIST_TYPE_ERROR.format(actual_type=actual_type))

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'status' not in homework or 'homework_name' not in homework:
        raise KeyError(MISSING_KEYS_ERROR)

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


def send_if_new_message(bot, message, last_message):
    """Отправляет сообщение, если оно отличается от последнего."""
    if message != last_message:
        send_message(bot, message)
        return message
    return last_message


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.error(PROGRAM_STOPPED_ERROR)
        return

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                last_message = send_if_new_message(bot, message, last_message)
                timestamp = response.get('current_date', timestamp)
            else:
                logger.debug(NO_NEW_STATUSES)

        except Exception as error:
            message = PROGRAM_ERROR.format(error=error)
            last_message = send_if_new_message(bot, message, last_message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s [%(levelname)s] %(message)s'
            '[%(funcName)s:%(lineno)d]'
        ),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file_path, encoding='utf-8')
        ]
    )
    main()
