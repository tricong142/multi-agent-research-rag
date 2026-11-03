import json
from pathlib import Path

nb_path = Path(r"c:\Users\dellcuatri142\Downloads\AI ENGINEER\scripts\kaggle_atomic_verifier_cellfix15.ipynb")
nb = json.loads(nb_path.read_text(encoding="utf-8"))

for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "code":
        src = "".join(cell["source"])
        if "FULL39_REVIEW_PATH" in src or "RUN_VALIDATION30" in src:
            print(f"Cell {i}:")
            print(src[:500])
            print("="*40)

