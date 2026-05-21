import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import random
from collections import Counter
from database import DB_PATH, get_user, update_balance, get_rpg

# ── RPG enemies ───────────────────────────────────────────────
ENEMIES = [
    {"name": "🐺 Чоно",        "hp": 40,  "attack": 8,  "reward": 300},
    {"name": "🐗 Зэрлэг гахай","hp": 60,  "attack": 12, "reward": 500},
    {"name": "🐉 Луу",         "hp": 150, "attack": 25, "reward": 1500},
    {"name": "💀 Яс тэнүүлч",  "hp": 80,  "attack": 15, "reward": 700},
    {"name": "🧟 Зомби",        "hp": 100, "attack": 18, "reward": 900},
    {"name": "👹 Чөтгөр",       "hp": 120, "attack": 22, "reward": 1200},
]

# ── Шагай (ankle-bone) configuration ─────────────────────────
# 4 тал: Морь / Хонь / Тэмээ / Ямаа
# "Бэрх" = тусдаа тал биш — 4 шагай бүгд өөр өөр гарвал нэрлэнэ
SHAGAI_SIDES   = ["Морь", "Хонь", "Тэмээ", "Ямаа"]
SHAGAI_EMOJIS  = {
    "Морь":  "🐴",
    "Хонь":  "🐑",
    "Тэмээ": "🐪",
    "Ямаа":  "🐐",
}
SHAGAI_WEIGHTS = [12, 38, 18, 32]   # sum = 100

# Four-of-a-kind multipliers
SHAGAI_4X = {"Морь": 200, "Тэмээ": 50, "Ямаа": 12, "Хонь": 8}
# Three-of-a-kind multipliers
SHAGAI_3X = {"Морь": 15, "Тэмээ": 8, "Ямаа": 1.5, "Хонь": 1.5}

# Roulette — red numbers
ROULETTE_RED = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}


def roll_shagai() -> list[str]:
    return random.choices(SHAGAI_SIDES, weights=SHAGAI_WEIGHTS, k=4)


