const CAPTURE_WIDTH = 480;
const CAPTURE_HEIGHT = 360;
const ANALYZE_INTERVAL_MS = 600;
const ANALYZE_TIMEOUT_MS = 4000;
const PAIRING_SECONDS = 600;
const DEFAULT_DEVICE_ID = "mirror-demo-001";
const PAIRING_STATUS_INTERVAL_MS = 3000;
const ROM_SHOULDER_KEY = "rom_shoulder";
const ROM_GUIDE_VIDEO_PATH = "/static/videos/rom_shoulder_demo.mp4";
const DEMO_MODE = new URLSearchParams(window.location.search).get("demo") === "1";
const DEMO_INITIAL_DELAY_MS = 6000;
const DEMO_STEP_DELAY_MS = 2600;
const DEMO_PLAYBACK_RATE = 1;
const DEMO_HOLD_SAMPLES = 6;
const DEMO_EXERCISE_DURATION_MS = 27000;
const UTC_OFFSET_PATTERN = /(Z|[+-]\d{2}:?\d{2})$/i;
const RECORD_DATE_FORMATTER = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
});
const HEALTH_CHECK_PLACEHOLDERS = [
    {
        key: "senior_disease_check",
        name: "노인질환 점검",
        category: "건강 체크",
        description: "혈압, 낙상 위험, 인지 상태 등 주요 건강 항목을 점검할 수 있도록 준비 중입니다.",
        status_label: "준비 중",
        analysis_supported: false,
        support_message: "노인질환 점검은 추후 지원 예정입니다."
    }
];

function updateMirrorScale() {
    const scale = Math.min((window.innerWidth * 0.92) / 1080, (window.innerHeight * 0.92) / 1920);
    document.documentElement.style.setProperty("--mirror-scale", scale);
}

let deviceId = DEFAULT_DEVICE_ID;
let users = [];
let exercises = [];
let currentUser = null;
let selectedExercise = null;
let selectedHealthCheck = null;
let pairingRemaining = PAIRING_SECONDS;
let pairingPollTimer = null;
let cameraStream = null;
let analyzeTimer = null;
let isAnalyzing = false;
let isStartingTracking = false;
let activeAnalysisRunId = 0;
let activeAnalysisController = null;
let serverAnalysisSession = null;
const TRACKING_DEBUG = new URLSearchParams(window.location.search).get("tracking_debug") === "1";
let returnToExerciseTimer = null;
let currentRep = 0;
let demoFlowStarted = false;
let demoAnalysisTimer = null;
let demoStage = 1;
let demoHoldCount = 0;
let demoStartedAt = 0;
let demoCompleted = false;
let exerciseSession = null;
let romPhase = "ready";
let romLatestResult = null;
let guideVideoAutoplayRunId = 0;
let romGuidePlaybackPending = false;
let romGuideRestartPending = false;
const el = (id) => document.getElementById(id);

function setText(node, value) { if (node) node.textContent = value; }

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options
    });
    const data = await response.json();
    if (!response.ok || data.success === false) {
        throw new Error(data.error || `요청에 실패했습니다: ${url}`);
    }
    return data;
}

function isExerciseSupported(exercise) {
    return Boolean(exercise && exercise.analysis_supported);
}

function isRomExercise(exercise = selectedExercise) {
    return Boolean(exercise && exercise.key === ROM_SHOULDER_KEY);
}

function guideVideoPathForExercise(exercise) {
    if (isRomExercise(exercise)) return ROM_GUIDE_VIDEO_PATH;
    return exercise.video_path || `/static/videos/${exercise.key}.mp4`;
}

function isTrainingViewActive() {
    return Boolean(el("training-view")?.classList.contains("active-view"));
}

function configureGuideVideoForExercise(guideVideo, exercise) {
    const isRomGuide = isRomExercise(exercise);
    guideVideoAutoplayRunId += 1;
    romGuidePlaybackPending = false;
    romGuideRestartPending = false;
    guideVideo.pause();
    guideVideo.autoplay = isRomGuide;
    guideVideo.controls = !isRomGuide;
    guideVideo.loop = true;
    guideVideo.playsInline = true;
    guideVideo.preload = isRomGuide ? "auto" : "";

    guideVideo.setAttribute("loop", "");
    guideVideo.setAttribute("playsinline", "");
    if (isRomGuide) {
        guideVideo.muted = true;
        guideVideo.defaultMuted = true;
        guideVideo.setAttribute("autoplay", "");
        guideVideo.setAttribute("muted", "");
        guideVideo.setAttribute("preload", "auto");
        guideVideo.removeAttribute("controls");
        return;
    }

    guideVideo.muted = false;
    guideVideo.defaultMuted = false;
    guideVideo.removeAttribute("autoplay");
    guideVideo.removeAttribute("muted");
    guideVideo.removeAttribute("preload");
    guideVideo.setAttribute("controls", "");
}

function pauseGuideVideo() {
    const guideVideo = el("guide-video");
    if (!guideVideo) return;
    guideVideoAutoplayRunId += 1;
    romGuidePlaybackPending = false;
    romGuideRestartPending = false;
    guideVideo.pause();
}

