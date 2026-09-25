import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="onewolf-public-tests-"))
os.environ.update(ENV="test", DB_PATH=str(_tmp / "data.db"), UPLOAD_DIR=str(_tmp / "uploads"))

from flask import Flask  # noqa: E402
from public.app import app, safe_next  # noqa: E402
from core import security, uploads  # noqa: E402


def test_public_pages_load():
    client = app.test_client()
    for path in ("/", "/news", "/apply", "/battles", "/login"):
        assert client.get(path).status_code == 200


def test_application_requires_csrf():
    assert app.test_client().post("/apply", data={}).status_code == 400


def test_machine_endpoint_requires_api_key():
    assert app.test_client().post("/api/battles/log").status_code == 401


def test_redirects_stay_on_site():
    assert safe_next("/account", "/") == "/account"
    for path in ("//other.example", "/\\other.example", "/a\r\nLocation: x"):
        assert safe_next(path, "/") == "/"


def test_client_ip_uses_only_trusted_proxy():
    probe = Flask(__name__)
    with probe.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "203.0.113.5"},
        headers={"CF-Connecting-IP": "192.0.2.20", "X-Forwarded-For": "192.0.2.30"},
    ):
        assert security.client_ip() == "203.0.113.5"


def test_webp_requires_webp_signature():
    assert not uploads.looks_like_declared(b"<html>", "webp")
    assert uploads.looks_like_declared(b"RIFF" + b"\0" * 4 + b"WEBP" + b"VP8 ", "webp")
