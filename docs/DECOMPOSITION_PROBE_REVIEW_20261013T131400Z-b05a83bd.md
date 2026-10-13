# Đối chiếu probe v2 — 20261013T131400Z-b05a83bd

**Probe đã chạy đủ nhưng chưa đạt gate: 12/18 decomposition hợp lệ, 6 incomplete.**
Không chạy 39 ca hoặc tích hợp dựa trên lượt này. `experiment_completed=true`
chỉ xác nhận đã thử đủ 18 claim; `automated_gate_pass=false` vẫn là kết luận chất lượng.

## Bằng chứng đã đối chiếu

ZIP SHA256:
`abb5e69ef781bf9850f1b1ca1d4b877c65316d664832070f3785caa41e1c6144`.
CRC đạt; 37/37 file trong output manifest khớp hash/size, đủ toàn bộ file ZIP
trừ chính manifest. Runtime 45/45, verifier patch 28/28 và 13 frozen sources
khớp repo v2 tại thời điểm audit, trước khi sửa v3. Criteria/contract/data đúng
bản đã bàn giao. Provenance model/revision/tokenizer/settings khớp baseline ghi
nhận; không trực tiếp hash lại trọng số trên GPU trong lượt audit local.

Replay khớp 18 predictions và 29 call traces; decomposition chỉ nhận claim,
không nhận context/gold/Judge explanation. Các validation error, tổng token và
metrics được tính lại, khớp ZIP. Original output giữ nguyên tại
`research-runs/kaggle-20261013T131400Z-b05a83bd/`.

| Mục | Kết quả thực đo |
|---|---:|
| Test runtime Kaggle | 203/203 đạt |
| Setup/preflight/freeze | Đạt |
| Claim đã thử | 18/18 |
| Decomposition hợp lệ | 12/18 |
| Incomplete | 6 |
| Backend calls | 29/36 tối đa |
| Đạt ngay attempt 1 | 7 |
| Repair được gọi / repair thành công | 11 / 5 |
| Generated / prompt tokens | 1.816 / 20.092 |
| Generated tokens tối đa một call | 141, dưới cap 1.536 |
| Thời gian stage probe | 188,849 giây, chưa tính setup |
| Cost USD | Không được backend đo, null |
| Gate tự động / human review | False / pending |

Không có assessment hoặc label trong probe nên không có accuracy verifier.
Lượt này cải thiện khả năng tuân thủ contract so với v1; nó chưa chứng minh chất
lượng kiểm chứng claim/context hay công cụ số học.

## Lỗi đã xác định

Trên 29 attempts, có 12 hợp lệ và 17 lần bị validator từ chối:

| Lỗi đầu tiên được ghi mỗi attempt | Số lần |
|---|---:|
| JSON sai | 6 |
| Bỏ sót nội dung claim | 4 |
| Scope không nguyên văn | 3 |
| AND bị xem là chưa tách | 2 |
| Thiếu entity/metric | 1 |
| Quote không có trong claim | 1 |

- Ba ca `006`, `012`, `015` đều lặp lỗi `"unresolved:[]}` ở cả hai attempts.
  Repair chưa sửa cú pháp. Log chứng minh sự lặp lại; giả thuyết echo draft làm
  model sao chép lỗi là hướng thử cần đo, chưa phải kết luận nhân quả.
- Ca `004` ghép các từ không liền nhau thành metric; ca `007` đổi `Training`
  thành `training`, sau đó bỏ entity. Validator exact source làm đúng nhiệm vụ;
  repair cần chỉ rõ trường bị từ chối và yêu cầu giữ chữ hoa/thường.
- Ca `017` cho thấy validator v2 từ chối quá chặt leading AND ở đầu vế thứ hai.
  Hai quote thực tế chứa hai predicate riêng; không có AND ở giữa một predicate.
  Repair sau đó tự thêm subject vào quote, làm sai nguyên văn.
- Ca `009` hợp lệ về cấu trúc nhưng đặt `On the tested dataset` vào time, bỏ
  condition. Đây là lỗi ngữ nghĩa scope đã thấy từ output.
