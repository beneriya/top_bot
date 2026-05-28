import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timedelta
from database import DB_PATH, get_user
from cogs.character import JOBS, COURSES, GENDER_MN, SEXUALITY_MN, calc_age, get_char
from config import WORK_COOLDOWN_MINUTES, BALANCE_CAP, HOURS_PER_GAME_YEAR, OWNER_ID, MANAGER_ROLE_NAME

def admin_only():
    async def predicate(ctx: commands.Context) -> bool:
        guild = ctx.guild
        if guild is None:
            return False
        member = guild.get_member(ctx.author.id)
        if not member or not (member.guild_permissions.administrator or ctx.author.id == OWNER_ID):
            await ctx.send("🚫 Зөвхөн admin ашиглах боломжтой!", ephemeral=True)
            return False
        return True
    return commands.check(predicate)

def manager_only():
    """Admin эсвэл Manager role-той хүн ашиглаж болно."""
    async def predicate(ctx: commands.Context) -> bool:
        guild = ctx.guild
        if guild is None:
            return False
        member = guild.get_member(ctx.author.id)
        if not member:
            return False
        is_admin   = member.guild_permissions.administrator or ctx.author.id == OWNER_ID
        is_manager = any(r.name == MANAGER_ROLE_NAME for r in member.roles)
        if not (is_admin or is_manager):
            await ctx.send(f"🚫 Зөвхөн **Admin** эсвэл **{MANAGER_ROLE_NAME}** role-той хүн ашиглах боломжтой!", ephemeral=True)
            return False
        return True
    return commands.check(predicate)

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
    # 6. virtual children — smart: delete if both parents dead, else transfer
    db.row_factory = aiosqlite.Row
    _children = await (await db.execute(
        "SELECT child_id, parent1_id, parent2_id FROM virtual_children WHERE guild_id=? AND (parent1_id=? OR parent2_id=?)",
        (gid, uid, uid)
    )).fetchall()
    for _ch in _children:
        _other = _ch["parent2_id"] if _ch["parent1_id"] == uid else _ch["parent1_id"]
        _other_alive = False
        if _other and _other != 0:
            _row = await (await db.execute(
                "SELECT 1 FROM character_info WHERE user_id=? AND guild_id=?", (_other, gid)
            )).fetchone()
            _other_alive = _row is not None
        if _other_alive:
            await db.execute(
                "UPDATE virtual_children SET custodian_id=? WHERE child_id=?", (_other, _ch["child_id"])
            )
        else:
            await db.execute("DELETE FROM virtual_children WHERE child_id=?", (_ch["child_id"],))
            await db.execute("DELETE FROM child_calc WHERE child_id=?", (_ch["child_id"],))
    # 7. child_calc (own entries) + child_votes
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
    @commands.hybrid_command(name="adminsetage", description="[Admin] Хэрэглэгчийн насыг тохируулах")
    @app_commands.describe(member="Хэрэглэгч", age="Шинэ нас (5–90)")
    @manager_only()
    async def adminsetage(self, ctx: commands.Context, member: discord.Member, age: int):
        if not 5 <= age <= 90:
            await ctx.send("❌ Нас 5–90 хооронд байх ёстой!", ephemeral=True)
            return
        char = await get_char(member.id, ctx.guild.id)
        if not char:
            await ctx.send(f"❌ **{member.display_name}** дүр үүсгээгүй байна!", ephemeral=True)
            return
        # birth_time-г шинэ насанд тохируулан тооцоолно
        new_birth = datetime.utcnow() - timedelta(hours=age * HOURS_PER_GAME_YEAR)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET birth_time=? WHERE user_id=? AND guild_id=?",
                (new_birth.isoformat(), member.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(
            f"✅ **{member.display_name}**-н насыг **{age}** болголоо.", ephemeral=True
        )

    # ── /adminsetgender ───────────────────────────────────────
    @commands.hybrid_command(name="adminsetgender", description="[Admin] Хэрэглэгчийн хүйсийг солих")
    @app_commands.describe(member="Хэрэглэгч", gender="Хүйс")
    @app_commands.choices(gender=[
        app_commands.Choice(name="👨 Эрэгтэй", value="male"),
        app_commands.Choice(name="👩 Эмэгтэй", value="female"),
    ])
    @manager_only()
    async def adminsetgender(self, ctx: commands.Context, member: discord.Member, gender: str):
        char = await get_char(member.id, ctx.guild.id)
        if not char:
            await ctx.send(f"❌ **{member.display_name}** дүр үүсгээгүй байна!", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET gender=? WHERE user_id=? AND guild_id=?",
                (gender, member.id, ctx.guild.id)
            )
            await db.commit()
        label = GENDER_MN.get(gender, gender)
        await ctx.send(
            f"✅ **{member.display_name}**-н хүйсийг **{label}** болголоо.", ephemeral=True
        )

    # ── /adminsetsexuality ────────────────────────────────────
    @commands.hybrid_command(name="adminsetsexuality", description="[Admin] Хэрэглэгчийн чиг баримжааг солих")
    @app_commands.describe(member="Хэрэглэгч", sexuality="Чиг баримжаа")
    @app_commands.choices(sexuality=[
        app_commands.Choice(name="💑 Straight", value="straight"),
        app_commands.Choice(name="🏳️‍🌈 Геи / Лесбиян", value="gay"),
        app_commands.Choice(name="💜 Бисексуал",      value="bisexual"),
    ])
    @manager_only()
    async def adminsetsexuality(self, ctx: commands.Context, member: discord.Member, sexuality: str):
        char = await get_char(member.id, ctx.guild.id)
        if not char:
            await ctx.send(f"❌ **{member.display_name}** дүр үүсгээгүй байна!", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET sexuality=? WHERE user_id=? AND guild_id=?",
                (sexuality, member.id, ctx.guild.id)
            )
            await db.commit()
        label = SEXUALITY_MN.get(sexuality, sexuality)
        await ctx.send(
            f"✅ **{member.display_name}**-н чиг баримжааг **{label}** болголоо.", ephemeral=True
        )

    # ── /adminsetjob ──────────────────────────────────────────
    @commands.hybrid_command(name="adminsetjob", description="[Admin] Ажлыг cooldown алгасаад тохируулах")
    @app_commands.describe(member="Хэрэглэгч", job="Ажлын ID")
    @manager_only()
    async def adminsetjob(self, ctx: commands.Context, member: discord.Member, job: str):
        if job not in JOBS and job != "none":
            await ctx.send(
                f"❌ Тийм ажил байхгүй! Боломжит ажлууд: {', '.join(JOBS.keys())}", ephemeral=True
            )
            return
        job_val = None if job == "none" else job
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE character_info SET job_id=?, last_setjob=NULL WHERE user_id=? AND guild_id=?",
                (job_val, member.id, ctx.guild.id)
            )
            # Курс шаардсан ажил бол user_courses-д бас нэмэх
            if job_val:
                required_course = JOBS[job_val].get("course")
                if required_course:
                    from datetime import datetime as _dt
                    await db.execute(
                        "INSERT OR IGNORE INTO user_courses (user_id, guild_id, course_name, completed_at) VALUES (?,?,?,?)",
                        (member.id, ctx.guild.id, required_course, _dt.utcnow().isoformat())
                    )
            await db.commit()
        job_name = JOBS[job]["name_mn"] if job != "none" else "Ажилгүй"
        await ctx.send(
            f"✅ **{member.display_name}**-н ажлыг **{job_name}** болголоо.", ephemeral=True
        )


    # ── /adminremovecourse ────────────────────────────────────
    @commands.hybrid_command(name="adminremovecourse", description="[Admin] Хэрэглэгчийн сурсан курс хүчингүй болгох")
    @app_commands.describe(member="Хэрэглэгч", course="Курсын ID (programming/cooking/driving/medical/teaching/law/accounting/business/engineering)")
    @manager_only()
    async def adminremovecourse(self, ctx: commands.Context, member: discord.Member, course: str):
        from cogs.character import COURSES
        # Ажлын нэрээр оруулсан бол (programmer → programming) автоматаар хөрвүүлэх
        if course not in COURSES:
            job_data = JOBS.get(course)
            if job_data and job_data.get("course"):
                course = job_data["course"]
            else:
                await ctx.send(
                    f"❌ Тийм курс байхгүй!\n"
                    f"Курсын нэр: `{'`, `'.join(COURSES.keys())}`\n"
                    f"Ажлын нэр: `{'`, `'.join(j for j,d in JOBS.items() if d.get('course'))}`",
                    ephemeral=True
                )
                return
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            # user_courses-д бичлэг байгаа эсэхийг шалгах
            course_row = await (await db.execute(
                "SELECT course_name FROM user_courses WHERE user_id=? AND guild_id=? AND course_name=?",
                (member.id, ctx.guild.id, course)
            )).fetchone()
            # job_id тохирч байгаа эсэхийг шалгах
            char_row = await (await db.execute(
                "SELECT job_id FROM character_info WHERE user_id=? AND guild_id=?",
                (member.id, ctx.guild.id)
            )).fetchone()
            job_matches = char_row and JOBS.get(char_row["job_id"], {}).get("course") == course

            if not course_row and not job_matches:
                await ctx.send(
                    f"❌ **{member.display_name}** энэ курсыг суралцаагүй, мөн тохирох ажил байхгүй байна.",
                    ephemeral=True
                )
                return

            # user_courses-с устгах (байвал)
            await db.execute(
                "DELETE FROM user_courses WHERE user_id=? AND guild_id=? AND course_name=?",
                (member.id, ctx.guild.id, course)
            )
            # Ажил тохирч байвал NULL болгох
            if job_matches:
                await db.execute(
                    "UPDATE character_info SET job_id=NULL WHERE user_id=? AND guild_id=?",
                    (member.id, ctx.guild.id)
                )
            await db.commit()

        cdata = COURSES[course]
        job_note = " Ажлыг нь хасав." if job_matches else ""
        await ctx.send(
            f"✅ **{member.display_name}**-н **{cdata['name_mn']}** курс хүчингүй болголоо.{job_note}",
            ephemeral=True
        )

    # ── /adminkill ────────────────────────────────────────────
    @commands.hybrid_command(name="adminkill", description="[Admin] Дүрийн бүх мэдээлэл database-с устгах")
    @app_commands.describe(member="Хэрэглэгч")
    @admin_only()
    async def adminkill(self, ctx: commands.Context, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await _full_wipe(member.id, ctx.guild.id, db)
        await ctx.send(
            f"💀 **{member.display_name}**-н бүх мэдээлэл (character, users, inventory, family, rpg) устгагдлаа.",
            ephemeral=True
        )

    # ── /adminsetbalance ──────────────────────────────────────
    @commands.hybrid_command(name="adminsetbalance", description="[Admin] Балансыг яг тохируулах")
    @app_commands.describe(member="Хэрэглэгч", amount="Шинэ баланс")
    @admin_only()
    async def adminsetbalance(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount < 0:
            await ctx.send("❌ Баланс 0-с бага байж болохгүй!", ephemeral=True)
            return
        amount = min(amount, BALANCE_CAP)
        await get_user(member.id, ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET balance=? WHERE user_id=? AND guild_id=?",
                (amount, member.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(
            f"✅ **{member.display_name}**-н балансыг **{amount:,} ₮** болголоо.", ephemeral=True
        )

    # ── /adminaddbalance ──────────────────────────────────────
    @commands.hybrid_command(name="adminaddbalance", description="[Admin] Мөнгө нэмэх/хасах (сөрөг тоо хасна)")
    @app_commands.describe(member="Хэрэглэгч", amount="Нэмэх/хасах дүн")
    @admin_only()
    async def adminaddbalance(self, ctx: commands.Context, member: discord.Member, amount: int):
        await get_user(member.id, ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "UPDATE users SET balance=MIN(?,MAX(0,balance+?)) WHERE user_id=? AND guild_id=?",
                (BALANCE_CAP, amount, member.id, ctx.guild.id)
            )
            await db.commit()
            row = await (await db.execute(
                "SELECT balance FROM users WHERE user_id=? AND guild_id=?",
                (member.id, ctx.guild.id)
            )).fetchone()
        sign = "+" if amount >= 0 else ""
        await ctx.send(
            f"✅ **{member.display_name}**: {sign}{amount:,} ₮ → Шинэ баланс: **{row['balance']:,} ₮**", ephemeral=True
        )

    # ── /adminsetlevel ────────────────────────────────────────
    @commands.hybrid_command(name="adminsetlevel", description="[Admin] Level тохируулах")
    @app_commands.describe(member="Хэрэглэгч", level="Шинэ level (1–100)")
    @manager_only()
    async def adminsetlevel(self, ctx: commands.Context, member: discord.Member, level: int):
        if not 1 <= level <= 100:
            await ctx.send("❌ Level 1–100 хооронд байх ёстой!", ephemeral=True)
            return
        await get_user(member.id, ctx.guild.id)
        xp_for_level = level * level * 100
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET level=?, xp=? WHERE user_id=? AND guild_id=?",
                (level, xp_for_level, member.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(
            f"✅ **{member.display_name}**-н level-г **{level}** болголоо.", ephemeral=True
        )

    # ── /adminresetchar ───────────────────────────────────────
    @commands.hybrid_command(name="adminresetchar", description="[Admin] Дүрийн бүх мэдээлэл цэвэрлэх")
    @app_commands.describe(member="Хэрэглэгч")
    @admin_only()
    async def adminresetchar(self, ctx: commands.Context, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await _full_wipe(member.id, ctx.guild.id, db)
        await ctx.send(
            f"✅ **{member.display_name}**-н бүх мэдээлэл цэвэрлэгдлээ. `/register` дахин хийх боломжтой.",
            ephemeral=True
        )

    # ── /adminsetprison ───────────────────────────────────────
    @commands.hybrid_command(name="adminsetprison", description="[Admin] Хэрэглэгчийг шоронд хийх")
    @app_commands.describe(member="Хэрэглэгч", minutes="Хугацаа (минутаар)")
    @manager_only()
    async def adminsetprison(self, ctx: commands.Context, member: discord.Member, minutes: int):
        if minutes <= 0:
            await ctx.send("❌ Хугацаа 0-с их байх ёстой!", ephemeral=True)
            return
        release = datetime.utcnow() + timedelta(minutes=minutes)
        await get_user(member.id, ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET prison_until=?, prison_count=COALESCE(prison_count,0)+1 WHERE user_id=? AND guild_id=?",
                (release.isoformat(), member.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(
            f"🚔 **{member.display_name}** **{minutes} минут**-аар шоронд орлоо.", ephemeral=True
        )

    # ── /adminresetcooldown ───────────────────────────────────
    @commands.hybrid_command(name="adminresetcooldown", description="[Admin] Work/daily/setjob/hack/rob cooldown бүгдийг цэвэрлэх")
    @app_commands.describe(member="Хэрэглэгч")
    @manager_only()
    async def adminresetcooldown(self, ctx: commands.Context, member: discord.Member):
        await get_user(member.id, ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET last_work=NULL, last_daily=NULL, hack_cooldown=NULL, rob_cooldown=NULL "
                "WHERE user_id=? AND guild_id=?",
                (member.id, ctx.guild.id)
            )
            await db.execute(
                "UPDATE character_info SET last_setjob=NULL WHERE user_id=? AND guild_id=?",
                (member.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(
            f"✅ **{member.display_name}**-н work / daily / setjob / hack / rob cooldown бүгд цэвэрлэгдлээ.",
            ephemeral=True
        )


    # ── /setvirtualchild ──────────────────────────────────────
    @commands.hybrid_command(name="setvirtualchild", description="[Admin] Хосод виртуал хүүхэд нэмэх")
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
            await ctx.send("Эцэг/эх хоёр ижил хүн байж болохгүй!", ephemeral=True)
            return

        # Хоёулаа гэрлэсэн байх ёстой (гэрлэлтийн нийцтэй байдал шалгах)
        from database import get_family as _gf
        fam1 = await _gf(parent1.id, ctx.guild.id)
        fam2 = await _gf(parent2.id, ctx.guild.id)
        if fam1.get("spouse_id") != parent2.id or fam2.get("spouse_id") != parent1.id:
            await ctx.send(
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
                (ctx.guild.id, p1, p2, sel_name, sel_gender, birth_time),
            )
            await db.commit()

        gender_mn = "Хөвгүүн" if sel_gender == "male" else "Охин"
        await ctx.send(
            f"👶 **{sel_name}** ({gender_mn}) — {parent1.display_name} & {parent2.display_name}-н хүүхдэд нэмэгдлээ!",
            ephemeral=True,
        )


    # ── /admingivechild ───────────────────────────────────────
    @commands.hybrid_command(name="admingivechild", description="[Admin] Нэг гишүүнд виртуал хүүхэд оноох")
    @app_commands.describe(
        parent="Эцэг/Эх болох хэрэглэгч",
        name="Хүүхдийн нэр (хоосон бол санамсаргүй)",
        gender="Хүйс (хоосон бол санамсаргүй)",
    )
    @app_commands.choices(gender=[
        app_commands.Choice(name="Хөвгүүн", value="male"),
        app_commands.Choice(name="Охин",    value="female"),
    ])
    @admin_only()
    async def admingivechild(
        self,
        interaction: discord.Interaction,
        parent: discord.Member,
        name: str = "",
        gender: str = "",
    ):
        from cogs.character import CHILD_NAMES
        import random as _random

        sel_gender = gender if gender in ("male", "female") else _random.choice(["male", "female"])
        sel_name   = name.strip() if name.strip() else _random.choice(CHILD_NAMES[sel_gender])
        birth_time = datetime.utcnow().isoformat()

        # parent2_id = 0 → ганц эцэг/эх (sentinel)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO virtual_children "
                "(guild_id,parent1_id,parent2_id,name,gender,birth_time,college,custodian_id) "
                "VALUES (?,?,0,?,?,?,0,NULL)",
                (ctx.guild.id, parent.id, sel_name, sel_gender, birth_time),
            )
            await db.commit()

        gender_mn = "Хөвгүүн" if sel_gender == "male" else "Охин"
        gender_mn = "Хөвгүүн" if sel_gender == "male" else "Охин"
        await ctx.send(
            f"👶 **{sel_name}** ({gender_mn}) — {parent.display_name}-д оноогдлоо!",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Admin(bot))
