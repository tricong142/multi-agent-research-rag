"""
eval_reader.py
================
Danh gia ReaderAgent tren mot tap PDF co ground-truth thu cong.

QUAN TRONG - CAN DU LIEU THAT TU BAN: script nay KHONG the tu tao du lieu
danh gia (khong the bia dat PDF mau hay nhan dung/sai - can PDF va nhan
that tu ban). Ban can chuan bi 1 file JSON manifest liet ke cac PDF mau +
nhan ky vong, vi du:

[
  {"pdf_path": "samples/scan_invoice.pdf", "page_no": 0, "expected_tool": "ocr_fallback"},
  {"pdf_path": "samples/simple_report.pdf", "page_no": 0, "expected_tool": "alt_segmentation"},
  {"pdf_path": "samples/complex_financial.pdf", "page_no": 5, "expected_tool": "layoutlmv3"}
]

2 CHI SO DUOC TINH:
  1. Router Accuracy: ty le lan chon tool DAU TIEN (truoc khi vao vong
     self-critique) trung voi expected_tool.
  2. Critique Recovery Rate: trong so cac lan chon SAI tool dau tien (hoac
     ket qua ban dau bi Gemini Critique/Heuristic Guardrail tu choi), ty
     le ma vong self-critique van cho ra ket qua CUOI CUNG duoc chap nhan
     (success=True). Day la thuoc do kha nang "tu sua loi" cua vong critique.

CACH CHAY:
    python eval_reader.py --manifest samples/manifest.json --model_dir ./layoutlmv3_doclaynet_model
"""

import argparse
import json

from reader_agent import ReaderAgent


def load_manifest(manifest_path: str) -> list:
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate(manifest_path: str, layoutlmv3_model_dir: str) -> dict:
    manifest = load_manifest(manifest_path)
    agent = ReaderAgent(layoutlmv3_model_dir=layoutlmv3_model_dir)

    total = len(manifest)
    router_correct = 0
    initial_wrong_cases = 0
    recovered_cases = 0
    detailed_results = []

    for sample in manifest:
        pdf_path = sample["pdf_path"]
        page_no = sample.get("page_no", 0)
        expected_tool = sample["expected_tool"]

        result = agent.process_page(pdf_path, page_no)
        first_attempt_tool = result["attempts"][0]["tool"] if result["attempts"] else None

        router_is_correct = first_attempt_tool == expected_tool
        if router_is_correct:
            router_correct += 1
        else:
            initial_wrong_cases += 1
            if result["success"]:
                recovered_cases += 1

        detailed_results.append(
            {
                "pdf_path": pdf_path,
                "page_no": page_no,
                "expected_tool": expected_tool,
                "first_attempt_tool": first_attempt_tool,
                "final_tool": result["final_tool"],
                "router_correct": router_is_correct,
                "final_success": result["success"],
                "num_attempts": len(result["attempts"]),
            }
        )

    router_accuracy = router_correct / total if total else 0.0
    recovery_rate = (recovered_cases / initial_wrong_cases) if initial_wrong_cases else None

    print(f"\n=== KET QUA DANH GIA ({total} mau) ===")
    print(f"Router Accuracy: {router_accuracy:.2%} ({router_correct}/{total})")
    if recovery_rate is not None:
        print(
            f"Critique Recovery Rate: {recovery_rate:.2%} "
            f"({recovered_cases}/{initial_wrong_cases} truong hop chon sai/loi ban dau duoc tu sua)"
        )
    else:
        print("Critique Recovery Rate: khong co truong hop chon sai/loi ban dau nao de tinh.")

    return {
        "router_accuracy": router_accuracy,
        "recovery_rate": recovery_rate,
        "details": detailed_results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="Duong dan file JSON manifest")
    parser.add_argument(
        "--model_dir", required=True, help="Duong dan thu muc model LayoutLMv3 da train"
    )
    args = parser.parse_args()

    evaluate(args.manifest, args.model_dir)
