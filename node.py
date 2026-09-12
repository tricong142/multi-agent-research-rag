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
from dataclasses import dataclass, field

import config
from generator.prompts import GENERATOR_SYSTEM_PROMPT, build_generator_user_prompt
from critic.prompts import CRITIC_SYSTEM_PROMPT, build_critic_user_prompt


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


class SummarizerNode:
    """
    Sử dụng:
        node = SummarizerNode(generator_model, generator_tokenizer,
                               critic_model, critic_tokenizer)
        result = node.run(context="...", question="...")
    """

    def __init__(self, generator_model, generator_tokenizer, critic_model, critic_tokenizer):
        self.generator_model = generator_model
        self.generator_tokenizer = generator_tokenizer
        self.critic_model = critic_model
        self.critic_tokenizer = critic_tokenizer

    def run(self, context: str, question: str) -> SummarizerResult:
        trials: list[SummarizerTrial] = []
        retry_instruction = None
        current_context = context

        for attempt in range(config.MAX_INTERNAL_RETRY):
            # --- Bước 1: Generator sinh answer + evidence ---
            gen_output = self._call_generator(current_context, question, retry_instruction)
            answer = gen_output["answer"]
            evidence_spans = gen_output["evidence_spans"]

            # --- Bước 2: Critic độc lập phê bình ---
            critic_output = self._call_critic(current_context, question, answer, evidence_spans)
            is_supported = critic_output["is_supported"]
            reason = critic_output["reason"]
            action = critic_output.get("action", "")

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
                # Trong hệ thống thật, đây là lúc gọi ngược lại Retrieval Agent
                # để lấy thêm context - SummarizerNode KHÔNG tự làm việc này
                # (không thuộc trách nhiệm của node), chỉ đánh dấu để
                # Orchestrator biết cần điều phối sang Retrieval Agent.
                # Ở đây, để vòng lặp nội bộ vẫn có thể tiếp tục thử nghiệm
                # với context hiện có, ta KHÔNG mở rộng context tự động.
                pass

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
        )
        if result is None:
            # Model trả JSON hỏng - coi như answer rỗng, để Critic (hoặc vòng lặp)
            # tự nhận diện và retry, KHÔNG để lỗi lan ra ngoài node.
            return {"answer": "", "evidence_spans": []}
        return result

    def _call_critic(self, context: str, question: str, answer: str, evidence_spans: list[str]) -> dict:
        user_prompt = build_critic_user_prompt(context, question, answer, evidence_spans)
        result = self._generate_json(
            self.critic_model, self.critic_tokenizer,
            CRITIC_SYSTEM_PROMPT, user_prompt,
        )
        if result is None:
            # Critic hỏng JSON - mặc định coi là "chưa đạt" (an toàn hơn là mặc
            # định "đạt", vì thà retry thừa còn hơn để lọt answer chưa được kiểm).
            return {"is_supported": False, "reason": "Critic trả JSON không hợp lệ.", "action": "rewrite"}
        return result

    def _generate_json(self, model, tokenizer, system_prompt: str, user_prompt: str) -> dict | None:
        """Hàm dùng chung để gọi model + parse JSON, tách riêng để dễ đổi
        sang backend serving khác (vLLM/TGI) sau này mà không sửa logic
        điều phối ở run(). Trả về None nếu parse lỗi - KHÔNG raise exception,
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

        try:
            return json.loads(generated)
        except json.JSONDecodeError:
            return None
