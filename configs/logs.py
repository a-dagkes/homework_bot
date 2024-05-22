"""Настройка логирования."""
import logging as log_configured
import sys

log_configured.basicConfig(
    level=log_configured.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        log_configured.StreamHandler(sys.stdout),
    ],
)
