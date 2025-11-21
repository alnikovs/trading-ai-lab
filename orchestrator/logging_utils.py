import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(logs_dir: Path, logger_name: str = "orchestrator") -> logging.Logger:
    logger = logging.getLogger(logger_name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = logging.Formatter(log_format)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "orchestrator.log"
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info(f"File logging initialized: {log_file}")
    except Exception as e:
        print(f"[WARNING] Failed to initialize file logging: {e}")
        print("[WARNING] Continuing with console logging only")
    
    return logger

