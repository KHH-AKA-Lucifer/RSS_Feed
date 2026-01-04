import os
import logging 
from logging.handlers import RotatingFileHandler

def setup_logger(
        name: str = "discord-bot",
        level: int = logging.INFO,
        log_dir: str = "logs",
        log_file: str = "logs.log",
) -> logging.Logger:
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir_path = os.path.join(base_dir, log_dir)
    os.makedirs(log_dir_path, exist_ok=True)
    log_path = os.path.join(log_dir_path, log_file)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname) - 8s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes= 5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger