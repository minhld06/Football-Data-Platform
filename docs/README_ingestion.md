# Ingestion Service — Football Data Platform

Script nạp dữ liệu thô (raw JSON) từ `data/raw/` vào schema `bronze` trên PostgreSQL.

## Mục đích

- Quét toàn bộ (hoặc theo filter) file JSON trong `data/raw/{source}/{entity}/{date}/`.
- Tính `content_hash` cho từng file để đảm bảo idempotency (chạy lại nhiều lần không tạo bản ghi trùng).
- Chuẩn hóa `league`/`season` từ tên file qua whitelist (xem `core/metadata.py`).
- Upsert vào bảng `bronze.raw_documents`.

## Cấu trúc

````
ingestion/
├── ingest.py           # Entry point, điều phối toàn bộ pipeline
├── core/
│   ├── discovery.py     # Quét file, tách source/entity_type/date từ path
│   ├── hashing.py       # Đọc JSON, tính content_hash
│   ├── metadata.py      # Chuẩn hóa league/season qua whitelist
│   └── db.py            # Kết nối Postgres, upsert vào bronze
├── .env                 # Thông tin kết nối DB (KHÔNG commit lên Git)
└── requirements.txt
````

## Cài đặt

````powershell
cd ingestion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
````

Tạo file `.env` với nội dung:

````
DB_HOST=localhost
DB_PORT=5432
DB_NAME=football
DB_USER=postgres
DB_PASSWORD=<mật khẩu Postgres>
````

## Chạy

**Chạy toàn bộ (mặc định):**

````powershell
python ingest.py
````

**Chạy có filter theo nguồn và/hoặc ngày:**

````powershell
python ingest.py --source football_data_org
python ingest.py --date 2026-07-08
python ingest.py --source football_data_org --date 2026-07-08
````

Script sẽ:
1. Quét file JSON trong `data/raw/` (toàn bộ hoặc theo filter).
2. Với mỗi file: tính hash, chuẩn hóa league/season, upsert vào `bronze.raw_documents`.
3. In log số lượng record mới (`[MỚI]`) và số lượng bị bỏ qua do trùng (`[SKIP - đã tồn tại]`).

### Ví dụ output

````
2026-07-13 21:27:50 [INFO] Tìm thấy 7 file cần xử lý
2026-07-13 21:27:51 [INFO] [MỚI] football_data_org | matches | hash=06679241...
...
2026-07-13 21:27:51 [INFO] Hoàn tất: 7 record mới, 0 record bị bỏ qua (trùng).
````

## Idempotency — vì sao chạy lại nhiều lần vẫn an toàn

`content_hash` được tính từ nội dung JSON gốc (đã `sort_keys`), **không bao gồm** thời điểm ingest. Bảng `bronze.raw_documents` có `UNIQUE INDEX` trên `(source, entity_type, content_hash)`. Nếu nội dung file không đổi, hash không đổi → `ON CONFLICT DO NOTHING` sẽ tự động bỏ qua, không tạo bản ghi trùng.

Nếu nội dung file thay đổi (ví dụ crawl lại standings có cập nhật), hash sẽ khác → được insert như 1 bản ghi mới, giữ đúng tính chất **immutable** của tầng Bronze.

## Giới hạn hiện tại / TODO
- [ ] `entity_id` hiện luôn là `NULL` — vì mỗi file hiện tại là 1 collection (nhiều trận đấu/nhiều đội trong 1 file), không phải 1 entity đơn lẻ.
- [ ] `source_url` chưa được crawler lưu lại, hiện để `NULL`.
- [ ] Chuẩn hóa `league`/`season` dựa trên whitelist cố định trong `core/metadata.py` (`LEAGUE_CODES`) — cần cập nhật thủ công khi thêm giải đấu mới.
````
````