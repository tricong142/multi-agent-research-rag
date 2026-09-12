"""
03_summarizer/merge_lora_weights.py

CHẠY Ở: KAGGLE NOTEBOOK (cần GPU để load model, dù merge tự nó không
train gì thêm) hoặc máy có đủ RAM/VRAM để load model 7B.
    python merge_lora_weights.py

TẠI SAO CẦN MERGE:
Lúc train ta chỉ lưu adapter LoRA (vài trăm MB), khi inference production
nên merge adapter vào base model thành 1 checkpoint đầy đủ - tránh phải
load base model + adapter riêng lẻ mỗi lần khởi động service (chậm hơn,
phức tạp hơn khi serving qua vLLM/TGI).

MERGE RIÊNG 2 LẦN, KHÔNG GỘP CHUNG 1 MODEL:
Generator và Critic PHẢI là 2 checkpoint độc lập trên đĩa sau merge,
đúng theo quyết định thiết kế đã thống nhất (Critic phải đánh giá độc
lập, không share trọng số với Generator sau khi đã fine-tune riêng).
Merge chung sẽ xoá bỏ chính sự tách biệt đó.
"""

import shutil
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def merge_adapter(adapter_path: Path, output_path: Path, role_name: str):
    if not adapter_path.exists():
        print(f"[BỎ QUA] Không tìm thấy adapter {role_name} tại {adapter_path}. "
              f"Chạy train_{role_name}_qlora.py trước.")
        return

    print(f"\n=== Merge {role_name} ===")
    print(f"Đang tải base model {config.BASE_MODEL_NAME}...")
    base_model = AutoModelForCausalLM.from_pretrained(
        config.BASE_MODEL_NAME,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    tokenizer = AutoTokenizer.from_pretrained(config.BASE_MODEL_NAME)

    print(f"Đang load adapter từ {adapter_path}...")
    model_with_adapter = PeftModel.from_pretrained(base_model, str(adapter_path))

    print("Đang merge adapter vào base model...")
    merged_model = model_with_adapter.merge_and_unload()

    output_path.mkdir(parents=True, exist_ok=True)
    merged_model.save_pretrained(str(output_path), safe_serialization=True)
    tokenizer.save_pretrained(str(output_path))

    print(f"Đã lưu {role_name} merged model -> {output_path}")

    # Giải phóng VRAM ngay để merge tiếp model thứ 2 trong cùng 1 lần chạy script,
    # tránh OOM khi chạy tuần tự Generator rồi Critic trên cùng 1 GPU T4.
    del base_model, model_with_adapter, merged_model
    torch.cuda.empty_cache()


def main():
    generator_final = config.GENERATOR_ADAPTER_DIR / "final"
    critic_final = config.CRITIC_ADAPTER_DIR / "final"

    merge_adapter(generator_final, config.GENERATOR_MERGED_DIR, "generator")
    merge_adapter(critic_final, config.CRITIC_MERGED_DIR, "critic")

    print("\n=== Hoàn tất ===")
    print(f"Generator merged: {config.GENERATOR_MERGED_DIR}")
    print(f"Critic merged   : {config.CRITIC_MERGED_DIR}")
    print("\n[TIẾP THEO] node.py sẽ load 2 model merged này để thực thi vòng lặp nội bộ.")


if __name__ == "__main__":
    main()
