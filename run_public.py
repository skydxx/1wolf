"""Запуск публичного сайта 1wolf.ru."""
import logging

from core import config, db, wsgi
from public.app import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

wsgi.prepare(app)

if __name__ == "__main__":
    wsgi.quiet_dev_server()
    db.init()
    logging.info("сайт: http://%s:%s", config.PUBLIC_HOST, config.PUBLIC_PORT)
    app.run(host=config.PUBLIC_HOST, port=config.PUBLIC_PORT, debug=config.DEBUG)
