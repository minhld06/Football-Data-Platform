import time
import logging
import requests
from functools import wraps
import os
import json
from pathlib import Path
from datetime import date, datetime

# ============================================================
# ROOT DIRECTORY FOR RAW DATA
# ============================================================
# Prefer reading from the RAW_DATA_DIR environment variable (set in .env).
# If not set, compute the project root from this file's location:
#   crawlers/common/utils.py -> go up 2 levels (common -> crawlers) -> project root
# This avoids hardcoding any OS-specific path, so it works correctly
# both running directly on Windows and running inside a Linux container.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = Path(os.environ.get("RAW_DATA_DIR", str(_PROJECT_ROOT / "data" / "raw")))
LOG_DIR = Path(os.environ.get("LOG_DIR", str(_PROJECT_ROOT / "logs")))


# ============================================================
# LOGGER — standard logging for the whole project
# ============================================================
def get_logger(name):
    """
    Create a logger with the standard format.
    Logs to the console (as before) and to logs/crawler.log for later review.
    Usage: logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:  # Avoid adding handlers multiple times
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_DIR / "crawler.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.setLevel(logging.INFO)

    return logger


# ============================================================
# RATE LIMITER — limits request rate
# ============================================================
class RateLimiter:
    """
    Ensures each request is spaced at least `min_delay` seconds apart.

    Usage:
        limiter = RateLimiter(min_delay=2.0)
        limiter.wait()  # Call before each request
    """
    def __init__(self, min_delay=2.0):
        self.min_delay = min_delay
        self.last_request_time = 0

    def wait(self):
        elapsed = time.time() - self.last_request_time
        remaining = self.min_delay - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self.last_request_time = time.time()


# ============================================================
# RETRY WITH EXPONENTIAL BACKOFF
# ============================================================
def retry_request(url, headers=None, max_retries=3, base_delay=1.0, timeout=10):
    """
    Sends a GET request, retrying automatically on failure.
    Each failed attempt waits twice as long as the previous one.

    Args:
        url: URL to request
        headers: HTTP headers
        max_retries: Maximum number of attempts
        base_delay: Initial wait time (seconds)

    Returns:
        response object, or None if all attempts failed
    """
    logger = get_logger(__name__)
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            
            if response.status_code == 200:
                return response
            
            # 429 = Too Many Requests, 502/503/504 = transient gateway/server errors — worth retrying
            if response.status_code in (429, 502, 503, 504):
                wait_time = base_delay * (2 ** attempt)
                logger.warning(f"Status {response.status_code}! Retrying attempt {attempt + 1}/{max_retries} after {wait_time}s...")
                time.sleep(wait_time)
                continue

            logger.error(f"Status {response.status_code} for URL: {url}")
            return None

        except requests.exceptions.ConnectionError:
            wait_time = base_delay * (2 ** attempt)
            logger.warning(f"Connection error! Retrying attempt {attempt + 1}/{max_retries} after {wait_time}s...")
            time.sleep(wait_time)

        except requests.exceptions.Timeout:
            wait_time = base_delay * (2 ** attempt)
            logger.warning(f"Timeout! Retrying attempt {attempt + 1}/{max_retries} after {wait_time}s...")
            time.sleep(wait_time)

    logger.error(f"Failed after {max_retries} attempts: {url}")
    return None

def save_raw(data, source, entity, filename, crawl_date=None):
    """
    Saves raw data using the structure:
    {RAW_DATA_DIR}/{source}/{entity}/{date}/{filename}_{HHMMSS_ffffff}.json

    Always use RAW_DATA_DIR (absolute, anchored to the project root or env var)
    instead of the relative path "data/raw/..." — because a relative path depends
    on the current working directory (CWD) when python runs, which can easily
    create a folder in the wrong place if the script is run from a subdirectory.
    """
    now = datetime.now()

    if crawl_date is None:
        crawl_date = now.date().isoformat()

    timestamp_str = now.strftime("%H%M%S_%f")

    path = RAW_DATA_DIR / source / entity / crawl_date / f"{filename}_{timestamp_str}.json"
    logger = get_logger(__name__)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"Failed to write file {path}: {e}")
        raise

    logger.info(f"Saved: {path}")
    return str(path)