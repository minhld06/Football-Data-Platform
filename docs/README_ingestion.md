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
python ingest.py --full-rehash
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

## Tracking file đã ingest — vì sao chạy lại nhanh hơn khi số file tăng

Mỗi lần 1 file được ghi thành công vào `bronze.raw_documents` (mới hoặc bị skip do trùng
`content_hash`), path tương đối + mtime + size của file được ghi vào `bronze.ingested_files`.
Lần chạy sau, file có mtime/size khớp với lần trước sẽ được bỏ qua, không đọc/hash lại —
chi phí mỗi lần chạy chỉ còn tỉ lệ với số file mới/đổi, không phải tổng số file tích lũy.

Dùng `--full-rehash` để bỏ qua tracking và hash lại toàn bộ (ví dụ khi nghi ngờ ai đó sửa
tay file raw mà không đổi mtime).

## Giới hạn hiện tại / TODO
- [ ] `entity_id` hiện luôn là `NULL` — vì mỗi file hiện tại là 1 collection (nhiều trận đấu/nhiều đội trong 1 file), không phải 1 entity đơn lẻ.
- [ ] `source_url` chưa được crawler lưu lại, hiện để `NULL`.
- [ ] Chuẩn hóa `league`/`season` dựa trên whitelist cố định trong `core/metadata.py` (`LEAGUE_CODES`) — cần cập nhật thủ công khi thêm giải đấu mới.

## Validation

Script `ingestion/validate.py` kiểm tra dữ liệu trong `bronze.raw_documents`:

````powershell
python ingestion/validate.py
````

Script sẽ:
1. Đếm số bản ghi theo `source`/`entity_type`/`league`/`season`, in ra console + log vào `logs/validation.log`.
2. So với `ingestion/core/expected.py` (`EXPECTED_COMBOS`) để tìm combo bị thiếu hoàn toàn — ví dụ một nguồn không có bản ghi cho 1 season mà nguồn khác đã có dữ liệu season đó.
3. Combo có dữ liệu nhưng không khai báo trong `EXPECTED_COMBOS` được log mức INFO ("ngoài kỳ vọng"), không tính là gap — có thể do crawler được mở rộng nhưng map chưa cập nhật.

Exit code `1` nếu phát hiện gap, `0` nếu sạch (dùng được cho CI sau này).

**Giới hạn:** chỉ kiểm tra ở mức combo (source/entity_type/league/season có tồn tại hay không), không so khớp từng trận đấu/đội cụ thể giữa các nguồn — vì `entity_id` trong Bronze hiện luôn `NULL`. So khớp chi tiết hơn để dành cho tầng Silver.
````
````