- Hai ca `001`, `008` dùng metric chung như `uses`, `retains`, `contained`.
  V2 cho phép predicate nên chưa thể dùng schema để kết luận toàn bộ sai; tuy
  nhiên chúng cần review liên kết với memory/accuracy/count trước khi kiểm số liệu.

## Review đủ 18 ca bằng AI

Đọc từng claim/plan/attempt. Đây là review AI để chẩn đoán, **không phải review
độc lập bằng người**, và không điền phiếu human thành pass.

| Claim ID | Kết luận review | Nội dung cần giữ/sửa |
|---|---|---|
| 001 | Cần làm rõ metric | Hai vế/số liệu giữ đủ; uses/retains chưa định danh đại lượng |
| 002 | Đạt theo review AI | Giữ accuracy 94% và entity |
| 003 | Đạt theo review AI | Giữ quan hệ study dùng human labels |
| 004 | Chưa review plan hợp lệ | Scope ghép từ không nguyên văn |
| 005 | Đạt theo review AI | All, population tasks, after compression |
| 006 | Chưa review plan hợp lệ | JSON sai; draft còn tách dataset phrase thành fragment |
| 007 | Chưa review plan hợp lệ | Sai chữ hoa/thường rồi bỏ entity |
| 008 | Cần làm rõ metric | Count 240 documents vẫn trong quote; metric quá chung |
| 009 | Sai loại scope | Dataset phải là condition |
| 010 | Đạt theo review AI | All, recall và after the revision |
| 011 | Đạt theo review AI | Some, audited population và after the patch |
| 012 | Chưa review plan hợp lệ | JSON sai; draft bỏ thời gian khỏi quote |
| 013 | Đạt theo review AI | North gateway, error rate, after calibration |
| 014 | Đạt theo review AI | All weekly trials, in May, throughput |
| 015 | Chưa review plan hợp lệ | JSON sai; draft gắn metric vào condition |
| 016 | Đạt theo review AI | Entity và tăng precision giữ nguyên; numeric chưa đo |
| 017 | Chưa review plan hợp lệ | Leading AND bị từ chối; repair quote không nguyên văn |
| 018 | Đạt theo review AI | All, low-temperature group và after update |

Chi tiết từng ca và judgments:
[review JSONL](decomposition-semantic-review-20261013T131400Z-b05a83bd.jsonl).
Số 9 đạt/2 cần sửa/1 sai/6 unreviewable là kết luận review AI cho diagnosis;
không thay gate chính thức 18/18 và human review. Đây là dữ liệu development đã thấy.

## Sửa tiếp và thứ tự nghiệm thu

Đã sửa candidate v3 riêng:

1. Cho phép leading AND ở quote thứ hai trở đi; vẫn từ chối inner AND, quote
   giả, chồng lấn và coverage thiếu. Không tự sửa nội dung quote.
2. Repair scope xác định `parts[i].scope.<field>` cần sửa; giữ kiểm tra nguyên
   văn/case. Repair JSON yêu cầu tạo lại từ input, không echo JSON hỏng.
3. Prompt phân biệt named metric, time, dataset/condition và fragment; có năm
   ví dụ tổng quát không chứa claim của probe. Code thêm guard hẹp cho explicit
   English dataset restriction; scope khác vẫn cần review ngữ nghĩa.
4. Giữ cùng 18 claim, model/revision, 2 attempts/2 calls mỗi claim, token cap và
   hard timeout. Freeze v3 mới; ZIP/criteria/notebook/source v2 được bảo tồn.

Dùng [notebook probe v3](../scripts/kaggle_decomposition_probe_v3.ipynb) theo
[hướng dẫn](DECOMPOSITION_PROBE_V3_KAGGLE.md). Chưa có inference model thật v3.
Sau probe đạt cấu trúc và review đủ mệnh đề mới chạy 39 ca; sau gate verifier
mới tích hợp, Reader, Summarizer và tám ca E2E theo yêu cầu.

Audit: [JSON](decomposition-probe-audit-20261013T131400Z-b05a83bd.json).
Source v2 trước sửa được giữ tại `research-runs/atomic-verifier-v2-source-snapshot/`.
