import argparse
import json
import sys

# Đảm bảo console UTF-8 trên Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.graph import build_research_rag_graph

def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Research RAG System (LangGraph StateGraph)")
    parser.add_argument("--query", type=str, default="What is LoRA and how does it reduce memory?", help="Câu hỏi nghiên cứu")
    parser.add_argument("--pdf", type=str, default=None, help="Đường dẫn file PDF nghiên cứu (nếu có)")
    parser.add_argument("--test-retry", action="store_true", help="Kích hoạt kiểm thử vòng lặp retry 3 lần và escalation")
    args = parser.parse_args()

    query = args.query
    if args.test_retry:
        query = f"[test_retry] {query}"

    print("\n" + "="*60)
    print("KHỞI ĐỘNG HỆ THỐNG MULTI-AGENT RESEARCH RAG")
    print(f"Câu truy vấn: {query}")
    print(f"File PDF kèm theo: {args.pdf}")
    print("="*60 + "\n")

    app = build_research_rag_graph()
    
    initial_state = {
        "query": query,
        "pdf_path": args.pdf,
        "retry_count": 0,
        "reasoning_trace": []
    }

    final_state = app.invoke(initial_state)

    print("\n" + "="*60)
    print("KẾT QUẢ CUỐI CÙNG (FINAL REPORT)")
    print("="*60)
    print(final_state.get("final_report", "Không có báo cáo được tạo ra."))
    
    print("\n" + "="*60)
    print("NHẬT KÝ SUY LUẬN TỔNG HỢP (REASONING TRACE)")
    print("="*60)
    for idx, step in enumerate(final_state.get("reasoning_trace", []), 1):
        print(f"[{idx}] {json.dumps(step, ensure_ascii=False)}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
