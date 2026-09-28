"""Loopback desktop server. Public hosting requires a hardened deployment adapter."""
import argparse
import base64
import io
import json
import logging
import os
import secrets
import sqlite3
import time
from contextlib import closing
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .domain import Invalid, required, calendar_file
from .store import Store, PROJECTS

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("business-apps")


def extract_pdf(body):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise Invalid("Для PDF установите зависимости из requirements.txt. Сейчас доступна вставка текста")
    try:
        raw = base64.b64decode(body.get("file", ""), validate=True)
        if len(raw) > 2_000_000 or not raw.startswith(b"%PDF-"):
            raise ValueError
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 10:
            raise ValueError
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if len(text.strip()) < 20:
            raise Invalid("В PDF нет текстового слоя. Скан требует OCR; вставьте распознанный текст вручную")
        return {"text": text[:50000]}
    except Invalid:
        raise
    except Exception:
        raise Invalid("Не удалось прочитать PDF. Лимит: 2 МБ, 10 страниц, без пароля")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    def __init__(self, address, store):
        self.store = store
        self.failures = {}
        self.public_hits = {}
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "BusinessDesk/1.0"
    def log_message(self, fmt, *args):
        # Never log request URLs: cancellation capabilities may be present.
        pass

    @property
    def store(self):
        return self.server.store

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            name = "desk_session_" + self.store.project
            return cookie[name].value if name in cookie else ""
        except Exception:
            return ""

    def send(self, status, value, content="application/json; charset=utf-8", headers=None):
        if not isinstance(value, bytes):
            value = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(value)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for key, val in (headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(value)

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, mutation):
        try:
            expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in expected:
                return self.send(403, {"error": "Недопустимый Host"})
            route = urlparse(self.path)
            path, query = route.path, parse_qs(route.query)
            body = {}
            if mutation:
                origin = self.headers.get("Origin")
                if self.headers.get("X-Requested-With") != "BusinessDesk" or (origin and origin not in {"http://" + x for x in expected}):
                    return self.send(403, {"error": "Недопустимый источник запроса"})
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.send(415, {"error": "Требуется JSON"})
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 3_000_000:
                    return self.send(413, {"error": "Запрос превышает лимит"})
                try:
                    body = json.loads(self.rfile.read(size))
                except (ValueError, UnicodeError):
                    raise Invalid("Неверный JSON")
                if not isinstance(body, dict):
                    raise Invalid("Ожидается объект JSON")
            if not mutation and path in ("/", "/public", "/app.js", "/style.css"):
                file = ROOT / "web" / ({"/": "index.html", "/public": "index.html"}.get(path, path[1:]))
                mime = "text/html; charset=utf-8" if file.suffix == ".html" else ("text/css; charset=utf-8" if file.suffix == ".css" else "application/javascript; charset=utf-8")
                return self.send(200, file.read_bytes(), mime)
            if not mutation and path == "/api/info":
                return self.send(200, {"project": self.store.project, "meta": PROJECTS[self.store.project],
                                     "settings": self.store.setting("business"), "authenticated": self.store.authorized(self.token())})
            if mutation and path == "/api/login":
                key = self.client_address[0]
                failures = [t for t in self.server.failures.get(key, []) if t > time.time() - 300]
                if len(failures) >= 8:
                    return self.send(429, {"error": "Слишком много попыток. Подождите 5 минут"})
                try:
                    token = self.store.login(body.get("password", ""))
                except Invalid:
                    self.server.failures[key] = failures + [time.time()]
                    raise
                self.server.failures[key] = []
                return self.send(200, {"ok": True}, headers={"Set-Cookie": f"desk_session_{self.store.project}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"})
            if path.startswith("/api/public/"):
                return self.public(path, query, body, mutation)
            if not self.store.authorized(self.token()):
                return self.send(401, {"error": "Войдите в приложение"})
            if not mutation:
                if path == "/api/dashboard":
                    return self.send(200, self.store.dashboard())
                if path == "/api/export":
                    return self.send(200, self.store.export(), "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="export.csv"'})
                if path == "/api/calendar" and self.store.project == "booking":
                    rid = query.get("id", [""])[0]
                    item = next((r for r in self.store.bookings() if r["id"] == rid), None)
                    if not item:
                        raise Invalid("Запись не найдена")
                    return self.send(200, calendar_file(item, self.store.setting("business")["name"]), "text/calendar; charset=utf-8", {"Content-Disposition": 'attachment; filename="appointment.ics"'})
                if path == "/api/email":
                    return self.email_download(query.get("id", [""])[0])
                return self.send(404, {"error": "Не найдено"})
            if path == "/api/logout":
                self.store.logout(self.token())
                return self.send(200, {"ok": True}, headers={"Set-Cookie": f"desk_session_{self.store.project}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            if path == "/api/password":
                self.store.change_password(body.get("old"), body.get("new"))
                return self.send(200, {"ok": True})
            if path == "/api/settings":
                return self.send(200, self.store.configure(body))
            if path == "/api/pdf" and self.store.project in ("invoice", "quote"):
                return self.send(200, extract_pdf(body))
            routes = {
                "quote": {"/api/create": self.store.create_quote, "/api/catalog": self.store.save_catalog},
                "invoice": {"/api/create": self.store.create_invoice},
                "support": {"/api/create": self.store.ask, "/api/article": self.store.save_article},
                "booking": {"/api/create": self.store.book, "/api/reminders": lambda b: self.store.prepare_reminders()},
            }
            if path in routes[self.store.project]:
                return self.send(200, routes[self.store.project][path](body))
            if path == "/api/invoice/save" and self.store.project == "invoice":
                return self.send(200, self.store.save_invoice(body.get("id"), body.get("fields", {})))
            if path == "/api/action":
                if self.store.project == "booking":
                    if body.get("action") != "cancel":
                        raise Invalid("Неизвестное действие")
                    return self.send(200, self.store.cancel(rid=body.get("id")))
                return self.send(200, self.store.action(body.get("id"), body.get("action"), body))
            return self.send(404, {"error": "Не найдено"})
        except Invalid as exc:
            self.send(400, {"error": str(exc)})
        except (ValueError, TypeError, KeyError):
            self.send(400, {"error": "Проверьте формат и обязательные поля"})
        except Exception:
            LOG.exception("Request failed")
            self.send(500, {"error": "Не удалось выполнить действие. Данные не подтверждены; проверьте журнал сервера"})

    def public(self, path, query, body, mutation):
        if mutation:
            key = self.client_address[0]
            hits = [t for t in self.server.public_hits.get(key, []) if t > time.time() - 60]
            if len(hits) >= 20:
                return self.send(429, {"error": "Слишком много запросов. Подождите минуту"})
            self.server.public_hits[key] = hits + [time.time()]
            if body.get("website"):
                raise Invalid("Запрос отклонён")
        if self.store.project == "booking":
            if not mutation and path == "/api/public/slots":
                return self.send(200, self.store.slots(query.get("date", [""])[0], query.get("service", [""])[0], query.get("resource", [""])[0]))
            if mutation and path == "/api/public/book":
                return self.send(200, self.store.book(body))
            if mutation and path == "/api/public/cancel":
                token = required(body.get("token"), "Код отмены", 100)
                return self.send(200, self.store.cancel(token=token))
            if not mutation and path == "/api/public/calendar":
                token = query.get("token", [""])[0]
                item = next((r for r in self.store.bookings(True) if secrets.compare_digest(r["cancel_token"], token)), None)
                if not item:
                    raise Invalid("Запись не найдена")
                return self.send(200, calendar_file(item, self.store.setting("business")["name"]), "text/calendar", {"Content-Disposition": 'attachment; filename="appointment.ics"'})
        if self.store.project == "support" and mutation and path == "/api/public/ask":
            if body.get("consent") is not True:
                raise Invalid("Нужно согласие на обработку обращения")
            return self.send(200, self.store.ask(body))
        return self.send(404, {"error": "Не найдено"})

    def email_download(self, rid):
        message = EmailMessage()
        if self.store.project == "support":
            row = next((x for x in self.store.records() if x["id"] == rid), None)
            if not row or row["status"] not in ("ready", "closed"):
                raise Invalid("Сначала сохраните проверенный ответ")
            recipient, subject, text = row["email"], "Ответ на ваше обращение", row["reply"]
        elif self.store.project == "booking":
            row = next((x for x in self.store.dashboard()["reminders"] if x["id"] == rid and x["status"] == "draft"), None)
            if not row:
                raise Invalid("Напоминание недоступно")
            recipient, subject = row["email"], "Напоминание о записи"
            text = f"Здравствуйте, {row['customer']}!\nВаша запись: {row['service']}, {row['start']} (UTC).\nЕсли время не подходит, свяжитесь с администратором."
        else:
            raise Invalid("Недоступно")
        message["To"], message["Subject"] = recipient, subject
        message["X-Unsent"] = "1"
        message.set_content(text)
        return self.send(200, message.as_bytes(), "message/rfc822", {"Content-Disposition": 'attachment; filename="draft.eml"'})


def run(project=None):
    parser = argparse.ArgumentParser(description="Four local business applications")
    parser.add_argument("--project", choices=PROJECTS, default=project or "quote")
    parser.add_argument("--port", type=int)
    parser.add_argument("--demo", action="store_true", help="Seed synthetic data in a separate demo database")
    parser.add_argument("--data-dir")
    parser.add_argument("--backup", help="Write a consistent SQLite backup and exit")
    args = parser.parse_args()
    directory = Path(args.data_dir) if args.data_dir else ROOT / "data" / (args.project + ("-demo" if args.demo else ""))
    store = Store(args.project, directory)
    if args.backup:
        target = Path(args.backup).resolve()
        if target == store.path.resolve() or target.exists():
            parser.error("Backup target must be a new file, different from the live database")
        with store.db() as db, closing(sqlite3.connect(target)) as backup:
            db.backup(backup)
        print("Backup saved:", target)
        return
    if args.demo:
        store.seed()
    port = args.port or PROJECTS[args.project]["port"]
    server = Server(("127.0.0.1", port), store)
    print(f"{PROJECTS[args.project]['name']} http://127.0.0.1:{port}", flush=True)
    print("Administrator password file:", directory.resolve() / "FIRST-LOGIN.txt", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
