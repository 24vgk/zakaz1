# logging_config.py
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging() -> None:
    """
    Общая настройка логирования:
      - вывод в консоль;
      - файл logs/bot.log (INFO+);
      - файл logs/errors.log (ERROR+);
      оба файла ротируются раз в сутки.
    """
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Формат логов
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Чтобы не плодить хендлеры при повторных вызовах
    if getattr(root, "_logging_already_configured", False):
        return

    # --- консоль ---
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # --- файл со всеми уровнями (INFO+) ---
    all_file = TimedRotatingFileHandler(
        filename=log_dir / "bot.log",
        when="midnight",          # раз в день
        interval=1,
        backupCount=14,           # храним 14 дней
        encoding="utf-8",
        utc=False,
    )
    all_file.setFormatter(fmt)
    all_file.setLevel(logging.INFO)
    root.addHandler(all_file)

    # --- файл только с ошибками (ERROR+) ---
    err_file = TimedRotatingFileHandler(
        filename=log_dir / "errors.log",
        when="midnight",
        interval=1,
        backupCount=30,           # подольше храним ошибки
        encoding="utf-8",
        utc=False,
    )
    err_file.setFormatter(fmt)
    err_file.setLevel(logging.ERROR)
    root.addHandler(err_file)

    # пометили, что уже настроили
    root._logging_already_configured = True
