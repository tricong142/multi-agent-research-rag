"""
01_train_layoutlmv3.py
=========================
Fine-tune LayoutLMv3ForTokenClassification tren dataset DocLayNet da xu ly
o 01_process_doclaynet.py (buoc tai/xu ly du lieu, chay truoc file nay).
Chay tren Kaggle Notebook (GPU T4).

INPUT: thu muc dataset da luu boi save_to_disk(), gom 3 split (train/
validation/test). Schema THAT (da xac nhan qua chay thu, khong bia dat):
    words              : list[str]   - moi phan tu la CA MOT DONG text
    bboxes_normalized  : list[[x0,y0,x1,y1]] - da chuan hoa ve thang 0-1000
    ner_tags           : list[int]   - id cua 11 lop DocLayNet
    image              : PIL Image (1025x1025)

Neu dataset dang nam san trong CUNG session Kaggle vua chay xong buoc xu
ly: giu nguyen INPUT_DIR mac dinh ben duoi.
Neu ban tai file zip ve roi upload lai thanh 1 Kaggle Dataset MOI cho
notebook train nay (notebook khac session): doi INPUT_DIR thanh duong dan
trong /kaggle/input/<ten-dataset-ban-dat>/...

Cai dat truoc (Kaggle thuong co san phan lon, chi can them neu thieu):
    !pip install -q -U transformers accelerate scikit-learn

GHI CHU VE PHIEN BAN transformers: tham so "eval_strategy" trong
TrainingArguments duoc doi ten tu "evaluation_strategy" ke tu transformers
4.41+. Neu ban gap loi ve tham so nay, doi ten cho khop voi phien ban dang
cai (kiem tra bang `import transformers; print(transformers.__version__)`).
"""

import os
import json
import numpy as np
from datasets import load_from_disk, DatasetDict
from transformers import (
    LayoutLMv3Processor,
    LayoutLMv3ForTokenClassification,
    TrainingArguments,
    Trainer,
)
from sklearn.metrics import precision_recall_fscore_support, accuracy_score

# ---------------------------------------------------------------------------
# CAU HINH
# ---------------------------------------------------------------------------
INPUT_DIR = "/kaggle/working/doclaynet_processed"
OUTPUT_MODEL_DIR = "/kaggle/working/layoutlmv3_doclaynet_model"
BASE_MODEL = "microsoft/layoutlmv3-base"
MAX_LENGTH = 512

# Sieu tham so danh cho T4 16GB - da can nhac de tranh OOM.
PER_DEVICE_BATCH_SIZE = 2
GRAD_ACCUM_STEPS = 8          # batch hieu dung = 2 * 8 = 16
NUM_EPOCHS = 15               # dataset nho (6910 mau train) nen can nhieu epoch hon
LEARNING_RATE = 1e-5


def load_label_map() -> tuple:
    with open(os.path.join(INPUT_DIR, "label_map.json"), "r", encoding="utf-8") as f:
        label_map = json.load(f)
    id2label = {int(k): v for k, v in label_map["id2label"].items()}
    label2id = label_map["label2id"]
    return id2label, label2id


def load_processed_dataset() -> DatasetDict:
    return DatasetDict(
        {
            split: load_from_disk(os.path.join(INPUT_DIR, split))
            for split in ["train", "validation", "test"]
        }
    )


def build_encode_fn(processor):
    def encode(examples):
        images = examples["image"]
        words_batch = examples["words"]
        boxes_batch = examples["bboxes_normalized"]
        labels_batch = examples["ner_tags"]

        encoding = processor(
            images,
            words_batch,
            boxes=boxes_batch,
            word_labels=labels_batch,
            truncation=True,
            padding="max_length",
            max_length=MAX_LENGTH,
        )
        return encoding

    return encode


def compute_metrics_fn(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)

    true_labels, true_preds = [], []
    for pred_row, label_row in zip(predictions, labels):
        for p, l in zip(pred_row, label_row):
            if l == -100:  # padding / special token, processor tu gan -100
                continue
            true_labels.append(l)
            true_preds.append(p)

    accuracy = accuracy_score(true_labels, true_preds)
    precision, recall, f1, _ = precision_recall_fscore_support(
        true_labels, true_preds, average="macro", zero_division=0
    )
    return {"accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1}


def main():
    id2label, label2id = load_label_map()
    dataset = load_processed_dataset()

    processor = LayoutLMv3Processor.from_pretrained(BASE_MODEL, apply_ocr=False)
    model = LayoutLMv3ForTokenClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(id2label),
        id2label=id2label,
        label2id=label2id,
    )

    encode_fn = build_encode_fn(processor)
    encoded_dataset = dataset.map(
        encode_fn,
        batched=True,
        batch_size=4,
        remove_columns=dataset["train"].column_names,
    )
    encoded_dataset.set_format(type="torch")

    training_args = TrainingArguments(
        output_dir="/kaggle/working/checkpoints",
        per_device_train_batch_size=PER_DEVICE_BATCH_SIZE,
        per_device_eval_batch_size=PER_DEVICE_BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM_STEPS,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        warmup_ratio=0.1,
        fp16=True,  # BAT BUOC tren T4 16GB, neu khong se OOM gan nhu chac chan
        eval_strategy="steps",
        eval_steps=200,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=2,  # gioi han so checkpoint luu de khong day disk Kaggle
        logging_steps=50,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=encoded_dataset["train"],
        eval_dataset=encoded_dataset["validation"],
        compute_metrics=compute_metrics_fn,
    )

    trainer.train()

    print("\n=== DANH GIA TREN TAP TEST ===")
    test_metrics = trainer.evaluate(encoded_dataset["test"])
    print(test_metrics)

    os.makedirs(OUTPUT_MODEL_DIR, exist_ok=True)
    trainer.save_model(OUTPUT_MODEL_DIR)
    processor.save_pretrained(OUTPUT_MODEL_DIR)

    # Luu them label_map.json vao CUNG thu muc model de tool_layoutlmv3.py
    # dung lai truc tiep, khong phu thuoc vao INPUT_DIR cua buoc xu ly du lieu.
    with open(os.path.join(OUTPUT_MODEL_DIR, "label_map.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"id2label": {str(k): v for k, v in id2label.items()}, "label2id": label2id},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nDa luu model vao: {OUTPUT_MODEL_DIR}")
    print("Dung utils_zip_and_download.py (doi SOURCE_DIR thanh duong dan nay) de tai model ve may.")


if __name__ == "__main__":
    main()
