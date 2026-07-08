# Rehab Exercise

Flask 서버와 브라우저 기반 스마트미러 UI로 구성된 노인 재활운동 피드백 1차 프로토타입입니다.

라즈베리파이 Chromium 브라우저 또는 일반 브라우저가 카메라 프레임을 캡처해 서버 PC의 Flask API로 전송하고, 서버는 OpenCV와 MediaPipe Pose로 자세를 분석해 실시간 피드백 JSON을 반환합니다.

## 현재 단계

현재 단계는 **발표/시연용 1차 프로토타입 정리 단계**입니다.

- 스마트미러 UI 흐름이 구현되어 있습니다.
- 브라우저 카메라 프레임을 서버로 전송합니다.
- `/analyze_frame`에서 실제 MediaPipe Pose 분석을 수행합니다.
- `shoulder.mp4` 기준의 어깨·몸통 3단계 순차 자세 분석을 지원합니다.
- 사용자, 운동 목록, 페어링 코드는 서버 API에서 제공합니다.
- MSSQL 연결 정보가 설정되어 있으면 DB를 우선 사용하고, 연결할 수 없으면 `mock_data.py` 개발용 데이터로 fallback합니다.
- 실제 모바일 앱 기기 등록, 사용자 인증은 아직 연결하지 않았습니다.

## 구현된 기능

### 화면 흐름

`templates/index.html`과 `static/js/main.js`에 다음 화면 흐름이 구현되어 있습니다.

1. 페어링 화면
2. 사용자 선택 화면
3. 홈 화면
4. 운동 선택 화면
5. 훈련 화면

페어링 코드는 브라우저에서 직접 만들지 않고 Flask API에서 발급합니다. 발표용으로 `등록 완료 테스트` 버튼을 누르면 서버의 페어링 상태가 완료로 바뀌고 사용자 선택 화면으로 이동합니다.

### 운동 분석

현재 서버 분석이 실제로 지원하는 운동은 `shoulder` 하나입니다.

- 운동명: `앉아서 양팔 들고 몸통 돌리기`
- 가이드 영상: `static/videos/shoulder.mp4`
- 분석 기준: 영상에서 샘플링한 3단계 기준 자세
- 단계 흐름: `pose1_left -> pose2_center -> pose3_right`
- 주요 측정값: 양팔 들어올림 각도, 몸통 회전, 얼굴 방향 보조값
- 완료 조건: 각 단계의 자세가 기준 범위에 들어오고 일정 프레임 동안 유지되면 다음 단계로 진행

`knee`, `flexibility`, `balance` 운동은 목록에는 표시되지만 아직 서버 분석 로직이 없습니다. 프론트에서는 `준비 중` 또는 `추후 지원 예정`으로 표시하며 시작 버튼을 비활성화합니다.

### 카메라 프레임 전송

브라우저는 훈련 화면에서 카메라 영상을 `<canvas>`에 그린 뒤 JPEG data URL로 변환해 `/analyze_frame`에 전송합니다.

- 캡처 크기: `480 x 360`
- 전송 형식: JPEG data URL
- 전송 주기: `600ms`
- 분석 타임아웃: `4000ms`

## 실행 방법

