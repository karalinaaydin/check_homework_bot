class APIResponseError(Exception):
    """Кастомное исключение для ошибок ответа API."""

class MissingTokenError(Exception):
    """Исключение для отсутствующих токенов."""