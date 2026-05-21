import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import random
from datetime import date, datetime, timedelta

from database import DB_PATH, get_user, update_balance
from config import (
    HOURS_PER_GAME_YEAR,
    MALE_DEATH_MIN, MALE_DEATH_MAX, FEMALE_DEATH_MIN, FEMALE_DEATH_MAX,
    MILESTONES,
    CHILD_COST_PER_YEAR, CHILD_EARN_NO_COLLEGE, CHILD_EARN_COLLEGE, CHILD_COLLEGE_COST,
    CHILD_MAX_COUNT, CHILD_PROMPT_COOLDOWN_DAYS, CHILD_VOTE_EXPIRY_HOURS,
    BG_TASK_INTERVAL_MINUTES, WORK_COOLDOWN_MINUTES,
)

# ══════════════════════════════════════════════════════════════
#  JOBS — static configuration
#  gender: "male" | "female" | None (any)
#  course: None = no course required
# ══════════════════════════════════════════════════════════════
JOBS: dict = {
    # ── Мэргэжил шаардагдахгүй — ЭРЭГТЭЙ ─────────────────────
    "construction": {
        "name_mn": "Барилгийн туслах", "emoji": "🏗️",
        "salary": (20_000, 50_000),
        "course": None, "gender": "male",
        "messages": [
            "Тоосго давхарлаж", "Цемент цутгаж",
            "Барилгын шавар зуурч", "Хэрэм барьж", "Налуугийн ажил хийж",
        ],
    },
    "warehouse": {
        "name_mn": "Агуулхын ажилтан", "emoji": "📦",
        "salary": (2_500, 4_500),
        "course": None, "gender": "male",
        "messages": [
            "Хайрцаг зөөж", "Барааг эмхлэж",
            "Тооллого хийж", "Форкливтоор ажилласан", "Барааг баглаж",
        ],
    },
    "delivery": {
        "name_mn": "Тэрэгний зөөгч", "emoji": "🛒",
        "salary": (3_000, 4_500),
        "course": None, "gender": "male",
        "messages": [
            "Дэлгүүрт тэрэг зөөж", "Захиалга хүргэж",
            "Олон давхарт гараар зөөж", "Хурдан гүйж",
        ],
    },
    # ── Мэргэжил шаардагдахгүй — ЭМЭГТЭЙ ─────────────────────
    "artist": {
        "name_mn": "Зураач", "emoji": "🎨",
        "salary": (1_500, 7_000),
        "course": None, "gender": "female",
        "messages": [
            "Уран зургаа зарж", "Захиалгат зураг зурж",
            "Гудамжинд урлалаа гаргаж", "Онлайнд зургаа борлуулж",
        ],
    },
    "service": {
        "name_mn": "Үйлчилгээний ажилтан", "emoji": "💁",
        "salary": (2_000, 5_000),
        "course": None, "gender": "female",
        "messages": [
            "Зочдод үйлчилж", "Кассанд ажилласан",
            "Дэлгүүрийн лангуу цэвэрлэж", "Захиалга баталгаажуулж",
        ],
    },
    "operator": {
        "name_mn": "Оператор", "emoji": "📞",
        "salary": (2_500, 6_000),
        "course": None, "gender": "female",
        "messages": [
            "Утасны дуудлага хүлээн авч", "Захиалга бүртгэж",
            "Хэрэглэгчийн асуудал шийдэж", "Лайв чатаар хариулж",
        ],
    },
    # ── Курс шаардлагатай — ЯМА Ч ХҮЙС ──────────────────────
    "programmer": {
        "name_mn": "Програмист", "emoji": "💻",
        "salary": (20_000, 50_000),
        "course": "programming", "gender": None,
        "messages": [
            "Python код бичиж", "Алдаа засаж дахин засаж",
            "API хөгжүүлж", "Дата боловсруулж", "UI дизайн хийж",
        ],
    },
    "cook": {
        "name_mn": "Тогооч", "emoji": "👨‍🍳",
        "salary": (8_000, 18_000),
        "course": "cooking", "gender": None,
        "messages": [
            "Хоол бэлдэж", "Шинэ рецепт туршиж",
            "Ресторанд ажилласан", "Банкетын хоол хийж",
        ],
    },
    "driver": {
        "name_mn": "Жолооч", "emoji": "🚗",
        "salary": (6_000, 13_000),
        "course": "driving", "gender": None,
        "messages": [
            "Зорчигч тээвэрлэж", "Барааны машин жолоодож",
            "Taxi хийж", "Хот хоорондоо явж",
        ],
    },
    "doctor": {
        "name_mn": "Эмч", "emoji": "👨‍⚕️",
        "salary": (30_000, 70_000),
        "course": "medical", "gender": None,
        "messages": [
            "Өвчтөн үзэж", "Мэс засал хийж",
            "Эм бичиж", "Эмнэлэгт жижүүрлэж",
        ],
    },
    "teacher": {
        "name_mn": "Багш", "emoji": "👨‍🏫",
        "salary": (10_000, 25_000),
        "course": "teaching", "gender": None,
        "messages": [
            "Хичээл заадаг", "Шалгалт авч",
            "Хүүхдүүдэд туслаж", "Хичээлийн материал бэлдэж",
        ],
    },
    "lawyer": {
        "name_mn": "Хуульч", "emoji": "⚖️",
        "salary": (25_000, 60_000),
        "course": "law", "gender": None,
        "messages": [
            "Шүүхэд өмгөөлж", "Гэрээ боловсруулж",
            "Хуулийн зөвлөгөө өгч", "Баримт бичиг бэлдэж",
        ],
    },
    "accountant": {
        "name_mn": "Нягтлан бодогч", "emoji": "📊",
        "salary": (15_000, 35_000),
        "course": "accounting", "gender": None,
        "messages": [
            "Санхүүгийн тайлан гаргаж", "Татвар тооцоолж",
            "Дансыг нягтлаж", "Excel-д ажилласан",
        ],
    },
    "manager": {
        "name_mn": "Менежер", "emoji": "👔",
        "salary": (20_000, 45_000),
        "course": "business", "gender": None,
        "messages": [
            "Ажилтнуудыг удирдаж", "Уулзалт зохион байгуулж",
            "Стратеги боловсруулж", "Тайлан бэлдэж",
        ],
    },
    "engineer": {
        "name_mn": "Инженер", "emoji": "⚙️",
        "salary": (22_000, 50_000),
        "course": "engineering", "gender": None,
        "messages": [
            "Систем дизайн хийж", "Тоног төхөөрөмж засварлаж",
            "Техникийн зөвлөгөө өгч", "Барилгын зураг гаргаж",
        ],
    },
}

