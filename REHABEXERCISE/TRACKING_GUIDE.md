# 스마트미러 운동자 인식·추적 구현 안내

## 현재 영상 경로와 구현 계획

현재 Raspberry Pi 측 스마트미러 브라우저는 getUserMedia 카메라 프레임을 JPEG data URL로 PC Flask의 POST /analyze_frame에 전달합니다. 별도 Raspberry Pi 송신 데몬은 저장소에 없으며 camera/camera_stream.py는 선택적인 PC 카메라 래퍼입니다. 기존 웹은 480×360, 600ms 주기(최대 약 1.67FPS), 분석 중 다음 요청을 보내지 않는 방식입니다. 이 경로를 유지했습니다.

기존 어깨·ROM 분석기는 각각 detect_pose(frame)를 호출하며 서버 전역 상태를 사용합니다. 공통 호출부에 운동자 선정을 추가하고, 검출·추적·자세 분석을 동일 수신 프레임에서 한 번씩 실행합니다. YOLO 검출은 한 번만 수행하고 원본 검출 목록을 보존한 채 ByteTrack에 전달하여 아직 ID가 없는 다른 사람도 중첩 검사에 포함합니다.

## 추가·수정 파일

| 파일 | 구분 | 역할 |
|---|---|---|
| pose/person_tracking.py | 추가 | YOLO person 검출, ByteTrack, 최초 ROI 선정, ID 잠금, 위치·크기 연속성, 중첩, Crop 여백 |
| pose/bytetrack.yaml | 추가 | 고·저 신뢰도 매칭과 새 트랙·버퍼 설정 |
| pose/pose_detector.py | 수정 | 기존 detect_pose(frame) 유지, 운동자 Crop만 MediaPipe 전달, 원본 좌표 복원, visibility·관절 이동·torso 귀속 검사 |
| pose/analysis_states.py | 수정 | 무효 분석 상태와 한국어 안내; 기존 건강 체크의 무효 결과 필터도 이 목록을 사용 |
| pose/exercise_feedback.py | 수정 | 무효 프레임 분석 차단, 연속 성공 hold 초기화, 완료 단계 보존 |
| pose/rom_checker.py | 수정 | 무효 프레임 최대 ROM 갱신 차단, 기존 최대값 보존 |
| app.py | 수정 | 분석·reset·stop 직렬화, 세션 토큰, 오래된 프레임·모드 변경 차단, 전체 처리 지연 반환 |
| static/js/main.js | 수정 | 상태 안내, 무효 결과의 수치·기록 제외, 빈 기록 저장 차단, 재확인, 토큰·종료 처리, 프리뷰와 같은 중앙 Crop |
| templates/index.html | 수정 | 디버그 Canvas와 운동자 재확인 버튼 |
| static/css/style.css | 수정 | 기존 화면 위에 오버레이·재확인 버튼 배치 |
| requirements.txt | 수정 | Ultralytics·lap 추가 |
| tests/test_person_tracking.py | 추가 | 후보·ID·중첩·Crop·관절 이상치·측정값·세션 API 안전성 테스트 |
| tests/test_tracking_ui.cjs | 추가 | 일시 중지 중 화면 수치·ROM 보존, 샘플 제외, 빈 기록 저장 차단 |
| TRACKING_GUIDE.md | 추가 | 실행, 테스트 및 한계 |

DB 스키마, 사용자 선택·페어링·기록 저장 API는 이 작업에서 수정하지 않았습니다. 작업 시작 전에 있던 변경 사항도 유지했습니다.

## 패키지·모델 설치 및 실행 (PC)

Python 3.10–3.12 가상환경에서 프로젝트의 기존 설치 절차와 DB 환경 설정을 적용합니다.

~~~powershell
cd C:\Users\User\VScode-workspace\REHABEXERCISE
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
python app.py
~~~

- 추가 패키지: ultralytics==8.3.203, lap>=0.5.12. Torch·PyYAML 등은 Ultralytics 의존성으로 설치됩니다. 기존 mediapipe==0.10.21을 유지했습니다.
- 기본 모델: 사전 학습된 yolo11n.pt. 별도 학습 없음. 다운로드 명령은 첫 분석 시 모델 다운로드로 인한 지연을 줄입니다.
- 모델은 첫 사용 때 한 번 로드하고 reset 시 다시 다운로드하거나 다시 로드하지 않습니다. GPU 사용 여부는 설치된 Torch·드라이버 및 Ultralytics 실행 환경에 따릅니다.
- 오프라인 환경에서는 모델을 미리 PC에 복사하고 PERSON_MODEL 환경 변수에 절대 경로를 지정합니다.
- PERSON_IMGSZ 기본 480. PC 성능에 따라 320으로 낮춘 뒤 작은 사람·팔 검출 누락을 다시 시험할 수 있습니다.
- Raspberry Pi에는 AI 패키지·모델을 설치하지 않습니다. 기존 카메라 전송 경로를 사용합니다.
- 일반 화면: http://127.0.0.1:5000/ ; 디버그: http://127.0.0.1:5000/?tracking_debug=1 . debug 화면의 녹색은 운동자, 주황색은 다른 사람, 흰색은 ROI입니다. demo=1은 모의 운동이므로 실제 추적 검증에는 사용하지 않습니다.

