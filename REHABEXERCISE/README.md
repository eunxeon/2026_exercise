# 스마트미러 기반 노인 질환 예방 운동 피드백 시스템

Flask 서버와 브라우저 기반 스마트미러 UI로 구성된 발표/시연용 1차 프로토타입입니다.

라즈베리파이 Chromium 브라우저 또는 일반 브라우저가 카메라 프레임을 캡처해 서버 PC의 Flask API로 전송하고, 서버는 OpenCV와 MediaPipe Pose로 자세를 분석해 실시간 피드백 JSON을 반환합니다.

## 현재 지원 기능

- 페어링 코드 발급 및 발표용 등록 완료 처리
- 사용자 선택
- 홈 화면, 질환 예방 운동 목록, 건강 체크, 운동 기록 화면 이동
- `shoulder` 질환 예방 운동의 3단계 자세 분석
- `rom_shoulder` 건강 체크의 어깨 관절 가동 범위 점검
- 브라우저 카메라 프레임을 `480 x 360` JPEG data URL로 변환해 `/analyze_frame`으로 전송
- 운동 종료 후 평균 정확도와 피드백 요약 저장
- 사용자별 운동 기록 조회
- MSSQL 연결 실패 시 `mock_data.py` fallback

발표용 `등록 완료 테스트` 버튼은 실제 모바일 앱 연동이 아니라 시연을 위한 서버 상태 전환 기능입니다.

## 현재 분석 범위

### 질환 예방 운동

현재 실제 분석을 지원하는 운동은 `shoulder`입니다.

- 화면 표시명: `앉아서 양팔 들고 몸통 돌리기`
- 가이드 영상: `static/videos/shoulder.mp4`
- 분석 기준: 영상에서 샘플링한 3단계 기준 자세
- 단계 흐름: `pose1_left -> pose2_center -> pose3_right`
- 주요 측정값: 양팔 들어올림 각도, 몸통 회전, 얼굴 방향 보조값
- 완료 조건: 각 단계 자세가 기준 범위에 들어오고 일정 프레임 동안 유지되면 다음 단계로 진행

### 건강 체크

현재 실제 점검을 지원하는 건강 체크 기능은 `rom_shoulder`입니다.

- 화면 표시명: `관절 가동 범위 점검`
- 설명: 카메라로 어깨 관절 움직임을 인식하여 가동 범위를 확인합니다.
- 측정 안내: 화면을 보며 팔을 천천히 들어올립니다.
- 기준값: 최대 어깨 가동 범위 `120도` 이상이면 `정상 범위`, `90도` 이상 120도 미만이면 `주의 필요`, 그보다 낮으면 측정 계속 안내
- 안내 문구: 본 결과는 운동 보조용 참고 정보이며 의학적 진단이 아닙니다.

### 비활성화된 기능

`knee`, `flexibility`, `balance`는 목록에는 표시되지만 서버 분석 로직이 아직 없습니다. 프론트에서는 `준비 중` 또는 `추후 지원 예정`으로 표시하고 시작 버튼을 비활성화합니다.

## 실행 방법

