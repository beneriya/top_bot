import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import asyncio
import calendar
from datetime import datetime, timedelta
from database import DB_PATH, get_user, update_balance

MAX_LEVEL   = 30
PRISON_MINS = 30

# ── Байдлын тайлбарууд ──────────────────────────────────────────
SOGTO_STATES = [
    (0,  "😐 Хэвийн, ердийн байдал"),
    (3,  "🙂 Бага зэрэг зовж эхэллээ"),
    (8,  "😄 Чөлөөтэй, хөгжилтэй"),
    (15, "😵 Толгой эргэж байна!"),
    (22, "🥴 Яривал буруу, алхвал унана"),
    (28, "💀 Үхээд өглөө бараг tsu2"),
]
MANS_STATES = [
    (0,  "😐 Хэвийн, ердийн байдал"),
    (3,  "😌 Бага зэрэг тайвшрав"),
    (8,  "🌫️ Толгой хөнгөрсөн мэт"),
    (15, "😵‍💫 Орчлон ертөнц эргэж байна"),
    (22, "🌀 Хий юм харагдаж эхэллээ..."),
    (28, "👁️ Нэг бурхан харагдаж байна"),
]

# ── Шоронгийн ранк ───────────────────────────────────────────────
PRISON_RANKS = [
    (20, "⛓️", "Шоронгийн хадаас"),
    (10, "💀", "Хулгар"),
    (5,  "😤", "Суугуул"),
    (1,  "🔰", "Шалбадай"),
    (0,  "✅", "Гэмт хэргийн бүртгэлгүй"),
]

def get_prison_rank(count: int) -> tuple[str, str]:
    """(emoji, rank_name) буцаана"""
    for threshold, emoji, name in PRISON_RANKS:
        if count >= threshold:
            return emoji, name
    return "✅", "Гэмт хэргийн бүртгэлгүй"

def get_state_text(level: int, states: list) -> str:
    text = states[0][1]
    for threshold, desc in states:
        if level >= threshold:
            text = desc
    return text

def make_bar(value: int, max_val: int, length: int = 12) -> str:
    filled = round((value / max_val) * length) if max_val else 0
    return f"`{'▰' * filled}{'▱' * (length - filled)}`"

def level_color(level: int) -> int:
    if level >= 28: return 0xFF0000
    if level >= 22: return 0xFF4400
    if level >= 15: return 0xFF8800
    if level >= 8:  return 0xFFCC00
    if level >= 3:  return 0xAAFF44
    return 0x44FF88

def prison_remaining(prison_until_str: str) -> timedelta | None:
    if not prison_until_str:
        return None
    diff = datetime.fromisoformat(prison_until_str) - datetime.utcnow()
    return diff if diff.total_seconds() > 0 else None



# ─────────────────────────────────────────────────────────────────────────────
#  ReleaseView — "Суллах" товч: хугацаа дуусвал хэрэглэгчийг чөлөөлнө
# ─────────────────────────────────────────────────────────────────────────────
class ReleaseView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, prison_until_str: str):
        super().__init__(timeout=None)
        self.user_id         = user_id
        self.guild_id        = guild_id
        self.prison_until_str = prison_until_str

    @discord.ui.button(label="\U0001f513 Суллах", style=discord.ButtonStyle.success)
    async def release_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("\u0422\u0430\u043d\u044b \u0442\u043e\u0432\u0447 \u0431\u0438\u0448!", ephemeral=True)
            return
        remaining = prison_remaining(self.prison_until_str)
        if remaining:
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            await interaction.response.send_message(
                f"\u23f3 \u04ae\u043b\u0434\u0441\u044d\u043d \u0445\u0443\u0433\u0430\u0446\u0430\u0430: **{mins}\u043c {secs}\u0441** \u0431\u0430\u0439\u043d\u0430, \u0434\u0430\u0445\u0438\u043d \u0445\u04af\u043b\u044d\u044d\u0440\u044d\u0435!",
                ephemeral=True
            )
            return
        # Time is up — clear prison
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET prison_until=NULL, sogto_level=0 WHERE user_id=? AND guild_id=?",
                (self.user_id, self.guild_id)
            )
            await db.commit()
        button.disabled = True
        button.label = "\u2705 \u0421\u0443\u043b\u043b\u0430\u0433\u0434\u043b\u0430\u0430"
        freed_embed = discord.Embed(
            title="\u2705  \u0421\u0443\u043b\u043b\u0430\u0433\u0434\u043b\u0430\u0430!",
            description="\u0422\u0430 \u044d\u0440\u04af\u04af\u043b\u0436\u04af\u04af\u043b\u044d\u0445\u044d\u044d\u0441 \u0447\u04e9\u043b\u04e9\u04e9\u043b\u04e9\u0433\u0434\u043b\u043e\u043e! \u0426\u0430\u0430\u0448\u0434\u0430\u0430 \u0430\u043d\u0445\u0430\u0430\u0440\u0430\u043b\u0436 \u043d\u04af\u04af\u0440\u044d\u044d.",
            color=0x00CC44
        )
        await interaction.response.edit_message(embed=freed_embed, view=self)

