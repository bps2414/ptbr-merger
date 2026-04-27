let currentPlan = null;
let lastPlanPayload = null;
let lastResultPayload = null;
let installPollTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function node(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const target = node(id);
  if (target) target.textContent = value;
}

function renderJson(id, payload) {
  setText(id, JSON.stringify(payload, null, 2));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderError(id, error) {
  renderJson(id, { status: "ERROR", message: error.message || String(error) });
}

function option(label, value) {
  const item = document.createElement("option");
  item.textContent = label;
  item.value = value;
  return item;
}

function selectedOrTyped(selectId, inputId) {
  const typed = node(inputId).value.trim();
  if (typed) return typed;
  return node(selectId).value;
}

function switchScreen(screen) {
  document.querySelectorAll(".screen").forEach((section) => {
    section.classList.toggle("active", section.id === `screen-${screen}`);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.screen === screen);
  });
}

function applyTheme(theme) {
  const value = theme || "system";
  localStorage.setItem("ptbrmerger-theme", value);
  document.documentElement.dataset.theme = value;
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.classList.toggle("active", button.dataset.themeChoice === value);
  });
}

function stateLabel(status) {
  const value = String(status || "").toUpperCase();
  if (value === "OK") return "Pronto";
  if (value === "WARN") return "Atenção";
  if (value === "BLOCKER") return "Pendente";
  return status || "Desconhecido";
}

function friendlyDependencyLine(dep, label) {
  if (!dep) return `${label}: não verificado`;
  if (dep.available) {
    return `${label}: pronto (${dep.version || dep.resolved_path || "detectado"})`;
  }
  return `${label}: precisa configurar`;
}

function renderDependencyStatus(payload) {
  const status = node("dependency-status");
  const alert = node("dependency-alert");
  const ready = Boolean(payload && payload.ready);
  const lines = [
    friendlyDependencyLine(payload.ffmpeg, "FFmpeg"),
    friendlyDependencyLine(payload.ffprobe, "FFprobe"),
  ];
  if (status) {
    status.innerHTML = `
      <p class="${ready ? "ok-text" : "warn-text"}">${ready ? "Dependências prontas." : "FFmpeg/FFprobe precisam estar prontos para inspecionar e gerar MKVs."}</p>
      <small>${lines.map(escapeHtml).join("<br>")}</small>
    `;
  }
  if (alert) {
    alert.classList.toggle("hidden", ready);
    alert.textContent = ready
      ? ""
      : "Falta FFmpeg ou FFprobe. Abra Configurações > Dependências para instalar uma cópia local.";
  }
  syncManualToolInputs(payload);
}

function syncManualToolInputs(payload) {
  const ffmpegInput = node("manual-ffmpeg-path");
  const ffprobeInput = node("manual-ffprobe-path");
  if (!ffmpegInput || !ffprobeInput || !payload) return;

  const ffmpegPath = payload.ffmpeg?.resolved_path || payload.ffmpeg?.configured || "";
  const ffprobePath = payload.ffprobe?.resolved_path || payload.ffprobe?.configured || "";
  if (!ffmpegInput.matches(":focus")) {
    ffmpegInput.value = ffmpegPath;
  }
  if (!ffprobeInput.matches(":focus")) {
    ffprobeInput.value = ffprobePath;
  }
}

function renderInstallProgress(payload) {
  const box = node("install-progress");
  const bar = node("install-progress-bar");
  const text = node("install-progress-text");
  if (!box || !bar || !text) return;

  const status = String(payload.status || "IDLE").toUpperCase();
  const progress = Math.max(0, Math.min(100, Number(payload.progress || 0)));
  box.classList.toggle("hidden", status === "IDLE");
  box.style.setProperty("--progress", `${progress}%`);
  text.textContent = payload.message || payload.error || status;

  if (status !== "RUNNING") {
    node("install-dependencies").disabled = false;
    node("install-dependencies").textContent = "Instalar FFmpeg local para este app";
  }
}