function playPendingRomGuideVideo() {
    const guideVideo = el("guide-video");
    if (!guideVideo || !romGuidePlaybackPending || !isRomExercise() || !isTrainingViewActive()) return;
    if (guideVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;

    const runId = guideVideoAutoplayRunId;
    romGuidePlaybackPending = false;
    if (romGuideRestartPending) {
        try {
            guideVideo.currentTime = 0;
        } catch (error) {
            console.warn("[guide-video] reset failed:", error);
        }
        romGuideRestartPending = false;
    }

    const playPromise = guideVideo.play();
    if (playPromise !== undefined) {
        playPromise.catch((error) => {
            if (runId === guideVideoAutoplayRunId && isRomExercise() && isTrainingViewActive()) {
                console.warn("[guide-video] autoplay failed:", error);
            }
        });
    }
}

function requestRomGuidePlayback({ restart = false } = {}) {
    if (!isRomExercise() || !isTrainingViewActive()) return;
    romGuidePlaybackPending = true;
    romGuideRestartPending = restart;
    playPendingRomGuideVideo();
}

function getRehabExercises() {
    return exercises.filter((exercise) => !isRomExercise(exercise));
}

function getHealthChecks() {
    return [
        ...exercises.filter(isRomExercise),
        ...HEALTH_CHECK_PLACEHOLDERS
    ];
}

function getSelectedOrFirstExercise() {
    const rehabExercises = getRehabExercises();
    if (selectedExercise && !isRomExercise(selectedExercise)) return selectedExercise;
    return rehabExercises.find(isExerciseSupported) || rehabExercises[0] || null;
}

function getSelectedOrFirstHealthCheck() {
    const checks = getHealthChecks();
    if (selectedHealthCheck && checks.some((check) => check.key === selectedHealthCheck.key)) return selectedHealthCheck;
    return checks.find(isExerciseSupported) || checks[0] || null;
}

function stopCameraExercise() {
    if (serverAnalysisSession) {
        const token = serverAnalysisSession;
        serverAnalysisSession = null;
        fetch("/stop_exercise", {method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({analysis_session: token}), keepalive: true}).catch(() => {});
    }
    if (el("tracking-overlay")) el("tracking-overlay").hidden = true;
    if (el("confirm-target-button")) el("confirm-target-button").hidden = true;
    activeAnalysisRunId += 1;
    if (activeAnalysisController) {
        activeAnalysisController.abort();
        activeAnalysisController = null;
    }
    if (returnToExerciseTimer) {
        clearTimeout(returnToExerciseTimer);
        returnToExerciseTimer = null;
    }
    clearInterval(analyzeTimer);
    clearInterval(demoAnalysisTimer);
    analyzeTimer = null;
    demoAnalysisTimer = null;
    isAnalyzing = false;
    isStartingTracking = false;
    if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    const video = el("camera-video");
    if (video) { video.pause(); video.srcObject = null; video.classList.remove("camera-ready"); }
    if (el("camera-placeholder")) el("camera-placeholder").hidden = false;
}

function resetExerciseSession() {
    exerciseSession = null;
    const returnButton = el("return-button");
    if (returnButton) {
        returnButton.disabled = false;
        setText(returnButton, "운동 종료 및 저장");
    }
    const romSaveButton = el("rom-save-button");
    if (romSaveButton) {
        romSaveButton.disabled = false;
        setText(romSaveButton, "결과 저장");
    }
}

function showView(viewId) {
    if (viewId !== "training-view") {
        stopCameraExercise();
        pauseGuideVideo();
    }
    document.querySelectorAll(".app-view").forEach((view) => view.classList.toggle("active-view", view.id === viewId));
}

function renderExerciseTrainingUI() {
    el("training-view").classList.remove("rom-mode", "rom-status-normal", "rom-status-caution", "rom-status-fail");
    el("training-panel").hidden = false;
    el("rom-panel").hidden = true;
    setText(document.querySelector("#guide-placeholder span"), "운동 가이드 영상");
    setText(document.querySelector(".camera-preview-label"), "내 자세");
}

function renderRomCheckUI({ reset = true } = {}) {
    el("training-view").classList.add("rom-mode");
    el("training-panel").hidden = true;
    el("rom-panel").hidden = false;
    setText(el("rom-title"), selectedExercise?.name || "관절 가동 범위 점검");
    setText(el("rom-description"), selectedExercise?.description || "카메라로 어깨 관절 움직임을 인식하여 가동 범위를 확인합니다.");
    setText(el("guide-title"), selectedExercise?.name || "관절 가동 범위 점검");
    setText(el("fallback-title"), selectedExercise?.name || "관절 가동 범위 점검");
    setText(document.querySelector("#guide-placeholder span"), "측정 참고 화면");
    setText(document.querySelector(".camera-preview-label"), "ROM 측정 화면");
    setText(el("rom-back-button"), "건강 체크로 돌아가기");
    if (reset) {
        romLatestResult = null;
        updateRomCheckUI(null);
        setRomPhase("ready");
    } else {
        updateRomCheckUI(romLatestResult);
        setRomPhase(romPhase);
    }
}

function formatRomAngle(value) {
    return Number.isFinite(value) ? `${Math.round(value)}°` : "--°";
}

function normalizeRomStatus(result) {
    const state = result?.state || "";
    const status = result?.rom_status || "";
    if (state === "NO_PERSON" || state === "LOW_VISIBILITY" || status.includes("실패")) return "fail";
    if (state === "NORMAL_RANGE" || status.includes("정상")) return "normal";
    if (state === "NEEDS_CAUTION" || status.includes("주의")) return "caution";
    return "measuring";
}

function getRomStatusLabel(result) {
    if (!result) return "측정 전";
    if (result.rom_status) return result.rom_status;
    if (result.state === "NO_PERSON" || result.state === "LOW_VISIBILITY") return "인식 실패";
    return "측정 중";
}

function getRomGuidance(result) {
    const tone = normalizeRomStatus(result);
    if (!result) return "의자에 바르게 앉거나 선 자세를 유지한 뒤, 한쪽 팔을 천천히 들어올려주세요.";
    if (tone === "normal") return "가동 범위가 충분합니다. 현재 범위에서 안전하게 운동을 진행하세요.";
    if (tone === "caution") return "가동 범위가 다소 부족합니다. 무리하지 말고 천천히 반복하세요.";
    if (tone === "fail") return "사람이 화면에 충분히 보이도록 한 뒤 다시 시도해주세요.";
    return result.feedback || "무리하지 말고 가능한 범위까지만 천천히 움직여주세요.";
}

function setRomGauge(currentAngle, maxAngle) {
    const current = Math.max(0, Math.min(180, Number.isFinite(currentAngle) ? currentAngle : 0));
    const max = Math.max(current, Math.min(180, Number.isFinite(maxAngle) ? maxAngle : 0));
    const gauge = el("rom-gauge");
    gauge.style.setProperty("--rom-current", `${current}deg`);
    gauge.style.setProperty("--rom-max", `${max}deg`);
}

function setRomPhase(phase) {
    romPhase = phase;
    const labels = { ready: "준비", measuring: "측정 중", result: "결과 확인" };
    setText(el("rom-phase-label"), labels[phase] || labels.ready);
    el("rom-step-ready").classList.toggle("active", phase === "ready");
    el("rom-step-measuring").classList.toggle("active", phase === "measuring");
    el("rom-step-result").classList.toggle("active", phase === "result");

    const startButton = el("rom-start-button");
    const stopButton = el("rom-stop-button");
    const retryButton = el("rom-retry-button");
    const saveButton = el("rom-save-button");
    startButton.hidden = phase === "result";
    stopButton.hidden = phase !== "measuring";
    retryButton.hidden = phase !== "result";
    saveButton.hidden = phase !== "result";
    startButton.disabled = phase === "measuring";
    setText(startButton, phase === "measuring" ? "측정 중..." : "측정 시작");
    setText(stopButton, "측정 종료");
    setText(retryButton, "다시 측정");
    setText(saveButton, exerciseSession?.saved ? "저장 완료" : "결과 저장");
    saveButton.disabled = Boolean(exerciseSession?.saved);
}

function updateRomCheckUI(result) {
    const currentAngle = Number.isFinite(result?.current_angle) ? Math.round(result.current_angle) : null;
    const maxAngle = Number.isFinite(result?.max_angle) ? Math.round(result.max_angle) : null;
    const targetAngle = Number.isFinite(result?.target_angle) ? Math.round(result.target_angle) : selectedExercise?.angle || 120;
    const statusLabel = getRomStatusLabel(result);
    const guidance = getRomGuidance(result);
    const tone = normalizeRomStatus(result);
    const trainingView = el("training-view");
    const resultCard = el("rom-result-card");

    trainingView.classList.toggle("rom-status-normal", tone === "normal");
    trainingView.classList.toggle("rom-status-caution", tone === "caution");
    trainingView.classList.toggle("rom-status-fail", tone === "fail");
    resultCard.classList.toggle("rom-status-normal", tone === "normal");
    resultCard.classList.toggle("rom-status-caution", tone === "caution");
    resultCard.classList.toggle("rom-status-fail", tone === "fail");

    setRomGauge(currentAngle, maxAngle);
    setText(el("rom-current-angle"), formatRomAngle(currentAngle));
    setText(el("rom-max-angle"), formatRomAngle(maxAngle));
    setText(el("rom-status"), statusLabel);
    setText(el("rom-threshold"), `${targetAngle}° 이상`);
    setText(el("rom-result-max"), `최대 가동 범위 ${formatRomAngle(maxAngle)}`);
    setText(el("rom-result-message"), guidance);
}

function updatePairingTimer() {
    const minutes = String(Math.floor(pairingRemaining / 60)).padStart(2, "0");
    const seconds = String(pairingRemaining % 60).padStart(2, "0");
    setText(el("pairing-timer"), `남은 시간: ${minutes}:${seconds}`);
}

async function issuePairingCode() {
    try {
        const data = await fetchJSON(`/api/devices/${deviceId}/pairing-code`, { method: "POST" });
        pairingRemaining = Number.isFinite(data.expires_in) ? data.expires_in : PAIRING_SECONDS;
        setText(el("pairing-code"), data.code || "------");
        setText(el("pairing-status-title"), "등록 상태 확인 중");
        setText(el("pairing-status-message"), "앱에서 등록을 완료하면 자동으로 다음 화면으로 이동합니다.");
    } catch (error) {
        pairingRemaining = PAIRING_SECONDS;
        setText(el("pairing-code"), "ERROR");
        setText(el("pairing-status-title"), "코드 발급 실패");
        setText(el("pairing-status-message"), error.message);
    }
    updatePairingTimer();
}

async function refreshPairingStatus() {
    try {
        const data = await fetchJSON(`/api/devices/${deviceId}/pairing-status`);
        if (Number.isFinite(data.expires_in)) {
            pairingRemaining = data.expires_in;
            updatePairingTimer();
        }
        if (data.paired) {
            setText(el("pairing-status-title"), "등록 완료");
            setText(el("pairing-status-message"), "사용자 목록을 불러왔습니다.");
            await loadUsers();
            if (pairingPollTimer) {
                clearInterval(pairingPollTimer);
                pairingPollTimer = null;
            }
            showView("user-view");
        }
    } catch (error) {
        setText(el("pairing-status-title"), "등록 상태 확인 실패");
        setText(el("pairing-status-message"), error.message);
    }
}

async function completePairingForDemo() {
    try {
        await fetchJSON(`/api/devices/${deviceId}/pairing-status/demo-complete`, { method: "POST" });
        await refreshPairingStatus();
    } catch (error) {
        setText(el("pairing-status-title"), "등록 테스트 실패");
        setText(el("pairing-status-message"), error.message);
    }
}

function renderUsers() {
    if (!users.length) {
        el("user-list").innerHTML = `<p class="empty-state">등록된 사용자가 없습니다.</p>`;
        return;
    }
    el("user-list").innerHTML = users.map((user) => `
        <button type="button" class="user-card" data-user-id="${user.id}">
            <span class="user-avatar">${user.name[0]}</span>
            <span class="user-copy"><strong>${user.name}</strong><em>${user.program}</em></span>
            <b>선택</b>
        </button>`).join("");
}

function selectUser(userId) {
    const user = users.find((item) => item.id === userId) || users[0];
    if (!user) return;
    currentUser = user;
    setText(el("home-avatar"), user.name[0]);
    setText(el("home-user-name"), `${user.name} 님`);
    setText(el("home-user-program"), `${user.program} · ${user.goal}`);
    showView("home-view");
}

function exerciseMetaText(exercise) {
    const status = isExerciseSupported(exercise) ? exercise.duration : `${exercise.duration} · 준비 중`;
    return `${exercise.part} · ${exercise.target}회 · ${status}`;
}

function healthCheckMetaText(check) {
    return check.status_label || (isExerciseSupported(check) ? "점검 가능" : "준비 중");
}

function renderHomeMenu() {
    setText(el("home-rehab-count"), `질환 예방 운동 ${getRehabExercises().length}개`);
    setText(el("home-health-count"), `건강 체크 ${getHealthChecks().length}개`);
}

function renderTodayExercises() {
    const todayExercises = getRehabExercises().filter((exercise) => exercise.is_today);
    setText(el("today-count"), `${todayExercises.length}개`);
    if (!todayExercises.length) {
        el("today-list").innerHTML = `<p class="empty-state">오늘 표시할 질환 예방 운동이 없습니다.</p>`;
        return;
    }
    el("today-list").innerHTML = todayExercises.map((exercise) => {
        const supported = isExerciseSupported(exercise);
        const selected = selectedExercise && selectedExercise.key === exercise.key;
        return `
            <button type="button" class="today-item ${selected ? "selected-today" : ""} ${supported ? "" : "is-disabled"}" data-exercise="${exercise.key}">
                <i></i><div><strong>${exercise.name}</strong><p>${exerciseMetaText(exercise)}</p></div><em>${supported ? exercise.part : "준비 중"}</em>
            </button>`;
    }).join("");
}

function renderExerciseList() {
    const rehabExercises = getRehabExercises();
    setText(el("exercise-count"), `${rehabExercises.length}개`);
    if (!rehabExercises.length) {
        el("exercise-list").innerHTML = `<p class="empty-state">표시할 질환 예방 운동이 없습니다.</p>`;
        return;
    }
    el("exercise-list").innerHTML = rehabExercises.map((exercise) => {
        const supported = isExerciseSupported(exercise);
        return `
            <button type="button" class="exercise-row ${supported ? "" : "is-disabled"}" data-exercise="${exercise.key}">
                <span>${exercise.category}</span><div><strong>${exercise.name}</strong><em>${exerciseMetaText(exercise)}</em></div>
            </button>`;
    }).join("");
}

function renderHealthCheckList() {
    const checks = getHealthChecks();
    setText(el("health-check-count"), `${checks.length}개`);
    if (!checks.length) {
        el("health-check-list").innerHTML = `<p class="empty-state">표시할 건강 체크가 없습니다.</p>`;
        return;
    }
    el("health-check-list").innerHTML = checks.map((check) => {
        const supported = isExerciseSupported(check);
        const selected = selectedHealthCheck && selectedHealthCheck.key === check.key;
        return `
            <button type="button" class="health-check-card ${selected ? "selected-check-row" : ""} ${supported ? "" : "is-disabled"}" data-check="${check.key}">
                <div><span>${check.category || "건강 체크"}</span><strong>${check.name}</strong><p>${check.description || check.support_message || ""}</p></div>
                <em>${healthCheckMetaText(check)}</em>
            </button>`;
    }).join("");
}

function renderSelectedExercise() {
    selectedExercise = selectedExercise || getSelectedOrFirstExercise();
    if (!selectedExercise) return;
    const supported = isExerciseSupported(selectedExercise);
    const supportMessage = selectedExercise.support_message || "이 운동 분석은 추후 지원 예정입니다.";
    setText(el("selected-title"), selectedExercise.name);
    setText(el("selected-description"), supported ? selectedExercise.description : `${selectedExercise.description} ${supportMessage}`);
    setText(el("exercise-title"), selectedExercise.name);
    setText(el("exercise-description"), supported ? selectedExercise.guide : supportMessage);
    setText(el("rep-counter"), isRomExercise(selectedExercise) ? "측정 준비" : `${currentRep} / ${selectedExercise.target}`);
    setText(el("angle-value"), supported ? `-- / ${selectedExercise.angle}°` : "준비 중");
    setText(el("fallback-title"), selectedExercise.name);
    setText(el("guide-title"), selectedExercise.name);
    const guideVideoPath = guideVideoPathForExercise(selectedExercise);
    setText(el("guide-path"), guideVideoPath);
    const guide = el("guide-video");
    configureGuideVideoForExercise(guide, selectedExercise);
    guide.src = guideVideoPath;
    guide.load();
    if (isRomExercise(selectedExercise)) requestRomGuidePlayback({ restart: true });
    const startButton = el("start-button");
    const exerciseStartButton = el("exercise-start-button");
    startButton.disabled = !supported;
    exerciseStartButton.disabled = !supported;
    setText(startButton, supported ? "선택한 운동 시작" : "추후 지원 예정");
    setText(exerciseStartButton, supported ? "이 운동 시작" : "추후 지원 예정");
    if (isRomExercise(selectedExercise)) renderRomCheckUI();
    else renderExerciseTrainingUI();
    document.querySelectorAll("[data-exercise]").forEach((button) => {
        button.classList.toggle("selected-row", button.matches(".exercise-row") && button.dataset.exercise === selectedExercise.key);
        button.classList.toggle("selected-today", button.matches(".today-item") && button.dataset.exercise === selectedExercise.key);
    });
    renderTodayExercises();
}

function renderSelectedHealthCheck() {
    selectedHealthCheck = getSelectedOrFirstHealthCheck();
    if (!selectedHealthCheck) return;
    const supported = isExerciseSupported(selectedHealthCheck);
    const supportMessage = selectedHealthCheck.support_message || "이 점검은 추후 지원 예정입니다.";
    setText(el("selected-check-title"), selectedHealthCheck.name);
    setText(el("selected-check-description"), supported ? selectedHealthCheck.description : `${selectedHealthCheck.description} ${supportMessage}`);
    const startButton = el("health-check-start-button");
    startButton.disabled = !supported;
    setText(startButton, supported ? "점검 시작" : "준비 중");
    document.querySelectorAll("[data-check]").forEach((button) => {
        button.classList.toggle("selected-check-row", button.dataset.check === selectedHealthCheck.key);
    });
}

function chooseExercise(key) {
    selectedExercise = getRehabExercises().find((item) => item.key === key) || selectedExercise;
    currentRep = 0;
    renderSelectedExercise();
}

function chooseHealthCheck(key) {
    selectedHealthCheck = getHealthChecks().find((item) => item.key === key) || selectedHealthCheck;
    renderSelectedHealthCheck();
    renderHealthCheckList();
}

async function loadDevice() {
    const data = await fetchJSON("/api/devices/current");
    deviceId = data.device?.id || DEFAULT_DEVICE_ID;
}

async function loadUsers() {
    const data = await fetchJSON("/api/users");
    users = data.users || [];
    renderUsers();
}

async function loadExercises() {
    const data = await fetchJSON("/api/exercises");
    exercises = data.exercises || [];
    selectedExercise = getRehabExercises().find(isExerciseSupported) || getRehabExercises()[0] || null;
    selectedHealthCheck = getHealthChecks().find(isExerciseSupported) || getHealthChecks()[0] || null;
    renderExerciseList();
    renderHealthCheckList();
    renderHomeMenu();
    renderSelectedExercise();
    renderSelectedHealthCheck();
}

function updateDateTime() {
    const now = new Date();
    setText(el("current-date"), now.toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", weekday: "long" }));
    setText(el("current-time"), now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));
}

async function startCameraExercise() {
    selectedExercise = selectedExercise || getSelectedOrFirstExercise();
    if (!selectedExercise) return;
    if (!isExerciseSupported(selectedExercise)) {
        renderSelectedExercise();
        setText(el("feedback-text"), selectedExercise.support_message || "이 운동 분석은 추후 지원 예정입니다.");
        return;
    }
    if (!currentUser) currentUser = users[0] || null;
    if (!currentUser) {
        showView("user-view");
        return;
    }
    showView("training-view");
    renderSelectedExercise();
    if (isRomExercise()) {
        renderRomCheckUI();
        return;
    }
    await startTrackingForSelectedExercise();
}

async function startSelectedRehabExercise() {
    if (!selectedExercise || isRomExercise(selectedExercise)) selectedExercise = getSelectedOrFirstExercise();
    await startCameraExercise();
}

async function startSelectedHealthCheck() {
    selectedHealthCheck = getSelectedOrFirstHealthCheck();
    renderSelectedHealthCheck();
    if (!selectedHealthCheck || !isExerciseSupported(selectedHealthCheck)) return;
    selectedExercise = selectedHealthCheck;
    currentRep = 0;
    await startCameraExercise();
}

async function startTrackingForSelectedExercise() {
    if (isStartingTracking) return;
    stopCameraExercise();
    isStartingTracking = true;
    const runId = activeAnalysisRunId + 1;
    activeAnalysisRunId = runId;
    if (DEMO_MODE && !isRomExercise()) {
        beginExerciseSession();
        await startDemoExercise();
        isStartingTracking = false;
        return;
    }
    if (isRomExercise()) {
        setRomPhase("measuring");
        setText(el("rom-result-message"), "카메라 권한을 요청하고 있습니다.");
    } else {
        setText(el("exercise-state"), "STARTING");
        setText(el("camera-message"), "카메라 권한을 요청하고 있습니다.");
    }
    try {
        const reset = await fetchJSON("/reset_exercise", { method: "POST", body: JSON.stringify({ exercise_key: selectedExercise.key, mode: selectedExercise.key, use_session: true }) });
        if (runId !== activeAnalysisRunId) {
            await fetchJSON("/stop_exercise", {method: "POST", body: JSON.stringify({analysis_session: reset.analysis_session})});
            return;
        }
        serverAnalysisSession = reset.analysis_session;
        cameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: CAPTURE_WIDTH }, height: { ideal: CAPTURE_HEIGHT }, facingMode: "user" }, audio: false });
        const video = el("camera-video");
        video.srcObject = cameraStream;
        await video.play();
        video.classList.add("camera-ready");
        el("camera-placeholder").hidden = true;
        beginExerciseSession();
        if (isRomExercise()) {
            setRomPhase("measuring");
            setText(el("rom-result-message"), "무리하지 말고 가능한 범위까지만 천천히 움직여주세요.");
        } else {
            setText(el("exercise-state"), "TRACKING");
            setText(el("camera-message"), "서버 분석을 시작합니다.");
        }
        analyzeTimer = setInterval(() => captureAndAnalyzeFrame(runId), ANALYZE_INTERVAL_MS);
        captureAndAnalyzeFrame(runId);
    } catch (error) {
        if (isRomExercise()) {
            setRomPhase("ready");
            setText(el("rom-result-message"), `카메라를 시작하지 못했습니다: ${error.message}`);
        } else {
            setText(el("exercise-state"), "ERROR");
            setText(el("camera-message"), `카메라를 시작하지 못했습니다: ${error.message}`);
            setText(el("feedback-text"), "카메라 권한과 HTTPS 또는 localhost 접속 여부를 확인해주세요.");
        }
    } finally {
        isStartingTracking = false;
    }
}

