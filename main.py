import csv
import io
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, request


app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CSV_URL = os.getenv("CSV_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "wc-secret").strip()

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

FIRST_MATCH_ROW = 3

TEAM1_NAME_COL = 2   # B
TEAM2_NAME_COL = 5   # E
TEAM2_GOALS_COL = 3  # C
TEAM1_GOALS_COL = 4  # D

RANKING_PLAYER_COL = 61  # BI
RANKING_TOTAL_COL = 62   # BJ
RANKING_RANK_COL = 63    # BK

POINTS_COLS = [8, 11, 14, 17, 20, 23, 26, 29, 32, 35, 38, 41, 44, 47, 50, 53, 56, 59]

TEAM_ENGLISH = {
    "مکزیک": "Mexico",
    "آفریقای جنوبی": "South Africa",
    "کره جنوبی": "South Korea",
    "جمهوری چک": "Czechia",
    "کانادا": "Canada",
    "بوسنی هرزگوین": "Bosnia and Herzegovina",
    "آمریکا": "United States",
    "پاراگوئه": "Paraguay",
    "قطر": "Qatar",
    "سوئیس": "Switzerland",
    "برزیل": "Brazil",
    "مراکش": "Morocco",
    "هائیتی": "Haiti",
    "اسکاتلند": "Scotland",
    "استرالیا": "Australia",
    "ترکیه": "Turkey",
    "آلمان": "Germany",
    "کوراکائو": "Curacao",
    "هلند": "Netherlands",
    "ژاپن": "Japan",
    "ساحل عاج": "Ivory Coast",
    "اکوادور": "Ecuador",
    "سوئد": "Sweden",
    "تونس": "Tunisia",
    "اسپانیا": "Spain",
    "کپ ورد": "Cape Verde",
    "بلژیک": "Belgium",
    "مصر": "Egypt",
    "عربستان سعودی": "Saudi Arabia",
    "اروگوئه": "Uruguay",
    "اورگوئه": "Uruguay",
    "ایران": "Iran",
    "نیوزلند": "New Zealand",
    "فرانسه": "France",
    "سنگال": "Senegal",
    "عراق": "Iraq",
    "نروژ": "Norway",
    "آرژانتین": "Argentina",
    "الجزایر": "Algeria",
    "اتریش": "Austria",
    "اردن": "Jordan",
    "پرتغال": "Portugal",
    "کنگو": "DR Congo",
    "انگلستان": "England",
    "کرواسی": "Croatia",
    "غنا": "Ghana",
    "پاناما": "Panama",
    "ازبکستان": "Uzbekistan",
    "کلمبیا": "Colombia",
}

FLAGS = {
    "Mexico": "🇲🇽",
    "South Africa": "🇿🇦",
    "South Korea": "🇰🇷",
    "Czechia": "🇨🇿",
    "Canada": "🇨🇦",
    "Bosnia and Herzegovina": "🇧🇦",
    "United States": "🇺🇸",
    "Paraguay": "🇵🇾",
    "Qatar": "🇶🇦",
    "Switzerland": "🇨🇭",
    "Brazil": "🇧🇷",
    "Morocco": "🇲🇦",
    "Haiti": "🇭🇹",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Australia": "🇦🇺",
    "Turkey": "🇹🇷",
    "Germany": "🇩🇪",
    "Curacao": "🇨🇼",
    "Netherlands": "🇳🇱",
    "Japan": "🇯🇵",
    "Ivory Coast": "🇨🇮",
    "Ecuador": "🇪🇨",
    "Sweden": "🇸🇪",
    "Tunisia": "🇹🇳",
    "Spain": "🇪🇸",
    "Cape Verde": "🇨🇻",
    "Belgium": "🇧🇪",
    "Egypt": "🇪🇬",
    "Saudi Arabia": "🇸🇦",
    "Uruguay": "🇺🇾",
    "Iran": "🇮🇷",
    "New Zealand": "🇳🇿",
    "France": "🇫🇷",
    "Senegal": "🇸🇳",
    "Iraq": "🇮🇶",
    "Norway": "🇳🇴",
    "Argentina": "🇦🇷",
    "Algeria": "🇩🇿",
    "Austria": "🇦🇹",
    "Jordan": "🇯🇴",
    "Portugal": "🇵🇹",
    "DR Congo": "🇨🇩",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Croatia": "🇭🇷",
    "Ghana": "🇬🇭",
    "Panama": "🇵🇦",
    "Uzbekistan": "🇺🇿",
    "Colombia": "🇨🇴",
}


def display_team(name: str) -> str:
    english = TEAM_ENGLISH.get(name, name)
    flag = FLAGS.get(english, "⚽")
    return f"{flag} {english}"
    
GAMES_PAGE_SIZE = 8
CACHE_TTL_SECONDS = 30

_cache: Dict[str, Any] = {
    "time": 0,
    "rows": [],
}


@app.get("/")
def home():
    return "WC Friends Ranking Bot is running ✅"


@app.post(f"/webhook/{WEBHOOK_SECRET}")
def telegram_webhook():
    update = request.get_json(silent=True) or {}

    if "message" in update:
        handle_message(update["message"])

    if "callback_query" in update:
        handle_callback(update["callback_query"])

    return {"ok": True}


@app.get(f"/set-webhook/{WEBHOOK_SECRET}")
def set_webhook():
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN is missing"}

    base_url = request.url_root.rstrip("/")
    webhook_url = f"{base_url}/webhook/{WEBHOOK_SECRET}"

    response = requests.post(
        f"{TELEGRAM_API}/setWebhook",
        json={
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True,
        },
        timeout=15,
    )

    return response.json()


@app.get(f"/delete-webhook/{WEBHOOK_SECRET}")
def delete_webhook():
    response = requests.post(
        f"{TELEGRAM_API}/deleteWebhook",
        json={"drop_pending_updates": True},
        timeout=15,
    )
    return response.json()


@app.get(f"/webhook-info/{WEBHOOK_SECRET}")
def webhook_info():
    response = requests.get(f"{TELEGRAM_API}/getWebhookInfo", timeout=15)
    return response.json()


def handle_message(message: Dict[str, Any]) -> None:
    chat_id = message["chat"]["id"]
    text = str(message.get("text", "")).strip()
    lower = text.lower()

    if text in ["/start", "/menu", "منو"]:
        send_main_menu(chat_id)
        return

    if "رنکینگ" in text or "ranking" in lower or "rank" in lower:
        send_ranking(chat_id)
        return

    if "بازی" in text or "لیست" in text or "games" in lower or "matches" in lower:
        send_games_page(chat_id, 0)
        return

    send_main_menu(chat_id)


def handle_callback(callback: Dict[str, Any]) -> None:
    query_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    data = str(callback.get("data", ""))

    answer_callback(query_id)

    if data == "ranking":
        send_ranking(chat_id)
        return

    if data == "games":
        send_games_page(chat_id, 0)
        return

    if data.startswith("games:"):
        page = safe_int(data.split(":", 1)[1], 0)
        send_games_page(chat_id, page)
        return

    if data.startswith("match:"):
        row_number = safe_int(data.split(":", 1)[1], 0)
        send_match_predictions(chat_id, row_number)
        return

    send_main_menu(chat_id)


def send_main_menu(chat_id: int) -> None:
    send_message(
        chat_id,
        "چی رو می‌خوای ببینی؟ 😄",
        reply_markup={
            "inline_keyboard": [
                [{"text": "🏆 رنکینگ", "callback_data": "ranking"}],
                [{"text": "📅 لیست بازی‌ها", "callback_data": "games"}],
            ]
        },
    )


def send_ranking(chat_id: int) -> None:
    rows = get_sheet_rows()

    ranking_rows = []
    for row in rows:
        player = cell(row, RANKING_PLAYER_COL)
        total = cell(row, RANKING_TOTAL_COL)
        rank = cell(row, RANKING_RANK_COL)

        if not player or not total:
            continue

        combined = f"{player} {total} {rank}".lower()
        if "player name" in combined or "total points" in combined or "rank" in combined:
            continue

        ranking_rows.append((rank, player, total))

    if not ranking_rows:
        send_message(chat_id, "رنکینگ پیدا نشد. ستون‌های BI:BJ:BK رو چک کن.")
        return

    text = "🏆 رنکینگ فعلی\n\n"
    for rank, player, total in ranking_rows[:30]:
        text += f"{rank}. {player} — {total} امتیاز\n"

    send_long_message(chat_id, text)


def send_games_page(chat_id: int, page: int) -> None:
    games = get_games()

    if not games:
        send_message(chat_id, "لیست بازی‌ها پیدا نشد. ستون‌های B و E رو چک کن.")
        return

    total_pages = (len(games) + GAMES_PAGE_SIZE - 1) // GAMES_PAGE_SIZE
    safe_page = max(0, min(page, total_pages - 1))

    start = safe_page * GAMES_PAGE_SIZE
    page_games = games[start:start + GAMES_PAGE_SIZE]

    keyboard = [
        [{"text": f"{g['index']}. {g['team1']} - {g['team2']}", "callback_data": f"match:{g['row_number']}"}]
        for g in page_games
    ]

    nav = []
    if safe_page > 0:
        nav.append({"text": "⬅️ قبلی", "callback_data": f"games:{safe_page - 1}"})
    if safe_page < total_pages - 1:
        nav.append({"text": "بعدی ➡️", "callback_data": f"games:{safe_page + 1}"})
    if nav:
        keyboard.append(nav)

    send_message(
        chat_id,
        f"📅 لیست بازی‌ها — صفحه {safe_page + 1} از {total_pages}",
        reply_markup={"inline_keyboard": keyboard},
    )


def send_match_predictions(chat_id: int, row_number: int) -> None:
    rows = get_sheet_rows()

    if row_number < 1 or row_number > len(rows):
        send_message(chat_id, "این ردیف بازی معتبر نیست.")
        return

    row = rows[row_number - 1]
    header1 = rows[0] if len(rows) >= 1 else []
    header2 = rows[1] if len(rows) >= 2 else []

    team1 = cell(row, TEAM1_NAME_COL)
    team2 = cell(row, TEAM2_NAME_COL)
    
    team1_display = display_team(team1)
    team2_display = display_team(team2)

    if not team1 or not team2:
        send_message(chat_id, "این ردیف بازی معتبر نیست.")
        return

    real_team1_goals = cell(row, TEAM1_GOALS_COL)
    real_team2_goals = cell(row, TEAM2_GOALS_COL)

    text = f"⚽ {team1_display} vs {team2_display}\n"

    if real_team1_goals != "" and real_team2_goals != "":
        text += f"Final: {team1_display} {real_team1_goals}-{real_team2_goals} {team2_display}\n"
    else:
        text += "نتیجه واقعی: هنوز وارد نشده\n"

    text += "\n📌 پیش‌بینی‌ها:\n\n"

    for index, points_col in enumerate(POINTS_COLS):
        player = get_player_name(header1, header2, points_col, index)

        pred_team2 = cell(row, points_col - 2)
        pred_team1 = cell(row, points_col - 1)
        points = cell(row, points_col)

        if pred_team1 == "" and pred_team2 == "":
            text += f"{player}: —\n"
            continue

        line = f"{player}: {team1_display} {pred_team1}-{pred_team2} {team2_display}"
        if points != "":
            line += f" | {points} امتیاز"

        text += line + "\n"

    send_long_message(chat_id, text)


def get_games() -> List[Dict[str, Any]]:
    rows = get_sheet_rows()
    games = []

    for zero_index, row in enumerate(rows[FIRST_MATCH_ROW - 1:], start=FIRST_MATCH_ROW):
        team1 = cell(row, TEAM1_NAME_COL)
        team2 = cell(row, TEAM2_NAME_COL)

        if not team1 or not team2:
            continue

        games.append(
            {
                "index": len(games) + 1,
                "row_number": zero_index,
                "team1": display_team(team1),
                "team2": display_team(team2),
            }
        )

    return games


def get_sheet_rows() -> List[List[str]]:
    now = time.time()

    if _cache["rows"] and now - _cache["time"] < CACHE_TTL_SECONDS:
        return _cache["rows"]

    if not CSV_URL:
        return []

    response = requests.get(CSV_URL, timeout=15)
    response.raise_for_status()

    text = response.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = [[str(value).strip() for value in row] for row in reader]

    _cache["rows"] = rows
    _cache["time"] = now

    return rows


def get_player_name(header1: List[str], header2: List[str], points_col: int, index: int) -> str:
    positions = [points_col - 2, points_col - 1, points_col]

    candidates = []
    for pos in positions:
        candidates.append(cell(header1, pos))
    for pos in positions:
        candidates.append(cell(header2, pos))

    for candidate in candidates:
        v = str(candidate).strip()
        lower = v.lower()

        if not v:
            continue
        if "امتیاز" in v or "نتیجه" in v or "پیش" in v:
            continue
        if "player name" in lower or "total points" in lower or "rank" in lower:
            continue

        return v

    return f"Player {index + 1}"


def cell(row: List[str], one_based_col: int) -> str:
    index = one_based_col - 1
    if index < 0 or index >= len(row):
        return ""
    return str(row[index]).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}

    if reply_markup:
        payload["reply_markup"] = reply_markup

    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)


def send_long_message(chat_id: int, text: str) -> None:
    max_len = 3800

    if len(text) <= max_len:
        send_message(chat_id, text)
        return

    for start in range(0, len(text), max_len):
        send_message(chat_id, text[start:start + max_len])


def answer_callback(callback_query_id: str) -> None:
    requests.post(
        f"{TELEGRAM_API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id},
        timeout=15,
    )