# ══════════════════════════════════════════════════════════════
#  COURSES — static configuration
# ══════════════════════════════════════════════════════════════
COURSES: dict = {
    "programming": {"name_mn": "Програмчлалын курс", "cost": 500_000,   "emoji": "💻", "unlocks": "programmer"},
    "cooking":     {"name_mn": "Тогоочийн курс",     "cost": 200_000,   "emoji": "🍳", "unlocks": "cook"},
    "driving":     {"name_mn": "Жолооны курс",        "cost": 150_000,   "emoji": "🚗", "unlocks": "driver"},
    "medical":     {"name_mn": "Эмчийн курс",         "cost": 1_500_000, "emoji": "🏥", "unlocks": "doctor"},
    "teaching":    {"name_mn": "Багшийн курс",        "cost": 300_000,   "emoji": "📚", "unlocks": "teacher"},
    "law":         {"name_mn": "Хуулийн курс",        "cost": 800_000,   "emoji": "⚖️", "unlocks": "lawyer"},
    "accounting":  {"name_mn": "Нягтлан бодох курс",  "cost": 400_000,   "emoji": "📊", "unlocks": "accountant"},
    "business":    {"name_mn": "Бизнесийн курс",      "cost": 600_000,   "emoji": "👔", "unlocks": "manager"},
    "engineering": {"name_mn": "Инженерийн курс",     "cost": 700_000,   "emoji": "⚙️", "unlocks": "engineer"},
}

GENDER_MN    = {"male": "👨 Эрэгтэй",        "female": "👩 Эмэгтэй"}
SEXUALITY_MN = {
    "straight": "💑 Straight",
    "gay":      "🏳️‍🌈 Геи / Лесбиян",
    "bisexual": "💜 Бисексуал",
}

# ── Virtual child names ──────────────────────────────────────────
CHILD_NAMES = {
    "male":   ["Болд","Бат","Ган","Эрдэнэ","Тулга","Баяр","Дорж","Мөнх","Тэмүүлэн","Нарандэлгэр",
               "Батбаяр","Гантулга","Мөнхбат","Тэмүүжин","Энхбат"],
    "female": ["Нарантуяа","Энхтуяа","Сарантуяа","Оюун","Дэлгэрмаа","Нандин","Туяа","Уянга",
               "Мөнхцэцэг","Анхтуяа","Хишигмаа","Энхзул","Номуун","Алтанцэцэг","Гэрэлмаа"],
}

# MILESTONES болон CHILD_* нь config.py-с import хийгдсэн (дээр)

# ══════════════════════════════════════════════════════════════
#  Helper functions (importable by other cogs)
# ══════════════════════════════════════════════════════════════
def calc_age(char) -> int:
    """
    Calculate in-game age.
    - New system (birth_time stored): 12 real hours = 1 game year
    - Legacy (birth_date stored):     1 real day    = 1 game year
    Accepts a character row dict or a birth_date string (legacy).\n"""
    if isinstance(char, dict):
        bt = char.get("birth_time")
        if bt:
            hours = (datetime.utcnow() - datetime.fromisoformat(bt)).total_seconds() / 3600
            return int(hours / HOURS_PER_GAME_YEAR)
        bd = char.get("birth_date")
    else:
        bd = str(char)
    if bd:
        return (date.today() - date.fromisoformat(bd)).days
    return 0


def calc_age_dt(birth_time_iso: str) -> int:
    """HOURS_PER_GAME_YEAR = 1 game year — for virtual children (always use birth_time)."""
    hours = (datetime.utcnow() - datetime.fromisoformat(birth_time_iso)).total_seconds() / 3600
    return int(hours / HOURS_PER_GAME_YEAR)


