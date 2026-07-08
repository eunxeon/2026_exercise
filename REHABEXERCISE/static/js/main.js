const CAPTURE_WIDTH = 480;
const CAPTURE_HEIGHT = 360;
const ANALYZE_INTERVAL_MS = 600;
const ANALYZE_TIMEOUT_MS = 4000;
const PAIRING_SECONDS = 600;
const DEFAULT_DEVICE_ID = "mirror-demo-001";
const PAIRING_STATUS_INTERVAL_MS = 3000;
const DEMO_MODE = new URLSearchParams(window.location.search).get("demo") === "1";
const DEMO_INITIAL_DELAY_MS = 6000;
const DEMO_STEP_DELAY_MS = 2600;
const DEMO_PLAYBACK_RATE = 1;
const DEMO_HOLD_SAMPLES = 6;
const DEMO_EXERCISE_DURATION_MS = 27000;

function updateMirrorScale() {
    const scale = Math.min((window.innerWidth * 0.92) / 1080, (window.innerHeight * 0.92) / 1920);
    document.documentElement.style.setProperty("--mirror-scale", scale);
}

let deviceId = DEFAULT_DEVICE_ID;
let users = [];
let exercises = [];
let selectedExercise = null;
let pairingRemaining = PAIRING_SECONDS;
let pairingPollTimer = null;
let cameraStream = null;
let analyzeTimer = null;
let isAnalyzing = false;
let currentRep = 0;
let demoFlowStarted = false;
let demoAnalysisTimer = null;
let demoStage = 1;
let demoHoldCount = 0;
let demoStartedAt = 0;
let demoCompleted = false;
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

function getSelectedOrFirstExercise() {
    return selectedExercise || exercises.find(isExerciseSupported) || exercises[0] || null;
}

function stopCameraExercise() {
    clearInterval(analyzeTimer);
    clearInterval(demoAnalysisTimer);
    analyzeTimer = null;
    demoAnalysisTimer = null;
    isAnalyzing = false;
    if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    const video = el("camera-video");
    if (video) { video.pause(); video.srcObject = null; video.classList.remove("camera-ready"); }
    if (el("camera-placeholder")) el("camera-placeholder").hidden = false;
}

function showView(viewId) {
    if (viewId !== "training-view") stopCameraExercise();
    document.querySelectorAll(".app-view").forEach((view) => view.classList.toggle("active-view", view.id === viewId));
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
    setText(el("home-avatar"), user.name[0]);
    setText(el("home-user-name"), `${user.name} 님`);
    setText(el("home-user-program"), `${user.program} · ${user.goal}`);
    showView("home-view");
}

function exerciseMetaText(exercise) {
    const status = isExerciseSupported(exercise) ? exercise.duration : `${exercise.duration} · 준비 중`;
    return `${exercise.part} · ${exercise.target}회 · ${status}`;
}

function renderTodayExercises() {
    const todayExercises = exercises.filter((exercise) => exercise.is_today);
    setText(el("today-count"), `${todayExercises.length}개`);
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
    setText(el("exercise-count"), `${exercises.length}개`);
    el("exercise-list").innerHTML = exercises.map((exercise) => {
        const supported = isExerciseSupported(exercise);
        return `
            <button type="button" class="exercise-row ${supported ? "" : "is-disabled"}" data-exercise="${exercise.key}">
                <span>${exercise.category}</span><div><strong>${exercise.name}</strong><em>${exerciseMetaText(exercise)}</em></div>
            </button>`;
    }).join("");
}

function renderSelectedExercise() {
    selectedExercise = getSelectedOrFirstExercise();
    if (!selectedExercise) return;
    const supported = isExerciseSupported(selectedExercise);
    const supportMessage = selectedExercise.support_message || "이 운동 분석은 추후 지원 예정입니다.";
    setText(el("selected-title"), selectedExercise.name);
    setText(el("selected-description"), supported ? selectedExercise.description : `${selectedExercise.description} ${supportMessage}`);
    setText(el("exercise-title"), selectedExercise.name);
    setText(el("exercise-description"), supported ? selectedExercise.guide : supportMessage);
    setText(el("rep-counter"), `${currentRep} / ${selectedExercise.target}`);
    setText(el("angle-value"), supported ? `-- / ${selectedExercise.angle}°` : "준비 중");
    setText(el("fallback-title"), selectedExercise.name);
    setText(el("guide-title"), selectedExercise.name);
    setText(el("guide-path"), selectedExercise.video_path || `static/videos/${selectedExercise.key}.mp4`);
    const guide = el("guide-video");
    guide.pause();
    guide.src = selectedExercise.video_path || `/static/videos/${selectedExercise.key}.mp4`;
    guide.load();
    const startButton = el("start-button");
    const exerciseStartButton = el("exercise-start-button");
    startButton.disabled = !supported;
    exerciseStartButton.disabled = !supported;
    setText(startButton, supported ? "선택한 운동 시작" : "추후 지원 예정");
    setText(exerciseStartButton, supported ? "이 운동 시작" : "추후 지원 예정");
    document.querySelectorAll("[data-exercise]").forEach((button) => {
        button.classList.toggle("selected-row", button.matches(".exercise-row") && button.dataset.exercise === selectedExercise.key);
        button.classList.toggle("selected-today", button.matches(".today-item") && button.dataset.exercise === selectedExercise.key);
    });
    renderTodayExercises();
}

