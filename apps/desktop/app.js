const app = document.querySelector("#app");
function defaultApiBase() {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) return configured;
  if (window.__TAURI_INTERNALS__ || location.protocol === "tauri:") return "http://127.0.0.1:8000";
  const hostname = location.hostname || "127.0.0.1";
  return `${location.protocol || "http:"}//${hostname}:8000`;
}
const API = defaultApiBase().replace(/\/$/, "");
const esc = value => String(value ?? "").replace(/[&<>\"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[char]));
const desktopInvoke = (command, args) => {
  const invoke = window.__TAURI_INTERNALS__?.invoke;
  return typeof invoke === "function" ? invoke(command, args) : null;
};
const showText = value => esc(String(value ?? "").replace(/\s+/g, " ").trim());
let mode = "review", oldFile = null, newFile = null, result = null, active = null, oldZoom = .7, newZoom = .7, showDiffPanel = true, scrollMode = "sync";
let ignoreWhitespace = true, ignoreCase = false, reviewFile = null, contractType = "", typeLoading = false, typeConfirmed = false, typeEditing = false, reviewLoading = false, reviewResult = "", reviewError = "", reviewPreview = null, reviewPreviewError = "", reviewAnnotations = [], reviewZoom = .7, reviewActive = null, reviewTab = "preview";
let caseFiles = [], activeCaseFileId = null, casesLoading = false, casesError = "";
let apiStatus = "starting";

function header() {
  const apiLabel = apiStatus === "ready" ? "API 服务" : apiStatus === "starting" ? "正在启动 API" : "API 服务不可用";
  return `<header class="top"><div class="brand"><small>CONTRACT REVIEW WORKSPACE 0.1.0</small><h1>标准合同 AI 预审工作台</h1></div><nav><button id="nav-review" class="${mode === "review" ? "active" : ""}">合同智审</button><button id="nav-compare" class="${mode === "compare" ? "active" : ""}">文档对比</button><button id="nav-cases" class="${mode === "cases" ? "active" : ""}">案例库</button></nav><span class="status">● ${apiLabel}</span></header>`;
}

function bindNavigation() {
  document.querySelector("#nav-review").onclick = () => { mode = "review"; renderReview(); };
  document.querySelector("#nav-compare").onclick = () => { mode = "compare"; uploadCompare(); };
  document.querySelector("#nav-cases").onclick = () => { mode = "cases"; renderCases(); void refreshCases(); };
}

async function refreshCases() {
  if (casesLoading) return;
  casesLoading = true;
  casesError = "";
  if (mode === "cases") renderCases();
  try {
    const response = await fetch(`${API}/api/v1/cases/database`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "案例库读取失败");
    caseFiles = Array.isArray(payload.items) ? payload.items : [];
    if (!caseFiles.some(file => file.id === activeCaseFileId)) activeCaseFileId = caseFiles[0]?.id || null;
  } catch (error) {
    caseFiles = [];
    activeCaseFileId = null;
    casesError = error?.message || "案例数据库读取失败";
  } finally {
    casesLoading = false;
  }
  if (mode === "cases") renderCases();
}

async function refreshApiStatus() {
  try {
    const response = await fetch(`${API}/health`, { cache: "no-store" });
    apiStatus = response.ok ? "ready" : "unavailable";
  } catch {
    apiStatus = "unavailable";
  }
  if (mode === "review") renderReview();
  else if (mode === "compare") uploadCompare();
  else renderCases();
}

function renderReview() {
  const output = reviewResult ? reviewWorkspaceHtml() : "";
  const typeContent = typeLoading ? `<b>正在识别...</b>` : typeEditing ? `<input id="contract-type-input" class="type-input" value="${esc(contractType)}" maxlength="200" placeholder="请输入合同类型"><button id="type-confirm" class="secondary" ${!contractType.trim() ? "disabled" : ""}>确认类型</button>` : `<b>${esc(contractType || "上传后自动识别")}</b>${reviewFile && !typeConfirmed ? `<button id="type-edit" class="text-button">${contractType ? "修改识别结果" : "手动输入合同类型"}</button>` : ""}${typeConfirmed ? `<span class="type-confirmed">已确认</span><button id="type-edit" class="text-button">修改识别结果</button>` : ""}`;
  app.innerHTML = `${header()}<main class="review-shell"><section class="review-card"><div class="section-title"><div><h2>合同智审</h2><p>上传合同后自动识别合同类型，识别完成即可开始智能审查；需要调整时点击“修改识别结果”。</p></div><span class="agent-status">Dify Agent</span></div><label class="review-upload"><strong>${reviewFile ? esc(reviewFile.name) : "选择合同文件"}</strong><span>${reviewFile ? `${(reviewFile.size / 1024).toFixed(1)} KB` : "支持 DOC、DOCX、PDF、JPG、PNG"}</span><input id="review-file" type="file" accept=".doc,.docx,.pdf,.jpg,.jpeg,.png"></label><div class="type-result"><span>合同类型</span><div class="type-value">${typeContent}</div></div><div class="review-actions"><button id="review-start" class="primary" ${!reviewFile || typeLoading || !typeConfirmed || reviewLoading ? "disabled" : ""}>${reviewLoading ? "正在分析合同..." : "开始合同智审"}</button></div>${reviewError ? `<p class="error">${esc(reviewError)}</p>` : ""}</section>${output}</main>`;
  bindNavigation();
  document.querySelector("#review-file").onchange = event => { reviewFile = event.target.files[0] || null; contractType = ""; typeConfirmed = false; typeEditing = false; reviewResult = ""; reviewPreview = null; reviewPreviewError = ""; reviewAnnotations = []; reviewError = ""; reviewLoading = false; if (reviewFile) { typeLoading = true; renderReview(); identifyType(); } else renderReview(); };
  document.querySelector("#review-start").onclick = runReview;
  document.querySelector("#type-confirm")?.addEventListener("click", () => { contractType = document.querySelector("#contract-type-input")?.value.trim() || contractType.trim(); if (contractType) { typeConfirmed = true; typeEditing = false; reviewResult = ""; reviewPreview = null; reviewAnnotations = []; reviewError = ""; renderReview(); } });
  document.querySelector("#type-edit")?.addEventListener("click", () => { typeEditing = true; typeConfirmed = false; reviewResult = ""; reviewPreview = null; reviewAnnotations = []; reviewError = ""; renderReview(); document.querySelector("#contract-type-input")?.focus(); });
  document.querySelector("#contract-type-input")?.addEventListener("input", event => { contractType = event.target.value; const button = document.querySelector("#type-confirm"); if (button) button.disabled = !contractType.trim(); });
  document.querySelector("#review-again")?.addEventListener("click", () => { reviewFile = null; contractType = ""; typeConfirmed = false; typeEditing = false; reviewResult = ""; reviewPreview = null; reviewPreviewError = ""; reviewAnnotations = []; renderReview(); });
  document.querySelector("#review-export")?.addEventListener("click", exportReviewReport);
  document.querySelectorAll("[data-review-tab]").forEach(tab => tab.onclick = () => { reviewTab = tab.dataset.reviewTab; renderReview(); });
  document.querySelector("#review-zoom")?.addEventListener("input", event => { reviewZoom = Number(event.target.value); renderReview(); });
  document.querySelectorAll("[data-review-zoom]").forEach(button => button.onclick = () => { const action = button.dataset.reviewZoom; reviewZoom = action === "out" ? Math.max(.5, +(reviewZoom - .1).toFixed(2)) : action === "in" ? Math.min(1.8, +(reviewZoom + .1).toFixed(2)) : .7; renderReview(); });
  document.querySelectorAll("[data-review-mark]").forEach(mark => mark.onclick = () => { reviewActive = Number(mark.dataset.reviewMark); document.querySelectorAll("[data-review-mark]").forEach(item => item.classList.toggle("selected", Number(item.dataset.reviewMark) === reviewActive)); });
  document.querySelectorAll("[data-review-locator]").forEach(item => item.onclick = () => { reviewActive = Number(item.dataset.reviewLocator); document.querySelectorAll("[data-review-mark], [data-review-locator]").forEach(node => node.classList.toggle("selected", Number(node.dataset.reviewMark || node.dataset.reviewLocator) === reviewActive)); document.querySelector(`.review-mark[data-review-mark="${reviewActive}"]`)?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }); });
}

