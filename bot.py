import os
import json
import logging
import plistlib
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

# Минимум Telegram Stars = 1. Потом поднимем.
STARS_PRICE = 1

# Токен платёжного провайдера для карт.
# Как получить: @BotFather → /mybots → твой бот → Payments → Stripe (TEST сначала)
# Вставь токен в переменную среды CARD_PROVIDER_TOKEN на Railway
CARD_PROVIDER_TOKEN = os.environ.get("CARD_PROVIDER_TOKEN", None)
CARD_PRICE_RUB = 1900  # копейки = 19 рублей

# ─── Шаблоны ────────────────────────────────────────────────────────────────

TEMPLATES = {
    "automation": {
        "label": "⏰ Автоматизации",
        "items": [
            {
                "id": "morning_routine",
                "name": "Утренний режим",
                "desc": "Яркость 80% и открыть приложение Погода",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.setbrightness",
                        "WFWorkflowActionParameters": {"WFBrightness": 0.8}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.openapp",
                        "WFWorkflowActionParameters": {"WFAppIdentifier": "com.apple.weather"}
                    }
                ]
            },
            {
                "id": "night_mode",
                "name": "Ночной режим",
                "desc": "Яркость 10% и громкость на минимум",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.setbrightness",
                        "WFWorkflowActionParameters": {"WFBrightness": 0.1}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.setvolume",
                        "WFWorkflowActionParameters": {"WFVolume": 0.0}
                    }
                ]
            },
            {
                "id": "flashlight_on",
                "name": "Фонарик на максимум",
                "desc": "Включить фонарик на полную яркость",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.setflashlight",
                        "WFWorkflowActionParameters": {
                            "WFFlashlightSetting": True,
                            "WFFlashlightLevel": 1.0
                        }
                    }
                ]
            },
        ]
    },
    "location": {
        "label": "📍 Геолокация",
        "items": [
            {
                "id": "copy_coordinates",
                "name": "Скопировать адрес",
                "desc": "Получить текущий адрес и скопировать в буфер обмена",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.getlocation",
                        "WFWorkflowActionParameters": {}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.setclipboard",
                        "WFWorkflowActionParameters": {}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
                        "WFWorkflowActionParameters": {
                            "WFNotificationActionTitle": "Готово!",
                            "WFNotificationActionBody": "Адрес скопирован в буфер"
                        }
                    }
                ]
            },
            {
                "id": "open_maps",
                "name": "Я здесь (открыть карту)",
                "desc": "Показать своё текущее местоположение на карте",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.getlocation",
                        "WFWorkflowActionParameters": {}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.showmaplink",
                        "WFWorkflowActionParameters": {}
                    }
                ]
            },
        ]
    },
    "text": {
        "label": "🌐 Текст и буфер",
        "items": [
            {
                "id": "clipboard_to_note",
                "name": "Буфер → Заметка",
                "desc": "Скопировал текст → нажал → создалась заметка в приложении Заметки",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
                        "WFWorkflowActionParameters": {}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.addnote",
                        "WFWorkflowActionParameters": {}
                    }
                ]
            },
            {
                "id": "search_google",
                "name": "Найти в Google",
                "desc": "Скопировал текст → нажал → открылся Google с поиском этого текста",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
                        "WFWorkflowActionParameters": {}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.openurl",
                        "WFWorkflowActionParameters": {}
                    }
                ]
            },
        ]
    },
    "quick": {
        "label": "🚀 Быстрые действия",
        "items": [
            {
                "id": "open_navigator",
                "name": "Открыть Яндекс.Навигатор",
                "desc": "Быстро открыть Яндекс Навигатор",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.openapp",
                        "WFWorkflowActionParameters": {"WFAppIdentifier": "ru.yandex.traffic"}
                    }
                ]
            },
            {
                "id": "silent_mode",
                "name": "Тихий режим",
                "desc": "Громкость 0 и яркость 30% одним нажатием",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.setvolume",
                        "WFWorkflowActionParameters": {"WFVolume": 0.0}
                    },
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.setbrightness",
                        "WFWorkflowActionParameters": {"WFBrightness": 0.3}
                    }
                ]
            },
            {
                "id": "open_telegram",
                "name": "Открыть Telegram",
                "desc": "Быстро открыть Telegram",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.openapp",
                        "WFWorkflowActionParameters": {"WFAppIdentifier": "ph.telegra.Telegraph"}
                    }
                ]
            },
        ]
    },
    "notification": {
        "label": "🔔 Напоминания",
        "items": [
            {
                "id": "water_reminder",
                "name": "Выпить воду",
                "desc": "Показать уведомление с напоминанием выпить воду прямо сейчас",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
                        "WFWorkflowActionParameters": {
                            "WFNotificationActionTitle": "💧 Время пить воду!",
                            "WFNotificationActionBody": "Выпей стакан воды прямо сейчас",
                            "WFNotificationActionSound": True
                        }
                    }
                ]
            },
            {
                "id": "timer_10",
                "name": "Таймер 10 минут",
                "desc": "Запустить таймер на 10 минут",
                "actions": [
                    {
                        "WFWorkflowActionIdentifier": "is.workflow.actions.timer.start",
                        "WFWorkflowActionParameters": {
                            "WFDuration": {
                                "Value": {"Unit": "min", "Value": 10},
                                "WFSerializationType": "WFQuantitySubstitution"
                            }
                        }
                    }
                ]
            },
        ]
    },
}

