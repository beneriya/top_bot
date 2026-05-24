import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import json
from database import DB_PATH, get_user, update_balance, get_family
from cogs.character import (get_char, can_marry_check, GENDER_MN, SEXUALITY_MN,
                             calc_age_dt, CHILD_NAMES, CHILD_COLLEGE_COST,
                             CHILD_COST_PER_YEAR, CHILD_EARN_NO_COLLEGE, CHILD_EARN_COLLEGE)
from config import HOUSES, HOUSE_SELL_RATIO, HOUSE_UPGRADE_RATIO, HOURS_PER_GAME_YEAR
from datetime import datetime


# ── Virtual children helpers ──────────────────────────────────────
async def get_virtual_children(guild_id: int, p1_id: int, p2_id: int) -> list:
    """Return virtual_children rows for a couple (always stored with smaller id first)."""
    a, b = (p1_id, p2_id) if p1_id < p2_id else (p2_id, p1_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM virtual_children WHERE guild_id=? AND parent1_id=? AND parent2_id=?",
            (guild_id, a, b),
        )
        return [dict(r) for r in await cur.fetchall()]


async def process_child_economics(user_id: int, guild_id: int, db) -> int:
    """
    Calculate accumulated child costs/earnings since last check.
    Applies to virtual children where user is a custodial parent.
    Returns the net balance delta (can be negative for costs).
    Handles age boundary: cost for <16, earnings for 16+, split properly.
    """
    db.row_factory = aiosqlite.Row
    cur = await db.execute("""
        SELECT vc.child_id, vc.birth_time, vc.college, vc.custodian_id,
               cc.last_calc
        FROM virtual_children vc
        LEFT JOIN child_calc cc ON cc.child_id=vc.child_id AND cc.parent_id=?
        WHERE vc.guild_id=?
          AND (vc.parent1_id=? OR vc.parent2_id=?)
          AND (vc.custodian_id IS NULL OR vc.custodian_id=?)
    """, (user_id, guild_id, user_id, user_id, user_id))
    children = await cur.fetchall()

    now       = datetime.utcnow()
    delta     = 0
    MAX_YEARS = 30  # cap per check

    for child in children:
        child_age = calc_age_dt(child["birth_time"])
        if child_age >= 32:
            continue

        lc = child["last_calc"]
        if not lc:
            # First time: just record timestamp, no charge yet
            await db.execute("""
                INSERT INTO child_calc (child_id, parent_id, last_calc)
                VALUES (?,?,?)
                ON CONFLICT(child_id, parent_id) DO UPDATE SET last_calc=excluded.last_calc
            """, (child["child_id"], user_id, now.isoformat()))
            continue

        elapsed_h = min(
            (now - datetime.fromisoformat(lc)).total_seconds() / 3600,
            MAX_YEARS * HOURS_PER_GAME_YEAR
        )
        elapsed_years = elapsed_h / HOURS_PER_GAME_YEAR
        if elapsed_years < 0.01:
            continue

        # Age at last_calc vs now — split cost/earn at age 16 boundary
        birth_dt   = datetime.fromisoformat(child["birth_time"])
        last_dt    = datetime.fromisoformat(lc)
        age_at_lc  = (last_dt  - birth_dt).total_seconds() / 3600 / HOURS_PER_GAME_YEAR
        age_at_now = (now       - birth_dt).total_seconds() / 3600 / HOURS_PER_GAME_YEAR

        ADULT_AGE  = 16.0
        rate_earn  = CHILD_EARN_COLLEGE if child["college"] else CHILD_EARN_NO_COLLEGE

        if age_at_lc >= ADULT_AGE:
            # Whole period: earning
            delta += int(rate_earn * elapsed_years)
        elif age_at_now < ADULT_AGE:
            # Whole period: cost
            delta -= int(CHILD_COST_PER_YEAR * elapsed_years)
        else:
            # Split: cost until 16, earn after 16
            cost_years = ADULT_AGE - age_at_lc
            earn_years = age_at_now - ADULT_AGE
            delta -= int(CHILD_COST_PER_YEAR * cost_years)
            delta += int(rate_earn * earn_years)

        await db.execute("""
            INSERT INTO child_calc (child_id, parent_id, last_calc)
            VALUES (?,?,?)
            ON CONFLICT(child_id, parent_id) DO UPDATE SET last_calc=excluded.last_calc
        """, (child["child_id"], user_id, now.isoformat()))

    return delta


