const CAPTURE_WIDTH = 480;
const CAPTURE_HEIGHT = 360;
const ANALYZE_INTERVAL_MS = 300;
const JPEG_QUALITY = 0.72;

function updateMirrorScale() {
    const baseWidth = 1080;
    const baseHeight = 1920;
    const scale = Math.min(window.innerWidth / baseWidth, window.innerHeight / baseHeight);
    document.documentElement.style.setProperty("--mirror-scale", scale);
}

const exercises = [
    { key: "shoulder", name: "앉아서 양팔 들고 몸통 돌리기", category: "어깨·몸통 재활", part: "상체", target: 3, duration: "약 1분", angle: 155, description: "의자에 앉아 양팔을 들고 왼쪽, 정면, 오른쪽 순서로 몸통을 움직입니다.", guide: "가이드 영상에 맞춰 양팔을 올리고 몸통을 좌우로 천천히 돌립니다." },
    { key: "knee", name: "무릎 굽혔다 펴기", category: "무릎 재활", part: "하체", target: 15, duration: "약 7분", angle: 70, description: "무릎을 안정적으로 굽혔다 펴며 하체 움직임을 확인합니다.", guide: "의자나 벽을 잡고 무리하지 않는 범위에서 진행하세요." },
    { key: "flexibility", name: "옆구리 늘리기", category: "유연성", part: "상체", target: 12, duration: "약 6분", angle: 75, description: "몸통을 천천히 기울여 옆구리와 허리 주변을 풀어줍니다.", guide: "반동을 주지 말고 숨을 편안히 쉬면서 움직이세요." },
    { key: "balance", name: "균형 운동", category: "기본 운동", part: "전신", target: 12, duration: "약 7분", angle: 65, description: "자세 흔들림을 줄이고 일상 보행 안정성을 높입니다.", guide: "필요하면 보호자나 벽을 가까이 두고 진행하세요." },
    { key: "strength", name: "근력 강화 운동", category: "근력 운동", part: "전신", target: 12, duration: "약 9분", angle: 80, description: "일상생활에 필요한 근력과 자세 유지 능력을 연습합니다.", guide: "천천히 움직이고 통증이 생기면 바로 멈추세요." }
];

let selectedExercise = exercises[0];
let cameraStream = null;
let analyzeTimer = null;
let isAnalyzing = false;
let currentRep = 0;

const els = {
    date: document.getElementById("current-date"),
    time: document.getElementById("current-time"),
    exerciseList: document.getElementById("exercise-list"),
    exerciseCount: document.getElementById("exercise-count"),
    selectedTitle: document.getElementById("selected-title"),
    selectedDescription: document.getElementById("selected-description"),
    exerciseTitle: document.getElementById("exercise-title"),
    exerciseDescription: document.getElementById("exercise-description"),
    exerciseState: document.getElementById("exercise-state"),
    repCounter: document.getElementById("rep-counter"),
    cameraMessage: document.getElementById("camera-message"),
    feedbackText: document.getElementById("feedback-text"),
    accuracyValue: document.getElementById("accuracy-value"),
    angleValue: document.getElementById("angle-value"),
    guideVideo: document.getElementById("guide-video"),
    guidePlaceholder: document.getElementById("guide-placeholder"),
    guideTitle: document.getElementById("guide-title"),
    guidePath: document.getElementById("guide-path"),
    cameraVideo: document.getElementById("camera-video"),
    captureCanvas: document.getElementById("capture-canvas"),
    cameraPlaceholder: document.getElementById("camera-placeholder"),
    fallbackTitle: document.getElementById("fallback-title"),
    startButton: document.getElementById("start-button"),
    returnButton: document.getElementById("return-button"),
    homeCameraState: document.getElementById("home-camera-state"),
    profileCameraState: document.getElementById("profile-camera-state")
};

function setText(element, value) {
    if (element) element.textContent = value;
}

function setCameraState(text, active = false) {
    [els.homeCameraState, els.profileCameraState].forEach((element) => {
        if (!element) return;
        element.classList.toggle("camera-active", active);
        element.lastChild.textContent = text;
    });
}

function showStatus(message, state = null) {
    setText(els.cameraMessage, message);
    if (state) setText(els.exerciseState, state);
}

