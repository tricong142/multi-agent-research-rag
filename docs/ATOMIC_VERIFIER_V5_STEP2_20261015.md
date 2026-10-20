# Bước 2 verifier v5 — probe Colab đạt cấu trúc, semantic gate chưa đạt

Ngày: 2026-10-15. Đã audit ZIP Colab run `20261015T103401Z-723b3e4a`:
**18/18 decomposition hợp lệ, 18 calls; review AI 16/18 claim đạt, hai metric
cần sửa. Chưa có human review, chưa chạy 39 ca, chưa đo false support.**

[Review đủ 18 claim/20 parts và provenance/replay](DECOMPOSITION_PROBE_REVIEW_20261015T103401Z-723b3e4a.md).

Notebook: https://www.kaggle.com/code/trcng23/atomic-verifier-v5-probe18-20261015/edit

## Đã thực hiện

1. Kiểm freeze probe local: `freeze_valid=true`, 18 claim, tối đa 36 calls.
2. Tạo notebook riêng, import artifact v5, chọn GPU T4 x2 và Internet on.
   Kaggle đã mount workspace và diagnostics. Lượt setup đầu dừng trước model
   loading tại `Overlapping source differs: research_rag/tests/test_summary_trace.py`.
3. Đối chiếu source thật trên Kaggle với manifest diagnostics, xác nhận SHA256
   `20ff80f2cfce9dad4190e1e52fe21507a9932bc91b0cf3f6318d897dbd5a40a0`.
   Builder trước đó thiếu allowed base hash của file được diagnostics cài sẵn.
   Bổ sung đúng hash, giữ assert và thêm fixture/regression giả lập file có sẵn.
   **3/3 test đóng gói đạt** sau sửa.
4. Dựng lại notebook và release manifest. Core verifier, prompt, criteria, dữ liệu,
   model revision và ngân sách v5 giữ nguyên. Có thử tiếp tục setup bằng đoạn
   code tương đương phần cuối cell 2; venv và bootstrap exit 0. Không có inference
   model được ghi nhận ở lượt này.
5. Sau đổi tên, Kaggle chuyển sang slug mới; tab URL cũ không còn đồng bộ.
   Tab canonical cho thấy **0 version**, nên thao tác Quick Save trước đó không
   được tính là đã bảo toàn output trên Kaggle. Traceback và hash quan sát được
   được ghi lại riêng trong báo cáo đóng gói.
6. Import lại tại URL canonical; tải draft ngược từ Kaggle và đối chiếu:
   **đủ ba code cell, cả ba khớp source local** (bỏ qua whitespace cuối cell).
   Payload có đúng allowed base hash mới.
7. Run All từ draft đã đối chiếu. Kaggle báo:

   ```text
   Draft Session: Fatal
   Firebase: Error (auth/internal-error).
   An error occurred starting the worker.
   ```

   Đã Refresh theo hộp lỗi Kaggle, nhưng lỗi xác thực lặp lại. Đây là lỗi
   khởi động worker trước model loading; chưa đủ thông tin để kết luận nguyên
   nhân bên trong Firebase/Kaggle. Không thay code model để che lỗi này.

## Artifact kiểm chứng

- [Notebook local đã sửa packaging](../scripts/kaggle_decomposition_probe_v5.ipynb),
  SHA256 `16c3cd235fe54e9848bc76a6b571b93dcc9e35735e9ecaca60112fd980e6da9a`.
- [Release manifest](atomic-verifier-v5-release.json).
- [Bằng chứng lỗi packaging và sửa](atomic-verifier-v5-kaggle-packaging-fix.json).
- Bản tải ngược từ Kaggle được giữ tại
  `research-runs/kaggle-step2-v5-20261015/verified-uploaded-probe.ipynb`, SHA256
  `65b81cbc1e82b983fbcdf767228a70677f12749cb290d957a8c00357baff4c48`.
  Metadata notebook khác serialization local; **code cells đã so khớp**, không
  suy ra byte toàn notebook giống nhau.
- Criteria SHA256 không đổi:
  `b110c02c404f7b91e52551d90e7605d850b12ac7ebb5a332fd292895ad27fa77`.

File sửa trong lượt này: `scripts/build_atomic_verifier_notebook.py`,
`scripts/test_atomic_notebook.py`, fixture
`scripts/fixtures/summary_trace_pre_v5.py.txt`, notebook/release manifest và tài
liệu trạng thái. Fixture lấy nguyên bytes từ ZIP diagnostics có manifest đã kiểm.

