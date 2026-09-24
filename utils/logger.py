import logging
import sys

def setup_logger(name: str = "MultiAgentRAG", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        if sys.platform == "win32":
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

logger = setup_logger()
