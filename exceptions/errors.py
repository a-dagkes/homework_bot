"""Кастомные классы обработки ошибок."""


class APIException(Exception):
    """Ошибки в работе API."""

    def __init__(self, message):
        """Сообщение об ошибке при обращении к эндпоинту."""
        super().__init__(message)