function reviewWorkspaceHtml() {
  const isPreview = reviewTab === "preview";
  return `<section class="review-workspace"><nav class="review-tabs" role="tablist"><button class="${isPreview ? "active" : ""}" data-review-tab="preview">标注预览</button><button class="${!isPreview ? "active" : ""}" data-review-tab="report">分析报告</button></nav><section class="review-tab-panel ${isPreview ? "active" : ""}">${isPreview ? `<div class="review-preview-layout"><section class="review-preview-panel"><header><div><h2>原文标注预览</h2><span>${esc(reviewFile?.name || "合同文件")}</span></div><div class="preview-zoom"><button data-review-zoom="out" title="缩小">−</button><input id="review-zoom" type="range" min=".5" max="1.8" step=".05" value="${reviewZoom}"><span>${Math.round(reviewZoom * 100)}%</span><button data-review-zoom="in" title="放大">+</button></div></header>${reviewPreview ? reviewDocumentHtml(reviewPreview, reviewAnnotations) : `<p class="preview-empty">${esc(reviewPreviewError || "暂无原文预览")}</p>`}</section><aside class="review-locator"><header><h3>标注定位</h3><span>${reviewAnnotations.length} 处</span></header><div class="review-locator-list">${reviewAnnotations.length ? reviewAnnotations.map(item => `<button class="review-locator-item ${reviewActive === item.annotation_id ? "selected" : ""}" data-review-locator="${item.annotation_id}"><b>#${item.annotation_id}</b><span>第 ${item.page} 页</span><p>${esc(item.text || "原文建议位置")}</p></button>`).join("") : `<p class="preview-empty">暂无可定位标注</p>`}</div></aside></div>` : ""}</section><section class="review-tab-panel ${!isPreview ? "active" : ""}">${!isPreview ? `<section class="review-output"><header><div><h2>合同智审报告</h2><span>${esc(reviewFile?.name || "合同文件")} · ${esc(contractType || "合同")}</span></div><div class="review-output-actions"><button id="review-export" class="export-button">导出 TXT</button><button id="review-again">重新上传</button></div></header><article>${markdownToHtml(reviewResult)}</article></section>` : ""}</section></section>`;
}

