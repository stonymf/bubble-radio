import os
import logging
from dotenv import load_dotenv

def configure_logging(log_filename):
    load_dotenv()
    log_directory = os.getenv('LOG_DIRECTORY', '.')
    log_file = os.path.join(log_directory, log_filename)
    logging.basicConfig(filename=log_file,
                        level=logging.INFO,
                        format='%(asctime)s %(levelname)s: %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')