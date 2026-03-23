import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
STARS_PRICE = 20  # Telegram Stars за одну генерацию

# ─── Шаблоны ────────────────────────────────────────────────────────────────

TEMPLATES = {
    "automation": {
        "label": "⏰ Автоматизации",
        "items": [
            {
                "id": "morning_routine",
                "name": "Утренний режим",
                "desc": "В 7:30 — выключить Do Not Disturb, яркость 80%, открыть погоду",
                "actions": [
                    {"WFWorkflowActionIdentifier": "is.workflow.actions.setbluetooth", "WFWorkflowActionParameters": {}},
                    {"WFWorkflowActionIdentifier": "is.workflow.actions.openapp", "WFWorkflowActionParameters": {"WFAppIdentifier": "com.apple.weather"}}
                ]
            },
            {
                "id": "night_mode",
                "name": "Ночной режим",
                "desc": "В 23:00 — включить Do Not Disturb, яркость 10%, выключить WiFi",
                "actions": []
            },
            {
                "id": "work_focus",
                "name": "Рабочий фокус",
                "desc": "Включить фокус Работа, выключить уведомления соцсетей",
                "actions": []
            },
        ]
    },
    "location": {
        "label": "📍 Геолокация",
        "items": [
            {
                "id": "send_location_telegram",
                "name": "Геолокация в Telegram",
                "desc": "Одна кнопка — отправить текущее местоположение в Telegram",
                "actions": []
            },
            {
                "id": "send_location_sms",
                "name": "Геолокация по SMS",
                "desc": "Отправить координаты на заданный номер через SMS",
                "actions": []
            },
            {
                "id": "arrived_home",
                "name": "Я дома",
                "desc": "Нажать кнопку — отправить сообщение 'Я дома' и координаты",
                "actions": []
            },
        ]
    },
    "text": {
        "label": "🌐 Текст и перевод",
        "items": [
            {
                "id": "translate_clipboard",
                "name": "Перевести буфер",
                "desc": "Скопировал текст → нажал → получил перевод на русский",
                "actions": []
            },
            {
                "id": "shorten_url",
                "name": "Сократить ссылку",
                "desc": "Скопировал URL → нажал → получил короткую ссылку",
                "actions": []
            },
            {
                "id": "clean_text",
                "name": "Очистить текст",
                "desc": "Убрать лишние пробелы и форматирование из буфера обмена",
                "actions": []
            },
        ]
    },
    "trigger": {
        "label": "🚗 По событию",
        "items": [
            {
                "id": "car_bluetooth",
                "name": "Сел в машину",
                "desc": "Подключился Bluetooth машины → открыть Яндекс.Навигатор + включить погромче",
                "actions": []
            },
            {
                "id": "home_wifi",
                "name": "Пришёл домой",
                "desc": "Подключился к домашнему WiFi → включить тихий режим + написать 'дома'",
                "actions": []
            },
            {
                "id": "low_battery",
                "name": "Батарея садится",
                "desc": "Заряд < 20% → включить режим энергосбережения + уменьшить яркость",
                "actions": []
            },
        ]
    },
    "notification": {
        "label": "🔔 Напоминания",
        "items": [
            {
                "id": "water_reminder",
                "name": "Пить воду",
                "desc": "Каждые 2 часа с 9:00 до 21:00 — напоминание выпить воду",
                "actions": []
            },
            {
                "id": "posture_reminder",
                "name": "Осанка",
                "desc": "Каждый час — напоминание выпрямить спину",
                "actions": []
            },
            {
                "id": "meeting_prep",
                "name": "Подготовка к встрече",
                "desc": "За 10 минут до события в календаре — напоминание и тихий режим",
                "actions": []
            },
        ]
    },
}

# ─── Генерация .shortcut файла через Claude ─────────────────────────────────