function renderChecks(checksPayload) {
  const checks = node("status-checks");
  if (!checks) return;
  checks.innerHTML = "";
  Object.values(checksPayload || {}).forEach((check) => {
    const state = String(check.status || "UNKNOWN").toLowerCase();
    const item = document.createElement("article");
    item.className = `check ${state}`;
    const manual = check.required_for_manual ? "necessário para mesclar" : "opcional no modo manual";
    item.innerHTML = `
      <strong>${escapeHtml(check.name || "check")}: ${escapeHtml(stateLabel(check.status))}</strong>
      <small>${escapeHtml(check.message || "sem detalhe")}</small>
      <span>${escapeHtml(manual)}</span>
    `;
    checks.appendChild(item);
  });
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    setText("status-summary", status.summary || "Sem resumo.");
    setText("manual-state", status.manual_ready ? "pronto para mesclar" : "precisa configurar");
    setText("workspace-path", status.workspace ? `Input: ${status.workspace.input_dir} | Output: ${status.workspace.output_dir}` : "");
    renderChecks(status.checks);
    const deps = await api("/api/dependencies");
    renderDependencyStatus(deps);
  } catch (error) {
    setText("status-summary", "Falha ao ler diagnóstico local.");
    renderError("plan-output", error);
  }
}

async function loadSettings() {
  try {
    const settings = await api("/api/settings");
    renderDependencyStatus(settings.dependencies);
  } catch (error) {
    renderError("result-output", error);
  }
}

async function loadFiles() {
  try {
    const payload = await api("/api/input-files");
    const target = node("target-select");
    const source = node("source-select");
    target.innerHTML = "";
    source.innerHTML = "";
    target.appendChild(option("Nenhum arquivo selecionado", ""));
    source.appendChild(option("Nenhum arquivo selecionado", ""));
    (payload.files || []).forEach((file) => {
      target.appendChild(option(file.name, file.path));
      source.appendChild(option(file.name, file.path));
    });
    invalidateCurrentPlan();
    if (!payload.files || payload.files.length === 0) {
      node("friendly-plan").textContent = "Coloque arquivos .mkv em input/ ou use caminhos completos.";
      renderJson("plan-output", {
        status: "EMPTY_INPUT",
        message: "Coloque arquivos .mkv na pasta input/ ou cole caminhos completos.",
      });
    }
  } catch (error) {
    renderError("plan-output", error);
  }
}

async function loadWorkflows() {
  const payload = await api("/api/workflows");
  const list = node("workflow-list");
  if (!list) return;
  list.innerHTML = "";
  (payload.workflows || []).forEach((workflow) => {
    const item = document.createElement("article");
    item.className = `panel workflow-card ${workflow.available ? "" : "disabled-card"}`;
    item.innerHTML = `
      <h2>${escapeHtml(workflow.label)}</h2>
      <p>${escapeHtml(workflow.description || "")}</p>
      <span>${workflow.available ? "Disponivel agora" : "Planejado"}</span>
    `;
    list.appendChild(item);
  });
}

async function loadJobs() {
  const payload = await api("/api/jobs");
  renderEntityList("job-list", payload.jobs || [], "Nenhuma tarefa criada nesta sessao.");
}

async function loadRecipes() {
  const payload = await api("/api/recipes");
  renderEntityList("recipe-list", payload.recipes || [], "Nenhuma receita salva ainda.");
}

async function loadProfiles() {
  const payload = await api("/api/language-profiles");
  renderEntityList("profile-list", payload.profiles || [], "Nenhum perfil encontrado.");
}

function renderEntityList(id, items, emptyText) {
  const list = node(id);
  if (!list) return;
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = `<div class="friendly-output">${escapeHtml(emptyText)}</div>`;
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("article");
    row.className = "entity-row";
    row.innerHTML = `
      <strong>${escapeHtml(item.label || item.id || item.workflow_id || "item")}</strong>
      <small>${escapeHtml(item.status || item.preferred_audio_language || item.validation_status || "")}</small>
    `;
    list.appendChild(row);
  });
}

function streamLabel(stream) {
  const parts = [stream.type, stream.codec, stream.language, stream.title].filter(Boolean);
  return parts.join(" / ") || `stream ${stream.index}`;
}