async def get_char(user_id: int, guild_id: int):
    """Return character_info row or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM character_info WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        )
        return await cur.fetchone()


async def get_completed_courses(user_id: int, guild_id: int) -> set:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT course_name FROM user_courses WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        )
        rows = await cur.fetchall()
    return {r["course_name"] for r in rows}


def can_marry_check(u_gender: str, u_sex: str, t_gender: str, t_sex: str) -> bool:
    """Return True if the two characters are romantically compatible."""
    def wants(gender, sex):
        if sex == "straight": return "female" if gender == "male" else "male"
        if sex == "gay":      return gender
        return None  # bisexual → any

    u_want = wants(u_gender, u_sex)
    t_want = wants(t_gender, t_sex)
    return (u_want is None or u_want == t_gender) and \
           (t_want is None or t_want == u_gender)


# ══════════════════════════════════════════════════════════════
#  Registration UI
# ══════════════════════════════════════════════════════════════
class AgeModal(discord.ui.Modal, title="🎂 Насаа оруулна уу"):
    age_input = discord.ui.TextInput(
        label="Эхлэх нас (5 – 60)",
        placeholder="жишээ: 18",
        min_length=1,
        max_length=2,
    )

    def __init__(self, gender: str, sexuality: str):
        super().__init__()
        self.char_gender    = gender
        self.char_sexuality = sexuality

    async def on_submit(self, interaction: discord.Interaction):
        try:
            age = int(self.age_input.value)
        except ValueError:
            await interaction.response.send_message("❌ Тоо оруулна уу!", ephemeral=True)
            return
        if not (5 <= age <= 60):
            await interaction.response.send_message("❌ Нас 5–60 байх ёстой!", ephemeral=True)
            return

        # birth_time: now - (age * 12 hours)  →  12h = 1 game year
        birth_time = (datetime.utcnow() - timedelta(hours=age * 12)).isoformat()
        death_age  = (
            random.randint(MALE_DEATH_MIN, MALE_DEATH_MAX) if self.char_gender == "male"
            else random.randint(FEMALE_DEATH_MIN, FEMALE_DEATH_MAX)
        )
        # Бүртгүүлсэн насаас доош байгаа хамгийн өндөр milestone-г тохируулна
        # → bg_task өнгөрсөн milestone-д дахиад DM илгээхгүй
        init_milestone = max((m for m in MILESTONES if m <= age), default=0)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT OR REPLACE INTO character_info
                       (user_id, guild_id, gender, sexuality, birth_date, birth_time,
                        death_age, job_id, last_milestone)
                   VALUES (?,?,?,?,NULL,?,?,NULL,?)""",
                (
                    interaction.user.id, interaction.guild_id,
                    self.char_gender, self.char_sexuality,
                    birth_time, death_age, init_milestone,
                ),
            )
            await db.commit()

        embed = discord.Embed(
            title="🎭 Дүр бүртгэгдлээ!",
            description=(
                f"**{interaction.user.display_name}**, тавтай морил! 🎉\n"
                f"Таны дүр амжилттай үүслээ."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(name="⚧ Хүйс",          value=GENDER_MN[self.char_gender],       inline=True)
        embed.add_field(name="❤️ Чиг баримжаа",  value=SEXUALITY_MN[self.char_sexuality], inline=True)
        embed.add_field(name="🎂 Нас",            value=f"{age} нас",                      inline=True)
        embed.add_field(name="⌛ Наслах хугацаа", value=f"хүртэл **{death_age}** нас",    inline=True)
        embed.set_footer(text="➡️  /setjob командаар ажил сонгоно уу!")
        await interaction.response.send_message(embed=embed)


class RegisterView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.sel_gender    = None
        self.sel_sexuality = None

    def _build_embed(self) -> discord.Embed:
        gender_val    = GENDER_MN.get(self.sel_gender, "—") if self.sel_gender else "❓ Сонгоогүй"
        sexuality_val = SEXUALITY_MN.get(self.sel_sexuality, "—") if self.sel_sexuality else "❓ Сонгоогүй"
        embed = discord.Embed(
            title="🎭 Дүр үүсгэх",
            description=(
                "Хүйс болон чиг баримжаагаа сонгоод **Үргэлжлүүлэх** дарна уу.\n"
                "Дараа нь насаа оруулна. *(5–60)*"
            ),
            color=0x5865F2,
        )
        embed.add_field(name="⚧ Хүйс",          value=gender_val,    inline=True)
        embed.add_field(name="❤️ Чиг баримжаа",  value=sexuality_val, inline=True)
        return embed

    @discord.ui.select(
        placeholder="⚧ Хүйсээ сонгоно уу...",
        options=[
            discord.SelectOption(label="Эрэгтэй", value="male",   emoji="👨"),
            discord.SelectOption(label="Эмэгтэй", value="female", emoji="👩"),
        ],
        row=0,
    )
    async def gender_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.sel_gender = select.values[0]
        self.confirm_btn.disabled = not (self.sel_gender and self.sel_sexuality)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.select(
        placeholder="❤️ Чиг баримжаагаа сонгоно уу...",
        options=[
            discord.SelectOption(
                label="Straight", value="straight", emoji="💑",
                description="Эсрэг хүйсийг татдаг",
            ),
            discord.SelectOption(
                label="Геи / Лесбиян", value="gay", emoji="🏳️‍🌈",
                description="Ижил хүйсийг татдаг",
            ),
            discord.SelectOption(
                label="Бисексуал", value="bisexual", emoji="💜",
                description="Хоёр хүйсийг татдаг",
            ),
        ],
        row=1,
    )
    async def sexuality_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.sel_sexuality = select.values[0]
        self.confirm_btn.disabled = not (self.sel_gender and self.sel_sexuality)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(
        label="Үргэлжлүүлэх ➡️",
        style=discord.ButtonStyle.primary,
        disabled=True,
        row=2,
    )
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AgeModal(self.sel_gender, self.sel_sexuality)
        )


# ══════════════════════════════════════════════════════════════
#  Autocomplete helpers
# ══════════════════════════════════════════════════════════════
async def _job_autocomplete(interaction: discord.Interaction, current: str):
    char = await get_char(interaction.user.id, interaction.guild_id)
    if not char:
        return []
    age       = calc_age(dict(char))
    completed = await get_completed_courses(interaction.user.id, interaction.guild_id)
    choices   = []
    for jid, jdata in JOBS.items():
        if jdata["gender"] and jdata["gender"] != char["gender"]:
            continue
        if age < 16:
            continue
        label = f"{jdata['emoji']} {jdata['name_mn']}"
        if jdata["course"] and jdata["course"] not in completed:
            label += "  🔒"
        if current.lower() in jid or current.lower() in jdata["name_mn"].lower():
            choices.append(app_commands.Choice(name=label[:100], value=jid))
    return choices[:25]


async def _course_autocomplete(interaction: discord.Interaction, current: str):
    completed = await get_completed_courses(interaction.user.id, interaction.guild_id)
    choices   = []
    for cname, cdata in COURSES.items():
        if cname in completed:
            continue
        label = f"{cdata['emoji']} {cdata['name_mn']}  —  {cdata['cost']:,} ₮"
        if current.lower() in cname or current.lower() in cdata["name_mn"].lower():
            choices.append(app_commands.Choice(name=label[:100], value=cname))
    return choices[:25]


# ══════════════════════════════════════════════════════════════
#  Child vote View  (sent via DM when couple gets the prompt)
# ══════════════════════════════════════════════════════════════
class ChildVoteView(discord.ui.View):
    def __init__(self, vote_id: int, p1_id: int, p2_id: int, guild_id: int):
        super().__init__(timeout=86_400)   # 24 hours
        self.vote_id  = vote_id
        self.p1_id    = p1_id
        self.p2_id    = p2_id
        self.guild_id = guild_id

    async def _vote(self, interaction: discord.Interaction, yes: bool):
        uid = interaction.user.id
        if uid == self.p1_id:
            col = "p1_vote"
        elif uid == self.p2_id:
            col = "p2_vote"
        else:
            await interaction.response.send_message("❌ Энэ санал танд хамааралгүй!", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if not yes:
                await db.execute("DELETE FROM child_votes WHERE vote_id=?", (self.vote_id,))
                await db.commit()
                await interaction.response.edit_message(content="❌ Хүүхэд төрүүлэхгүй болохоор шийдлээ.", embed=None, view=None)
                return

            await db.execute(f"UPDATE child_votes SET {col}=1 WHERE vote_id=?", (self.vote_id,))
            await db.commit()

            cur = await db.execute("SELECT * FROM child_votes WHERE vote_id=?", (self.vote_id,))
            row = await cur.fetchone()
            if not row:
                await interaction.response.edit_message(content="ℹ️ Санал хүчингүй болсон байна.", embed=None, view=None)
                return

            if row["p1_vote"] == 1 and row["p2_vote"] == 1:
                # Both agreed → create virtual child!
                gender = random.choice(["male", "female"])
                name   = random.choice(CHILD_NAMES[gender])
                birth_time = datetime.utcnow().isoformat()
                p1, p2 = (self.p1_id, self.p2_id) if self.p1_id < self.p2_id else (self.p2_id, self.p1_id)
                await db.execute(
                    "INSERT INTO virtual_children (guild_id,parent1_id,parent2_id,name,gender,birth_time,college,custodian_id) VALUES (?,?,?,?,?,?,0,NULL)",
                    (self.guild_id, p1, p2, name, gender, birth_time),
                )
                await db.execute("DELETE FROM child_votes WHERE vote_id=?", (self.vote_id,))
                await db.commit()
                self.stop()

                gender_mn = "хүү" if gender == "male" else "охин"
                for parent_id in [self.p1_id, self.p2_id]:
                    try:
                        user = await interaction.client.fetch_user(parent_id)
                        embed = discord.Embed(
                            title=f"👶 {name} ертөнцэд мэндэллээ!",
                            description=f"Таны **{name}** ({gender_mn}) гэр бүлд нэмэгдлээ! 🎉",
                            color=discord.Color.pink(),
                        )
                        await user.send(embed=embed)
                    except Exception:
                        pass

                await interaction.response.edit_message(content=f"👶 **{name}** ({gender_mn}) мэндэллээ!", embed=None, view=None)
            else:
                await interaction.response.edit_message(content="✅ Таны санал бүртгэгдлээ. Хань тань ч хариулахыг хүлээж байна.", embed=None, view=None)

    @discord.ui.button(label="Тийм 👶", style=discord.ButtonStyle.success)
    async def yes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, True)

    @discord.ui.button(label="Үгүй ❌", style=discord.ButtonStyle.danger)
    async def no_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, False)


