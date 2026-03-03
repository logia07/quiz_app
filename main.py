import os
from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, save_participant, get_all_participants
from PIL import Image, ImageDraw, ImageFont
import io
import json
import csv
import uuid
from datetime import datetime, timedelta

# =============================================================================
# 🔴 КОНФИГУРАЦИЯ
# =============================================================================
VK_APP_ID = "54460400"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
RESULTS_DIR = os.path.join(STATIC_DIR, "results")
TEMPLATE_PATH = os.path.join(STATIC_DIR, "full_template.jpg")
FONT_PATH = os.path.join(STATIC_DIR, "fonts", "ofont.ru_StudioScriptCTT.ttf")

os.makedirs(RESULTS_DIR, exist_ok=True)
init_db()

# =============================================================================
# 🔴 FASTAPI APP
# =============================================================================
app = FastAPI()

# =============================================================================
# 🔴 CORS MIDDLEWARE
# =============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# 🔴 IFRAME HEADERS ДЛЯ VK (ФИКС 1 — CSP)
# =============================================================================
@app.middleware("http")
async def add_frame_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "ALLOWALL"
    # 🔴 ФИКС 1 — РАСШИРЕННЫЙ CSP ДЛЯ VK DESKTOP
    response.headers["Content-Security-Policy"] = "frame-ancestors https://vk.com https://*.vk.com https://*.userapi.com https://*.vkuserapi.net *"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# =============================================================================
# 🔴 ЗАГЛУШКА ЕСЛИ НЕТ ШАБЛОНА
# =============================================================================
if not os.path.exists(TEMPLATE_PATH):
    placeholder_img = Image.new('RGB', (1080, 4830), color=(245, 245, 245))
    placeholder_draw = ImageDraw.Draw(placeholder_img)
    placeholder_font = ImageFont.load_default()
    placeholder_draw.text((50, 50), "ЗАГЛУШКА", fill="black", font=placeholder_font)
    placeholder_img.save(TEMPLATE_PATH)


