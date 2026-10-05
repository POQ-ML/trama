"""Logging — helper stdlib."""
from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Retorna logger stdlib com handler básico se ainda sem handlers."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    return logger
