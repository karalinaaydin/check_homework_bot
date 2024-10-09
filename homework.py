import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv
from telebot import TeleBot

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения."""
    tokens = {
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }

    missing_tokens = [name for name, value in tokens.items() if not value]

    if missing_tokens:
        logger.critical(f"Отсутствуют переменные: {missing_tokens}")
        sys.exit("Программа остановлена из-за отсутствия переменных.")
    return True


def get_api_answer(timestamp):
    """Делает запрос к API сервиса Практикум Домашка."""
    params = {'from_date': timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != 200:
            logger.error(
                f"Ошибка при запросе к API: Код ответа {response.status_code}."
                f"Текст ответа: {response.text}"
            )
            raise Exception(
                f"API вернул неожиданный код: {response.status_code}")

        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logger.error(
            f"""Ошибка при запросе к API.
            Код ответа: {response.status_code}, ошибка: {http_err}
            """
        )
        raise requests.exceptions.HTTPError(
            f"""Ошибка при запросе к API.
            Код ответа: {response.status_code}, ошибка: {http_err}
            """
        )
    except requests.RequestException as req_err:
        logger.error(f"Ошибка при запросе к API: {req_err}")
        raise Exception(f"Ошибка при запросе к API: {req_err}")


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        logger.error("Ответ API должен быть словарем")
        raise TypeError("Ответ API должен быть словарем")

    if 'homeworks' not in response or 'current_date' not in response:
        logger.error("В ответе API отсутствуют необходимые ключи")
        raise KeyError("В ответе API отсутствуют необходимые ключи")

    if not isinstance(response['homeworks'], list):
        raise TypeError("Значение по ключу 'homeworks' должно быть списком")

    if not response['homeworks']:
        logger.debug("Новых статусов нет")

    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'status' not in homework or 'homework_name' not in homework:
        raise KeyError("""
                       Отсутствуют ключи 'status'
                       или 'homework_name' в ответе API.
                       """)
    status = homework.get('status')
    homework_name = homework.get('homework_name')

    if status not in HOMEWORK_VERDICTS:
        logger.error(f"Неожиданный статус домашней работы: {status}")
        raise ValueError(f"Неожиданный статус домашней работы: {status}")

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        bot.send_message(chat_id, message)
        logger.debug(f'Сообщение отправлено: {message}')
    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения: {e}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        return

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    last_error = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
                last_error = None
            else:
                logger.debug('Новых статусов нет')
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            logger.error(f'Сбой в работе программы: {error}')
            if str(error) != last_error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                last_error = str(error)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
