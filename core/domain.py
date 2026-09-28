"""Deterministic business rules; no model-generated prices or accounting decisions."""
import csv
import hashlib
import io
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo


class Invalid(ValueError):
    pass


def required(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Invalid(f"{label}: заполните поле (до {limit} символов)")
    return value.strip()


def email(value):
    value = required(value, "Email", 254).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise Invalid("Проверьте адрес email")
    return value


def money(value):
    try:
        number = Decimal(str(value).strip().replace(",", "."))
        if not number.is_finite() or number < 0 or number > 100000000:
            raise InvalidOperation
        rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if number != rounded:
            raise Invalid("У суммы может быть не больше двух знаков после запятой")
        return rounded
    except (InvalidOperation, ValueError):
        raise Invalid("Сумма должна быть числом от 0 до 100 000 000")


def quote_lines(text, catalog):
    """CSV SKU,quantity. Unknown codes are review items, never fuzzy substitutes."""
    result, total = [], Decimal("0")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows) > 200:
        raise Invalid("Добавьте от 1 до 200 строк: артикул,количество")
    for row in rows:
        if not row or not any(x.strip() for x in row):
            continue
        if len(row) != 2:
            raise Invalid("Каждая строка: артикул,количество. Например LAMP-01,3")
        sku = required(row[0], "Артикул", 80).upper()
        try:
            quantity = Decimal(row[1].strip())
            if not quantity.is_finite() or quantity <= 0 or quantity > 100000:
                raise InvalidOperation
        except InvalidOperation:
            raise Invalid("Количество должно быть положительным числом до 100 000")
        product = catalog.get(sku)
        item = {"sku": sku, "quantity": str(quantity), "matched": bool(product)}
        if product:
            price = money(product["price"])
            subtotal = (price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += subtotal
            item.update(name=product["name"], price=str(price), subtotal=str(subtotal))
        else:
            item.update(name="Нет в каталоге — нужна проверка", price=None, subtotal=None)
        result.append(item)
    if not result:
        raise Invalid("Нет позиций для расчёта")
    return result, str(total.quantize(Decimal("0.01")))


INVOICE_LABELS = {
    "vendor": ["vendor", "supplier", "поставщик"],
    "number": ["invoice", "invoice number", "номер", "счет", "счёт"],
    "date": ["date", "дата"], "due": ["due", "due date", "срок"],
    "net": ["net", "subtotal", "без налога"], "tax": ["tax", "налог", "ндс"],
    "total": ["total", "итого"], "currency": ["currency", "валюта"],
}


def parse_invoice(text):
    fields = {}
    for key, labels in INVOICE_LABELS.items():
        pattern = r"^\s*(?:" + "|".join(re.escape(x) for x in labels) + r")\s*:\s*(.+?)\s*$"
        matches = re.findall(pattern, text, re.I | re.M)
        fields[key] = matches[0] if len(matches) == 1 else ""
    return fields


def validate_invoice(fields):
    problems = []
    for name in ("vendor", "number", "date", "due", "net", "tax", "total", "currency"):
        if not str(fields.get(name, "")).strip():
            problems.append(f"Не заполнено: {name}")
    dates = {}
    for name in ("date", "due"):
        try:
            dates[name] = datetime.strptime(fields.get(name, ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            problems.append(f"{name}: нужна дата ГГГГ-ММ-ДД")
    if len(dates) == 2 and dates["due"] < dates["date"]:
        problems.append("Срок оплаты раньше даты счёта")
    try:
        amounts = {k: money(fields.get(k, "")) for k in ("net", "tax", "total")}
        if amounts["net"] + amounts["tax"] != amounts["total"]:
            problems.append("Сумма без налога + налог не равна итогу")
        if amounts["total"] == 0:
            problems.append("Итог должен быть больше нуля")
    except Invalid as exc:
        problems.append(str(exc))
    if fields.get("currency") not in ("EUR", "USD", "GBP", "RUB", "UAH", "PLN", "CZK"):
        problems.append("Выберите поддерживаемую валюту")
    return problems


def invoice_key(fields):
    vendor = re.sub(r"\s+", " ", str(fields.get("vendor", "")).strip().casefold())
    number = str(fields.get("number", "")).strip().casefold()
    return hashlib.sha256((vendor + "|" + number).encode()).hexdigest() if vendor and number else None


STOP = set("what how when where is are the a an do does my i can to of on in and about please как что где когда мне мой моя это для по на и с в у о ли вы я".split())


def tokens(text):
    return set(re.findall(r"[\w]+", text.casefold())) - STOP


def support_answer(question, articles):
    words = tokens(question)
    ranked = []
    for article in articles:
        terms = tokens(article["title"] + " " + article.get("keywords", ""))
        common = words & terms
        if common:
            score = len(common) / max(1, len(words))
            ranked.append((score, len(common), article))
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if not ranked or ranked[0][0] < .5 or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return {"answer": "В базе знаний нет однозначного ответа. Обращение передано оператору.",
                "source": None, "status": "needs_agent", "method": "knowledge_search"}
    article = ranked[0][2]
    return {"answer": article["body"], "source": {"id": article["id"], "title": article["title"]},
            "status": "suggested", "method": "knowledge_search"}


def slot_time(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        raise Invalid("Время должно содержать часовой пояс")


def check_booking(start, duration, settings, now=None):
    now = now or datetime.now(timezone.utc)
    local = start.astimezone(ZoneInfo(settings["timezone"]))
    end = local + timedelta(minutes=duration)
    if start < now + timedelta(minutes=30) or start > now + timedelta(days=60):
        raise Invalid("Запись доступна за 30 минут — 60 дней")
    if local.weekday() > 4 or local.hour < settings["open_hour"] or end.date() != local.date() or \
            end.hour > settings["close_hour"] or (end.hour == settings["close_hour"] and end.minute):
        raise Invalid("Время вне рабочего графика: понедельник–пятница")
    if local.minute % 30 or local.second or local.microsecond:
        raise Invalid("Выберите слот с шагом 30 минут")


def safe_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    for row in rows:
        writer.writerow(["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v for v in row])
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def calendar_file(booking, business):
    def esc(value):
        return str(value).replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")
    def stamp(value):
        return slot_time(value).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BookDesk//EN", "BEGIN:VEVENT",
             f"UID:{booking['id']}@bookdesk.local", "DTSTAMP:" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
             "DTSTART:" + stamp(booking["start"]), "DTEND:" + stamp(booking["end"]),
             "SUMMARY:" + esc(business + " — " + booking["service"]),
             "STATUS:" + ("CANCELLED" if booking["status"] == "cancelled" else "CONFIRMED"),
             "END:VEVENT", "END:VCALENDAR"]
    return ("\r\n".join(lines) + "\r\n").encode()
