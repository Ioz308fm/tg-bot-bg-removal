import os
from uuid import uuid4
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from rembg import remove
from PIL import Image, ImageDraw
from dotenv import load_dotenv
import asyncio
import nest_asyncio
import io

# === Конфигурация ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
BG_PATH = "backgrounds/"
TEMPLATE_PATH = "templates/"
user_states = {}  # {user_id: state}

# === Предустановленные цвета и шаблоны ===
COLOR_OPTIONS = {
    "Белый": (255, 255, 255),
    "Чёрный": (0, 0, 0),
    "Красный": (255, 0, 0),
    "Зелёный": (0, 255, 0),
    "Синий": (0, 0, 255)
}

TEMPLATES = {
    "Пейзаж": f"{TEMPLATE_PATH}landscape.jpg",
    "Градиент": f"{TEMPLATE_PATH}gradient.jpg",
    "Абстракция": f"{TEMPLATE_PATH}abstract.jpg"
}

# === Клавиатуры ===
# Клавиатура при первом запуске
def start_keyboard():
    return ReplyKeyboardMarkup([["Начать"]], resize_keyboard=True)

# Основная клавиатура после начала
def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["Выбрать фон", "Инструкция"],
        ],
        resize_keyboard=True
    )

def choose_background_method_keyboard():
    return ReplyKeyboardMarkup([
        ["Шаблон", "Цвет", "Свой фон"],
        ["Назад"]
    ], resize_keyboard=True)

def color_keyboard():
    return ReplyKeyboardMarkup(
        [[color] for color in COLOR_OPTIONS] + [["⬅️ Назад"]],
        resize_keyboard=True
    )

def template_keyboard():
    return ReplyKeyboardMarkup(
        [[template] for template in TEMPLATES] + [["⬅️ Назад"]],
        resize_keyboard=True
    )

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user_states[user_id] = {"mode": None}

    await update.message.reply_text(
        "Привет! Я бот для удаления фона с фото 🖼\nНажми 'Начать', чтобы приступить!",
        reply_markup=start_keyboard()
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()

    # Главное меню
    if text == "Начать":
        await update.message.reply_text(
        "Отправь мне фото, и я удалю фон.\nТакже можешь выбрать фон, цвет или шаблон.",
        reply_markup=main_keyboard()
    )
        
    elif text == "Инструкция":
        await update.message.reply_text(
            "Чтобы изменить фон:\n"
            "1. Нажми 'Выбрать фон'\n"
            "2. Выбери цвет, шаблон или отправь своё фото\n"
            "3. Отправь фото — получишь результат!",
            reply_markup=main_keyboard()
        )

    elif text == "Выбрать фон":
        user_states[user_id]["mode"] = "choosing_background_method"
        await update.message.reply_text("Выберите способ установки фона:", reply_markup=choose_background_method_keyboard())

    elif text == "Шаблон":
        user_states[user_id]["mode"] = "choosing_template"

        # Отправляем каждое изображение с подписью
        for name, path in TEMPLATES.items():
            if os.path.exists(path):
                await update.message.reply_photo(
                    photo=open(path, "rb"),
                    caption=name
                )

        await update.message.reply_text("Выберите шаблон:", reply_markup=template_keyboard())

    elif text == "Цвет":
        user_states[user_id]["mode"] = "choosing_color"
        await update.message.reply_text("Выберите цвет фона:", reply_markup=color_keyboard())

    elif text == "Свой фон":
        user_states[user_id]["mode"] = "waiting_for_background"
        await update.message.reply_text("Отправьте своё изображение-фон", reply_markup=main_keyboard())

    elif text in COLOR_OPTIONS:
        user_states[user_id]["color_bg"] = COLOR_OPTIONS[text]
        user_states[user_id]["background"] = None  # Удалить фон/шаблон
        await update.message.reply_text(f"Цвет фона установлен на {text}, отправьте свое изображение", reply_markup=main_keyboard())

    elif text in TEMPLATES:
        user_states[user_id]["background"] = TEMPLATES[text]
        user_states[user_id]["color_bg"] = None
        await update.message.reply_text(f"Установлен шаблон: {text}, отправьте свое изображение", reply_markup=main_keyboard())

    elif text == "Назад":
        user_states[user_id]["mode"] = None
        await update.message.reply_text("Возвращаюсь в главное меню", reply_markup=main_keyboard())

    else:
        await update.message.reply_text("Неизвестная команда.", reply_markup=main_keyboard())

# === Обработка фото ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user_data = user_states.setdefault(user_id, {})

    file = await update.message.photo[-1].get_file()
    photo_bytes = await file.download_as_bytearray()

    # === Если ожидается пользовательский фон ===
    if user_data.get("mode") == "waiting_for_background":
        # Сохраняем фото как фон
        ext = file.file_path.split('.')[-1]
        bg_filename = f"{BG_PATH}{user_id}_bg.{ext}"
        with open(bg_filename, "wb") as f:
            f.write(photo_bytes)

        user_data["background"] = bg_filename
        user_data["color_bg"] = None
        user_data["mode"] = None

        await update.message.reply_text(
            "Фон установлен! Теперь отправьте фото, с которого нужно удалить фон.",
            reply_markup=main_keyboard()
        )
        return  # ВЫХОД: это не фото для обработки, это фон

    input_image = Image.open(io.BytesIO(photo_bytes))

    # Удаляем фон
    output_image = remove(input_image)

    # Подставляем фон (если есть)
    user_data = user_states.get(user_id, {})
    if "background" in user_data:
        bg_path = user_data["background"]
        bg_image = Image.open(bg_path).resize(output_image.size).convert("RGBA")
        output_image = Image.alpha_composite(bg_image, output_image.convert("RGBA"))
    else:
        # Белый фон по умолчанию
        white_bg = Image.new("RGBA", output_image.size, (255, 255, 255, 255))
        output_image = Image.alpha_composite(white_bg, output_image.convert("RGBA"))

    # Сохраняем результат в оперативной памяти
    result_io = io.BytesIO()
    output_image.save(result_io, format="PNG")
    result_io.seek(0)

    await update.message.reply_photo(photo=result_io, caption="Готово!", reply_markup=main_keyboard())



# === Запуск ===
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await app.run_polling()

if __name__ == "__main__":
    os.makedirs(BG_PATH, exist_ok=True)
    os.makedirs(TEMPLATE_PATH, exist_ok=True)

    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