## 상태와 선정 기준

- ROI: 화면 가로 25–75%, 세로 10–95%. 사람 박스의 ROI 포함 비율 ≥55%, 중앙점이 ROI 안, 화면 면적 비율 4–80%, 최초 confidence ≥0.35를 요구합니다.
- 후보 점수: ROI 포함 50%, 중앙 근접 40%, 적정 크기 10%. 후보 간 점수 차가 0.12 미만이면 MULTIPLE_PEOPLE로 선정을 보류합니다. 최대 박스만 선택하지 않습니다.
- 같은 후보가 수신 프레임 3회 유지되어야 잠급니다. 이후 같은 ID를 안정적으로 확인하고 신뢰도 검사에 통과해야 분석합니다.
- 정상 프레임 TRACKING은 운동 분석기의 기존 STAGE_1/2/3, COMPLETE, MEASURING 등 결과로 이어집니다. analysis_valid=true, tracking 메타데이터를 함께 반환합니다.
- WAITING_TARGET: 중앙 영역 안내. MULTIPLE_PEOPLE: 후보 위치 조정 안내.
- TARGET_LOST: ID 누락, 박스의 급격한 이동·크기 변화, 수신 간격 2초 초과 시 발생. 다른 ID를 자동 선정하지 않으며 원래 ID가 다시 나타나도 사용자 재확인 전에는 측정하지 않습니다.
- OCCLUDED: 운동자 면적 대비 겹침 ≥40% 또는 tracked 박스 IoU ≥0.30. 모든 검출 박스를 추가 검사하므로 아직 ID가 없는 가림도 차단합니다. 수신 프레임 3회 안정화와 관절 안정화 이후 같은 ID로 재개합니다.
- 일부 중첩 >10%는 주요 관절 visibility ≥0.7을 요구합니다. 일반 visibility 기준은 기존 0.5입니다. 다른 tracked 사람의 박스에 torso 관절 3개 이상이 들어가는 skeleton도 차단합니다.
- LOW_CONFIDENCE: 어깨·허리가 운동자 박스를 벗어나거나, 주요 관절의 원본 좌표 이동이 시간·운동자 크기 대비 비정상적이거나, 값이 유한하지 않을 때 발생합니다. 손목·팔꿈치는 torso보다 넓은 이동 허용치를 사용합니다. 거부된 이상치를 다음 기준 좌표로 사용하지 않습니다.
- TRACKING_ERROR: 모델·추적 실행 실패. 전체 화면 MediaPipe로 우회하지 않습니다. 서버 로그에서 원인을 확인할 수 있습니다.
- 무효 프레임은 각도·정확도·최대 ROM·단계 성공 수를 갱신하지 않으며 기록 샘플에도 포함하지 않습니다. 중단 전 단계와 최대 ROM은 유지하되 연속 성공 hold는 끊습니다.
- 운동자 재확인 버튼은 **새 측정**을 시작합니다. 이전 최대 ROM·단계·저장 전 샘플을 초기화하므로 서로 다른 사람이 한 기록에 섞이지 않습니다.

## 기존 API 호환성 및 상태 유지

- detect_pose(frame), /analyze_frame의 기존 image·exercise_key·mode 필드는 유지합니다. 결과에 analysis_valid, tracking, analysis_latency_ms를 추가합니다.
- 새 웹 UI는 /reset_exercise에 use_session=true를 보내 토큰을 받고 모든 분석·종료 요청에 analysis_session을 전송합니다. 이전 실행의 토큰·다른 운동 모드는 HTTP 409로 차단합니다. /stop_exercise는 해당 토큰의 추적을 종료합니다.
- 기존 token 없는 클라이언트는 token 없는 reset 후 사용할 수 있습니다. token을 사용하는 새 웹 세션에 token 없이 프레임을 보내면 차단됩니다. 기존 클라이언트도 시작·종료 시 reset/stop을 사용해야 합니다.
- reset·stop·분석은 공통 RLock으로 직렬화합니다. 현재 전역 운동 분석 구조에 맞춰 **PC 서버 하나·프로세스 하나·운동자 스트림 하나**를 지원합니다. 다중 worker나 여러 스마트미러 동시 분석에는 장치별 별도 상태 저장소가 추가로 필요합니다. 토큰은 인증 수단이 아닙니다.
- 기존 5/8초 공백에 따른 분석기 자동 초기화는 제거했습니다. 일시 중지 때문에 이미 성공한 단계나 ROM 최대값이 사라지지 않으며 명시적 시작/reset으로 초기화합니다.
- MediaPipe는 Crop 좌표 변화와 다른 사람의 이전 skeleton 전파를 막기 위해 static_image_mode=True를 사용합니다. 모델은 재사용하지만 자체 프레임 간 smoothing 대신 별도 연속성 검사로 보호합니다. 이에 따른 속도·각도 노이즈 변화는 실기 검증이 필요합니다.
- x/y/z(normalized), pixel은 원본 프레임 기준으로 복원합니다. MediaPipe world 값은 그대로 유지합니다. 코드상 임의 스케일 변경이 없음을 테스트했지만 Crop 전후 실제 world 추정값·기존 어깨 기준 영상 점수의 동등성을 보장하지는 않습니다.