# ══════════════════════════════════════════════════════════════
#  Marriage UI
# ══════════════════════════════════════════════════════════════
class MarriageView(discord.ui.View):
    def __init__(self, proposer: discord.Member, target: discord.Member,
                 ring_item_id: int, ring_qty: int, guild_id: int):
        super().__init__(timeout=60)
        self.proposer   = proposer
        self.target     = target
        self.ring_item_id = ring_item_id
        self.ring_qty   = ring_qty
        self.guild_id   = guild_id
        self.done       = False

    async def _finish(self, interaction: discord.Interaction, accepted: bool):
        if self.done:
            return
        self.done = True
        self.stop()

        if accepted:
            async with aiosqlite.connect(DB_PATH) as db:
                # Consume ring from proposer
                if self.ring_qty > 1:
                    await db.execute(
                        "UPDATE inventory SET quantity=quantity-1 WHERE item_id=? AND user_id=? AND guild_id=?",
                        (self.ring_item_id, self.proposer.id, self.guild_id)
                    )
                else:
                    await db.execute(
                        "DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?",
                        (self.ring_item_id, self.proposer.id, self.guild_id)
                    )
                # Link spouses + record marriage time
                _now = datetime.utcnow().isoformat()
                await db.execute(
                    "UPDATE family SET spouse_id=?, married_at=? WHERE user_id=? AND guild_id=?",
                    (self.target.id, _now, self.proposer.id, self.guild_id)
                )
                await db.execute(
                    "UPDATE family SET spouse_id=?, married_at=? WHERE user_id=? AND guild_id=?",
                    (self.proposer.id, _now, self.target.id, self.guild_id)
                )
                await db.commit()

            embed = discord.Embed(
                title="💒 Гэрлэлт баталгаажлаа!",
                description=(
                    f"🎊 **{self.proposer.display_name}** болон **{self.target.display_name}** гэрлэллээ!\n"
                    f"Аз жаргалтай амьдралыг хүсье! 💍"
                ),
                color=discord.Color.pink()
            )
        else:
            embed = discord.Embed(
                title="💔 Санал татгалзлаа",
                description=f"**{self.target.display_name}** гэрлэлтийн саналаас татгалзлаа.",
                color=discord.Color.red()
            )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Зөвшөөрөх 💍", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Энэ санал танд хамааралгүй!", ephemeral=True)
            return
        await self._finish(interaction, True)

    @discord.ui.button(label="Татгалзах ❌", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Энэ санал танд хамааралгүй!", ephemeral=True)
            return
        await self._finish(interaction, False)

    async def on_timeout(self):
        self.done = True


# ══════════════════════════════════════════════════════════════
#  Adoption UI
# ══════════════════════════════════════════════════════════════
class AdoptView(discord.ui.View):
    def __init__(self, parent: discord.Member, child: discord.Member,
                 doc_item_id: int, doc_qty: int, guild_id: int):
        super().__init__(timeout=60)
        self.parent      = parent
        self.child       = child
        self.doc_item_id = doc_item_id
        self.doc_qty     = doc_qty
        self.guild_id    = guild_id
        self.done        = False

    async def _finish(self, interaction: discord.Interaction, accepted: bool):
        if self.done:
            return
        self.done = True
        self.stop()

        if accepted:
            parent_fam = await get_family(self.parent.id, self.guild_id)
            children   = json.loads(parent_fam["children"] or "[]")
            children.append(self.child.id)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE family SET children=? WHERE user_id=? AND guild_id=?",
                    (json.dumps(children), self.parent.id, self.guild_id)
                )
                await db.execute(
                    "UPDATE family SET parent_id=? WHERE user_id=? AND guild_id=?",
                    (self.parent.id, self.child.id, self.guild_id)
                )
                if self.doc_qty > 1:
                    await db.execute(
                        "UPDATE inventory SET quantity=quantity-1 WHERE item_id=? AND user_id=? AND guild_id=?",
                        (self.doc_item_id, self.parent.id, self.guild_id)
                    )
                else:
                    await db.execute(
                        "DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?",
                        (self.doc_item_id, self.parent.id, self.guild_id)
                    )
                await db.commit()

            embed = discord.Embed(
                title="🎊 Үрчлэлт баталгаажлаа!",
                description=f"**{self.parent.display_name}** **{self.child.display_name}**-г үрчлэн авлаа! 🍼",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="❌ Үрчлэлтийн санал татгалзлаа",
                description=f"**{self.child.display_name}** үрчлэгдэхээс татгалзлаа.",
                color=discord.Color.red()
            )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Зөвшөөрөх ✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.child.id:
            await interaction.response.send_message("❌ Энэ санал танд хамааралгүй!", ephemeral=True)
            return
        await self._finish(interaction, True)

    @discord.ui.button(label="Татгалзах ❌", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.child.id:
            await interaction.response.send_message("❌ Энэ санал танд хамааралгүй!", ephemeral=True)
            return
        await self._finish(interaction, False)

    async def on_timeout(self):
        self.done = True


# ══════════════════════════════════════════════════════════════
#  Divorce custody View
# ══════════════════════════════════════════════════════════════
class DivorceView(discord.ui.View):
    def __init__(self, user_id: int, spouse_id: int, vchildren: list, guild_id: int):
        super().__init__(timeout=60)
        self.user_id   = user_id
        self.spouse_id = spouse_id
        self.vchildren = vchildren
        self.guild_id  = guild_id

    async def _do_divorce(self, interaction: discord.Interaction, keeper_id: int):
        loser_id = self.spouse_id if keeper_id == self.user_id else self.user_id
        a, b = (self.user_id, self.spouse_id) if self.user_id < self.spouse_id else (self.spouse_id, self.user_id)
        async with aiosqlite.connect(DB_PATH) as db:
            # Give custody to keeper
            await db.execute(
                "UPDATE virtual_children SET custodian_id=? WHERE guild_id=? AND parent1_id=? AND parent2_id=?",
                (keeper_id, self.guild_id, a, b),
            )
            # Divorce
            for uid in [self.user_id, self.spouse_id]:
                await db.execute("UPDATE family SET spouse_id=NULL WHERE user_id=? AND guild_id=?",
                                 (uid, self.guild_id))
            await db.commit()

        self.stop()
        loser = interaction.guild.get_member(loser_id)
        keeper = interaction.guild.get_member(keeper_id)
        child_names = ", ".join(f"**{c['name']}**" for c in self.vchildren)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="💔 Гэрлэлт цуцлагдлаа",
                description=(
                    f"{keeper.mention if keeper else keeper_id} хүүхдүүдийг ({child_names}) авлаа.\n"
                    f"{loser.mention if loser else loser_id} хүүхэдгүй болов."
                ),
                color=discord.Color.red(),
            ),
            view=None,
        )

    @discord.ui.button(label="Өөрөө авах", style=discord.ButtonStyle.primary)
    async def take_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌", ephemeral=True); return
        await self._do_divorce(interaction, self.user_id)

    @discord.ui.button(label="Ханьд өгөх", style=discord.ButtonStyle.secondary)
    async def give_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌", ephemeral=True); return
        await self._do_divorce(interaction, self.spouse_id)


