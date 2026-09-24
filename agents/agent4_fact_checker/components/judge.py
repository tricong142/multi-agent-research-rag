import re
from typing import Optional, Any
from utils.logger import logger


class FactCheckJudge:
    """
    Trọng tài kiểm chứng sự thật khoa học (Scientific NLI Judge).
    So khớp cặp Premise (Evidence / Context) và Hypothesis (Claim) để đưa ra phán quyết:
    - "support": Khẳng định được chứng minh đầy đủ.
    - "contradict": Khẳng định mâu thuẫn hoặc phủ định tài liệu nguồn.
    - "not_enough_info": Tài liệu nguồn không đủ dữ kiện chứng minh.
    
    Cung cấp siêu dữ liệu chi tiết (matched_keywords, justification_sentence) phục vụ Writer Agent.
    """

    # Bảng từ điển ánh xạ thuật ngữ song ngữ (Anh - Việt) chuyên ngành Khoa học máy tính & AI
    BILINGUAL_MAP = {
        "giảm": ["reduce", "reduces", "reduction", "reducing", "decrease", "decreases", "lower", "drop"],
        "tăng": ["increase", "increases", "increasing", "boost", "higher", "raise"],
        "tham số": ["parameter", "parameters"],
        "huấn luyện": ["train", "training", "trainable", "trained", "fine-tuning", "finetune"],
        "đóng băng": ["freeze", "freezes", "frozen", "freezing"],
        "trọng số": ["weight", "weights"],
        "mô hình": ["model", "models"],
        "ngôn ngữ": ["language", "languages"],
        "lớn": ["large"],
        "áp dụng": ["apply", "applies", "applied", "application"],
        "thành công": ["successful", "successfully", "achieve"],
        "chi phí": ["cost", "costs", "requirement", "requirements", "overhead"],
        "bộ nhớ": ["memory", "vram"],
        "độ trễ": ["latency", "delay", "inference time"],
        "phân rã": ["decomposition", "decompose", "factorization"],
        "hạng thấp": ["low-rank", "low rank", "rank"],
        "chú ý": ["attention", "self-attention", "cross-attention"],
        "độ chính xác": ["accuracy", "performance", "score", "bleu"],
    }

    AI_CORE_ENTITIES = {
        "lora", "qlora", "transformer", "bert", "roberta", "deberta",
        "gpt", "gpt-3", "gpt-4", "resnet", "dpo", "attention", "adam",
        "scibert", "rag", "react", "bleu", "glue", "vram", "gpu"
    }

    NEGATION_WORDS_VN = {"không", "không thể", "chưa", "chẳng", "không có", "tránh"}
    NEGATION_WORDS_EN = {"not", "never", "cannot", "no", "hardly", "fail", "fails", "unable", "dispense"}

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        self.model_path = model_path
        self.device = device
        self.classifier = None
        self._init_classifier()

    def _init_classifier(self):
        """Khởi tạo transformer pipeline nếu model_path tồn tại."""
        if self.model_path:
            try:
                from transformers import pipeline
                self.classifier = pipeline(
                    "text-classification",
                    model=self.model_path,
                    device=self.device,
                    return_all_scores=True
                )
                logger.info(f"[FactCheckJudge] Đã nạp thành công mô hình NLI từ: {self.model_path}")
            except Exception as e:
                logger.warning(f"[FactCheckJudge] Không thể nạp mô hình từ {self.model_path} ({e}). Sử dụng Heuristic Judge.")
                self.classifier = None

    def judge_claim(
        self,
        claim: str,
        evidence_spans: list[str],
        context: str = ""
    ) -> dict[str, Any]:
        """
        Đánh giá một claim cụ thể dựa trên evidence_spans hoặc full context.
        Trả về: {status, confidence, evidence, matched_keywords, reason}
        """
        if not claim or not claim.strip():
            return {
                "status": "not_enough_info",
                "confidence": 1.0,
                "evidence": "",
                "matched_keywords": [],
                "reason": "Luận điểm rỗng."
            }

        # Nếu có mô hình transformer đã load
        if self.classifier is not None:
            return self._predict_with_model(claim, evidence_spans, context)

        # Mặc định: Dùng Heuristic NLI Judge (bilingual, robust, offline)
        return self._heuristic_judge(claim, evidence_spans, context)

    def _predict_with_model(self, claim: str, evidence_spans: list[str], context: str) -> dict[str, Any]:
        """
        Dự đoán qua mô hình Transformer với cơ chế Multi-span Aggregation.
        """
        spans_to_test = [s.strip() for s in evidence_spans if s.strip()]
        if not spans_to_test and context:
            spans_to_test = [s.strip() for s in re.split(r"[.?!]\s+", context) if len(s.strip()) > 20][:5]

        if not spans_to_test:
            return {
                "status": "not_enough_info",
                "confidence": 0.95,
                "evidence": "Không có chứng cứ tương ứng.",
                "matched_keywords": [],
                "reason": "Thiếu hoàn toàn chứng cứ."
            }

        results = []
        for span in spans_to_test:
            text_pair = f"{span[:384]} </s></s> {claim}"
            try:
                scores_list = self.classifier(text_pair)[0]
                label_scores = {r["label"].lower(): r["score"] for r in scores_list}
                top_label = max(label_scores, key=label_scores.get)

                if "entailment" in top_label or "support" in top_label:
                    status = "support"
                elif "contradiction" in top_label or "contradict" in top_label:
                    status = "contradict"
                else:
                    status = "not_enough_info"

                results.append({
                    "status": status,
                    "confidence": round(label_scores[top_label], 3),
                    "evidence": span,
                    "matched_keywords": list(set(re.findall(r"\w+", claim.lower())).intersection(set(re.findall(r"\w+", span.lower())))),
                    "reason": f"Dự đoán bởi mô hình {self.model_path} ({top_label})."
                })
            except Exception as e:
                logger.warning(f"[FactCheckJudge] Lỗi khi infer transformer: {e}")
                return self._heuristic_judge(claim, evidence_spans, context)

        # Ưu tiên phán quyết:
        # 1. Nếu bất kỳ span nào chỉ ra CONTRADICT -> gán contradict
        contradict_results = [r for r in results if r["status"] == "contradict"]
        if contradict_results:
            return max(contradict_results, key=lambda x: x["confidence"])

        # 2. Nếu có span SUPPORT -> lấy span có confidence cao nhất
        support_results = [r for r in results if r["status"] == "support"]
        if support_results:
            return max(support_results, key=lambda x: x["confidence"])

        # 3. Ngược lại -> NOT_ENOUGH_INFO
        return results[0] if results else {
            "status": "not_enough_info",
            "confidence": 0.85,
            "evidence": "",
            "matched_keywords": [],
            "reason": "Không có span nào đủ thông tin chứng minh."
        }

    def _extract_and_expand_tokens(self, text: str) -> tuple[set[str], set[str], bool, set[str]]:
        """
        Trích xuất tokens, chuẩn hóa số liệu, phát hiện phủ định và nhận diện thực thể AI.
        Trả về (expanded_tokens, normalized_numbers, has_negation, matched_entities).
        """
        clean_text = text.lower()
        raw_numbers = re.findall(r"\b\d+(?:[,\.]\d+)?\b", clean_text)
        normalized_numbers = {n.replace(",", "").replace(".", "") for n in raw_numbers}

        words = set(re.findall(r"\w+", clean_text))
        has_neg = bool(words.intersection(self.NEGATION_WORDS_VN) or words.intersection(self.NEGATION_WORDS_EN))
        entities = words.intersection(self.AI_CORE_ENTITIES)

        expanded_words = set(words)
        for vn_key, en_list in self.BILINGUAL_MAP.items():
            if vn_key in clean_text:
                expanded_words.update(en_list)
            for en_word in en_list:
                if en_word in words:
                    expanded_words.add(vn_key)
                    expanded_words.update(en_list)

        return expanded_words, normalized_numbers, has_neg, entities

    def _heuristic_judge(self, claim: str, evidence_spans: list[str], context: str) -> dict[str, Any]:
        """
        Thuật toán Heuristic NLI chuyên sâu cho các bài báo khoa học máy tính và AI.
        """
        combined_evidence = " ".join(evidence_spans) if evidence_spans else context
        if not combined_evidence or not combined_evidence.strip():
            return {
                "status": "not_enough_info",
                "confidence": 0.95,
                "evidence": "Không có tài liệu hoặc chứng cứ trích dẫn.",
                "matched_keywords": [],
                "reason": "Thiếu hoàn toàn bằng chứng trích dẫn."
            }

        claim_tokens, claim_nums, claim_neg, claim_ents = self._extract_and_expand_tokens(claim)

        target_pool = evidence_spans if evidence_spans else [s.strip() for s in re.split(r"[.?!]\s+", context) if s.strip()]

        best_span = ""
        best_score = 0.0
        best_overlap_count = 0
        best_ev_neg = False
        best_ev_nums = set()
        best_matched_kws = []

        for span in target_pool:
            ev_tokens, ev_nums, ev_neg, ev_ents = self._extract_and_expand_tokens(span)
            
            overlap_set = claim_tokens.intersection(ev_tokens)
            token_overlap = len(overlap_set)
            score = token_overlap / max(len(claim_tokens), 1)

            # Thưởng điểm số liệu
            common_nums = claim_nums.intersection(ev_nums)
            if common_nums:
                score += 0.35

            # Thưởng điểm thực thể AI cốt lõi (LoRA, Transformer...)
            if claim_ents.intersection(ev_ents):
                score += 0.25

            if score > best_score:
                best_score = score
                best_overlap_count = token_overlap
                best_span = span
                best_ev_neg = ev_neg
                best_ev_nums = ev_nums
                best_matched_kws = list(overlap_set)

        # 1. Phát hiện CONTRADICT
        # TH A: Chia sẻ cùng chủ đề (score >= 0.18 hoặc overlap >= 3 từ khóa) nhưng mâu thuẫn phủ định
        if (best_score >= 0.18 or best_overlap_count >= 3) and (claim_neg != best_ev_neg):
            return {
                "status": "contradict",
                "confidence": 0.88,
                "evidence": best_span,
                "matched_keywords": best_matched_kws,
                "reason": "Mâu thuẫn khẳng định/phủ định giữa luận điểm và chứng cứ."
            }

        # TH B: Xung đột số liệu cụ thể
        if claim_nums and best_ev_nums and (best_score >= 0.25 or best_overlap_count >= 3):
            if not claim_nums.intersection(best_ev_nums):
                return {
                    "status": "contradict",
                    "confidence": 0.85,
                    "evidence": best_span,
                    "matched_keywords": best_matched_kws,
                    "reason": f"Xung đột số liệu: claim chứa {list(claim_nums)} nhưng evidence có {list(best_ev_nums)}."
                }

        # 2. Phán quyết SUPPORT
        if best_score >= 0.25 or (claim_nums and claim_nums.intersection(best_ev_nums) and best_score >= 0.18):
            return {
                "status": "support",
                "confidence": min(0.98, round(best_score + 0.2, 2)),
                "evidence": best_span,
                "matched_keywords": best_matched_kws,
                "reason": "Khớp thực thể và ngữ nghĩa khoa học với tài liệu nguồn."
            }

        # 3. Phán quyết NOT_ENOUGH_INFO
        return {
            "status": "not_enough_info",
            "confidence": 0.85,
            "evidence": best_span if best_score > 0.15 else "Không tìm thấy chứng cứ tương ứng.",
            "matched_keywords": best_matched_kws,
            "reason": "Độ tương đồng ngữ nghĩa dưới ngưỡng xác thực."
        }
