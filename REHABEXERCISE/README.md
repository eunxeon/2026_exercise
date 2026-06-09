# Rehab Mirror

Flask 기반 재활 스마트미러 예제입니다. 라즈베리파이 Chromium 브라우저에서 카메라를 켜고, 캡처한 프레임을 서버 PC의 Flask API로 보내 분석 결과를 화면에 표시합니다.

## 서버 PC 실행

1. 프로젝트 폴더로 이동합니다.

```powershell
cd C:\Users\User\VScode-workspace\REHABEXERCISE
```

2. 가상환경을 만들고 활성화합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

3. 패키지를 설치합니다.

```powershell
pip install flask opencv-python numpy
```

4. 서버를 실행합니다.

```powershell
python app.py
```

서버는 `host="0.0.0.0"`, `port=5000`으로 실행되므로 같은 네트워크의 라즈베리파이에서 접속할 수 있습니다.

## 서버 PC IP 확인

Windows PowerShell에서 다음 명령을 실행합니다.

```powershell
ipconfig
```

무선랜 또는 유선랜 항목의 `IPv4 주소`를 확인합니다. 예를 들어 `192.168.0.25`라면 라즈베리파이에서는 `http://192.168.0.25:5000`으로 접속합니다.

## Windows 방화벽

라즈베리파이에서 접속이 되지 않으면 Windows Defender 방화벽에서 Python 또는 TCP 포트 `5000` 인바운드 연결을 허용합니다. 같은 Wi-Fi에 연결되어 있는지도 함께 확인하세요.

## 라즈베리파이 Chromium 접속

1. 서버 PC와 라즈베리파이를 같은 네트워크에 연결합니다.
2. 라즈베리파이에서 Chromium을 실행합니다.
3. `http://서버PC_IP:5000`으로 접속합니다.
4. `선택한 운동 시작` 버튼을 누릅니다.
5. 카메라 권한 요청이 나오면 허용합니다.
6. 카메라 화면이 보이고 정확도, 각도, 피드백 문구가 갱신되는지 확인합니다.

## 동작 확인 순서

1. 서버 PC에서 `python app.py` 실행
2. 서버 PC 브라우저에서 `http://127.0.0.1:5000` 접속
3. 서버 PC 브라우저에서 `http://127.0.0.1:5000/health` 확인
4. 라즈베리파이 Chromium에서 `http://서버PC_IP:5000` 접속
5. `선택한 운동 시작` 클릭
6. 카메라 권한 허용
7. 카메라 화면 표시 확인
8. 정확도, 현재/목표 각도, 피드백 문구가 서버 응답으로 갱신되는지 확인
9. 서버 터미널에 `[/analyze_frame]` 요청 로그가 찍히는지 확인

## 오류 체크리스트

- 라즈베리파이에서 화면이 열리지 않으면 서버 PC IP, 같은 네트워크 연결, 방화벽을 확인합니다.
- 화면은 열리지만 카메라가 켜지지 않으면 Chromium 카메라 권한과 카메라 장치 연결을 확인합니다.
- 카메라는 켜지는데 피드백이 바뀌지 않으면 서버 터미널에 `/analyze_frame` 로그가 찍히는지 확인합니다.
- getUserMedia가 실패하면 `localhost`가 아닌 원격 주소 접속에서 브라우저 보안 정책이 영향을 줄 수 있습니다. Chromium 설정과 네트워크 환경을 확인합니다.

## 이번 작업에서 바뀐 파일

- `app.py`: `/health`, `/analyze_frame` API와 base64 이미지 디코딩을 추가했습니다.
- `templates/index.html`: 훈련 화면에 실제 카메라 `video`와 숨김 `canvas`를 추가했습니다.
- `static/js/main.js`: 브라우저 카메라 권한 요청, 프레임 캡처, 서버 전송, 응답 반영 로직을 추가했습니다.
- `static/css/style.css`: 카메라 화면과 placeholder/canvas 표시 스타일을 정리했습니다.
- `pose/pose_detector.py`: OpenCV 프레임을 받는 placeholder 자세 감지 구조를 추가했습니다.
- `pose/exercise_feedback.py`: 서버 연결 확인용 분석 결과 생성 함수를 추가했습니다.
- `camera/camera_stream.py`: 향후 서버 측 카메라 입력을 위한 OpenCV 래퍼를 추가했습니다.
