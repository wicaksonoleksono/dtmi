
import os
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from app import create_app
load_dotenv()
flask_app = create_app()
flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1)

application = flask_app  # gunicorn uses: wsgi:application

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple("127.0.0.1", 5000, application, use_reloader=True, use_debugger=True)