function beginExerciseSession() {
    exerciseSession = {
        userId: currentUser.id,
        exerciseKey: selectedExercise.key,
        startedAt: new Date().toISOString(),
        samples: [],
        saved: false
    };
    const returnButton = el("return-button");
    returnButton.disabled = false;
    setText(returnButton, "운동 종료 및 저장");
    if (isRomExercise()) setRomPhase(romPhase);
}

async function startRomMeasurement() {
    if (!isRomExercise() || romPhase === "measuring") return;
    stopCameraExercise();
    resetExerciseSession();
    romLatestResult = null;
    updateRomCheckUI(null);
    setRomPhase("measuring");
    await startTrackingForSelectedExercise();
}

function stopRomMeasurement() {
    if (!isRomExercise()) return;
    stopCameraExercise();
    setRomPhase("result");
    updateRomCheckUI(romLatestResult);
    if (!romLatestResult) {
        setText(el("rom-result-message"), "측정된 프레임이 없습니다. 다시 측정해주세요.");
    }
}

function retryRomMeasurement() {
    stopCameraExercise();
    resetExerciseSession();
    romLatestResult = null;
    updateRomCheckUI(null);
    setRomPhase("ready");
}

function leaveRomMeasurement() {
    stopCameraExercise();
    resetExerciseSession();
    romLatestResult = null;
    updateRomCheckUI(null);
    setRomPhase("ready");
    renderHealthCheckList();
    renderSelectedHealthCheck();
    showView("health-check-view");
}

