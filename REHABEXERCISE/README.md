# 스마트미러 기반 재활운동 피드백 시스템

이 프로젝트는 라즈베리파이 카메라와 서버용 컴퓨터를 이용해 노인의 재활운동 자세를 분석하고, 스마트미러 화면에 운동 피드백을 보여주는 웹 기반 시스템입니다.

현재 단계의 목표는 완성된 자세 인식 기능이 아니라, 실행 가능한 Flask 서버와 세로형 스마트미러 UI, 그리고 MediaPipe 자세 인식 모듈을 붙일 수 있는 기본 구조를 만드는 것입니다.

## 폴더 구조

```text
REHABEXERCISE/
├─ app.py
├─ requirements.txt
├─ README.md
├─ static/
│  ├─ css/
│  │  └─ style.css
│  ├─ js/
│  │  └─ main.js
│  └─ assets/
├─ templates/
│  └─ index.html
├─ pose/
│  ├─ __init__.py
│  ├─ pose_detector.py
│  └─ exercise_feedback.py
└─ camera/
   ├─ __init__.py
   └─ camera_stream.py
```

## 라즈베리파이와 서버용 컴퓨터 역할

라즈베리파이는 카메라로 사용자 영상을 촬영하고, 가능하면 영상만 서버용 컴퓨터로 전송합니다. MediaPipe 같은 무거운 자세 인식 처리는 라즈베리파이에서 하지 않는 방향입니다.

서버용 컴퓨터는 Flask 서버를 실행하고, 라즈베리파이에서 받은 영상 또는 서버 컴퓨터의 웹캠 영상을 처리합니다. 이후 MediaPipe로 관절 좌표를 추출하고, 운동 정확도와 관절 각도, 피드백 문구를 계산합니다.

스마트미러 웹 화면은 세로형 모니터에 띄우기 위한 UI입니다. 운동 화면, 카메라 영역, 정확도, 관절 각도, 피드백 문구, 현재 단계를 표시합니다.

## 설치 방법

Windows PowerShell 기준입니다.

```powershell
cd C:\Users\User\VS-workspace\2026_exercise\REHABEXERCISE
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행 방법

```powershell
python app.py
```

실행 후 브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:5000
```

서버 상태 확인 주소는 아래와 같습니다.

```text
http://127.0.0.1:5000/health
```

정상 실행 중이면 다음 JSON이 반환됩니다.

```json
{"status":"ok"}
```

## 현재 구현된 기능

- Flask 서버 기본 실행
- `/` 경로에서 스마트미러 메인 화면 표시
- `/health` 경로에서 서버 상태 JSON 반환
- 세로형 스마트미러 UI
- 카메라 화면 placeholder
- 운동 정확도, 관절 각도, 피드백 문구, 현재 단계 표시
- JavaScript 기반 예시 운동 진행 흐름
- MediaPipe 자세 인식용 `pose_detector.py` 뼈대
- 자세 평가와 각도 계산용 `exercise_feedback.py` 뼈대
- OpenCV 카메라 입력용 `camera_stream.py` 뼈대

## 앞으로 구현할 기능

- 라즈베리파이 카메라 영상 전송
- 서버에서 영상 스트림 수신
- MediaPipe Pose를 이용한 실제 관절 좌표 추출
- 운동 종류별 기준 자세 데이터 작성
- 반복 횟수, 단계, 정확도 판정 로직 고도화
- 운동 기록 저장 및 조회
- 스마트미러 실제 모니터 환경에서 UI 크기 조정
