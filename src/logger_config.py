import os
import logging
from src.config import LOG_DIR


def configure_logging(log_filename, logger_name=None):
    log_file = os.path.join(LOG_DIR, log_filename)

    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger
