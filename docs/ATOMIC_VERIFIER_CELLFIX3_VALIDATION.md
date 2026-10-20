# Candidate cellfix3 — chuẩn bị chạy lại assessment-smoke

Đã sửa candidate từ đúng source của ZIP cellfix2 `20261017T085227Z-e0a1ba82`; giữ nguyên v8 phát hành, source/predictions/ZIP cellfix2 để replay.
Candidate nằm trong workspace thử nghiệm riêng; chưa đưa vào serving hoặc tích hợp Reader/Summarizer.

**Thay đổi**

- Validator và decoder dùng chung kiểm tra target và binding từng numeric record.
- Atomic target được nhận dạng bằng span entity nguyên văn trong context: chỉ một observation cho target đó; nhiều câu bằng chứng và nhiều quantity nằm trong observation này. Member trùng hoặc baseline ngoài target bị từ chối vào repair. Không tự xóa observation mâu thuẫn.
- Target không xuất hiện nguyên văn chưa thể lập nhãn atomic quyết định; alias/coreference không được suy đoán. Có guard cho measurement của một named target khác cùng prefix, kể cả khi model điền đúng member nhưng mượn số liệu của đối tượng khác.
- Numeric record phải gắn right operand đúng metric/object của left requirement. Bộ lọc decoder loại cặp lệch object/metric và quantity chỉ xuất hiện ở vị trí bị phủ định. Nếu context có measurement thay thế phù hợp, lỗi binding được đưa vào repair trong ngân sách cũ. Thật sự thiếu measurement vẫn là unknown hợp lệ.
- Phép kiểm value có thể dùng vế measurement nguyên văn độc lập thay cho cả câu có phủ định về metric khác. Chỉ tách khi đủ điều kiện hữu hạn; giữ modality, phủ định rộng, phủ định phía trước và phủ định quy chiếu về câu trước ở trạng thái unknown. Có ca kiểm tra với memory/accuracy, pressure/temperature và cost/latency.
- Mẫu explicit quantity denial chấp nhận một cụm metric ngắn có từ trong claim giữa observed quantity và “not”, như observed-percent + accuracy + not + claimed-percent. Vẫn giữ các guard cho threshold, claim phủ định và câu giả định; không tự chuyển đổi đơn vị.

Các quy tắc này không thay thế suy luận ngữ nghĩa hoặc việc kiểm bằng chứng đầy đủ. Một scope entity nghèo thông tin, alias, quan hệ đồng tham chiếu, phạm vi thời gian phức tạp hoặc evidence bị model bỏ qua vẫn cần đánh giá riêng.

**Kiểm tra local**

- 153 regression test đạt, trong đó 18 test mới. Bao gồm token filter LMFE thật, trace cellfix2 đã quan sát, câu mới, nhiều quantity, named property, quantifier, scope, repair/exhaustion và deadline.
- Validate-only cho probe18, smoke12 và full39 đạt. Đây là kiểm tra freeze/cấu hình, không phải inference trên các bộ này.
- Model/revision, seed, tokenizer, dataset, budget và gate giữ nguyên. Per case: 8 call, 2 attempt/stage, 1.536 generated token/call, 180 giây. Smoke tối đa 96 call; full39 tối đa 312 call.
- Giữ được flag `smoke_passed=False` và gọi download khi mô phỏng smoke trượt. Phép mô phỏng này chỉ kiểm vòng đời cell; không được tính là kết quả Qwen.
- Hai fixture cũ được sửa có chủ đích theo contract chặt hơn: decoder phải từ chối hai member khác nhau cho một atomic target; binding sai có bằng chứng thay thế phải vào repair. Không thay gold hoặc hạ gate.

Hash, log và đường dẫn candidate chính xác được ghi trong `atomic-verifier-cellfix3-validation.json` cùng thư mục.

Cell được cập nhật bước chọn parent sau lỗi assertion hash. Bản cũ lưu parent trước khi xác minh, nên cache sai có thể tồn tại qua lần chạy lại. Bản sửa ưu tiên nguồn hiện tại/cache đã xác minh hoặc tìm workspace cellfix2 lân cận, kiểm hash criteria, fingerprint manifest đã audit và đủ 75 file trước khi lưu parent. Tám test startup đã đạt, gồm cache/root cũ, chạy lại, source bị sửa và manifest không hợp lệ. Source delta của verifier không đổi; bằng chứng hash và phạm vi sửa nằm trong `atomic-verifier-cellfix3-parent-selection-fix.json`. Chưa có hash thực tế của source Colab trong traceback người dùng gửi, nên không khẳng định một nguyên nhân cụ thể tại runtime.

**Phần chưa hoàn thành qua môi trường hiện tại**

Chưa chạy inference Qwen/T4 cho candidate mới. Local dùng PyTorch `2.6.0+cpu`, `cuda_available=false`, không có CUDA device; công cụ trình duyệt không thấy tab Chrome/Edge/Colab đang truy cập được.
Không ghi nhận 12/12 smoke, 18/18 probe, human review hoặc zero false support trên full39 cho cellfix3.
Các câu mới ở regression đã dùng phát triển, không phải tập held-out. Cần bộ đánh giá mới tách riêng sau khi chốt candidate.

**Chạy tiếp trên Colab T4**

1. Giữ session vừa tạo ZIP cellfix2 trên; cần còn `root`, `out`, `env`, `python`, `manifest`, `run`, `bundle`. Cell tìm source có SHA criteria cha `a31549bda8776f6a566689c59378e5c47092faf6000d4597ef7ab82fdafa197b` và kiểm đủ đầu vào trước khi sửa bản sao. Cache parent sai không còn được dùng mặc định. Nếu nguồn đã audit không còn, cell dừng và in root/hash thực tế; không thay hash bằng một giá trị bất kỳ để đi tiếp.
2. Mở `scripts/colab_v8_assessment_smoke_cellfix3.py`, sao chép **toàn bộ nội dung**, thay cell assessment-smoke hiện tại rồi chạy đúng một cell này. File tự chứa patch và regression; không upload thêm module hay dựng notebook khác.
3. Cell tạo workspace/output mới, chạy regression và ba validate-only, kiểm CUDA rồi chạy smoke thật bằng runner cũ. Giữ nguyên `HF_HOME` để dùng lại model cache; không thay dependency.
4. Lấy ZIP mới tên `output-cellfix3-<run_id>.zip`. ZIP có input manifest, provenance, log và patch contents để audit/replay. Cell kết thúc không đồng nghĩa smoke đã đạt: chỉ `code==0` và `automated_gate_pass=true` mới đặt `smoke_passed=True`.
5. Nếu smoke trượt, dừng trước probe/full39. Nếu đạt, audit ZIP trước; probe18/human review mới vẫn phải gắn đúng candidate trước full39. Bộ 39 cần báo riêng nhãn đúng, false support, incomplete và gold-support rejection.

Không có patch riêng cho ID claim và không sửa predictions để tạo điểm đạt.
