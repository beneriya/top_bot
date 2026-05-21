import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from database import DB_PATH, get_user, update_balance, get_happiness
from datetime import datetime, timedelta
import random
import json
from cogs.character import JOBS, get_char, calc_age
from cogs.family import process_child_economics
from config import (
    WORK_COOLDOWN_MINUTES, DAILY_COOLDOWN_HOURS,
    DAILY_REWARD_MIN, DAILY_REWARD_MAX, WORK_MIN_AGE,
    BALANCE_CAP,
)

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Баланс харах ──────────────────────────────────────────
    @app_commands.command(name="balance", description="Өөрийн төгрөгийн үлдэгдлийг харах")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user = await get_user(target.id, interaction.guild_id)
        bank_bal = user.get("bank", 0) or 0
        embed = discord.Embed(
            title=f"\U0001f4b0 {target.display_name}-н данс",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="\U0001f4b5 Pocket", value=f"**{user['balance']:,} \u20ae**", inline=True)
        embed.add_field(name="\U0001f3e6 Bank",   value=f"**{bank_bal:,} \u20ae**",       inline=True)
        embed.add_field(name="\U0001f4b0 \u041d\u0438\u0439\u0442", value=f"**{user['balance']+bank_bal:,} \u20ae**", inline=True)
        await interaction.response.send_message(embed=embed)

    # ── Ажил хийж мөнгө олох ──────────────────────────────────
    @app_commands.command(name="work", description="Ажил хийж төгрөг олох (30 минут тутамд)")
    async def work(self, interaction: discord.Interaction):
        # 1. Дүр шалгах
        char = await get_char(interaction.user.id, interaction.guild_id)
        if not char:
            await interaction.response.send_message(
                "🎭 Эхлээд `/register` командаар дүр үүсгэнэ үү!", ephemeral=True
            )
            return

        age = calc_age(dict(char))

        # 2. Нас барсан эсэх
        if age >= char["death_age"]:
            await interaction.response.send_message(
                "💀 Таны дүр нас барсан! `/register` командаар шинэ дүр үүсгэнэ үү.", ephemeral=True
            )
            return

        # 3. Насны шаардлага
        if age < WORK_MIN_AGE:
            await interaction.response.send_message(
                f"🚫 Та **{age} настай** байна. {WORK_MIN_AGE} наснаас ажилладаг!", ephemeral=True
            )
            return

        # 4. Ажил сонгосон эсэх
        if not char["job_id"] or char["job_id"] not in JOBS:
            await interaction.response.send_message(
                "💼 Ажил сонгоогүй байна! `/setjob` командаар ажил сонгоно уу.", ephemeral=True
            )
            return

        job = JOBS[char["job_id"]]

        # 5. Cooldown — атомик шалгалт (race condition-с хамгаалах)
        now    = datetime.utcnow()
        cutoff = (now - timedelta(minutes=WORK_COOLDOWN_MINUTES)).isoformat()
        uid, gid = interaction.user.id, interaction.guild_id

        await get_user(uid, gid)   # user бүртгэл байгааг баталгаажуулах

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            # last_work-г cooldown дууссан тохиолдолд л шинэчлэх — нэг хүсэлт л өнгөрнө
            cur = await db.execute(
                """UPDATE users SET last_work=?
                   WHERE user_id=? AND guild_id=?
                   AND (last_work IS NULL OR last_work <= ?)""",
                (now.isoformat(), uid, gid, cutoff),
            )
            await db.commit()

            if cur.rowcount == 0:
                # Cooldown идэвхтэй — үлдсэн хугацааг тооцоолох
                r = await (await db.execute(
                    "SELECT last_work FROM users WHERE user_id=? AND guild_id=?", (uid, gid)
                )).fetchone()
                last      = datetime.fromisoformat(r["last_work"])
                remaining = timedelta(minutes=WORK_COOLDOWN_MINUTES) - (now - last)
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                await interaction.response.send_message(
                    f"⏳ Дараагийн ажилд **{mins}м {secs}с** хүлээнэ үү!", ephemeral=True
                )
                return

        # 6. Happiness multiplier
        from database import get_happiness as _gh
        happiness = await _gh(uid, gid)
        if happiness <= 0:
            h_mult = 0.3
        elif happiness < 10:
            h_mult = 0.5 + happiness * 0.05
        else:
            h_mult = 1.0 + (happiness - 10) * 0.05

        # 6. Цалин тооцоолох + хүүхдийн эдийн засаг
        sal_min, sal_max = job["salary"]
        earned   = int(random.randint(sal_min, sal_max) * h_mult)
        work_msg = random.choice(job["messages"])

        async with aiosqlite.connect(DB_PATH) as db:
            child_delta  = await process_child_economics(uid, gid, db)
            total_change = earned + child_delta
            await db.execute(
                "UPDATE users SET balance=MIN(?,MAX(0,balance+?)) WHERE user_id=? AND guild_id=?",
                (BALANCE_CAP, total_change, uid, gid),
            )
            await db.commit()

        embed = discord.Embed(
            title=f"{job['emoji']} Ажил хийлээ!",
            description=f"**{work_msg}** ажлаа хийгээд **{earned:,} ₮** оллоо!",
            color=discord.Color.green(),
        )
        embed.add_field(name="💼 Мэргэжил", value=job["name_mn"], inline=True)
        embed.add_field(name="🎂 Нас",       value=f"{age} нас",   inline=True)
        h_emoji = "😊" if happiness >= 15 else ("😐" if happiness >= 8 else "😔")
        embed.add_field(name=f"{h_emoji} Аз жаргал", value=f"**{happiness}/20** ({h_mult:.0%})", inline=True)
        if child_delta != 0:
            if child_delta < 0:
                embed.add_field(name="👶 Хүүхдийн зардал", value=f"**-{abs(child_delta):,} ₮**", inline=True)
            else:
                embed.add_field(name="👶 Хүүхдийн орлого", value=f"**+{child_delta:,} ₮**", inline=True)
        await interaction.response.send_message(embed=embed)

    # ── Өдөр тутмын урамшуулал ────────────────────────────────
    @app_commands.command(name="daily", description="Өдөр тутмын урамшуулал авах")
    async def daily(self, interaction: discord.Interaction):
        user = await get_user(interaction.user.id, interaction.guild_id)
        now = datetime.utcnow()

        if user["last_daily"]:
            last = datetime.fromisoformat(user["last_daily"])
            diff = now - last
            if diff < timedelta(hours=DAILY_COOLDOWN_HOURS):
                remaining = timedelta(hours=DAILY_COOLDOWN_HOURS) - diff
                hours = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                await interaction.response.send_message(
                    f"⏳ Дараагийн урамшуулалд **{hours}ц {mins}м** хүлээнэ үү!", ephemeral=True
                )
                return

        reward = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET balance=balance+?, last_daily=? WHERE user_id=? AND guild_id=?",
                (reward, now.isoformat(), interaction.user.id, interaction.guild_id)
            )
            await db.commit()

        embed = discord.Embed(
            title="🎁 Өдөр тутмын урамшуулал!",
            description=f"**{reward:,} ₮** авлаа! Маргааш дахиад ирнэ үү!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ── Мөнгө шилжүүлэх ───────────────────────────────────────
    @app_commands.command(name="transfer", description="Өөр хүнд мөнгө шилжүүлэх")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Дүн 0-с их байх ёстой!", ephemeral=True)
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ Өөртөө шилжүүлэх боломжгүй!", ephemeral=True)
            return

        sender = await get_user(interaction.user.id, interaction.guild_id)
        if sender["balance"] < amount:
            await interaction.response.send_message(
                f"❌ Хүрэлцэхгүй байна! Таны үлдэгдэл: **{sender['balance']:,} ₮**", ephemeral=True
            )
            return

        await update_balance(interaction.user.id, interaction.guild_id, -amount)
        await update_balance(member.id, interaction.guild_id, amount)

        embed = discord.Embed(
            title="💸 Шилжүүлэг амжилттай!",
            description=f"**{amount:,} ₮**-ийг {member.mention}-д шилжүүллээ!",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    # ── /givemoney (Admin) ────────────────────────────────────
    @app_commands.command(name="givemoney", description="Хэрэглэгчид мөнгө өгөх [Admin]")
    @app_commands.checks.has_permissions(administrator=True)
    async def givemoney(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Дүн 0-с их байх ёстой!", ephemeral=True)
            return
        await update_balance(member.id, interaction.guild_id, amount)
        embed = discord.Embed(
            title="💸 Admin — Мөнгө нэмлээ",
            description=f"{member.mention}-д **{amount:,} ₮** нэмэгдлээ.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @givemoney.error
    async def givemoney_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Зөвхөн Admin хэрэглэх боломжтой!", ephemeral=True)

    # ── Category keyword map (шууд текст оруулахад ажиллана) ────
    CATEGORY_ALIASES = {
        "ring": "ring",       "rings": "ring",      "бөгж": "ring",
        "alcohol": "alcohol", "архи": "alcohol",    "drink": "alcohol",
        "cigarette": "cigarette", "тамхи": "cigarette", "smoke": "cigarette",
        "vape": "vape",       "вэйп": "vape",
        "accessory": "accessory", "аксессуар": "accessory", "цаг": "accessory",
        "gem": "gem",         "gems": "gem",        "үнэт": "gem",   "чулуу": "gem",
        "vehicle": "vehicle", "машин": "vehicle",   "хөдлөх": "vehicle",
        "realestate": "realestate", "байшин": "realestate",  "house": "realestate",
        "other": "other",     "бусад": "other",     "тоглоом": "other",
        "food": "food",       "хоол": "food",       "идэх": "food",
    }
    CATEGORY_LABELS = {
        "ring": "💍 Бөгж", "alcohol": "🍺 Архи", "cigarette": "🚬 Тамхи",
        "vape": "💨 Вэйп", "accessory": "⌚ Гоёл чимэглэл", "gem": "💎 Үнэт чулуу",
        "vehicle": "🚗 Хөдлөх хөрөнгө", "realestate": "🏠 Үл хөдлөх хөрөнгө",
        "other": "⚔️ Тоглоом/Бусад",
        "food": "🍽️ Хоол/Идэш",
    }

    # ── Дэлгүүр харах (категориор) ────────────────────────────
    @app_commands.command(name="shop", description="Дэлгүүрийн барааг харах  /shop gem · /shop alcohol · хоосон=бүгд")
    @app_commands.describe(category="alcohol · gem · ring · vehicle · cigarette · vape ... шууд бичнэ үү")
    async def shop(self, interaction: discord.Interaction, category: str = None):
        OTHER_TYPES = ("weapon", "armor", "heal", "ticket", "adoption")

        # Keyword → canonical category
        if category:
            category = self.CATEGORY_ALIASES.get(category.lower().strip(), category.lower().strip())

        # ── Real-estate category — informational, not a shop item ──
        if category == "realestate":
            from database import HOUSES
            embed = discord.Embed(
                title="🏠 Үл хөдлөх хөрөнгө",
                description=(
                    "Байшин нь дэлгүүрээс биш `/buyhouse` командаар авна.\n"
                    "Зарахдаа `/sellhouse`, ахиулахдаа `/upgradehouse` ашиглана уу."
                ),
                color=0x9B59B6
            )
            for lv, (name, price) in HOUSES.items():
                embed.add_field(
                    name=f"Түвшин {lv} — {name}",
                    value=f"**{price:,} ₮**",
                    inline=False
                )
            embed.set_footer(text="/buyhouse командаар авна уу  •  зарахдаа /sellhouse")
            await interaction.response.send_message(embed=embed)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if category and category not in ("other", "realestate"):
                cursor = await db.execute(
                    "SELECT * FROM shop WHERE item_type=? ORDER BY price", (category,)
                )
            elif category == "other":
                placeholders = ",".join("?" * len(OTHER_TYPES))
                cursor = await db.execute(
                    f"SELECT * FROM shop WHERE item_type IN ({placeholders}) ORDER BY price",
                    OTHER_TYPES
                )
            else:
                cursor = await db.execute("SELECT * FROM shop ORDER BY item_type, price")
            items = await cursor.fetchall()

        title = f"🏪 Дэлгүүр — {self.CATEGORY_LABELS.get(category, f'❓ {category}')}" if category else "🏪 Дэлгүүр"

        embed = discord.Embed(title=title, color=0x9B59B6)
        if not items:
            embed.description = "Бараа байхгүй байна."
        else:
            lines = []
            for item in items:
                eff = ""
                if item["effect_type"] == "sogto":
                    eff = f" *(+{item['effect_value']} согтолт)*"
                elif item["effect_type"] == "mansuuralt":
                    eff = f" *(+{item['effect_value']} мансуурал)*"
                lines.append(
                    f"{item['emoji']} **{item['name']}** — `{item['price']:,} ₮`{eff}\n"
                    f"　ID: `{item['item_id']}` · {item['description']}"
                )
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) > 950:
                    embed.add_field(name="​", value=chunk, inline=False)
                    chunk = line + "\n"
                else:
                    chunk += line + "\n"
            if chunk:
                embed.add_field(name="​", value=chunk, inline=False)

        embed.set_footer(text="/buy <ID> командаар авна уу  •  категори сонгоход нарийвчилсан жагсаалт харагдана")
        await interaction.response.send_message(embed=embed)

    # ── Бараа худалдаж авах ────────────────────────────────────
    @app_commands.command(name="buy", description="Дэлгүүрээс бараа авах  —  /buy 93  эсвэл  /buy 93 10")
    @app_commands.describe(args="ID [тоо]  —  жишээ: '93'  эсвэл  '93 10'  (10ш авна, max 100)")
    async def buy(self, interaction: discord.Interaction, args: str):
        # args parse: "item_id [quantity]"
        parts = args.strip().split()
        try:
            item_id  = int(parts[0])
            quantity = int(parts[1]) if len(parts) > 1 else 1
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "❌ Буруу формат! `/buy 93` эсвэл `/buy 93 10` гэж бичнэ үү.", ephemeral=True
            )
            return

        if quantity < 1:
            await interaction.response.send_message("❌ Тоо 1-с их байх ёстой!", ephemeral=True)
            return
        if quantity > 100:
            await interaction.response.send_message("❌ Нэг удаад хамгийн ихдээ **100** авч болно!", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM shop WHERE item_id=?", (item_id,))
            item = await cursor.fetchone()

        if not item:
            await interaction.response.send_message("❌ Ийм бараа олдсонгүй!", ephemeral=True)
            return

        # Weapon/armor нэгийг л авна — quantity=1 хязгаарлах
        if item["item_type"] in ("weapon", "armor") and quantity > 1:
            await interaction.response.send_message(
                "⚔️ Зэвсэг/хуягыг нэг нэгээр авна уу (тоглолтод нэг л ашиглагдана).", ephemeral=True
            )
            return

        total_price = item["price"] * quantity
        user        = await get_user(interaction.user.id, interaction.guild_id)

        if user["balance"] < total_price:
            can_afford = user["balance"] // item["price"]
            hint = f"\n💡 Та хамгийн ихдээ **{can_afford}ш** авах боломжтой." if can_afford > 0 and quantity > 1 else ""
            await interaction.response.send_message(
                f"❌ Мөнгө хүрэлцэхгүй!\n"
                f"Хэрэгтэй: **{total_price:,} ₮**  |  Таных: **{user['balance']:,} ₮**{hint}",
                ephemeral=True
            )
            return

        await update_balance(interaction.user.id, interaction.guild_id, -total_price)

        # Inventory-д нэмэх (weapon/armor: эдэлгээ = quantity болно)
        WEAPON_DURABILITY = 10  # 10 тулаан тэсвэрлэнэ
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if item["item_type"] in ("weapon", "armor"):
                inv_qty = WEAPON_DURABILITY  # durability as quantity
            else:
                inv_qty = quantity

            cursor = await db.execute(
                "SELECT quantity FROM inventory WHERE user_id=? AND guild_id=? AND item_id=?",
                (interaction.user.id, interaction.guild_id, item_id)
            )
            existing = await cursor.fetchone()
            if existing:
                await db.execute(
                    "UPDATE inventory SET quantity=quantity+? WHERE user_id=? AND guild_id=? AND item_id=?",
                    (inv_qty, interaction.user.id, interaction.guild_id, item_id)
                )
            else:
                await db.execute(
                    "INSERT INTO inventory (user_id, guild_id, item_id, quantity) VALUES (?,?,?,?)",
                    (interaction.user.id, interaction.guild_id, item_id, inv_qty)
                )

            # ── Weapon/armor → RPG-д шууд тоноглох ───────────────
            equip_note = ""
            if item["item_type"] == "weapon":
                await db.execute(
                    "INSERT OR IGNORE INTO rpg (user_id, guild_id) VALUES (?,?)",
                    (interaction.user.id, interaction.guild_id)
                )
                await db.execute(
                    "UPDATE rpg SET attack=?, weapon=? WHERE user_id=? AND guild_id=?",
                    (10 + item["effect_value"], item["name"],
                     interaction.user.id, interaction.guild_id)
                )
                equip_note = f"\n⚔️ Дайралт **+{item['effect_value']}** нэмэгдлээ! (эдэлгээ: {WEAPON_DURABILITY} тулаан)"
            elif item["item_type"] == "armor":
                await db.execute(
                    "INSERT OR IGNORE INTO rpg (user_id, guild_id) VALUES (?,?)",
                    (interaction.user.id, interaction.guild_id)
                )
                await db.execute(
                    "UPDATE rpg SET defense=?, armor=? WHERE user_id=? AND guild_id=?",
                    (5 + item["effect_value"], item["name"],
                     interaction.user.id, interaction.guild_id)
                )
                equip_note = f"\n🛡️ Хамгаалалт **+{item['effect_value']}** нэмэгдлээ! (эдэлгээ: {WEAPON_DURABILITY} тулаан)"
            await db.commit()

        qty_txt = f"x{quantity} " if quantity > 1 else ""
        embed = discord.Embed(
            title="✅ Худалдан авалт амжилттай!",
            description=(
                f"{item['emoji']} **{item['name']}** {qty_txt}авлаа!\n"
                f"**{total_price:,} ₮** зарцуулагдлаа.{equip_note}"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Үлдэгдэл: {user['balance'] - total_price:,} ₮")
        await interaction.response.send_message(embed=embed)

    # ── Inventory харах ────────────────────────────────────────
    @app_commands.command(name="inventory", description="Өөрийн inventory харах")
    async def inventory(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT s.name, s.emoji, s.item_type, i.quantity, i.item_id
                FROM inventory i JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=?
            """, (interaction.user.id, interaction.guild_id))
            items = await cursor.fetchall()

        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}-н зүйлс",
            color=discord.Color.orange()
        )
        if not items:
            embed.description = "Inventory хоосон байна. /дэлгүүр-ээс зүйлс авна уу!"
        else:
            for item in items:
                embed.add_field(
                    name=f"{item['emoji']} {item['name']} x{item['quantity']}",
                    value=f"ID: `{item['item_id']}`",
                    inline=True
                )
        await interaction.response.send_message(embed=embed)

    # ── Баянчуудын жагсаалт ───────────────────────────────────
    @app_commands.command(name="richlist", description="Серверийн хамгийн баян хүмүүс")
    async def richlist(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT user_id, balance FROM users WHERE guild_id=? ORDER BY balance DESC LIMIT 10",
                (interaction.guild_id,)
            )
            rows = await cursor.fetchall()

        embed  = discord.Embed(title="🏆 Баянчуудын TOP 10", color=discord.Color.gold())
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            member = interaction.guild.get_member(row["user_id"])
            name   = member.display_name if member else f"ID:{row['user_id']}"
            medal  = medals[i] if i < 3 else f"**{i+1}.**"
            embed.add_field(
                name=f"{medal} {name}",
                value=f"**{row['balance']:,} ₮**",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  BANK COMMANDS
    # ══════════════════════════════════════════════════════════

    @app_commands.command(name="deposit", description="Мөнгөө банкинд хадгалах (pocket → bank)")
    async def deposit(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Дүн 0-с их байх ёстой!", ephemeral=True)
            return
        uid, gid = interaction.user.id, interaction.guild_id
        user = await get_user(uid, gid)
        if user["balance"] < amount:
            await interaction.response.send_message(
                f"❌ Pocket-д хүрэлцэхгүй! Pocket: **{user['balance']:,} ₮**", ephemeral=True
            )
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET balance=balance-?, bank=bank+? WHERE user_id=? AND guild_id=?",
                (amount, amount, uid, gid)
            )
            await db.commit()
        embed = discord.Embed(
            title="\U0001f3e6 Банкинд хадгаллаа!",
            description=f"**{amount:,} ₮** банкинд хийгдлээ.",
            color=discord.Color.blue()
        )
        embed.add_field(name="\U0001f4b5 Pocket", value=f"**{user['balance']-amount:,} ₮**", inline=True)
        embed.add_field(name="\U0001f3e6 Bank",   value=f"**{(user.get('bank',0)+amount):,} ₮**", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="withdraw", description="Банкнаас мөнгөө гаргах (bank → pocket)")
    async def withdraw(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Дүн 0-с их байх ёстой!", ephemeral=True)
            return
        uid, gid = interaction.user.id, interaction.guild_id
        user = await get_user(uid, gid)
        bank_bal = user.get("bank", 0) or 0
        if bank_bal < amount:
            await interaction.response.send_message(
                f"❌ Банкинд хүрэлцэхгүй! Bank: **{bank_bal:,} ₮**", ephemeral=True
            )
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET balance=MIN(1000000000,balance+?), bank=bank-? WHERE user_id=? AND guild_id=?",
                (amount, amount, uid, gid)
            )
            await db.commit()
        embed = discord.Embed(
            title="\U0001f4b8 Банкнаас гаргалаа!",
            description=f"**{amount:,} ₮** pocket-д нэмэгдлээ.",
            color=discord.Color.green()
        )
        embed.add_field(name="\U0001f4b5 Pocket", value=f"**{user['balance']+amount:,} ₮**", inline=True)
        embed.add_field(name="\U0001f3e6 Bank",   value=f"**{bank_bal-amount:,} ₮**", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bank", description="Банкны данс болон нийт хөрөнгийг харах")
    async def bank_info(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        uid, gid = target.id, interaction.guild_id
        user = await get_user(uid, gid)
        pocket = user["balance"]
        bank   = user.get("bank", 0) or 0

        # Inventory value
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("""
                SELECT SUM(s.price * i.quantity) as total_val
                FROM inventory i JOIN shop s ON i.item_id=s.item_id
                WHERE i.user_id=? AND i.guild_id=?
            """, (uid, gid))
            row = await cur.fetchone()
        inv_val = row["total_val"] or 0

        total = pocket + bank + inv_val
        embed = discord.Embed(
            title=f"\U0001f3e6 {target.display_name}-н данс",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="\U0001f4b5 Pocket",     value=f"**{pocket:,} ₮**",  inline=True)
        embed.add_field(name="\U0001f3e6 Bank",       value=f"**{bank:,} ₮**",    inline=True)
        embed.add_field(name="\U0001f392 Inventory",  value=f"**{inv_val:,} ₮**", inline=True)
        embed.add_field(name="\U0001f4b0 Нийт хөрөнгө", value=f"**{total:,} ₮**", inline=False)
        embed.set_footer(text="/deposit хийж банкинд хадгал  •  /withdraw гаргах")
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /eat  — consume food item, raise happiness
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="eat", description="Хоол идэж аз жаргалын түвшнийг нэмэгдүүлэх")
    @app_commands.describe(item_id="Хоолны барааны ID (/shop food-оос харна уу)")
    async def eat(self, interaction: discord.Interaction, item_id: int):
        uid, gid = interaction.user.id, interaction.guild_id
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("""
                SELECT i.item_id, i.quantity, s.name, s.emoji, s.effect_value
                FROM inventory i JOIN shop s ON i.item_id=s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='food' AND i.item_id=?
            """, (uid, gid, item_id))
            food = await cur.fetchone()

        if not food:
            await interaction.response.send_message(
                "❌ Inventory-д тийм хоол байхгүй! `/shop food` дээрээс аваад ирнэ үү.", ephemeral=True
            )
            return

        happiness = await get_happiness(uid, gid)
        gain      = food["effect_value"]
        new_hap   = happiness + gain

        if new_hap > 20:
            # Overeating — penalty
            user    = await get_user(uid, gid)
            penalty = int(user["balance"] * 0.10)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET balance=MAX(0,balance-?), happiness=20, happiness_updated=? WHERE user_id=? AND guild_id=?",
                    (penalty, datetime.utcnow().isoformat(), uid, gid)
                )
                # Still consume item
                if food["quantity"] > 1:
                    await db.execute("UPDATE inventory SET quantity=quantity-1 WHERE item_id=? AND user_id=? AND guild_id=?", (item_id,uid,gid))
                else:
                    await db.execute("DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?", (item_id,uid,gid))
                await db.commit()
            embed = discord.Embed(
                title="\U0001f974 Хэтрүүлэн идсэний улмаас эрүүл мэндэд хохирол учирлаа!",
                description=(
                    f"{food['emoji']} **{food['name']}** идэхэд аз жаргал 20-аас хэтэрлээ.\n"
                    f"Эрүүл мэндийн суутгал: **-{penalty:,} ₮** (10%)\n"
                    f"Аз жаргал: **20/20** (дээд хэмжээнд байна)"
                ),
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET happiness=?, happiness_updated=? WHERE user_id=? AND guild_id=?",
                (new_hap, datetime.utcnow().isoformat(), uid, gid)
            )
            if food["quantity"] > 1:
                await db.execute("UPDATE inventory SET quantity=quantity-1 WHERE item_id=? AND user_id=? AND guild_id=?", (item_id,uid,gid))
            else:
                await db.execute("DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?", (item_id,uid,gid))
            await db.commit()

        h_bar = "♥" * new_hap + "♡" * (20 - new_hap)
        embed = discord.Embed(
            title=f"{food['emoji']} {food['name']} идлээ!",
            description=f"Аз жаргал **+{gain}** нэмэгдлээ!",
            color=discord.Color.green()
        )
        embed.add_field(name="\U0001f60a Аз жаргал", value=f"**{new_hap}/20**\n{h_bar}", inline=False)
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /rob  — steal from pocket
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="rob", description="Бусдын pocket-аас хулгай хийх (1 цаг cooldown)")
    @app_commands.describe(member="Хулгайлах хүн")
    async def rob(self, interaction: discord.Interaction, member: discord.Member):
        uid, gid = interaction.user.id, interaction.guild_id
        if member.id == uid:
            await interaction.response.send_message("❌ Өөрөөсөө хулгай хийх боломжгүй!", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ Bot-оос хулгай хийх боломжгүй!", ephemeral=True)
            return

        now = datetime.utcnow()
        robber = await get_user(uid, gid)

        # Cooldown check
        if robber.get("rob_cooldown"):
            last_rob  = datetime.fromisoformat(robber["rob_cooldown"])
            remaining = timedelta(hours=1) - (now - last_rob)
            if remaining.total_seconds() > 0:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                await interaction.response.send_message(
                    f"⏳ Rob cooldown: **{mins}м {secs}с** хүлээнэ үү!", ephemeral=True
                )
                return

        victim = await get_user(member.id, gid)
        v_pocket = victim["balance"]

        if v_pocket <= 0:
            await interaction.response.send_message(
                f"\U0001f45b {member.display_name}-н pocket хоосон байна. Өөр хүнийг сонгоно уу!",
                ephemeral=True
            )
            return

        # Apply cooldown now (pocket had money)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET rob_cooldown=? WHERE user_id=? AND guild_id=?",
                (now.isoformat(), uid, gid)
            )
            await db.commit()

        # 45% success chance
        success = random.random() < 0.45

        if success:
            # Tiered steal %
            if v_pocket <= 30_000:
                pct = random.uniform(0.08, 0.14)
            elif v_pocket <= 60_000:
                pct = random.uniform(0.11, 0.15)
            elif v_pocket <= 100_000:
                pct = random.uniform(0.13, 0.17)
            elif v_pocket <= 200_000:
                pct = random.uniform(0.15, 0.20)
            else:
                stolen = random.randint(30_000, 50_000)
                pct    = None

            if pct is not None:
                stolen = int(v_pocket * pct)

            await update_balance(member.id, gid, -stolen)
            await update_balance(uid, gid, stolen)
            embed = discord.Embed(
                title="\U0001f977 Хулгай амжилттай!",
                description=(
                    f"{member.display_name}-н pocket-аас **{stolen:,} ₮** авлаа!\n"
                    f"└ Тэдний pocket: **{v_pocket-stolen:,} ₮** болж буурлаа."
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)

        else:
            # Fail — fine + tension
            fine_pct   = random.uniform(0.10, 0.20)
            fine       = int(robber["balance"] * fine_pct)
            old_tension = robber.get("tension", 0) or 0
            new_tension = old_tension + 3

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET balance=MAX(0,balance-?), tension=? WHERE user_id=? AND guild_id=?",
                    (fine, new_tension, uid, gid)
                )
                await db.commit()

            if new_tension >= 6:
                # Prison 30 minutes
                release = now + timedelta(minutes=30)
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE users SET prison_until=?, prison_reason='rob' WHERE user_id=? AND guild_id=?",
                        (release.isoformat(), uid, gid)
                    )
                    await db.commit()
                embed = discord.Embed(
                    title="\U0001f6a8 Цагдаад баригдлаа! Шоронд орлоо!",
                    description=(
                        f"Хулгай амжилтгүй болж цагдаад баригдлаа.\n"
                        f"Торгууль: **-{fine:,} ₮**\n"
                        f"⚡ Тэнсэн: **{new_tension}/6** → Шоронд орлоо!\n"
                        f"\U0001f510 Суллагдах: <t:{int(release.timestamp())}:R>"
                    ),
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="⚠️ Цагдаагийн анхааруулга!",
                    description=(
                        f"Хулгай амжилтгүй болж цагдаа анхааруулга өгөв.\n"
                        f"Торгууль: **-{fine:,} ₮**\n"
                        f"⚡ Тэнсэн: **{new_tension}/6**  ({'Дараагийн удаа шоронд орно!' if new_tension >= 3 else 'Болгоомжтой байгаарай!'})"
                    ),
                    color=discord.Color.orange()
                )
            await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /hack  — steal from bank (programmer only, 35% success)
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="hack", description="Банкинд халдах — зөвхөн програмист ашиглана (2 цаг cooldown)")
    @app_commands.describe(member="Хак хийх хүн")
    async def hack(self, interaction: discord.Interaction, member: discord.Member):
        uid, gid = interaction.user.id, interaction.guild_id
        if member.id == uid:
            await interaction.response.send_message("❌ Өөрийгөө хак хийх боломжгүй!", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ Bot-ыг хак хийх боломжгүй!", ephemeral=True)
            return

        # Check programmer job
        from cogs.character import get_char
        char = await get_char(uid, gid)
        if not char or char.get("job_id") != "programmer":
            await interaction.response.send_message(
                "\U0001f4bb Хак команд зөвхөн **Програмист** мэргэжилтэй хүн ашиглах боломжтой!\n"
                "`/setjob` болон `/courses` командаар програмчлалын курс аваад програмист болно уу.",
                ephemeral=True
            )
            return

        now    = datetime.utcnow()
        hacker = await get_user(uid, gid)

        # Cooldown check — 2 hours
        if hacker.get("hack_cooldown"):
            last_hack = datetime.fromisoformat(hacker["hack_cooldown"])
            remaining = timedelta(hours=2) - (now - last_hack)
            if remaining.total_seconds() > 0:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                await interaction.response.send_message(
                    f"⏳ Hack cooldown: **{mins}м {secs}с** хүлээнэ үү!", ephemeral=True
                )
                return

        victim = await get_user(member.id, gid)
        v_bank = victim.get("bank", 0) or 0

        if v_bank <= 0:
            # Can immediately try another target
            await interaction.response.send_message(
                f"\U0001f4ca {member.display_name}-н банкны данс хоосон байна. Өөр хүнийг сонгоно уу!",
                ephemeral=True
            )
            return

        # Apply cooldown
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET hack_cooldown=? WHERE user_id=? AND guild_id=?",
                (now.isoformat(), uid, gid)
            )
            await db.commit()

        # 35% success
        success = random.random() < 0.35

        if success:
            pct    = random.uniform(0.20, 0.30)
            stolen = min(int(v_bank * pct), 200_000)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET bank=MAX(0,bank-?) WHERE user_id=? AND guild_id=?",
                    (stolen, member.id, gid)
                )
                await db.execute(
                    "UPDATE users SET balance=MIN(1000000000,balance+?) WHERE user_id=? AND guild_id=?",
                    (stolen, uid, gid)
                )
                await db.commit()
            embed = discord.Embed(
                title="\U0001f5a5️ Хак амжилттай!",
                description=(
                    f"{member.display_name}-н банкнаас **{stolen:,} ₮** авлаа!\n"
                    f"└ Тэдний банк: **{v_bank-stolen:,} ₮** болж буурлаа."
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)

        else:
            old_tension = hacker.get("tension", 0) or 0
            new_tension = old_tension + 2

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET tension=? WHERE user_id=? AND guild_id=?",
                    (new_tension, uid, gid)
                )
                await db.commit()

            if new_tension >= 6:
                release = now + timedelta(minutes=45)
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE users SET prison_until=?, prison_reason='hack' WHERE user_id=? AND guild_id=?",
                        (release.isoformat(), uid, gid)
                    )
                    await db.commit()
                embed = discord.Embed(
                    title="\U0001f6a8 FBI баривчиллаа! Шоронд орлоо!",
                    description=(
                        f"Хак амжилтгүй болж FBI баривчиллаа.\n"
                        f"⚡ Тэнсэн: **{new_tension}/6** → Шоронд орлоо! (45 мин)\n"
                        f"\U0001f510 Суллагдах: <t:{int(release.timestamp())}:R>"
                    ),
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="⚠️ Hack-ийн оролдлого илэрлээ!",
                    description=(
                        f"Хак амжилтгүй болж FBI анхааруулга өгөв.\n"
                        f"⚡ Тэнсэн: **{new_tension}/6**  ({'Дараагийн удаа шоронд орно!' if new_tension >= 4 else 'Болгоомжтой байгаарай!'})"
                    ),
                    color=discord.Color.orange()
                )
            await interaction.response.send_message(embed=embed)


