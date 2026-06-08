function updateMirrorScale() {
    const baseWidth = 1080;
    const baseHeight = 1920;
    const scale = Math.min(window.innerWidth / baseWidth, window.innerHeight / baseHeight);
    document.documentElement.style.setProperty("--mirror-scale", scale);
}

const exercises = [
    { key: "intro", name: "노인 입체운동에 대하여", category: "기초 안내", part: "전신", target: 0, duration: "약 5분", angle: 0, description: "입체운동의 목적과 스마트미러 사용 흐름을 확인합니다.", guide: "처음 사용하는 분은 이 안내 영상을 먼저 확인하면 좋습니다.", video: "/static/videos/intro.mp4" },
    { key: "intensity", name: "운동강도에 대한 쉬운 이해", category: "기초 안내", part: "전신", target: 0, duration: "약 4분", angle: 0, description: "운동 중 숨참, 피로감, 통증 신호를 쉽게 구분합니다.", guide: "운동 전 오늘 몸 상태를 확인하고 강도를 조절하는 데 사용합니다.", video: "/static/videos/intensity.mp4" },
    { key: "aerobic", name: "유산소 운동", category: "기본 운동", part: "전신", target: 20, duration: "약 10분", angle: 70, description: "지구력과 심폐 기능을 위한 가벼운 반복 운동입니다.", guide: "호흡을 편하게 유지하면서 일정한 속도로 움직여주세요.", video: "/static/videos/aerobic.mp4" },
    { key: "balance", name: "균형 운동", category: "기본 운동", part: "전신", target: 12, duration: "약 7분", angle: 65, description: "자세 흔들림을 줄이고 낙상 예방에 도움을 줍니다.", guide: "필요하면 의자나 벽을 잡고 안전하게 따라 해주세요.", video: "/static/videos/balance.mp4" },
    { key: "flexibility", name: "유연 운동", category: "기본 운동", part: "전신", target: 15, duration: "약 8분", angle: 75, description: "굳은 근육과 관절을 부드럽게 풀어주는 운동입니다.", guide: "반동을 주지 말고 천천히 늘려주세요.", video: "/static/videos/flexibility.mp4" },
    { key: "seated", name: "노인 앉은 자세 운동", category: "의자 운동", part: "전신", target: 15, duration: "약 8분", angle: 80, description: "의자에 앉아 안전하게 따라 할 수 있는 전신 운동입니다.", guide: "허리를 세우고 발바닥을 바닥에 붙인 상태로 진행해주세요.", video: "/static/videos/seated.mp4" },
    { key: "strength", name: "강화 운동", category: "근력 운동", part: "전신", target: 12, duration: "약 9분", angle: 80, description: "근력 유지와 일상 동작 회복을 돕는 운동입니다.", guide: "무리하게 힘을 주지 말고 가능한 범위에서 반복해주세요.", video: "/static/videos/strength.mp4" },
    { key: "shoulder", name: "어깨 유착성 피막염 운동", category: "어깨 재활", part: "상체", target: 15, duration: "약 8분", angle: 80, description: "어깨 관절을 부드럽게 움직이며 가동 범위를 확인합니다.", guide: "통증이 없는 범위에서 천천히 팔을 올리고 내립니다.", video: "/static/videos/shoulder.mp4" },
    { key: "disc", name: "요추 신경관 협착증 및 디스크 탈출증", category: "허리 재활", part: "코어", target: 10, duration: "약 8분", angle: 55, description: "허리에 부담을 줄이며 코어 안정성을 확인합니다.", guide: "허리 통증이 생기면 즉시 중단하고 전문가에게 확인해주세요.", video: "/static/videos/disc.mp4" },
    { key: "parkinson-aerobic", name: "파킨슨병 유산소 운동", category: "파킨슨 운동", part: "전신", target: 20, duration: "약 10분", angle: 70, description: "리듬감 있는 움직임으로 보행과 지구력을 돕습니다.", guide: "박자에 맞춰 천천히, 넘어지지 않도록 안정적으로 움직여주세요.", video: "/static/videos/parkinson-aerobic.mp4" },
    { key: "parkinson-strength", name: "파킨슨병 강화 운동", category: "파킨슨 운동", part: "전신", target: 12, duration: "약 9분", angle: 75, description: "일상생활에 필요한 근력과 자세 유지 능력을 돕습니다.", guide: "움직임이 작아지지 않도록 천천히 크게 따라 해주세요.", video: "/static/videos/parkinson-strength.mp4" }
];

