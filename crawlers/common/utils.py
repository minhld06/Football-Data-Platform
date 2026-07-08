import time
import logging
import requests
from functools import wraps
import os
import json
from datetime import date

# ============================================================
# LOGGER — ghi log chuẩn cho toàn bộ project
# ============================================================
def get_logger(name):
    """
    Tạo logger với format chuẩn.
    Dùng: logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:  # Tránh thêm handler nhiều lần
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger


# ============================================================
# RATE LIMITER — giới hạn tốc độ request
# ============================================================
class RateLimiter:
    """
    Đảm bảo mỗi request cách nhau ít nhất `min_delay` giây.
    
    Dùng:
        limiter = RateLimiter(min_delay=2.0)
        limiter.wait()  # Gọi trước mỗi request
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
# RETRY VỚI EXPONENTIAL BACKOFF
# ============================================================
def retry_request(url, headers=None, max_retries=3, base_delay=1.0, timeout=10):
    """
    Gửi GET request, tự động thử lại nếu thất bại.
    Mỗi lần thất bại chờ lâu gấp đôi lần trước.
    
    Args:
        url: URL cần request
        headers: HTTP headers
        max_retries: Số lần thử tối đa
        base_delay: Thời gian chờ ban đầu (giây)
    
    Returns:
        response object hoặc None nếu thất bại hết
    """
    logger = get_logger(__name__)
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            
            if response.status_code == 200:
                return response
            
            # 429 = Too Many Requests — chờ lâu hơn
            if response.status_code == 429:
                wait_time = base_delay * (2 ** attempt)
                logger.warning(f"Rate limited! Chờ {wait_time}s rồi thử lại...")
                time.sleep(wait_time)
                continue
                
            logger.error(f"Status {response.status_code} cho URL: {url}")
            return None

        except requests.exceptions.ConnectionError:
            wait_time = base_delay * (2 ** attempt)
            logger.warning(f"Lỗi kết nối! Thử lại lần {attempt + 1}/{max_retries} sau {wait_time}s...")
            time.sleep(wait_time)

        except requests.exceptions.Timeout:
            logger.error(f"Timeout cho URL: {url}")
            return None

    logger.error(f"Thất bại sau {max_retries} lần thử: {url}")
    return None

def save_raw(data, source, entity, filename, crawl_date=None):
    """
    Lưu raw data theo cấu trúc:
    data/raw/{source}/{entity}/{date}/{filename}.json
    """
    if crawl_date is None:
        crawl_date = date.today().isoformat()

    path = f"data/raw/{source}/{entity}/{crawl_date}/{filename}.json"

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Đã lưu: {path}")
    return path