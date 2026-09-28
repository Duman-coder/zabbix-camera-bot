import os
import logging
import asyncio
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ZABBIX_URL = os.getenv("ZABBIX_URL")
ZABBIX_USER = os.getenv("ZABBIX_USER")
ZABBIX_PASSWORD = os.getenv("ZABBIX_PASSWORD")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


def get_zabbix_auth_token():
    """Авторизация в Zabbix API по логину/паролю и получение сессионного токена"""
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {
            "username": ZABBIX_USER,
            "password": ZABBIX_PASSWORD
        },
        "id": 1
    }
    response = requests.post(ZABBIX_URL, json=payload, timeout=10)
    data = response.json()
    if "result" in data:
        return data["result"]
    else:
        raise Exception(f"Ошибка авторизации Zabbix: {data.get('error')}")


def get_cameras_status(query_text: str):
    """Поиск хостов в Zabbix по текстовому запросу"""
    auth_token = get_zabbix_auth_token()

    # Приводим запрос к верхнему регистру (например "ovn 1" -> "OVN.1" или "OVN.001")
    formatted_query = query_text.strip().upper().replace(" ", ".")

    payload = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {
            "search": {
                "name": formatted_query
            },
            "selectInterfaces": ["ip"],
            "selectTriggers": ["triggerid", "description", "value", "priority"],
            "output": ["hostid", "host", "name", "status"]
        },
        "auth": auth_token,
        "id": 2
    }

    response = requests.post(ZABBIX_URL, json=payload, timeout=10)
    data = response.json()
    hosts = data.get("result", [])

    if not hosts:
        return f"🔍 Камеры по запросу `{query_text}` не найдены."

    lines = [f"📊 **Результаты проверки ({query_text.upper()}):**\n"]

    for host in hosts:
        hostname = host.get("name") or host.get("host")
        ip = host["interfaces"][0]["ip"] if host.get("interfaces") else "N/A"

        # Проверяем триггеры с активным статусом проблемы (value == "1")
        triggers = host.get("triggers", [])
        active_problems = [t for t in triggers if t.get("value") == "1"]

        if active_problems:
            status_icon = "🔴"
            details = f"Проблема: {active_problems[0]['description']}"
        else:
            status_icon = "🟢"
            details = "Доступна (ОК)"

        lines.append(f"{status_icon} `{hostname}` ({ip}) — {details}")

    return "\n".join(lines)


@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "👋 Привет! Отправь мне название объекта или камеры для проверки.\n"
        "Например: `OVN.001` или `OVN 5`",
        parse_mode="Markdown"
    )


@dp.message()
async def query_handler(message: types.Message):
    await message.answer("🔍 Запрашиваю данные из Zabbix...")
    try:
        report = get_cameras_status(message.text)
        await message.answer(report, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка выполнения: {e}")
        await message.answer(f"⚠️ Ошибка при обращении к Zabbix: `{e}`", parse_mode="Markdown")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())