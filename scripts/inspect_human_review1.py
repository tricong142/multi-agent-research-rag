from pathlib import Path
import re

text = Path("../HUMAN_REVIEW (1).html").read_text(encoding="utf-8")
print("Total length:", len(text))

# Let's inspect the first article
m = re.search(r'(<article data-id="decompose:001">.*?</article>)', text, re.DOTALL)
if m:
    print("Article 001 sample:")
    print(m.group(1)[:1000])
    print("...")
    print(m.group(1)[-500:])
else:
    print("Article 001 not found")