# ══════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════
class Family(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /marry ────────────────────────────────────────────────
    @commands.hybrid_command(name="marry", description="Хэн нэгэнд гэрлэлт санал болгох")
    async def marry(self, ctx: commands.Context, member: discord.Member):
        if member.id == ctx.author.id:
            await ctx.send("❌ Өөртөө санал болгох боломжгүй!", ephemeral=True)
            return
        if member.bot:
            await ctx.send("❌ Bot-тай гэрлэх боломжгүй!", ephemeral=True)
            return
        # Block marrying adopted relatives (parent, child, sibling)
        my_fam     = await get_family(ctx.author.id, ctx.guild.id)
        their_fam  = await get_family(member.id, ctx.guild.id)
        my_kids    = json.loads(my_fam["children"] or "[]")
        their_kids = json.loads(their_fam["children"] or "[]")
        if (my_fam["parent_id"] == member.id          # target is my parent
            or their_fam["parent_id"] == ctx.author.id  # I am their parent
            or member.id in my_kids                   # target is my adopted child
            or ctx.author.id in their_kids      # I am their adopted child
            or (my_fam["parent_id"] and my_fam["parent_id"] == their_fam["parent_id"])  # same parent
        ):
            await ctx.send(
                "Гэр бүлийн гишүүнтэй гэрлэх боломжгүй!",
                ephemeral=True
            )
            return

        # Бөгж шалгах
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT i.item_id, i.quantity FROM inventory i
                JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='ring'
                ORDER BY s.price DESC LIMIT 1
            """, (ctx.author.id, ctx.guild.id))
            ring = await cursor.fetchone()

        if not ring:
            await ctx.send(
                "💍 Гэрлэлтийн бөгж хэрэгтэй! `/shop ring` дээрээс авна уу.", ephemeral=True
            )
            return

        proposer_fam = await get_family(ctx.author.id, ctx.guild.id)
        target_fam   = await get_family(member.id, ctx.guild.id)

        if proposer_fam["spouse_id"]:
            await ctx.send("❌ Та аль хэдийн гэрлэсэн байна!", ephemeral=True)
            return
        if target_fam["spouse_id"]:
            await ctx.send(
                f"❌ {member.display_name} аль хэдийн гэрлэсэн байна!", ephemeral=True
            )
            return

        # Хүйс/чиг баримжааны нийцтэй байдал шалгах (хоёулаа дүртэй бол)
        p_char = await get_char(ctx.author.id, ctx.guild.id)
        t_char = await get_char(member.id, ctx.guild.id)
        if p_char and t_char:
            if not can_marry_check(p_char["gender"], p_char["sexuality"],
                                   t_char["gender"], t_char["sexuality"]):
                p_sex = SEXUALITY_MN.get(p_char["sexuality"], p_char["sexuality"])
                t_sex = SEXUALITY_MN.get(t_char["sexuality"], t_char["sexuality"])
                await ctx.send(
                    f"💔 Таны бэлгийн чиг баримжаа нийцэхгүй байна!\n"
                    f"Та: {GENDER_MN.get(p_char['gender'])} · {p_sex}\n"
                    f"{member.display_name}: {GENDER_MN.get(t_char['gender'])} · {t_sex}",
                    ephemeral=True,
                )
                return

        embed = discord.Embed(
            title="💍 Гэрлэлтийн санал!",
            description=(
                f"{ctx.author.mention} → {member.mention}\n\n"
                f"**{member.display_name}**, гэрлэлтийн санал ирлээ!\n"
                f"Зөвшөөрөх үү?"
            ),
            color=discord.Color.pink()
        )
        embed.set_footer(text="60 секундын дотор хариулна уу!")
        view = MarriageView(
            ctx.author, member,
            ring["item_id"], ring["quantity"],
            ctx.guild.id
        )
        await ctx.send(embed=embed, view=view)

    # ── /divorce ──────────────────────────────────────────────
    @commands.hybrid_command(name="divorce", description="Гэрлэлт цуцлах")
    async def divorce(self, ctx: commands.Context):
        fam = await get_family(ctx.author.id, ctx.guild.id)
        if not fam["spouse_id"]:
            await ctx.send("❌ Та гэрлээгүй байна!", ephemeral=True)
            return

        spouse_id  = fam["spouse_id"]
        vchildren  = await get_virtual_children(ctx.guild.id, ctx.author.id, spouse_id)

        if vchildren:
            # Show custody choice before divorcing
            embed = discord.Embed(
                title="💔 Гэрлэлт цуцлах",
                description=(
                    f"Та **{len(vchildren)} виртуал хүүхэдтэй** байна.\n"
                    f"Хүүхдүүдийг хэн нь авч үлдэх вэ?"
                ),
                color=discord.Color.red(),
            )
            view = DivorceView(ctx.author.id, spouse_id, vchildren, ctx.guild.id)
            await ctx.send(embed=embed, view=view, ephemeral=True)
        else:
            # No virtual children → divorce immediately
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE family SET spouse_id=NULL WHERE user_id=? AND guild_id=?",
                                 (ctx.author.id, ctx.guild.id))
                await db.execute("UPDATE family SET spouse_id=NULL WHERE user_id=? AND guild_id=?",
                                 (spouse_id, ctx.guild.id))
                await db.commit()

            spouse = ctx.guild.get_member(spouse_id)
            await ctx.send(
                f"💔 {ctx.author.mention} болон {spouse.mention if spouse else 'хань'} салалаа."
            )

    # ── /adopt ────────────────────────────────────────────────
    @commands.hybrid_command(name="adopt", description="Хүүхэд үрчлэх (үрчлэлтийн бичиг хэрэгтэй)")
    async def adopt(self, ctx: commands.Context, member: discord.Member):
        if member.id == ctx.author.id or member.bot:
            await ctx.send("❌ Боломжгүй!", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT i.item_id, i.quantity FROM inventory i
                JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='adoption'
            """, (ctx.author.id, ctx.guild.id))
            doc = await cursor.fetchone()

        if not doc:
            await ctx.send(
                "📄 Үрчлэлтийн бичиг хэрэгтэй! `/shop other` дээрээс авна уу.", ephemeral=True
            )
            return

        child_fam = await get_family(member.id, ctx.guild.id)
        if child_fam["parent_id"]:
            await ctx.send(
                f"❌ {member.display_name} аль хэдийн эцэг эхтэй!", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="👶 Үрчлэлтийн санал!",
            description=(
                f"{ctx.author.mention} таныг үрчлэхийг хүсч байна!\n\n"
                f"**{member.display_name}**, зөвшөөрөх үү?"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="60 секундын дотор хариулна уу!")
        view = AdoptView(
            ctx.author, member,
            doc["item_id"], doc["quantity"],
            ctx.guild.id
        )
        await ctx.send(embed=embed, view=view)

    # ── /family ───────────────────────────────────────────────
    @commands.hybrid_command(name="family", description="Гэр бүлийн мэдээлэл харах")
    async def family_info(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        fam    = await get_family(target.id, ctx.guild.id)

        embed = discord.Embed(
            title=f"👨‍👩‍👧‍👦  {target.display_name}-н гэр бүл",
            color=discord.Color.pink()
        )

        # Хань
        if fam["spouse_id"]:
            sp = ctx.guild.get_member(fam["spouse_id"])
            embed.add_field(
                name="💍 Хань",
                value=sp.mention if sp else f"ID:{fam['spouse_id']}",
                inline=True
            )
        else:
            embed.add_field(name="💍 Хань", value="Одоохондоо ганц бие", inline=True)

        # Эцэг/эх
        if fam["parent_id"]:
            parent = ctx.guild.get_member(fam["parent_id"])
            embed.add_field(
                name="👨‍👩‍👦 Эцэг/эх",
                value=parent.mention if parent else f"ID:{fam['parent_id']}",
                inline=True
            )
            embed.add_field(name="​", value="​", inline=True)

        # Хүүхдүүд (adopted = real users + virtual = bot-generated)
        adopted = json.loads(fam["children"] or "[]")
        adopted_lines = []
        for cid in adopted:
            ch = ctx.guild.get_member(cid)
            adopted_lines.append(f"👤 {ch.mention if ch else f'ID:{cid}'} *(үрчлэгдсэн)*")

        # Virtual children — always show, regardless of current marriage status
        virtual_lines = []
        async with aiosqlite.connect(DB_PATH) as _vc_db:
            _vc_db.row_factory = aiosqlite.Row
            _vc_cur = await _vc_db.execute(
                "SELECT * FROM virtual_children WHERE guild_id=? AND (parent1_id=? OR parent2_id=?)",
                (ctx.guild.id, target.id, target.id)
            )
            all_vchildren = [dict(r) for r in await _vc_cur.fetchall()]
        for vc in all_vchildren:
            vage  = calc_age_dt(vc["birth_time"])
            emoji = "👦" if vc["gender"] == "male" else "👧"
            if vage >= 32:
                status = " *(гарсан)*"
            elif vage >= 16:
                clg = " 🎓" if vc["college"] else ""
                status = f" *(бие даасан{clg})*"
            else:
                status = f" *({vage} нас)*"
            virtual_lines.append(f"{emoji} **{vc['name']}**{status} `(ID:{vc['child_id']})`")

        all_children = adopted_lines + virtual_lines
        if all_children:
            embed.add_field(name="👶 Хүүхдүүд", value="\n".join(all_children), inline=False)
        else:
            embed.add_field(name="👶 Хүүхдүүд", value="Одоохондоо үгүй", inline=False)

        # ── Үл хөдлөх хөрөнгө (байшин) ───────────────────────
        own_lv = fam["house_level"] or 0
        if own_lv > 0:
            own_txt = f"👤 **{target.display_name}** — {HOUSES[own_lv][0]}  `{HOUSES[own_lv][1]:,} ₮`"
        else:
            own_txt = f"👤 **{target.display_name}** — 🚫 Байшингүй"

        house_lines = [own_txt]
        if fam["spouse_id"]:
            sp_fam  = await get_family(fam["spouse_id"], ctx.guild.id)
            sp_lv   = sp_fam["house_level"] or 0
            sp_mem  = ctx.guild.get_member(fam["spouse_id"])
            sp_name = sp_mem.display_name if sp_mem else "Хань"
            if sp_lv > 0:
                sp_txt = f"💍 **{sp_name}** — {HOUSES[sp_lv][0]}  `{HOUSES[sp_lv][1]:,} ₮`"
            else:
                sp_txt = f"💍 **{sp_name}** — 🚫 Байшингүй"
            house_lines.append(sp_txt)

        embed.add_field(
            name="🏠 Үл хөдлөх хөрөнгө",
            value="\n".join(house_lines),
            inline=False
        )

        # ── Хөдлөх хөрөнгө (vehicles) ─────────────────────────
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT s.name, s.emoji, s.price, i.quantity
                FROM inventory i
                JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='vehicle'
                ORDER BY s.price DESC
            """, (target.id, ctx.guild.id))
            vehicles = await cursor.fetchall()

        if vehicles:
            shown = vehicles[:3]
            rest  = len(vehicles) - 3
            # shop.emoji ашигладаг (яг таарах emoji)
            v_lines = [f"{v['emoji']} **{v['name']}**  `{v['price']:,} ₮`" for v in shown]
            if rest > 0:
                v_lines.append(f"*+ {rest} хөдлөх хөрөнгө...*")
            embed.add_field(
                name="🚗 Хөдлөх хөрөнгө",
                value="\n".join(v_lines),
                inline=False
            )
        await ctx.send(embed=embed)

    # ── /buyhouse ─────────────────────────────────────────────
    @commands.hybrid_command(name="buyhouse", description="Байшин авах (10,000,000 ₮)")
    async def buy_house(self, ctx: commands.Context):
        fam = await get_family(ctx.author.id, ctx.guild.id)
        if (fam["house_level"] or 0) > 0:
            await ctx.send(
                "🏠 Аль хэдийн байшинтай байна! `/upgradehouse` командаар ахиулна уу.",
                ephemeral=True
            )
            return

        price = HOUSES[1][1]
        name  = HOUSES[1][0]
        user  = await get_user(ctx.author.id, ctx.guild.id)

        if user["balance"] < price:
            await ctx.send(
                f"❌ Мөнгө хүрэлцэхгүй!\n"
                f"Хэрэгтэй: **{price:,} ₮**  |  Таных: **{user['balance']:,} ₮**",
                ephemeral=True
            )
            return

        await update_balance(ctx.author.id, ctx.guild.id, -price)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE family SET house_level=1 WHERE user_id=? AND guild_id=?",
                (ctx.author.id, ctx.guild.id)
            )
            await db.commit()

        embed = discord.Embed(
            title="🏠 Байшин авлаа!",
            description=f"{name} худалдан авлаа!\n**{price:,} ₮** зарцуулагдлаа.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # ── /upgradehouse ─────────────────────────────────────────
    @commands.hybrid_command(name="upgradehouse", description="Байшинг дараагийн түвшинд ахиулах (60% зарж, шинийг авна)")
    async def upgrade_house(self, ctx: commands.Context):
        fam    = await get_family(ctx.author.id, ctx.guild.id)
        cur_lv = fam["house_level"] or 0

        if cur_lv == 0:
            await ctx.send(
                "❌ Эхлээд `/buyhouse` командаар байшин авна уу!", ephemeral=True
            )
            return
        if cur_lv >= 3:
            await ctx.send(
                f"✅ Байшин хамгийн дээд түвшинд байна — **{HOUSES[3][0]}**!", ephemeral=True
            )
            return

        next_lv    = cur_lv + 1
        sell_price = int(HOUSES[cur_lv][1] * HOUSE_UPGRADE_RATIO)
        buy_price  = HOUSES[next_lv][1]
        net_cost   = buy_price - sell_price

        user = await get_user(ctx.author.id, ctx.guild.id)
        if user["balance"] < net_cost:
            await ctx.send(
                f"❌ Мөнгө хүрэлцэхгүй!\n"
                f"Зарах ({int(HOUSE_UPGRADE_RATIO*100)}%): **+{sell_price:,} ₮**\n"
                f"Шинэ байшин ({HOUSES[next_lv][0]}): **{buy_price:,} ₮**\n"
                f"Хэрэгтэй нэмэлт: **{net_cost:,} ₮**  |  Таных: **{user['balance']:,} ₮**",
                ephemeral=True
            )
            return

        await update_balance(ctx.author.id, ctx.guild.id, -net_cost)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE family SET house_level=? WHERE user_id=? AND guild_id=?",
                (next_lv, ctx.author.id, ctx.guild.id)
            )
            await db.commit()

        embed = discord.Embed(
            title="🏡 Байшин шинэчлэгдлээ!",
            description=(
                f"{HOUSES[cur_lv][0]}  →  **{HOUSES[next_lv][0]}**\n\n"
                f"Зарсан үнэ: **{sell_price:,} ₮**\n"
                f"Шинэ байшин: **{buy_price:,} ₮**\n"
                f"Нийт зарцуулалт: **{net_cost:,} ₮**"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # ── /sellhouse ────────────────────────────────────────────
    @commands.hybrid_command(name="sellhouse", description="Байшингаа зарах (үнийн 60% буцаан авна)")
    async def sell_house(self, ctx: commands.Context):
        fam    = await get_family(ctx.author.id, ctx.guild.id)
        cur_lv = fam["house_level"] or 0

        if cur_lv == 0:
            await ctx.send("❌ Байшин байхгүй байна!", ephemeral=True)
            return

        refund     = int(HOUSES[cur_lv][1] * HOUSE_SELL_RATIO)
        house_name = HOUSES[cur_lv][0]

        await update_balance(ctx.author.id, ctx.guild.id, refund)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE family SET house_level=0 WHERE user_id=? AND guild_id=?",
                (ctx.author.id, ctx.guild.id)
            )
            await db.commit()

        embed = discord.Embed(
            title="🏚️ Байшин зарагдлаа!",
            description=f"{house_name} зарагдлаа.\n**{refund:,} ₮** буцаан авлаа.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)


    # ── /payschool ────────────────────────────────────────────
    @commands.hybrid_command(name="payschool", description="Виртуал хүүхдийнхээ коллежийн төлбөр төлөх")
    async def payschool(self, ctx: commands.Context):
        uid, gid = ctx.author.id, ctx.guild.id

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM virtual_children WHERE guild_id=? AND (parent1_id=? OR parent2_id=?)",
                (gid, uid, uid)
            )
            children = [dict(r) for r in await cur.fetchall()]

        if not children:
            await ctx.send(
                "Таньд виртуал хүүхэд байхгүй байна.", ephemeral=True
            )
            return

        eligible = [c for c in children if calc_age_dt(c["birth_time"]) >= 16 and not c["college"]]
        if not eligible:
            await ctx.send(
                "Коллежид орох насанд (16+) хүрсэн хүүхэд байхгүй / аль хэдийн төгсөн.", ephemeral=True
            )
            return

        user = await get_user(uid, gid)
        total_cost = CHILD_COLLEGE_COST * len(eligible)
        if user["balance"] < total_cost:
            await ctx.send(
                f"Мөнгө хүрэлцэхгүй! Хэрэгтэй: **{total_cost:,} ₮**  | Таных: **{user['balance']:,} ₮**",
                ephemeral=True
            )
            return

        await update_balance(uid, gid, -total_cost)
        async with aiosqlite.connect(DB_PATH) as db:
            for c in eligible:
                await db.execute(
                    "UPDATE virtual_children SET college=1 WHERE child_id=?", (c["child_id"],)
                )
            await db.commit()

        names = ", ".join(f"**{c['name']}**" for c in eligible)
        await ctx.send(
            f"🎓 {names} коллежид орлоо!\n"
            f"💸 **{total_cost:,} ₮** зарцуулагдлаа."
        )


async def setup(bot):
    await bot.add_cog(Family(bot))