async function startDemoExercise() {
    const guide = el("guide-video");
    guide.muted = true;
    guide.loop = true;
    guide.playbackRate = DEMO_PLAYBACK_RATE;
    guide.currentTime = 0;
    demoStage = 1;
    demoHoldCount = 0;
    demoStartedAt = performance.now();
    demoCompleted = false;
    setText(el("exercise-state"), "TRACKING");
    setText(el("camera-message"), "자세를 인식하고 있습니다.");
    setText(el("feedback-text"), "가이드 영상에 맞춰 천천히 움직여주세요.");
    guide.play().catch(() => {
        guide.addEventListener("canplay", () => guide.play(), { once: true });
    });
    updateDemoAnalysis();
    demoAnalysisTimer = setInterval(updateDemoAnalysis, 250);
    await startDemoCameraPreview();
}

async function startDemoCameraPreview() {
    const cameraVideo = el("camera-video");
    const placeholder = el("camera-placeholder");
    if (!navigator.mediaDevices?.getUserMedia) {
        setText(el("camera-message"), "브라우저 보안 설정에서 카메라 사용을 허용해주세요.");
        return;
    }
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: CAPTURE_WIDTH }, height: { ideal: CAPTURE_HEIGHT } },
            audio: false
        });
        cameraVideo.srcObject = cameraStream;
        await cameraVideo.play();
        cameraVideo.classList.add("camera-ready");
        placeholder.hidden = true;
        setText(el("camera-message"), "카메라 화면과 자세 분석을 시작합니다.");
    } catch (error) {
        console.error("Demo camera start failed:", error);
        setText(el("camera-message"), `카메라를 시작하지 못했습니다: ${error.message}`);
        setText(placeholder?.querySelector("p"), "카메라 권한 또는 Chromium 실행 설정을 확인해주세요.");
    }
}

