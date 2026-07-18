# Thiết kế: Script validation cho Bronze (`ingestion/validate.py`)

**Ngày**: 2026-07-18
**Trạng thái**: Chờ duyệt

## Bối cảnh & vấn đề

`bronze.raw_documents` hiện không có cách nào tự động kiểm tra dữ liệu có đủ theo kỳ vọng hay không — ví dụ một nguồn ngừng crawl một giải đấu mà không ai để ý. `entity_id` luôn `NULL` (mỗi file gộp nhiều trận/đội, không phải 1 record/1 entity), nên không thể so khớp từng trận cụ thể giữa các nguồn một cách đáng tin cậy ở tầng Bronze.

## Mục tiêu

- Đếm số bản ghi trong `bronze.raw_documents` theo `source`/`entity_type`/`league`/`season`.
- Phát hiện **combo bị thiếu hoàn toàn** so với kỳ vọng (ví dụ: statbunker thiếu standings cho một season mà nguồn khác đã có).
- Không đổi schema hay logic ingest hiện có.

## Ngoài phạm vi

- So khớp từng trận đấu/đội cụ thể giữa các nguồn (cần `entity_id` chuẩn hóa — để dành cho tầng Silver/dbt).
- Gap theo thời gian thực (ví dụ: cảnh báo khi crawler không chạy quá N ngày) — không nằm trong yêu cầu ban đầu.

## Thiết kế

### 1. `ingestion/core/expected.py`

Khai báo tĩnh, season-agnostic (season đổi theo thời gian nên không hardcode):

```python
EXPECTED_COMBOS = {
    "football_data_org": {"matches": ["premier-league", "ligue-1"], "standings": ["premier-league", "ligue-1"]},
    "statbunker":         {"standings": ["premier-league"]},
    "understat":          {"standings": ["premier-league", "ligue-1"]},
}
```

### 2. `ingestion/validate.py`

1. Một query: `SELECT source, entity_type, league, season, COUNT(*) FROM bronze.raw_documents GROUP BY 1,2,3,4` (tái dùng `core/db.get_connection()`).
2. In bảng đếm ra console + log vào `logs/validation.log` (cùng pattern logger với `ingest.py`).
3. Suy ra season set theo từng `league` (union season đã thấy ở bất kỳ nguồn nào). Với mỗi `(source, entity_type, league)` trong `EXPECTED_COMBOS`, kiểm tra đã có bản ghi cho **mọi** season của league đó chưa → thiếu thì liệt kê là gap.
4. Combo có dữ liệu nhưng không có trong `EXPECTED_COMBOS` → log mức INFO ("ngoài kỳ vọng"), không tính là gap (tránh false positive khi crawler được mở rộng nhưng map chưa cập nhật).
5. Exit code `1` nếu có gap, `0` nếu sạch.

### 3. Xử lý lỗi

Lỗi kết nối DB/query lỗi → fail fast (raise, không nuốt lỗi) — đúng nguyên tắc lỗi hạ tầng của dự án.

### 4. Testing

Tách hàm thuần `find_gaps(counts, expected)` để test không cần DB thật. Thêm `ingestion/tests/test_validate.py`, theo pattern `test_tracking.py` đã có:

- Combo có trong expected, có bản ghi cho mọi season → không gap.
- Combo có trong expected, thiếu 1 season → gap.
- Combo có dữ liệu nhưng ngoài expected → không gap, chỉ log info.

## Rủi ro còn lại đã biết

- `EXPECTED_COMBOS` là khai báo thủ công, cần cập nhật khi thêm nguồn/giải đấu mới (giống `LEAGUE_CODES` trong `metadata.py`) — chấp nhận được ở quy mô Phase 1.