let selectedExercise = exercises.find((exercise) => exercise.key === "shoulder");
let exerciseTimer = null;
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
    video: document.getElementById("exercise-video"),
    videoFallback: document.getElementById("video-fallback"),
    fallbackTitle: document.getElementById("fallback-title"),
    startButton: document.getElementById("start-button"),
    returnButton: document.getElementById("return-button")
};

function setText(element, value) {
    if (element) element.textContent = value;
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
                <em>${exercise.part} · ${exercise.target ? `${exercise.target}회` : "영상 안내"} · ${exercise.duration}</em>
            </div>
        </button>
    `).join("");
}

function setVideoSource(exercise) {
    if (!els.video) return;
    els.video.pause();
    els.video.removeAttribute("src");
    els.video.load();
    els.video.src = exercise.video;
    if (els.videoFallback) els.videoFallback.hidden = false;
    setText(els.fallbackTitle, exercise.name);
}

function renderSelectedExercise() {
    setText(els.selectedTitle, selectedExercise.name);
    setText(els.selectedDescription, selectedExercise.description);
    setText(els.exerciseTitle, selectedExercise.name);
    setText(els.exerciseDescription, selectedExercise.guide);
    setText(els.repCounter, `${currentRep} / ${selectedExercise.target || "-"}`);
    setText(els.angleValue, selectedExercise.angle ? `${Math.round(selectedExercise.angle * 0.92)}°` : "-");
    setVideoSource(selectedExercise);

    document.querySelectorAll(".exercise-row").forEach((button) => {
        button.classList.toggle("selected-row", button.dataset.exercise === selectedExercise.key);
    });
    document.querySelectorAll(".today-item").forEach((button) => {
        button.classList.toggle("selected-today", button.dataset.exercise === selectedExercise.key);
    });
}

function resetExerciseState(message = "운동 시작 후 진행률이 표시됩니다.") {
    clearInterval(exerciseTimer);
    currentRep = 0;
    setText(els.exerciseState, "READY");
    setText(els.cameraMessage, message);
    setText(els.feedbackText, "통증이 있으면 즉시 중단하고 보호자에게 알려주세요.");
    setText(els.accuracyValue, "92%");
    renderSelectedExercise();
}

function chooseExercise(key) {
    const nextExercise = exercises.find((exercise) => exercise.key === key);
    if (!nextExercise) return;
    selectedExercise = nextExercise;
    resetExerciseState("선택한 운동으로 준비되었습니다.");
}

function startExerciseDemo() {
    showView("training-view");
    clearInterval(exerciseTimer);
    currentRep = 0;

    setText(els.exerciseState, selectedExercise.target ? "TRACKING" : "GUIDE");
    setText(els.cameraMessage, selectedExercise.target ? "예시 영상을 보며 같은 속도로 따라 해주세요." : "안내 영상을 편안하게 시청해주세요.");
    setText(els.feedbackText, selectedExercise.guide);
    renderSelectedExercise();

    if (els.video) {
        els.video.play().then(() => {
            if (els.videoFallback) els.videoFallback.hidden = true;
        }).catch(() => {
            if (els.videoFallback) els.videoFallback.hidden = false;
        });
    }

    if (!selectedExercise.target) return;

    exerciseTimer = setInterval(() => {
        currentRep += 1;
        const progress = currentRep / selectedExercise.target;
        const accuracy = Math.min(97, Math.round(86 + progress * 10));
        const angle = Math.min(selectedExercise.angle, Math.round(selectedExercise.angle * (0.55 + progress * 0.45)));
        const completedRep = Math.min(currentRep, selectedExercise.target);
        const isComplete = currentRep >= selectedExercise.target;

        setText(els.repCounter, `${completedRep} / ${selectedExercise.target}`);
        setText(els.accuracyValue, `${accuracy}%`);
        setText(els.angleValue, `${angle}°`);
        setText(els.feedbackText, isComplete ? "운동 완료. 안정적으로 수행했습니다." : "좋아요. 호흡을 유지하면서 같은 속도로 반복해주세요.");

        if (isComplete) {
            clearInterval(exerciseTimer);
            setText(els.exerciseState, "COMPLETE");
            setText(els.cameraMessage, "오늘 운동 기록이 임시 저장되었습니다.");
            if (els.video) els.video.pause();
        }
    }, 900);
}

function returnHome() {
    clearInterval(exerciseTimer);
    if (els.video) els.video.pause();
    resetExerciseState();
    showView("home-view");
}

updateMirrorScale();
window.addEventListener("resize", updateMirrorScale);

updateDateTime();
setInterval(updateDateTime, 1000);
renderExerciseList();
renderSelectedExercise();

if (els.startButton) els.startButton.addEventListener("click", startExerciseDemo);
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