function updateDemoAnalysis() {
    if (demoCompleted) return;
    const elapsedSeconds = (performance.now() - demoStartedAt) / 1000;
    const progress = Math.min(1, (performance.now() - demoStartedAt) / DEMO_EXERCISE_DURATION_MS);
    const fastWave = Math.sin(elapsedSeconds * 2.6);
    const slowWave = Math.sin(elapsedSeconds * 1.05 + 0.8);
    const stageForFrame = demoStage;
    let targetArm;
    let targetTorso;
    let arm;
    let torso;
    let feedback;

    if (stageForFrame === 1) {
        targetArm = 158;
        targetTorso = 11;
        const armLift = Math.min(1, progress / 0.27);
        const torsoTurn = Math.min(1, progress / 0.29);
        const movementShake = (1 - armLift) * 9 + 3;
        arm = 20 + (targetArm - 20) * armLift + fastWave * movementShake + slowWave * 6;
        torso = targetTorso * torsoTurn + fastWave * 2 + slowWave * 3;
        feedback = armLift < 0.8 ? "양팔을 천천히 올려주세요." : "좋습니다. 몸통을 왼쪽으로 돌려주세요.";
    } else if (stageForFrame === 2) {
        targetArm = 153;
        targetTorso = 2;
        const centerTurn = Math.min(1, Math.max(0, (progress - 0.34) / 0.22));
        arm = 142 + (targetArm - 142) * centerTurn + fastWave * 5 + slowWave * 4;
        torso = 13 + (targetTorso - 13) * centerTurn + fastWave * 2 + slowWave * 3;
        feedback = "좋습니다. 양팔을 유지하며 정면으로 돌아오세요.";
    } else {
        targetArm = 41;
        targetTorso = -41;
        const lowerArm = Math.min(1, Math.max(0, (progress - 0.64) / 0.25));
        const movementShake = (1 - lowerArm) * 8 + 3;
        arm = 153 + (targetArm - 153) * lowerArm + fastWave * movementShake + slowWave * 5;
        torso = 2 + (targetTorso - 2) * lowerArm + fastWave * 3 + slowWave * 4;
        feedback = "팔을 내리며 몸통을 오른쪽으로 돌려주세요.";
    }

    arm = Math.round(arm);
    torso = Math.round(torso);
    const armError = Math.abs(arm - targetArm);
    const torsoError = Math.abs(torso - targetTorso);
    const accuracyVariation = fastWave * 3 + slowWave * 4;
    const accuracy = Math.round(Math.max(42, Math.min(98, 99 - armError * 0.42 - torsoError * 0.9 + accuracyVariation)));
    const accurateEnough = accuracy >= 90;
    demoHoldCount = accurateEnough ? demoHoldCount + 1 : Math.max(0, demoHoldCount - 2);

    if (stageForFrame === 1 && progress >= 0.30 && accurateEnough && demoHoldCount >= DEMO_HOLD_SAMPLES) {
        demoStage = 2;
        demoHoldCount = 0;
    } else if (stageForFrame === 2 && progress >= 0.61 && accurateEnough && demoHoldCount >= DEMO_HOLD_SAMPLES) {
        demoStage = 3;
        demoHoldCount = 0;
    }

    const complete = stageForFrame === 3 && progress >= 0.95 && accurateEnough && demoHoldCount >= DEMO_HOLD_SAMPLES;
    currentRep = complete ? 3 : stageForFrame - 1;
    if (complete) {
        feedback = "전체 동작을 잘 완료했습니다.";
        demoCompleted = true;
        clearInterval(demoAnalysisTimer);
        demoAnalysisTimer = null;
    }
    else if (accurateEnough) feedback = "정확한 자세입니다. 잠시 유지해주세요.";

    setText(el("exercise-state"), complete ? "COMPLETE" : `STAGE_${stageForFrame}`);
    setText(el("rep-counter"), `${currentRep} / 3`);
    setText(el("accuracy-value"), `${accuracy}%`);
    setText(el("angle-value"), `팔 ${arm} / ${targetArm}° · 몸통 ${torso} / ${targetTorso}°`);
    setText(el("feedback-text"), feedback);
    setText(el("camera-message"), complete ? "오늘 운동을 완료했습니다." : "자세를 실시간으로 분석하고 있습니다.");
    collectExerciseSample({
        accuracy,
        feedback,
        state: complete ? "COMPLETE" : `STAGE_${stageForFrame}`,
        stage: stageForFrame
    });
}

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runDemoFlow() {
    if (!DEMO_MODE || demoFlowStarted) return;
    demoFlowStarted = true;
    await wait(DEMO_INITIAL_DELAY_MS);
    el("home-view").querySelector('[data-view="exercise-view"]').click();
    await wait(DEMO_STEP_DELAY_MS);
    el("exercise-view").querySelector('[data-view="home-view"]').click();
    await wait(DEMO_STEP_DELAY_MS);
    el("change-user-button").click();
    await wait(DEMO_STEP_DELAY_MS);
    el("user-list").querySelector('[data-user-id="user-1"]').click();
    await wait(DEMO_STEP_DELAY_MS);
    el("start-button").click();
}

