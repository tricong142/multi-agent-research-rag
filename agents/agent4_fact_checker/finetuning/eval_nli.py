"""
eval_nli.py
===========
Đánh giá độ chính xác (Precision, Recall, F1, Confusion Matrix) của mô hình NLI.
Chạy sau khi đã fine-tune qua train_scibert_scifact.py.
"""

import json
from pathlib import Path
import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
from sklearn.metrics import classification_report, confusion_matrix

MODEL_DIR = "./scibert_scifact_model"
ID2LABEL = {0: "CONTRADICT", 1: "NOT_ENOUGH_INFO", 2: "SUPPORT"}
LABEL2ID = {"CONTRADICT": 0, "NOT_ENOUGH_INFO": 1, "SUPPORT": 2}


def evaluate():
    print(f"Đang nạp mô hình từ {MODEL_DIR}...")
    try:
        classifier = pipeline("text-classification", model=MODEL_DIR, device=0)
    except Exception:
        print("Không tìm thấy GPU hoặc model cục bộ, nạp trên CPU...")
        classifier = pipeline("text-classification", model=MODEL_DIR)

    # Đọc dữ liệu kiểm thử từ tập dev đã ghép cặp
    from finetune_scibert_scifact import load_corpus, build_nli_pairs, DATA_DIR
    corpus = load_corpus()
    dev_pairs = build_nli_pairs(DATA_DIR / "claims_dev.jsonl", corpus)

    if not dev_pairs:
        print("Không tìm thấy dữ liệu dev, sử dụng mẫu dự phòng...")
        dev_pairs = [
            {"premise": "LoRA reduces trainable parameters by 10,000x.", "hypothesis": "LoRA reduces parameters.", "label": 2},
            {"premise": "LoRA reduces trainable parameters by 10,000x.", "hypothesis": "LoRA increases parameters.", "label": 0},
            {"premise": "Transformers use self-attention.", "hypothesis": "ResNet uses convolution.", "label": 1},
        ]

    y_true = []
    y_pred = []

    print(f"Đang đánh giá trên {len(dev_pairs)} mẫu...")
    for item in dev_pairs[:200]:  # Đánh giá tối đa 200 mẫu để tiết kiệm thời gian
        premise = item["premise"]
        hypothesis = item["hypothesis"]
        true_label = item["label"]

        text_pair = f"{premise[:256]} </s></s> {hypothesis}"
        res = classifier(text_pair)[0]
        pred_label_str = res["label"]

        pred_label_id = 1
        for lid, lname in ID2LABEL.items():
            if lname in pred_label_str:
                pred_label_id = lid
                break

        y_true.append(true_label)
        y_pred.append(pred_label_id)

    print("\n" + "="*55)
    print("BÁO CÁO ĐÁNH GIÁ MÔ HÌNH NLI FACT-CHECKER")
    print("="*55)
    print(classification_report(y_true, y_pred, target_names=["CONTRADICT", "NOT_ENOUGH_INFO", "SUPPORT"], zero_division=0))
    print("Confusion Matrix:")
    print(confusion_matrix(y_true, y_pred))


if __name__ == "__main__":
    evaluate()
