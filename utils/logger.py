"""
utils/logger.py

Centralized logging setup using loguru.
Import `logger` from here in every module instead of using print().

Usage:
    from utils.logger import logger
    logger.info("Fetched 5 emails")
    logger.warning("Token expired, refreshing...")
    logger.error("Gmail API call failed: {error}", error=str(e))
"""

import os
import sys
from loguru import logger

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Remove default loguru handler
logger.remove()

# Console output — clean format for development
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
    colorize=True,
)

# File output — full format for debugging
logger.add(
    "logs/agent.log",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="10 MB",
    retention="7 days",
    compression="zip",
)

__all__ = ["logger"]
