// 1080x1920 세로형 스마트미러 캔버스를 현재 브라우저 크기에 맞춰 비율 그대로 축소합니다.
function updateMirrorScale() {
    const baseWidth = 1080;
    const baseHeight = 1920;
    // 화면을 90도 회전해서 일반 가로 모니터를 꽉 채우므로 너비/높이 기준을 서로 바꿔 계산합니다.
    const scale = Math.min(window.innerWidth / baseHeight, window.innerHeight / baseWidth);

    document.documentElement.style.setProperty("--mirror-scale", scale);
}

// UI 시안에서 사용할 운동별 표시 데이터입니다.
const exercises = {
    shoulder: {
        title: "어깨 관절 가동 범위 운동",
        description: "팔을 천천히 들어 올리며 어깨 각도를 확인합니다. 무리하지 않는 범위에서 정확한 자세를 유지하세요.",
        target: 15,
        sets: "1 / 3",
        speed: "천천히",
        targetAngle: 80,
        duration: "약 8분",
        level: "기초",
        note: "통증이 있으면 즉시 중단"
    },
    knee: {
        title: "무릎 굽힘 균형 운동",
        description: "무릎을 천천히 굽히며 몸의 중심이 흔들리지 않도록 균형을 유지합니다.",
        target: 12,
        sets: "1 / 2",
        speed: "보통",
        targetAngle: 65,
        duration: "약 6분",
        level: "기초",
        note: "상체를 곧게 유지"
    },
    elbow: {
        title: "팔꿈치 굽힘 반복 운동",
        description: "팔꿈치를 일정한 속도로 굽혔다 펴며 관절 각도와 반복 정확도를 확인합니다.",
        target: 20,
        sets: "1 / 3",
        speed: "일정하게",
        targetAngle: 100,
        duration: "약 7분",
        level: "중간",
        note: "손목 힘을 빼고 진행"
    }
};

let selectedExerciseKey = "shoulder";
let exerciseTimer = null;
let currentRep = 0;

// 현재 날짜와 시간을 1초마다 화면에 표시합니다.
function updateDateTime() {
    const now = new Date();

    const dateText = now.toLocaleDateString("ko-KR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        weekday: "long"
    });

    const timeText = now.toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
    });

    document.getElementById("current-date").textContent = dateText;
    document.getElementById("current-time").textContent = timeText;
}

// 하단 버튼에 따라 중앙 콘텐츠 화면을 전환합니다.
function showView(viewId) {
    document.querySelectorAll(".app-view").forEach((view) => {
        view.classList.toggle("active-view", view.id === viewId);
    });

    document.getElementById("select-button").classList.toggle("active-action", viewId === "selection-view");
    document.getElementById("records-button").classList.toggle("active-action", viewId === "records-view");
}

// 선택한 운동 데이터를 메인 운동 화면과 선택 요약 영역에 반영합니다.
function renderSelectedExercise() {
    const exercise = exercises[selectedExerciseKey];

    document.getElementById("exercise-title").textContent = exercise.title;
    document.getElementById("exercise-description").textContent = exercise.description;
    document.getElementById("target-count").textContent = `${exercise.target}회`;
    document.getElementById("set-count").textContent = exercise.sets;
    document.getElementById("exercise-speed").textContent = exercise.speed;
    document.getElementById("target-angle").textContent = `목표 각도 ${exercise.targetAngle}°`;
    document.getElementById("rep-counter").textContent = `${currentRep} / ${exercise.target}`;
    document.getElementById("selected-duration").textContent = exercise.duration;
    document.getElementById("selected-level").textContent = exercise.level;
    document.getElementById("selected-note").textContent = exercise.note;

    document.querySelectorAll(".exercise-option").forEach((button) => {
        button.classList.toggle("selected-option", button.dataset.exercise === selectedExerciseKey);
    });
}

// 운동 시작 시안입니다. 실제 센서 없이도 횟수, 정확도, 각도, 피드백이 움직입니다.
function startExerciseDemo() {
    const exercise = exercises[selectedExerciseKey];

    showView("exercise-view");
    clearInterval(exerciseTimer);
    currentRep = 0;

    document.getElementById("exercise-state").textContent = "TRACKING";
    document.getElementById("camera-message").textContent = "자세를 인식하고 있습니다.";
    document.getElementById("feedback-text").textContent = "좋아요. 천천히 움직임을 이어가세요.";
    renderSelectedExercise();

    exerciseTimer = setInterval(() => {
        currentRep += 1;

        const accuracy = Math.min(96, 84 + currentRep);
        const angle = Math.min(exercise.targetAngle, Math.round(exercise.targetAngle * (0.55 + currentRep / exercise.target * 0.45)));
        const isComplete = currentRep >= exercise.target;

        document.getElementById("rep-counter").textContent = `${Math.min(currentRep, exercise.target)} / ${exercise.target}`;
        document.getElementById("accuracy-value").textContent = `${accuracy}%`;
        document.getElementById("accuracy-progress").style.width = `${accuracy}%`;
        document.getElementById("angle-value").textContent = `${angle}°`;
        document.getElementById("feedback-text").textContent = isComplete
            ? "운동 완료. 안정적으로 수행했습니다."
            : "좋아요. 호흡을 유지하며 같은 속도로 반복하세요.";

        if (isComplete) {
            clearInterval(exerciseTimer);
            document.getElementById("exercise-state").textContent = "COMPLETE";
            document.getElementById("camera-message").textContent = "오늘 운동 기록이 임시 저장되었습니다.";
        }
    }, 900);
}

// 창 크기가 바뀌어도 세로형 UI 비율을 유지합니다.
updateMirrorScale();
window.addEventListener("resize", updateMirrorScale);

// 페이지가 열리면 즉시 한 번 실행하고, 이후 1초마다 갱신합니다.
updateDateTime();
setInterval(updateDateTime, 1000);
renderSelectedExercise();

// 하단 조작 버튼과 운동 선택 버튼을 연결합니다.
document.getElementById("start-button").addEventListener("click", startExerciseDemo);
document.getElementById("select-button").addEventListener("click", () => showView("selection-view"));
document.getElementById("records-button").addEventListener("click", () => showView("records-view"));

document.querySelectorAll(".exercise-option").forEach((button) => {
    button.addEventListener("click", () => {
        selectedExerciseKey = button.dataset.exercise;
        currentRep = 0;
        clearInterval(exerciseTimer);
        document.getElementById("exercise-state").textContent = "READY";
        document.getElementById("camera-message").textContent = "선택한 운동으로 준비되었습니다.";
        renderSelectedExercise();
        showView("exercise-view");
    });
});