SYSTEM_PROMPT = """Ты эксперт по iOS Shortcuts. Твоя задача — генерировать валидные JSON структуры для файлов .shortcut (формат iOS Shortcuts).

Формат ответа — ТОЛЬКО валидный JSON, без пояснений, без markdown блоков:
{
  "name": "Название команды",
  "description": "Краткое описание",
  "actions": [
    {
      "WFWorkflowActionIdentifier": "идентификатор_действия",
      "WFWorkflowActionParameters": {}
    }
  ]
}

Используй реальные идентификаторы iOS Shortcuts actions:
- is.workflow.actions.getlocation — получить геолокацию
- is.workflow.actions.sendmessage — отправить SMS
- is.workflow.actions.notification — показать уведомление
- is.workflow.actions.setalarm — установить будильник
- is.workflow.actions.setvolume — установить громкость
- is.workflow.actions.setbrightness — установить яркость
- is.workflow.actions.setflashlight — фонарик
- is.workflow.actions.openapp — открыть приложение
- is.workflow.actions.getclipboard — получить буфер обмена
- is.workflow.actions.setclipboard — установить буфер обмена
- is.workflow.actions.text — текстовый блок
- is.workflow.actions.url — URL
- is.workflow.actions.openurl — открыть URL
- is.workflow.actions.wait — пауза в секундах
- is.workflow.actions.nothing — ничего не делать

Генерируй только то, что реально поддерживает iOS Shortcuts. Не выдумывай действия."""


async def generate_shortcut(user_request: str) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Создай iOS Shortcut: {user_request}"}]
    )
    text = message.content[0].text.strip()
    # убираем markdown если вдруг есть
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def build_shortcut_plist(shortcut_data: dict) -> bytes:
    """Создаём минимальный валидный .shortcut файл (plist формат)"""
    import plistlib
    actions = shortcut_data.get("actions", [])
    plist_data = {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "2600.0.57",
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowIcon": {
            "WFWorkflowIconBackgroundColorData": b"\x00\x00\x00\x00",
            "WFWorkflowIconStartGlyphIndex": 9731,
            "WFWorkflowIconGlyphIndex": 59511,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowName": shortcut_data.get("name", "Моя команда"),
        "WFWorkflowNoInputBehavior": {"Name": "WFWorkflowNoInputBehaviorAskForInput", "Parameters": {}},
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": [],
    }
    return plistlib.dumps(plist_data, fmt=plistlib.FMT_XML)


# ─── Клавиатуры ─────────────────────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Шаблоны (бесплатно)", callback_data="templates")],
        [InlineKeyboardButton("✨ Своя команда (20 ⭐)", callback_data="custom")],
        [InlineKeyboardButton("📦 Мои команды", callback_data="my_shortcuts")],
    ])


