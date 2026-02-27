import os
from flask import Flask, jsonify
from src.downloader import init_db
from src.scheduler import init_scheduler
from src.routes import api, streams, admin, archive, downloads


def create_app():
    application = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
        static_url_path="/static",
    )

    application.register_blueprint(api.bp)
    application.register_blueprint(streams.bp)
    application.register_blueprint(admin.bp)
    application.register_blueprint(archive.bp)
    application.register_blueprint(downloads.bp)

    @application.route("/health")
    def health():
        return jsonify({"status": "ok"})

    return application


app = create_app()
init_db()
init_scheduler()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
