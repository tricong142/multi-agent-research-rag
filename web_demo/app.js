"use strict";

const actions = {
  search: "Retrieval",
  read: "Reader",
  summarize: "Summarizer",
  factcheck: "Fact-Checker",
  write: "Writer"
};
const statuses = {
  completed: "Hoàn tất",
  partial: "Báo cáo một phần",
  insufficient_evidence: "Thiếu bằng chứng",
  no_local_source: "Không tìm thấy PDF phù hợp",
  read_ready: "Đã đọc PDF",
  retrieved: "Đã truy xuất",
  summary_ready: "Đã gắn nguồn",
  summary_unverified: "Chưa đủ nguồn",
  verified: "Đã kiểm chứng",
  no_hits: "Không có kết quả",
  reader_failed: "Lỗi đọc PDF",
  retrieval_failed: "Lỗi truy xuất",
  summarizer_failed: "Lỗi tóm tắt",
  writer_failed: "Lỗi lập báo cáo",
  timed_out: "Hết thời gian"
};

const byId = id => document.getElementById(id);
const question = byId("question");
const pdfInput = byId("pdf-input");
const pdfPreview = byId("pdf-preview");
const run = byId("run");
const notice = byId("notice");
let liveReady = false;
let busy = false;

function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}

function badge(id, text) {
  const el = byId(id);
  el.hidden = !text;
  el.textContent = text || "";
}

async function request(url, options) {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Không nhận được kết quả.");
  return result;
}

function renderEvents(events) {
  const latest = new Map();
  const rows = [];
  for (const event of events) {
    const name = actions[event.action];
    if (!name) continue;
    const started = event.event === "tool_start";
    const status = started ? "Đang chạy" : statuses[event.status] || event.status;
    latest.set(event.action, {started, status});
    const duration = typeof event.elapsed_ms === "number" ? ` · ${event.elapsed_ms} ms` : "";
    rows.push(node("li", `Bước ${event.step} · ${name} · ${status}${duration}`));
  }
  byId("agents").replaceChildren(...Object.entries(actions).map(([key, name]) => {
    const event = latest.get(key);
    const card = node("div", undefined, event ? "agent observed" : "agent");
    card.append(node("strong", name), node("span", event?.status || "Chưa chạy"));
    return card;
  }));
  byId("events").replaceChildren(...(rows.length ? rows : [node("li", "Chưa có sự kiện agent.")]));
}

function renderReport(result) {
  badge("mode", result.mode === "saved_gpu" ? "Kết quả GPU lưu sẵn" : "Lượt chạy local");
  badge("result-status", statuses[result.graph_status] || result.graph_status);
  renderEvents(result.events);
  const target = byId("report");
  target.replaceChildren();
  if (result.paper) target.append(node("p", result.paper, "source-name"));
  for (const sentence of result.report.sentences) {
    const item = node("article", undefined, "sentence");
    item.append(node("p", sentence.text));
    for (const id of sentence.claim_ids) {
      const citation = result.claims[id];
      if (!citation) continue;
      const fold = node("details", undefined, "citation");
      fold.append(node("summary", `${id} · ${citation.title}${citation.page ? ` · trang PDF ${citation.page}` : ""}`));
      fold.append(node("p", citation.text, "claim-text"));
      fold.append(node("blockquote", citation.quote), node("code", citation.source_id));
      if (citation.url) {
        const link = node("a", "Mở PDF tại trang nguồn", "pdf-link");
        link.href = citation.url;
        link.target = "_blank";
        link.rel = "noopener";
        fold.append(link);
      }
      item.append(fold);
    }
    target.append(item);
  }
  if (result.report.limitations.length) {
    const list = node("ul", undefined, "limitation-list");
    for (const limit of result.report.limitations) list.append(node("li", limit));
    target.append(node("h3", "Giới hạn"), list);
  }
  if (typeof result.factcheck_calls === "number") {
    target.append(node("p", `Lượt gọi Agent 4: ${result.factcheck_calls}`, "muted"));
  }
  if (result.graph_errors?.length) target.append(node("p", result.graph_errors.join(" · "), "warning"));
}

