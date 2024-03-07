import os
import logging
from dotenv import load_dotenv

def configure_logging(log_filename, logger_name=None):
    load_dotenv()
    log_directory = os.getenv('LOG_DIRECTORY', '.')
    log_file = os.path.join(log_directory, log_filename)

    # Create or get the logger
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    logger.setLevel(logging.INFO)

    # Check if the logger already has handlers to avoid duplicate logs
    if not logger.handlers:
        # Create file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # Create formatter and add it to the handler
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)

        # Add the handler to the logger
        logger.addHandler(file_handler)

    return logger