# Sửa lỗi cell 2 verifier — 2026-10-13

## Kết luận từ ZIP

`rag-validation-20261013T102527Z-d29489cf.zip` đúng CRC và 18 file trong output
manifest đúng size/hash. Venv, bootstrap, torch, serving, pip-check và freeze
đều exit 0. Contract-tests chạy 194 tests, có một error, không có failure.

Test lỗi:
`test_notebook_compiles_and_embeds_all_frozen_sources_and_unique_run_id`.
Nó mở `scripts/kaggle_atomic_verifier_v1.ipynb` dưới workspace `/tmp` của
Kaggle và nhận FileNotFoundError. Notebook chạy ở kernel; payload chỉ đưa code,
dữ liệu và tests vào workspace runtime, không chứa chính notebook đó.

Đây là lỗi đóng gói trong notebook bàn giao. Kiểm thử local trước đó đạt vì
repo local có file notebook; thiếu kiểm thử workspace sau đóng gói. Lượt ZIP
này dừng trước preflight/freeze check và inference atomic candidate.

## Đã sửa

- Chuyển test notebook từ `research_rag/tests/test_atomic_experiment.py` sang
  `scripts/test_atomic_notebook.py`, chạy local trước bàn giao. Test này vẫn
  kiểm ba cells, payload/source hashes, UUID và các thiết lập timeout/setup.
- Giữ 11 tests runtime experiment trên Kaggle, giữ lệnh discover toàn bộ
  `research_rag/tests` và yêu cầu exit 0 trước bước tiếp theo.
- Bổ sung test dựng workspace từ payload, không có thư mục scripts: khám phá
  đủ 11 tests runtime và chạy kiểm frozen source/data. Các tests hành vi runtime
  được chạy đủ trong bộ regression local.
- Tạo criteria `atomic-verifier-v1-setup2-20261013` trước inference. Chỉ hai
  source đóng băng đổi: vị trí test và default criteria path của runner.
  Model, prompts, dữ liệu/gold, contract, baseline, budget và quality gates giữ
  nguyên. File criteria v1 gốc được bảo tồn; snapshot giữ sáu artifact gốc.
- Tạo lại notebook; setup chỉ in hoàn tất sau cả test/preflight/freeze check.
  Khi stage setup thất bại, notebook in phần cuối stderr để thấy traceback.

## Kiểm chứng

65/65 tests local đạt, gồm 11 tests runtime experiment và ba tests đóng gói.
13 source frozen và 13 file v3 khớp hash. Payload candidate 27 file khớp repo.
Đây là kiểm thử code bằng backend giả lập; chưa chạy bản setup2 trên Kaggle.

- [Báo cáo có hash](atomic-verifier-cell2-fix-20261013.json).
- [Log kiểm thử](atomic-verifier-cell2-fix-tests.log).
- [Snapshot trước sửa](../research-runs/atomic-verifier-setup-v1-20261013/snapshot-manifest.json).
- [Stderr Kaggle gốc](../research-runs/kaggle-20261013T102527Z-d29489cf/contract-tests.stderr.log).

SHA256 notebook mới:
`dae74cb08d6f83ad94d7dec073f7f509b93c58eb58bee975cfc2b4092cff083c`.

## Chạy bản sửa

1. Giữ ZIP lỗi làm bằng chứng. Tạo notebook Kaggle mới và import
   [kaggle_atomic_verifier_v1.ipynb](../scripts/kaggle_atomic_verifier_v1.ipynb).
   Markdown đầu notebook phải ghi **Atomic verifier v1 setup2**.
2. Bật GPU T4 và Internet; chạy cell 1 rồi cell 2 một lần.
3. Chỉ chạy cell 3 khi cell 2 có dòng:

   ```text
   SETUP COMPLETE: atomic-verifier-v1-setup2-20261013; runtime tests, preflight and freeze check passed
   ```

   `contract-tests`, `preflight`, `atomic-freeze-check` phải đều completed với
   exit_code 0. Nếu cell 2 vẫn lỗi, giữ ZIP mới; không bỏ test hoặc sửa status
   để chạy cell 3.
4. Sau cell 3, Save Version WITH Output, tải ZIP ở đường dẫn được in, dừng GPU
   rồi gửi ZIP để đối chiếu chất lượng verifier.

Gate model thật và human review còn pending. Chưa chuyển sang bước 4.
