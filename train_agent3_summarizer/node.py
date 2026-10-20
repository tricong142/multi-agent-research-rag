"""
03_summarizer/node.py

INTERFACE DUY NHẤT để LangGraph (tầng Orchestrator, ngoài phạm vi thư
mục này) import và gọi vào. Class SummarizerNode hiện thực hoá ĐÚNG
luồng trong sơ đồ đã thống nhất:

  Nhận context + câu hỏi/intent (kèm lịch sử các lần thử trước)
    -> LLM sinh answer + evidence span (Generator)
    -> LLM critic độc lập phê bình (Critic)
    -> Được hỗ trợ?
         Có  -> trả kết quả ra ngoài
         Không -> Chọn hành động (rewrite / lấy thêm context / hạ tin cậy)
                  -> quay lại sinh answer (Generator), lặp lại
    Giới hạn MAX_INTERNAL_RETRY lần - hết vẫn phải return, KHÔNG raise
    exception hay treo vô hạn (đúng nguyên tắc đã thống nhất từ Bước 1).

CHẠY Ở: có thể chạy cả Kaggle (lúc test nhanh sau khi train) lẫn
production server thật (sau khi đã merge model qua merge_lora_weights.py).
KHÔNG cần GPU nếu dùng bản đã quantize/hoặc gọi qua API serving riêng
(vLLM/TGI) - class này chỉ định nghĩa LOGIC điều phối, phần load model
cụ thể được tách vào 2 hàm _call_generator/_call_critic để dễ đổi
backend sau này (từ transformers thuần sang vLLM chẳng hạn).

LƯU Ý QUAN TRỌNG VỀ retry_count vs MAX_INTERNAL_RETRY (đã thống nhất
từ Bước 1 - Retrieval Agent, áp dụng y hệt cho Summarizer):
  - MAX_INTERNAL_RETRY (dùng trong file này) = vòng lặp RIÊNG của node
    Summarizer, KHÔNG lưu vào AgentState dùng chung của toàn graph.
  - retry_count (tầng Orchestrator) = biến RIÊNG, đếm số lần graph lớn
    quay lại Summarizer TỪ NODE KHÁC (ví dụ từ Fact-Checker), khác hoàn
    toàn với retry nội bộ ở đây. SummarizerNode KHÔNG được đọc/ghi vào
    retry_count của Orchestrator.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Callable

if __package__:
    from . import config
    from .generator.prompts import GENERATOR_SYSTEM_PROMPT, build_generator_user_prompt
    from .critic.prompts import CRITIC_SYSTEM_PROMPT, build_critic_user_prompt
else:  # direct execution from this directory
    import config
    from generator.prompts import GENERATOR_SYSTEM_PROMPT, build_generator_user_prompt
    from critic.prompts import CRITIC_SYSTEM_PROMPT, build_critic_user_prompt


def output_schema_issue(value, role: str) -> str | None:
    """Validate each role's wire contract before the node reads any fields."""
    if not isinstance(value, dict):
        return role + "_object_required"
    if role == "generator":
        if set(value) != {"answer", "evidence_spans"}:
            return "generator_fields_required"
        if not isinstance(value["answer"], str) or not value["answer"].strip():
            return "generator_answer_required"
        spans = value["evidence_spans"]
        if not isinstance(spans, list) or any(not isinstance(s, str) or not s.strip() for s in spans):
            return "generator_evidence_spans_schema"
    elif role == "critic":
        required = {"is_supported", "reason", "action"}
        if not required <= set(value) or set(value) - required - {"suggested_query"}:
            return "critic_fields_required"
        if type(value["is_supported"]) is not bool:
            return "critic_support_boolean_required"
        if not isinstance(value["reason"], str) or not value["reason"].strip():
            return "critic_reason_required"
        actions = ("",) if value["is_supported"] else config.CRITIC_ACTIONS
        if value["action"] not in actions:
            return "critic_action_schema"
        if "suggested_query" in value and (not isinstance(value["suggested_query"], str)
                                          or not value["suggested_query"].strip()
                                          or len(value["suggested_query"]) > 4000):
            return "critic_query_schema"
    else:
        raise ValueError("Unknown summarizer role: " + role)
    return None


@dataclass
class SummarizerTrial:
    """1 lần thử trong lịch sử nội bộ - dùng để model đọc lại ở lượt sau,
    tránh lặp lại đúng lỗi đã mắc."""
    answer: str
    evidence_spans: list[str]
    is_supported: bool
    critique_reason: str
    action: str