function updateDateTime() {
    const now = new Date();
    setText(els.date, now.toLocaleDateString("ko-KR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        weekday: "long"
    }));
    setText(els.time, now.toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
    }));
}

function showView(viewId) {
    document.querySelectorAll(".app-view").forEach((view) => {
        view.classList.toggle("active-view", view.id === viewId);
    });
}

function renderExerciseList() {
    if (!els.exerciseList) return;
    setText(els.exerciseCount, `${exercises.length}개`);
    els.exerciseList.innerHTML = exercises.map((exercise) => `
        <button type="button" class="exercise-row" data-exercise="${exercise.key}">
            <span>${exercise.category}</span>
            <div>
                <strong>${exercise.name}</strong>
                <em>${exercise.part} · ${exercise.target}회 · ${exercise.duration}</em>
            </div>
        </button>
    `).join("");
}

function renderSelectedExercise() {
    setText(els.selectedTitle, selectedExercise.name);
    setText(els.selectedDescription, selectedExercise.description);
    setText(els.exerciseTitle, selectedExercise.name);
    setText(els.exerciseDescription, selectedExercise.guide);
    setText(els.repCounter, `${currentRep} / ${selectedExercise.target}`);
    setText(els.angleValue, `-- / ${selectedExercise.angle}°`);
    setText(els.fallbackTitle, selectedExercise.name);
    setText(els.guideTitle, selectedExercise.name);
    setText(els.guidePath, `static/videos/${selectedExercise.key}.mp4`);

    if (els.guideVideo) {
        els.guideVideo.pause();
        els.guideVideo.src = `/static/videos/${selectedExercise.key}.mp4`;
        els.guideVideo.load();
    }

    document.querySelectorAll(".exercise-row").forEach((button) => {
        button.classList.toggle("selected-row", button.dataset.exercise === selectedExercise.key);
    });
    document.querySelectorAll(".today-item").forEach((button) => {
        button.classList.toggle("selected-today", button.dataset.exercise === selectedExercise.key);
    });
}

if (els.guideVideo) {
    els.guideVideo.addEventListener("loadeddata", () => {
        if (els.guidePlaceholder) els.guidePlaceholder.hidden = true;
        els.guideVideo.hidden = false;
    });
    els.guideVideo.addEventListener("error", () => {
        els.guideVideo.hidden = true;
        if (els.guidePlaceholder) els.guidePlaceholder.hidden = false;
    });
}

function resetExerciseState(message = "운동 시작 후 카메라 화면이 표시됩니다.") {
    stopCameraExercise();
    currentRep = 0;
    setText(els.exerciseState, "READY");
    setText(els.feedbackText, "통증이 있으면 즉시 중단하고 보호자에게 알려주세요.");
    setText(els.accuracyValue, "--%");
    showStatus(message);
    renderSelectedExercise();
}

function chooseExercise(key) {
    const nextExercise = exercises.find((exercise) => exercise.key === key);
    if (!nextExercise) return;
    selectedExercise = nextExercise;
    resetExerciseState("선택한 운동으로 준비되었습니다.");
}

function stopCameraExercise() {
    if (analyzeTimer) {
        clearInterval(analyzeTimer);
        analyzeTimer = null;
    }
    isAnalyzing = false;

    if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
        cameraStream = null;
    }

    if (els.cameraVideo) {
        els.cameraVideo.pause();
        els.cameraVideo.srcObject = null;
        els.cameraVideo.classList.remove("camera-ready");
    }
    if (els.cameraPlaceholder) els.cameraPlaceholder.hidden = false;
    setCameraState("카메라 준비", false);
}