function resetResult(mode) {
  badge("mode", mode);
  badge("result-status", "");
  byId("report").replaceChildren();
  renderEvents([]);
}

function setBusy(value) {
  busy = value;
  run.disabled = busy || !liveReady;
  pdfInput.disabled = busy;
  for (const button of byId("example-options").querySelectorAll("button")) button.disabled = busy;
}

function reportError(error) {
  badge("result-status", "Lỗi");
  byId("report").replaceChildren(node("p", error.message, "warning"));
}

pdfInput.addEventListener("change", () => {
  const previous = pdfPreview.getAttribute("href");
  if (previous) URL.revokeObjectURL(previous);
  pdfPreview.removeAttribute("href");
  pdfPreview.hidden = true;
  const error = byId("pdf-error");
  const file = pdfInput.files[0];
  if (file && (!file.name.toLowerCase().endsWith(".pdf") || file.size > 25 * 1024 * 1024)) {
    error.textContent = "Chọn file PDF tối đa 25 MiB.";
    error.hidden = false;
    pdfInput.value = "";
    return;
  }
  error.hidden = true;
  if (file) {
    pdfPreview.href = URL.createObjectURL(new Blob([file], {type: "application/pdf"}));
    pdfPreview.hidden = false;
  }
});

byId("query-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (busy || !liveReady) return;
  setBusy(true);
  resetResult("Lượt chạy local");
  byId("report").append(node("p", "Đang chọn PDF và nạp pipeline.", "muted"));
  try {
    const file = pdfInput.files[0];
    const payload = {method: "POST"};
    if (file) {
      payload.body = new FormData();
      payload.body.append("question", question.value);
      payload.body.append("pdf", file);
    } else {
      payload.headers = {"Content-Type": "application/json"};
      payload.body = JSON.stringify({question: question.value});
    }
    const {id} = await request("/api/run", payload);
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 700));
      const job = await request(`/api/run/${id}`);
      if (job.events) renderEvents(job.events);
      if (job.status === "done") {
        renderReport(job.result);
        break;
      }
      if (job.status === "failed") throw new Error(job.error);
      if (job.paper) byId("report").replaceChildren(node("p", `Đang xử lý ${job.paper}`, "muted"));
    }
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(false);
  }
});

async function initialize() {
  renderEvents([]);
  try {
    const config = await request("/api/status");
    liveReady = config.live_ready;
    const savedReady = config.saved_cases.length > 0;
    badge("runtime", liveReady || savedReady ? "Sẵn sàng chạy demo" : "Chưa có kết quả demo");
    notice.textContent = liveReady ? "Có thể chạy model trên máy này." :
      [savedReady ? "Dùng «Xem kết quả lưu sẵn» để trình bày demo." : "",
        config.problems.join(" "), "Bạn vẫn có thể chọn và xem trước PDF."].filter(Boolean).join(" ");
    for (const title of config.papers) byId("papers").append(node("li", title));
    byId("examples").hidden = !config.examples.length;
    for (const example of config.examples) {
      const row = node("div", undefined, "example");
      const use = node("button", example.question, "example-question");
      use.type = "button";
      use.addEventListener("click", () => {
        question.value = example.question;
        question.focus();
      });
      row.append(use);
      if (config.saved_cases.includes(example.id)) {
        const saved = node("button", "Xem kết quả lưu sẵn", "saved");
        saved.type = "button";
        saved.setAttribute("aria-label", `Xem kết quả lưu sẵn · ${example.id}`);
        saved.addEventListener("click", async () => {
          if (busy) return;
          setBusy(true);
          question.value = example.question;
          resetResult("Kết quả GPU lưu sẵn");
          try {
            renderReport(await request(`/api/saved/${encodeURIComponent(example.id)}`));
          } catch (error) {
            reportError(error);
          } finally {
            setBusy(false);
          }
        });
        row.append(saved);
      }
      byId("example-options").append(row);
    }
    setBusy(false);
  } catch (error) {
    badge("runtime", "Lỗi kết nối");
    notice.textContent = error.message;
  }
}

initialize();
