import os
import json
import torch
from pathlib import Path
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from transformers import AutoModelForCausalLM, AutoTokenizer

# ============================================================
# 1. ĐƯỜNG DẪN 2 MODEL ĐÃ MERGE TRÊN KAGGLE CỦA BẠN
# ============================================================
GENERATOR_PATH = "/kaggle/input/datasets/trcng23/generator-merged-model"
CRITIC_PATH = "/kaggle/input/datasets/trcng23/critic-merged-model"

# ============================================================
# 2. PROMPTS CHUẨN CỦA AGENT 3
# ============================================================
GENERATOR_SYSTEM_PROMPT = """Bạn là Generator của một hệ thống Summarizer Agent.
Nhiệm vụ: đọc context và câu hỏi, sinh câu trả lời ngắn gọn kèm evidence_span nguyên văn từ context.
Luôn trả lời bằng JSON đúng định dạng:
{"answer": "...", "evidence_spans": ["..."]}
"""

CRITIC_SYSTEM_PROMPT = """Bạn là Critic ĐỘC LẬP của một hệ thống Summarizer Agent.
Nhiệm vụ: đọc context, câu hỏi, answer và evidence_spans, đánh giá xem answer có được hỗ trợ không.
Luôn trả lời bằng JSON đúng định dạng:
{"is_supported": true/false, "reason": "...", "action": "rewrite"|"request_more_context"|"lower_confidence"|""}
"""

def build_generator_user_prompt(context, question, retry_instruction=None):
    prompt = f"Context:\n\"\"\"\n{context}\n\"\"\"\n\nCâu hỏi: {question}"
    if retry_instruction:
        prompt += f"\n\nInstruction bổ sung: {retry_instruction}"
    return prompt

def build_critic_user_prompt(context, question, answer, evidence_spans):
    evidence_text = "\n".join(f"  - \"{e}\"" for e in evidence_spans)
    return f"Context:\n\"\"\"\n{context}\n\"\"\"\n\nCâu hỏi: {question}\n\nAnswer của Generator: {answer}\n\nEvidence_spans:\n{evidence_text}"

# ============================================================
# 3. CLASS SUMMARIZERNODE (TỐI ƯU TỐC ĐỘ MAX_TOKENS=120)
# ============================================================
@dataclass
class SummarizerTrial:
    answer: str
    evidence_spans: list[str]
    is_supported: bool
    critique_reason: str
    action: str

@dataclass
class SummarizerResult:
    answer: str
    evidence_spans: list[str]
    is_supported: bool
    reasoning_trace: list[SummarizerTrial] = field(default_factory=list)
    confidence: str = "high"

class SummarizerNode:
    def __init__(self, generator_model, generator_tokenizer, critic_model, critic_tokenizer, max_retries=2):
        self.generator_model = generator_model
        self.generator_tokenizer = generator_tokenizer
        self.critic_model = critic_model
        self.critic_tokenizer = critic_tokenizer
        self.max_retries = max_retries

    def run(self, context: str, question: str) -> SummarizerResult:
        trials = []
        retry_instruction = None

        for attempt in range(self.max_retries):
            gen_out = self._call_generator(context, question, retry_instruction)
            ans = gen_out.get("answer", "")
            spans = gen_out.get("evidence_spans", [])

            crit_out = self._call_critic(context, question, ans, spans)
            is_sup = crit_out.get("is_supported", False)
            reason = crit_out.get("reason", "")
            action = crit_out.get("action", "rewrite")

            trials.append(SummarizerTrial(ans, spans, is_sup, reason, action))

            if is_sup:
                return SummarizerResult(ans, spans, True, trials, "high")

            retry_instruction = f"Lỗi ở câu trước: {reason}. Hãy sinh lại bám sát evidence."

        last = trials[-1]
        return SummarizerResult(last.answer, last.evidence_spans, False, trials, "low")

    def _call_generator(self, context, question, retry_instruction):
        prompt = build_generator_user_prompt(context, question, retry_instruction)
        res = self._generate_json(self.generator_model, self.generator_tokenizer, GENERATOR_SYSTEM_PROMPT, prompt)
        return res if res else {"answer": "", "evidence_spans": []}

    def _call_critic(self, context, question, answer, evidence_spans):
        prompt = build_critic_user_prompt(context, question, answer, evidence_spans)
        res = self._generate_json(self.critic_model, self.critic_tokenizer, CRITIC_SYSTEM_PROMPT, prompt)
        return res if res else {"is_supported": False, "reason": "JSON không hợp lệ", "action": "rewrite"}

    def _generate_json(self, model, tokenizer, sys_prompt, user_prompt):
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=120,      # Tối ưu: Chỉ sinh tối đa 120 tokens, cực nhanh!
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id
            )
        generated = tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )
        try:
            return json.loads(generated)
        except Exception:
            return None

