# asgi.py
from asgiref.wsgi import WsgiToAsgi
from wsgi import application as wsgi_app

application = WsgiToAsgi(wsgi_app)