def templates_keyboard():
    buttons = []
    for cat_id, cat in TEMPLATES.items():
        buttons.append([InlineKeyboardButton(cat["label"], callback_data=f"cat_{cat_id}")])
    buttons.append([InlineKeyboardButton("« Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def category_keyboard(cat_id: str):
    cat = TEMPLATES[cat_id]
    buttons = []
    for item in cat["items"]:
        buttons.append([InlineKeyboardButton(item["name"], callback_data=f"tpl_{cat_id}_{item['id']}")])
    buttons.append([InlineKeyboardButton("« Назад", callback_data="templates")])
    return InlineKeyboardMarkup(buttons)


def back_to_main():
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Главное меню", callback_data="main_menu")]])


# ─── Хэндлеры ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я создаю команды для iPhone (iOS Shortcuts).\n\n"
        "📋 *Шаблоны* — готовые команды, бесплатно\n"
        "✨ *Своя команда* — опиши что нужно, я сгенерирую за 20 ⭐\n\n"
        "Что выбираешь?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "main_menu":
        await query.edit_message_text(
            "👋 Главное меню\n\nВыбери что хочешь сделать:",
            reply_markup=main_menu_keyboard()
        )

    elif data == "templates":
        await query.edit_message_text(
            "📋 *Шаблоны*\n\nВыбери категорию — все шаблоны бесплатны:",
            parse_mode="Markdown",
            reply_markup=templates_keyboard()
        )

    elif data.startswith("cat_"):
        cat_id = data[4:]
        cat = TEMPLATES[cat_id]
        await query.edit_message_text(
            f"{cat['label']}\n\nВыбери шаблон:",
            reply_markup=category_keyboard(cat_id)
        )

    elif data.startswith("tpl_"):
        _, cat_id, item_id = data.split("_", 2)
        cat = TEMPLATES[cat_id]
        item = next(i for i in cat["items"] if i["id"] == item_id)
        context.user_data["pending_template"] = item

        await query.edit_message_text(
            f"📌 *{item['name']}*\n\n{item['desc']}\n\nОтправить тебе этот шаблон?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, скачать!", callback_data=f"send_tpl_{cat_id}_{item_id}")],
                [InlineKeyboardButton("« Назад", callback_data=f"cat_{cat_id}")],
            ])
        )

    elif data.startswith("send_tpl_"):
        _, cat_id, item_id = data.split("_", 2)
        cat = TEMPLATES[cat_id]
        item = next(i for i in cat["items"] if i["id"] == item_id)

        shortcut_data = {
            "name": item["name"],
            "description": item["desc"],
            "actions": item["actions"]
        }
        file_bytes = build_shortcut_plist(shortcut_data)
        filename = f"{item_id}.shortcut"

        await query.edit_message_text(f"⬇️ Отправляю *{item['name']}*...", parse_mode="Markdown")
        await query.message.reply_document(
            document=file_bytes,
            filename=filename,
            caption=(
                f"✅ *{item['name']}*\n\n"
                f"{item['desc']}\n\n"
                "📱 *Как установить:*\n"
                "1. Нажми на файл\n"
                "2. Откроется приложение Команды\n"
                "3. Нажми «Добавить команду»\n\n"
                "Готово!"
            ),
            parse_mode="Markdown",
            reply_markup=back_to_main()
        )

    elif data == "custom":
        context.user_data["waiting_for_custom"] = True
        await query.edit_message_text(
            "✨ *Своя команда*\n\n"
            "Опиши что должна делать команда — простым языком.\n\n"
            "Например:\n"
            "• _Каждое утро в 7:30 отправляй мою геолокацию жене_\n"
            "• _Когда подключаюсь к WiFi в офисе — включи фокус Работа_\n"
            "• _Кнопка которая включает фонарик и ставит таймер на 10 минут_\n\n"
            "Стоимость: *20 ⭐ Telegram Stars* (~20 ₽)\n\n"
            "Напиши задачу:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Отмена", callback_data="main_menu")]])
        )

    elif data == "my_shortcuts":
        history = context.user_data.get("history", [])
        if not history:
            await query.edit_message_text(
                "📦 *Мои команды*\n\nТы пока не создавал команд. Попробуй сгенерировать свою!",
                parse_mode="Markdown",
                reply_markup=back_to_main()
            )
        else:
            text = "📦 *Мои команды:*\n\n"
            for h in history[-5:]:
                text += f"• {h}\n"
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main())


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_custom"):
        await update.message.reply_text(
            "Используй меню 👇",
            reply_markup=main_menu_keyboard()
        )
        return

    user_request = update.message.text
    context.user_data["waiting_for_custom"] = False
    context.user_data["pending_request"] = user_request

    # Отправляем инвойс для оплаты Stars
    await update.message.reply_invoice(
        title="Генерация iOS Shortcut",
        description=f"Команда: {user_request[:100]}",
        payload=f"shortcut_{update.effective_user.id}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice("Генерация команды", STARS_PRICE)],
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_request = context.user_data.get("pending_request", "")

    msg = await update.message.reply_text("⚙️ Оплата получена! Генерирую команду...")

    try:
        shortcut_data = await generate_shortcut(user_request)
        file_bytes = build_shortcut_plist(shortcut_data)
        filename = shortcut_data.get("name", "shortcut").replace(" ", "_") + ".shortcut"

        # Сохраняем в историю
        history = context.user_data.get("history", [])
        history.append(shortcut_data.get("name", user_request[:50]))
        context.user_data["history"] = history

        await msg.delete()
        await update.message.reply_document(
            document=file_bytes,
            filename=filename,
            caption=(
                f"✅ *{shortcut_data.get('name', 'Команда готова')}*\n\n"
                f"{shortcut_data.get('description', '')}\n\n"
                "📱 *Как установить:*\n"
                "1. Нажми на файл\n"
                "2. Откроется приложение Команды\n"
                "3. Нажми «Добавить команду»\n\n"
                "Готово!"
            ),
            parse_mode="Markdown",
            reply_markup=back_to_main()
        )

    except Exception as e:
        logger.error(f"Generation error: {e}")
        await msg.edit_text(
            "❌ Что-то пошло не так при генерации. Напиши мне — разберёмся и вернём Stars.",
            reply_markup=back_to_main()
        )


# ─── Запуск ──────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