# ─── Промт для Claude ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты эксперт по iOS Shortcuts. Генерируй ТОЛЬКО валидный JSON для .shortcut файлов.

ПРАВИЛА:
1. Отвечай ТОЛЬКО JSON — никакого текста, никаких пояснений
2. Используй ТОЛЬКО эти проверенные action identifiers:
   - is.workflow.actions.setbrightness → WFWorkflowActionParameters: {"WFBrightness": 0.0-1.0}
   - is.workflow.actions.setvolume → {"WFVolume": 0.0-1.0}
   - is.workflow.actions.setflashlight → {"WFFlashlightSetting": true, "WFFlashlightLevel": 1.0}
   - is.workflow.actions.notification → {"WFNotificationActionTitle": "...", "WFNotificationActionBody": "..."}
   - is.workflow.actions.openapp → {"WFAppIdentifier": "bundle.id.here"}
   - is.workflow.actions.getclipboard → {}
   - is.workflow.actions.setclipboard → {}
   - is.workflow.actions.getlocation → {}
   - is.workflow.actions.showmaplink → {}
   - is.workflow.actions.openurl → {}
   - is.workflow.actions.timer.start → {"WFDuration": {"Value": {"Unit": "min", "Value": 10}, "WFSerializationType": "WFQuantitySubstitution"}}
   - is.workflow.actions.wait → {"WFDuration": {"Value": {"Unit": "sec", "Value": 5}, "WFSerializationType": "WFQuantitySubstitution"}}

3. Bundle ID популярных приложений:
   ph.telegra.Telegraph, net.whatsapp.WhatsApp, ru.yandex.traffic,
   com.google.Maps, com.apple.weather, com.apple.camera,
   com.apple.mobilenotes, com.apple.mobilesafari, com.apple.Music,
   com.spotify.client, com.vk.vkclient

4. НЕ придумывай action identifiers — только из списка выше

