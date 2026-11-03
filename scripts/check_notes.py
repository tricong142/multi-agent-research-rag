import json
import sys
from pathlib import Path

REPO = Path(r"c:\Users\dellcuatri142\Downloads\AI ENGINEER")
sys.path.insert(0, str(REPO))

from scripts.review_atomic_cellfix13_full39 import NOTES

print("Total notes in cellfix13:", len(NOTES))
for k, v in list(NOTES.items())[:5]:
    print(k, "->", v[:60])