function pageFrame(page, zoom) {
  const width = Math.max(1, Math.round(900 * zoom));
  const sourceWidth = Math.max(1, Number(page.width_px) || 1);
  const sourceHeight = Math.max(1, Number(page.height_px) || sourceWidth * Math.SQRT2);
  return { width, height: Math.max(1, Math.round(width * sourceHeight / sourceWidth)) };
}

function pageImageHtml(page, index, className = "") {
  const priority = index < 2 ? ` loading="eager" fetchpriority="high"` : ` loading="lazy"`;
  return `<img${className ? ` class="${className}"` : ""} src="${API}${page.url}" alt="第 ${page.page} 页" width="${page.width_px}" height="${page.height_px}" decoding="async"${priority}>`;
}

function reviewDocumentHtml(data, annotations) {
  return `<div class="review-document-scroll"><div class="review-document-pages">${data.pages.map((page, index) => { const frame = pageFrame(page, reviewZoom); return `<figure style="width:${frame.width}px;height:${frame.height}px">${pageImageHtml(page, index)}<div class="review-layers">${annotations.filter(item => item.page === page.page).map(item => { const box = item.box; const left = box.x0 / data.page_width_pt * 100, top = box.y0 / data.page_height_pt * 100, width = Math.max(.4, (box.x1 - box.x0) / data.page_width_pt * 100), height = Math.max(.7, (box.y1 - box.y0) / data.page_height_pt * 100); return `<button class="review-mark ${reviewActive === item.annotation_id ? "selected" : ""}" data-review-mark="${item.annotation_id}" title="${esc(item.text)}" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%"><i>${item.annotation_id}</i></button>`; }).join("")}</div><figcaption>${page.page} / ${data.page_count}</figcaption></figure>`; }).join("")}</div></div>`;
}

