# utils/logger.py

import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


def get_logger(name: str) -> logging.Logger:
    """
    Mengembalikan logger dengan:
    - File handler rotating harian, retention 90 hari.
    - Console handler.
    - Nama file log diambil dari bagian terakhir `name`.
    """
    # Tentukan folder logs
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Ambil nama modul / blueprint terakhir untuk nama file
    file_name = name.split(".")[-1] + ".log"
    log_file = log_dir / file_name

    # Buat logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # Hindari duplikasi handler

    if not logger.handlers:
        # Rotating file handler: setiap tengah malam, simpan 90 hari
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=90,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        logger.debug(f"[Logger] Initialized '{name}', output → {log_file}")

    return logger
