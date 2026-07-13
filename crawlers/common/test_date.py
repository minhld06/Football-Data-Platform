from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def parse_to_utc(value):
    if not value:
        return None
    value = str(value).strip()

    if value.endswith("Z"):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)

    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=VN_TZ).astimezone(timezone.utc)
    except ValueError:
        pass

    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"]:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=VN_TZ).astimezone(timezone.utc)
        except ValueError:
            continue

    raise ValueError(f"Không parse được datetime: {value}")


def to_vietnam_display(dt_utc):
    if dt_utc is None:
        return None
    if dt_utc.tzinfo is None:
        raise ValueError("dt_utc phải là datetime aware (có tzinfo), không được naive")
    return dt_utc.astimezone(VN_TZ)


# ============================================================
# TEST — tự chạy và tự đọc kết quả trước khi hỏi mình đúng/sai
# ============================================================
if __name__ == "__main__":
    print("=== Test 1: ISO UTC với Z (football-data.org) ===")
    v1 = "2025-08-15T19:00:00Z"
    r1 = parse_to_utc(v1)
    print(f"Input : {v1}")
    print(f"UTC   : {r1}")
    print(f"VN    : {to_vietnam_display(r1)}")
    print()

    print("=== Test 2: Simple datetime, giả định giờ VN (statbunker) ===")
    v2 = "2025-08-15 19:00:00"
    r2 = parse_to_utc(v2)
    print(f"Input : {v2}")
    print(f"UTC   : {r2}")
    print(f"VN    : {to_vietnam_display(r2)}")
    print()

    print("=== Test 3: Rỗng / None ===")
    print(f"parse_to_utc('')   -> {parse_to_utc('')}")
    print(f"parse_to_utc(None) -> {parse_to_utc(None)}")
    print()

    print("=== Test 4: ISO có offset khác 0 (kiểm tra convert đúng chưa) ===")
    v4 = "2025-08-15T19:00:00+03:00"
    r4 = parse_to_utc(v4)
    print(f"Input : {v4}")
    print(f"UTC   : {r4}")
    print(f"VN    : {to_vietnam_display(r4)}")