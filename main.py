import os
from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from database import init_db, save_participant, get_all_participants
from PIL import Image, ImageDraw, ImageFont
import io
import json
import requests
import csv

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ .env ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VK_APP_ID = "1234567"
TELEGRAM_BOT_NAME = "Sloboda8Marta_bot"  # ← без @

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATE_PATH = os.path.join(STATIC_DIR, "full_template.jpg")

init_db()
app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Создаём заглушку, если шаблона нет
if not os.path.exists(TEMPLATE_PATH):
    img = Image.new('RGB', (1080, 4830), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except:
        font = ImageFont.load_default()
    draw.text((50, 50), "ЗАГЛУШКА\n(full_template.jpg не найден)", fill="black", font=font)
    img.save(TEMPLATE_PATH)


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


def smart_split(text: str, max_first_line=38):
    """Разбивает текст на 2 строки: первая — до 38 символов, вторая — остаток"""
    if not text:
        return "", ""
    words = text.split()
    line1 = ""
    line2 = ""
    for word in words:
        test_line = f"{line1} {word}".strip()
        if len(test_line) <= max_first_line:
            line1 = test_line
        else:
            line2 = " ".join(words[len(line1.split()):])
            break
    if not line1:
        line1 = text[:max_first_line]
        line2 = text[max_first_line:]
    return line1, line2


@app.post("/generate")
async def generate_result(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    platform = data.get("platform", "web")
    answers = data.get("answers", {})

    save_participant(user_id, platform, json.dumps(answers, ensure_ascii=False))

    img = Image.open(TEMPLATE_PATH).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_path = os.path.join(STATIC_DIR, "fonts", "Blogger_Sans-Light_Italic.otf")
    try:
        font = ImageFont.truetype(font_path, 40)  # ← размер шрифта: 40
    except Exception as e:
        print(f"⚠️ Шрифт не загружен: {e}. Используем стандартный.")
        font = ImageFont.load_default()

    # Твои координаты
    y_first = {
        'name': 827,
        'city': 1131,
        'dream': 1422,
        'age': 1733,
        'hobby': 2023,
        'goal': 2312,
        'quote': 2604,
        'extra': 2864
    }

    fields = ['name', 'city', 'dream', 'age', 'hobby', 'goal', 'quote', 'extra']

    for field in fields:
        text = str(answers.get(field, "")).strip()[:76]  # ← 76 символов
        if not text:
            continue

        line1, line2 = smart_split(text, max_first_line=38)  # ← 38 на первую строку

        y1 = y_first[field]
        draw.text((164, y1), line1, fill=(85, 85, 85), font=font)
        if line2:
            draw.text((164, y1 + 68), line2, fill=(85, 85, 85), font=font)

    img_io = io.BytesIO()
    img.save(img_io, 'JPEG', quality=95)
    img_io.seek(0)

    # Отправка в Telegram (только если токен задан)
    if platform == "telegram" and user_id and TELEGRAM_BOT_TOKEN:
        caption = (
            "✨ Ваш персонализированный результат!\n\n"
            "Хочешь такой же? Пройди анкету прямо сейчас 👇\n"
            f"https://t.me/{TELEGRAM_BOT_NAME}?start"
        )
        img_io_for_tg = io.BytesIO(img_io.getvalue())
        img_io_for_tg.name = "result.jpg"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {"photo": img_io_for_tg}
        payload = {"chat_id": user_id, "caption": caption}
        try:
            requests.post(url, data=payload, files=files)
        except Exception as e:
            print("Telegram send error:", e)

    return StreamingResponse(img_io, media_type="image/jpeg")


@app.get("/admin/export")
def export_csv(password: str = Query(...)):
    if password != "radar1786":
        return {"error": "Access denied"}

    participants = get_all_participants()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "User ID", "Platform", "Data", "Completed At"])
    for row in participants:
        writer.writerow(row)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=participants.csv"}
    )