function renderInspection(targetInspect, sourceInspect) {
  const targetName = targetInspect.name || "alvo";
  const sourceName = sourceInspect.name || "fonte";
  const sourceAudio = sourceInspect.has_ptbr_audio
    ? `Áudio PT-BR detectado na faixa ${sourceInspect.ptbr_stream_index}.`
    : "Áudio PT-BR ainda não foi detectado na fonte.";
  node("friendly-plan").innerHTML = `
    <p><strong>${escapeHtml(targetName)}</strong> será usado como vídeo principal.</p>
    <p><strong>${escapeHtml(sourceName)}</strong> será usado como fonte de áudio.</p>
    <p>${escapeHtml(sourceAudio)}</p>
  `;
  const streams = (sourceInspect.streams || []).map(streamLabel).slice(0, 5);
  if (streams.length) {
    node("friendly-plan").innerHTML += `<small>Faixas da fonte: ${escapeHtml(streams.join(" | "))}</small>`;
  }
}

async function inspectFiles() {
  const target = selectedOrTyped("target-select", "target-path");
  const source = selectedOrTyped("source-select", "source-path");
  setText("plan-state", "detectando");
  try {
    const targetInspect = await api("/api/inspect", { method: "POST", body: JSON.stringify({ path: target }) });
    const sourceInspect = await api("/api/inspect", { method: "POST", body: JSON.stringify({ path: source }) });
    renderInspection(targetInspect, sourceInspect);
    renderJson("plan-output", { target: targetInspect, source: sourceInspect });
    setText("plan-state", "detectado");
  } catch (error) {
    node("friendly-plan").textContent = "Não consegui detectar as faixas. Abra os detalhes técnicos para ver o motivo.";
    renderError("plan-output", error);
    setText("plan-state", "erro");
  }
}

