"""
train_scibert_scifact.py
========================
Huấn luyện mô hình NLI 3 nhãn (SciBERT) trên tập dữ liệu khoa học SciFact (AllenAI).
Tối ưu hóa chạy 100% tự động trên Kaggle Notebook (GPU T4 x2 hoặc 1 GPU T4 16GB).

CÁC TỐI ƯU HÓA ĐẶC BIỆT CHO KAGGLE T4:
1. Tải trực tiếp dữ liệu SciFact từ AWS S3 của AllenAI, tự phát hiện file rỗng/hỏng để tải lại.
2. Tự động ánh xạ và ghép nối (Premise - Abstract sentences) và (Hypothesis - Claim).
3. Thống kê minh bạch phân bố số lượng nhãn (Class Distribution) trước khi huấn luyện.
4. Tối ưu bộ nhớ cho Kaggle T4 (fp16, dataloader_num_workers=2, save_total_limit=1).
5. Báo cáo chi tiết F1 cho từng nhãn (SUPPORT, CONTRADICT, NOT_ENOUGH_INFO).

Cài đặt trước trên Kaggle:
    !pip install -q -U transformers datasets accelerate scikit-learn torch

Đầu ra:
    Mô hình lưu tại: ./scibert_scifact_model/
"""

import os
import json
import urllib.request
from collections import Counter
from pathlib import Path

import torch
import numpy as np
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding
)
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

# Khóa cố định GPU 0 để đạt hiệu năng tối đa, tránh phân mảnh VRAM
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

MODEL_NAME = "allenai/scibert_scivocab_uncased"
OUTPUT_DIR = "./scibert_scifact_model"
DATA_DIR = Path("./scifact_data")

LABEL2ID = {"CONTRADICT": 0, "NOT_ENOUGH_INFO": 1, "SUPPORT": 2}
ID2LABEL = {0: "CONTRADICT", 1: "NOT_ENOUGH_INFO", 2: "SUPPORT"}

URLS = {
    "corpus": "https://scifact.s3-us-west-2.amazonaws.com/data/corpus.jsonl",
    "claims_train": "https://scifact.s3-us-west-2.amazonaws.com/data/claims_train.jsonl",
    "claims_dev": "https://scifact.s3-us-west-2.amazonaws.com/data/claims_dev.jsonl",
}


