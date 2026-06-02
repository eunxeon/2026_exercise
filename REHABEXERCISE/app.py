from flask import Flask, render_template

# Flask 애플리케이션을 생성합니다.
app = Flask(__name__)


@app.route("/")
def index():
    """메인 스마트미러 UI 페이지를 렌더링합니다."""
    return render_template("index.html")


if __name__ == "__main__":
    # 라즈베리파이 또는 같은 네트워크의 다른 기기에서도 접속할 수 있도록 host를 0.0.0.0으로 설정합니다.
    app.run(host="0.0.0.0", port=5000, debug=True)
