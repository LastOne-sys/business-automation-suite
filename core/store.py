import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .domain import (Invalid, required, email, money, quote_lines, parse_invoice, validate_invoice,
                     invoice_key, support_answer, slot_time, check_booking, safe_csv, calendar_file)

PROJECTS = {
    "quote": {"name": "QuoteDesk", "tagline": "Из заявки — в точное предложение", "port": 8111},
    "invoice": {"name": "InvoiceDesk", "tagline": "Проверенные счета. Понятные платежи.", "port": 8112},
    "support": {"name": "SupportDesk", "tagline": "Ответы из ваших знаний, контроль у команды", "port": 8113},
    "booking": {"name": "BookDesk", "tagline": "Свободное время становится записью", "port": 8114},
}


def now():
    return datetime.now(timezone.utc).isoformat()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()


class Store:
    def __init__(self, project, directory):
        if project not in PROJECTS:
            raise Invalid("Неизвестный проект")
        self.project, self.directory = project, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "database.sqlite3"
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
              data TEXT NOT NULL, dedupe TEXT UNIQUE, created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, record_id TEXT, action TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS appointments(id TEXT PRIMARY KEY, resource TEXT NOT NULL,
              start TEXT NOT NULL, end TEXT NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL,
              cancel_token TEXT UNIQUE, created TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS slots ON appointments(resource, state, start, end);
            CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY, booking_id TEXT UNIQUE, state TEXT,
              data TEXT, created TEXT);
            """)
            if not db.execute("SELECT 1 FROM settings WHERE key='admin'").fetchone():
                password = secrets.token_urlsafe(18)
                salt = secrets.token_hex(16)
                self.set_setting(db, "admin", {"salt": salt, "hash": password_hash(password, salt)})
                (self.directory / "FIRST-LOGIN.txt").write_text(
                    "Local administrator password (keep private; delete after saving):\n" + password + "\n", encoding="utf-8")
            if not db.execute("SELECT 1 FROM settings WHERE key='business'").fetchone():
                self.set_setting(db, "business", {"name": PROJECTS[project]["name"], "currency": "EUR",
                    "timezone": "UTC", "open_hour": 9, "close_hour": 18, "demo": False,
                    "resources": ["Специалист 1"], "services": {"Консультация": 30, "Расширенная встреча": 60}})

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def set_setting(db, key, value):
        db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(value, ensure_ascii=False)))

    def setting(self, key):
        with self.db() as db:
            return json.loads(db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()[0])

    def login(self, password):
        auth = self.setting("admin")
        if not isinstance(password, str) or len(password) > 256 or not secrets.compare_digest(password_hash(password, auth["salt"]), auth["hash"]):
            raise Invalid("Неверный пароль")
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (now(),))
            db.execute("INSERT INTO sessions VALUES(?,?)", (hashlib.sha256(token.encode()).hexdigest(),
                       (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()))
        return token

    def authorized(self, token):
        with self.db() as db:
            return bool(db.execute("SELECT 1 FROM sessions WHERE token=? AND expires>?",
                        (hashlib.sha256(token.encode()).hexdigest(), now())).fetchone())

    def logout(self, token):
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, old, new):
        token = self.login(old)
        self.logout(token)
        if not isinstance(new, str) or not 12 <= len(new) <= 128:
            raise Invalid("Новый пароль: от 12 до 128 символов")
        salt = secrets.token_hex(16)
        with self.db() as db:
            self.set_setting(db, "admin", {"salt": salt, "hash": password_hash(new, salt)})
            db.execute("DELETE FROM sessions")
        (self.directory / "FIRST-LOGIN.txt").unlink(missing_ok=True)

    def audit(self, db, rid, action):
        db.execute("INSERT INTO audit(record_id,action,created) VALUES(?,?,?)", (rid, action, now()))

    def insert(self, db, kind, state, data, dedupe=None):
        rid = secrets.token_hex(8)
        db.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?)", (rid, kind, state, json.dumps(data, ensure_ascii=False), dedupe, now(), now()))
        self.audit(db, rid, "created:" + state)
        return rid

    def records(self, kind=None):
        with self.db() as db:
            rows = db.execute("SELECT * FROM records WHERE kind=? ORDER BY created DESC", (kind or self.project,)).fetchall()
        return [dict(json.loads(r["data"]), id=r["id"], status=r["state"], created=r["created"], updated=r["updated"]) for r in rows]

    def get(self, db, rid, kind=None):
        row = db.execute("SELECT * FROM records WHERE id=? AND kind=?", (rid, kind or self.project)).fetchone()
        if not row:
            raise Invalid("Запись не найдена")
        return row, json.loads(row["data"])

    def update(self, db, rid, state, data, dedupe=None):
        db.execute("UPDATE records SET state=?,data=?,dedupe=?,updated=? WHERE id=?",
                   (state, json.dumps(data, ensure_ascii=False), dedupe, now(), rid))
        self.audit(db, rid, "updated:" + state)

    def catalog(self):
        return {r["sku"]: r for r in self.records("catalog")}

    def save_catalog(self, body):
        text = required(body.get("csv"), "Каталог CSV", 100000)
        import csv, io
        reader = csv.DictReader(io.StringIO(text))
        if not {"sku", "name", "price"}.issubset(reader.fieldnames or []):
            raise Invalid("Заголовок CSV: sku,name,price")
        products = []
        seen = set()
        for row in reader:
            sku = required(row.get("sku"), "Артикул", 80).upper()
            if sku in seen:
                raise Invalid("Повтор артикула: " + sku)
            seen.add(sku)
            products.append({"sku": sku, "name": required(row.get("name"), "Название"), "price": str(money(row.get("price")))})
        if not 1 <= len(products) <= 1000:
            raise Invalid("Каталог: от 1 до 1000 позиций")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM records WHERE kind='catalog'")
            for p in products:
                self.insert(db, "catalog", "active", p)
        return {"count": len(products)}

    def create_quote(self, body):
        customer = required(body.get("customer"), "Клиент")
        raw = required(body.get("lines"), "Позиции", 20000)
        lines, subtotal = quote_lines(raw, self.catalog())
        discount = money(body.get("discount", 0))
        if discount > 100:
            raise Invalid("Скидка: от 0 до 100 процентов")
        from decimal import Decimal, ROUND_HALF_UP
        total = (Decimal(subtotal) * (1 - discount / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        data = {"customer": customer, "email": email(body.get("email")), "raw": raw, "lines": lines,
                "subtotal": subtotal, "discount": str(discount), "total": str(total), "currency": self.setting("business")["currency"]}
        with self.db() as db:
            rid = self.insert(db, "quote", "review" if any(not x["matched"] for x in lines) else "draft", data)
        return {"id": rid}

    def create_invoice(self, body):
        text = required(body.get("text"), "Текст счёта", 50000)
        fields = parse_invoice(text)
        fingerprint = hashlib.sha256(text.strip().encode()).hexdigest()
        key = invoice_key(fields)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for old in db.execute("SELECT id,data FROM records WHERE kind='invoice'"):
                if json.loads(old["data"]).get("fingerprint") == fingerprint:
                    return {"id": old["id"], "duplicate": True}
            if key and db.execute("SELECT 1 FROM records WHERE dedupe=?", (key,)).fetchone():
                raise Invalid("Счёт этого поставщика с таким номером уже существует")
            rid = self.insert(db, "invoice", "review", {"fields": fields, "problems": validate_invoice(fields),
                 "source": text, "fingerprint": fingerprint}, key)
        return {"id": rid}

    def save_invoice(self, rid, body):
        fields = {k: str(body.get(k, "")).strip()[:200] for k in ("vendor", "number", "date", "due", "net", "tax", "total", "currency")}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self.get(db, rid)
            if row["state"] == "paid":
                raise Invalid("Оплаченный счёт нельзя редактировать")
            data.update(fields=fields, problems=validate_invoice(fields))
            try:
                self.update(db, rid, "review", data, invoice_key(fields))
            except sqlite3.IntegrityError:
                raise Invalid("Этот номер счёта уже используется у поставщика")
        return {"ok": True}

    def save_article(self, body):
        data = {"title": required(body.get("title"), "Заголовок"),
                "keywords": required(body.get("keywords"), "Ключевые слова", 1000),
                "body": required(body.get("body"), "Ответ", 10000)}
        with self.db() as db:
            rid = body.get("id")
            if rid:
                self.get(db, rid, "article")
                self.update(db, rid, "published", data)
            else:
                rid = self.insert(db, "article", "published", data)
        return {"id": rid}

    def ask(self, body):
        question = required(body.get("question"), "Вопрос", 4000)
        answer = support_answer(question, self.records("article"))
        data = {"customer": required(body.get("customer"), "Имя"), "email": email(body.get("email")),
                "question": question, **answer, "reply": ""}
        with self.db() as db:
            rid = self.insert(db, "support", answer["status"], data)
        return {"id": rid, **answer}

    def action(self, rid, action, body):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self.get(db, rid)
            state = row["state"]
            if self.project == "quote":
                if action == "approve" and state == "draft" and all(x["matched"] for x in data["lines"]):
                    state = "approved"
                elif action == "archive" and state in ("review", "draft", "approved"):
                    state = "archived"
                else:
                    raise Invalid("Подтвердить можно только черновик без неизвестных артикулов")
            elif self.project == "invoice":
                if action == "approve" and state == "review" and not validate_invoice(data["fields"]):
                    state = "approved"
                elif action == "paid" and state == "approved":
                    state = "paid"
                else:
                    raise Invalid("Сначала исправьте поля и подтвердите счёт")
            elif self.project == "support":
                if action == "reply" and state != "closed":
                    data["reply"] = required(body.get("reply"), "Ответ", 10000)
                    state = "ready"
                elif action == "close" and state == "ready":
                    state = "closed"
                else:
                    raise Invalid("Сначала сохраните ответ оператора")
            self.update(db, rid, state, data, row["dedupe"])
        return {"ok": True}

    def bookings(self, include_tokens=False):
        with self.db() as db:
            rows = db.execute("SELECT * FROM appointments ORDER BY start").fetchall()
        return [dict(json.loads(r["data"]), id=r["id"], status=r["state"], start=r["start"], end=r["end"],
                     **({"cancel_token": r["cancel_token"]} if include_tokens else {})) for r in rows]

    def slots(self, day, service, resource):
        settings = self.setting("business")
        if service not in settings["services"] or resource not in settings["resources"]:
            raise Invalid("Выберите услугу и специалиста")
        try:
            date = datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            raise Invalid("Проверьте дату")
        length = settings["services"][service]
        busy = [r for r in self.bookings() if r["resource"] == resource and r["status"] == "confirmed"]
        result = []
        for minute in range(settings["open_hour"] * 60, settings["close_hour"] * 60, 30):
            start = date.replace(hour=minute // 60, minute=minute % 60, tzinfo=ZoneInfo(settings["timezone"])).astimezone(timezone.utc)
            try:
                check_booking(start, length, settings)
            except Invalid:
                continue
            end = start + timedelta(minutes=length)
            if not any(start < slot_time(x["end"]) and end > slot_time(x["start"]) for x in busy):
                result.append({"value": start.isoformat(), "label": start.astimezone(ZoneInfo(settings["timezone"])).strftime("%H:%M")})
        return result

    def book(self, body):
        settings = self.setting("business")
        service, resource = body.get("service"), body.get("resource")
        if service not in settings["services"] or resource not in settings["resources"]:
            raise Invalid("Неизвестная услуга или специалист")
        start = slot_time(body.get("start"))
        check_booking(start, settings["services"][service], settings)
        end = start + timedelta(minutes=settings["services"][service])
        data = {"customer": required(body.get("customer"), "Имя"), "email": email(body.get("email")),
                "service": service, "resource": resource, "note": str(body.get("note", ""))[:2000]}
        if body.get("consent") is not True:
            raise Invalid("Нужно согласие на обработку контактных данных для записи")
        rid, token = secrets.token_hex(8), secrets.token_urlsafe(24)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM appointments WHERE resource=? AND state='confirmed' AND start<? AND end>?",
                          (resource, end.isoformat(), start.isoformat())).fetchone():
                raise Invalid("Это время уже занято. Выберите другой слот")
            db.execute("INSERT INTO appointments VALUES(?,?,?,?,?,?,?,?)", (rid, resource, start.isoformat(), end.isoformat(),
                       "confirmed", json.dumps(data, ensure_ascii=False), token, now()))
            self.audit(db, rid, "booking:confirmed")
        return {"id": rid, "cancel_token": token, "start": start.isoformat()}

    def cancel(self, rid=None, token=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM appointments WHERE " + ("cancel_token=?" if token else "id=?"), (token or rid,)).fetchone()
            if not row:
                raise Invalid("Запись не найдена")
            db.execute("UPDATE appointments SET state='cancelled' WHERE id=?", (row[0],))
            db.execute("UPDATE reminders SET state='cancelled' WHERE booking_id=?", (row[0],))
            self.audit(db, row[0], "booking:cancelled")
        return {"ok": True}

    def prepare_reminders(self):
        created = 0
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT * FROM appointments WHERE state='confirmed'").fetchall():
                start = slot_time(row["start"])
                if datetime.now(timezone.utc) < start <= datetime.now(timezone.utc) + timedelta(hours=24):
                    data = json.loads(row["data"])
                    data["start"] = row["start"]
                    cur = db.execute("INSERT OR IGNORE INTO reminders VALUES(?,?,?,?,?)", (secrets.token_hex(8), row["id"], "draft", json.dumps(data), now()))
                    created += cur.rowcount
        return {"created": created}

    def export(self):
        if self.project == "invoice":
            return safe_csv([["id", "status", "vendor", "number", "date", "due", "net", "tax", "total", "currency"]] +
                [[r["id"], r["status"]] + [r["fields"][k] for k in ("vendor", "number", "date", "due", "net", "tax", "total", "currency")]
                 for r in self.records() if r["status"] in ("approved", "paid")])
        if self.project == "quote":
            return safe_csv([["id", "customer", "email", "status", "total", "currency"]] +
                [[r[k] for k in ("id", "customer", "email", "status", "total", "currency")] for r in self.records() if r["status"] == "approved"])
        columns = ["id", "customer", "email", "status", "start", "end", "service"] if self.project == "booking" else ["id", "customer", "email", "status", "question", "reply"]
        return safe_csv([columns] + [[r.get(k, "") for k in columns] for r in (self.bookings() if self.project == "booking" else self.records())])

    def dashboard(self):
        with self.db() as db:
            audit = [dict(x) for x in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 50")]
            reminders = [dict(json.loads(x["data"]), id=x["id"], status=x["state"], booking_id=x["booking_id"]) for x in db.execute("SELECT * FROM reminders ORDER BY created DESC")]
        return {"project": self.project, "meta": PROJECTS[self.project], "settings": self.setting("business"),
                "records": self.bookings() if self.project == "booking" else self.records(),
                "catalog": list(self.catalog().values()), "articles": self.records("article"), "audit": audit, "reminders": reminders}

    def configure(self, body):
        current = self.setting("business")
        current["name"] = required(body.get("name"), "Название компании", 100)
        if body.get("currency") not in ("EUR", "USD", "GBP", "RUB", "UAH", "PLN", "CZK"):
            raise Invalid("Неподдерживаемая валюта")
        if self.project == "quote" and current["currency"] != body["currency"] and self.catalog():
            raise Invalid("Валюта каталога уже задана. Для другой валюты создайте отдельное рабочее пространство через --data-dir")
        current["currency"] = body["currency"]
        if self.project == "booking":
            try:
                ZoneInfo(body.get("timezone", ""))
                opening, closing = int(body["open_hour"]), int(body["close_hour"])
                if not 0 <= opening < closing <= 23:
                    raise ValueError
            except Exception:
                raise Invalid("Проверьте часовой пояс и часы работы")
            current.update(timezone=body["timezone"], open_hour=opening, close_hour=closing)
            if "resources" in body:
                resources = [required(x, "Специалист", 100) for x in str(body["resources"]).splitlines() if x.strip()]
                if not 1 <= len(resources) <= 20 or len(set(resources)) != len(resources):
                    raise Invalid("Нужно от 1 до 20 уникальных специалистов, по одному в строке")
                if any(r["resource"] not in resources and r["status"] == "confirmed" and slot_time(r["end"]) > datetime.now(timezone.utc) for r in self.bookings()):
                    raise Invalid("Нельзя убрать специалиста с предстоящими записями")
                current["resources"] = resources
            if "services" in body:
                services = {}
                for line in str(body["services"]).splitlines():
                    if not line.strip():
                        continue
                    try:
                        name, minutes = line.rsplit(",", 1)
                        name = required(name, "Название услуги", 100)
                        minutes = int(minutes.strip())
                        if minutes not in (30, 60, 90, 120) or name in services:
                            raise ValueError
                    except (ValueError, Invalid):
                        raise Invalid("Услуги: название,минуты. Длительность: 30, 60, 90 или 120; имена уникальны")
                    services[name] = minutes
                if not 1 <= len(services) <= 30:
                    raise Invalid("Добавьте от 1 до 30 услуг")
                current["services"] = services
        with self.db() as db:
            self.set_setting(db, "business", current)
            self.audit(db, "settings", "settings:updated")
        return {"ok": True}

    def seed(self):
        """Explicit demo only. Never changes an existing customer database."""
        with self.db() as db:
            if db.execute("SELECT 1 FROM records UNION ALL SELECT 1 FROM appointments LIMIT 1").fetchone():
                return
            settings = self.setting("business")
            settings["demo"] = True
            self.set_setting(db, "business", settings)
        if self.project == "quote":
            self.save_catalog({"csv": "sku,name,price\nLAMP-01,Светильник Nordic,49.90\nWIRE-10,Кабель 10 м,12.50\nSOCKET-2,Розетка двойная,8.20"})
            self.create_quote({"customer": "DEMO · Studio North", "email": "studio@example.com", "lines": "LAMP-01,12\nWIRE-10,3", "discount": 5})
            self.create_quote({"customer": "DEMO · Green Office", "email": "office@example.com", "lines": "SOCKET-2,20\nUNKNOWN-1,2"})
        elif self.project == "invoice":
            self.create_invoice({"text": "Vendor: DEMO North Supply\nInvoice: NS-2026-041\nDate: 2026-09-28\nDue: 2026-10-12\nNet: 1000\nTax: 200\nTotal: 1200\nCurrency: EUR"})
            self.create_invoice({"text": "Vendor: DEMO Paper Co\nInvoice: PC-019\nDate: 2026-09-28\nDue: 2026-10-05\nNet: 100\nTax: 20\nTotal: 130\nCurrency: EUR"})
        elif self.project == "support":
            self.save_article({"title": "Доставка заказа", "keywords": "доставка доставки заказа сроки доставить shipping delivery", "body": "Демонстрационная политика: доставка занимает 3–5 рабочих дней после подтверждения заказа. Точный статус уточняет оператор."})
            self.save_article({"title": "Возврат товара", "keywords": "возврат вернуть refund return", "body": "Демонстрационная политика: для запроса возврата укажите номер заказа и причину. Решение принимает сотрудник поддержки; автоматический возврат денег не выполняется."})
            self.ask({"customer": "DEMO · Анна", "email": "anna@example.com", "question": "Какие сроки доставки заказа?"})
            self.ask({"customer": "DEMO · Алекс", "email": "alex@example.com", "question": "Измените банковские реквизиты"})
        elif self.project == "booking":
            date = datetime.now(timezone.utc).date() + timedelta(days=1)
            while date.weekday() > 4:
                date += timedelta(days=1)
            slots = self.slots(date.isoformat(), "Консультация", "Специалист 1")
            if slots:
                self.book({"customer": "DEMO · Анна", "email": "anna@example.com", "service": "Консультация", "resource": "Специалист 1", "start": slots[0]["value"], "consent": True})