```powershell
cd C:\Users\User\VScode-workspace\REHABEXERCISE
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

필요한 Python 의존성은 [requirements.txt](requirements.txt)에 정리되어 있습니다.

- `flask`
- `opencv-python`
- `mediapipe==0.10.21`
- `numpy`
- `pyodbc`
- `python-dotenv`

서버는 기본적으로 다음 주소에서 실행됩니다.

```text
http://0.0.0.0:5000
```

로컬 PC 브라우저 테스트는 다음 주소를 사용합니다.

```text
http://127.0.0.1:5000
```

같은 네트워크의 스마트미러 또는 라즈베리파이 Chromium에서는 서버 PC의 IPv4 주소로 접속합니다.

```text
http://서버PC_IP:5000
```

브라우저 카메라는 `localhost` 또는 HTTPS 환경에서 권한 요청이 정상 동작합니다. 라즈베리파이에서 접속할 때 카메라 권한이 막히면 Chromium의 site permission, 주소 보안 정책, 카메라 장치 연결 상태를 확인하세요.

데모 자동 흐름은 쿼리 파라미터로 켤 수 있습니다.

```text
http://127.0.0.1:5000?demo=1
```

## MSSQL 설정

DB 없이 실행하면 앱은 자동으로 `mock_data.py` fallback 데이터를 사용합니다. MSSQL을 사용하려면 SQL Server와 ODBC Driver 18 for SQL Server를 준비한 뒤 다음 순서로 설정합니다.

1. `.env.example`을 `.env`로 복사합니다.
2. `.env`에서 `DB_ENABLED=true`로 바꿉니다.
3. `DB_SERVER`, `DB_NAME`, 인증 정보를 환경에 맞게 수정합니다.
4. `sql/schema.sql`로 없는 테이블과 제약조건을 생성합니다.
5. `sql/seed.sql`로 초기 발표/시연 데이터를 넣습니다.

`.env.example`의 주요 항목은 다음과 같습니다.

```text
DB_ENABLED=false
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_SERVER=localhost\SQLEXPRESS
DB_PORT=
DB_NAME=REHABEXERCISE
DB_USERNAME=
DB_PASSWORD=
DB_TRUSTED_CONNECTION=yes
DB_TRUST_SERVER_CERTIFICATE=yes
DB_CONNECTION_TIMEOUT=3
DB_MIRROR_ID=mirror-demo-001
PAIRING_CODE_TTL_SECONDS=600
DB_FALLBACK_TO_MOCK=1
```

Windows 인증을 쓸 경우 `DB_TRUSTED_CONNECTION=yes`로 설정하고 `DB_USERNAME`, `DB_PASSWORD`는 비워둘 수 있습니다.

`DB_FALLBACK_TO_MOCK=1`이면 MSSQL 설정이 없거나 연결에 실패해도 앱은 종료되지 않고 개발용 데이터로 계속 동작합니다.

## 주요 라우트

### 화면/상태

- `GET /`: 스마트미러 UI를 렌더링합니다.
- `GET /health`: 서버 연결 확인용 엔드포인트입니다.

### 데이터 API

- `GET /api/devices/current`: 현재 데모 스마트미러 기기 정보를 반환합니다.
- `POST /api/devices/<device_id>/pairing-code`: 서버에서 페어링 코드를 발급합니다.
- `GET /api/devices/<device_id>/pairing-status`: 현재 페어링 상태를 반환합니다.
- `POST /api/devices/<device_id>/pairing-status/demo-complete`: 발표용으로 페어링을 완료 처리합니다.
- `GET /api/users`: 사용자 목록을 반환합니다.
- `GET /api/devices/<device_id>/users`: 기기에 연결된 사용자 목록 형식으로 데모 사용자 목록을 반환합니다.
- `GET /api/exercises`: 운동 기능과 건강 체크 목록, 지원 상태를 반환합니다.
- `POST /api/exercise-records`: 운동 종료 시 평균 정확도와 피드백 요약을 저장합니다.
- `GET /api/users/<user_id>/exercise-records`: 사용자별 운동 기록 목록을 반환합니다.

### 분석 API

- `POST /reset_exercise`: 선택한 운동 또는 건강 체크의 분석 상태를 초기화합니다.
- `POST /analyze_frame`: 브라우저에서 전송한 카메라 프레임을 분석합니다.

`/analyze_frame` 요청 예시:

```json
{
  "image": "data:image/jpeg;base64,...",
  "exercise_key": "shoulder"
}
```

사람이 감지되지 않으면 `NO_PERSON`, 필요한 관절의 신뢰도가 낮으면 `LOW_VISIBILITY` 상태를 반환합니다. 잘못된 이미지 요청은 서버 오류 500이 아니라 400 오류 JSON으로 반환됩니다.

## 운동 기록 저장 흐름

프론트는 지원되는 운동 기능 또는 건강 체크를 시작하면 세션을 만들고, `/analyze_frame` 응답의 정확도, 피드백, 상태, 단계를 세션 안에 누적합니다. `rom_shoulder`는 현재 각도, 최대 각도, 판정 결과도 함께 누적합니다.

사용자가 `운동 종료 및 저장` 또는 `결과 저장` 버튼을 누르면 평균 정확도와 피드백 요약을 `/api/exercise-records`로 전송합니다. 저장된 기록은 `운동 기록` 화면에서 `/api/users/<user_id>/exercise-records`를 통해 조회합니다.

DB 연결이 실패하면 같은 API가 `mock_data.py`의 메모리 저장소를 사용하므로 시연 흐름은 중단되지 않습니다. 단, mock 저장소의 기록은 서버 프로세스를 재시작하면 사라집니다.

## 폴더 구조

```text
REHABEXERCISE/
  app.py                    Flask 앱과 API 라우트
  db.py                     MSSQL 연결 설정과 pyodbc 실행 래퍼
  data_store.py             MSSQL 우선, mock fallback 데이터 저장소
  mock_data.py              개발용 기기/사용자/운동 fallback 데이터
  .env.example              MSSQL 환경변수 예시
  requirements.txt          Python 의존성
  camera/
    camera_stream.py        선택적 서버 측 카메라 래퍼
  pose/
    pose_detector.py        MediaPipe Pose landmark 추출
    exercise_feedback.py    shoulder 3단계 순차 자세 분석
    rom_checker.py          rom_shoulder 어깨 관절 가동 범위 점검
  static/
    css/style.css           스마트미러 UI 스타일
    js/main.js              화면 흐름, API 호출, 카메라 프레임 전송
    videos/shoulder.mp4     현재 지원 운동 가이드 영상
  templates/
    index.html              스마트미러 단일 페이지 UI
  sql/
    schema.sql              MSSQL 테이블/제약조건 생성 스크립트
    seed.sql                반복 실행 가능한 초기 발표/시연 데이터
```

## 현재 한계

- 실제 모바일 앱 페어링과 사용자 인증은 아직 연결하지 않았습니다.
- 실제 서버 분석은 `shoulder` 운동 기능과 `rom_shoulder` 건강 체크만 지원합니다.
- `knee`, `flexibility`, `balance`는 표시만 하며 분석 시작은 막아두었습니다.
- 자동화 테스트 파일은 아직 없습니다.
- MediaPipe 기준값은 `shoulder.mp4`에서 샘플링한 상수이므로 실제 사용자별 보정은 아직 없습니다.
- 운동 기록은 평균 정확도와 피드백 요약 중심의 1차 저장만 지원합니다.
