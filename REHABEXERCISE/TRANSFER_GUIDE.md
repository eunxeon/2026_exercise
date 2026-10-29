# 다른 PC에서 개발 이어가기

보안 정리된 `codex/p49-rehab-exercise` 브랜치를 사용합니다. 로컬 Codex 스냅샷은 보존하며 해당 참조는 브랜치 Push에 포함하지 않습니다.

```powershell
git clone --branch codex/p49-rehab-exercise https://github.com/eunxeon/2026_exercise.git
cd 2026_exercise\REHABEXERCISE
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

A컴퓨터의 `.env`를 안전한 경로로 별도 전달하거나 `.env.example`을 복사하여 설정합니다. 기존 `.env`를 예제로 덮어쓰지 마세요. `.env`에는 기존 데모 로그인을 유지하는 `DEMO_GUARDIAN_PASSWORD_HASH`가 추가되어 있습니다. 해시가 없으면 데모 로그인은 거부되지만 새 계정 회원가입/로그인은 가능합니다. 기존 데모 비밀번호는 바꾸지 않았습니다. 해시만으로 실제 비밀번호나 다른 서비스 재사용 여부를 확인할 수 없습니다.

새 데모 비밀번호를 선택한다면 로컬에서 Werkzeug의 `generate_password_hash`로 해시를 생성하여 `.env`에 저장합니다. 인증정보를 터미널 기록, 문서, Git에 넣지 마세요.

SQL Server의 기존 계정/데이터는 변경하지 않았습니다. `sql/guardian_demo_seed.sql`은 자동 실행하지 않습니다. 필요한 경우에만 승인된 DB 세션에서 매개변수화된 호출 `EXEC sys.sp_set_session_context @key=N'DEMO_GUARDIAN_PASSWORD_HASH', @value=?`에 로컬 해시를 바인딩하고 같은 연결에서 시드 SQL을 실행합니다. 이 시드는 기존 데모 계정의 해시를 갱신할 수 있습니다. 환경변수만 설정하고 SQL을 실행하면 전달되지 않습니다. 값이 없는 경우 시드는 DB 변경 전에 중단합니다.

## 별도 준비

- SQL Server ODBC Driver 18, DB 서버/인스턴스 주소와 Windows 또는 SQL 인증 권한
- 실제 DB 데이터: 별도 보안 백업/복원 또는 기존 DB 서버 접근. Git에는 데이터가 포함되지 않습니다. 스키마/시드/정리 스크립트를 기존 DB에 임의 실행하지 마세요.
- `yolo11n.pt`: 다운로드된 모델은 Git에서 제외됩니다. A컴퓨터의 파일을 `REHABEXERCISE/yolo11n.pt`로 별도 복사합니다. 다른 위치는 `PERSON_MODEL` 환경변수로 지정합니다.
- 카메라 권한, 포트 5000 및 네트워크 설정. 원격 카메라 접속은 브라우저 보안 요구사항을 확인합니다.
- 영상 파일은 업로드 대상에 남아 있습니다. 공개 가능한 시연 영상인지 확인해야 합니다.
- 가상환경, 캐시, 로그는 복사하지 않고 재생성합니다.

```powershell
python app.py
```

## 검증

`REHABEXERCISE` 폴더에서:

```powershell
python -m unittest discover -s tests -v
node tests/test_tracking_ui.cjs
```

인증 테스트는 DB 연결을 차단하고 mock 계정만 사용합니다. 실제 MSSQL 로그인, 카메라/MediaPipe 통합 동작은 별도 환경에서 확인해야 합니다.
