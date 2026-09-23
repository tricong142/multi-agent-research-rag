# Đẩy Agent Writer lên nhánh `agent_writer_5`

Chạy bằng PowerShell. Cài Git và Git LFS trước. Thay đường dẫn nguồn cho phù hợp
máy của bạn. Ví dụ này tải nhánh có sẵn, chép toàn bộ thư mục học tập và đẩy
commit mới; không đẩy ZIP hoặc các bản vá cũ.

```powershell
$source = 'C:\Users\dellcuatri142\Downloads\AI ENGINEER\writer_agent_v8_study'
$checkout = 'C:\Users\dellcuatri142\Downloads\multi-agent-research-rag'

git clone --branch agent_writer_5 --single-branch https://github.com/tricong142/multi-agent-research-rag.git $checkout
Set-Location $checkout
git lfs install --local
git status --short --branch

Copy-Item -LiteralPath $source -Destination (Join-Path $checkout 'writer_agent_v8_study') -Recurse
git lfs track 'writer_agent_v8_study/05_writer/checkpoints/writer_qlora/adapter_model.safetensors'
git lfs track 'writer_agent_v8_study/05_writer/data/writer_sft_raw.jsonl'
git lfs track 'writer_agent_v8_study/05_writer/data/writer_sft_validated.jsonl'

git add .gitattributes writer_agent_v8_study
git lfs ls-files
git -c core.whitespace=cr-at-eol diff --cached --check
git diff --cached --stat
git commit -m 'Add Agent Writer v8 study package'
git push origin agent_writer_5
git status --short --branch
```

Nếu checkout đã tồn tại, dùng `Set-Location $checkout`, rồi `git pull --ff-only
origin agent_writer_5` trước khi `Copy-Item`. Nếu thư mục đích đã tồn tại,
kiểm tra các thay đổi của bạn trước khi cập nhật; tránh chép đè mù quáng.
GitHub yêu cầu đăng nhập bằng credential manager, token hoặc SSH tùy cấu hình.
Sau khi clone ở máy khác, chạy `git lfs pull` nếu ba file lớn chỉ là LFS pointer.

Đọc `writer_agent_v8_study/BAT_DAU_O_DAY.md` để chạy smoke check và hiểu giới
hạn của metrics. Adapter cần base model Qwen riêng để inference.
