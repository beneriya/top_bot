import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timedelta
from database import DB_PATH, get_user
from cogs.character import JOBS, COURSES, GENDER_MN, SEXUALITY_MN, calc_age, get_char
from config import WORK_COOLDOWN_MINUTES, BALANCE_CAP, HOURS_PER_GAME_YEAR

def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild and interaction.guild.get_member(interaction.user.id):
            if interaction.guild.get_member(interaction.user.id).guild_permissions.administrator:
                return True
        await interaction.response.send_message("🚫 Зөвхөн admin ашиглах боломжтой!", ephemeral=True)
        return False
    return app_commands.check(predicate)

async def _full_wipe(uid: int, gid: int, db):
    """Хэрэглэгчийн бүх мэдээллийг database-с арилгах."""
    # 1. character_info + courses
    await db.execute("DELETE FROM character_info WHERE user_id=? AND guild_id=?", (uid, gid))
    await db.execute("DELETE FROM user_courses   WHERE user_id=? AND guild_id=?", (uid, gid))
    # 2. users row (balance, bank, level, xp, cooldowns …)
    await db.execute("DELETE FROM users          WHERE user_id=? AND guild_id=?", (uid, gid))
    # 3. inventory
    await db.execute("DELETE FROM inventory      WHERE user_id=? AND guild_id=?", (uid, gid))
    # 4. family row + clear spouse reference
    await db.execute("UPDATE family SET spouse_id=NULL WHERE spouse_id=? AND guild_id=?", (uid, gid))
    await db.execute("DELETE FROM family         WHERE user_id=? AND guild_id=?", (uid, gid))
    # 5. rpg
    await db.execute("DELETE FROM rpg            WHERE user_id=? AND guild_id=?", (uid, gid))
    # 6. virtual children custody transfer → other parent keeps them
    await db.execute("""
        UPDATE virtual_children
        SET custodian_id = CASE
            WHEN parent1_id=? THEN parent2_id
            ELSE parent1_id
        END
        WHERE guild_id=? AND (parent1_id=? OR parent2_id=?)
    """, (uid, gid, uid, uid))
    # 7. child_calc + child_votes
    await db.execute("DELETE FROM child_calc  WHERE parent_id=?",  (uid,))
    await db.execute("""
        DELETE FROM child_votes
        WHERE guild_id=? AND (parent1_id=? OR parent2_id=?)
    """, (gid, uid, uid))
    await db.commit()


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /adminsetage ──────────────────────────────────────────
    @app_commands.command(name="adminsetage", description="[Admin] Хэрэглэгчийн насыг тохируулах")
    @app_commands.describe(member="Хэрэглэгч", age="Шинэ нас (5–90)")
    @admin_only()
    async def adminsetage(self, interaction: discord.Interaction, member: discord.Member, age: int):
        if not 5 <= age <= 90:
            await interaction.response.send_message("❌ Нас 5–90 хооронд байх ёстой!", ephemeral=True)
            return
        char = await get_char(member.id, interaction.guild_id)
        if not char:
            await interaction.response.send_message(f"❌ **{member.display_name}** дүр үүсгээгүй байна!", ephemeral=True)
            return
        # birth_time-г шинэ насанд тохируулан тооцоолно
        new_birth = datetime.utcnow() - timedelta(hours=age * HOURS_PER_GAME_YEAR)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET birth_time=? WHERE user_id=? AND guild_id=?",
                (new_birth.isoformat(), member.id, interaction.guild_id)
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н насыг **{age}** болголоо.", ephemeral=True
        )

    # ── /adminsetgender ───────────────────────────────────────
    @app_commands.command(name="adminsetgender", description="[Admin] Хэрэглэгчийн хүйсийг солих")
    @app_commands.describe(member="Хэрэглэгч", gender="Хүйс")
    @app_commands.choices(gender=[
        app_commands.Choice(name="👨 Эрэгтэй", value="male"),
        app_commands.Choice(name="👩 Эмэгтэй", value="female"),
    ])
    @admin_only()
    async def adminsetgender(self, interaction: discord.Interaction, member: discord.Member, gender: str):
        char = await get_char(member.id, interaction.guild_id)
        if not char:
            await interaction.response.send_message(f"❌ **{member.display_name}** дүр үүсгээгүй байна!", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET gender=? WHERE user_id=? AND guild_id=?",
                (gender, member.id, interaction.guild_id)
            )
            await db.commit()
        label = GENDER_MN.get(gender, gender)
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н хүйсийг **{label}** болголоо.", ephemeral=True
        )

    # ── /adminsetsexuality ────────────────────────────────────
    @app_commands.command(name="adminsetsexuality", description="[Admin] Хэрэглэгчийн чиг баримжааг солих")
    @app_commands.describe(member="Хэрэглэгч", sexuality="Чиг баримжаа")
    @app_commands.choices(sexuality=[
        app_commands.Choice(name="💑 Straight", value="straight"),
        app_commands.Choice(name="🏳️‍🌈 Геи / Лесбиян", value="gay"),
        app_commands.Choice(name="💜 Бисексуал",      value="bisexual"),
    ])
    @admin_only()
    async def adminsetsexuality(self, interaction: discord.Interaction, member: discord.Member, sexuality: str):
        char = await get_char(member.id, interaction.guild_id)
        if not char:
            await interaction.response.send_message(f"❌ **{member.display_name}** дүр үүсгээгүй байна!", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET sexuality=? WHERE user_id=? AND guild_id=?",
                (sexuality, member.id, interaction.guild_id)
            )
            await db.commit()
        label = SEXUALITY_MN.get(sexuality, sexuality)
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н чиг баримжааг **{label}** болголоо.", ephemeral=True
        )

    # ── /adminsetjob ──────────────────────────────────────────
    @app_commands.command(name="adminsetjob", description="[Admin] Ажлыг cooldown алгасаад тохируулах")
    @app_commands.describe(member="Хэрэглэгч", job="Ажлын ID")
    @admin_only()
    async def adminsetjob(self, interaction: discord.Interaction, member: discord.Member, job: str):
        if job not in JOBS and job != "none":
            await interaction.response.send_message(
                f"❌ Тийм ажил байхгүй! Боломжит ажлууд: {', '.join(JOBS.keys())}", ephemeral=True
            )
            return
        job_val = None if job == "none" else job
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET job_id=?, last_setjob=NULL WHERE user_id=? AND guild_id=?",
                (job_val, member.id, interaction.guild_id)
            )
            await db.commit()
        job_name = JOBS[job]["name_mn"] if job != "none" else "Ажилгүй"
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н ажлыг **{job_name}** болголоо.", ephemeral=True
        )


    # ── /adminkill ────────────────────────────────────────────
    @app_commands.command(name="adminkill", description="[Admin] Дүрийн бүх мэдээлэл database-с устгах")
    @app_commands.describe(member="Хэрэглэгч")
    @admin_only()
    async def adminkill(self, interaction: discord.Interaction, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await _full_wipe(member.id, interaction.guild_id, db)
        await interaction.response.send_message(
            f"💀 **{member.display_name}**-н бүх мэдээлэл (character, users, inventory, family, rpg) устгагдлаа.",
            ephemeral=True
        )

    # ── /adminsetbalance ──────────────────────────────────────
    @app_commands.command(name="adminsetbalance", description="[Admin] Балансыг яг тохируулах")
    @app_commands.describe(member="Хэрэглэгч", amount="Шинэ баланс")
    @admin_only()
    async def adminsetbalance(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount < 0:
            await interaction.response.send_message("❌ Баланс 0-с бага байж болохгүй!", ephemeral=True)
            return
        amount = min(amount, BALANCE_CAP)
        await get_user(member.id, interaction.guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET balance=? WHERE user_id=? AND guild_id=?",
                (amount, member.id, interaction.guild_id)
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н балансыг **{amount:,} ₮** болголоо.", ephemeral=True
        )

    # ── /adminaddbalance ──────────────────────────────────────
    @app_commands.command(name="adminaddbalance", description="[Admin] Мөнгө нэмэх/хасах (сөрөг тоо хасна)")
    @app_commands.describe(member="Хэрэглэгч", amount="Нэмэх/хасах дүн")
    @admin_only()
    async def adminaddbalance(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await get_user(member.id, interaction.guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "UPDATE users SET balance=MIN(?,MAX(0,balance+?)) WHERE user_id=? AND guild_id=?",
                (BALANCE_CAP, amount, member.id, interaction.guild_id)
            )
            await db.commit()
            row = await (await db.execute(
                "SELECT balance FROM users WHERE user_id=? AND guild_id=?",
                (member.id, interaction.guild_id)
            )).fetchone()
        sign = "+" if amount >= 0 else ""
        await interaction.response.send_message(
            f"✅ **{member.display_name}**: {sign}{amount:,} ₮ → Шинэ баланс: **{row['balance']:,} ₮**", ephemeral=True
        )

    # ── /adminsetlevel ────────────────────────────────────────
    @app_commands.command(name="adminsetlevel", description="[Admin] Level тохируулах")
    @app_commands.describe(member="Хэрэглэгч", level="Шинэ level (1–100)")
    @admin_only()
    async def adminsetlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        if not 1 <= level <= 100:
            await interaction.response.send_message("❌ Level 1–100 хооронд байх ёстой!", ephemeral=True)
            return
        await get_user(member.id, interaction.guild_id)
        xp_for_level = level * level * 100
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET level=?, xp=? WHERE user_id=? AND guild_id=?",
                (level, xp_for_level, member.id, interaction.guild_id)
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н level-г **{level}** болголоо.", ephemeral=True
        )

    # ── /adminresetchar ───────────────────────────────────────
    @app_commands.command(name="adminresetchar", description="[Admin] Дүрийн бүх мэдээлэл цэвэрлэх")
    @app_commands.describe(member="Хэрэглэгч")
    @admin_only()
    async def adminresetchar(self, interaction: discord.Interaction, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await _full_wipe(member.id, interaction.guild_id, db)
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н бүх мэдээлэл цэвэрлэгдлээ. `/register` дахин хийх боломжтой.",
            ephemeral=True
        )

    # ── /adminsetprison ───────────────────────────────────────
    @app_commands.command(name="adminsetprison", description="[Admin] Хэрэглэгчийг шоронд хийх")
    @app_commands.describe(member="Хэрэглэгч", minutes="Хугацаа (минутаар)")
    @admin_only()
    async def adminsetprison(self, interaction: discord.Interaction, member: discord.Member, minutes: int):
        if minutes <= 0:
            await interaction.response.send_message("❌ Хугацаа 0-с их байх ёстой!", ephemeral=True)
            return
        release = datetime.utcnow() + timedelta(minutes=minutes)
        await get_user(member.id, interaction.guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET prison_until=? WHERE user_id=? AND guild_id=?",
                (release.isoformat(), member.id, interaction.guild_id)
            )
            await db.commit()
        await interaction.response.send_message(
            f"🚔 **{member.display_name}** **{minutes} минут**-аар шоронд орлоо.", ephemeral=True
        )

    # ── /adminresetcooldown ───────────────────────────────────
    @app_commands.command(name="adminresetcooldown", description="[Admin] Work/setjob cooldown цэвэрлэх")
    @app_commands.describe(member="Хэрэглэгч")
    @admin_only()
    async def adminresetcooldown(self, interaction: discord.Interaction, member: discord.Member):
        await get_user(member.id, interaction.guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET last_work=NULL, last_daily=NULL WHERE user_id=? AND guild_id=?",
                (member.id, interaction.guild_id)
            )
            await db.commit()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET last_setjob=NULL WHERE user_id=? AND guild_id=?",
                (member.id, interaction.guild_id)
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ **{member.display_name}**-н work/setjob/daily cooldown цэвэрлэгдлээ.", ephemeral=True
        )


    # ── /setvirtualchild ──────────────────────────────────────
    @app_commands.command(name="setvirtualchild", description="[Admin] Хосод виртуал хүүхэд нэмэх")
    @app_commands.describe(
        parent1="Эцэг/Эх 1",
        parent2="Эцэг/Эх 2",
        name="Хүүхдийн нэр (хоосон бол санамсаргүй)",
        gender="Хүйс (хоосон бол санамсаргүй)",
    )
    @app_commands.choices(gender=[
        app_commands.Choice(name="Хөвгүүн", value="male"),
        app_commands.Choice(name="Охин",    value="female"),
    ])
    @admin_only()
    async def setvirtualchild(
        self,
        interaction: discord.Interaction,
        parent1: discord.Member,
        parent2: discord.Member,
        name: str = "",
        gender: str = "",
    ):
        from cogs.character import CHILD_NAMES
        import random as _random

        if parent1.id == parent2.id:
            await interaction.response.send_message("Эцэг/эх хоёр ижил хүн байж болохгүй!", ephemeral=True)
            return

        # Хоёулаа гэрлэсэн байх ёстой (гэрлэлтийн нийцтэй байдал шалгах)
        from database import get_family as _gf
        fam1 = await _gf(parent1.id, interaction.guild_id)
        fam2 = await _gf(parent2.id, interaction.guild_id)
        if fam1.get("spouse_id") != parent2.id or fam2.get("spouse_id") != parent1.id:
            await interaction.response.send_message(
                f"❌ **{parent1.display_name}** болон **{parent2.display_name}** гэрлэсэн байх ёстой!",
                ephemeral=True
            )
            return

        sel_gender = gender if gender in ("male", "female") else _random.choice(["male", "female"])
        sel_name   = name.strip() if name.strip() else _random.choice(CHILD_NAMES[sel_gender])
        p1, p2     = (parent1.id, parent2.id) if parent1.id < parent2.id else (parent2.id, parent1.id)
        birth_time = datetime.utcnow().isoformat()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO virtual_children "
                "(guild_id,parent1_id,parent2_id,name,gender,birth_time,college,custodian_id) "
                "VALUES (?,?,?,?,?,?,0,NULL)",
                (interaction.guild_id, p1, p2, sel_name, sel_gender, birth_time),
            )
            await db.commit()

        gender_mn = "Хөвгүүн" if sel_gender == "male" else "Охин"
        await interaction.response.send_message(
            f"👶 **{sel_name}** ({gender_mn}) — {parent1.display_name} & {parent2.display_name}-н хүүхдэд нэмэгдлээ!",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Admin(bot))
