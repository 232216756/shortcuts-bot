# iPhone Shortcuts Bot

Telegram бот для создания iOS Shortcuts команд.

## Деплой на Render.com

### 1. Залей код на GitHub
- Создай новый репозиторий на github.com
- Загрузи все файлы (bot.py, requirements.txt, Procfile)

### 2. Задеплой на Render
- Зайди на render.com → New → Background Worker
- Подключи свой GitHub репозиторий
- В разделе Environment Variables добавь:
  - `BOT_TOKEN` = твой токен от BotFather
  - `ANTHROPIC_API_KEY` = твой ключ от console.anthropic.com

### 3. Включи оплату Stars
- Напиши @BotFather
- /mybots → выбери бота → Payments
- Включи Telegram Stars

### Готово!
Бот будет доступен по ссылке t.me/iphone_shortcuts_bot
