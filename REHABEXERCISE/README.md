# Rehab Exercise

라즈베리파이 Chromium 브라우저에서 카메라 프레임을 캡처해 서버 PC의 Flask 서버로 전송하고, 서버의 `/analyze_frame` API가 프레임을 분석해 JSON 결과를 반환하는 재활 운동 테스트 프로젝트입니다.

## 현재 단계

현재 단계는 **실제 MediaPipe 관절 분석 1차 적용**입니다.

- `/analyze_frame` API는 기존 통신 구조를 유지합니다.
- 브라우저의 카메라 전송 구조와 `static/js/main.js`는 변경하지 않았습니다.
- DB는 아직 연결하지 않았습니다.
- 운동 기준값은 코드 내부 상수로 임시 정의해 테스트합니다.
- 우선 팔 들어올리기 운동 하나만 분석합니다.

## 분석 방식

서버는 OpenCV BGR 프레임을 RGB로 변환한 뒤 MediaPipe Pose에 입력합니다. 감지된 landmark 중 다음 관절 좌표를 사용합니다.

- `LEFT_SHOULDER`, `LEFT_ELBOW`, `LEFT_WRIST`
- `RIGHT_SHOULDER`, `RIGHT_ELBOW`, `RIGHT_WRIST`
- `LEFT_HIP`, `RIGHT_HIP`

팔 들어올리기 운동은 어깨를 기준으로 엉덩이-어깨-팔꿈치 각도를 계산합니다. 목표 각도는 `80도`, 허용 범위는 `±10도`입니다.

## 서버 PC 실행

```powershell
cd C:\Users\User\VScode-workspace\REHABEXERCISE
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

서버는 `host="0.0.0.0"`, `port=5000`으로 실행되므로 같은 네트워크의 라즈베리파이에서 접속할 수 있습니다.

## 라즈베리파이 Chromium 접속

1. 서버 PC와 라즈베리파이를 같은 네트워크에 연결합니다.
2. 서버 PC에서 `ipconfig`로 IPv4 주소를 확인합니다.
3. 라즈베리파이 Chromium에서 `http://서버PC_IP:5000`으로 접속합니다.
4. 카메라 권한을 허용합니다.
5. 카메라 앞에 서서 팔 들어올리기 자세를 테스트합니다.

## 테스트 방법

1. 서버 PC에서 `python app.py`를 실행합니다.
2. 브라우저에서 `http://127.0.0.1:5000/health`가 `{"status":"ok"}`를 반환하는지 확인합니다.
3. 라즈베리파이 Chromium에서 서버 페이지에 접속합니다.
4. 카메라 프레임이 전송되면 서버 터미널에서 다음 형태의 로그를 확인합니다.

```text
[/analyze_frame] decoded frame: 480x360
[/analyze_frame] angle=82 accuracy=96 state=TRACKING
```

5. 사람이 보이지 않으면 `state`가 `NO_PERSON`으로 반환됩니다.
6. 팔, 어깨, 엉덩이 관절의 신뢰도가 낮으면 `state`가 `LOW_VISIBILITY`로 반환됩니다.

## 주요 응답 예시

```json
{
  "success": true,
  "accuracy": 92,
  "angle": 82,
  "target_angle": 80,
  "feedback": "좋아요! 현재 자세가 목표 각도에 가깝습니다.",
  "state": "TRACKING"
}
```

## 수정한 파일

- `app.py`: `/analyze_frame`에서 실제 어깨 운동 분석을 호출하고 angle, accuracy, state 로그를 출력합니다.
- `pose/pose_detector.py`: MediaPipe Pose로 사람 landmark를 추출하고 `NO_PERSON`, `LOW_VISIBILITY`, `TRACKING` 상태를 반환합니다.
- `pose/exercise_feedback.py`: 팔 들어올리기 운동의 어깨 각도, 정확도, 피드백을 계산합니다.
- `requirements.txt`: Flask, OpenCV, NumPy, MediaPipe 의존성을 포함합니다.
