"""Кастомные классы обработки ошибок."""


class TokenError(Exception):
    """Класс обработки ошибок при загрузке токенов."""

    def __init__(self, token_name):
        """Сообщение об ошибке содержащее имя токена."""
        self.token_name = token_name
        super().__init__(f'Ошибка доступа к токену {token_name}.')


class APIException(Exception):
    """Ошибки в работе API."""

    def __init__(self, message):
        """Сообщение об ошибке при обращении к эндпоинту."""
        self.message = message
        super().__init__(f'Ошибка обращения к эндпоинту: {message}')
