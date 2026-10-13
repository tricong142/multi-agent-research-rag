"""
03_summarizer/config.py

NGUỒN CONFIG DUY NHẤT của Summarizer Agent. Mọi file khác trong thư mục
này (generate_training_data.py, train_generator_qlora.py, node.py, ...)
PHẢI import từ đây, KHÔNG được hardcode lại path/hyperparameter riêng.

CHẠY Ở ĐÂU: file này chạy được cả trên Kaggle lẫn local (không có phần
nào cần GPU/mạng) - chỉ là khai báo hằng số + đường dẫn.

LƯU Ý QUAN TRỌNG VỀ PATH:
Corpus dùng chung với Agent 1 (Retrieval) - KHÔNG tự tải/xử lý lại
dataset ai-arxiv-chunked lần 2. Nếu path CORPUS_PATH bên dưới không tồn
tại, nghĩa là bạn chưa chạy xong Bước 1 (kb_indexing) của Agent 1 -
phải chạy xong pipeline đó trước, không phải lỗi của code Agent 3 này.
"""

from pathlib import Path

# ============================================================
# PATH GỐC
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent  # train_agents/
SUMMARIZER_ROOT = Path(__file__).parent       # train_agents/03_summarizer/

# Corpus TÁI SỬ DỤNG từ Agent 1 - đường dẫn này phải khớp với
# OUTPUT_PATH trong kb_indexing/scripts/01_prepare_corpus.py
CORPUS_PATH = PROJECT_ROOT / "kb_indexing" / "data" / "corpus.jsonl"

# ============================================================
# DATA PATHS (Summarizer tự sinh, không liên quan Agent 1)
# ============================================================
DATA_DIR = SUMMARIZER_ROOT / "data"
RAW_DATA_PATH = DATA_DIR / "summarizer_sft_raw.jsonl"
VALIDATED_DATA_PATH = DATA_DIR / "summarizer_sft_validated.jsonl"
REJECTED_DATA_PATH = DATA_DIR / "summarizer_sft_rejected.jsonl"
EVAL_MANUAL_PATH = DATA_DIR / "summarizer_eval_manual.jsonl"

# ============================================================
# CHECKPOINT PATHS
# ============================================================
CHECKPOINT_DIR = SUMMARIZER_ROOT / "checkpoints"
GENERATOR_ADAPTER_DIR = CHECKPOINT_DIR / "generator_qlora"
CRITIC_ADAPTER_DIR = CHECKPOINT_DIR / "critic_qlora"
GENERATOR_MERGED_DIR = CHECKPOINT_DIR / "generator_merged"   # output của merge_lora_weights.py
CRITIC_MERGED_DIR = CHECKPOINT_DIR / "critic_merged"         # output của merge_lora_weights.py

# ============================================================
# MODEL CONFIG
# ============================================================
# Cùng base model với Agent 1 (Retrieval) để đồng bộ hạ tầng serving -
# không có lý do kỹ thuật bắt buộc phải khác, và dùng chung giúp giảm
# số lượng base model phải load khi triển khai nhiều agent cùng lúc
# (có thể share base weights, chỉ swap LoRA adapter).
BASE_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

# ============================================================
# LORA HYPERPARAMETERS (dùng chung cho cả generator và critic,
# có thể override riêng nếu 1 trong 2 cần rank khác sau khi eval)
# ============================================================
LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

# ============================================================
# TRAINING HYPERPARAMETERS
# ============================================================
NUM_TRAIN_EPOCHS = 3
PER_DEVICE_TRAIN_BATCH_SIZE = 2
GRADIENT_ACCUMULATION_STEPS = 8   # effective batch size = 16
LEARNING_RATE = 2e-4
MAX_SEQ_LENGTH = 1536              # dài hơn Retrieval Agent (1024) vì context+answer+evidence dài hơn
EVAL_STEPS = 50
SAVE_STEPS = 50
SAVE_TOTAL_LIMIT = 3

# ============================================================
# INNER LOOP (node.py) - đúng theo sơ đồ: "vòng lặp nội bộ ≤N"
# ============================================================
MAX_INTERNAL_RETRY = 3  # KHÁC HOÀN TOÀN retry_count của Orchestrator tầng ngoài
                         # (xem lại phần "Lưu ý kỹ thuật" đã thống nhất ở Bước 1)

CRITIC_ACTIONS = ["rewrite", "request_more_context", "lower_confidence"]

# ============================================================
# SYNTHETIC DATA GENERATION
# ============================================================
OPENAI_MODEL_FOR_DATA_GEN = "gpt-4o"
N_SAMPLES_TO_GENERATE = 800   # số mẫu (context, question, answer, evidence) cần sinh
MIN_CHUNK_LENGTH_FOR_QA = 200  # chunk quá ngắn khó sinh câu hỏi có ý nghĩa, bỏ qua

# ============================================================
# EVAL THRESHOLDS - ngưỡng tối thiểu để coi model "dùng được"
# trước khi ráp vào LangGraph (không phải luật cứng, điều chỉnh theo
# yêu cầu thực tế dự án, nhưng PHẢI có ngưỡng, không để mơ hồ)
# ============================================================
MIN_GROUNDING_RATE = 0.80     # % câu trả lời của generator có evidence khớp thật trong context
MIN_CRITIC_PRECISION = 0.75   # % lần critic báo "không hỗ trợ" là đúng thật