async function startCameraExercise() {
    showView("training-view");
    stopCameraExercise();
    renderSelectedExercise();
    showStatus("카메라 권한을 요청하고 있습니다.", "STARTING");

    try {
        await fetch("/reset_exercise", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ exercise_key: selectedExercise.key })
        });
    } catch (error) {
        console.warn("Exercise reset failed:", error);
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showStatus("브라우저 보안 설정 때문에 카메라 API를 사용할 수 없습니다.", "ERROR");
        return;
    }

    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: CAPTURE_WIDTH },
                height: { ideal: CAPTURE_HEIGHT },
                facingMode: "user"
            },
            audio: false
        });

        els.cameraVideo.srcObject = cameraStream;
        await els.cameraVideo.play();
        els.cameraVideo.classList.add("camera-ready");
        if (els.cameraPlaceholder) els.cameraPlaceholder.hidden = true;
        setCameraState("카메라 작동 중", true);
        showStatus("서버 분석을 시작합니다.", "TRACKING");

        analyzeTimer = setInterval(captureAndAnalyzeFrame, ANALYZE_INTERVAL_MS);
        captureAndAnalyzeFrame();
    } catch (error) {
        console.error("Camera start failed:", error);
        showStatus(`카메라를 시작하지 못했습니다: ${error.message}`, "ERROR");
        setText(els.feedbackText, "카메라 권한, 연결 상태, HTTPS 또는 localhost 접속 여부를 확인해 주세요.");
        if (els.cameraPlaceholder) els.cameraPlaceholder.hidden = false;
    }
}

async function captureAndAnalyzeFrame() {
    if (isAnalyzing || !els.cameraVideo || !els.captureCanvas) return;
    if (els.cameraVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;

    isAnalyzing = true;
    const context = els.captureCanvas.getContext("2d");
    els.captureCanvas.width = CAPTURE_WIDTH;
    els.captureCanvas.height = CAPTURE_HEIGHT;
    context.drawImage(els.cameraVideo, 0, 0, CAPTURE_WIDTH, CAPTURE_HEIGHT);
    const image = els.captureCanvas.toDataURL("image/jpeg", JPEG_QUALITY);

    try {
        const response = await fetch("/analyze_frame", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                image,
                exercise_key: selectedExercise.key
            })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "서버 분석에 실패했습니다.");
        }
        applyAnalysisResult(result);
    } catch (error) {
        console.error("Frame analysis failed:", error);
        showStatus("서버 분석 응답을 받지 못했습니다.", "ERROR");
        setText(els.feedbackText, error.message);
    } finally {
        isAnalyzing = false;
    }
}

function applyAnalysisResult(result) {
    const accuracy = Number.isFinite(result.accuracy) ? result.accuracy : 0;
    const angle = Number.isFinite(result.angle) ? result.angle : 0;
    const targetAngle = Number.isFinite(result.target_angle) ? result.target_angle : selectedExercise.angle;

    setText(els.exerciseState, result.state || "TRACKING");
    setText(els.accuracyValue, `${Math.round(accuracy)}%`);
    setText(els.angleValue, `${Math.round(angle)} / ${Math.round(targetAngle)}°`);
    setText(els.feedbackText, result.feedback || "분석 결과를 화면에 반영했습니다.");
    if (result.instruction) setText(els.exerciseDescription, result.instruction);

    if (Number.isFinite(result.completed_stages) && Number.isFinite(result.total_stages)) {
        currentRep = result.completed_stages;
        setText(els.repCounter, `${result.completed_stages} / ${result.total_stages}`);
    }
    if (result.state === "COMPLETE") {
        setText(els.cameraMessage, "오늘 운동을 완료했습니다.");
    } else if (Number.isFinite(result.hold_count) && Number.isFinite(result.hold_target)) {
        setText(els.cameraMessage, `자세 유지 ${result.hold_count} / ${result.hold_target}`);
    } else {
        setText(els.cameraMessage, "카메라 프레임을 서버로 전송하고 있습니다.");
    }
}

function returnHome() {
    resetExerciseState();
    showView("home-view");
}

updateMirrorScale();
window.addEventListener("resize", updateMirrorScale);

updateDateTime();
setInterval(updateDateTime, 1000);
renderExerciseList();
renderSelectedExercise();

if (els.startButton) els.startButton.addEventListener("click", startCameraExercise);
if (els.returnButton) els.returnButton.addEventListener("click", returnHome);

document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
});

document.querySelectorAll(".today-item").forEach((button) => {
    button.addEventListener("click", () => chooseExercise(button.dataset.exercise));
});

if (els.exerciseList) {
    els.exerciseList.addEventListener("click", (event) => {
        const button = event.target.closest(".exercise-row");
        if (!button) return;
        chooseExercise(button.dataset.exercise);
    });
}