Формат ответа (строго):
{"name":"Название до 30 символов","description":"Что делает одним предложением","actions":[{"WFWorkflowActionIdentifier":"is.workflow.actions.XXX","WFWorkflowActionParameters":{}}]}"""


async def generate_shortcut(user_request: str) -> dict:
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Создай iOS Shortcut: {user_request}"}]
        )
        text = message.content[0].text.strip()

        # Чистим markdown если есть
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)

        if not result.get("name"):
            result["name"] = "Моя команда"
        if not result.get("description"):
            result["description"] = user_request[:100]
        if not isinstance(result.get("actions"), list):
            result["actions"] = []

        return result

    except Exception as e:
        logger.error(f"Generation error: {e}")
        return {"name": "Моя команда", "description": user_request[:100], "actions": []}


def build_shortcut_plist(shortcut_data: dict) -> bytes:
    plist_data = {
        "WFWorkflowActions": shortcut_data.get("actions", []),
        "WFWorkflowClientVersion": "2600.0.57",
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowIcon": {
            "WFWorkflowIconBackgroundColorData": b"\xff\x60\x00\x00",
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
        [InlineKeyboardButton("✨ Своя команда", callback_data="custom")],
        [InlineKeyboardButton("📦 Мои команды", callback_data="my_shortcuts")],
    ])


def templates_keyboard():
    buttons = [[InlineKeyboardButton(cat["label"], callback_data=f"cat__{cat_id}")]
               for cat_id, cat in TEMPLATES.items()]
    buttons.append([InlineKeyboardButton("« Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def category_keyboard(cat_id: str):
    buttons = [[InlineKeyboardButton(item["name"], callback_data=f"tpl__{cat_id}__{item['id']}")]
               for item in TEMPLATES[cat_id]["items"]]
    buttons.append([InlineKeyboardButton("« Назад", callback_data="templates")])
    return InlineKeyboardMarkup(buttons)


def payment_keyboard(is_custom=False, cat_id=None, item_id=None):
    buttons = []
    if is_custom:
        buttons.append([InlineKeyboardButton(f"⭐ Оплатить {STARS_PRICE} Star", callback_data="pay_stars")])
        if CARD_PROVIDER_TOKEN:
            buttons.append([InlineKeyboardButton("💳 Оплатить картой (~19 ₽)", callback_data="pay_card")])
    else:
        buttons.append([InlineKeyboardButton("✅ Скачать бесплатно", callback_data=f"send_tpl__{cat_id}__{item_id}")])
    buttons.append([InlineKeyboardButton("« Отмена", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def back_to_main():
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Главное меню", callback_data="main_menu")]])


# ─── Хэндлеры ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_info = f"⭐ {STARS_PRICE} Star"
    if CARD_PROVIDER_TOKEN:
        price_info += " или 💳 картой (~19 ₽)"
    await update.message.reply_text(
        "👋 Привет! Я создаю команды для iPhone (iOS Shortcuts).\n\n"
        "📋 *Шаблоны* — готовые команды, бесплатно\n"
        f"✨ *Своя команда* — опиши задачу, сгенерирую за {price_info}\n\n"
        "Выбирай:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "main_menu":
        await query.edit_message_text("Главное меню:", reply_markup=main_menu_keyboard())

    elif data == "templates":
        await query.edit_message_text(
            "📋 *Шаблоны*\n\nВсе бесплатно — выбери категорию:",
            parse_mode="Markdown",
            reply_markup=templates_keyboard()
        )

    elif data.startswith("cat__"):
        cat_id = data[5:]
        if cat_id in TEMPLATES:
            await query.edit_message_text(
                f"{TEMPLATES[cat_id]['label']}\n\nВыбери шаблон:",
                reply_markup=category_keyboard(cat_id)
            )

    elif data.startswith("tpl__"):
        _, cat_id, item_id = data.split("__", 2)
        if cat_id in TEMPLATES:
            item = next((i for i in TEMPLATES[cat_id]["items"] if i["id"] == item_id), None)
            if item:
                await query.edit_message_text(
                    f"📌 *{item['name']}*\n\n{item['desc']}",
                    parse_mode="Markdown",
                    reply_markup=payment_keyboard(cat_id=cat_id, item_id=item_id)
                )

    elif data.startswith("send_tpl__"):
        _, cat_id, item_id = data.split("__", 2)
        if cat_id in TEMPLATES:
            item = next((i for i in TEMPLATES[cat_id]["items"] if i["id"] == item_id), None)
            if item:
                file_bytes = build_shortcut_plist({
                    "name": item["name"],
                    "description": item["desc"],
                    "actions": item["actions"]
                })
                await query.edit_message_text(f"⬇️ Отправляю...", parse_mode="Markdown")
                await query.message.reply_document(
                    document=file_bytes,
                    filename=f"{item_id}.shortcut",
                    caption=(
                        f"✅ *{item['name']}*\n\n"
                        f"{item['desc']}\n\n"
                        "📱 *Установка:* нажми на файл → «Добавить команду»"
                    ),
                    parse_mode="Markdown",
                    reply_markup=back_to_main()
                )

    elif data == "custom":
        context.user_data["waiting_for_custom"] = True
        price_text = f"⭐ {STARS_PRICE} Telegram Star"
        if CARD_PROVIDER_TOKEN:
            price_text += " или 💳 картой (~19 ₽)"
        await query.edit_message_text(
            "✨ *Своя команда*\n\n"
            "Опиши что должна делать команда — простым языком.\n\n"
            "Примеры:\n"
            "• _Включить фонарик и поставить таймер на 10 минут_\n"
            "• _Открыть Telegram и Spotify одновременно_\n"
            "• _Яркость на минимум и тихий режим_\n\n"
            f"💰 Стоимость: {price_text}\n\n"
            "✍️ Напиши задачу:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Отмена", callback_data="main_menu")]])
        )

    elif data == "pay_stars":
        user_request = context.user_data.get("pending_request")
        if not user_request:
            await query.answer("Ошибка. Начни сначала.", show_alert=True)
            return
        await query.delete_message()
        await query.message.reply_invoice(
            title="✨ Генерация iOS Shortcut",
            description=user_request[:255],
            payload=f"stars_{query.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Генерация команды", STARS_PRICE)],
        )

    elif data == "pay_card":
        if not CARD_PROVIDER_TOKEN:
            await query.answer("Оплата картой временно недоступна", show_alert=True)
            return
        user_request = context.user_data.get("pending_request")
        if not user_request:
            await query.answer("Ошибка. Начни сначала.", show_alert=True)
            return
        await query.delete_message()
        await query.message.reply_invoice(
            title="✨ Генерация iOS Shortcut",
            description=user_request[:255],
            payload=f"card_{query.from_user.id}",
            provider_token=CARD_PROVIDER_TOKEN,
            currency="RUB",
            prices=[LabeledPrice("Генерация команды", CARD_PRICE_RUB)],
        )

    elif data == "my_shortcuts":
        history = context.user_data.get("history", [])
        if not history:
            await query.edit_message_text(
                "📦 *Мои команды*\n\nПока пусто — создай первую!",
                parse_mode="Markdown",
                reply_markup=back_to_main()
            )
        else:
            text = "📦 *Мои команды:*\n\n" + "\n".join(f"• {h}" for h in history[-10:])
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_main())


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_custom"):
        await update.message.reply_text("Используй меню 👇", reply_markup=main_menu_keyboard())
        return

    user_request = update.message.text
    context.user_data["waiting_for_custom"] = False
    context.user_data["pending_request"] = user_request

    price_text = f"⭐ {STARS_PRICE} Telegram Star"
    if CARD_PROVIDER_TOKEN:
        price_text += " или 💳 картой (~19 ₽)"

    await update.message.reply_text(
        f"📝 Задача:\n_{user_request}_\n\n💰 {price_text}\n\nВыбери способ оплаты:",
        parse_mode="Markdown",
        reply_markup=payment_keyboard(is_custom=True)
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_request = context.user_data.get("pending_request", "")
    if not user_request:
        await update.message.reply_text("❌ Не нашёл задачу. Попробуй ещё раз.", reply_markup=back_to_main())
        return

    msg = await update.message.reply_text("⚙️ Оплата получена! Генерирую команду...")
    shortcut_data = await generate_shortcut(user_request)
    file_bytes = build_shortcut_plist(shortcut_data)
    filename = shortcut_data.get("name", "shortcut").replace(" ", "_").replace("/", "_") + ".shortcut"

    history = context.user_data.get("history", [])
    history.append(shortcut_data.get("name", user_request[:50]))
    context.user_data["history"] = history[-20:]
    context.user_data.pop("pending_request", None)

    await msg.delete()
    await update.message.reply_document(
        document=file_bytes,
        filename=filename,
        caption=(
            f"✅ *{shortcut_data.get('name', 'Команда готова')}*\n\n"
            f"{shortcut_data.get('description', '')}\n\n"
            f"Действий в команде: {len(shortcut_data.get('actions', []))}\n\n"
            "📱 *Установка:* нажми на файл → «Добавить команду»"
        ),
        parse_mode="Markdown",
        reply_markup=back_to_main()
    )


# ─── Запуск ──────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set!")
        return

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