class Substances(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._recovery_task = None

    async def cog_load(self):
        self._recovery_task = asyncio.create_task(self._recover_loop())

    def cog_unload(self):
        if self._recovery_task:
            self._recovery_task.cancel()

    async def _recover_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(1800)
            try:
                now_iso = datetime.utcnow().isoformat()
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE users SET sogto_level = MAX(0, sogto_level - 1) WHERE sogto_level > 0"
                    )
                    await db.execute(
                        "UPDATE users SET mansuuralt_level = MAX(0, mansuuralt_level - 1) WHERE mansuuralt_level > 0"
                    )
                    # Auto-release expired prison sentences
                    await db.execute(
                        "UPDATE users SET prison_until=NULL, sogto_level=0 WHERE prison_until IS NOT NULL AND prison_until <= ?",
                        (now_iso,)
                    )
                    await db.commit()
            except Exception:
                pass

    # ────────────────────────────────────────────────────────────
    #  /drink
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="drink", description="Inventory-аас архи ууж согтох")
    @app_commands.describe(item_id="Архины item ID  (/shop alcohol)")
    async def drink(self, interaction: discord.Interaction, item_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT i.quantity, s.name, s.emoji, s.effect_value, s.item_type
                FROM inventory i JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND i.item_id=?
            """, (interaction.user.id, interaction.guild_id, item_id))
            inv_item = await cursor.fetchone()

        if not inv_item:
            await interaction.response.send_message(
                "❌ Тэр зүйл inventory-д байхгүй! `/shop alcohol` → `/buy`", ephemeral=True
            )
            return
        if inv_item["item_type"] != "alcohol":
            await interaction.response.send_message(
                "❌ Энэ архи биш!", ephemeral=True
            )
            return

        user    = await get_user(interaction.user.id, interaction.guild_id)
        current = user.get("sogto_level", 0)

        # ── MAX → PRISON ─────────────────────────────────────────
        if current >= MAX_LEVEL:
            release_at  = datetime.utcnow() + timedelta(minutes=PRISON_MINS)
            new_count   = user.get("prison_count", 0) + 1
            rank_e, rank_n = get_prison_rank(new_count)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET prison_until=?, prison_count=?, prison_reason='alcohol' WHERE user_id=? AND guild_id=?",
                    (release_at.isoformat(), new_count, interaction.user.id, interaction.guild_id)
                )
                await db.commit()

            embed = discord.Embed(
                title="🚔  Та эрүүлжүүлэхэд орлоо!",
                description=(
                    f"Та хэтрүүлэн уусан тул **{PRISON_MINS} минутын** хугацаанд\n"
                    f"TOP Bot-ын бүх командуудыг хэрэглэх эрхгүй боллоо.\n\n"
                    f"✅ **/help** — командуудын жагсаалт харах\n"
                    f"✅ **/eruuljuuleh** — шоронгийн статус харах\n\n"
                    f"⏱️  Суллагдах: <t:{calendar.timegm(release_at.timetuple())}:R>"
                ),
                color=0xFF4400
            )
            embed.add_field(
                name="🏴  Шоронгийн ранк",
                value=f"{rank_e} **{rank_n}** *(нийт {new_count} удаа)*",
                inline=False
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Шоронгоос эрт гарах боломжгүй — хугацаа дуустал хүлээнэ үү")
            await interaction.response.send_message(embed=embed)
            return

        # ── Ердийн уух ───────────────────────────────────────────
        new_level = min(MAX_LEVEL, current + inv_item["effect_value"])

        async with aiosqlite.connect(DB_PATH) as db:
            if inv_item["quantity"] <= 1:
                await db.execute(
                    "DELETE FROM inventory WHERE user_id=? AND guild_id=? AND item_id=?",
                    (interaction.user.id, interaction.guild_id, item_id)
                )
            else:
                await db.execute(
                    "UPDATE inventory SET quantity=quantity-1 WHERE user_id=? AND guild_id=? AND item_id=?",
                    (interaction.user.id, interaction.guild_id, item_id)
                )
            await db.execute(
                "UPDATE users SET sogto_level=? WHERE user_id=? AND guild_id=?",
                (new_level, interaction.user.id, interaction.guild_id)
            )
            await db.commit()

        bar   = make_bar(new_level, MAX_LEVEL)
        state = get_state_text(new_level, SOGTO_STATES)
        color = level_color(new_level)

        embed = discord.Embed(
            title=f"{inv_item['emoji']}  {inv_item['name']} уулаа!",
            color=color
        )
        embed.add_field(
            name="🍺  Согтолтын түвшин",
            value=f"{bar} **{new_level}/{MAX_LEVEL}**",
            inline=False
        )
        embed.add_field(name="Байдал", value=state, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        if new_level == MAX_LEVEL:
            embed.set_footer(text="⚠️  MAX! Дахин уувал 30 минутын турш эрүүлжүүлэхэд орно!")
        else:
            embed.set_footer(text="30 минут тутамд согтолт -1 автоматаар буурна")
        await interaction.response.send_message(embed=embed)

    # ────────────────────────────────────────────────────────────
    #  /smoke
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="smoke", description="Inventory-аас тамхи/вэйп хэрэглэх")
    @app_commands.describe(item_id="Тамхи эсвэл вэйпийн item ID")
    async def smoke(self, interaction: discord.Interaction, item_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT i.quantity, s.name, s.emoji, s.effect_value, s.item_type
                FROM inventory i JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND i.item_id=?
            """, (interaction.user.id, interaction.guild_id, item_id))
            inv_item = await cursor.fetchone()

        if not inv_item:
            await interaction.response.send_message("❌ Тэр зүйл inventory-д байхгүй!", ephemeral=True)
            return
        if inv_item["item_type"] not in ("cigarette", "vape"):
            await interaction.response.send_message("❌ Энэ тамхи эсвэл вэйп биш!", ephemeral=True)
            return

        user    = await get_user(interaction.user.id, interaction.guild_id)
        current = user.get("mansuuralt_level", 0)

        # ── MAX → 10% health tax ─────────────────────────────────
        if current >= MAX_LEVEL:
            penalty = max(1, int(user["balance"] * 0.10))
            await update_balance(interaction.user.id, interaction.guild_id, -penalty)

            embed = discord.Embed(
                title="🏥  Эрүүл мэндийн зардал суутгагдлаа!",
                description=(
                    f"Та эрүүл мэндээ хохироож байгаа тул\n"
                    f"эмчилгээнд чинь зориулж мөнгө суутгалаа.\n\n"
                    f"💸  **{penalty:,} ₮** балансаас хасагдлаа.\n"
                    f"💨  Мансуурал: {make_bar(MAX_LEVEL, MAX_LEVEL)} **{MAX_LEVEL}/{MAX_LEVEL}**"
                ),
                color=0xCC0000
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="30 минут тутамд мансуурал автоматаар буурна")
            await interaction.response.send_message(embed=embed)
            return

        # ── Ердийн хэрэглэх ──────────────────────────────────────
        new_level = min(MAX_LEVEL, current + inv_item["effect_value"])
        action    = "сорлоо" if inv_item["item_type"] == "vape" else "татлаа"

        async with aiosqlite.connect(DB_PATH) as db:
            if inv_item["quantity"] <= 1:
                await db.execute(
                    "DELETE FROM inventory WHERE user_id=? AND guild_id=? AND item_id=?",
                    (interaction.user.id, interaction.guild_id, item_id)
                )
            else:
                await db.execute(
                    "UPDATE inventory SET quantity=quantity-1 WHERE user_id=? AND guild_id=? AND item_id=?",
                    (interaction.user.id, interaction.guild_id, item_id)
                )
            await db.execute(
                "UPDATE users SET mansuuralt_level=? WHERE user_id=? AND guild_id=?",
                (new_level, interaction.user.id, interaction.guild_id)
            )
            await db.commit()

        bar   = make_bar(new_level, MAX_LEVEL)
        state = get_state_text(new_level, MANS_STATES)
        color = level_color(new_level)

        embed = discord.Embed(
            title=f"{inv_item['emoji']}  {inv_item['name']} {action}!",
            color=color
        )
        embed.add_field(
            name="💨  Мансуурлын түвшин",
            value=f"{bar} **{new_level}/{MAX_LEVEL}**",
            inline=False
        )
        embed.add_field(name="Байдал", value=state, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        if new_level == MAX_LEVEL:
            embed.set_footer(text="⚠️  MAX! Дахин хэрэглэвэл эрүүл мэндийн зардал суутгагдана!")
        else:
            embed.set_footer(text="30 минут тутамд мансуурал -1 автоматаар буурна")
        await interaction.response.send_message(embed=embed)

    # ────────────────────────────────────────────────────────────
    #  /mystate
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="mystate", description="Өөрийн согтолт болон мансуурлын түвшин харах")
    async def mystate(self, interaction: discord.Interaction):
        user  = await get_user(interaction.user.id, interaction.guild_id)
        sogto = user.get("sogto_level", 0)
        mans  = user.get("mansuuralt_level", 0)
        color = level_color(max(sogto, mans))

        embed = discord.Embed(
            title=f"🧠  {interaction.user.display_name}-н одоогийн байдал",
            color=color
        )
        embed.add_field(
            name="🍺  Согтолт",
            value=f"{make_bar(sogto, MAX_LEVEL)} **{sogto}/{MAX_LEVEL}**\n{get_state_text(sogto, SOGTO_STATES)}",
            inline=False
        )
        embed.add_field(
            name="💨  Мансуурал",
            value=f"{make_bar(mans, MAX_LEVEL)} **{mans}/{MAX_LEVEL}**\n{get_state_text(mans, MANS_STATES)}",
            inline=False
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="30 минут тутамд автоматаар -1 буурна  •  /drink /smoke нэмнэ")
        await interaction.response.send_message(embed=embed)

    # ────────────────────────────────────────────────────────────
    #  /eruuljuuleh  — статус харах (товч байхгүй)
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="eruuljuuleh", description="Шоронгийн статус болон ранк харах")
    async def eruuljuuleh(self, interaction: discord.Interaction):
        user         = await get_user(interaction.user.id, interaction.guild_id)
        prison_until = user.get("prison_until")
        count        = user.get("prison_count", 0)
        remaining    = prison_remaining(prison_until)
        rank_e, rank_n = get_prison_rank(count)

        if not remaining:
            embed = discord.Embed(
                title="✅  Та эрүүлжүүлэхэд байхгүй",
                color=0x00CC44
            )
            if count == 0:
                embed.description = "Та одоо хүртэл шоронд орж байгаагүй. Гэмт хэргийн бүртгэлгүй!"
            else:
                embed.description = f"Та одоо чөлөөтэй боловч гэмт хэргийн бүртгэлтэй."
            embed.add_field(
                name="🏴  Шоронгийн ранк",
                value=f"{rank_e} **{rank_n}** *(нийт {count} удаа шоронд орсон)*",
                inline=False
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # ── Шоронд байна ─────────────────────────────────────────
        release_at = datetime.fromisoformat(prison_until)
        release_ts = calendar.timegm(release_at.timetuple())
        mins = int(remaining.total_seconds() // 60)
        secs = int(remaining.total_seconds() % 60)
        elapsed = PRISON_MINS * 60 - remaining.total_seconds()
        prog_bar = make_bar(max(0, int(elapsed)), PRISON_MINS * 60)

        embed = discord.Embed(
            title="🚔  Та эрүүлжүүлэхэд байна",
            description=(
                f"Уучлаарай, та хэтрүүлэн уусан тул эрүүлжүүлэхэд орсон байна.\n\n"
                f"⏳  Үлдсэн хугацаа: **{mins}м {secs}с**\n"
                f"{prog_bar}\n"
                f"🕐  Суллагдах: <t:{release_ts}:R>"
            ),
            color=0xFF4400
        )
        embed.add_field(
            name="🏴  Шоронгийн ранк",
            value=f"{rank_e} **{rank_n}** *(нийт {count} удаа)*",
            inline=False
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="\u0425\u0443\u0433\u0430\u0446\u0430\u0430 \u0434\u0443\u0443\u0441\u0441\u0430\u043d \u0434\u0430\u0440\u0430\u0430 \"\U0001f513 \u0421\u0443\u043b\u043b\u0430\u0445\" \u0442\u043e\u0432\u0447\u0438\u0439\u0433 \u0434\u0430\u0440\u0430\u0430!")
        view = ReleaseView(interaction.user.id, interaction.guild_id, prison_until)
        await interaction.response.send_message(embed=embed, view=view)

    # ────────────────────────────────────────────────────────────
    #  /prisonlist  — одоо шоронд байгаа хүмүүсийн жагсаалт
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="prisonlist", description="Одоо эрүүлжүүлэхэд байгаа хүмүүсийн жагсаалт")
    async def prisonlist(self, interaction: discord.Interaction):
        now = datetime.utcnow().isoformat()

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT user_id, prison_until, prison_count
                FROM users
                WHERE guild_id=? AND prison_until IS NOT NULL AND prison_until > ?
                ORDER BY prison_count DESC
            """, (interaction.guild_id, now))
            rows = await cursor.fetchall()

        if not rows:
            embed = discord.Embed(
                title="🏛️  Эрүүлжүүлэх — Одоогийн байдал",
                description="✅ Одоо эрүүлжүүлэхэд хэн ч байхгүй байна!",
                color=0x00CC44
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(
            title=f"🚔  Эрүүлжүүлэхэд байгаа хүмүүс — {len(rows)} хүн",
            color=0xFF4400
        )

        lines = []
        for i, row in enumerate(rows, 1):
            member = interaction.guild.get_member(row["user_id"])
            name   = member.display_name if member else f"ID:{row['user_id']}"
            count  = row["prison_count"]
            rank_e, rank_n = get_prison_rank(count)

            release = datetime.fromisoformat(row["prison_until"])
            rem     = release - datetime.utcnow()
            mins    = int(rem.total_seconds() // 60)
            secs    = int(rem.total_seconds() % 60)
            ts      = calendar.timegm(release.timetuple())

            lines.append(
                f"**{i}.** {rank_e} **{name}** — {rank_n} *({count} удаа)*\n"
                f"　⏳ Гарах: <t:{ts}:R> *(үлдсэн {mins}м {secs}с)*"
            )

        embed.description = "\n\n".join(lines)
        embed.set_footer(text="Шоронгийн дотоод ранк: Шалбадай → Суугуул → Хулгар → Шоронгийн хадаас")
        await interaction.response.send_message(embed=embed)


    # ────────────────────────────────────────────────────────────
    #  /releaseprison  [Admin]
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="releaseprison", description="Хэрэглэгчийг эрүүлжүүлэхээс гаргах [Admin]")
    @app_commands.checks.has_permissions(administrator=True)
    async def releaseprison(self, interaction: discord.Interaction, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT prison_until, prison_count FROM users WHERE user_id=? AND guild_id=?",
                (member.id, interaction.guild_id)
            )
            row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message(
                f"❌ {member.display_name} бүртгэлгүй байна!", ephemeral=True
            )
            return

        remaining = prison_remaining(row["prison_until"])
        if not remaining:
            await interaction.response.send_message(
                f"ℹ️ {member.display_name} одоо эрүүлжүүлэхэд байхгүй байна.", ephemeral=True
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET prison_until=NULL, sogto_level=0 WHERE user_id=? AND guild_id=?",
                (member.id, interaction.guild_id)
            )
            await db.commit()

        embed = discord.Embed(
            title="🔓 Admin — Эрүүлжүүлэхээс гаргалаа",
            description=f"{member.mention} эрүүлжүүлэхээс чөлөөлөгдлөө.\n"
                        f"*(Нийт {row['prison_count']} удаа шоронд орсон бүртгэл хэвээр үлдэнэ)*",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @releaseprison.error
    async def releaseprison_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Зөвхөн Admin хэрэглэх боломжтой!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Substances(bot))