@dataclass
class SummarizerResult:
    """Kết quả CUỐI CÙNG trả ra ngoài cho Orchestrator - đây là format
    duy nhất mà tầng graph lớn cần biết, không cần biết chi tiết bên
    trong đã lặp bao nhiêu lần."""
    answer: str
    evidence_spans: list[str]
    is_supported: bool
    reasoning_trace: list[SummarizerTrial] = field(default_factory=list)
    confidence: str = "high"  # "high" | "low" - "low" khi hết MAX_INTERNAL_RETRY mà vẫn chưa đạt
    missing_information: list[str] = field(default_factory=list)
    suggested_query: str | None = None
    suggested_action: str | None = None


class SummarizerNode:
    """
    Sử dụng:
        node = SummarizerNode(generator_model, generator_tokenizer,
                               critic_model, critic_tokenizer)
        result = node.run(context="...", question="...")
    """

    def __init__(self, generator_model, generator_tokenizer, critic_model, critic_tokenizer,
                 *, on_generation: Callable[[dict], None] | None = None):
        self.generator_model = generator_model
        self.generator_tokenizer = generator_tokenizer
        self.critic_model = critic_model
        self.critic_tokenizer = critic_tokenizer
        # Opt-in only: raw generations can contain private answer/evidence text.
        self.on_generation = on_generation

    def run(self, context: str, question: str) -> SummarizerResult:
        trials: list[SummarizerTrial] = []
        retry_instruction = (
            "Answer the question directly in complete factual sentences, naming the subject and predicate. "
            "Do not return a bare number or a pointer to another section as the answer. "
            "If the requested fact is absent, state what is missing. Copy evidence text without source ID prefixes."
        )
        current_context = context

        for attempt in range(config.MAX_INTERNAL_RETRY):
            # --- Bước 1: Generator sinh answer + evidence ---
            gen_output = self._call_generator(current_context, question, retry_instruction)
            answer = gen_output["answer"]
            evidence_spans = gen_output["evidence_spans"]

            # --- Bước 2: Critic độc lập phê bình ---
            if gen_output.get("validation_issue"):
                critic_output = {"is_supported": False, "reason": gen_output["validation_issue"],
                                 "action": "rewrite"}
            else:
                critic_output = self._call_critic(current_context, question, answer, evidence_spans)
            is_supported = critic_output["is_supported"] is True
            reason = critic_output["reason"]
            action = critic_output.get("action", "")
            if re.fullmatch(r"[\d\s.,%+\-]+", str(answer).strip()):
                is_supported = False
                reason = "Restate the quantity as a complete factual sentence identifying its subject."
                action = "rewrite"

            trials.append(SummarizerTrial(
                answer=answer,
                evidence_spans=evidence_spans,
                is_supported=is_supported,
                critique_reason=reason,
                action=action,
            ))

            # --- Bước 3: Rẽ nhánh "Được hỗ trợ?" ---
            if is_supported:
                return SummarizerResult(
                    answer=answer,
                    evidence_spans=evidence_spans,
                    is_supported=True,
                    reasoning_trace=trials,
                    confidence="high",
                )

            # --- Không được hỗ trợ: chọn hành động rồi quay lại Generator ---
            if action not in config.CRITIC_ACTIONS:
                # Phòng thủ: nếu model trả action không hợp lệ (lỗi hiếm nhưng
                # có thể xảy ra), mặc định về "rewrite" thay vì crash.
                action = "rewrite"

            retry_instruction = self._build_retry_instruction(action, reason)

            if action == "request_more_context":
                # Yield immediately: more generations over the same insufficient
                # context do not satisfy this request. The controller owns retrieval.
                query = critic_output.get("suggested_query")
                if not isinstance(query, str) or not query.strip() or len(query) > 4000:
                    query = question[:4000]
                return SummarizerResult(answer=answer, evidence_spans=evidence_spans,
                                        is_supported=False, reasoning_trace=trials, confidence="low",
                                        missing_information=[str(reason)], suggested_query=query,
                                        suggested_action="search")

        # --- Hết MAX_INTERNAL_RETRY mà vẫn chưa đạt - LỐI THOÁT AN TOÀN BẮT BUỘC ---
        # Không raise exception, không treo vô hạn - trả kết quả tốt nhất hiện có
        # kèm confidence="low" để tầng ngoài (Fact-Checker/Orchestrator) biết mà
        # xử lý thận trọng hơn.
        last_trial = trials[-1]
        return SummarizerResult(
            answer=last_trial.answer,
            evidence_spans=last_trial.evidence_spans,
            is_supported=False,
            reasoning_trace=trials,
            confidence="low",
            missing_information=[last_trial.critique_reason], suggested_query=question[:4000],
            suggested_action="search",
        )

    def _build_retry_instruction(self, action: str, critic_reason: str) -> str:
        if action == "rewrite":
            return (
                f"Câu trả lời trước bị đánh giá chưa đạt: {critic_reason}. "
                f"Hãy sinh lại, bám sát evidence chặt chẽ hơn, không suy diễn thêm."
            )
        elif action == "request_more_context":
            return (
                f"Context hiện tại được đánh giá không đủ: {critic_reason}. "
                f"Hãy trả lời PHẦN có căn cứ, và nêu rõ phần nào chưa đủ thông tin."
            )
        elif action == "lower_confidence":
            return (
                f"Câu trả lời trước có suy diễn vượt evidence: {critic_reason}. "
                f"Hãy sinh lại với ngôn từ thể hiện rõ mức độ không chắc chắn."
            )
        return critic_reason

    def _call_generator(self, context: str, question: str, retry_instruction: str | None) -> dict:
        user_prompt = build_generator_user_prompt(context, question, retry_instruction)
        result = self._generate_json(
            self.generator_model, self.generator_tokenizer,
            GENERATOR_SYSTEM_PROMPT, user_prompt,
            role="generator",
        )
        issue = output_schema_issue(result, "generator")
        if issue:
            # Model trả JSON hỏng - coi như answer rỗng, để Critic (hoặc vòng lặp)
            # tự nhận diện và retry, KHÔNG để lỗi lan ra ngoài node.
            return {"answer": "", "evidence_spans": [], "validation_issue":
                    "Generator JSON/schema invalid (" + issue +
                    "). Return answer as a nonempty string and evidence_spans as a list of strings."}
        return result

    def _call_critic(self, context: str, question: str, answer: str, evidence_spans: list[str]) -> dict:
        user_prompt = build_critic_user_prompt(context, question, answer, evidence_spans)
        result = self._generate_json(
            self.critic_model, self.critic_tokenizer,
            CRITIC_SYSTEM_PROMPT, user_prompt,
            role="critic",
        )
        issue = output_schema_issue(result, "critic")
        if issue:
            # Critic hỏng JSON - mặc định coi là "chưa đạt" (an toàn hơn là mặc
            # định "đạt", vì thà retry thừa còn hơn để lọt answer chưa được kiểm).
            return {"is_supported": False, "reason": "Critic JSON/schema invalid (" + issue +
                    "). Return boolean is_supported, nonempty reason and a valid action.", "action": "rewrite"}
        return result

    def _generate_json(self, model, tokenizer, system_prompt: str, user_prompt: str,
                       *, role: str) -> dict | None:
        """Hàm dùng chung để gọi model + parse JSON, tách riêng để dễ đổi
        sang backend serving khác (vLLM/TGI) sau này mà không sửa logic
        điều phối ở run(). Trả về None nếu parse/schema lỗi - KHÔNG raise exception,
        để hàm gọi (_call_generator/_call_critic) tự quyết định fallback phù
        hợp với vai trò của từng bên, đúng nguyên tắc "lối thoát an toàn,
        không crash, không treo vô hạn" đã thống nhất từ Bước 1."""
        import torch  # import cục bộ - chỉ cần khi thực sự inference bằng transformers

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            output_ids = model.generate(
                **inputs, max_new_tokens=512, temperature=0.1, do_sample=False
            )
        generated = tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )

        parse_error = None
        try:
            result = json.loads(generated)
        except json.JSONDecodeError as exc:
            result = None
            parse_error = {"message": exc.msg, "position": exc.pos}
        schema_issue = output_schema_issue(result, role) if parse_error is None else None
        if self.on_generation is not None:
            self.on_generation({"event": "summarizer_generation", "role": role,
                                "raw_output": generated, "json_valid": parse_error is None,
                                "parsed_type": type(result).__name__, "parse_error": parse_error,
                                "schema_valid": parse_error is None and schema_issue is None,
                                "schema_issue": schema_issue,
                                "generated_tokens": len(output_ids[0]) - inputs["input_ids"].shape[1],
                                "max_new_tokens": 512})
        return result if schema_issue is None else None
