# Thiết kế: Theo dõi file đã ingest để tăng tốc `ingestion/ingest.py`

**Ngày**: 2026-07-17
**Trạng thái**: Chờ duyệt

## Bối cảnh & vấn đề

`ingestion/ingest.py` hiện quét lại **toàn bộ** `data/raw/**/*.json` mỗi lần chạy ([discovery.py:15](../../../ingestion/core/discovery.py)), rồi đọc + tính SHA-256 cho **từng file** ([hashing.py](../../../ingestion/core/hashing.py)) trước khi upsert vào `bronze.raw_documents` với `ON CONFLICT (source, entity_type, content_hash) DO NOTHING`.

Việc dedup ở tầng DB đã đúng và rẻ. Chi phí thật sự nằm ở việc đọc + parse JSON + hash **lại** những file đã ingest ở lần chạy trước — chi phí này tỉ lệ thuận với **tổng số file tích lũy từ trước tới giờ**, không phải với số file mới mỗi lần chạy. Khi số lượng file trong `data/raw/` tăng lên nhiều lần, thời gian chạy ingest sẽ tăng tương ứng dù phần lớn file không có gì thay đổi.

## Mục tiêu

- Giảm chi phí đọc/hash lặp lại cho các file đã ingest thành công ở lần chạy trước.
- Không thay đổi cơ chế dedup dựa trên `content_hash` đang có ở `bronze.raw_documents` (vẫn là lưới an toàn cuối cùng chống trùng nội dung).
- Giữ hành vi idempotent và triết lý xử lý lỗi hiện tại của dự án (lỗi từng file thì skip có log, không âm thầm bỏ qua vĩnh viễn).

## Ngoài phạm vi

- Không đổi cấu trúc `bronze.raw_documents` hay logic dedup theo `content_hash`.
- Không tối ưu cho quy mô hàng trăm nghìn file trở lên (ví dụ: load tracking theo batch thay vì toàn bộ) — để dành cho Phase 2 nếu cần.
- Không thay đổi cách crawler ghi file raw.

## Thiết kế

### 1. Bảng tracking mới

Migration `infra/postgres/migrations/003_bronze_ingested_files.sql`:

```sql
CREATE TABLE bronze.ingested_files (
  file_path     TEXT PRIMARY KEY,   -- path tương đối so với RAW_DIR, vd: football_data_org/matches/2026-07-10/epl.json
  source        TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  mtime         TIMESTAMPTZ NOT NULL,
  size_bytes    BIGINT NOT NULL,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- Dùng **path tương đối so với `RAW_DIR`** làm khóa chính, không dùng absolute path — vì absolute path khác nhau giữa chạy trực tiếp trên host và chạy trong container Docker (`docker compose run --rm ingestion`), nếu dùng absolute path thì đổi cách chạy sẽ khiến toàn bộ file bị coi là "mới" trở lại.
- `mtime` + `size_bytes` là fingerprint rẻ để phát hiện file có khả năng đã đổi nội dung, không thay thế `content_hash` (vẫn tính hash đầy đủ cho file được coi là mới/đổi, giữ nguyên lưới an toàn dedup ở DB).

### 2. Thay đổi luồng ingest

Trong `build_records()` ([ingest.py:33](../../../ingestion/ingest.py)), chèn bước lọc giữa `discover_files()` và vòng lặp hash:

1. `discover_files()` chạy như cũ — chỉ liệt kê path + metadata, không đọc nội dung file.
2. Load 1 lần các dòng `bronze.ingested_files` khớp với filter `--source`/`--date` hiện tại thành dict `{file_path: (mtime, size_bytes)}`.
3. Với mỗi file phát hiện được: nếu **không** bật `--full-rehash` và file đã có trong dict với `mtime` + `size_bytes` khớp chính xác → bỏ qua, không đọc/hash.
4. File còn lại (chưa từng thấy, hoặc mtime/size khác, hoặc đang chạy `--full-rehash`) → đi qua `read_and_hash()` + `parse_league_season()` như hiện tại.
5. Sau khi `upsert_record()` trả về mà **không lỗi** (dù là insert mới hay bị `ON CONFLICT DO NOTHING` bỏ qua vì trùng `content_hash`) → upsert dòng tương ứng vào `bronze.ingested_files` (`ON CONFLICT (file_path) DO UPDATE SET mtime, size_bytes, ingested_at`).

### 3. Xử lý lỗi

Giữ nguyên triết lý hiện tại của dự án — chỉ thêm quy tắc: **chỉ ghi tracking khi file đã được xử lý thành công ở tầng Bronze.**

| Tình huống | Hành vi |
|---|---|
| Lỗi đọc/parse file (`OSError`, `JSONDecodeError`, `ValueError`) | Skip + log như hiện tại ([ingest.py:43-45](../../../ingestion/ingest.py)); **không** ghi tracking → lần sau tự động thử lại |
| Hash thành công nhưng upsert Bronze lỗi (`DataError`/`IntegrityError`) | Skip + log như hiện tại ([ingest.py:99](../../../ingestion/ingest.py)); **không** ghi tracking → lần sau tự động thử lại |
| Upsert Bronze thành công (record mới hoặc bị skip do trùng `content_hash`) | Ghi/refresh tracking |

Lý do không ghi tracking khi lỗi: các lỗi này thường do dữ liệu hoặc schema, có thể tự khỏi sau khi fix (ví dụ migrate thêm cột) mà không cần file đổi mtime — nếu đánh dấu "đã xử lý" thì file lỗi sẽ bị giấu vĩnh viễn cho tới khi ai đó chạy `--full-rehash` thủ công.

### 4. CLI

Thêm flag `--full-rehash` vào `parse_args()`:

```
python ingestion/ingest.py --full-rehash
```

Khi bật: bỏ qua hoàn toàn bước lọc theo tracking table ở mục 2.3 (coi mọi file khớp `--source`/`--date` là "cần hash"), nhưng vẫn ghi/refresh tracking sau khi thành công như bình thường. Dùng thủ công khi nghi ngờ raw bị sửa tay mà mtime/size không đổi (ví dụ ai đó `touch -d` sau khi sửa nội dung) — đây là rủi ro chấp nhận được vì CLAUDE.md đã quy định "Raw data stays raw", nghĩa là raw file về nguyên tắc không nên bị mutate sau khi crawl.

### 5. Testing

Repo hiện chưa có automated test cho ingestion. Thêm `ingestion/tests/test_tracking.py` — test thuần logic cho hàm lọc file mới/đã đổi, dùng dict tracked files giả lập, không cần DB thật:

- File chưa từng có trong tracking → giữ lại (cần hash).
- File có trong tracking, mtime + size khớp → bỏ qua.
- File có trong tracking, mtime khác → giữ lại.
- File có trong tracking, mtime khớp nhưng size khác → giữ lại.
- Bật `--full-rehash` → giữ lại toàn bộ, bất kể tracking.

## Rủi ro còn lại đã biết

- Sửa file raw thủ công mà giữ nguyên cả mtime và size sẽ không bị phát hiện trừ khi chạy `--full-rehash` thủ công. Chấp nhận được vì đây là hành vi trái nguyên tắc "raw data stays raw" của dự án, không phải luồng vận hành bình thường.
- Load toàn bộ tracking table khớp filter vào memory mỗi lần chạy — đủ rẻ ở quy mô hiện tại (Phase 1), có thể cần tối ưu (batch theo `file_path IN (...)`) nếu số file tăng lên rất lớn ở Phase 2.
