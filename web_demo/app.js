/**
 * Multi-Agent Research RAG - Interactive Web Application Logic
 * Pure Vanilla JavaScript - High Performance & Dynamic Animations
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const presetsList = document.getElementById('presets-list');
  const questionInput = document.getElementById('question-input');
  const btnRun = document.getElementById('btn-run-query');
  const enableLiveSteps = document.getElementById('enable-live-steps');
  const selectedBadge = document.getElementById('selected-scenario-badge');
  const currentCycleStatus = document.getElementById('current-cycle-status');
  const stepCounter = document.getElementById('step-counter');
  const eventStreamContainer = document.getElementById('event-stream-container');
  
  // Tabs & panels
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');
  
  // Detail containers
  const reportContainer = document.getElementById('report-view-container');
  const retrievalContainer = document.getElementById('retrieval-detail-content');
  const readerContainer = document.getElementById('reader-detail-content');
  const summarizerContainer = document.getElementById('summarizer-detail-content');
  const factcheckerContainer = document.getElementById('factchecker-detail-content');
  const writerContainer = document.getElementById('writer-detail-content');
  const jsonViewer = document.getElementById('json-state-viewer');
  const btnCopyState = document.getElementById('btn-copy-state');
  
  // State
  let presetsData = [];
  let selectedPresetId = null;
  let currentResearchState = null;

  // =========================================================================
  // Initialize Studio & Load Presets
  // =========================================================================

  async function initStudio() {
    try {
      const res = await fetch('/api/presets');
      if (!res.ok) throw new Error('Không thể nạp danh sách presets');
      presetsData = await res.json();
      renderPresets();
      
      // Auto-select first preset
      if (presetsData.length > 0) {
        selectPreset(presetsData[0]);
      }
    } catch (err) {
      console.warn('Fallback to local presets:', err);
      showToast('Đang kết nối backend server...');
    }
  }

  function renderPresets() {
    presetsList.innerHTML = '';
    presetsData.forEach((preset) => {
      const card = document.createElement('div');
      card.className = `preset-card ${selectedPresetId === preset.id ? 'selected' : ''}`;
      card.id = `preset-${preset.id}`;
      card.innerHTML = `
        <div class="preset-header">
          <span class="preset-title">${preset.title}</span>
          <span class="preset-badge ${preset.badge_color}">${preset.badge}</span>
        </div>
        <div class="preset-paper">&#128214; ${preset.paper}</div>
      `;
      card.addEventListener('click', () => selectPreset(preset));
      presetsList.appendChild(card);
    });
  }

  function selectPreset(preset) {
    selectedPresetId = preset.id;
    questionInput.value = preset.question;
    selectedBadge.textContent = preset.category;
    
    // Update card selection styles
    document.querySelectorAll('.preset-card').forEach((el) => el.classList.remove('selected'));
    const activeEl = document.getElementById(`preset-${preset.id}`);
    if (activeEl) activeEl.classList.add('selected');
  }

  // =========================================================================
  // Tab Navigation Handling
  // =========================================================================

  tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');
      switchTab(targetId);
    });
  });

  function switchTab(tabId) {
    tabButtons.forEach((b) => b.classList.remove('active'));
    tabPanels.forEach((p) => p.classList.remove('active'));

    const activeBtn = document.querySelector(`[data-tab="${tabId}"]`);
    const activePanel = document.getElementById(tabId);
    if (activeBtn) activeBtn.classList.add('active');
    if (activePanel) activePanel.classList.add('active');
  }

  // =========================================================================
  // Interactive Flow Execution & Animation
  // =========================================================================

  btnRun.addEventListener('click', handleRunWorkflow);

  async function handleRunWorkflow() {
    const question = questionInput.value.trim();
    if (!question) {
      showToast('Vui lòng nhập câu hỏi nghiên cứu.');
      questionInput.focus();
      return;
    }

    setRunningState(true);
    resetTopologyNodes();
    eventStreamContainer.innerHTML = '<div class="empty-state">Khởi tạo đồ thị LangGraph StateGraph...</div>';
    currentCycleStatus.textContent = 'Trạng thái: Đang phân giải luồng điều phối...';

    const useAnimation = enableLiveSteps.checked;

    try {
      if (useAnimation) {
        animateNodeSequence();
      }

      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: question,
          preset_id: selectedPresetId
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || 'Lỗi thực thi đồ thị Agent');
      }

      const data = await res.json();
      currentResearchState = data;

      // Render all panels
      renderExecutionResults(data);
      completeTopologyNodes();
      
      currentCycleStatus.textContent = `Hoàn thành luồng (Tổng thời gian: ${data.total_time_ms} ms &middot; ${data.steps_used} steps)`;
      stepCounter.textContent = `${data.steps_used} steps &middot; ${data.total_time_ms} ms`;
      showToast('Thực thi 5-Agent thành công!');

      // Switch to final report tab
      switchTab('tab-report');

    } catch (err) {
      console.error(err);
      showToast(`Lỗi: ${err.message}`);
      currentCycleStatus.textContent = `Lỗi thực thi: ${err.message}`;
      markTopologyError();
    } finally {
      setRunningState(false);
    }
  }

  function setRunningState(isRunning) {
    btnRun.disabled = isRunning;
    questionInput.disabled = isRunning;
    if (isRunning) {
      btnRun.innerHTML = `
        <span class="pulse-dot"></span>
        <span>Đang chạy 5 Agents...</span>
      `;
    } else {
      btnRun.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        <span>Chạy luồng 5 Agent</span>
      `;
    }
  }

  // =========================================================================
  // Topology Animation Effects
  // =========================================================================

  function resetTopologyNodes() {
    const nodes = document.querySelectorAll('.flow-node');
    nodes.forEach((n) => {
      n.className = 'flow-node';
    });
  }

  function animateNodeSequence() {
    const sequence = [
      { id: 'node-controller', delay: 100 },
      { id: 'node-retrieval', delay: 350 },
      { id: 'node-reader', delay: 650 },
      { id: 'node-summarizer', delay: 950 },
      { id: 'node-factchecker', delay: 1250 },
      { id: 'node-writer', delay: 1550 },
      { id: 'node-controller', delay: 1850 }
    ];

    sequence.forEach(({ id, delay }) => {
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) {
          el.classList.add('executing');
          setTimeout(() => el.classList.remove('executing'), 400);
        }
      }, delay);
    });
  }

  function completeTopologyNodes() {
    const nodeIds = ['node-controller', 'node-retrieval', 'node-reader', 'node-summarizer', 'node-factchecker', 'node-writer'];
    nodeIds.forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.className = 'flow-node completed';
      }
    });
  }

  function markTopologyError() {
    const nodes = document.querySelectorAll('.flow-node');
    nodes.forEach((n) => n.classList.add('error'));
  }

  // =========================================================================
  // Render Execution Results to Tabs
  // =========================================================================

  function renderExecutionResults(data) {
    // 1. Render Event Stream
    renderEvents(data.events);

    // 2. Render Final Report
    renderFinalReport(data.final_report, data.low_confidence_warning, data.status, data);

    // 3. Render Agent Details
    renderRetrievalDetail(data.node_traces.retrieval);
    renderReaderDetail(data.node_traces.reader);
    renderSummarizerDetail(data.node_traces.summarizer);
    renderFactcheckerDetail(data.node_traces.factchecker);
    renderWriterDetail(data.node_traces.writer);

    // 4. Render State JSON
    jsonViewer.textContent = JSON.stringify(data, null, 2);
  }

  function renderEvents(events) {
    if (!events || events.length === 0) {
      eventStreamContainer.innerHTML = '<div class="empty-state">Không có sự kiện nào được ghi nhận.</div>';
      return;
    }

    eventStreamContainer.innerHTML = '';
    events.forEach((ev) => {
      const div = document.createElement('div');
      div.className = `event-entry ${ev.event || ''}`;
      
      let desc = '';
      if (ev.event === 'decision') {
        desc = `Hành động: <strong>${ev.action}</strong> &middot; Lý do: ${ev.reason}`;
      } else if (ev.event === 'agent_result') {
        desc = `Kết quả ${ev.action}: trạng thái <strong>${ev.status}</strong> &middot; ${ev.evidence_count} evidence chunks (${ev.elapsed_ms} ms)`;
      } else if (ev.event === 'tool_start') {
        desc = `Gọi tool/agent: <strong>${ev.action}</strong> (Step ${ev.step})`;
      } else {
        desc = JSON.stringify(ev);
      }

      div.innerHTML = `
        <div class="event-top">
          <span class="event-type">${ev.event.toUpperCase()}</span>
          <span class="event-time">${ev.elapsed_ms ? ev.elapsed_ms + ' ms' : ''}</span>
        </div>
        <div class="event-desc">${desc}</div>
      `;
      eventStreamContainer.appendChild(div);
    });

    eventStreamContainer.scrollTop = eventStreamContainer.scrollHeight;
  }

  function renderFinalReport(report, isLowConfidence, status, data) {
    if (!report) {
      reportContainer.innerHTML = '<div class="empty-state large">Báo cáo rỗng hoặc không có câu nào được kiểm chứng.</div>';
      return;
    }

    const question = (data && data.question) || 'Nghiên cứu khoa học';
    const presetTitle = (data && data.preset && data.preset.title) || 'Báo cáo tổng hợp tri thức';

    const hasSentences = report.sentences && report.sentences.length > 0;
    const badgeClass = (!hasSentences || isLowConfidence) ? 'report-header-badge warning' : 'report-header-badge';
    const badgeText = (!hasSentences)
      ? '&#9888; Cảnh báo: Không đủ dữ liệu chứng minh (Abstention Mode)'
      : (isLowConfidence 
          ? '&#9888; Low Confidence Warning (Có giới hạn kiểm chứng)' 
          : '&#10003; 100% Verified Scientific Claims Pool');

    let sentencesHtml = '';
    if (hasSentences) {
      report.sentences.forEach((s) => {
        sentencesHtml += `
          <div class="report-sentence-item">
            <span class="sentence-check-icon">&#10004;</span>
            <div class="sentence-text">
              ${s.text}
              <span class="sentence-citation">[verified &middot; ${s.sentence_id}]</span>
            </div>
          </div>
        `;
      });
    } else {
      sentencesHtml = `
        <div style="background: rgba(245,158,11,0.08); border: 1px dashed rgba(245,158,11,0.3); border-radius: 8px; padding: 18px; margin-bottom: 16px;">
          <p style="font-size: 0.9rem; color: #FCD34D; line-height: 1.6;">
            <strong>Chế độ từ chối an toàn (Safety Abstention):</strong> Hệ thống không tìm thấy đủ bằng chứng nguyên văn hoặc phát hiện mâu thuẫn trong kho ngữ liệu để khẳng định mệnh đề này. Không có câu nào được đưa vào báo cáo để ngăn ngừa ảo giác (Hallucination).
          </p>
        </div>
      `;
    }

    let limitationsHtml = '';
    if (report.limitations && report.limitations.length > 0) {
      limitationsHtml = `
        <div class="limitations-box">
          <div class="limitations-title">&#9888; Giới hạn &amp; Ghi chú độ tin cậy (Limitations &amp; Boundary):</div>
          <ul class="limitations-list">
            ${report.limitations.map((l) => `<li>${l}</li>`).join('')}
          </ul>
        </div>
      `;
    }

    const verifiedCount = (data && data.verified_claims) ? data.verified_claims.length : 0;
    const statsBadge = verifiedCount > 0 
      ? `<span style="font-family: var(--font-mono); font-size: 0.75rem; color: #34D399; margin-left: 10px;">(${verifiedCount} claims đã qua Fact-Checker)</span>`
      : '';

    reportContainer.innerHTML = `
      <div class="report-card">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
          <span class="${badgeClass}">${badgeText}</span>
          ${statsBadge}
        </div>
        <h3 class="report-title">${presetTitle}</h3>
        <p style="font-size: 0.85rem; color: #94A3B8; margin-bottom: 18px; border-left: 2px solid var(--accent-indigo); padding-left: 10px;">
          <strong>Chủ đề nghiên cứu:</strong> ${question}
        </p>
        <div class="report-sentences-list">
          ${sentencesHtml}
        </div>
        ${limitationsHtml}
      </div>
    `;
  }

  function renderRetrievalDetail(trace) {
    if (!trace || !trace.chunks) {
      retrievalContainer.innerHTML = '<div class="empty-state">Chưa có lượt truy xuất nào.</div>';
      return;
    }

    let chunksHtml = '';
    trace.chunks.forEach((c) => {
      chunksHtml += `
        <div class="chunk-card">
          <div class="chunk-header">
            <span class="chunk-source">&#128196; Nguồn: ${c.source_id} (${c.doc_id})</span>
            <span class="chunk-score">Độ tương đồng: ${(c.score * 100).toFixed(1)}%</span>
          </div>
          <div class="chunk-body">${c.text}</div>
        </div>
      `;
    });

    retrievalContainer.innerHTML = `
      <div style="margin-bottom: 14px;">
        <p style="font-size: 0.85rem; color: var(--text-muted);">
          Chính sách định tuyến: <strong style="color: #fff;">${trace.decision.toUpperCase()}</strong> &middot; 
          Chỉ mục: <strong style="color: var(--accent-cyan);">${trace.index_type}</strong> &middot; 
          Thời gian: <span style="font-family: var(--font-mono); color: #34D399;">${trace.latency_ms} ms</span>
        </p>
      </div>
      <div>${chunksHtml}</div>
    `;
  }

  function renderReaderDetail(trace) {
    if (!trace || !trace.detected_blocks) {
      readerContainer.innerHTML = '<div class="empty-state">PDF Reader không được kích hoạt trong lượt này.</div>';
      return;
    }

    let blocksHtml = trace.detected_blocks.map((b) => `
      <div style="background: rgba(15,23,42,0.4); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 8px;">
        <span style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--accent-violet);">Khối [${b.type}]:</span>
        <span style="font-size: 0.8rem; color: #CBD5E1; margin-left: 8px;">BoundingBox: [${b.bbox.join(', ')}] &middot; Confidence: ${(b.confidence * 100).toFixed(1)}%</span>
      </div>
    `).join('');

    readerContainer.innerHTML = `
      <div style="margin-bottom: 12px; font-size: 0.85rem; color: var(--text-muted);">
        Công cụ: <strong style="color: #fff;">${trace.engine}</strong> &middot; 
        Trang đã đọc: <span style="color: var(--accent-violet); font-family: var(--font-mono);">${trace.read_pages.join(', ')}</span>
      </div>
      <div>${blocksHtml}</div>
    `;
  }

  function renderSummarizerDetail(trace) {
    if (!trace || !trace.draft_answer) {
      summarizerContainer.innerHTML = '<div class="empty-state">Chưa có kết quả từ Summarizer.</div>';
      return;
    }

    let verbatimHtml = trace.verbatim_check.map((v) => `
      <div class="verbatim-span-item">
        <strong>&#10003; Verbatim Span Grounded:</strong> "${v.span}" 
        <span style="color: var(--text-muted); font-size: 0.72rem; margin-left: 8px;">(Offset: ${v.offset_start})</span>
      </div>
    `).join('');

    summarizerContainer.innerHTML = `
      <div style="margin-bottom: 14px;">
        <span style="font-size: 0.85rem; color: var(--text-muted);">Mô hình: <strong style="color: #fff;">${trace.model}</strong> &middot; 
        Độ tin cậy: <strong style="color: #34D399;">${trace.confidence.toUpperCase()}</strong> &middot;
        Thời gian: <span style="font-family: var(--font-mono); color: #34D399;">${trace.latency_ms} ms</span></span>
      </div>
      <div style="background: rgba(15,23,42,0.6); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 14px; margin-bottom: 14px;">
        <div style="font-size: 0.78rem; font-weight: 600; color: var(--accent-sky); margin-bottom: 6px;">Bản thảo sơ bộ (Draft Answer):</div>
        <div style="font-size: 0.9rem; color: #fff; line-height: 1.6;">${trace.draft_answer}</div>
      </div>
      <div>
        <div style="font-size: 0.78rem; font-weight: 600; color: #34D399; margin-bottom: 8px;">Kiểm tra Verbatim Evidence Gate:</div>
        ${verbatimHtml}
      </div>
    `;
  }

  function renderFactcheckerDetail(trace) {
    if (!trace || !trace.claim) {
      factcheckerContainer.innerHTML = '<div class="empty-state">Chưa có dữ liệu từ Fact-Checker.</div>';
      return;
    }

    const badgeColor = trace.label === 'support' ? '#34D399' : '#FB7185';

    factcheckerContainer.innerHTML = `
      <div style="margin-bottom: 14px;">
        <span style="font-size: 0.85rem; color: var(--text-muted);">Mô hình: <strong style="color: #fff;">${trace.model}</strong></span>
      </div>
      <div style="background: rgba(15,23,42,0.6); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 14px; margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 0.78rem; font-weight: 600; color: var(--accent-emerald);">Mệnh đề kiểm tra:</span>
          <span style="font-family: var(--font-mono); font-size: 0.8rem; font-weight: 700; color: ${badgeColor}; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.05); border: 1px solid ${badgeColor};">
            VERDICT: ${trace.label.toUpperCase()} (${(trace.confidence_score * 100).toFixed(1)}%)
          </span>
        </div>
        <div style="font-size: 0.9rem; color: #fff; line-height: 1.5;">${trace.claim}</div>
        <div class="math-trace-box">&#128225; <strong>Decimal Arithmetic Trace:</strong> ${trace.math_trace}</div>
      </div>
    `;
  }

  function renderWriterDetail(trace) {
    if (!trace || !trace.critic_reviews) {
      writerContainer.innerHTML = '<div class="empty-state">Chưa có dữ liệu từ Writer.</div>';
      return;
    }

    let reviewsHtml = trace.critic_reviews.map((r) => `
      <div style="background: rgba(15,23,42,0.5); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-family: var(--font-mono); font-size: 0.78rem; color: #fff;">[${r.sentence_id}] Phán quyết Critic: <strong style="color: #34D399;">${r.verdict.toUpperCase()}</strong></span>
        <span style="font-size: 0.75rem; color: var(--text-muted);">${r.reason}</span>
      </div>
    `).join('');

    writerContainer.innerHTML = `
      <div style="margin-bottom: 14px;">
        <span style="font-size: 0.85rem; color: var(--text-muted);">Mô hình: <strong style="color: #fff;">${trace.model}</strong> &middot; 
        Vòng lặp sửa đổi: <strong style="color: var(--accent-amber);">${trace.internal_retries}/${trace.max_internal_retries}</strong> &middot; 
        Hành động: <strong style="color: #fff;">${trace.action_selected.toUpperCase()}</strong></span>
      </div>
      <div>${reviewsHtml}</div>
    `;
  }

  // =========================================================================
  // Copy JSON State & Toast Helper
  // =========================================================================

  btnCopyState.addEventListener('click', () => {
    if (!currentResearchState) {
      showToast('Chưa có state để sao chép.');
      return;
    }
    navigator.clipboard.writeText(JSON.stringify(currentResearchState, null, 2))
      .then(() => showToast('Đã sao chép State JSON vào clipboard!'))
      .catch(() => showToast('Không thể sao chép JSON.'));
  });

  function showToast(msg) {
    const toastContainer = document.getElementById('toast');
    const toast = document.createElement('div');
    toast.className = 'toast-message';
    toast.textContent = msg;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 2800);
  }

  // Start initialization
  initStudio();
});
