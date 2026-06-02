const exercise = {
    title: "어깨 관절 가동 범위 운동",
    targetReps: 15,
    targetAngle: 80
};

let timerId = null;
let currentRep = 0;

function updateDateTime() {
    const now = new Date();

    document.getElementById("current-date").textContent = now.toLocaleDateString("ko-KR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        weekday: "short"
    });

    document.getElementById("current-time").textContent = now.toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
    });
}

function renderStatus({ accuracy, angle, stage, feedback }) {
    document.getElementById("accuracy-value").textContent = `${accuracy}%`;
    document.getElementById("accuracy-progress").style.width = `${accuracy}%`;
    document.getElementById("angle-value").textContent = `${angle}도`;
    document.getElementById("target-angle").textContent = `목표 각도 ${exercise.targetAngle}도`;
    document.getElementById("stage-value").textContent = stage;
    document.getElementById("rep-counter").textContent = `${currentRep} / ${exercise.targetReps}회`;
    document.getElementById("feedback-text").textContent = feedback;
}

function resetExercise() {
    clearInterval(timerId);
    timerId = null;
    currentRep = 0;

    document.getElementById("exercise-state").textContent = "READY";
    document.getElementById("camera-message").textContent = "카메라 또는 라즈베리파이 영상 입력을 연결할 영역입니다.";
    renderStatus({
        accuracy: 0,
        angle: 0,
        stage: "준비",
        feedback: "운동 시작 버튼을 누르면 예시 피드백이 표시됩니다."
    });
}

function startExerciseDemo() {
    resetExercise();
    document.getElementById("exercise-state").textContent = "TRACKING";
    document.getElementById("camera-message").textContent = "현재는 실제 카메라 대신 예시 데이터로 화면 흐름을 보여줍니다.";

    timerId = setInterval(() => {
        currentRep += 1;

        const progress = currentRep / exercise.targetReps;
        const accuracy = Math.min(96, Math.round(70 + progress * 26));
        const angle = Math.min(exercise.targetAngle, Math.round(exercise.targetAngle * (0.45 + progress * 0.55)));
        const isComplete = currentRep >= exercise.targetReps;

        renderStatus({
            accuracy,
            angle,
            stage: isComplete ? "완료" : "운동 중",
            feedback: isComplete
                ? "운동이 완료되었습니다. 안정적인 속도로 잘 수행했습니다."
                : "좋습니다. 팔을 천천히 올리고 같은 속도로 내려오세요."
        });

        if (isComplete) {
            clearInterval(timerId);
            timerId = null;
            document.getElementById("exercise-state").textContent = "COMPLETE";
        }
    }, 800);
}

updateDateTime();
setInterval(updateDateTime, 1000);
resetExercise();

document.getElementById("start-button").addEventListener("click", startExerciseDemo);
document.getElementById("reset-button").addEventListener("click", resetExercise);
