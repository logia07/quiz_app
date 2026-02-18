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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VK_APP_ID = "54435997"
TELEGRAM_BOT_NAME = "Sloboda8Marta_bot"

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATE_PATH = os.path.join(STATIC_DIR, "full_template.jpg")

init_db()
app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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


def smart_split(text: str, max_first_line=33):
    """
    Исправленная функция: делит текст на 2 строки по символам.
    Если в 1 строке 30+ символов, то во 2 можно до 40 символов.
    Иначе во 2 строке максимум 33 символа.
    """
    if not text:
        return "", ""

    # Первая строка: максимум max_first_line символов
    line1 = text[:max_first_line]

    # Остаток для второй строки
    remaining = text[max_first_line:]

    # Если в 1 строке 30+ символов, то во 2 можно 40, иначе 33
    max_line2 = 40 if len(line1) >= 30 else 33

    # Вторая строка: максимум max_line2 символов
    line2 = remaining[:max_line2]

    return line1, line2


@app.post("/generate")
async def generate_result(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    platform = data.get("platform", "web")
    answers = data.get("answers", {})

    # Сохраняем в БД
    save_participant(user_id, platform, json.dumps(answers, ensure_ascii=False))

    # Генерируем изображение
    img = Image.open(TEMPLATE_PATH).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_path = os.path.join(STATIC_DIR, "fonts", "Blogger_Sans-Light_Italic.otf")
    try:
        font = ImageFont.truetype(font_path, 35)
    except Exception as e:
        print(f"⚠️ Шрифт не загружен: {e}. Используем стандартный.")
        font = ImageFont.load_default()

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
        text = str(answers.get(field, "")).strip()[:70]  # ← ИСПРАВЛЕНО: 70 вместо 76
        if not text:
            continue
        line1, line2 = smart_split(text, max_first_line=33)
        y1 = y_first[field]
        draw.text((164, y1), line1, fill=(85, 85, 85), font=font)
        if line2:
            draw.text((164, y1 + 68), line2, fill=(85, 85, 85), font=font)

    img_io = io.BytesIO()
    img.save(img_io, 'JPEG', quality=95)
    img_io.seek(0)
    img_bytes = img_io.getvalue()

    # 🔴 TELEGRAM: Отправляем картинку в чат с ботом
    if platform == "telegram" and user_id and TELEGRAM_BOT_TOKEN:
        caption = (
            "✨ Ваш персонализированный результат!\n\n"
            "Хочешь такой же? Пройди анкету прямо сейчас 👇\n"
            f"https://t.me/{TELEGRAM_BOT_NAME}?start"
        )

        # Отправляем фото с inline keyboard для шеринга
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

        # Inline keyboard с кнопкой "Поделиться"
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "📤 Поделиться с подружками",
                        "switch_inline_query": "✨ Мой результат из анкеты Слобода! Пройди тоже 👇"
                    }
                ]
            ]
        }

        payload = {
            "chat_id": user_id,
            "caption": caption,
            "reply_markup": json.dumps(keyboard)
        }

        files = {"photo": ("result.jpg", io.BytesIO(img_bytes), "image/jpeg")}

        try:
            response = requests.post(url, data=payload, files=files, timeout=10)
            if response.status_code != 200:
                print(f"❌ Telegram send failed: {response.status_code} | {response.text}")
            else:
                print(f"✅ Sent to Telegram user {user_id}")
        except Exception as e:
            print(f"❌ Telegram send error: {e}")

    return StreamingResponse(io.BytesIO(img_bytes), media_type="image/jpeg")


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