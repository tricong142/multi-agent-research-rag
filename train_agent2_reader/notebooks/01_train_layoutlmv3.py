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

# Sieu tham so da toi uu thuc chien cho T4 16GB:
# - TANG batch size tu 2 len 4: Tan dung tot Tensor Cores cua T4, giam thoi gian moi step
# - GIAM grad accum tu 8 xuong 4: Giu nguyen effective batch size (4 * 4 = 16 tren 1 GPU, hoac 32 tren 2 GPU)
# - GIAM epoch tu 15 xuong 5: Diem hoi tu toi uu cho Pretrained LayoutLMv3, chong overfit va giam ~3x thoi gian
# - Tang nhe learning rate len 2e-5: Giup mo hinh hoi tu sac ben trong 5 epochs
PER_DEVICE_BATCH_SIZE = 4
GRAD_ACCUM_STEPS = 4          # batch hieu dung = 4 * 4 = 16 (1 GPU) hoac 4 * 4 * 2 = 32 (2 GPU)
NUM_EPOCHS = 5                # 5 epochs la diem vang hoi tu cho transfer learning
LEARNING_RATE = 2e-5


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


def clamp_bbox(box):
    """
    Kep toa do box [x0, y0, x1, y1] ve thang chuan [0, 1000] cua LayoutLMv3.
    Dam bao 0 <= x0 <= x1 <= 1000 va 0 <= y0 <= y1 <= 1000 de triet tieu loi
    CUDA assertion trong embedding layer (kich thuoc bang lookup co dinh 1024).
    """
    x0 = min(max(int(box[0]), 0), 1000)
    y0 = min(max(int(box[1]), 0), 1000)
    x1 = min(max(int(box[2]), 0), 1000)
    y1 = min(max(int(box[3]), 0), 1000)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return [x0, y0, x1, y1]


def build_encode_fn(processor):
    def encode(examples):
        images = examples["image"]
        words_batch = examples["words"]
        boxes_batch = examples["bboxes_normalized"]
        labels_batch = examples["ner_tags"]

        # 1. Clamp bounding boxes dau vao truoc khi dua vao processor
        clamped_boxes_batch = [
            [clamp_bbox(box) for box in doc_boxes]
            for doc_boxes in boxes_batch
        ]

        encoding = processor(
            images,
            words_batch,
            boxes=clamped_boxes_batch,
            word_labels=labels_batch,
            truncation=True,
            padding="max_length",
            max_length=MAX_LENGTH,
        )

        # 2. Phong thu kep (double defense): clamp lai encoding["bbox"]
        # Dam bao 100% khong co index < 0 hoac >= 1024 lot vao GPU embedding lookup
        encoding["bbox"] = [
            [clamp_bbox(box) for box in doc_boxes]
            for doc_boxes in encoding["bbox"]
        ]
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

    # Tinh warmup_steps chuan thay cho warmup_ratio de tranh canh bao deprecation
    effective_batch_size = PER_DEVICE_BATCH_SIZE * GRAD_ACCUM_STEPS
    steps_per_epoch = len(encoded_dataset["train"]) // effective_batch_size
    total_train_steps = max(steps_per_epoch * NUM_EPOCHS, 1)
    warmup_steps = int(0.1 * total_train_steps)

    training_args = TrainingArguments(
        output_dir="/kaggle/working/checkpoints",
        per_device_train_batch_size=PER_DEVICE_BATCH_SIZE,
        per_device_eval_batch_size=PER_DEVICE_BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM_STEPS,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        warmup_steps=warmup_steps,
        fp16=True,  # BAT BUOC tren T4 16GB, neu khong se OOM gan nhu chac chan
        eval_strategy="epoch",  # Danh gia moi epoch 1 lan, giam thoi gian dung cho eval giua chung
        save_strategy="epoch",  # Luu checkpoint moi epoch
        save_total_limit=1,     # Chi giu 1 checkpoint tot nhat de tiet kiem disk Kaggle
        logging_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        dataloader_num_workers=2,  # Prefetch batch da luong CPU de GPU khong bi doi data
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