def evaluate_shagai(dice: list[str]) -> tuple[float, str]:
    """Returns (multiplier, description). multiplier 0 = lose."""
    counts  = Counter(dice)
    top_cnt = max(counts.values())

    # Бэрх — 4 шагай бүгд өөр өөр (Морь+Тэмээ+Хонь+Ямаа)
    if len(counts) == 4:
        return 5.0, "⚡ **4 Бэрх** — Морь+Тэмээ+Хонь+Ямаа — 5x"

    # 4 of a kind
    if top_cnt == 4:
        animal = next(k for k, v in counts.items() if v == 4)
        mult   = SHAGAI_4X[animal]
        return mult, f"🎯 4× {SHAGAI_EMOJIS[animal]} **{animal}** — {mult}x"

    # 3 of a kind
    if top_cnt == 3:
        animal = next(k for k, v in counts.items() if v == 3)
        mult   = SHAGAI_3X[animal]
        return mult, f"✨ 3× {SHAGAI_EMOJIS[animal]} **{animal}** — {mult}x"

    return 0, "💨 Хожил байхгүй"


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ══════════════════════════════════════════════════════════
    #  /slot
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="slot", description="Slot machine тоглох")
    async def slot(self, interaction: discord.Interaction, bet: int):
        if bet < 100:
            await interaction.response.send_message("❌ Хамгийн бага бооцоо **100 ₮**!", ephemeral=True)
            return

        user = await get_user(interaction.user.id, interaction.guild_id)
        if user["balance"] < bet:
            await interaction.response.send_message(
                f"❌ Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} ₮**", ephemeral=True
            )
            return

        symbols = ["🍒","🍋","🍊","🍇","⭐","💎","7️⃣"]
        weights = [30, 25, 20, 15, 6, 3, 1]
        reels   = random.choices(symbols, weights=weights, k=3)

        if reels[0] == reels[1] == reels[2]:
            mult = {
                "💎": 50, "7️⃣": 30, "⭐": 10
            }.get(reels[0], 5)
            winnings = bet * mult
            result   = f"🎉 **JACKPOT!** {mult}x = **+{winnings:,} ₮**"
            color    = discord.Color.gold()
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            winnings = int(bet * 1.5)
            result   = f"✅ Хоёр ижил! **+{winnings:,} ₮**"
            color    = discord.Color.green()
        else:
            winnings = -bet
            result   = f"❌ Таарсангүй! **-{bet:,} ₮**"
            color    = discord.Color.red()

        await update_balance(interaction.user.id, interaction.guild_id, winnings)
        embed = discord.Embed(title="🎰 Slot Machine", color=color)
        embed.add_field(name="Дүн",    value=f"[ {reels[0]} | {reels[1]} | {reels[2]} ]", inline=False)
        embed.add_field(name="Үр дүн", value=result, inline=False)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} ₮")
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /coinflip
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="coinflip", description="Зоос шидэх — 50/50, 2x (heads/tails)")
    @app_commands.describe(choice="Таны сонголт", bet="Бооцооны дүн")
    @app_commands.choices(choice=[
        app_commands.Choice(name="🦅 Толгой (Heads)", value="heads"),
        app_commands.Choice(name="🪙 Сүүл (Tails)",  value="tails"),
    ])
    async def coinflip(self, interaction: discord.Interaction, choice: str, bet: int):
        if bet < 100:
            await interaction.response.send_message("❌ Хамгийн бага бооцоо **100 ₮**!", ephemeral=True)
            return

        user = await get_user(interaction.user.id, interaction.guild_id)
        if user["balance"] < bet:
            await interaction.response.send_message(
                f"❌ Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} ₮**", ephemeral=True
            )
            return

        result = random.choice(["heads", "tails"])
        labels = {"heads": "🦅 Толгой (Heads)", "tails": "🪙 Сүүл (Tails)"}

        if result == choice:
            winnings = bet
            outcome  = f"✅ Зөв! **+{bet:,} ₮**"
            color    = discord.Color.green()
        else:
            winnings = -bet
            outcome  = f"❌ Буруу! **-{bet:,} ₮**"
            color    = discord.Color.red()

        await update_balance(interaction.user.id, interaction.guild_id, winnings)

        embed = discord.Embed(title="🪙 Зоос шидлээ!", color=color)
        embed.add_field(name="Таны сонголт", value=labels[choice],  inline=True)
        embed.add_field(name="Үр дүн",       value=labels[result],  inline=True)
        embed.add_field(name="Ашиг/Алдагдал",value=outcome,         inline=False)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} ₮")
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /rps  (Rock-Paper-Scissors)
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="rps", description="Чулуу-Цаас-Хайч — bot-той тоглох")
    @app_commands.describe(choice="Таны сонголт", bet="Бооцооны дүн (хожвол 1.5x)")
    @app_commands.choices(choice=[
        app_commands.Choice(name="🪨 Чулуу",  value="rock"),
        app_commands.Choice(name="📄 Цаас",   value="paper"),
        app_commands.Choice(name="✂️ Хайч",   value="scissors"),
    ])
    async def rps(self, interaction: discord.Interaction, choice: str, bet: int):
        if bet < 100:
            await interaction.response.send_message("❌ Хамгийн бага бооцоо **100 ₮**!", ephemeral=True)
            return

        user = await get_user(interaction.user.id, interaction.guild_id)
        if user["balance"] < bet:
            await interaction.response.send_message(
                f"❌ Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} ₮**", ephemeral=True
            )
            return

        bot_choice = random.choice(["rock", "paper", "scissors"])
        labels = {"rock": "🪨 Чулуу", "paper": "📄 Цаас", "scissors": "✂️ Хайч"}

        # Хожих тохиолдлууд
        wins = {("rock","scissors"), ("paper","rock"), ("scissors","paper")}

        if choice == bot_choice:
            winnings = 0
            outcome  = "🤝 Тэнцлээ! Мөнгө өөрчлөгдсөнгүй."
            color    = discord.Color.blue()
        elif (choice, bot_choice) in wins:
            winnings = int(bet * 0.5)     # net gain: 1.5x payout − bet = +0.5x
            outcome  = f"✅ Та хожлоо! **+{winnings:,} ₮**"
            color    = discord.Color.green()
        else:
            winnings = -bet
            outcome  = f"❌ Та хожигдлоо! **-{bet:,} ₮**"
            color    = discord.Color.red()

        await update_balance(interaction.user.id, interaction.guild_id, winnings)

        embed = discord.Embed(title="✂️ Чулуу-Цаас-Хайч", color=color)
        embed.add_field(name="Таны сонголт",  value=labels[choice],     inline=True)
        embed.add_field(name="Bot-н сонголт", value=labels[bot_choice], inline=True)
        embed.add_field(name="Үр дүн",        value=outcome,            inline=False)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} ₮")
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /roulette
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="roulette", description="Рулетка — улаан/хар, сондгой/тэгш, тоо (0–36)")
    @app_commands.describe(bet_type="Таны тавил", bet="Бооцооны дүн", number="Тодорхой тоо (0–36, зөвхөн 'number' горимд)")
    @app_commands.choices(bet_type=[
        app_commands.Choice(name="🔴 Улаан (Red)   — 2x",   value="red"),
        app_commands.Choice(name="⚫ Хар (Black)    — 2x",   value="black"),
        app_commands.Choice(name="🔢 Сондгой (Odd) — 2x",   value="odd"),
        app_commands.Choice(name="🔢 Тэгш (Even)   — 2x",   value="even"),
        app_commands.Choice(name="🎯 Тоо (Number)  — 36x",  value="number"),
    ])
    async def roulette(self, interaction: discord.Interaction,
                       bet_type: str, bet: int,
                       number: int = None):
        if bet < 100:
            await interaction.response.send_message("❌ Хамгийн бага бооцоо **100 ₮**!", ephemeral=True)
            return

        if bet_type == "number":
            if number is None or not (0 <= number <= 36):
                await interaction.response.send_message(
                    "❌ `number` горимд `number` параметрт 0–36 тоо оруулна уу!", ephemeral=True
                )
                return

        user = await get_user(interaction.user.id, interaction.guild_id)
        if user["balance"] < bet:
            await interaction.response.send_message(
                f"❌ Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} ₮**", ephemeral=True
            )
            return

        # Spin
        spin = random.randint(0, 36)
        if spin == 0:
            spin_color = "🟢 Ногоон (0)"
        elif spin in ROULETTE_RED:
            spin_color = f"🔴 Улаан ({spin})"
        else:
            spin_color = f"⚫ Хар ({spin})"

        # Evaluate
        won = False
        if bet_type == "red"    and spin != 0 and spin in ROULETTE_RED:
            won, mult = True, 2
        elif bet_type == "black" and spin != 0 and spin not in ROULETTE_RED:
            won, mult = True, 2
        elif bet_type == "odd"   and spin != 0 and spin % 2 == 1:
            won, mult = True, 2
        elif bet_type == "even"  and spin != 0 and spin % 2 == 0:
            won, mult = True, 2
        elif bet_type == "number" and spin == number:
            won, mult = True, 36
        else:
            mult = 2  # default (unused)

        if won:
            winnings = bet * (mult - 1)
            outcome  = f"✅ Хожлоо! **+{winnings:,} ₮** ({mult}x)"
            color    = discord.Color.green()
        else:
            winnings = -bet
            outcome  = f"❌ Хожигдлоо! **-{bet:,} ₮**"
            color    = discord.Color.red()

        await update_balance(interaction.user.id, interaction.guild_id, winnings)

        embed = discord.Embed(title="🎡 Рулетка", color=color)
        embed.add_field(name="🎰 Тоглосон дүн", value=spin_color, inline=False)
        embed.add_field(name="Таны тавил",
                        value=f"{bet_type.upper()}" + (f" → {number}" if bet_type=="number" else ""),
                        inline=True)
        embed.add_field(name="Үр дүн", value=outcome, inline=True)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} ₮")
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /shagai  (Mongolian ankle-bone dice)
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="shagai", description="Шагай шидэх — 4 шагай, Монгол уламжлалт тоглоом")
    async def shagai(self, interaction: discord.Interaction, bet: int):
        if bet < 100:
            await interaction.response.send_message("❌ Хамгийн бага бооцоо **100 ₮**!", ephemeral=True)
            return

        user = await get_user(interaction.user.id, interaction.guild_id)
        if user["balance"] < bet:
            await interaction.response.send_message(
                f"❌ Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} ₮**", ephemeral=True
            )
            return

        dice = roll_shagai()
        mult, desc = evaluate_shagai(dice)

        dice_display = "  ".join(f"{SHAGAI_EMOJIS[d]} {d}" for d in dice)

        if mult > 0:
            winnings = int(bet * (mult - 1))
            outcome  = f"✅ {desc}\n**+{winnings:,} ₮**"
            color    = discord.Color.gold() if mult >= 50 else discord.Color.green()
        else:
            winnings = -bet
            outcome  = f"{desc}\n**-{bet:,} ₮**"
            color    = discord.Color.red()

        await update_balance(interaction.user.id, interaction.guild_id, winnings)

        embed = discord.Embed(title="🦴 Шагай", color=color)
        embed.add_field(name="4 Шагайн дүн", value=dice_display, inline=False)
        embed.add_field(name="Үр дүн", value=outcome, inline=False)
        embed.add_field(
            name="📊 Хожлын хүснэгт",
            value=(
                "```\n"
                "┌──────────────────────────────────┐\n"
                "│  4× 🐴 Морь        →   200x      │\n"
                "│  4× 🐪 Тэмээ       →    50x      │\n"
                "│  4× 🐐 Ямаа        →    12x      │\n"
                "│  4× 🐑 Хонь        →     8x      │\n"
                "│  ⚡ Бэрх (4 өөр)   →     5x      │\n"
                "│  3× 🐴 Морь        →    15x      │\n"
                "│  3× 🐪 Тэмээ       →     8x      │\n"
                "│  3× 🐐 Ямаа        →   1.5x      │\n"
                "│  3× 🐑 Хонь        →   1.5x      │\n"
                "│  Бусад             →     0x      │\n"
                "└──────────────────────────────────┘\n"
                "```"
            ),
            inline=False
        )
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} ₮")
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /battle
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="battle", description="Дайстай тулалдах RPG тулаан")
    async def battle(self, interaction: discord.Interaction):
        rpg = await get_rpg(interaction.user.id, interaction.guild_id)
        if rpg["hp"] <= 0:
            await interaction.response.send_message(
                "❌ HP байхгүй байна! `/heal` командаар эмчлүүлнэ үү.", ephemeral=True
            )
            return

        enemy      = random.choice(ENEMIES).copy()
        player_hp  = rpg["hp"]
        battle_log = []
        round_num  = 1

        while player_hp > 0 and enemy["hp"] > 0:
            dmg_e = max(1, rpg["attack"] - random.randint(0,3) + random.randint(0,5))
            enemy["hp"] -= dmg_e
            battle_log.append(f"⚔️ Та **{dmg_e}** хохирол үзүүллээ")
            if enemy["hp"] <= 0:
                break
            dmg_p = max(1, enemy["attack"] - rpg["defense"] + random.randint(-2,3))
            player_hp -= dmg_p
            battle_log.append(f"💥 {enemy['name']} танд **{dmg_p}** хохирол үзүүллээ")
            round_num += 1
            if round_num > 10:
                break

        if enemy["hp"] <= 0:
            reward = enemy["reward"] + random.randint(0, 200)
            await update_balance(interaction.user.id, interaction.guild_id, reward)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE rpg SET hp=? WHERE user_id=? AND guild_id=?",
                    (max(1, player_hp), interaction.user.id, interaction.guild_id)
                )
                await db.commit()
            embed = discord.Embed(
                title=f"⚔️ Тулаан — {enemy['name']} ялагдлаа!",
                description="\n".join(battle_log[-6:]),
                color=discord.Color.green()
            )
            embed.add_field(name="🏆 Шагнал",    value=f"**{reward:,} ₮**",        inline=True)
            embed.add_field(name="❤️ Үлдсэн HP", value=f"**{max(1, player_hp)}**", inline=True)
        else:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE rpg SET hp=0 WHERE user_id=? AND guild_id=?",
                    (interaction.user.id, interaction.guild_id)
                )
                await db.commit()
            embed = discord.Embed(
                title="💀 Тулаан — Та ялагдлаа!",
                description="\n".join(battle_log[-6:]),
                color=discord.Color.red()
            )
            embed.add_field(name="❤️ HP", value="**0** — `/heal` командаар эмчлүүлнэ үү", inline=False)

        # ── Зэвсэг/хуягын эдэлгээ буурах ─────────────────────────
        durability_notes = []
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            for eq_type, default_stat, stat_col, name_col, default_name in [
                ("weapon", 10, "attack", "weapon", "Нударга"),
                ("armor",   5, "defense","armor",  "Хувцас"),
            ]:
                cur = await db.execute("""
                    SELECT i.item_id, i.quantity, s.name, s.effect_value
                    FROM inventory i JOIN shop s ON i.item_id = s.item_id
                    WHERE i.user_id=? AND i.guild_id=? AND s.item_type=?
                """, (interaction.user.id, interaction.guild_id, eq_type))
                row = await cur.fetchone()
                if row:
                    new_qty = row["quantity"] - 1
                    if new_qty <= 0:
                        await db.execute(
                            "DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?",
                            (row["item_id"], interaction.user.id, interaction.guild_id)
                        )
                        await db.execute(
                            f"UPDATE rpg SET {stat_col}=?, {name_col}=? WHERE user_id=? AND guild_id=?",
                            (default_stat, default_name, interaction.user.id, interaction.guild_id)
                        )
                        durability_notes.append(f"💔 **{row['name']}** эвдэрлээ!")
                    else:
                        await db.execute(
                            "UPDATE inventory SET quantity=? WHERE item_id=? AND user_id=? AND guild_id=?",
                            (new_qty, row["item_id"], interaction.user.id, interaction.guild_id)
                        )
                        if new_qty <= 3:
                            durability_notes.append(f"⚠️ **{row['name']}** эдэлгээ: {new_qty} тулаан үлдлээ")
            await db.commit()

        if durability_notes:
            embed.add_field(name="🔧 Тоног төхөөрөмж", value="\n".join(durability_notes), inline=False)

        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /heal
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="heal", description="HP-г бүрэн сэргээх (inventory-аас эмчилгээ ашиглана)")
    async def heal(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT i.item_id, i.quantity FROM inventory i
                JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='heal'
            """, (interaction.user.id, interaction.guild_id))
            heal_item = await cursor.fetchone()

        if not heal_item:
            await interaction.response.send_message(
                "❌ Эмчилгээ байхгүй байна! `/shop other` дээрээс авна уу.", ephemeral=True
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            cursor  = await db.execute(
                "SELECT max_hp FROM rpg WHERE user_id=? AND guild_id=?",
                (interaction.user.id, interaction.guild_id)
            )
            row     = await cursor.fetchone()
            max_hp  = row[0] if row else 100

            await db.execute(
                "UPDATE rpg SET hp=? WHERE user_id=? AND guild_id=?",
                (max_hp, interaction.user.id, interaction.guild_id)
            )
            if heal_item["quantity"] > 1:
                await db.execute(
                    "UPDATE inventory SET quantity=quantity-1 WHERE item_id=? AND user_id=? AND guild_id=?",
                    (heal_item["item_id"], interaction.user.id, interaction.guild_id)
                )
            else:
                await db.execute(
                    "DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?",
                    (heal_item["item_id"], interaction.user.id, interaction.guild_id)
                )
            await db.commit()

        embed = discord.Embed(
            title="❤️ Эмчилгээ хийгдлээ!",
            description=f"HP **{max_hp}** болж сэргэлээ!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /rpg
    # ══════════════════════════════════════════════════════════
    @app_commands.command(name="rpg", description="RPG тоглогчийн статус харах")
    async def rpg_status(self, interaction: discord.Interaction):
        rpg    = await get_rpg(interaction.user.id, interaction.guild_id)
        filled = int((rpg["hp"] / rpg["max_hp"]) * 10)
        bar    = "❤️" * filled + "🖤" * (10 - filled)

        embed = discord.Embed(
            title=f"⚔️ {interaction.user.display_name}-н RPG статус",
            color=discord.Color.red()
        )
        embed.add_field(name="❤️ HP",         value=f"{bar}\n{rpg['hp']}/{rpg['max_hp']}", inline=False)
        embed.add_field(name="⚔️ Дайралт",    value=f"**{rpg['attack']}**",    inline=True)
        embed.add_field(name="🛡️ Хамгаалалт", value=f"**{rpg['defense']}**",   inline=True)
        embed.add_field(name="🗡️ Зэвсэг",     value=f"**{rpg['weapon']}**",    inline=True)
        embed.add_field(name="🥋 Хуяг",       value=f"**{rpg['armor']}**",     inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Games(bot))
