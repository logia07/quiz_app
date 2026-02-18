import os
from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from database import init_db, save_participant, get_all_participants
from PIL import Image, ImageDraw, ImageFont
import io
import json
import requests
import csv
import uuid
from datetime import datetime, timedelta

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VK_APP_ID = "54435997"
TELEGRAM_BOT_NAME = "Sloboda8Marta_bot"

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
RESULTS_DIR = os.path.join(STATIC_DIR, "results")
TEMPLATE_PATH = os.path.join(STATIC_DIR, "full_template.jpg")

# 🔴 СОЗДАЁМ ПАПКУ ДЛЯ РЕЗУЛЬТАТОВ
os.makedirs(RESULTS_DIR, exist_ok=True)

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
    if not text:
        return "", ""

    line1 = text[:max_first_line]
    remaining = text[max_first_line:]
    max_line2 = 40 if len(line1) >= 30 else 33
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
        text = str(answers.get(field, "")).strip()[:70]
        if not text:
            continue
        line1, line2 = smart_split(text, max_first_line=33)
        y1 = y_first[field]
        draw.text((164, y1), line1, fill=(85, 85, 85), font=font)
        if line2:
            draw.text((164, y1 + 68), line2, fill=(85, 85, 85), font=font)

    # 🔴 СОХРАНЯЕМ КАРТИНКУ НА ДИСК
    unique_id = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    filename = f"result_{unique_id}.jpg"
    filepath = os.path.join(RESULTS_DIR, filename)

    img.save(filepath, 'JPEG', quality=95)

    # 🔴 ПУБЛИЧНЫЙ URL ДЛЯ VK
    public_url = f"/static/results/{filename}"

    # Возвращаем картинку + URL
    img_io = io.BytesIO()
    img.save(img_io, 'JPEG', quality=95)
    img_io.seek(0)
    img_bytes = img_io.getvalue()

    # 🔴 TELEGRAM: Отправляем картинку в чат с ботом
    if platform == "telegram" and user_id and TELEGRAM_BOT_TOKEN:
        caption = "Результат уже в чате с ботом! Поделись с подружками и участвуй в розыгрыше призов!"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {"chat_id": user_id, "caption": caption}
        files = {"photo": ("result.jpg", io.BytesIO(img_bytes), "image/jpeg")}

        try:
            response = requests.post(url, data=payload, files=files, timeout=10)
            if response.status_code != 200:
                print(f"❌ Telegram send failed: {response.status_code} | {response.text}")
            else:
                print(f"✅ Sent to Telegram user {user_id}")
        except Exception as e:
            print(f"❌ Telegram send error: {e}")

    # 🔴 ВОЗВРАЩАЕМ URL ВМЕСТЕ С КАРТИНКОЙ
    response = StreamingResponse(io.BytesIO(img_bytes), media_type="image/jpeg")
    response.headers["X-Result-URL"] = public_url
    return response


# 🔴 НОВЫЙ ЭНДПОИНТ — ОЧИСТКА СТАРЫХ ФАЙЛОВ
@app.post("/admin/cleanup")
def cleanup_old_results(password: str = Query(...), days: int = 2):
    """
    Удаляет файлы результатов старше указанного количества дней.

    Параметры:
    - password: пароль администратора
    - days: сколько дней хранить файлы (по умолчанию 2)

    Пример:
    POST /admin/cleanup?password=radar1786&days=2
    """
    if password != "radar1786":
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    total_size = 0

    try:
        for filename in os.listdir(RESULTS_DIR):
            filepath = os.path.join(RESULTS_DIR, filename)

            # Пропускаем папки
            if os.path.isdir(filepath):
                continue

            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))

            if file_mtime < cutoff:
                file_size = os.path.getsize(filepath)
                os.remove(filepath)
                deleted += 1
                total_size += file_size
                print(f"🗑️ Deleted: {filename} ({file_size / 1024 / 1024:.2f} MB)")

        return {
            "success": True,
            "deleted": deleted,
            "freed_space_mb": round(total_size / 1024 / 1024, 2),
            "days": days,
            "cutoff_date": cutoff.isoformat()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# 🔴 НОВЫЙ ЭНДПОИНТ — СТАТИСТИКА ПО ДИСКУ
@app.get("/admin/disk-usage")
def disk_usage(password: str = Query(...)):
    """
    Показывает статистику использования диска файлами результатов.

    Пример:
    GET /admin/disk-usage?password=radar1786
    """
    if password != "radar1786":
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    total_files = 0
    total_size = 0
    oldest_file = None
    newest_file = None

    try:
        for filename in os.listdir(RESULTS_DIR):
            filepath = os.path.join(RESULTS_DIR, filename)

            if os.path.isdir(filepath):
                continue

            total_files += 1
            file_size = os.path.getsize(filepath)
            total_size += file_size
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))

            if oldest_file is None or file_mtime < oldest_file:
                oldest_file = file_mtime
            if newest_file is None or file_mtime > newest_file:
                newest_file = file_mtime

        return {
            "total_files": total_files,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "oldest_file": oldest_file.isoformat() if oldest_file else None,
            "newest_file": newest_file.isoformat() if newest_file else None,
            "results_dir": RESULTS_DIR
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


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