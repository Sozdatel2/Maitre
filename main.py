import os
import logging
import traceback
import asyncio
import nextcord
from nextcord import Interaction
from nextcord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("VERIFY_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Maitre")

STATUSES = [
    "смотрит за тикетами 📩",
    "играет в разгребание завалов 🧹",
    "слушает как энергетик булькает 🥤",
    "смотрит за входящими 🚪",
    "носится на 2x скорости 🐱💨",
    "завидует тому, как Lounge отдыхает 😤",
    "разгребает 100500 тикетов одновременно 😭",
    "паникует с того, как дедлайны подгорают 🔥",
]

class MaitreBot(commands.Bot):
    def __init__(self):
        intents = nextcord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="h.", intents=intents, help_command=None)

bot = MaitreBot()

_initialized = False

@tasks.loop(seconds=17)
async def rotate_status():
    """Каждые 17 секунд меняет статус бота."""
    text = STATUSES[rotate_status.current_loop % len(STATUSES)]

    try:
        activity = nextcord.CustomActivity(name=text)
        await bot.change_presence(activity=activity)
    except Exception as e:
        log.warning(f"⚠️ CustomActivity не сработал, fallback на watching: {e}")
        activity = nextcord.Activity(
            type=nextcord.ActivityType.watching,
            name=text,
        )
        await bot.change_presence(activity=activity)

@rotate_status.before_loop
async def before_rotate():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    global _initialized

    log.info(f"🎩 Maître на месте. Вошёл как {bot.user}")

    if not _initialized:
        _initialized = True

        for cog in ["cogs.verify", "cogs.tickets", "cogs.recruitment"]:
            try:
                bot.load_extension(cog)
                log.info(f"✅ Загружен ког: {cog}")
            except Exception as e:
                log.error(f"❌ Ког {cog} НЕ загружен: {type(e).__name__}: {e}")
                traceback.print_exc()

        try:
            if hasattr(bot, "sync_application_commands"):
                await bot.sync_application_commands()
            elif hasattr(bot, "sync_all_application_commands"):
                await bot.sync_all_application_commands()
            log.info("🔄 Слэш-команды синкнуты")
        except Exception as e:
            log.error(f"❌ Ошибка синка: {type(e).__name__}: {e}")

        rotate_status.start()
        log.info("🔄 Циклический статус запущен")

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ VERIFY_TOKEN не найден в .env")
    bot.run(TOKEN)