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
            embed = discord.Embed(
                title="⬆️ Level ахилаа!",
                description=f"{message.author.mention} **{new_lv}** дүнгийн түвшинд хүрлээ! 🎉",
                color=discord.Color.gold()
            )
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
    @app_commands.command(name="profile", description="Өөрийн эсвэл бусдын дэлгэрэнгүй профайл харах")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        await interaction.response.defer()

        user = await get_user(target.id, interaction.guild_id)
        char = await get_char(target.id, interaction.guild_id)

        # ── XP progress bar ───────────────────────────────────────
        needed_xp = xp_for_level(user["level"])
        filled    = round((user["xp"] / needed_xp) * 14) if needed_xp else 0
        xp_bar    = f"`{'█' * filled}{'░' * (14 - filled)}  {user['xp']}/{needed_xp}`"

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Balance leaderboard rank
            cur = await db.execute(
                "SELECT COUNT(*)+1 FROM users WHERE guild_id=? AND balance > ?",
                (interaction.guild_id, user["balance"])
            )
            bal_rank = (await cur.fetchone())[0]

            # Level rank
            cur = await db.execute(
                "SELECT COUNT(*)+1 FROM users WHERE guild_id=?"
                " AND (level > ? OR (level=? AND xp > ?))",
                (interaction.guild_id, user["level"], user["level"], user["xp"])
            )
            lv_rank = (await cur.fetchone())[0]

            # Family
            fam_cur = await db.execute(
                "SELECT * FROM family WHERE user_id=? AND guild_id=?",
                (target.id, interaction.guild_id)
            )
            fam_row = await fam_cur.fetchone()

            # Inventory value
            inv_cur = await db.execute("""
                SELECT COALESCE(SUM(s.price * i.quantity),0) AS total_val,
                       COALESCE(SUM(i.quantity),0)           AS total_qty
                FROM inventory i JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=?
            """, (target.id, interaction.guild_id))
            inv_row = await inv_cur.fetchone()

            # Most expensive vehicle + count
            veh_cur = await db.execute("""
                SELECT s.name, s.emoji, s.price, i.quantity
                FROM inventory i JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='vehicle'
                ORDER BY s.price DESC
            """, (target.id, interaction.guild_id))
            vehicles = await veh_cur.fetchall()

        # ── Family info ───────────────────────────────────────────
        if fam_row:
            sp_id  = fam_row["spouse_id"]
            kids   = json.loads(fam_row["children"] or "[]")
            sp_mem = interaction.guild.get_member(sp_id) if sp_id else None
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
        embed = discord.Embed(
            title=f"👤  {target.display_name}-н профайл",
            color=0xFF4400 if remaining else 0x5865F2
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # XP / Level
        embed.add_field(
            name=f"⭐  Түвшин #{lv_rank}",
            value=f"**{user['level']}** дүнгийн түвшин\n{xp_bar}",
            inline=False
        )

        # Balance (left) + Rank (right)  ← "flex" display
        embed.add_field(
            name="💰  Balance",
            value=f"**{user['balance']:,} ₮**",
            inline=True
        )
        embed.add_field(
            name=f"{medal}  Баялгийн ранк",
            value=f"**#{bal_rank}** серверт",
            inline=True
        )
        embed.add_field(name="​", value="​", inline=True)   # spacer

        # Inventory
        embed.add_field(
            name="🎒  Inventory",
            value=f"{inv_row['total_qty']} зүйл  ≈  {inv_row['total_val']:,} ₮",
            inline=True
        )

        # Family
        embed.add_field(
            name="👨‍👩‍👧  Гэр бүл",
            value=f"{marriage_txt}\n{child_txt}",
            inline=True
        )
        embed.add_field(name="​", value="​", inline=True)

        # Real estate + Vehicles (full-width)
        embed.add_field(
            name="🏠  Үл хөдлөх хөрөнгө",
            value=house_txt,
            inline=True
        )
        embed.add_field(
            name="🚗  Хөдлөх хөрөнгө",
            value=veh_txt,
            inline=True
        )
        embed.add_field(name="​", value="​", inline=True)

        # Prison
        embed.add_field(
            name="🏴  Шорон",
            value=prison_val,
            inline=False
        )

        # ── 🎭 Дүр ───────────────────────────────────────────────
        if char:
            char = dict(char)
            age     = calc_age(char)
            gender  = GENDER_MN.get(char.get("gender",""), "—")
            job_id  = char.get("job_id")
            job_txt = f"{JOBS[job_id]['emoji']} {JOBS[job_id]['name_mn']}" if job_id and job_id in JOBS else "💼 Ажилгүй"

            # Эзэмшсэн мэргэжлүүд — хамгийн үнэтэй 3-г харуулах
            completed = await get_completed_courses(target.id, interaction.guild_id)
            if completed:
                # Курс бүрийг нийт job salary-р эрэмбэлэх
                sorted_courses = sorted(
                    completed,
                    key=lambda c: JOBS.get(COURSES[c]["unlocks"], {}).get("salary", (0,0))[1]
                                  if c in COURSES else 0,
                    reverse=True
                )
                top3   = sorted_courses[:3]
                rest   = len(sorted_courses) - 3
                lines  = [f"{COURSES[c]['emoji']} {COURSES[c]['name_mn']}" for c in top3 if c in COURSES]
                if rest > 0:
                    lines.append(f"*болон {rest} бусад*")
                course_txt = "\n".join(lines)
            else:
                course_txt = "📭 Курс эзэмшээгүй"

            embed.add_field(
                name="🎭  Дүр",
                value=f"{gender}  •  **{age} нас**\n{job_txt}",
                inline=True
            )
            embed.add_field(
                name="🎓  Мэргэжлүүд",
                value=course_txt,
                inline=True
            )
            embed.add_field(name="​", value="​", inline=True)
        else:
            embed.add_field(
                name="🎭  Дүр",
                value="*`/register` командаар дүр үүсгэнэ үү*",
                inline=False
            )

        embed.set_footer(text=f"TOP Bot  •  {target.name}")
        await interaction.followup.send(embed=embed)

    # ── /top ──────────────────────────────────────────────────────
    @app_commands.command(name="top", description="Серверийн TOP 10 идэвхтэй хүмүүс")
    async def leaderboard(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT user_id, level, xp FROM users WHERE guild_id=?"
                " ORDER BY level DESC, xp DESC LIMIT 10",
                (interaction.guild_id,)
            )
            rows = await cur.fetchall()

        embed  = discord.Embed(title="🏆 Идэвхийн жагсаалт TOP 10", color=discord.Color.gold())
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            member = interaction.guild.get_member(row["user_id"])
            name   = member.display_name if member else f"ID:{row['user_id']}"
            medal  = medals[i] if i < 3 else f"**{i+1}.**"
            embed.add_field(
                name=f"{medal} {name}",
                value=f"Түвшин: **{row['level']}** | XP: **{row['xp']}**",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    # ── /level_role_add ───────────────────────────────────────────
    @app_commands.command(name="level_role_add", description="Тодорхой түвшинд role өгөх тохиргоо [Admin]")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO level_roles (guild_id,level,role_id) VALUES (?,?,?)",
                (interaction.guild_id, level, role.id)
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ **{level}** дүнгийн түвшинд {role.mention} role өгөх болно!"
        )


async def setup(bot):
    await bot.add_cog(Levels(bot))
