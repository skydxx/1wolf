"""1wolf.ru — публичный сайт: новости, описание полка, заявки, аккаунты."""
import hmac
import logging
import re
import secrets
from datetime import timedelta

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)

from core import config, db, discord_bot, discord_oauth, notify, security, uploads
from core.repo import applications, audit, battles, members, news, users

log = logging.getLogger("public")

db.init()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = config.PUBLIC_SECRET_KEY
app.config.update(
    MAX_CONTENT_LENGTH=config.MAX_CONTENT_MB * 1024 * 1024,
    SESSION_COOKIE_NAME=config.PUBLIC_COOKIE,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.ENV == "prod",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    JSON_SORT_KEYS=False,
)

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
)


@app.after_request
def headers(resp):
    return security.apply_security_headers(resp, csp=CSP)


PROFILE_SETUP_EXEMPT = ("/complete-profile", "/logout", "/static", "/media")


@app.before_request
def before():
    security.csrf_protect(exempt_paths=("/api/battles/log",))
    g.user = None
    uid = session.get("user_id")
    if uid:
        row = users.get(uid)
        if row and row["active"]:
            g.user = row
        else:
            session.pop("user_id", None)
    if g.user and not g.user["profile_completed"]:
        if not any(request.path.startswith(p) for p in PROFILE_SETUP_EXEMPT):
            return redirect(url_for("complete_profile"))


@app.context_processor
def globals_():
    return {"cfg": config, "user": g.get("user"), "csrf_token": security.csrf_token}


@app.template_filter("dt")
def fmt_dt(value, fmt="%d.%m.%Y %H:%M"):
    if not value:
        return "—"
    from datetime import datetime
    try:
        return datetime.fromisoformat(value).astimezone().strftime(fmt)
    except ValueError:
        return value


@app.template_filter("rich")
def fmt_rich(text: str) -> str:
    """Мини-разметка новостей: абзацы, **жирный**, *курсив*, ссылки, списки."""
    from markupsafe import Markup, escape

    out, lines = [], (text or "").replace("\r\n", "\n").split("\n")
    bullets: list[str] = []

    def flush():
        if bullets:
            out.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    def inline(raw: str) -> str:
        safe = str(escape(raw))
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
        safe = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", safe)
        safe = re.sub(
            r"(https?://[^\s<]+)",
            r'<a href="\1" target="_blank" rel="noopener nofollow">\1</a>',
            safe,
        )
        return safe

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith(("- ", "• ")):
            bullets.append(inline(stripped[2:]))
            continue
        if stripped.startswith("## "):
            flush()
            out.append(f"<h3>{inline(stripped[3:])}</h3>")
            continue
        flush()
        out.append(f"<p>{inline(stripped)}</p>")
    flush()
    return Markup("".join(out))


def safe_next(target: str, fallback: str) -> str:
    """Только внутренние пути: // и //host уводят на чужой домен."""
    if (target.startswith("/") and not target.startswith("//")
            and "\\" not in target and not any(ord(c) < 32 for c in target)):
        return target
    return fallback


def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        if not g.get("user"):
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper


# ────────────────────────── контент ──────────────────────────

@app.route("/")
def index():
    return render_template("index.html", posts=news.published(limit=3))


@app.route("/roster")
def roster_page():
    from core.repo import wt_roster
    rating_by_nick = {r["nick"].lower(): r for r in wt_roster.get_snapshot()}
    return render_template("roster.html", rows=members.public_list(), counts=members.counts(),
                           rating_by_nick=rating_by_nick)


@app.route("/battles")
def battles_page():
    return render_template("battles.html", rows=battles.listing(), counts=battles.counts())