# ══════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════
class Character(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bg_task.start()

    async def cog_unload(self):
        self.bg_task.cancel()

    # ── Background task ────────────────────────────────────────
    @tasks.loop(minutes=BG_TASK_INTERVAL_MINUTES)
    async def bg_task(self):
        """Handles age milestone DMs, child prompts, and expired vote cleanup."""
        now = datetime.utcnow()
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row

                # 0. Death notifications & inheritance
                cur0 = await db.execute("SELECT * FROM character_info WHERE death_notified=0")
                all_chars = await cur0.fetchall()
                for char in all_chars:
                    char = dict(char)
                    age  = calc_age(char)
                    if age < char.get("death_age", 999):
                        continue
                    uid, gid = char["user_id"], char["guild_id"]

                    # Get balance
                    bal_row = await (await db.execute(
                        "SELECT balance FROM users WHERE user_id=? AND guild_id=?", (uid, gid)
                    )).fetchone()
                    balance = bal_row["balance"] if bal_row else 0
                    inherit_pool = int(balance * 0.50)

                    # Find family: spouse + adopted children
                    fam_row = await (await db.execute(
                        "SELECT spouse_id FROM family WHERE user_id=? AND guild_id=?", (uid, gid)
                    )).fetchone()
                    family_ids = []
                    if fam_row and fam_row["spouse_id"]:
                        family_ids.append(fam_row["spouse_id"])
                    adopted = await (await db.execute(
                        "SELECT user_id FROM family WHERE parent_id=? AND guild_id=?", (uid, gid)
                    )).fetchall()
                    family_ids += [r["user_id"] for r in adopted]
                    family_ids = list(dict.fromkeys(family_ids))

                    # Virtual children count
                    vc_row = await (await db.execute(
                        "SELECT COUNT(*) AS cnt FROM virtual_children WHERE (parent1_id=? OR parent2_id=?) AND guild_id=?",
                        (uid, uid, gid)
                    )).fetchone()
                    vc_count = vc_row["cnt"] if vc_row else 0

                    # Distribute 50% inheritance to real family members
                    if family_ids and inherit_pool > 0:
                        share = inherit_pool // len(family_ids)
                        for fid in family_ids:
                            await db.execute(
                                "UPDATE users SET balance=MIN(1000000000,balance+?) WHERE user_id=? AND guild_id=?",
                                (share, fid, gid)
                            )

                    # Mark notified before sending DMs
                    await db.execute(
                        "UPDATE character_info SET death_notified=1 WHERE user_id=? AND guild_id=?",
                        (uid, gid)
                    )
                    await db.commit()

                    # DM the deceased
                    try:
                        deceased = await self.bot.fetch_user(uid)
                        embed_d = discord.Embed(
                            title="🪶 Таны дүр нас барлаа",
                            description=(
                                f"Таны дүр **{char['death_age']} насандаа** нас барлаа.\n"
                                + (
                                    f"💰 Нийт хөрөнгийн 50% ({inherit_pool:,} ₮) гэр бүлд үлдлээ.\n"
                                    if family_ids and inherit_pool > 0 else ""
                                )
                                + "`/register` командаар шинэ дүр үүсгэнэ үү."
                            ),
                            color=0x555555,
                        )
                        await deceased.send(embed=embed_d)
                    except Exception:
                        pass

                    # DM family members
                    if family_ids:
                        share = (inherit_pool // len(family_ids)) if inherit_pool > 0 else 0
                        for fid in family_ids:
                            try:
                                fmember = await self.bot.fetch_user(fid)
                                vc_txt = f"\n👶 Виртуал хүүхэд: **{vc_count}**" if vc_count else ""
                                money_txt = f"\n💰 Өв хөрөнгөөс **{share:,} ₮** таны дансанд орлоо." if share > 0 else ""
                                embed_f = discord.Embed(
                                    title="🪶 Гэр бүлийн гишүүн таалал төгсөв",
                                    description=(
                                        f"Таны гэр бүлийн нэг нь **{char['death_age']} насандаа** нас барлаа."
                                        + money_txt + vc_txt
                                    ),
                                    color=0x555555,
                                )
                                await fmember.send(embed=embed_f)
                            except Exception:
                                pass

                # 1. Age milestone notifications
                cur = await db.execute("SELECT * FROM character_info")
                chars = await cur.fetchall()
                for char in chars:
                    char = dict(char)
                    age = calc_age(char)
                    if age >= char.get("death_age", 999):
                        continue
                    last_ms = char.get("last_milestone") or 0
                    for ms in MILESTONES:
                        if age >= ms > last_ms:
                            try:
                                user = await self.bot.fetch_user(char["user_id"])
                                embed = discord.Embed(
                                    title=f"🎂 Тавтай мэндэлсэн өдрийн мэнд!",
                                    description=(
                                        f"**{user.display_name}**, таны **{ms}-р** төрсөн өдрийн мэнд хүргэе! 🎉🎊\n"
                                        f"Та тоглоомын ертөнцөд **{ms} настай** боллоо!"
                                    ),
                                    color=0xFF69B4,
                                )
                                milestones_left = [m for m in MILESTONES if m > ms]
                                if milestones_left:
                                    embed.set_footer(text=f"Дараагийн тэмдэглэлт нас: {milestones_left[0]} 🎂")
                                await user.send(embed=embed)
                            except Exception:
                                pass
                            await db.execute(
                                "UPDATE character_info SET last_milestone=? WHERE user_id=? AND guild_id=?",
                                (ms, char["user_id"], char["guild_id"]),
                            )
                            break

                # 2. Married couple child prompts
                cur2 = await db.execute("""
                    SELECT f.user_id AS p1, f.spouse_id AS p2, f.guild_id, f.last_child_prompt
                    FROM family f
                    WHERE f.spouse_id IS NOT NULL AND f.user_id < f.spouse_id
                """)
                couples = await cur2.fetchall()
                for couple in couples:
                    p1, p2, guild_id = couple["p1"], couple["p2"], couple["guild_id"]

                    # Skip if pending vote exists
                    cur_v = await db.execute(
                        "SELECT vote_id FROM child_votes WHERE parent1_id=? AND parent2_id=? AND guild_id=?",
                        (p1, p2, guild_id),
                    )
                    if await cur_v.fetchone():
                        continue

                    # Skip if max children reached
                    cur_c = await db.execute(
                        "SELECT COUNT(*) AS cnt FROM virtual_children WHERE guild_id=? AND parent1_id=? AND parent2_id=?",
                        (guild_id, p1, p2),
                    )
                    cnt = (await cur_c.fetchone())["cnt"]
                    if cnt >= CHILD_MAX_COUNT:
                        continue

                    # Check cooldown (CHILD_PROMPT_COOLDOWN_DAYS бодит хоног)
                    lcp = couple["last_child_prompt"]
                    if lcp:
                        elapsed = (now - datetime.fromisoformat(lcp)).total_seconds()
                        if elapsed < CHILD_PROMPT_COOLDOWN_DAYS * 86_400:
                            continue

                    # Create vote record
                    await db.execute(
                        "INSERT INTO child_votes (guild_id,parent1_id,parent2_id,p1_vote,p2_vote,created_at) VALUES (?,?,?,NULL,NULL,?)",
                        (guild_id, p1, p2, now.isoformat()),
                    )
                    await db.commit()
                    cur_new = await db.execute(
                        "SELECT vote_id FROM child_votes WHERE parent1_id=? AND parent2_id=? AND guild_id=? ORDER BY vote_id DESC LIMIT 1",
                        (p1, p2, guild_id),
                    )
                    vote_row = await cur_new.fetchone()
                    if not vote_row:
                        continue
                    vote_id = vote_row["vote_id"]

                    # Update last_child_prompt for both family rows
                    for pid in [p1, p2]:
                        await db.execute(
                            "UPDATE family SET last_child_prompt=? WHERE user_id=? AND guild_id=?",
                            (now.isoformat(), pid, guild_id),
                        )
                    await db.commit()

                    # DM both parents
                    embed_cp = discord.Embed(
                        title="👶 Хүүхэд төрүүлэх үү?",
                        description=(
                            "Та болон хань тань хүүхэдтэй болмоор байна уу?\n"
                            "Хоёулаа **Тийм** дарвал хүүхэд мэндэлнэ!"
                        ),
                        color=discord.Color.pink(),
                    )
                    for uid in [p1, p2]:
                        try:
                            u = await self.bot.fetch_user(uid)
                            await u.send(embed=embed_cp, view=ChildVoteView(vote_id, p1, p2, guild_id))
                        except Exception:
                            pass

                # 3. Clean up expired votes (> 24h)
                await db.execute(
                    "DELETE FROM child_votes WHERE created_at < ?",
                    ((now - timedelta(hours=CHILD_VOTE_EXPIRY_HOURS)).isoformat(),),
                )
                await db.commit()

        except Exception as e:
            import logging
            logging.getLogger("TOP_Bot").error(f"bg_task алдаа: {e}", exc_info=True)

    @bg_task.before_loop
    async def before_bg_task(self):
        await self.bot.wait_until_ready()

    # ── /register ─────────────────────────────────────────────
    @app_commands.command(name="register", description="Дүр үүсгэж тоглоомыг эхлүүлэх")
    async def register(self, interaction: discord.Interaction):
        view = RegisterView()
        await interaction.response.send_message(embed=view._build_embed(), view=view, ephemeral=True)

    # ── /mychar ───────────────────────────────────────────────
    @app_commands.command(name="mychar", description="Өөрийн дүрийн мэдээлэл харах")
    async def mychar(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        char   = await get_char(target.id, interaction.guild_id)

        if not char:
            msg = ("🎭 Дүр үүсгээгүй байна!"
                   if target == interaction.user
                   else f"🎭 **{target.display_name}** дүр үүсгээгүй байна!")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        age       = calc_age(dict(char))
        completed = await get_completed_courses(target.id, interaction.guild_id)

        # Death check
        if age >= char["death_age"]:
            embed = discord.Embed(
                title="🪦 Дүр нас барсан",
                description=(
                    f"**{target.display_name}**-н дүр **{char['death_age']} насандаа** нас барлаа.\n"
                    f"`/register` командаар шинэ дүр үүсгэнэ үү."
                ),
                color=0x555555,
            )
            await interaction.response.send_message(embed=embed)
            return

        job_txt = "Ажилгүй"
        if char["job_id"] and char["job_id"] in JOBS:
            j = JOBS[char["job_id"]]
            job_txt = f"{j['emoji']} {j['name_mn']}"

        course_txt = "Байхгүй"
        if completed:
            lines = []
            for cn in completed:
                if cn in COURSES:
                    c = COURSES[cn]
                    lines.append(f"{c['emoji']} {c['name_mn']}")
            course_txt = "\n".join(lines) if lines else "Байхгүй"

        embed = discord.Embed(
            title=f"🎭 {target.display_name}-н дүр",
            color=0x5865F2,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="⚧ Хүйс",           value=GENDER_MN.get(char["gender"], char["gender"]),       inline=True)
        embed.add_field(name="❤️ Чиг баримжаа",   value=SEXUALITY_MN.get(char["sexuality"], char["sexuality"]), inline=True)
        embed.add_field(name="🎂 Нас",             value=f"**{age}** нас",                                    inline=True)
        embed.add_field(name="💼 Ажил",            value=job_txt,                                             inline=True)
        embed.add_field(name="⌛ Наслах хязгаар",  value=f"**{char['death_age']}** нас",                     inline=True)
        embed.add_field(name="📚 Курс",            value=course_txt,                                          inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /jobs ─────────────────────────────────────────────────
    @app_commands.command(name="jobs", description="Бүх ажлын жагсаалт болон шаардлагыг харах")
    async def jobs(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            char      = await get_char(interaction.user.id, interaction.guild_id)
            completed = await get_completed_courses(interaction.user.id, interaction.guild_id) if char else set()

            free_male   = []
            free_female = []
            course_jobs = []

            for jid, jdata in JOBS.items():
                sal_min, sal_max = jdata["salary"]
                line = (
                    f"{jdata['emoji']} **{jdata['name_mn']}**\n"
                    f"   💰 {sal_min:,} – {sal_max:,} ₮"
                )
                if jdata["course"]:
                    cd     = COURSES[jdata["course"]]
                    owned  = jdata["course"] in completed
                    status = "✅ Суралцсан" if owned else f"🔒 {cd['name_mn']} ({cd['cost']:,} ₮)"
                    course_jobs.append(f"{line}\n   {status}")
                elif jdata["gender"] == "male":
                    free_male.append(line)
                else:
                    free_female.append(line)

            embed = discord.Embed(
                title="💼 Ажлын жагсаалт",
                description="Курс шаардлагатай ажлыг суралцсаны дараа `/setjob` -оор сонгоно.",
                color=0x5865F2,
            )
            if free_male:
                embed.add_field(name="👨 Эрэгтэй (шаардлагагүй)",  value="\n\n".join(free_male),   inline=False)
            if free_female:
                embed.add_field(name="👩 Эмэгтэй (шаардлагагүй)", value="\n\n".join(free_female), inline=False)
            if course_jobs:
                embed.add_field(name="🎓 Мэргэжлийн ажлууд",      value="\n\n".join(course_jobs), inline=False)

            if not char:
                embed.set_footer(text="⚠️  /register командаар дүр үүсгэснийхээ дараа ажил сонгоно уу.")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Алдаа гарлаа: `{e}`", ephemeral=True)

    # ── /setjob ───────────────────────────────────────────────
    @app_commands.command(name="setjob", description="Ажлаа сонгох")
    @app_commands.describe(job="Ажлын нэр — жагсаалтаас сонгоно уу")
    @app_commands.autocomplete(job=_job_autocomplete)
    async def setjob(self, interaction: discord.Interaction, job: str):
        uid, gid = interaction.user.id, interaction.guild_id
        char = await get_char(uid, gid)
        if not char:
            await interaction.response.send_message(
                "🎭 Эхлээд `/register` командаар дүр үүсгэнэ үү!", ephemeral=True
            )
            return

        # ── Нас барсан эсэх ──────────────────────────────────────
        age = calc_age(dict(char))
        if age >= char["death_age"]:
            await interaction.response.send_message(
                "💀 Таны дүр нас барсан! `/register` командаар шинэ дүр үүсгэнэ үү.", ephemeral=True
            )
            return
        if age < 16:
            await interaction.response.send_message(
                f"🚫 Та **{age} настай** байна. 16 наснаас ажилладаг!", ephemeral=True
            )
            return

        # ── Ажил байгаа эсэх ─────────────────────────────────────
        if job not in JOBS:
            await interaction.response.send_message("❌ Тийм ажил байхгүй!", ephemeral=True)
            return

        jdata = JOBS[job]

        # ── Хүйсийн шаардлага ────────────────────────────────────
        if jdata["gender"] and jdata["gender"] != char["gender"]:
            gender_txt = "эрэгтэй" if jdata["gender"] == "male" else "эмэгтэй"
            await interaction.response.send_message(
                f"❌ **{jdata['name_mn']}** зөвхөн {gender_txt}чүүдэд зориулагдсан!", ephemeral=True
            )
            return

        # ── Курсийн шаардлага ─────────────────────────────────────
        if jdata["course"]:
            completed = await get_completed_courses(uid, gid)
            if jdata["course"] not in completed:
                cd = COURSES[jdata["course"]]
                await interaction.response.send_message(
                    f"🔒 **{jdata['name_mn']}** ажил хийхийн тулд "
                    f"**{cd['name_mn']}** ({cd['cost']:,} ₮) суралцах шаардлагатай!\n"
                    f"`/enroll {jdata['course']}` командаар элсэнэ үү.",
                    ephemeral=True,
                )
                return

        # ── Аль хэдийн энэ ажилтай бол ───────────────────────────
        now = datetime.utcnow()
        if char["job_id"] == job:
            # last_setjob шалгаж үлдсэн хугацааг харуулах
            cd_txt = ""
            ls = char["last_setjob"] if hasattr(char, "__getitem__") else None
            try:
                ls = char["last_setjob"]
            except Exception:
                ls = None
            if ls:
                rem = timedelta(minutes=WORK_COOLDOWN_MINUTES) - (now - datetime.fromisoformat(ls))
                if rem.total_seconds() > 0:
                    m, s = int(rem.total_seconds() // 60), int(rem.total_seconds() % 60)
                    cd_txt = f"\n⏳ Ажил солих боломжтой болох хүртэл: **{m}м {s}с**"
            await interaction.response.send_message(
                f"{jdata['emoji']} Та аль хэдийн **{jdata['name_mn']}**-аар ажиллаж байна!{cd_txt}",
                ephemeral=True
            )
            return

        # ── setjob 30 мин cooldown шалгалт ───────────────────────
        try:
            ls = char["last_setjob"]
        except Exception:
            ls = None
        if ls:
            rem = timedelta(minutes=WORK_COOLDOWN_MINUTES) - (now - datetime.fromisoformat(ls))
            if rem.total_seconds() > 0:
                m, s = int(rem.total_seconds() // 60), int(rem.total_seconds() % 60)
                cur_job = JOBS.get(char["job_id"], {})
                cur_name = cur_job.get("name_mn", "тодорхойгүй")
                await interaction.response.send_message(
                    f"⏳ Та **{cur_name}**-аар ажиллаж байна!\n"
                    f"Ажил солих боломжтой болох хүртэл: **{m}м {s}с**",
                    ephemeral=True
                )
                return

        # ── Ажил солих ────────────────────────────────────────────
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET job_id=?, last_setjob=? WHERE user_id=? AND guild_id=?",
                (job, now.isoformat(), uid, gid),
            )
            await db.commit()

        sal_min, sal_max = jdata["salary"]
        embed = discord.Embed(
            title=f"{jdata['emoji']} Ажил сонгогдлоо!",
            description=(
                f"**{jdata['name_mn']}** болж ажиллаж эхэллээ!\n\n"
                f"💰 Цалин: **{sal_min:,} – {sal_max:,} ₮** (30 мин тутамд)\n"
                f"⏳ Ажил солих боломжтой болох хүртэл: **30м 00с**"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="➡️  /work командаар ажлаа хийж цалингаа аваарай!")
        await interaction.response.send_message(embed=embed)
    # ── /courses ──────────────────────────────────────────────
    @app_commands.command(name="courses", description="Боломжит курсуудыг харах")
    async def courses(self, interaction: discord.Interaction):
        completed = await get_completed_courses(interaction.user.id, interaction.guild_id)

        lines_owned = []
        lines_avail = []
        for cname, cdata in COURSES.items():
            unlocks_job = JOBS.get(cdata["unlocks"], {})
            j_name = unlocks_job.get("name_mn", cdata["unlocks"])
            j_emoji = unlocks_job.get("emoji", "💼")
            if cname in completed:
                lines_owned.append(
                    f"✅ {cdata['emoji']} **{cdata['name_mn']}**\n"
                    f"   → {j_emoji} {j_name} нээгдсэн"
                )
            else:
                lines_avail.append(
                    f"{cdata['emoji']} **{cdata['name_mn']}**  —  `{cdata['cost']:,} ₮`\n"
                    f"   → {j_emoji} {j_name} нээнэ\n"
                    f"   `/enroll {cname}`"
                )

        embed = discord.Embed(
            title="📚 Курсийн жагсаалт",
            description="Курст элсэж мэргэжилтэй ажил хийж илүү их цалин авна уу!",
            color=0x5865F2,
        )
        if lines_owned:
            embed.add_field(name="✅ Суралцсан курсууд", value="\n\n".join(lines_owned), inline=False)
        if lines_avail:
            embed.add_field(name="🎓 Боломжит курсууд",  value="\n\n".join(lines_avail), inline=False)
        if not lines_owned and not lines_avail:
            embed.description = "Курс байхгүй байна."
        await interaction.response.send_message(embed=embed)

    # ── /enroll ───────────────────────────────────────────────
    @app_commands.command(name="enroll", description="Курст элсэж мэргэжил эзэмших")
    @app_commands.describe(course="Элсэх курсийн нэр")
    @app_commands.autocomplete(course=_course_autocomplete)
    async def enroll(self, interaction: discord.Interaction, course: str):
        char = await get_char(interaction.user.id, interaction.guild_id)
        if not char:
            await interaction.response.send_message(
                "🎭 Эхлээд `/register` командаар дүр үүсгэнэ үү!", ephemeral=True
            )
            return
        if course not in COURSES:
            await interaction.response.send_message("❌ Тийм курс байхгүй!", ephemeral=True)
            return

        completed = await get_completed_courses(interaction.user.id, interaction.guild_id)
        if course in completed:
            await interaction.response.send_message(
                f"✅ **{COURSES[course]['name_mn']}**-д аль хэдийн элссэн байна!", ephemeral=True
            )
            return

        cdata = COURSES[course]
        user  = await get_user(interaction.user.id, interaction.guild_id)
        if user["balance"] < cdata["cost"]:
            await interaction.response.send_message(
                f"❌ Мөнгө хүрэлцэхгүй!\n"
                f"Хэрэгтэй: **{cdata['cost']:,} ₮**  |  Таных: **{user['balance']:,} ₮**",
                ephemeral=True,
            )
            return

        await update_balance(interaction.user.id, interaction.guild_id, -cdata["cost"])
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT OR REPLACE INTO user_courses
                       (user_id, guild_id, course_name, completed_at)
                   VALUES (?,?,?,?)""",
                (
                    interaction.user.id, interaction.guild_id,
                    course, datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()

        unlocks_job = JOBS.get(cdata["unlocks"], {})
        j_name  = unlocks_job.get("name_mn", cdata["unlocks"])
        j_emoji = unlocks_job.get("emoji", "💼")

        embed = discord.Embed(
            title=f"{cdata['emoji']} Курс дууслаа!",
            description=(
                f"**{cdata['name_mn']}** амжилттай дууслаа!\n\n"
                f"{j_emoji} **{j_name}** ажил нээгдлээ.\n"
                f"`/setjob {cdata['unlocks']}` командаар ажил сонгоно уу."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(name="💸 Зарцуулалт", value=f"{cdata['cost']:,} ₮", inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Character(bot))