# ============================================================
# 4. HÀM KIỂM TRA EVIDENCE VERBATIM
# ============================================================
def normalize_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()

def is_verbatim_match(evidence: str, context: str, fuzzy_threshold: float = 0.9) -> tuple[bool, str]:
    norm_evidence = normalize_whitespace(evidence).lower()
    norm_context = normalize_whitespace(context).lower()

    if norm_evidence in norm_context:
        return True, "exact"

    window_size = len(norm_evidence)
    best_ratio = 0.0
    for i in range(0, max(1, len(norm_context) - window_size + 1)):
        window = norm_context[i : i + window_size]
        ratio = SequenceMatcher(None, norm_evidence, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
        if best_ratio >= fuzzy_threshold:
            return True, f"fuzzy_{best_ratio:.2f}"

    return False, f"below_threshold_{best_ratio:.2f}"

# ============================================================
# 5. NẠP 2 MODEL VÀO 2 GPU SẠCH SẼ
# ============================================================
print("[*] Đang nạp Generator lên GPU 0 (cuda:0)...", flush=True)
gen_tokenizer = AutoTokenizer.from_pretrained(GENERATOR_PATH)
gen_model = AutoModelForCausalLM.from_pretrained(
    GENERATOR_PATH, torch_dtype=torch.bfloat16, device_map="cuda:0"
).eval()

print("[*] Đang nạp Critic lên GPU 1 (cuda:1)...", flush=True)
crit_tokenizer = AutoTokenizer.from_pretrained(CRITIC_PATH)
crit_model = AutoModelForCausalLM.from_pretrained(
    CRITIC_PATH, torch_dtype=torch.bfloat16, device_map="cuda:1"
).eval()

node = SummarizerNode(gen_model, gen_tokenizer, crit_model, crit_tokenizer)
print("[*] ✅ KHỞI TẠO XONG! BẮT ĐẦU CHẠY BENCHMARK 18 MẪU...\n", flush=True)

# ============================================================
# 6. BỘ 18 MẪU TEST VÀ VÒNG LẶP CHẠY EVAL
# ============================================================
eval_samples = [
    {"context": "Low-Rank Adaptation, or LoRA, freezes the pre-trained model weights and injects trainable rank decomposition matrices into each layer of the Transformer architecture, greatly reducing the number of trainable parameters for downstream tasks. Compared to GPT-3 175B fine-tuned with Adam, LoRA can reduce the number of trainable parameters by 10,000 times and the GPU memory requirement by 3 times. LoRA performs on-par or better than fine-tuning in model quality on RoBERTa, DeBERTa, GPT-2, and GPT-3, despite having fewer trainable parameters, a higher training throughput, and, unlike adapters, no additional inference latency.", "question": "LoRA giúp giảm số lượng tham số cần huấn luyện và nhu cầu bộ nhớ GPU như thế nào so với GPT-3 175B tinh chỉnh bằng Adam?", "expected_is_answerable": True, "expected_answer": "LoRA có thể làm giảm số lượng tham số cần huấn luyện đi 10.000 lần và giảm nhu cầu bộ nhớ GPU đi 3 lần so với GPT-3 175B tinh chỉnh bằng Adam."},
    {"context": "Low-Rank Adaptation, or LoRA, freezes the pre-trained model weights and injects trainable rank decomposition matrices into each layer of the Transformer architecture, greatly reducing the number of trainable parameters for downstream tasks. Compared to GPT-3 175B fine-tuned with Adam, LoRA can reduce the number of trainable parameters by 10,000 times and the GPU memory requirement by 3 times. LoRA performs on-par or better than fine-tuning in model quality on RoBERTa, DeBERTa, GPT-2, and GPT-3, despite having fewer trainable parameters, a higher training throughput, and, unlike adapters, no additional inference latency.", "question": "Hiệu năng của LoRA có làm tăng độ trễ suy luận (inference latency) như phương pháp adapters không?", "expected_is_answerable": True, "expected_answer": "Không, khác với adapters, LoRA không gây thêm độ trễ suy luận nào."},
    {"context": "Low-Rank Adaptation, or LoRA, freezes the pre-trained model weights and injects trainable rank decomposition matrices into each layer of the Transformer architecture, greatly reducing the number of trainable parameters for downstream tasks. Compared to GPT-3 175B fine-tuned with Adam, LoRA can reduce the number of trainable parameters by 10,000 times and the GPU memory requirement by 3 times. LoRA performs on-par or better than fine-tuning in model quality on RoBERTa, DeBERTa, GPT-2, and GPT-3, despite having fewer trainable parameters, a higher training throughput, and, unlike adapters, no additional inference latency.", "question": "Tác giả đề xuất LoRA trong bài báo là ai và được công bố tại hội nghị nào?", "expected_is_answerable": False, "expected_answer": "Ngữ cảnh được cung cấp không chứa thông tin về tác giả hoặc hội nghị công bố LoRA."},
    
    {"context": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable and requiring significantly less time to train.", "question": "Kiến trúc Transformer được đề xuất dựa trên cơ chế nào và loại bỏ hoàn toàn những thành phần nào?", "expected_is_answerable": True, "expected_answer": "Transformer dựa hoàn toàn vào cơ chế chú ý (attention mechanisms) và loại bỏ hoàn toàn tính tái hồi (recurrence) cũng như tích chập (convolutions)."},
    {"context": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable and requiring significantly less time to train.", "question": "Thử nghiệm trên hai tác vụ dịch máy cho thấy mô hình Transformer có những ưu điểm gì?", "expected_is_answerable": True, "expected_answer": "Thử nghiệm cho thấy Transformer vượt trội về chất lượng, có khả năng song song hóa tốt hơn và đòi hỏi ít thời gian huấn luyện hơn đáng kể."},
    {"context": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable and requiring significantly less time to train.", "question": "Mô hình Transformer sử dụng bao nhiêu layer attention và kích thước hidden dimension là bao nhiêu?", "expected_is_answerable": False, "expected_answer": "Ngữ cảnh được cung cấp không chứa thông tin về số lượng layer attention hay kích thước hidden dimension."},

    {"context": "Large pre-trained language models have been shown to store factual knowledge in their parameters, and achieve state-of-the-art results when fine-tuned on downstream NLP tasks. However, their ability to access and precisely manipulate knowledge is still limited, and hence on knowledge-intensive tasks, their performance falls behind task-specific architectures. In this work, we develop a general-purpose fine-tuning recipe for retrieval-augmented generation (RAG) — models which combine pre-trained parametric and non-parametric memory for language generation.", "question": "Hạn chế của các mô hình ngôn ngữ lớn tiền huấn luyện khi thực hiện các tác vụ đòi hỏi nhiều tri thức là gì?", "expected_is_answerable": True, "expected_answer": "Khả năng truy cập và thao tác chính xác tri thức của chúng còn hạn chế, do đó hiệu năng của chúng kém hơn các kiến trúc chuyên biệt cho tác vụ."},
    {"context": "Large pre-trained language models have been shown to store factual knowledge in their parameters, and achieve state-of-the-art results when fine-tuned on downstream NLP tasks. However, their ability to access and precisely manipulate knowledge is still limited, and hence on knowledge-intensive tasks, their performance falls behind task-specific architectures. In this work, we develop a general-purpose fine-tuning recipe for retrieval-augmented generation (RAG) — models which combine pre-trained parametric and non-parametric memory for language generation.", "question": "Phương pháp retrieval-augmented generation (RAG) kết hợp những loại bộ nhớ nào cho việc sinh ngôn ngữ?", "expected_is_answerable": True, "expected_answer": "RAG kết hợp bộ nhớ có tham số (parametric memory) và phi tham số (non-parametric memory) đã được tiền huấn luyện."},
    {"context": "Large pre-trained language models have been shown to store factual knowledge in their parameters, and achieve state-of-the-art results when fine-tuned on downstream NLP tasks. However, their ability to access and precisely manipulate knowledge is still limited, and hence on knowledge-intensive tasks, their performance falls behind task-specific architectures. In this work, we develop a general-purpose fine-tuning recipe for retrieval-augmented generation (RAG) — models which combine pre-trained parametric and non-parametric memory for language generation.", "question": "Bộ truy xuất tài liệu trong mô hình RAG sử dụng hàm loss nào để tối ưu hóa?", "expected_is_answerable": False, "expected_answer": "Ngữ cảnh được cung cấp không đề cập đến hàm loss của bộ truy xuất tài liệu."},

    {"context": "While large language models (LLMs) have demonstrated impressive performance across various NLP tasks in few-shot and zero-shot settings, they are prone to factual errors (hallucinations) and cannot interact with the external world to obtain updated information. In this paper, we explore using LLMs to generate both reasoning traces and task-specific actions in an interleaved manner, allowing for greater synergy between the two: reasoning traces help the model induce, track, and update action plans as well as handle exceptions, while actions allow it to interface with external sources, such as knowledge bases or environments, to gather information.", "question": "Phương pháp ReAct kết hợp hai yếu tố nào một cách xen kẽ để tăng sức mạnh tổng hợp cho LLM?", "expected_is_answerable": True, "expected_answer": "ReAct kết hợp các vết lập luận (reasoning traces) và các hành động cụ thể cho tác vụ (task-specific actions) một cách xen kẽ."},
    {"context": "While large language models (LLMs) have demonstrated impressive performance across various NLP tasks in few-shot and zero-shot settings, they are prone to factual errors (hallucinations) and cannot interact with the external world to obtain updated information. In this paper, we explore using LLMs to generate both reasoning traces and task-specific actions in an interleaved manner, allowing for greater synergy between the two: reasoning traces help the model induce, track, and update action plans as well as handle exceptions, while actions allow it to interface with external sources, such as knowledge bases or environments, to gather information.", "question": "Trong ReAct, hành động (actions) giúp mô hình ngôn ngữ làm được điều gì với thế giới bên ngoài?", "expected_is_answerable": True, "expected_answer": "Actions cho phép mô hình giao tiếp với các nguồn bên ngoài như cơ sở tri thức hoặc môi trường để thu thập thông tin."},
    {"context": "While large language models (LLMs) have demonstrated impressive performance across various NLP tasks in few-shot and zero-shot settings, they are prone to factual errors (hallucinations) and cannot interact with the external world to obtain updated information. In this paper, we explore using LLMs to generate both reasoning traces and task-specific actions in an interleaved manner, allowing for greater synergy between the two: reasoning traces help the model induce, track, and update action plans as well as handle exceptions, while actions allow it to interface with external sources, such as knowledge bases or environments, to gather information.", "question": "ReAct đạt điểm số bao nhiêu phần trăm trên tập dữ liệu HotpotQA và AlfWorld?", "expected_is_answerable": False, "expected_answer": "Ngữ cảnh được cung cấp không chứa điểm số trên các tập dữ liệu HotpotQA hay AlfWorld."},

    {"context": "QLoRA is an efficient finetuning approach that reduces memory usage enough to finetune a 65B parameter model on a single 48GB GPU while preserving full 16-bit finetuning task performance. QLoRA backpropagates gradients through a frozen, 4-bit quantized pretrained language model into Low Rank Adapters (LoRA). Our best model family, which we name Guanaco, outperforms all previous openly released models on the Vicuna benchmark, reaching 99.3% of the performance level of ChatGPT while only requiring 24 hours of finetuning on a single GPU.", "question": "QLoRA có thể tinh chỉnh mô hình kích thước bao nhiêu tham số trên một GPU 48GB đơn lẻ?", "expected_is_answerable": True, "expected_answer": "QLoRA có thể tinh chỉnh một mô hình có kích thước 65 tỷ (65B) tham số trên một GPU 48GB đơn lẻ."},
    {"context": "QLoRA is an efficient finetuning approach that reduces memory usage enough to finetune a 65B parameter model on a single 48GB GPU while preserving full 16-bit finetuning task performance. QLoRA backpropagates gradients through a frozen, 4-bit quantized pretrained language model into Low Rank Adapters (LoRA). Our best model family, which we name Guanaco, outperforms all previous openly released models on the Vicuna benchmark, reaching 99.3% of the performance level of ChatGPT while only requiring 24 hours of finetuning on a single GPU.", "question": "Họ mô hình Guanaco của QLoRA đạt bao nhiêu phần trăm hiệu năng so với ChatGPT trên benchmark Vicuna?", "expected_is_answerable": True, "expected_answer": "Guanaco đạt 99.3% mức hiệu năng của ChatGPT trên benchmark Vicuna chỉ sau 24 giờ tinh chỉnh."},
    {"context": "QLoRA is an efficient finetuning approach that reduces memory usage enough to finetune a 65B parameter model on a single 48GB GPU while preserving full 16-bit finetuning task performance. QLoRA backpropagates gradients through a frozen, 4-bit quantized pretrained language model into Low Rank Adapters (LoRA). Our best model family, which we name Guanaco, outperforms all previous openly released models on the Vicuna benchmark, reaching 99.3% of the performance level of ChatGPT while only requiring 24 hours of finetuning on a single GPU.", "question": "Kiểu lượng tử hóa 4-bit NormalFloat (NF4) của QLoRA được thiết kế dựa trên phân phối toán học nào?", "expected_is_answerable": False, "expected_answer": "Ngữ cảnh được cung cấp không đề cập đến phân phối toán học của NormalFloat (NF4)."},

    {"context": "Direct Preference Optimization (DPO) is a stable, performant, and computationally lightweight algorithm for training language models from human preferences. Traditional methods like RLHF require fitting a reward model and then training a policy using reinforcement learning algorithms such as PPO, which are often unstable and hyperparameter-sensitive. In contrast, DPO implicitly optimizes the same objective as RLHF under a Bradley-Terry preference model, but in closed form, requiring only a simple cross-entropy loss over preferences without needing an explicit reward model or RL loop.", "question": "Khác với RLHF truyền thống dùng PPO, thuật toán Direct Preference Optimization (DPO) tối ưu hóa mục tiêu bằng cách nào?", "expected_is_answerable": True, "expected_answer": "DPO tối ưu hóa dạng đóng (closed form) chỉ bằng một hàm mất mát cross-entropy đơn giản trên sở thích, không cần mô hình phần thưởng rõ ràng hay vòng lặp RL."},
    {"context": "Direct Preference Optimization (DPO) is a stable, performant, and computationally lightweight algorithm for training language models from human preferences. Traditional methods like RLHF require fitting a reward model and then training a policy using reinforcement learning algorithms such as PPO, which are often unstable and hyperparameter-sensitive. In contrast, DPO implicitly optimizes the same objective as RLHF under a Bradley-Terry preference model, but in closed form, requiring only a simple cross-entropy loss over preferences without needing an explicit reward model or RL loop.", "question": "Mô hình sở thích nào được DPO sử dụng để ngầm tối ưu hóa cùng mục tiêu với RLHF?", "expected_is_answerable": True, "expected_answer": "DPO sử dụng mô hình sở thích Bradley-Terry (Bradley-Terry preference model)."},
    {"context": "Direct Preference Optimization (DPO) is a stable, performant, and computationally lightweight algorithm for training language models from human preferences. Traditional methods like RLHF require fitting a reward model and then training a policy using reinforcement learning algorithms such as PPO, which are often unstable and hyperparameter-sensitive. In contrast, DPO implicitly optimizes the same objective as RLHF under a Bradley-Terry preference model, but in closed form, requiring only a simple cross-entropy loss over preferences without needing an explicit reward model or RL loop.", "question": "Hệ số beta điều chỉnh độ phân kỳ KL trong hàm mục tiêu của DPO được đặt mặc định là bao nhiêu?", "expected_is_answerable": False, "expected_answer": "Ngữ cảnh được cung cấp không chứa thông tin về giá trị mặc định của hệ số beta."}
]

MIN_GROUNDING_RATE = 0.85
MIN_CRITIC_PRECISION = 0.80

n_total = len(eval_samples)
n_grounded = 0
n_predicted_unsupported = 0
n_predicted_unsupported_correct = 0
results = []

import time
start_time = time.time()

for idx, sample in enumerate(eval_samples, 1):
    t0 = time.time()
    print(f"[{idx}/{n_total}] Đang eval câu: '{sample['question'][:45]}...'", end="", flush=True)
    result = node.run(context=sample["context"], question=sample["question"])
    t_elapsed = time.time() - t0
    print(f" -> Xong ({t_elapsed:.1f}s)", flush=True)

    is_grounded = True
    if result.evidence_spans:
        for span in result.evidence_spans:
            valid, method = is_verbatim_match(span, sample["context"])
            if not valid:
                is_grounded = False
                break
    elif sample["expected_is_answerable"]:
        is_grounded = False
    n_grounded += int(is_grounded)

    final_trial = result.reasoning_trace[-1] if result.reasoning_trace else None
    if final_trial and not final_trial.is_supported:
        n_predicted_unsupported += 1
        if not sample["expected_is_answerable"]:
            n_predicted_unsupported_correct += 1

    results.append({
        **sample,
        "predicted_answer": result.answer,
        "predicted_evidence": result.evidence_spans,
        "is_supported_final": result.is_supported,
        "confidence": result.confidence,
        "n_internal_retries": len(result.reasoning_trace),
        "is_grounded": is_grounded,
    })

grounding_rate = n_grounded / n_total if n_total else 0
critique_precision = (
    n_predicted_unsupported_correct / n_predicted_unsupported
    if n_predicted_unsupported else float("nan")
)

print("\n" + "=" * 65)
print("📊 KẾT QUẢ ĐÁNH GIÁ ĐỊNH LƯỢNG AGENT 3:")
print("=" * 65)
print(f"Tổng số mẫu test    : {n_total} (Tổng thời gian: {time.time()-start_time:.1f}s)")
print(f"Grounding Rate      : {grounding_rate:.1%}  (Ngưỡng KPI: {MIN_GROUNDING_RATE:.0%}) -> {'✅ ĐẠT' if grounding_rate >= MIN_GROUNDING_RATE else '❌ CHƯA ĐẠT'}")
print(f"Critique Precision  : {critique_precision:.1%}  (Ngưỡng KPI: {MIN_CRITIC_PRECISION:.0%}) -> {'✅ ĐẠT' if critique_precision >= MIN_CRITIC_PRECISION else '❌ CHƯA ĐẠT'}")
print(f"Số lần Critic cảnh báo: {n_predicted_unsupported} lần (Đúng: {n_predicted_unsupported_correct} lần)")

output_file = Path("/kaggle/working/eval_results.jsonl")
with open(output_file, "w", encoding="utf-8") as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"\n📁 Đã lưu file kết quả -> {output_file}")
print("Tải file này về máy để chạy tiếp Giai đoạn 3 (LLM Judge) nhé!")