# =============================================================================
# 🔴 МАРШРУТЫ
# =============================================================================
@app.get("/")
@app.get("/quiz_app")
@app.get("/quiz_app/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# =============================================================================
# 🔴 УТИЛИТЫ — ШРИФТЫ
# =============================================================================
def get_font(size=46):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


# =============================================================================
# 🔴 УТИЛИТЫ — ТЕКСТ
# =============================================================================
def split_image_text(text: str, max_chars=72):
    """Умный перенос по словам (для IMAGE)."""
    text = text[:max_chars]
    if len(text) <= 36:
        return text, ""
    last_space = text[:36].rfind(' ')
    if last_space == -1:
        return text[:36], text[36:72]
    return text[:last_space], text[last_space + 1:72]


def draw_text(image_draw, position, text, font_size=45, fill=(85, 85, 85)):
    """
    🔴 ОТРИСОВКА ТЕКСТА (БЕЗ EMOJI)

    - font_size=45 — стандартный размер
    - Отступ между строками: 68px
    - Emoji удаляются на клиенте (index.html)
    """
    x, y = position
    font = get_font(font_size)
    image_draw.text((x, y), text, font=font, fill=fill)


# =============================================================================
# 🔴 ГЕНЕРАЦИЯ РЕЗУЛЬТАТА
# =============================================================================
@app.post("/generate")
async def generate_result(request: Request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        platform = data.get("platform", "web")
        answers = data.get("answers", {})

        # Валидация платформы
        if platform not in ["vk", "telegram", "web"]:
            platform = "web"

        # Генерация изображения
        template_img = Image.open(TEMPLATE_PATH).convert("RGB")
        template_draw = ImageDraw.Draw(template_img)

        y_positions = {
            'name': 815, 'city': 1117, 'dream': 1408, 'age': 1719,
            'hobby': 2010, 'goal': 2299, 'quote': 2591, 'extra': 2851
        }

        for field, y_pos in y_positions.items():
            text = str(answers.get(field, "")).strip()[:72]
            if not text:
                continue
            line1, line2 = split_image_text(text)
            draw_text(template_draw, (164, y_pos), line1)
            if line2:
                draw_text(template_draw, (164, y_pos + 68), line2)

        # Сохранение результата
        short_id = uuid.uuid4().hex[:8]
        filename = f"r_{short_id}.jpg"
        filepath = os.path.join(RESULTS_DIR, filename)
        template_img.save(filepath, 'JPEG', quality=95)

        public_url = f"/r/{short_id}"

        # 🔴 ИСПРАВЛЕНИЕ 1 — ДОБАВЛЕН 4-й ПАРАМЕТР (public_url):
        safe_user_id = user_id if user_id else "anonymous"
        save_participant(safe_user_id, platform, json.dumps(answers, ensure_ascii=False), public_url)

        # Возврат изображения
        img_io = io.BytesIO()
        template_img.save(img_io, 'JPEG', quality=95)
        img_io.seek(0)

        response = StreamingResponse(img_io, media_type="image/jpeg")
        response.headers["X-Result-URL"] = public_url
        return response

    except json.JSONDecodeError as e:
        print(f"❌ JSON Error: {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


# =============================================================================
# 🔴 PREVIEW СТРАНИЦА С OPEN GRAPH TAGS (ДЛЯ SHARE В TELEGRAM/VK)
# =============================================================================
@app.get("/preview/{short_id}")
async def preview_result(short_id: str):
    """HTML страница с OG tags для красивого preview в мессенджерах."""
    try:
        filepath = os.path.join(RESULTS_DIR, f"r_{short_id}.jpg")
        if not os.path.exists(filepath):
            return JSONResponse(status_code=404, content={"error": "Result not found"})

        # 🔴 ИСПРАВЛЕНО: убраны пробелы в конце URL
        site_url = os.getenv("SITE_URL", "https://sloboda8marta.ru")
        image_url = f"{site_url}/r/{short_id}"

        # 🔴 ТОЛЬКО ЗАГОЛОВОК И КАРТИНКА (текст в message — не дублируем)
        og_title = "Результат анкеты"

        # 🔴 OG TAGS — ЭТО ПОПАДЁТ В VK SHARE:
        html_content = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{og_title}</title>

  <!-- 🔴 OG TAGS ДЛЯ VK SHARE -->
  <meta property="og:type" content="website">
  <meta property="og:title" content="{og_title}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:width" content="1080">
  <meta property="og:image:height" content="4830">
  <meta property="og:url" content="{image_url}">
  <meta property="og:site_name" content="Между нами девочками">

  <!-- Twitter Cards -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{og_title}">
  <meta name="twitter:image" content="{image_url}">

  <meta http-equiv="refresh" content="1;url={image_url}">

  <style>
    body {{ margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f9f9f9; font-family: sans-serif; }}
    .loading {{ text-align: center; color: #555; }}
    img {{ max-width: 100%; height: auto; border-radius: 16px; }}
  </style>
</head>
<body>
  <div class="loading">
    <p>🌸 Загрузка анкеты...</p>
    <img src="{image_url}" alt="Результат анкеты">
    <p><small>Если не загрузилось, <a href="{image_url}">нажми сюда</a></small></p>
  </div>
</body>
</html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# =============================================================================
# 🔴 КОРОТКИЕ ССЫЛКИ НА РЕЗУЛЬТАТ
# =============================================================================
@app.get("/r/{short_id}")
async def redirect_result(short_id: str):
    """Перенаправление с короткой ссылки на результат."""
    try:
        filepath = os.path.join(RESULTS_DIR, f"r_{short_id}.jpg")
        if os.path.exists(filepath):
            return FileResponse(filepath, media_type="image/jpeg")
        else:
            return JSONResponse(status_code=404, content={"error": "Result not found"})
    except OSError as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# =============================================================================
# 🔴 АДМИН ПАНЕЛЬ
# =============================================================================
@app.post("/admin/cleanup")
def cleanup_old_results(password: str = Query(...), days: int = 2):
    """Очистка старых результатов."""
    if password != "radar1786":
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    cutoff = datetime.now() - timedelta(days=days)
    deleted, total_size = 0, 0

    for filename in os.listdir(RESULTS_DIR):
        filepath = os.path.join(RESULTS_DIR, filename)
        if os.path.isdir(filepath):
            continue
        try:
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if file_mtime < cutoff:
                file_size = os.path.getsize(filepath)
                os.remove(filepath)
                deleted += 1
                total_size += file_size
        except OSError:
            continue

    return {"success": True, "deleted": deleted, "freed_space_mb": round(total_size / 1024 / 1024, 2)}


@app.get("/admin/disk-usage")
def disk_usage(password: str = Query(...)):
    """Статистика использования диска."""
    if password != "radar1786":
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    total_files, total_size = 0, 0
    for filename in os.listdir(RESULTS_DIR):
        filepath = os.path.join(RESULTS_DIR, filename)
        if os.path.isdir(filepath):
            continue
        try:
            total_files += 1
            total_size += os.path.getsize(filepath)
        except OSError:
            continue

    return {"total_files": total_files, "total_size_mb": round(total_size / 1024 / 1024, 2)}


@app.get("/admin/export")
def export_csv(password: str = Query(...)):
    """Экспорт участников в CSV — ПО ЯЧЕЙКАМ."""
    if password != "radar1786":
        return {"error": "Access denied"}

    participants = get_all_participants()
    output = io.StringIO()
    # 🔴 ДОБАВЛЕНО: delimiter=';' для Excel
    writer = csv.writer(output, delimiter=';', lineterminator='\r\n')
    # 🔴 ИСПРАВЛЕНО: BOM отдельно в начало файла
    output.write('\ufeff')
    writer.writerow(["ID", "User ID", "Platform", "Result URL", "Completed At"])
    for row in participants:
        writer.writerow(row)
    output.seek(0)

    return StreamingResponse(
        # 🔴 ДОБАВЛЕНО: .encode('utf-8-sig')
        iter([output.getvalue().encode('utf-8-sig')]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=participants.csv"}
    )