## 자동 테스트

~~~powershell
python -m unittest discover -s tests -v
node tests/test_tracking_ui.cjs
node --check static/js/main.js
~~~

검증 결과: Python 24개 통과(신규 13개 + 기존 건강 알림 API 11개), UI 보호 검증 통과, JS 문법 검사 통과, Python 변경 파일 구문 검사 통과. 추적 테스트는 모델·카메라 대신 합성 박스/landmark를 사용하며 DB 접근을 비활성화하고 API는 대체 데이터 저장소로 검증했습니다. 실제 YOLO·ByteTrack 추론, MediaPipe 추론, 실제 DB 저장, 브라우저 카메라 및 Raspberry Pi 연결을 검증한 결과는 아닙니다.

## 실제 단일·다중 인원 테스트

| 시나리오 | 확인할 결과 |
|---|---|
| 한 사람 중앙·좌우 이동·빠른 팔 올리기 | 선정 완료, 동일 ID 유지, 팔/손목 Crop 포함, 정상 운동 성공/ROM 갱신 |
| 큰 사람이 화면 가장자리에서 등장 | 최초 운동자 유지; 최초 선정 때에도 크기만으로 결정하지 않음 |
| 비슷한 두 후보가 동시에 중앙 진입 | 위치 조정 안내, 단계·ROM·기록 샘플 변화 없음 |
| 다른 사람이 멀리 통과 | 기존 ID로 정상 분석 |
| 일부 중첩·visibility 저하 | 신뢰도 조건 충족 시만 분석; 누락 관절로 ROM 최대값 상승하지 않음 |
| 심한 중첩·두 사람 교차·전후 자리 교환 | 안내 표시, 수치/성공 횟수/ROM 갱신 중지; 분리 후 원래 운동자임을 영상과 ID로 확인 |
| 운동자가 완전히 사라짐, 타인이 같은 위치 차지 | TARGET_LOST 지속, 타인 데이터가 정상 결과로 저장되지 않음 |
| 재확인 버튼 | 새 측정으로 ID·단계·최대 ROM·샘플 초기화 |
| 중단 10초 뒤 같은 운동자 재개 | 중첩 일시 중지 동안 최대 ROM·완료 단계가 유지; 추적 손실이면 재확인 필요 |
| 유효 결과 없이 종료·저장 | 기록 저장 차단 |
| 종료 직전 요청 지연·빠른 재시작·운동 종류 변경 | 과거 토큰은 409, 새 세션 측정값에 영향 없음 |
| 모델 미설치·파일 누락·실행 예외 | TRACKING_ERROR, 전체 화면 분석이나 잘못된 정상 기록 없음 |

동일 조명·거리에서 기존 단일 인원 결과와 새 Crop 결과의 관절 각도·ROM 최대값·단계 성공률을 비교합니다. 실제 다중 인원 영상을 동의하에 기록하고 프레임마다 실제 운동자·ID·state·analysis_valid·겹침·angle·max_angle·analysis_latency_ms를 비교하여 ID switch와 잘못된 정상 판정을 집계해야 합니다. PC에서 p50/p95 지연을 측정하고 600ms 주기, 4초 웹 timeout과 비교합니다. 디버그 박스는 분석 시점의 결과이므로 실시간 영상보다 늦게 보일 수 있습니다.

## 현재 구현과 추가 검증 사항

ROI 선정, ByteTrack의 낮은 confidence 매칭, ID 잠금, Crop·좌표 변환, 중첩·관절 신뢰도 차단, 상태 안내, 세션·종료 초기화, 기록 샘플 보호가 구현되었습니다.

ByteTrack은 appearance ReID/신원 인증이 없어 사람들이 완전히 겹치거나 자리를 바꾸면 같은 숫자 ID가 타인에게 이어질 수 있습니다. 박스·관절 검사는 이 위험을 줄이는 휴리스틱이며 제거를 보장하지 않습니다. 현재 낮은 수신 FPS에서는 빠른 교차를 놓칠 수 있으며 검출된 박스만으로 앞뒤 가림을 확정할 수 없어 보수적으로 측정을 멈춥니다. 실제 영상에서 ID 전환, 같은 ID의 타인 관절 선택, 빠른 운동의 과도한 거부, Crop 팔 잘림, world 값 변화, CPU/GPU 지연을 검증한 뒤 임계값을 조정해야 합니다. 정확도가 개선되었다고 단정하지 않습니다.