function markdownToHtml(value) {
  let html = esc(value).replace(/^###\s+(.+)$/gm, "<h3>$1</h3>").replace(/^##\s+(.+)$/gm, "<h2>$1</h2>").replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");
  html = html.replace(/^[-*]\s+(.+)$/gm, "<li>$1</li>").replace(/(<li>.*<\/li>\n?)+/g, block => `<ul>${block}</ul>`);
  return html.split(/\n{2,}/).map(block => block.startsWith("<h") || block.startsWith("<ul") ? block : `<p>${block.replace(/\n/g, "<br>")}</p>`).join("");
}

async function exportReviewReport() {
  if (!reviewResult) return;
  const sourceName = reviewFile?.name || "合同";
  const baseName = sourceName.replace(/\.[^.]+$/, "").replace(/[\\/:*?"<>|]+/g, "_") || "合同";
  const content = [`合同智审报告`, `文件：${sourceName}`, `合同类型：${contractType || "未识别"}`, `生成时间：${new Date().toLocaleString("zh-CN")}`, "", reviewResult].join("\n");
  const filename = `${baseName}-智审报告.txt`;
  const saveReport = desktopInvoke("save_review_report", { filename, content });
  if (saveReport) {
    try {
      const savedPath = await saveReport;
      window.alert(`报告已导出到：\n${savedPath}`);
    } catch (error) {
      window.alert(error?.message || "报告导出失败");
    }
    return;
  }

  const blob = new Blob(["\ufeff", content], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  const objectUrl = URL.createObjectURL(blob);
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function identifyType() {
  const form = new FormData(); form.append("file", reviewFile);
  try {
    const response = await fetch(`${API}/api/v1/contract/type`, { method: "POST", body: form });
    const body = await response.text();
    let payload;
    try { payload = body ? JSON.parse(body) : {}; } catch { throw new Error(`合同类型接口返回了无效响应 (${response.status}): ${body.slice(0, 200) || "空响应"}`); }
    if (!response.ok) throw new Error(payload.detail || "合同类型识别失败");
    contractType = payload.contract_type || "";
    typeConfirmed = Boolean(contractType.trim());
    typeEditing = false;
  } catch (error) { contractType = ""; reviewError = error.message || "合同类型识别失败"; }
  typeLoading = false; renderReview();
}

async function runReview() {
  if (!reviewFile || !typeConfirmed || !contractType.trim() || reviewLoading) return;
  reviewLoading = true; reviewError = ""; reviewPreviewError = ""; renderReview();
  const form = new FormData(); form.append("file", reviewFile); form.append("contract_type", contractType.trim());
  try {
    const response = await fetch(`${API}/api/v1/contract/review`, { method: "POST", body: form });
    const body = await response.text();
    let payload;
    try { payload = body ? JSON.parse(body) : {}; } catch { throw new Error(`合同智审接口返回了无效响应 (${response.status}): ${body.slice(0, 200) || "空响应"}`); }
    if (!response.ok) throw new Error(payload.detail || "合同智审失败");
    reviewResult = payload.review || "智能体未返回审查内容";
    reviewPreview = payload.preview || null;
    reviewPreviewError = payload.preview_error || "";
    reviewAnnotations = payload.annotations || [];
    reviewActive = reviewAnnotations[0]?.annotation_id ?? null;
  } catch (error) { reviewError = error.message || "合同智审失败"; }
  reviewLoading = false; renderReview();
}

function uploadCompare() {
  app.innerHTML = `${header()}<main class="form"><h2>文档内容对比</h2><p>上传旧版和新版文档，查看文档内容差异及其原文位置。</p><div class="files"><label><b>旧文档</b><span id="old-name">${oldFile ? esc(oldFile.name) : "选择文件"}</span><small>DOC、DOCX、PDF、JPG、PNG</small><input id="old" type="file" accept=".doc,.docx,.pdf,.jpg,.jpeg,.png"></label><label><b>新文档</b><span id="new-name">${newFile ? esc(newFile.name) : "选择文件"}</span><small>DOC、DOCX、PDF、JPG、PNG</small><input id="new" type="file" accept=".doc,.docx,.pdf,.jpg,.jpeg,.png"></label></div><div class="options"><label><input id="ws" type="checkbox" ${ignoreWhitespace ? "checked" : ""}> 忽略空格和换行差异</label><label><input id="ic" type="checkbox" ${ignoreCase ? "checked" : ""}> 忽略英文大小写</label><button id="start" ${!oldFile || !newFile ? "disabled" : ""}>开始对比</button></div><p id="error" class="error"></p></main>`;
  bindNavigation();
  document.querySelector("#old").onchange = event => { oldFile = event.target.files[0]; uploadCompare(); };
  document.querySelector("#new").onchange = event => { newFile = event.target.files[0]; uploadCompare(); };
  document.querySelector("#ws").onchange = event => { ignoreWhitespace = event.target.checked; };
  document.querySelector("#ic").onchange = event => { ignoreCase = event.target.checked; };
  document.querySelector("#start").onclick = compare;
}

async function compare() {
  if (!oldFile || !newFile) return;
  const button = document.querySelector("#start"); button.disabled = true; button.textContent = "正在生成预览并对比...";
  const form = new FormData(); form.append("old_file", oldFile); form.append("new_file", newFile); form.append("ignore_whitespace", String(ignoreWhitespace)); form.append("ignore_case", String(ignoreCase));
  try { const response = await fetch(`${API}/api/v1/compare`, { method: "POST", body: form }); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "文档对比失败"); result = payload.result; active = result.annotations[0]?.diff_id ?? null; oldZoom = .7; newZoom = .7; renderCompareResult(); }
  catch (error) { document.querySelector("#error").textContent = error.message || "文档对比失败"; button.disabled = false; button.textContent = "开始对比"; }
}

function parseCaseText(text) {
  return text.replace(/\r\n/g, "\n").split(/\n\s*\n+/).map(block => {
    const lines = block.split("\n").map(line => line.trim()).filter(Boolean);
    if (!lines.length) return null;
    const field = pattern => lines.find(line => pattern.test(line)) || "";
    const sourceLine = field(/^来源[：:]/), dateLine = field(/^日期[：:]/), linkLine = field(/^链接[：:]/), summaryLine = field(/^摘要[：:]/);
    const value = line => line.replace(/^[^：:]+[：:]\s*/, "").trim();
    const link = value(linkLine).match(/https?:\/\/[^\s\])]+/i)?.[0] || "";
    return { title: lines[0], source: value(sourceLine), date: value(dateLine), link, summary: value(summaryLine), raw: lines.filter(line => !/^(来源|日期|链接|摘要)[：:]/.test(line)).slice(1).join(" ") };
  }).filter(Boolean);
}

function parseCaseFile(text, filename) {
  try {
    const json = JSON.parse(text);
    const records = Array.isArray(json) ? json : Array.isArray(json.items) ? json.items : Array.isArray(json.cases) ? json.cases : null;
    if (records) return records.map((item, index) => ({ title: String(item.title || item.name || `案例 ${index + 1}`), source: String(item.source || item.source_name || ""), date: String(item.date || item.published_at || ""), link: String(item.link || item.url || ""), summary: String(item.summary || item.content || ""), raw: "" }));
  } catch { /* Plain text is the normal LegalNewsAlerts export format. */ }
  return parseCaseText(text);
}

function activeCaseFile() { return caseFiles.find(item => item.id === activeCaseFileId) || null; }

function caseLink(url) {
  try { const safe = new URL(url); return /^https?:$/.test(safe.protocol) ? `<button type="button" class="case-open-link" data-case-open-url="${esc(safe.href)}">打开原文</button>` : ""; }
  catch { return ""; }
}

async function openCaseLink(event) {
  const url = event.currentTarget.dataset.caseOpenUrl;
  try {
    const safe = new URL(url);
    if (!/^https?:$/.test(safe.protocol)) throw new Error("链接地址无效");
    const openExternal = desktopInvoke("open_external_url", { url: safe.href });
    if (openExternal) {
      await openExternal;
      return;
    }
    if (!window.open(safe.href, "_blank", "noopener,noreferrer")) throw new Error("浏览器阻止了新窗口");
  } catch (error) {
    window.alert(error?.message || "无法打开原文链接");
  }
}

function renderCases() {
  const selected = activeCaseFile();
  const sidebar = casesLoading
    ? `<p class="case-empty">正在读取数据库...</p>`
    : caseFiles.length
      ? caseFiles.map(file => `<div class="case-file-row ${file.id === activeCaseFileId ? "active" : ""}"><button class="case-file-select" data-case-file="${esc(file.id)}"><b>${esc(file.name)}</b><span>${file.items.length} 条案例</span></button></div>`).join("")
      : `<p class="case-empty">${esc(casesError || "数据库中暂无案例")}</p>`;
  const content = casesLoading
    ? `<div class="case-empty-state"><h2>正在读取案例</h2></div>`
    : casesError
      ? `<div class="case-empty-state"><h2>案例库读取失败</h2><p>${esc(casesError)}</p><button class="case-sync" id="case-refresh-empty">重新加载</button></div>`
      : selected
        ? selected.items.length
          ? selected.items.map((item, index) => `<article class="case-card"><header><span class="case-index">${String(index + 1).padStart(2, "0")}</span><div><h2>${esc(item.title)}</h2><p>${[item.source, item.date].filter(Boolean).map(esc).join(" · ") || "未提供来源和日期"}</p></div></header>${item.summary ? `<p class="case-summary">${esc(item.summary)}</p>` : ""}${item.raw ? `<p class="case-raw">${esc(item.raw)}</p>` : ""}${item.link ? `<footer>${caseLink(item.link)}<span>${esc(item.link)}</span></footer>` : ""}</article>`).join("")
          : `<div class="case-empty-state"><h2>当前日期暂无案例</h2></div>`
        : `<div class="case-empty-state"><h2>数据库中暂无案例</h2></div>`;
  app.innerHTML = `${header()}<main class="cases-shell"><aside class="case-sidebar"><div class="case-sidebar-head"><div><h2>案例数据</h2><span>${caseFiles.length} 个日期</span></div></div><div class="case-file-list">${sidebar}</div></aside><section class="case-content"><header class="case-content-head"><div><h1>案例库</h1><p>${selected ? `${esc(selected.name)} · ${selected.items.length} 条案例` : "从数据库读取案例"}</p></div><div><button class="case-sync" id="case-refresh" ${casesLoading ? "disabled" : ""}>刷新</button>${selected ? `<span class="case-count">${selected.items.length}</span>` : ""}</div></header><div class="case-list">${content}</div></section></main>`;
  bindNavigation();
  document.querySelectorAll("[data-case-file]").forEach(button => button.onclick = () => { activeCaseFileId = button.dataset.caseFile; renderCases(); });
  document.querySelector("#case-refresh")?.addEventListener("click", refreshCases);
  document.querySelector("#case-refresh-empty")?.addEventListener("click", refreshCases);
  document.querySelectorAll("[data-case-open-url]").forEach(button => button.onclick = openCaseLink);
}

function markHtml(annotation, side, page, data) {
  const marks = annotation.page_marks.filter(item => item.side === side && item.page === page);
  return marks.map((mark, index) => {
    if (!mark.box) return `<button class="mark pin ${annotation.kind} ${active === annotation.diff_id ? "selected" : ""}" data-mark-id="${annotation.diff_id}">${annotation.diff_id}</button>`;
    const box = mark.box;
    const padX = .35, padY = .35;
    const rawLeft = box.x0 / data.page_width_pt * 100, rawTop = box.y0 / data.page_height_pt * 100;
    const left = Math.max(0, rawLeft - padX), top = Math.max(0, rawTop - padY);
    const width = Math.min(100 - left, Math.max(.4, (box.x1 - box.x0) / data.page_width_pt * 100 + padX * 2));
    const height = Math.min(100 - top, Math.max(.7, (box.y1 - box.y0) / data.page_height_pt * 100 + padY * 2));
    const label = index === 0 ? `<i>${annotation.diff_id}</i>` : "";
    return `<button class="mark ${annotation.kind} ${active === annotation.diff_id ? "selected" : ""}" data-mark-id="${annotation.diff_id}" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%">${label}</button>`;
  }).join("");
}

function zoomControl(side, value) { return `<div class="preview-zoom" aria-label="${side === "old" ? "旧文档" : "新文档"}缩放"><button data-zoom-action="out" data-zoom-side="${side}" title="缩小" aria-label="缩小">−</button><button data-zoom-action="in" data-zoom-side="${side}" title="放大" aria-label="放大">+</button><input data-zoom-input="${side}" type="range" min=".5" max="1.8" step=".05" value="${value}" aria-label="缩放比例"><span data-zoom-value="${side}">${Math.round(value * 100)}%</span></div>`; }

function preview(side, data) { const value = side === "old" ? oldZoom : newZoom; return `<section class="preview"><header><div><small>${side === "old" ? "旧文档" : "新文档"}</small><b>${esc(data.filename)}</b></div><div class="preview-meta"><span>${data.page_count} 页 · ${data.ext.toUpperCase()}</span>${zoomControl(side, value)}</div></header><div class="scroll" id="scroll-${side}"><div class="pages">${data.pages.map((page, index) => { const frame = pageFrame(page, value); return `<figure style="width:${frame.width}px;height:${frame.height}px">${pageImageHtml(page, index)}<div class="layers">${result.annotations.map(annotation => markHtml(annotation, side, page.page, data)).join("")}</div><figcaption>${page.page} / ${data.page_count}</figcaption></figure>`; }).join("")}</div></div></section>`; }

function renderCompareResult() {
  app.innerHTML = `<div class="result ${showDiffPanel ? "" : "diff-hidden"}">${header()}<header class="result-head"><div><h1>文档内容对比</h1><p>忽略字体、粗体、斜体等格式，仅标记文本内容差异。</p></div><div class="result-actions"><label class="scroll-mode"><span>滑动方式</span><select id="scroll-mode" aria-label="文档滑动方式"><option value="sync" ${scrollMode === "sync" ? "selected" : ""}>同步滑动</option><option value="async" ${scrollMode === "async" ? "selected" : ""}>异步滑动</option></select></label><button id="toggle-diff" aria-expanded="${showDiffPanel}">${showDiffPanel ? "隐藏差异" : "显示差异"}</button><button id="again">重新对比</button></div></header><main><div class="previews">${preview("old", result.old)}${preview("new", result.new)}</div><aside class="diff" aria-hidden="${!showDiffPanel}"><h2>内容差异 <small>${result.annotations.length} 处</small></h2>${result.annotations.map(annotation => `<button class="item ${annotation.diff_id === active ? "selected" : ""}" data-id="${annotation.diff_id}"><b>#${annotation.diff_id}</b><em>${annotation.kind === "added" ? "新增" : annotation.kind === "removed" ? "删除" : "修改"}</em>${annotation.old_text ? `<del>− ${showText(annotation.old_text)}</del>` : ""}${annotation.new_text ? `<ins>+ ${showText(annotation.new_text)}</ins>` : ""}</button>`).join("")}</aside></main></div>`;
  bindNavigation(); document.querySelector("#again").onclick = uploadCompare;
  document.querySelector("#toggle-diff").onclick = () => { showDiffPanel = !showDiffPanel; renderCompareResult(); };
  document.querySelector("#scroll-mode").onchange = event => {
    scrollMode = event.target.value;
    bindScrollSync();
  };
  document.querySelectorAll("[data-zoom-input]").forEach(input => input.oninput = event => { const side = event.target.dataset.zoomInput; if (side === "old") oldZoom = Number(event.target.value); else newZoom = Number(event.target.value); renderCompareResult(); });
  document.querySelectorAll("[data-zoom-action]").forEach(button => button.onclick = () => { const side = button.dataset.zoomSide; const current = side === "old" ? oldZoom : newZoom; const next = button.dataset.zoomAction === "out" ? Math.max(.5, +(current - .1).toFixed(2)) : button.dataset.zoomAction === "in" ? Math.min(1.8, +(current + .1).toFixed(2)) : .7; if (side === "old") oldZoom = next; else newZoom = next; renderCompareResult(); });
  document.querySelectorAll(".item").forEach(item => item.onclick = () => selectDiff(Number(item.dataset.id))); document.querySelectorAll(".mark").forEach(mark => mark.onclick = event => { event.stopPropagation(); selectDiff(Number(mark.dataset.markId)); }); bindScrollSync();
}

function selectDiff(id) { active = id; document.querySelectorAll(".item").forEach(item => item.classList.toggle("selected", Number(item.dataset.id) === id)); document.querySelectorAll(".mark").forEach(mark => mark.classList.toggle("selected", Number(mark.dataset.markId) === id)); document.querySelector(`.mark[data-mark-id="${id}"]`)?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }); }
function bindScrollSync() { const oldScroll = document.querySelector("#scroll-old"), newScroll = document.querySelector("#scroll-new"); if (!oldScroll || !newScroll) return; oldScroll.onscroll = null; newScroll.onscroll = null; if (scrollMode !== "sync") return; let locked = false; const sync = (from, to) => { if (locked) return; locked = true; to.scrollTop = from.scrollTop / Math.max(1, from.scrollHeight - from.clientHeight) * Math.max(0, to.scrollHeight - to.clientHeight); to.scrollLeft = from.scrollLeft / Math.max(1, from.scrollWidth - from.clientWidth) * Math.max(0, to.scrollWidth - to.clientWidth); requestAnimationFrame(() => { locked = false; }); }; oldScroll.onscroll = () => sync(oldScroll, newScroll); newScroll.onscroll = () => sync(newScroll, oldScroll); }

renderReview();
void refreshCases();
setTimeout(refreshApiStatus, 500);
