"""Общая обвязка запуска: за прокси и без болтливых заголовков."""
from werkzeug.middleware.proxy_fix import ProxyFix

from core import config


def prepare(app):
    """Ставится на оба приложения: доверяем одному прокси впереди (nginx)."""
    if config.ENV == "prod":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    return app


def quiet_dev_server():
    """Дев-сервер по умолчанию печатает версию Werkzeug и Python в Server:."""
    try:
        from werkzeug.serving import WSGIRequestHandler
        WSGIRequestHandler.server_version = "1wolf"
        WSGIRequestHandler.sys_version = ""
    except Exception:
        pass
