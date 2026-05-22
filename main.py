import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import calendar
import logging
import logging.handlers
from datetime import datetime
from dotenv import load_dotenv
from database import init_db, DB_PATH
import aiosqlite

load_dotenv()

# ── Logging setup ────────────────────────────────────────────────
def setup_logging() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Файлд бичих — өдөр бүр шинэ, 7 хоног хадгалах
    file_h = logging.handlers.TimedRotatingFileHandler(
        "logs/bot.log", when="midnight", interval=1,
        backupCount=7, encoding="utf-8",
    )
    file_h.setFormatter(fmt)
    # Консолд харуулах
    console_h = logging.StreamHandler()
    console_h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_h)
    root.addHandler(console_h)
    # discord.py-н дотоод debug мессежийг хаах
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    return logging.getLogger("TOP_Bot")

logger = setup_logging()

# ── Prison-aware CommandTree ─────────────────────────────────────
# /help болон /eruuljuuleh-г үргэлж зөвшөөрнө; бусад командуудыг
# prison_until > now байвал хориглоно.

ALLOWED_IN_PRISON = {"help", "eruuljuuleh"}

# Дүргүй хүн ашиглаж болох командууд
NO_CHAR_REQUIRED = {
    "register", "help",
    "profile", "top", "richlist", "balance",
    "serverinfo", "stats", "active",
    "givemoney", "releaseprison", "giverole", "removerole",
    "level_role_add",
    "eruuljuuleh", "prisonlist",
    "jobs", "courses", "rlb",
    # Bank (no char needed)
    "deposit", "withdraw", "bank",
    # Admin commands
    "adminsetage", "adminsetgender", "adminsetsexuality", "adminsetjob",
    "adminrevive", "adminkill", "adminsetbalance", "adminaddbalance",
    "adminsetlevel", "adminresetchar", "adminsetprison", "adminresetcooldown",
}

class PrisonTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cmd_name = interaction.command.name if interaction.command else None

        # Prison-д байхад зөвшөөрөгдсөн командууд
        if cmd_name in ALLOWED_IN_PRISON:
            return True

        # Guild байхгүй бол (DM) — зөвшөөрнө
        if not interaction.guild_id:
            return True

        # Admin эрхтэй хүнийг prison check-с чөлөөлнө
        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        if member and member.guild_permissions.administrator:
            return True

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT prison_until FROM users WHERE user_id=? AND guild_id=?",
                    (interaction.user.id, interaction.guild_id)
                )
                row = await cursor.fetchone()

            if row and row["prison_until"]:
                release = datetime.fromisoformat(row["prison_until"])
                now     = datetime.utcnow()
                if now < release:
                    remaining = release - now
                    mins = int(remaining.total_seconds() // 60)
                    secs = int(remaining.total_seconds() % 60)
                    release_ts = calendar.timegm(release.timetuple())

                    embed = discord.Embed(
                        title="🚔 Уучлаарай, та эрүүлжүүлэхэд орсон байна!",
                        description=(
                            f"Та хэтрүүлэн уусан тул TOP Bot-ын командуудыг\n"
                            f"хэрэглэх эрхгүй байна.\n\n"
                            f"⏳ Үлдсэн хугацаа: **{mins}м {secs}с**\n"
                            f"🕐 Суллагдах: <t:{release_ts}:R>\n\n"
                            f"**/eruuljuuleh** командаар шоронгийн статусаа харах боломжтой.\n"
                            f"**/help** командаар командуудыг харах боломжтой."
                        ),
                        color=0xFF4400
                    )
                    embed.set_footer(text="TOP Bot  •  Эрүүлжүүлэх систем")
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return False
                else:
                    # Хугацаа дууссан бол prison цэвэрлэх
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        reason_cur = await db.execute(
                            "SELECT prison_reason FROM users WHERE user_id=? AND guild_id=?",
                            (interaction.user.id, interaction.guild_id)
                        )
                        reason_row = await reason_cur.fetchone()
                        reason = reason_row["prison_reason"] if reason_row else None
                        # Тэнсэн: архиар шоронд орсон бол тэнсэн хэвээр байна
                        if reason != "alcohol":
                            await db.execute(
                                "UPDATE users SET prison_until=NULL, sogto_level=0, tension=0, prison_reason=NULL WHERE user_id=? AND guild_id=?",
                                (interaction.user.id, interaction.guild_id)
                            )
                        else:
                            await db.execute(
                                "UPDATE users SET prison_until=NULL, sogto_level=0 WHERE user_id=? AND guild_id=?",
                                (interaction.user.id, interaction.guild_id)
                            )
                        await db.commit()
        except Exception:
            pass

        # ── Character шалгалт ────────────────────────────────────
        if cmd_name not in NO_CHAR_REQUIRED:
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    cur = await db.execute(
                        "SELECT user_id FROM character_info WHERE user_id=? AND guild_id=?",
                        (interaction.user.id, interaction.guild_id)
                    )
                    has_char = await cur.fetchone()
                if not has_char:
                    await interaction.response.send_message(
                        "🎭 Эхлээд **`/register`** командаар дүр үүсгэнэ үү!\n"
                        "Дүр үүсгэхгүйгээр командуудыг ашиглах боломжгүй.",
                        ephemeral=True
                    )
                    return False
            except Exception:
                pass

        return True


# ── Bot setup ────────────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, tree_cls=PrisonTree)

@bot.event
async def on_ready():
    logger.info(f"{bot.user} онлайн боллоо!")
    logger.info(f"{len(bot.guilds)} серверт холбогдсон")
    logger.info(f"Tree дэх командын тоо: {len(bot.tree.get_commands())}")
    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info(f"{guild.name} серверт {len(synced)} команд sync хийгдлээ")
    except Exception as e:
        logger.error(f"Sync алдаа: {e}")

async def load_cogs():
    cogs = ["character", "economy", "levels", "games", "family", "stats", "roles", "substances", "help", "admin"]
    for cog in cogs:
        try:
            await bot.load_extension(f"cogs.{cog}")
            logger.info(f"{cog} cog ачааллаа")
        except Exception as e:
            logger.error(f"{cog} cog алдаа: {e}", exc_info=True)

async def main():
    async with bot:
        await init_db()
        await load_cogs()
        token = os.getenv("TOKEN")
        if not token:
            logger.critical("TOKEN олдонгүй! .env файлаа шалгана уу.")
            return
        await bot.start(token)

asyncio.run(main())