function renderPlan(plan) {
  lastPlanPayload = plan;
  renderJson("plan-output", plan);
  if (!plan.ready) {
    const problems = (plan.problems || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    node("friendly-plan").innerHTML = `
      <p class="warn-text"><strong>Plano bloqueado.</strong></p>
      <ul class="plain-list">${problems || "<li>Revise os arquivos selecionados.</li>"}</ul>
    `;
    return;
  }
  node("friendly-plan").innerHTML = `
    <p><strong>Plano pronto.</strong></p>
    <ul class="plain-list">
      <li>Vídeo mantido de: ${escapeHtml(plan.target.name || "arquivo 4K")}</li>
      <li>Áudio PT-BR vindo de: ${escapeHtml(plan.source.name || "fonte PT-BR")}</li>
      <li>Original protegido: não será substituído.</li>
      <li>Saída: ${escapeHtml(plan.output_path)}</li>
    </ul>
  `;
}

function invalidateCurrentPlan() {
  currentPlan = null;
  lastPlanPayload = null;
  const runButton = node("run-plan");
  if (runButton) runButton.disabled = true;
  setText("plan-state", "aguardando");
}

async function buildPlan() {
  const target = selectedOrTyped("target-select", "target-path");
  const source = selectedOrTyped("source-select", "source-path");
  setText("plan-state", "criando");
  try {
    currentPlan = await api("/api/manual-plan", {
      method: "POST",
      body: JSON.stringify({ target_path: target, source_path: source }),
    });
    renderPlan(currentPlan);
    node("run-plan").disabled = !currentPlan.ready;
    setText("plan-state", currentPlan.ready ? "pronto" : "bloqueado");
  } catch (error) {
    currentPlan = null;
    node("run-plan").disabled = true;
    node("friendly-plan").textContent = "Não consegui criar o plano. Veja os detalhes técnicos.";
    renderError("plan-output", error);
    setText("plan-state", "erro");
  }
}

function renderRunResult(result) {
  lastResultPayload = result;
  renderJson("result-output", result);
  if (result.status === "SUCCESS") {
    node("friendly-result").innerHTML = `
      <p class="ok-text"><strong>MKV final gerado.</strong></p>
      <p>${escapeHtml(result.output_path)}</p>
      <p>Relatório: ${escapeHtml(result.report_path)}</p>
    `;
    node("reports-summary").innerHTML = `
      <p><strong>Último arquivo gerado:</strong> ${escapeHtml(result.output_path)}</p>
      <p>Relatório: ${escapeHtml(result.report_path)}</p>
      <p>Receita técnica: ${escapeHtml(result.recipe_path)}</p>
    `;
    return;
  }
  node("friendly-result").innerHTML = `
    <p class="warn-text"><strong>Geração finalizada com aviso.</strong></p>
    <p>Status: ${escapeHtml(result.status || "desconhecido")}</p>
  `;
}

async function runPlan() {
  if (!currentPlan || !currentPlan.ready) return;
  setText("result-state", "gerando");
  node("run-plan").disabled = true;
  try {
    const result = await api("/api/manual-run", {
      method: "POST",
      body: JSON.stringify({ plan_id: currentPlan.plan_id }),
    });
    renderRunResult(result);
    await loadJobs();
    await loadRecipes();
    setText("result-state", result.status || "finalizado");
  } catch (error) {
    node("friendly-result").textContent = "Não consegui gerar o MKV final. Veja os detalhes técnicos.";
    renderError("result-output", error);
    setText("result-state", "erro");
    node("run-plan").disabled = false;
  }
}

async function openFolder(location) {
  try {
    const result = await api("/api/open-folder", {
      method: "POST",
      body: JSON.stringify({ location }),
    });
    renderRunResult(result);
    setText("result-state", result.status || "aberto");
  } catch (error) {
    renderError("result-output", error);
    setText("result-state", "erro");
  }
}

async function checkDependencies() {
  const deps = await api("/api/dependencies");
  renderDependencyStatus(deps);
  return deps;
}

async function installDependencies() {
  const button = node("install-dependencies");
  button.disabled = true;
  button.textContent = "Instalação em andamento";
  renderInstallProgress({ status: "RUNNING", message: "Iniciando instalação local.", progress: 1 });
  try {
    const start = await api("/api/dependencies/install-ffmpeg", { method: "POST", body: "{}" });
    renderInstallProgress(start);
    pollInstallStatus();
  } catch (error) {
    renderInstallProgress({ status: "ERROR", message: error.message || String(error), progress: 100 });
    renderError("result-output", error);
    button.disabled = false;
    button.textContent = "Instalar FFmpeg local para este app";
  }
}

async function pollInstallStatus() {
  if (installPollTimer) {
    clearTimeout(installPollTimer);
  }
  try {
    const status = await api("/api/dependencies/install-status");
    renderInstallProgress(status);
    if (status.status === "RUNNING") {
      installPollTimer = setTimeout(pollInstallStatus, 1000);
      return;
    }
    renderRunResult(status);
    await checkDependencies();
    await loadStatus();
  } catch (error) {
    renderInstallProgress({ status: "ERROR", message: error.message || String(error), progress: 100 });
    renderError("result-output", error);
    node("install-dependencies").disabled = false;
    node("install-dependencies").textContent = "Instalar FFmpeg local para este app";
  }
}

async function saveManualTools() {
  const result = await api("/api/dependencies/use-local-tools", {
    method: "POST",
    body: JSON.stringify({
      ffmpeg_path: node("manual-ffmpeg-path").value,
      ffprobe_path: node("manual-ffprobe-path").value,
    }),
  });
  renderRunResult(result);
  await checkDependencies();
  await loadStatus();
}

document.querySelectorAll("[data-screen]").forEach((button) => {
  button.addEventListener("click", () => switchScreen(button.dataset.screen));
});
document.querySelectorAll("[data-theme-choice]").forEach((button) => {
  button.addEventListener("click", () => {
    applyTheme(button.dataset.themeChoice);
    api("/api/settings/theme", { method: "POST", body: JSON.stringify({ theme: button.dataset.themeChoice }) }).catch(() => {});
  });
});
document.querySelectorAll("[data-open-location]").forEach((button) => {
  button.addEventListener("click", () => openFolder(button.dataset.openLocation));
});

node("refresh-status").addEventListener("click", loadStatus);
node("load-files").addEventListener("click", loadFiles);
node("inspect-files").addEventListener("click", inspectFiles);
node("build-plan").addEventListener("click", buildPlan);
node("run-plan").addEventListener("click", runPlan);
node("check-dependencies").addEventListener("click", checkDependencies);
node("settings-check-dependencies").addEventListener("click", checkDependencies);
node("install-dependencies").addEventListener("click", installDependencies);
node("save-manual-tools").addEventListener("click", saveManualTools);

["target-select", "source-select", "target-path", "source-path"].forEach((id) => {
  node(id).addEventListener("change", invalidateCurrentPlan);
  node(id).addEventListener("input", invalidateCurrentPlan);
});

applyTheme(localStorage.getItem("ptbrmerger-theme") || "system");
loadStatus();
loadSettings();
loadFiles();
loadWorkflows();
loadJobs();
loadRecipes();
loadProfiles();
