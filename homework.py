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


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения."""
    missing_tokens = [
        name for name in REQUIRED_TOKENS if not globals().get(name)
        ]

    if missing_tokens:
        logger.critical(f'Отсутствуют переменные: {missing_tokens}')
        return False


def get_api_answer(timestamp):
    """Делает запрос к API сервиса Практикум Домашка."""
    params = {'from_date': timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException as req_err:
        logger.error(
            f'Ошибка при запросе к API: {req_err}. '
            f'Параметры запроса: {params}'
        )
        raise

    if response.status_code != HTTPStatus.OK:
        logger.error(
            f'Ошибка при запросе к API: Код ответа {response.status_code}. '
            f'Параметры запроса: {params}'
        )
        raise requests.exceptions.HTTPError(
            f'Ошибка при запросе к API: Код ответа {response.status_code}. '
            f'Параметры запроса: {params}'
        )

    response_json = response.json()

    if 'code' in response_json or 'error' in response_json:
        error_message = response_json.get('error', 'Неизвестная ошибка')
        logger.error(
            f'API вернул ошибку: {error_message}. Параметры запроса: {params}'
            )
        raise APIResponseError(
            f'API вернул ошибку: {error_message}.'
            f'Параметры запроса: {params}'
            )

    return response_json


def check_response(response):
    '''Проверяет корректность ответа API.'''
    if not isinstance(response, dict):
        actual_type = type(response).__name__
        logger.error(
            f'Ответ API должен быть словарем, получен тип: {actual_type}'
            )
        raise TypeError(
            f'Ответ API должен быть словарем, получен тип: {actual_type}'
            )

    if 'homeworks' not in response:
        logger.error('''В ответе API отсутствует ключ "homeworks"''')
        raise KeyError('''В ответе API отсутствует ключ "homeworks"''')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        actual_type = type(homeworks).__name__
        logger.error(
            f'Значение по ключу "homeworks" должно быть списком, '
            f'но был получен тип: {actual_type}'
            )
        raise TypeError(
            f'Значение по ключу "homeworks" должно быть списком, '
            f'но был получен тип: {actual_type}'
            )

    return homeworks


def parse_status(homework):
    '''Извлекает статус домашней работы.'''
    if 'status' not in homework or 'homework_name' not in homework:
        raise KeyError(
            'Отсутствуют ключи "status" или "homework_name" в ответе API.'
            )
    status = homework['status']
    name = homework['homework_name']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f"Неожиданный статус домашней работы: {status}")

    return (
        f'Изменился статус проверки работы "{name}"'
        f'{HOMEWORK_VERDICTS[status]}'
    )


def send_message(bot, message):
    '''Отправляет сообщение в Telegram.'''
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение отправлено: {message}')
    except Exception as e:
        logger.error(
            f'Ошибка при отправке сообщения: {e}. Сообщение: "{message}"'
            )


def send_if_new_message(bot, message, last_message):
    '''Отправляет сообщение, если оно отличается от последнего.'''
    if message != last_message:
        send_message(bot, message)
        return message
    return last_message


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.error(
            '''
            Программа завершена из-за отсутствия
            необходимых переменных окружения.
            '''
            )
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
                if message != last_message:
                    last_message = send_if_new_message(bot, message,
                                                       last_message)
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.debug('Новых статусов нет')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if message != last_message:
                send_message(bot, message)
                last_message = send_if_new_message(bot, message, last_message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file_path, encoding='utf-8')
        ]
    )
    main()
