import os
from dotenv import load_dotenv
from asgiref.wsgi import WsgiToAsgi
from werkzeug.middleware.proxy_fix import ProxyFix
from app import create_app

load_dotenv()

flask_app = create_app()
flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1)

application = WsgiToAsgi(flask_app)
