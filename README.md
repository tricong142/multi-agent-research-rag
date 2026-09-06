# 02_reader — Document Layout Reader Agent

Pipeline doc/parse tai lieu PDF, ket hop 3 cong cu trich xuat (PyMuPDF /
Tesseract OCR / LayoutLMv3 da fine-tune) voi 1 agent dieu phoi ket hop
**Heuristic Guardrails** (quy tac tat dinh, re) va **LLM Chain-of-Thought**
(Google Gemini API) cho ca buoc chon tool (Router) lan buoc tu kiem tra
chat luong (Self-Critique).

## Cau truc thu muc

```
02_reader/
├── notebooks/
│   ├── 00_inspect_doclaynet.py     # Giai doan A: liet ke schema that cua dataset
│   ├── 01_process_doclaynet.py     # Giai doan B: xu ly + luu dataset (Arrow)
│   └── 01_train_layoutlmv3.py      # Fine-tune LayoutLMv3 Token Classification
├── tools/
│   ├── common_schema.py            # Dinh dang du lieu chung cho ca 3 tool
│   ├── tool_layoutlmv3.py          # Nap model LayoutLMv3 da train, phan loai layout
│   ├── tool_ocr_fallback.py        # Tesseract OCR cho file scan/mo
│   └── tool_alt_segmentation.py    # PyMuPDF block parser cho text don gian
├── reader_policy.py                # Prompt CoT + Schema Pydantic cho Gemini Router & Critique
├── reader_agent.py                 # Router + Self-Critique Loop (Heuristic + Gemini CoT)
├── eval_reader.py                  # Danh gia Router accuracy + Critique recovery rate
└── README.md
```

## 1. Cai dat

Chay tren Kaggle Notebook cho phan `notebooks/` (can GPU T4), va tren may
local (hoac server rieng) cho phan agent/tools sau khi da tai model ve.

```bash
# Cho notebooks/ (chay tren Kaggle)
pip install -q -U datasets huggingface_hub transformers accelerate scikit-learn pillow

# Cho tools/ + reader_agent.py (chay noi ban muon dung agent, vd local/server)
pip install pymupdf pytesseract pillow torch transformers google-genai pydantic
```

Tesseract OCR can cai **binary** rieng (khong chi python package):
```bash
sudo apt-get install tesseract-ocr   # Ubuntu/Debian
```

## 2. Tai va xu ly dataset (Kaggle, GPU T4)

Thu tu bat buoc, khong nhay coc:

1. `notebooks/00_inspect_doclaynet.py` — liet ke file `.parquet` that trong
   nhanh `refs/convert/parquet` cua repo `pierreguillou/DocLayNet-base`
   (nhanh nay do HuggingFace Datasets Server tu dong tao ra vi repo goc con
   dung loading script da bi chan), in ra schema that de doi chieu.
2. `notebooks/01_process_doclaynet.py` — convert bbox (x,y,w,h) -> (x0,y0,
   x1,y1), chuan hoa toa do ve thang 0-1000 (dung `original_width`/
   `original_height`, KHONG dung `image.size` — 2 he toa do nay khac nhau
   trong dataset nay), luu ra `/kaggle/working/doclaynet_processed/` kem
   `label_map.json` (11 lop: Caption, Footnote, Formula, List-item,
   Page-footer, Page-header, Picture, Section-header, Table, Text, Title).

## 3. Fine-tune LayoutLMv3 (Kaggle, GPU T4)

Chay `notebooks/01_train_layoutlmv3.py` (cung session Kaggle, sau khi da
co `/kaggle/working/doclaynet_processed/`). Sieu tham so da can chinh cho
VRAM 16GB cua T4 (fp16, batch nho + gradient accumulation). Model + label
map duoc luu vao `/kaggle/working/layoutlmv3_doclaynet_model/`.

Tai model ve may (zip roi tao link tai truc tiep trong notebook — xem
`utils_zip_and_download.py` da trao doi truoc do, doi `SOURCE_DIR` thanh
duong dan model nay).

## 4. Cau hinh Google Gemini API

```bash
export GEMINI_API_KEY="your-key-here"
# Tuy chon, mac dinh la gemini-2.5-flash - kiem tra model moi nhat tai
# ai.google.dev truoc khi doi:
export GEMINI_MODEL="gemini-2.5-flash"
```

## 5. Chay ReaderAgent

```python
from reader_agent import ReaderAgent

agent = ReaderAgent(layoutlmv3_model_dir="./layoutlmv3_doclaynet_model")
result = agent.process_page("mydoc.pdf", page_no=0)

print(result["success"], result["final_tool"])
for block in result["blocks"]:
    print(block.to_dict())
```

Hoac chay truc tiep tu dong lenh:
```bash
python reader_agent.py mydoc.pdf 0
```

## 6. Danh gia (can du lieu ground-truth cua ban)

Chuan bi `manifest.json` (xem huong dan chi tiet trong docstring cua
`eval_reader.py`), roi chay:

```bash
python eval_reader.py --manifest samples/manifest.json --model_dir ./layoutlmv3_doclaynet_model
```

## Luu y quan trong ve thiet ke (de tranh nham lan khi bao tri)

- **Line-level, khong phai word-level**: du DocLayNet-base cung cap text o
  cap do "dong" (mot dong co the gom nhieu doan text rieng), nen model
  LayoutLMv3 duoc train va infer o cap do DONG, khong phai tung tu rieng
  le. `tools/tool_layoutlmv3.py` gom cac tu PyMuPDF trich duoc thanh dong
  (theo `block_no`+`line_no`) truoc khi dua vao model, de khop phan phoi
  du lieu train.
- **He toa do bbox**: trong dataset da xu ly, bbox chuan hoa dua tren
  `original_width`/`original_height` cua trang GOC, khong phai kich thuoc
  anh COCO (`coco_width`/`coco_height` = 1025x1025 co dinh). Nham lan cho
  nay se lam sai toan bo toa do.
- **Chi phi Gemini API**: Heuristic Guardrails duoc thiet ke de chan cac
  truong hop RO RANG (khong co text layer, layout qua don gian) truoc khi
  goi Gemini, giup giam dang ke so luot goi API that su can thiet.
