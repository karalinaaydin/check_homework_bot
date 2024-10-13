class APIResponseError(Exception):
    """Кастомное исключение для ошибок ответа API."""

class MissingTokensError(Exception):
    """Кастомное исключение для ошибок отсутствующих токенов."""

class SendMessageError(Exception):
    """Кастомное исключение для ошибок отправки сообщения."""

class ProgramError(Exception):
    """Кастомное исключение для ошибок сбоя программы."""
