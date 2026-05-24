import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import json
from datetime import datetime
from database import DB_PATH, get_user, HOUSES
from cogs.character import JOBS, COURSES, GENDER_MN, get_char, calc_age, get_completed_courses

def xp_for_level(level: int) -> int:
    return int(100 * (level ** 1.5))

class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        user     = await get_user(message.author.id, message.guild.id)
        new_xp   = user["xp"] + 10
        new_lv   = user["level"]
        leveled  = False
        while new_xp >= xp_for_level(new_lv):
            new_xp -= xp_for_level(new_lv)
            new_lv += 1
            leveled = True

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET xp=?, level=?, messages=messages+1 WHERE user_id=? AND guild_id=?",
                (new_xp, new_lv, message.author.id, message.guild.id)
            )
            await db.commit()

        if leveled:
            needed_next = xp_for_level(new_lv)
            embed = discord.Embed(
                title=f"⬆️  Түвшин ахиллаа!",
                description=(
                    f"🎊 {message.author.mention}\n"
                    f"**{new_lv - 1}** → **{new_lv}** дүн  ✨"
                ),
                color=0xFEE75C
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.add_field(name="⭐ Шинэ түвшин",   value=f"**{new_lv}**",         inline=True)
            embed.add_field(name="✨ Дараагийн XP",   value=f"**{needed_next:,}**",  inline=True)
            embed.set_footer(text="TOP Bot  •  /profile командаар дэлгэрэнгүйг харна уу")
            await message.channel.send(embed=embed)
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT role_id FROM level_roles WHERE guild_id=? AND level=?",
                    (message.guild.id, new_lv)
                )
                row = await cur.fetchone()
                if row:
                    role = message.guild.get_role(row["role_id"])
                    if role:
                        await message.author.add_roles(role)
                        await message.channel.send(
                            f"🎭 {message.author.mention} **{role.name}** role авлаа!"
                        )

    # ── /profile ──────────────────────────────────────────────────
    @commands.hybrid_command(name="profile", description="Өөрийн эсвэл бусдын дэлгэрэнгүй профайл харах")
    async def profile(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        await ctx.defer()

        user = await get_user(target.id, ctx.guild.id)
        char = await get_char(target.id, ctx.guild.id)

        # ── XP progress bar ───────────────────────────────────────
        needed_xp = xp_for_level(user["level"])
        filled    = round((user["xp"] / needed_xp) * 14) if needed_xp else 0
        xp_bar    = f"`{'▰' * filled}{'▱' * (14 - filled)}  {user['xp']}/{needed_xp}`"

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Balance leaderboard rank
            cur = await db.execute(
                "SELECT COUNT(*)+1 FROM users WHERE guild_id=? AND balance > ?",
                (ctx.guild.id, user["balance"])
            )
            bal_rank = (await cur.fetchone())[0]

            # Level rank
            cur = await db.execute(
                "SELECT COUNT(*)+1 FROM users WHERE guild_id=?"
                " AND (level > ? OR (level=? AND xp > ?))",
                (ctx.guild.id, user["level"], user["level"], user["xp"])
            )
            lv_rank = (await cur.fetchone())[0]

            # Family
            fam_cur = await db.execute(
                "SELECT * FROM family WHERE user_id=? AND guild_id=?",
                (target.id, ctx.guild.id)
            )
            fam_row = await fam_cur.fetchone()

            # Inventory value
            inv_cur = await db.execute("""
                SELECT COALESCE(SUM(CASE WHEN s.item_type IN ('weapon','armor') THEN s.price ELSE s.price * i.quantity END),0) AS total_val,
                       COALESCE(SUM(CASE WHEN s.item_type IN ('weapon','armor') THEN 1 ELSE i.quantity END),0) AS total_qty
                FROM inventory i JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=?
            """, (target.id, ctx.guild.id))
            inv_row = await inv_cur.fetchone()

            # Most expensive vehicle + count
            veh_cur = await db.execute("""
                SELECT s.name, s.emoji, s.price, i.quantity
                FROM inventory i JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='vehicle'
                ORDER BY s.price DESC
            """, (target.id, ctx.guild.id))
            vehicles = await veh_cur.fetchall()

        # ── Family info ───────────────────────────────────────────
        if fam_row:
            sp_id  = fam_row["spouse_id"]
            kids   = json.loads(fam_row["children"] or "[]")
            sp_mem = ctx.guild.get_member(sp_id) if sp_id else None
            marriage_txt = f"💍 {sp_mem.display_name}-тай гэрлэсэн" if sp_mem else (
                f"💍 ID:{sp_id}" if sp_id else "💔 Гэрлээгүй"
            )
            child_txt = f"👶 {len(kids)} хүүхэд" if kids else "👶 Хүүхэдгүй"
            house_lv  = fam_row["house_level"]
        else:
            marriage_txt = "💔 Гэрлээгүй"
            child_txt    = "👶 Хүүхэдгүй"
            house_lv     = 0

        # ── Үл хөдлөх хөрөнгө (real estate) ─────────────────────
        if house_lv and house_lv > 0:
            house_txt = f"{HOUSES[house_lv][0]}"
        else:
            house_txt = "🚫 Байшингүй"

        # ── Хөдлөх хөрөнгө (vehicles) ────────────────────────────
        if vehicles:
            top_v = vehicles[0]
            total_veh = sum(v["quantity"] for v in vehicles)
            if total_veh == 1:
                veh_txt = f"{top_v['emoji']} {top_v['name']}"
            else:
                veh_txt = f"{top_v['emoji']} {top_v['name']}  *(нийт {total_veh} хөдлөх хөрөнгө)*"
        else:
            veh_txt = "🚫 Байхгүй"

        # ── Prison ───────────────────────────────────────────────
        from cogs.substances import get_prison_rank, prison_remaining
        count       = user.get("prison_count", 0)
        rank_e, rank_n = get_prison_rank(count)
        remaining   = prison_remaining(user.get("prison_until"))

        if remaining:
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            prison_val = (
                f"🚔 Шоронд байна — {mins}м {secs}с үлдсэн\n"
                f"{rank_e} **{rank_n}** *(нийт {count} удаа)*"
            )
        elif count == 0:
            prison_val = "✅ Гэмт хэргийн бүртгэлгүй"
        else:
            prison_val = f"{rank_e} **{rank_n}** *(нийт {count} удаа)*"

        # ── Balance rank medal ────────────────────────────────────
        medal = "🥇" if bal_rank == 1 else "🥈" if bal_rank == 2 else "🥉" if bal_rank == 3 else "💹"

        # ── Build embed ───────────────────────────────────────────
        # ── XP bar ─────────────────────────────────────────────────────
        needed_xp  = xp_for_level(user["level"])
        xp_filled  = round(12 * user["xp"] / needed_xp) if needed_xp else 0
        xp_bar_str = "▰" * xp_filled + "▱" * (12 - xp_filled)

        # ── Pocket/Bank totals ──────────────────────────────────────────
        async with aiosqlite.connect(DB_PATH) as db2:
            db2.row_factory = aiosqlite.Row
            _ub = await db2.execute("SELECT bank FROM users WHERE user_id=? AND guild_id=?",
                                    (target.id, ctx.guild.id))
            _ubr = await _ub.fetchone()
        bank_bal = (_ubr["bank"] if _ubr and _ubr["bank"] else 0)
        total_w  = user["balance"] + bank_bal

        # ── Color: red if in prison, purple if top-3, blue otherwise ───
        if remaining:
            clr = 0xED4245
        elif bal_rank <= 3:
            clr = 0xF1C40F
        else:
            clr = 0x5865F2

        embed = discord.Embed(color=clr)
        embed.set_author(
            name=f"{target.display_name}  —  профайл",
            icon_url=target.display_avatar.url
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # Row 1: Level / Rank / XP bar
        embed.add_field(
            name="⭐ Түвшин",
            value=f"**{user['level']}**  `#{lv_rank}`",
            inline=True
        )
        embed.add_field(
            name=f"{medal} Баялгийн ранк",
            value=f"**#{bal_rank}** серверт",
            inline=True
        )
        embed.add_field(name="​", value="​", inline=True)
        embed.add_field(
            name="✨ XP",
            value=f"`{xp_bar_str}` **{user['xp']:,} / {needed_xp:,}**",
            inline=False
        )

        # Row 2: Money
        embed.add_field(name="💵 Pocket",  value=f"**{user['balance']:,} ₮**", inline=True)
        embed.add_field(name="🏦 Bank",    value=f"**{bank_bal:,} ₮**",        inline=True)
        embed.add_field(name="💎 Нийт",    value=f"**{total_w:,} ₮**",         inline=True)

        # Row 3: Inventory / Family
        embed.add_field(
            name="🎒 Inventory",
            value=f"**{inv_row['total_qty']}** зүйл  ≈  {inv_row['total_val']:,} ₮",
            inline=True
        )
        embed.add_field(
            name="👨‍👩‍👧 Гэр бүл",
            value=f"{marriage_txt}\n{child_txt}",
            inline=True
        )
        embed.add_field(name="​", value="​", inline=True)

        # Row 4: Assets
        embed.add_field(name="🏠 Байшин",  value=house_txt, inline=True)
        embed.add_field(name="🚗 Хөдлөх",  value=veh_txt,   inline=True)
        embed.add_field(name="​", value="​", inline=True)

        # Row 5: Character
        if char:
            char = dict(char)
            age    = calc_age(char)
            gender = GENDER_MN.get(char.get("gender",""), "—")
            job_id = char.get("job_id")
            job_txt = f"{JOBS[job_id]['emoji']} {JOBS[job_id]['name_mn']}" if job_id and job_id in JOBS else "💼 Ажилгүй"
            completed = await get_completed_courses(target.id, ctx.guild.id)
            if completed:
                sorted_c = sorted(
                    completed,
                    key=lambda c: JOBS.get(COURSES[c]["unlocks"], {}).get("salary", (0,0))[1]
                                  if c in COURSES else 0,
                    reverse=True
                )
                top3 = sorted_c[:3]; rest = len(sorted_c) - 3
                clines = [f"{COURSES[c]['emoji']} {COURSES[c]['name_mn']}" for c in top3 if c in COURSES]
                if rest > 0: clines.append(f"*+{rest} бусад*")
                course_txt = "\n".join(clines)
            else:
                course_txt = "📭 Курс эзэмшээгүй"
            embed.add_field(
                name="🎭 Дүр",
                value=f"{gender}  •  **{age} нас**\n{job_txt}",
                inline=True
            )
            embed.add_field(name="🎓 Мэргэжлүүд", value=course_txt, inline=True)
            embed.add_field(name="​", value="​", inline=True)
        else:
            embed.add_field(
                name="🎭 Дүр",
                value="*`/register` командаар дүр үүсгэнэ үү*",
                inline=False
            )

        # Prison row
        embed.add_field(name="🏴 Шорон", value=prison_val, inline=False)

        embed.set_footer(text=f"TOP Bot  •  {target.name}  •  /profile")
        await ctx.send(embed=embed)
    # ── /top ──────────────────────────────────────────────────────
    @commands.hybrid_command(name="top", description="Серверийн TOP 10 идэвхтэй хүмүүс")
    async def leaderboard(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT user_id, level, xp FROM users WHERE guild_id=?"
                " ORDER BY level DESC, xp DESC LIMIT 10",
                (ctx.guild.id,)
            )
            rows = await cur.fetchall()

        if not rows:
            await ctx.send("⚠️ Мэдээлэл байхгүй.", ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        top_xp = (rows[0]["level"] * 1000 + rows[0]["xp"]) or 1
        def lbar(lv, xp, mx, length=8):
            score = lv * 1000 + xp
            filled = round(length * score / mx) if mx else 0
            return "▰" * filled + "▱" * (length - filled)
        lines = []
        for i, row in enumerate(rows):
            m  = ctx.guild.get_member(row["user_id"])
            nm = (m.display_name if m else f"User#{row['user_id']}")[:16]
            med = medals[i] if i < 3 else f"`#{i+1:>2}`"
            bar = lbar(row["level"], row["xp"], top_xp)
            lines.append(f"{med}  `{bar}`  LV.**{row['level']}**  •  {nm}")
        embed = discord.Embed(
            title="⭐  Түвшний жагсаалт TOP 10",
            description="\n".join(lines),
            color=0xFEE75C
        )
        embed.set_footer(text="TOP Bot  •  /top  •  Түвшин + XP-р эрэмбэлсэн")
        await ctx.send(embed=embed)

    # ── /level_role_add ───────────────────────────────────────────
    @commands.hybrid_command(name="level_role_add", description="Тодорхой түвшинд role өгөх тохиргоо [Admin]")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level_role(self, ctx: commands.Context, level: int, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO level_roles (guild_id,level,role_id) VALUES (?,?,?)",
                (ctx.guild.id, level, role.id)
            )
            await db.commit()
        await ctx.send(
            f"✅ **{level}** дүнгийн түвшинд {role.mention} role өгөх болно!"
        )


async def setup(bot):
    await bot.add_cog(Levels(bot))