@app.route("/api/battles/log", methods=["POST"])
def api_battles_log():
    """Дёргает Discord-бот из /logbattle (discord_cog/battles.py) — не браузер,
    авторизация ключом, не CSRF-токеном (см. before() exempt_paths)."""
    if not config.BATTLES_API_KEY or not hmac.compare_digest(request.headers.get("X-API-Key", ""), config.BATTLES_API_KEY):
        abort(401)
    data = request.get_json(silent=True) or {}
    opponent = security.clip(data.get("opponent"), 80)
    result = data.get("result")
    if not opponent or result not in ("win", "loss", "draw"):
        return {"ok": False, "error": "opponent и result (win|loss|draw) обязательны"}, 400
    battle_id = battles.create(
        opponent=opponent,
        result=result,
        mode=security.clip(data.get("mode"), 40),
        br=security.clip(data.get("br"), 20),
        mvp_nick=security.clip(data.get("mvp_nick"), 40),
        note=security.clip(data.get("note"), 500),
        logged_by=security.clip(data.get("logged_by"), 60) or "Discord",
        discord_message_id=data.get("discord_message_id"),
    )
    return {"ok": True, "id": battle_id}


@app.route("/news")
def news_list():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 10
    total = news.count_published()
    posts = news.published(limit=per_page, offset=(page - 1) * per_page)
    return render_template("news_list.html", posts=posts, page=page,
                           pages=max(1, (total + per_page - 1) // per_page))


@app.route("/news/<slug>")
def news_post(slug):
    post = news.by_slug(slug)
    if not post:
        abort(404)
    news.bump_views(post["id"])
    return render_template("news_post.html", post=post,
                           more=[p for p in news.published(limit=4) if p["id"] != post["id"]][:3])


@app.route("/media/<path:stored_name>")
def media(stored_name):
    """Публично отдаются только обложки новостей — вложения заявок недоступны."""
    if not re.fullmatch(r"[0-9]{6,}_[0-9a-f]{10,}\.[a-z0-9]{2,5}", stored_name):
        abort(404)
    with db.ro() as conn:
        row = conn.execute("SELECT 1 FROM news WHERE cover=? AND published=1", (stored_name,)).fetchone()
    if not row:
        abort(404)
    from flask import send_from_directory
    return send_from_directory(config.UPLOAD_DIR, stored_name, max_age=86400)


# ────────────────────────── заявки ──────────────────────────

FIELD_LIMITS = {
    "real_name": 40, "nick": 40, "discord_nick": 40, "discord_id": 25, "age": 10, "tz": 40,
    "main_mode": 30, "top_br": 120, "hours": 30, "playtime": 120,
    "prev_clans": 120, "source": 120, "about": 4000,
}


@app.route("/apply", methods=["GET"])
def apply_form():
    prefill = {}
    if g.get("user"):
        already = members.by_user_id(g.user["id"])
        if not already and g.user["wt_nick"]:
            already = members.by_nick(g.user["wt_nick"])
        if already:
            flash("Ты уже в составе полка — заявка не нужна.", "ok")
            return redirect(url_for("account"))
        prefill = {"nick": g.user["wt_nick"] or "", "discord_nick": g.user["discord_nick"] or ""}
    return render_template("apply.html", form=prefill)


@app.route("/apply", methods=["POST"])
def apply_submit():
    ip = security.client_ip()
    form = {k: (v or "").strip() for k, v in request.form.items()}
    errors = []

    if form.get("website"):
        log.warning("apply: honeypot ip=%s", ip)
        return redirect(url_for("apply_done"))

    if g.get("user"):
        already = members.by_user_id(g.user["id"])
        if not already and g.user["wt_nick"]:
            already = members.by_nick(g.user["wt_nick"])
        if already:
            flash("Ты уже в составе полка — заявка не нужна.", "error")
            return render_template("apply.html", form=form), 400

    if not security.rate_ok("apply_burst", ip):
        errors.append("Заявка уже отправлена. Подожди пару минут.")
    elif not security.rate_ok("apply_ip", ip):
        errors.append("С этого адреса заявок сегодня уже достаточно. Напиши в Discord.")

    for field, limit in FIELD_LIMITS.items():
        if len(form.get(field, "")) > limit:
            errors.append(f"Поле «{field}» длиннее {limit} символов.")

    if not 2 <= len(form.get("real_name", "")) <= 40:
        errors.append("Укажи реальное имя.")
    nick = form.get("nick", "")
    if not 2 <= len(nick) <= 40:
        errors.append("Укажи ник в War Thunder.")
    if not 2 <= len(form.get("discord_nick", "")) <= 40:
        errors.append("Укажи ник в Discord.")
    if form.get("discord_id") and not re.fullmatch(r"\d{15,25}", form["discord_id"]):
        errors.append("Discord ID — только цифры. Можно оставить пустым.")
    if nick and members.by_nick(nick):
        errors.append(f"«{nick}» уже в составе полка — заявка не нужна. Есть вопрос — пиши в Discord.")
    elif nick and applications.recent_rejection(nick):
        errors.append(f"По нику «{nick}» недавно был отказ. Повторно подать можно через сутки "
                      "после решения — если это ошибка, напиши в Discord.")
    for flag, text in (("joined_discord", "Вступление в Discord обязательно."),
                       ("has_mic", "Микрофон обязателен: полковые играются в войсе."),
                       ("rules_ok", "Подтверди, что прочитал требования.")):
        if not request.form.get(flag):
            errors.append(text)

    discord_verified = False
    if config.DISCORD_APPS_ENABLED and not errors:
        verify = discord_bot.verify_member(form.get("discord_id") or None, form.get("discord_nick"))
        if verify is not None:
            discord_verified = bool(verify.get("found"))
            if not discord_verified:
                errors.append("Не нашли тебя в Discord с таким ником. Проверь, что ник совпадает "
                              "с тем, что в Discord, и что ты точно на сервере.")

    files, file_errors = uploads.save_many(request.files.getlist("attachments"))
    errors += file_errors

    if errors:
        for e in errors:
            flash(e, "error")
        for f in files:
            uploads.remove(f["stored_name"])
        return render_template("apply.html", form=form), 400

    app_id = applications.create(
        dict(
            user_id=g.user["id"] if g.get("user") else None,
            real_name=form.get("real_name"),
            nick=form.get("nick"),
            discord_nick=form.get("discord_nick"),
            discord_id=form.get("discord_id") or None,
            age=form.get("age") or None,
            tz=form.get("tz") or None,
            main_mode=form.get("main_mode") or None,
            top_br=form.get("top_br") or None,
            hours=form.get("hours") or None,
            playtime=form.get("playtime") or None,
            has_mic=1,
            joined_discord=1,
            prev_clans=form.get("prev_clans") or None,
            source=form.get("source") or None,
            about=form.get("about") or None,
            ip=ip,
            user_agent=request.headers.get("User-Agent", "")[:300],
        ),
        files,
    )
    security.rate_note("apply_burst", ip)
    security.rate_note("apply_ip", ip)
    audit.log("user" if g.get("user") else "system",
              g.user["id"] if g.get("user") else None,
              g.user["username"] if g.get("user") else "guest",
              "apply", f"app#{app_id}", form.get("nick", ""), ip)

    row, atts = applications.get(app_id)
    notify.new_application(
        row, len(atts), f"{config.ADMIN_URL}/a/{app_id}",
        on_success=lambda: applications.mark_notified(app_id),
    )
    if config.DISCORD_APPS_ENABLED:
        result = discord_bot.create_application_channel(row, atts)
        if result and result.get("ok"):
            applications.set_discord_channel(
                app_id, result.get("channel_id"), result.get("log_message_id"), discord_verified)
    session["last_app_id"] = app_id
    return redirect(url_for("apply_done"))


@app.route("/apply/done")
def apply_done():
    return render_template("apply_done.html", app_id=session.pop("last_app_id", None))


# ────────────────────────── аккаунты ──────────────────────────

@app.route("/register")
def register():
    return redirect(url_for("login", next=request.args.get("next", "")))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("account"))
    if request.method == "POST":
        ip = security.client_ip()
        login_value = (request.form.get("login") or "").strip()[:120]
        password = (request.form.get("password") or "")[:200]
        if not security.rate_hit("login_ip", ip) or not security.rate_hit("login_user", login_value.lower()):
            flash("Слишком много попыток входа. Подожди 15 минут.", "error")
            return render_template("login.html", login_value=login_value), 429
        row = users.by_login(login_value)
        if row and row["active"] and row["profile_completed"] and security.verify_password(row["password_hash"], password):
            security.rate_reset("login_user", login_value.lower())
            users.touch_login(row["id"])
            session.clear()
            session["user_id"] = row["id"]
            session.permanent = True
            audit.log("user", row["id"], row["username"], "login", "", "", ip)
            nxt = request.form.get("next") or ""
            return redirect(safe_next(nxt, url_for("account")))
        flash("Неверный логин или пароль.", "error")
        return render_template("login.html", login_value=login_value), 401
    return render_template("login.html", login_value="")


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


# ────────────────────────── Discord OAuth ──────────────────────────

@app.route("/auth/discord/login")
def discord_login():
    if not config.DISCORD_OAUTH_CLIENT_ID:
        flash("Вход через Discord временно недоступен.", "error")
        return redirect(url_for("login"))
    state = secrets.token_urlsafe(24)
    session["_oauth_state"] = state
    nxt = request.args.get("next") or ""
    if nxt and safe_next(nxt, ""):
        session["_oauth_next"] = nxt
    else:
        session.pop("_oauth_next", None)
    # link=1 — привязка Discord к уже вошедшему аккаунту, не логин с нуля
    session["_oauth_link"] = bool(g.get("user")) and request.args.get("link") == "1"
    return redirect(discord_oauth.build_authorize_url(state))


@app.route("/auth/discord/callback")
def discord_callback():
    error = request.args.get("error")
    if error:
        flash("Вход через Discord отменён.", "error")
        return redirect(url_for("login"))

    state = request.args.get("state", "")
    expected = session.pop("_oauth_state", None)
    if not expected or not hmac.compare_digest(state, expected):
        flash("Сессия входа истекла, попробуй ещё раз.", "error")
        return redirect(url_for("login"))

    code = request.args.get("code", "")
    ip = security.client_ip()
    is_link = session.pop("_oauth_link", False)
    nxt = session.pop("_oauth_next", "") or ""

    try:
        profile = discord_oauth.exchange_code(code)
    except discord_oauth.OAuthError as e:
        flash(str(e), "error")
        return redirect(url_for("login"))

    discord_id = str(profile.get("id") or "")
    discord_username = profile.get("username") or discord_id
    discord_avatar = discord_oauth.avatar_url(discord_id, profile.get("avatar"))
    if not discord_id:
        flash("Discord не вернул ID пользователя.", "error")
        return redirect(url_for("login"))

    verify = discord_bot.verify_member(discord_id, None)
    if verify is None:
        flash("Не получилось проверить членство в Discord-сервере прямо сейчас. Попробуй чуть позже.", "error")
        return redirect(url_for("login"))
    if not verify.get("found"):
        flash(f"Доступ запрещён: ты не состоишь на нашем Discord-сервере. Вступи по ссылке и попробуй снова.", "error")
        return redirect(url_for("index") + "#discord")

    if is_link:
        if not g.get("user"):
            flash("Сессия истекла, войди заново.", "error")
            return redirect(url_for("login"))
        other = users.by_discord_id(discord_id)
        if other and other["id"] != g.user["id"]:
            flash("Этот Discord-аккаунт уже привязан к другому пользователю сайта.", "error")
            return redirect(url_for("account"))
        users.link_discord(g.user["id"], discord_id, discord_username, discord_avatar)
        audit.log("user", g.user["id"], g.user["username"], "link_discord", "", "", ip)
        flash("Discord привязан.", "ok")
        return redirect(url_for("account"))

    row = users.by_discord_id(discord_id)
    if row and row["active"]:
        users.touch_login(row["id"])
        session.clear()
        session["user_id"] = row["id"]
        session.permanent = True
        audit.log("user", row["id"], row["username"], "login_discord", "", "", ip)
        return redirect(safe_next(nxt, url_for("account")))

    placeholder_username = f"discord_{discord_id}"
    placeholder_hash = security.hash_password(secrets.token_urlsafe(32))
    uid = users.create_from_discord(discord_id, discord_username, discord_avatar,
                                    placeholder_username, placeholder_hash, ip)
    audit.log("user", uid, discord_username, "register_discord", "", "", ip)
    session.clear()
    session["user_id"] = uid
    session.permanent = True
    return redirect(url_for("complete_profile"))


@app.route("/complete-profile", methods=["GET", "POST"])
@login_required
def complete_profile():
    if g.user["profile_completed"]:
        return redirect(url_for("account"))
    form = {}
    if request.method == "POST":
        form = {k: (v or "")[:200].strip() for k, v in request.form.items()}
        errors = []
        if not security.USERNAME_RE.match(form.get("username", "")):
            errors.append("Логин: 3–32 символа, латиница, цифры, точка, дефис, подчёркивание.")
        else:
            existing = users.by_username(form["username"])
            if existing and existing["id"] != g.user["id"]:
                errors.append("Такой логин уже занят.")
        problem = security.password_problem(request.form.get("password", ""))
        if problem:
            errors.append(problem)
        elif request.form.get("password") != request.form.get("password2"):
            errors.append("Пароли не совпадают.")
        intent = form.get("intent")
        if intent not in ("clan", "music"):
            errors.append("Выбери, зачем регистрируешься.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("complete_profile.html", form=form), 400

        users.complete_profile(g.user["id"], form["username"], security.hash_password(request.form["password"]))
        users.update_profile(g.user["id"], form.get("wt_nick") or None, g.user["discord_username"])
        users.set_intent(g.user["id"], intent)
        audit.log("user", g.user["id"], form["username"], "complete_profile", "", "", security.client_ip())
        flash("Логин задан навсегда, аккаунт готов.", "ok")
        return redirect(url_for("account"))
    return render_template("complete_profile.html", form=form)


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            users.update_profile(
                g.user["id"],
                security.clip(request.form.get("wt_nick"), 40),
                security.clip(request.form.get("discord_nick"), 40),
            )
            flash("Профиль обновлён.", "ok")
        elif action == "password":
            current = (request.form.get("current") or "")[:200]
            new = (request.form.get("password") or "")[:200]
            problem = security.password_problem(new)
            if not security.verify_password(g.user["password_hash"], current):
                flash("Текущий пароль неверный.", "error")
            elif problem:
                flash(problem, "error")
            elif new != request.form.get("password2"):
                flash("Пароли не совпадают.", "error")
            else:
                users.set_password(g.user["id"], security.hash_password(new))
                flash("Пароль изменён.", "ok")
        elif action == "link_telegram":
            code = users.create_telegram_link_code(g.user["id"])
            session["_tg_link_code"] = code
        elif action == "unlink_telegram":
            users.unlink_telegram(g.user["id"])
            flash("Telegram отвязан.", "ok")
        return redirect(url_for("account"))
    roster_member = members.by_user_id(g.user["id"])
    if not roster_member and g.user["wt_nick"]:
        roster_member = members.by_nick(g.user["wt_nick"])
    tg_code = session.pop("_tg_link_code", None)
    tg_deep_link = f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start={tg_code}" if tg_code else None
    from core.db import ro
    with ro() as conn:
        season_promos = conn.execute(
            "SELECT * FROM season_promos WHERE user_id=? AND expires_at > datetime('now') ORDER BY issued_at DESC",
            (g.user["id"],),
        ).fetchall()
    return render_template("account.html", apps=applications.by_user(g.user["id"]),
                           roster_member=roster_member, tg_code=tg_code, tg_deep_link=tg_deep_link,
                           season_promos=season_promos)


# ────────────────────────── ошибки ──────────────────────────

@app.errorhandler(400)
def e400(_e):
    return render_template("error.html", code=400, text="Запрос не принят. Обнови страницу и попробуй снова."), 400


@app.errorhandler(404)
def e404(_e):
    return render_template("error.html", code=404, text="Такой страницы нет."), 404


@app.errorhandler(413)
def e413(_e):
    flash(f"Файлы слишком тяжёлые. Лимит — {config.MAX_CONTENT_MB} МБ на заявку.", "error")
    return render_template("apply.html", form={}), 413


@app.errorhandler(429)
def e429(_e):
    return render_template("error.html", code=429,
                           text=g.get("rate_message", "Слишком много запросов. Попробуй позже.")), 429


@app.errorhandler(500)
def e500(_e):
    log.exception("500 на %s", request.path)
    return render_template("error.html", code=500, text="Что-то сломалось на нашей стороне."), 500