async function captureAndAnalyzeFrame(runId = activeAnalysisRunId) {
    if (runId !== activeAnalysisRunId || !selectedExercise) return;
    const video = el("camera-video");
    if (isAnalyzing || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    isAnalyzing = true;
    const canvas = el("capture-canvas");
    // Match object-fit: cover in the preview, including non-4:3 cameras.
    const ratio = CAPTURE_WIDTH / CAPTURE_HEIGHT;
    const sourceWidth = Math.min(video.videoWidth, video.videoHeight * ratio);
    const sourceHeight = sourceWidth / ratio;
    canvas.getContext("2d").drawImage(video,
        (video.videoWidth - sourceWidth) / 2, (video.videoHeight - sourceHeight) / 2,
        sourceWidth, sourceHeight, 0, 0, CAPTURE_WIDTH, CAPTURE_HEIGHT);
    const image = canvas.toDataURL("image/jpeg", 0.72);
    const controller = new AbortController();
    activeAnalysisController = controller;
    const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
    try {
        const response = await fetch("/analyze_frame", { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal, body: JSON.stringify({ image, exercise_key: selectedExercise.key, mode: selectedExercise.key, analysis_session: serverAnalysisSession }) });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || "서버 분석에 실패했습니다.");
        if (runId !== activeAnalysisRunId || !el("training-view").classList.contains("active-view")) return;
        applyAnalysisResult(result);
    } catch (error) {
        if (runId !== activeAnalysisRunId) return;
        if (isRomExercise()) {
            setText(el("rom-result-message"), "분석 응답을 기다리고 있습니다. 자세를 유지해주세요.");
        } else {
            setText(el("exercise-state"), "ANALYZING");
            setText(el("feedback-text"), "분석 응답을 기다리고 있습니다. 자세를 유지해주세요.");
        }
    } finally {
        clearTimeout(timeoutId);
        if (activeAnalysisController === controller) activeAnalysisController = null;
        if (runId === activeAnalysisRunId) isAnalyzing = false;
    }
}

function renderTracking(result) {
    const tracking = result.tracking || {};
    const button = el("confirm-target-button");
    if (button) button.hidden = !tracking.requires_confirmation;
    const canvas = el("tracking-overlay");
    if (!canvas) return;
    canvas.hidden = !TRACKING_DEBUG;
    if (!TRACKING_DEBUG) return;
    canvas.width = CAPTURE_WIDTH; canvas.height = CAPTURE_HEIGHT;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 2;
    function box(b, color, label) {
        if (!b) return;
        ctx.strokeStyle = color; ctx.fillStyle = color;
        ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]);
        if (label) ctx.fillText(label, b[0] + 3, b[1] + 15);
    }
    box(tracking.roi, "#ffffff", "ROI");
    (tracking.people || []).forEach(p => box(p.box, p.id === tracking.target_id ? "#27e5a5" : "#ffb347", String(p.id)));
}

