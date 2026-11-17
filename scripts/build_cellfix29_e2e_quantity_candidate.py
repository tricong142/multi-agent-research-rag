"""Build a CPU diagnostic candidate from the frozen Cellfix29 package."""

from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from research_rag.atomic_adapter import PAYLOAD, PAYLOAD_SHA256


QUANTITIES = "04_factchecker/inference/cellfix14_quantities.py"
OUTPUT = PAYLOAD.parent / "atomic-cellfix29-e2e-quantity-candidate.zip"


def edit_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Unexpected frozen quantity parser: {old!r}")
    return text.replace(old, new, 1)


def candidate_bytes() -> bytes:
    baseline = PAYLOAD.read_bytes()
    if sha256(baseline).hexdigest() != PAYLOAD_SHA256:
        raise ValueError("Cellfix29 baseline hash mismatch")
    buffer = BytesIO()
    with ZipFile(BytesIO(baseline)) as source, ZipFile(buffer, "w", ZIP_DEFLATED) as candidate:
        quantities = source.read(QUANTITIES).decode().replace("\r\n", "\n")
        quantities = edit_once(quantities, "_STOP = set('and or but of for with from to in on at by than as after before during ",
                               "_STOP = set('and or but of for with from to in on at by than as after before during over ")
        quantities = edit_once(quantities, "    excluded += [m.span() for m in re.finditer(\n",
                               "    references = [m.span() for m in re.finditer(\n")
        quantities = edit_once(quantities, "        value, kind = next(iter(quantities(m[0])))\n",
                               "        value, kind = next(iter(quantities(m[0])))\n"
                               "        if kind != 'percent' and any(start <= m.start() < end for start, end in references):\n"
                               "            continue\n")
        quantities = edit_once(quantities, "        if any(a <= m.start() < b for a,b in excluded): continue",
                               "        if any(a <= m.start() < b for a,b in excluded + references): continue")
        compile(quantities, QUANTITIES, "exec")
        for name in sorted(source.namelist()):
            member = source.getinfo(name)
            candidate.writestr(member, quantities.encode() if name == QUANTITIES else source.read(name))
    return buffer.getvalue()


if __name__ == "__main__":
    payload = candidate_bytes()
    OUTPUT.write_bytes(payload)
    print(OUTPUT, sha256(payload).hexdigest())
