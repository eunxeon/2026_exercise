NO_PERSON_STATE = "NO_PERSON"
LOW_VISIBILITY_STATE = "LOW_VISIBILITY"

INVALID_EXERCISE_ANALYSIS_STATES = frozenset(
    {
        NO_PERSON_STATE,
        LOW_VISIBILITY_STATE,
        "WAITING_TARGET", "MULTIPLE_PEOPLE", "TARGET_LOST", "OCCLUDED",
        "STABILIZING", "LOW_CONFIDENCE", "TRACKING_ERROR",
    }
)

UNAVAILABLE_EXERCISE_FEEDBACK = {
    "WAITING_TARGET": "화면 중앙의 운동 영역에 서주세요.",
    "MULTIPLE_PEOPLE": "운동자가 명확하지 않습니다. 한 명만 중앙 운동 영역에 서주세요.",
    "TARGET_LOST": "운동자를 다시 확인하고 있습니다. 중앙에 선 뒤 운동자 재확인을 눌러주세요.",
    "OCCLUDED": "정확한 측정을 위해 주변 사람과 거리를 확보해주세요.",
    "STABILIZING": "운동자를 확인하고 있습니다. 잠시 자세를 유지해주세요.",
    "LOW_CONFIDENCE": "관절 인식이 불안정합니다. 양팔이 잘 보이도록 조정해주세요.",
    "TRACKING_ERROR": "운동자 추적을 실행하지 못했습니다. 서버 모델 및 패키지를 확인해주세요.",
    NO_PERSON_STATE: "카메라에 머리부터 허리까지 보이도록 앉아주세요.",
    LOW_VISIBILITY_STATE: "양팔과 얼굴이 잘 보이도록 카메라 위치를 조정해주세요.",
}

INVALID_EXERCISE_ANALYSIS_FEEDBACKS = frozenset(
    UNAVAILABLE_EXERCISE_FEEDBACK.values()
)