function applyAnalysisResult(result) {
    renderTracking(result);
    if (result.analysis_valid === false) {
        setText(el("exercise-state"), result.state);
        setText(el("feedback-text"), result.feedback);
        setText(el("camera-message"), result.feedback);
        setText(el("rom-result-message"), result.feedback);
        return;
    }
    if (result.tracking) setText(el("camera-message"), "운동자가 인식되었습니다.");
    if (isRomExercise() || Number.isFinite(result.max_angle)) {
        applyRomAnalysisResult(result);
        return;
    }
    const accuracy = Number.isFinite(result.accuracy) ? result.accuracy : 0;
    const angle = Number.isFinite(result.angle) ? result.angle : 0;
    const target = Number.isFinite(result.target_angle) ? result.target_angle : selectedExercise.angle;
    const torso = Number.isFinite(result.torso_rotation) ? Math.round(result.torso_rotation) : 0;
    const targetTorso = Number.isFinite(result.target_torso_rotation) ? Math.round(result.target_torso_rotation) : 0;
    setText(el("exercise-state"), result.state || "TRACKING");
    setText(el("accuracy-value"), `${Math.round(accuracy)}%`);
    setText(el("angle-value"), `팔 ${Math.round(angle)} / ${Math.round(target)}° · 몸통 ${torso} / ${targetTorso}°`);
    setText(el("feedback-text"), result.feedback || "분석 결과가 화면에 반영됩니다.");
    collectExerciseSample(result);
    if (result.instruction) setText(el("exercise-description"), result.instruction);
    if (Number.isFinite(result.completed_stages) && Number.isFinite(result.total_stages)) {
        currentRep = result.completed_stages;
        setText(el("rep-counter"), `${result.completed_stages} / ${result.total_stages}`);
    }
    setText(el("camera-message"), result.state === "COMPLETE" ? "오늘 운동을 완료했습니다." : result.tracking ? "운동자가 인식되었습니다." : "카메라 프레임을 서버로 전송하고 있습니다.");
}

function applyRomAnalysisResult(result) {
    romLatestResult = result;
    updateRomCheckUI(result);
    collectExerciseSample(result);
    if (romPhase !== "result") setRomPhase("measuring");
}

function collectExerciseSample(result) {
    if (!exerciseSession || exerciseSession.saved || result.analysis_valid === false) return;
    exerciseSession.samples.push({
        accuracy: Number.isFinite(result.accuracy) ? Number(result.accuracy) : null,
        feedback: result.feedback || "",
        state: result.state || "",
        stage: result.stage || null,
        maxAngle: Number.isFinite(result.max_angle) ? Number(result.max_angle) : null,
        romStatus: result.rom_status || "",
        feedbackSummary: result.feedback_summary || "",
        capturedAt: new Date().toISOString()
    });
}

function summarizeFeedback(samples) {
    if (exerciseSession?.exerciseKey === ROM_SHOULDER_KEY) {
        const maxAngle = Math.max(0, ...samples.map((sample) => sample.maxAngle).filter(Number.isFinite));
        const latestStatus = [...samples].reverse().find((sample) => sample.romStatus)?.romStatus || "인식 실패";
        return `최대 가동 범위 ${Math.round(maxAngle)}도, ${latestStatus}로 측정되었습니다.`;
    }
    const messages = [];
    samples.forEach((sample) => {
        if (sample.feedback && !messages.includes(sample.feedback)) messages.push(sample.feedback);
    });
    return messages.slice(-3).join(" / ") || "운동 기록이 저장되었습니다.";
}

function averageAccuracy(samples) {
    if (exerciseSession?.exerciseKey === ROM_SHOULDER_KEY) return null;
    const values = samples.map((sample) => sample.accuracy).filter(Number.isFinite);
    if (!values.length) return null;
    return Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100) / 100;
}

function exerciseNameByKey(key) {
    return exercises.find((exercise) => exercise.key === key)?.name || key;
}

function parseUtcTimestamp(value) {
    if (!value) return null;
    const text = String(value).trim();
    if (!text) return null;
    const normalized = text.includes("T") ? text : text.replace(" ", "T");
    const timestamp = UTC_OFFSET_PATTERN.test(normalized) ? normalized : `${normalized}Z`;
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? null : date;
}

function formatRecordDate(value) {
    const date = parseUtcTimestamp(value);
    if (!date) return "";
    const parts = Object.fromEntries(RECORD_DATE_FORMATTER.formatToParts(date).map((part) => [part.type, part.value]));
    return `${parts.month}. ${parts.day}. ${parts.hour}:${parts.minute}`;
}

function formatRecordAccuracy(record) {
    if (record?.exercise_key === ROM_SHOULDER_KEY) return "해당 없음";
    return Number.isFinite(record?.accuracy_avg) ? `${Math.round(record.accuracy_avg)}%` : "--%";
}

async function loadExerciseRecords() {
    if (!currentUser) {
        setText(el("record-user-name"), "--");
        setText(el("record-total-count"), "0개");
        el("record-list").innerHTML = `<p class="empty-state">사용자를 먼저 선택해주세요.</p>`;
        return;
    }
    setText(el("record-user-name"), currentUser.name);
    setText(el("record-latest-key"), "--");
    setText(el("record-latest-accuracy"), "--%");
    el("record-list").innerHTML = `<p class="empty-state">기록을 불러오는 중입니다.</p>`;
    try {
        const data = await fetchJSON(`/api/users/${currentUser.id}/exercise-records`);
        const records = data.records || [];
        setText(el("record-total-count"), `${records.length}개`);
        if (!records.length) {
            el("record-list").innerHTML = `<p class="empty-state">저장된 운동 기록이 없습니다.</p>`;
            return;
        }
        const latest = records[0];
        setText(el("record-latest-key"), exerciseNameByKey(latest.exercise_key));
        setText(el("record-latest-accuracy"), formatRecordAccuracy(latest));
        el("record-list").innerHTML = records.map((record) => `
            <article>
                <span>${formatRecordDate(record.ended_at || record.started_at)}</span>
                <strong>${exerciseNameByKey(record.exercise_key)}</strong>
                <p>${record.feedback_summary || "저장된 피드백 요약이 없습니다."}</p>
            </article>`).join("");
    } catch (error) {
        setText(el("record-total-count"), "0개");
        el("record-list").innerHTML = `<p class="empty-state">운동 기록을 불러오지 못했습니다: ${error.message}</p>`;
    }
}