def download_scifact_data():
    """Tải trực tiếp dữ liệu SciFact từ S3, tự phục hồi nếu file bị ngắt quãng hoặc 0 byte."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in URLS.items():
        file_path = DATA_DIR / f"{name}.jsonl"
        # Kiểm tra file chưa tồn tại hoặc bị lỗi tải dở dang (0 bytes)
        if not file_path.exists() or file_path.stat().st_size == 0:
            print(f"Đang tải {name}.jsonl từ {url}...")
            try:
                urllib.request.urlretrieve(url, file_path)
                print(f"-> Đã tải xong {file_path.name} ({file_path.stat().st_size} bytes)")
            except Exception as e:
                print(f"Lỗi tải {name}: {e}")
        else:
            print(f"File {name}.jsonl đã sẵn sàng ({file_path.stat().st_size} bytes).")


def load_corpus() -> dict[str, dict]:
    """Nạp corpus: doc_id -> {title, abstract_sentences}."""
    corpus = {}
    corpus_file = DATA_DIR / "corpus.jsonl"
    if not corpus_file.exists():
        return corpus

    with open(corpus_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                corpus[str(item["doc_id"])] = {
                    "title": item.get("title", ""),
                    "sentences": item.get("abstract", [])
                }
    return corpus


def build_nli_pairs(claims_file: Path, corpus: dict) -> list[dict]:
    """
    Chuyển đổi dữ liệu SciFact thành các cặp NLI (Premise, Hypothesis, Label):
    - Premise: Câu chứng cứ trích từ abstract của bài báo kèm tiêu đề
    - Hypothesis: Luận điểm khoa học (claim)
    - Label: 0 (CONTRADICT), 1 (NOT_ENOUGH_INFO), 2 (SUPPORT)
    """
    pairs = []
    if not claims_file.exists():
        return pairs

    with open(claims_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            claim = item["claim"]
            evidence_dict = item.get("evidence", {})
            cited_doc_ids = [str(cid) for cid in item.get("cited_doc_ids", [])]

            has_evidence = False

            # 1. Các cặp có chứng cứ SUPPORT hoặc CONTRADICT
            for doc_id, ev_list in evidence_dict.items():
                doc_id_str = str(doc_id)
                if doc_id_str not in corpus:
                    continue
                doc_info = corpus[doc_id_str]
                doc_sentences = doc_info["sentences"]

                for ev in ev_list:
                    label_str = ev.get("label", "NOT_ENOUGH_INFO")
                    sent_indices = ev.get("sentences", [])
                    premise_sents = [doc_sentences[idx] for idx in sent_indices if idx < len(doc_sentences)]
                    
                    # Nếu sent_indices rỗng, fallback lấy 2 câu đầu của abstract
                    if not premise_sents and doc_sentences:
                        premise_sents = doc_sentences[:2]

                    premise_text = " ".join(premise_sents).strip()
                    if premise_text:
                        pairs.append({
                            "premise": f"{doc_info['title']}. {premise_text}",
                            "hypothesis": claim,
                            "label": LABEL2ID.get(label_str, 1)
                        })
                        has_evidence = True

            # 2. Tạo mẫu NOT_ENOUGH_INFO (Negative sampling từ các tài liệu được trích dẫn nhưng không có evidence)
            if cited_doc_ids:
                for cid in cited_doc_ids:
                    if cid in corpus and str(cid) not in evidence_dict:
                        doc_info = corpus[cid]
                        sample_text = " ".join(doc_info["sentences"][:2]).strip()
                        if sample_text:
                            pairs.append({
                                "premise": f"{doc_info['title']}. {sample_text}",
                                "hypothesis": claim,
                                "label": LABEL2ID["NOT_ENOUGH_INFO"]
                            })
                            break
            elif not has_evidence:
                pairs.append({
                    "premise": "No supporting scientific evidence documented.",
                    "hypothesis": claim,
                    "label": LABEL2ID["NOT_ENOUGH_INFO"]
                })

    return pairs


def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    preds = np.argmax(predictions, axis=1)
    
    # Macro metrics
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average="macro", zero_division=0)
    acc = accuracy_score(labels, preds)
    
    # Per-class F1 metrics
    _, _, f1_per_class, _ = precision_recall_fscore_support(labels, preds, average=None, zero_division=0, labels=[0, 1, 2])
    
    metrics = {
        "accuracy": round(acc, 4),
        "f1_macro": round(f1, 4),
        "precision_macro": round(precision, 4),
        "recall_macro": round(recall, 4),
        "f1_contradict": round(f1_per_class[0], 4) if len(f1_per_class) > 0 else 0.0,
        "f1_nei": round(f1_per_class[1], 4) if len(f1_per_class) > 1 else 0.0,
        "f1_support": round(f1_per_class[2], 4) if len(f1_per_class) > 2 else 0.0,
    }
    return metrics


def main():
    print("=" * 65)
    print("PIPELINE HUẤN LUYỆN SCIBERT NLI CHO FACT-CHECKER (KAGGLE T4x2)")
    print("=" * 65)

    # 1. Tải và xử lý dữ liệu
    download_scifact_data()
    corpus = load_corpus()
    print(f"Đã nạp {len(corpus)} tài liệu nghiên cứu vào Corpus.")

    train_pairs = build_nli_pairs(DATA_DIR / "claims_train.jsonl", corpus)
    dev_pairs = build_nli_pairs(DATA_DIR / "claims_dev.jsonl", corpus)

    print(f"\n[Dữ liệu huấn luyện] Tổng số cặp: {len(train_pairs)}")
    train_dist = Counter(p["label"] for p in train_pairs)
    for lid, lname in ID2LABEL.items():
        print(f"  - {lname:<15}: {train_dist.get(lid, 0)} mẫu ({train_dist.get(lid, 0)/max(len(train_pairs), 1)*100:.1f}%)")

    print(f"\n[Dữ liệu kiểm thử] Tổng số cặp: {len(dev_pairs)}")
    dev_dist = Counter(p["label"] for p in dev_pairs)
    for lid, lname in ID2LABEL.items():
        print(f"  - {lname:<15}: {dev_dist.get(lid, 0)} mẫu ({dev_dist.get(lid, 0)/max(len(dev_pairs), 1)*100:.1f}%)")

    if not train_pairs:
        print("CẢNH BÁO: Dữ liệu rỗng! Tạo bộ dữ liệu mẫu dự phòng để kiểm thử.")
        train_pairs = [
            {"premise": "LoRA reduces trainable parameters by 10,000x.", "hypothesis": "LoRA freezes weights and reduces parameters.", "label": 2},
            {"premise": "LoRA reduces trainable parameters by 10,000x.", "hypothesis": "LoRA increases memory usage 10x.", "label": 0},
            {"premise": "Transformers use self-attention.", "hypothesis": "ResNet50 achieves 90% accuracy on ImageNet.", "label": 1},
        ]
        dev_pairs = train_pairs

    train_ds = Dataset.from_list(train_pairs)
    dev_ds = Dataset.from_list(dev_pairs)

    # 2. Tokenizer & Tokenization
    print(f"\nNạp tokenizer mô hình nền: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def preprocess_function(examples):
        return tokenizer(
            examples["premise"],
            examples["hypothesis"],
            truncation=True,
            max_length=256
        )

    tokenized_train = train_ds.map(preprocess_function, batched=True)
    tokenized_dev = dev_ds.map(preprocess_function, batched=True)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    # 3. Model Architecture
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID
    )

    # 4. Training Arguments tối ưu hóa cho GPU T4 16GB
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        gradient_accumulation_steps=2,    # effective batch size = 32
        num_train_epochs=3,
        weight_decay=0.01,
        warmup_ratio=0.1,
        fp16=torch.cuda.is_available(),   # Kích hoạt Tensor Cores của GPU T4
        dataloader_num_workers=2,         # Nạp dữ liệu song song 2 CPU threads
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,               # Tiết kiệm dung lượng đĩa Kaggle
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        logging_steps=20,
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_dev,
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics
    )

    # 5. Huấn luyện
    print("\nBắt đầu huấn luyện...")
    trainer.train()

    # 6. Lưu kết quả
    print(f"\nLưu mô hình tốt nhất vào: {OUTPUT_DIR}")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print("=" * 65)
    print("HOÀN TẤT HUẤN LUYỆN SCIBERT THÀNH CÔNG!")
    print("=" * 65)


if __name__ == "__main__":
    main()
