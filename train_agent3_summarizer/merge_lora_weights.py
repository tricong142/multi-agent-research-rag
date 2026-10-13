import os
import shutil
from pathlib import Path
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

# ============================================================
# 1. ĐƯỜNG DẪN CHUẨN XÁC TỪ DATASET CỦA BẠN
# ============================================================
BASE_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

CRITIC_ADAPTER_PATH = Path(
    "/kaggle/input/datasets/trcng23/agent3-adapters/checkpoints/critic_qlora/final"
)
CRITIC_MERGED_PATH = Path("/kaggle/working/critic_merged")

# ============================================================
# 2. DỌN SẠCH ĐĨA TRƯỚC KHI CHẠY
# ============================================================
print("[*] Dọn dẹp các file thừa và thư mục lỗi cũ...")
os.system(f"rm -rf {CRITIC_MERGED_PATH}")
os.system("rm -rf ~/.cache/huggingface/hub/*")

print("[*] Dung lượng đĩa khả dụng hiện tại:")
os.system("df -h /kaggle/working")

# ============================================================
# 3. MERGE VÀ LƯU CRITIC
# ============================================================
print(f"\n[1/4] Đang tải base model {BASE_MODEL_NAME}...")
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_NAME,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME)

print(f"[2/4] Đang nạp adapter từ: {CRITIC_ADAPTER_PATH}...")
model_with_adapter = PeftModel.from_pretrained(base_model, str(CRITIC_ADAPTER_PATH))

print("[3/4] Đang merge adapter vào base model...")
merged_model = model_with_adapter.merge_and_unload()

# MẸO THỰC TẾ VIETTEL: Sau khi model đã merge xong trên RAM/VRAM,
# xóa ngay cache tải về của Hugging Face để lấy lại ~15GB đĩa trống!
print("[*] Giải phóng cache tải về trước khi ghi đĩa...")
os.system("rm -rf ~/.cache/huggingface/hub/*")

CRITIC_MERGED_PATH.mkdir(parents=True, exist_ok=True)
print(f"[4/4] Đang lưu model đã merge vào: {CRITIC_MERGED_PATH}...")
merged_model.save_pretrained(
    str(CRITIC_MERGED_PATH),
    safe_serialization=True,
    max_shard_size="4GB"
)
tokenizer.save_pretrained(str(CRITIC_MERGED_PATH))

print(f"\n✅ HOÀN TẤT: Đã merge thành công Critic tại {CRITIC_MERGED_PATH}")

# Giải phóng VRAM
del base_model, model_with_adapter, merged_model
torch.cuda.empty_cache()

# Kiểm tra lại dung lượng sau khi lưu xong
os.system("df -h /kaggle/working")