## Điều kiện chưa đạt

| Gate | Trạng thái |
| --- | --- |
| Probe model 18/18 hợp lệ | Đạt trên Colab; đã replay |
| Review đủ mệnh đề/coverage/quantifier/entity-metric/time-condition | Đã review AI 20 parts; 16/18 claim đạt, 007/008 metric quá chung |
| Human review đúng hash để admission 39 ca | Pending; không ký thay người review |
| Verifier model 39/39 nhãn đúng, zero false support/failure | Chưa chạy; false support chưa đo, không được ghi bằng 0 |
| Review đúng bằng chứng, giải thích và missing information từng ca | Pending; probe không có context/evidence assessment |

## Chuyển sang Colab theo yêu cầu

Người dùng chọn dùng GPU khác, sau đó chọn mở Colab bằng Chrome/Edge.
Colab trong trình duyệt của agent có phiên đăng nhập nhưng không tải được
trình soạn thảo: `Monaco: unable to load: Error: [object Event]`. Lỗi lặp lại
sau nút **Tải lại**, trước bước chọn accelerator. Chưa xác nhận Colab có cấp
GPU hay quota còn đủ; không suy ra lỗi quota từ lỗi editor này.

- Tạo [notebook Colab v5](../scripts/colab_decomposition_probe_v5.ipynb), bốn
  code cell, khoảng 3,1 MB. Payload có 67 file gồm source, evaluation inputs và
  tokenizer/config dùng chung. Không cần upload 7 GB workspace hoặc weights
  fine-tuned; runner `base_instruct` tải đúng revision trong criteria từ HF.
- [Builder](../scripts/build_colab_atomic_probe.py) tái sử dụng process-group
  timeout, lưu log và ZIP từ notebook Kaggle. Source/criteria/prompt/model/
  decoder/dữ liệu/ngân sách v5 không đổi. Manifest ghi hash từng file payload.
- [Test đóng gói](../scripts/test_colab_atomic_probe.py) giải nén đúng payload
  sang thư mục tạm độc lập rồi chạy **80/80 frozen regression tests** và cả hai
  chế độ `validate-only`: 18 claim/36 calls, 39 ca/312 calls. **2/2 test đóng gói
  Colab đạt**, tổng thời gian 40,946 giây. Đây là chạy local, không phải model.
- Notebook tạo venv riêng, cài runtime đã pin, kiểm CUDA và regression/freeze
  trước probe. Chỉ preflight verifier; không bao gồm FAISS/toàn bộ năm agent.
- Người dùng đã chạy Colab và gửi ZIP: setup, CUDA, 80 regression tests, hai
  validate-only và probe exit 0. Đã kiểm manifest/provenance/replay; xem báo cáo
  run ở đầu trang. Bộ 39 ca và review người còn chờ.
- CLI Colab chính thức hiện chỉ hỗ trợ Linux/macOS theo
  [README của Google](https://github.com/googlecolab/google-colab-cli).
  Ubuntu WSL có Python nhưng chưa có CLI Colab/uv; không cài thêm hay mở OAuth
  riêng trong lúc người dùng tiếp tục bằng Chrome/Edge.

Artifact/hash: [manifest Colab](atomic-verifier-v5-colab-release.json),
[validation và trạng thái](atomic-verifier-v5-colab-validation.json).

Quy trình chạy Colab đã dùng cho ZIP này:

1. Mở https://colab.research.google.com/, **Tệp → Tải sổ tay lên**, chọn
   `scripts/colab_decomposition_probe_v5.ipynb` từ workspace này.
2. **Runtime → Change runtime type → T4 GPU**, giữ chế độ miễn phí nếu có.
   Chưa có quyền mua/nâng gói compute.
3. **Run all**. Notebook chạy kiểm tra rồi probe 18 claim và tải ZIP output.
   Nếu cell lỗi, giữ log/ZIP đã tạo; không chạy đè stage cũ.
4. Giữ output trước khi dừng GPU. Kiểm manifest, provenance, replay và review
   tất cả 18 predictions theo rubric. Không dùng v4 thay cho inference v5.
5. Run này còn hai metric cần sửa. Phải sửa candidate, thêm regression và đóng
   băng phiên bản tiếp theo trước khi inference lại; không sửa predictions v5.
   Chỉ sau probe mới và human review đúng hash đạt mới chạy 39 ca. Không điền
   reviewer người hoặc các judgment `true` thay cho review thật.