```powershell
cd C:\Users\User\VScode-workspace\REHABEXERCISE
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

서버는 기본적으로 다음 주소에서 실행됩니다.

```text
http://0.0.0.0:5000
```

같은 네트워크의 라즈베리파이 Chromium에서는 서버 PC의 IPv4 주소를 사용해 접속합니다.

```text
http://서버PC_IP:5000
```

로컬 PC 브라우저 테스트는 다음 주소를 사용할 수 있습니다.

```text
http://127.0.0.1:5000
```

데모 자동 흐름은 쿼리 파라미터로 켤 수 있습니다.

```text
http://127.0.0.1:5000?demo=1
```

## MSSQL 설정

DB 없이 실행하면 앱은 자동으로 `mock_data.py` fallback 데이터를 사용합니다. MSSQL을 사용하려면 SQL Server와 ODBC Driver 18 for SQL Server를 준비한 뒤 다음 순서로 설정합니다.

1. `.env.example`을 `.env`로 복사합니다.
2. `.env`에서 `DB_ENABLED=true`로 바꿉니다.
3. `DB_SERVER`, `DB_NAME`, 인증 정보를 환경에 맞게 수정합니다.
4. `sql/schema.sql`로 테이블을 생성합니다.
5. `sql/seed.sql`로 초기 발표/시연 데이터를 넣습니다.

예시:

```powershell
copy .env.example .env
sqlcmd -S localhost -d RehabMirror -i sql\schema.sql
sqlcmd -S localhost -d RehabMirror -i sql\seed.sql
python app.py
```

Windows 인증을 쓸 경우 `.env`에서 `DB_TRUSTED_CONNECTION=yes`로 설정하고 `DB_USERNAME`, `DB_PASSWORD`는 비워둘 수 있습니다.

DB 연결이 실패해도 `DB_FALLBACK_TO_MOCK=1`이면 앱은 종료되지 않고 개발용 더미 데이터로 계속 동작합니다.

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
- `GET /api/devices/<device_id>/users`: 데모 사용자 목록을 반환합니다.
- `GET /api/exercises`: 운동 목록과 지원 상태를 반환합니다.

이 API들은 `data_store.py`를 통해 MSSQL을 먼저 조회하고, DB 설정이 없거나 연결 실패 시 `mock_data.py`를 사용합니다.

### 분석 API

- `POST /reset_exercise`: 운동 분석 상태를 초기화합니다.
- `POST /analyze_frame`: 브라우저에서 전송한 카메라 프레임을 분석합니다.

`/analyze_frame` 요청 예시:

```json
{
  "image": "data:image/jpeg;base64,...",
  "exercise_key": "shoulder"
}
```

응답 예시:

```json
{
  "success": true,
  "accuracy": 87,
  "angle": 156,
  "target_angle": 158,
  "torso_rotation": 10,
  "target_torso_rotation": 11,
  "feedback": "좋습니다. 현재 자세를 잠시 유지해주세요.",
  "state": "STAGE_1",
  "stage": 1,
  "completed_stages": 0,
  "total_stages": 3,
  "instruction": "1단계: 양팔을 올리고 영상처럼 왼쪽으로 돌아주세요."
}
```

사람이 감지되지 않으면 `NO_PERSON`, 필요한 관절의 신뢰도가 낮으면 `LOW_VISIBILITY` 상태를 반환합니다.

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
  static/
    css/style.css           스마트미러 UI 스타일
    js/main.js              화면 흐름, API 호출, 카메라 프레임 전송
    videos/shoulder.mp4     현재 지원 운동 가이드 영상
  templates/
    index.html              스마트미러 단일 페이지 UI
  sql/
    schema.sql              MSSQL 테이블 생성 스크립트
    seed.sql                초기 발표/시연 데이터
```

## 분석 흐름

1. 브라우저가 카메라 권한을 요청합니다.
2. 카메라 프레임을 `480 x 360` 캔버스에 그립니다.
3. 캔버스를 JPEG data URL로 변환합니다.
4. `/analyze_frame`에 `exercise_key`와 이미지를 전송합니다.
5. Flask 서버가 data URL을 OpenCV BGR 프레임으로 디코딩합니다.
6. `pose/pose_detector.py`가 MediaPipe Pose landmark를 추출합니다.
7. `pose/exercise_feedback.py`가 shoulder 3단계 기준 자세와 비교합니다.
8. 서버가 정확도, 현재 단계, 완료 단계 수, 피드백 문구를 JSON으로 반환합니다.
9. 프론트가 훈련 화면의 정확도, 각도, 단계, 피드백을 갱신합니다.

## 현재 한계

- MSSQL 연동 구조는 추가되었지만, DB가 없거나 연결 실패 시 `mock_data.py`로 fallback합니다.
- 페어링은 실제 모바일 앱 연동이 아니라 발표용 상태 전환입니다.
- 서버 분석은 `shoulder` 운동만 지원합니다.
- `knee`, `flexibility`, `balance`는 UI에 표시만 하며 분석 시작은 막아두었습니다.
- 테스트 자동화는 아직 없습니다.
- MediaPipe 기준값은 `shoulder.mp4`에서 샘플링한 상수이므로 실제 사용자별 보정은 아직 없습니다.
- `ExerciseRecords` 테이블은 준비했지만 운동 기록 저장 API는 다음 단계에서 구현합니다.

## 다음 개발 계획

1. 실제 기기 등록 API와 모바일 앱 페어링 흐름을 연결합니다.
2. 사용자별 운동 처방, 운동 이력, 완료 기록 저장 기능을 추가합니다.
3. `ExerciseRecords` 저장 API를 `/analyze_frame` 완료 흐름과 연결합니다.
4. `knee`, `flexibility`, `balance` 운동별 분석 로직과 가이드 영상을 추가합니다.
5. 운동 분석 기준값을 사용자 체형과 카메라 위치에 맞게 보정하는 절차를 설계합니다.
6. Flask 테스트 클라이언트 기반 API 테스트와 자세 분석 단위 테스트를 추가합니다.