function chooseExercise(key) {
    selectedExercise = exercises.find((item) => item.key === key) || selectedExercise;
    currentRep = 0;
    renderSelectedExercise();
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
    selectedExercise = exercises.find(isExerciseSupported) || exercises[0] || null;
    renderExerciseList();
    renderSelectedExercise();
}

function updateDateTime() {
    const now = new Date();
    setText(el("current-date"), now.toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", weekday: "long" }));
    setText(el("current-time"), now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));
}

async function startCameraExercise() {
    selectedExercise = getSelectedOrFirstExercise();
    if (!selectedExercise) return;
    if (!isExerciseSupported(selectedExercise)) {
        renderSelectedExercise();
        setText(el("feedback-text"), selectedExercise.support_message || "이 운동 분석은 추후 지원 예정입니다.");
        return;
    }
    showView("training-view");
    renderSelectedExercise();
    if (DEMO_MODE) {
        startDemoExercise();
        return;
    }
    setText(el("exercise-state"), "STARTING");
    setText(el("camera-message"), "카메라 권한을 요청하고 있습니다.");
    try {
        await fetchJSON("/reset_exercise", { method: "POST", body: JSON.stringify({ exercise_key: selectedExercise.key }) });
        cameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: CAPTURE_WIDTH }, height: { ideal: CAPTURE_HEIGHT }, facingMode: "user" }, audio: false });
        const video = el("camera-video");
        video.srcObject = cameraStream;
        await video.play();
        video.classList.add("camera-ready");
        el("camera-placeholder").hidden = true;
        setText(el("exercise-state"), "TRACKING");
        setText(el("camera-message"), "서버 분석을 시작합니다.");
        analyzeTimer = setInterval(captureAndAnalyzeFrame, ANALYZE_INTERVAL_MS);
        captureAndAnalyzeFrame();
    } catch (error) {
        setText(el("exercise-state"), "ERROR");
        setText(el("camera-message"), `카메라를 시작하지 못했습니다: ${error.message}`);
        setText(el("feedback-text"), "카메라 권한과 HTTPS 또는 localhost 접속 여부를 확인해주세요.");
    }
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

async function captureAndAnalyzeFrame() {
    const video = el("camera-video");
    if (isAnalyzing || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    isAnalyzing = true;
    const canvas = el("capture-canvas");
    canvas.getContext("2d").drawImage(video, 0, 0, CAPTURE_WIDTH, CAPTURE_HEIGHT);
    const image = canvas.toDataURL("image/jpeg", 0.72);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
    try {
        const response = await fetch("/analyze_frame", { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal, body: JSON.stringify({ image, exercise_key: selectedExercise.key }) });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || "서버 분석에 실패했습니다.");
        applyAnalysisResult(result);
    } catch (error) {
        setText(el("exercise-state"), "ANALYZING");
        setText(el("feedback-text"), "분석 응답을 기다리고 있습니다. 자세를 유지해주세요.");
    } finally {
        clearTimeout(timeoutId);
        isAnalyzing = false;
    }
}

function applyAnalysisResult(result) {
    const accuracy = Number.isFinite(result.accuracy) ? result.accuracy : 0;
    const angle = Number.isFinite(result.angle) ? result.angle : 0;
    const target = Number.isFinite(result.target_angle) ? result.target_angle : selectedExercise.angle;
    const torso = Number.isFinite(result.torso_rotation) ? Math.round(result.torso_rotation) : 0;
    const targetTorso = Number.isFinite(result.target_torso_rotation) ? Math.round(result.target_torso_rotation) : 0;
    setText(el("exercise-state"), result.state || "TRACKING");
    setText(el("accuracy-value"), `${Math.round(accuracy)}%`);
    setText(el("angle-value"), `팔 ${Math.round(angle)} / ${Math.round(target)}° · 몸통 ${torso} / ${targetTorso}°`);
    setText(el("feedback-text"), result.feedback || "분석 결과가 화면에 반영됩니다.");
    if (result.instruction) setText(el("exercise-description"), result.instruction);
    if (Number.isFinite(result.completed_stages) && Number.isFinite(result.total_stages)) {
        currentRep = result.completed_stages;
        setText(el("rep-counter"), `${result.completed_stages} / ${result.total_stages}`);
    }
    setText(el("camera-message"), result.state === "COMPLETE" ? "오늘 운동을 완료했습니다." : "카메라 프레임을 서버로 전송하고 있습니다.");
}

el("guide-video").addEventListener("loadeddata", () => { el("guide-placeholder").hidden = true; el("guide-video").hidden = false; });
el("guide-video").addEventListener("error", () => { el("guide-video").hidden = true; el("guide-placeholder").hidden = false; });
el("new-code-button").addEventListener("click", issuePairingCode);
el("complete-pairing-button").addEventListener("click", completePairingForDemo);
el("change-user-button").addEventListener("click", () => showView("user-view"));
el("start-button").addEventListener("click", startCameraExercise);
el("exercise-start-button").addEventListener("click", startCameraExercise);
el("return-button").addEventListener("click", () => showView("exercise-view"));
el("user-list").addEventListener("click", (event) => { const card = event.target.closest(".user-card"); if (card) selectUser(card.dataset.userId); });
el("exercise-list").addEventListener("click", (event) => { const row = event.target.closest(".exercise-row"); if (row) chooseExercise(row.dataset.exercise); });
el("today-list").addEventListener("click", (event) => { const item = event.target.closest(".today-item"); if (item) chooseExercise(item.dataset.exercise); });
document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));

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