function openRecordsView() {
    showView("records-view");
    loadExerciseRecords();
}

async function finishExerciseSession() {
    if (!exerciseSession || exerciseSession.saved) {
        if (isRomExercise()) {
            setRomPhase("result");
            setText(el("rom-result-message"), exerciseSession?.saved ? "이미 저장된 결과입니다." : "저장할 측정 결과가 없습니다. 먼저 측정을 시작해주세요.");
            return;
        }
        showView("exercise-view");
        return;
    }
    if (exerciseSession.saving) return;
    if (!exerciseSession.samples.length) {
        setText(el("feedback-text"), "신뢰할 수 있는 측정 결과가 없습니다. 운동자를 확인하고 다시 측정해주세요.");
        setText(el("rom-result-message"), "신뢰할 수 있는 측정 결과가 없어 저장할 수 없습니다.");
        return;
    }
    exerciseSession.saving = true;

    const isRomSession = exerciseSession.exerciseKey === ROM_SHOULDER_KEY;
    const actionButton = isRomSession ? el("rom-save-button") : el("return-button");
    actionButton.disabled = true;
    setText(actionButton, isRomSession ? "저장 중" : "기록 저장 중");
    stopCameraExercise();

    const payload = {
        user_id: exerciseSession.userId,
        exercise_key: exerciseSession.exerciseKey,
        accuracy_avg: averageAccuracy(exerciseSession.samples),
        feedback_summary: summarizeFeedback(exerciseSession.samples),
        started_at: exerciseSession.startedAt,
        ended_at: new Date().toISOString()
    };

    try {
        await fetchJSON("/api/exercise-records", { method: "POST", body: JSON.stringify(payload) });
        exerciseSession.saved = true;
        if (isRomSession) {
            setRomPhase("result");
            setText(el("rom-result-message"), `${payload.feedback_summary} 결과가 저장되었습니다.`);
        } else {
            setText(el("feedback-text"), "운동 기록이 저장되었습니다.");
            setText(el("camera-message"), "기록 저장 완료");
        }
    } catch (error) {
        if (isRomSession) {
            setText(el("rom-result-message"), `결과를 저장하지 못했습니다: ${error.message}`);
        } else {
            setText(el("feedback-text"), `운동 기록을 저장하지 못했습니다: ${error.message}`);
            setText(el("camera-message"), "저장 실패. 다시 저장하거나 운동 선택 화면으로 이동할 수 있습니다.");
        }
    } finally {
        if (!exerciseSession) return;
        exerciseSession.saving = false;
        if (isRomSession) {
            setText(actionButton, exerciseSession.saved ? "저장 완료" : "결과 저장");
            actionButton.disabled = exerciseSession.saved;
            return;
        }
        setText(actionButton, exerciseSession.saved ? "운동 선택으로" : "다시 저장");
        actionButton.disabled = false;
        if (exerciseSession.saved) {
            returnToExerciseTimer = setTimeout(() => {
                returnToExerciseTimer = null;
                resetExerciseSession();
                showView("exercise-view");
            }, 900);
        }
    }
}

el("guide-video").addEventListener("loadeddata", () => { el("guide-placeholder").hidden = true; el("guide-video").hidden = false; playPendingRomGuideVideo(); });
el("guide-video").addEventListener("canplay", playPendingRomGuideVideo);
el("guide-video").addEventListener("error", () => { el("guide-video").hidden = true; el("guide-placeholder").hidden = false; });
el("new-code-button").addEventListener("click", issuePairingCode);
el("complete-pairing-button").addEventListener("click", completePairingForDemo);
el("change-user-button").addEventListener("click", () => showView("user-view"));
el("records-button").addEventListener("click", openRecordsView);
el("start-button").addEventListener("click", startSelectedRehabExercise);
el("exercise-start-button").addEventListener("click", startSelectedRehabExercise);
el("health-check-start-button").addEventListener("click", startSelectedHealthCheck);
el("return-button").addEventListener("click", finishExerciseSession);
el("rom-start-button").addEventListener("click", startRomMeasurement);
el("rom-stop-button").addEventListener("click", stopRomMeasurement);
el("rom-retry-button").addEventListener("click", retryRomMeasurement);
el("rom-save-button").addEventListener("click", finishExerciseSession);
el("rom-back-button").addEventListener("click", leaveRomMeasurement);
el("user-list").addEventListener("click", (event) => { const card = event.target.closest(".user-card"); if (card) selectUser(card.dataset.userId); });
el("exercise-list").addEventListener("click", (event) => { const row = event.target.closest(".exercise-row"); if (row) chooseExercise(row.dataset.exercise); });
el("health-check-list").addEventListener("click", (event) => { const row = event.target.closest(".health-check-card"); if (row) chooseHealthCheck(row.dataset.check); });
el("today-list").addEventListener("click", (event) => { const item = event.target.closest(".today-item"); if (item) chooseExercise(item.dataset.exercise); });
document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
    const viewId = button.dataset.view;
    if (viewId === "exercise-view") {
        if (!selectedExercise || isRomExercise(selectedExercise)) selectedExercise = getSelectedOrFirstExercise();
        renderExerciseList();
        renderSelectedExercise();
    }
    if (viewId === "health-check-view") {
        renderHealthCheckList();
        renderSelectedHealthCheck();
    }
    showView(viewId);
}));

async function initializeApp() {
    updateMirrorScale();
    window.addEventListener("resize", updateMirrorScale);
    updateDateTime();
    setInterval(updateDateTime, 1000);
    setInterval(() => {
        pairingRemaining = Math.max(0, pairingRemaining - 1);
        if (pairingRemaining <= 0) issuePairingCode();
        else updatePairingTimer();
    }, 1000);

    try {
        await loadDevice();
        await Promise.all([loadUsers(), loadExercises(), issuePairingCode()]);
        pairingPollTimer = setInterval(refreshPairingStatus, PAIRING_STATUS_INTERVAL_MS);
        if (DEMO_MODE) {
            selectUser("user-1");
            runDemoFlow();
        }
    } catch (error) {
        setText(el("pairing-status-title"), "초기 데이터 로딩 실패");
        setText(el("pairing-status-message"), error.message);
    }
}

initializeApp();

// Reconfirmation starts a fresh measurement so two people's results cannot mix.
el("confirm-target-button")?.addEventListener("click", () => {
    resetExerciseSession();
    romLatestResult = null;
    startTrackingForSelectedExercise();
});
