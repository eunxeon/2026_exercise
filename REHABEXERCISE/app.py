from flask import Flask, jsonify, render_template


def create_app():
    """Flask 애플리케이션을 생성합니다.

    나중에 카메라 스트리밍, 자세 인식 API, 운동 기록 저장 기능을 붙이기 쉽도록
    앱 생성 로직을 함수로 분리해 둡니다.
    """
    app = Flask(__name__)

    @app.route("/")
    def index():
        """스마트미러 메인 화면을 보여줍니다."""
        return render_template("index.html")

    @app.route("/health")
    def health():
        """서버가 정상 실행 중인지 확인하는 간단한 상태 API입니다."""
        return jsonify({"status": "ok"})

    return app


app = create_app()


if __name__ == "__main__":
    # 같은 네트워크의 라즈베리파이에서 접속할 수 있도록 0.0.0.0으로 실행합니다.
    app.run(host="0.0.0.0", port=5000, debug=True)
