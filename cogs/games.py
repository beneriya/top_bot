import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import random
from collections import Counter
from database import DB_PATH, get_user, update_balance, get_rpg

async def _update_game_stats(user_id: int, guild_id: int, bet: int, winnings: int):
    """Мөрийтэй тоглоомын статистик хадгалах."""
    async with aiosqlite.connect(DB_PATH) as db:
        if winnings > 0:
            await db.execute(
                "UPDATE users SET game_wins=game_wins+1, game_won_amount=game_won_amount+?, game_wagered=game_wagered+? WHERE user_id=? AND guild_id=?",
                (winnings, bet, user_id, guild_id)
            )
        elif winnings < 0:
            await db.execute(
                "UPDATE users SET game_losses=game_losses+1, game_lost_amount=game_lost_amount+?, game_wagered=game_wagered+? WHERE user_id=? AND guild_id=?",
                (abs(winnings), bet, user_id, guild_id)
            )
        else:
            await db.execute(
                "UPDATE users SET game_wagered=game_wagered+? WHERE user_id=? AND guild_id=?",
                (bet, user_id, guild_id)
            )
        await db.commit()

# ── RPG enemies ───────────────────────────────────────────────
ENEMIES = [
    {"name": "\U0001f43a Чоно",         "hp": 40,  "attack": 8,  "reward_min": 800,  "reward_max": 1100},
    {"name": "\U0001f417 Зэрлэг гахай", "hp": 60,  "attack": 12, "reward_min": 900,  "reward_max": 1200},
    {"name": "\U0001f480 Яс тэнүүлч",   "hp": 80,  "attack": 15, "reward_min": 1000, "reward_max": 1350},
    {"name": "\U0001f9df Зомби",         "hp": 100, "attack": 18, "reward_min": 1150, "reward_max": 1500},
    {"name": "\U0001f479 Чөтгөр",        "hp": 120, "attack": 22, "reward_min": 1350, "reward_max": 1700},
    {"name": "\U0001f409 Луу",          "hp": 150, "attack": 25, "reward_min": 1650, "reward_max": 2000},
]

# ── Шагай ─────────────────────────────────────────────────────
SHAGAI_SIDES   = ["Морь", "Хонь", "Тэмээ", "Ямаа"]
SHAGAI_EMOJIS  = {"Морь": "\U0001f434", "Хонь": "\U0001f411", "Тэмээ": "\U0001f42a", "Ямаа": "\U0001f410"}
SHAGAI_WEIGHTS = [12, 38, 18, 32]

# Nerfed: 4x Морь 200->100, 4x Тэмээ 50->40
SHAGAI_4X = {"Морь": 100, "Тэмээ": 40, "Ямаа": 12, "Хонь": 8}
# Nerfed: 3x Ямаа/Хонь 1.5->0.5 (partial loss)
SHAGAI_3X = {"Морь": 15, "Тэмээ": 8, "Ямаа": 0.5, "Хонь": 0.5}

ROULETTE_RED = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}


def roll_shagai() -> list:
    return random.choices(SHAGAI_SIDES, weights=SHAGAI_WEIGHTS, k=4)


def evaluate_shagai(dice: list) -> tuple:
    """Returns (multiplier, description). multiplier=0 means lose all."""
    counts  = Counter(dice)
    top_cnt = max(counts.values())

    if len(counts) == 4:
        return 5.0, "\u26a1 **4 Бэрх** — Морь+Тэмээ+Хонь+Ямаа — 5x"

    if top_cnt == 4:
        animal = next(k for k, v in counts.items() if v == 4)
        mult   = SHAGAI_4X[animal]
        emoji  = SHAGAI_EMOJIS[animal]
        return mult, f"\U0001f3af 4\u00d7 {emoji} **{animal}** — {mult}x"

    if top_cnt == 3:
        animal = next(k for k, v in counts.items() if v == 3)
        mult   = SHAGAI_3X[animal]
        emoji  = SHAGAI_EMOJIS[animal]
        if mult < 1:
            return mult, f"\U0001f62c 3\u00d7 {emoji} **{animal}** — хагас алдагдал (-50%)"
        return mult, f"\u2728 3\u00d7 {emoji} **{animal}** — {mult}x"

    return 0, "\U0001f4a8 Хожил байхгүй"


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ══════════════════════════════════════════════════════════
    #  /slot  — 10 symbols, big-bet scaling (500k+ = 2x)
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="slot", description="Slot machine тоглох — том бооцоонд өндөр хожил (500k+)")
    async def slot(self, ctx: commands.Context, bet: int):
        if bet < 100:
            await ctx.send("\u274c Хамгийн бага бооцоо **100 \u20ae**!", ephemeral=True)
            return
        user = await get_user(ctx.author.id, ctx.guild.id)
        if user["balance"] < bet:
            await ctx.send(
                f"\u274c Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} \u20ae**", ephemeral=True
            )
            return

        big_bet = bet >= 1_000_000

        # 10 symbols → lower 2-match probability vs old 7
        symbols = ["\U0001f352","\U0001f34b","\U0001f34a","\U0001f347","\U0001f353","\U0001f349","\U0001f351","\u2b50","\U0001f48e","7\ufe0f\u20e3"]
        weights = [22, 18, 15, 12, 10, 8, 5, 5, 3, 2]
        reels   = random.choices(symbols, weights=weights, k=3)

        if reels[0] == reels[1] == reels[2]:
            base_mult = {"\U0001f48e": 50, "7\ufe0f\u20e3": 30, "\u2b50": 10}.get(reels[0], 5)
            # Big bet bonus: rare symbols same, base (5x) gets +3 → 8x
            mult      = (base_mult + 3) if (big_bet and base_mult < 10) else base_mult
            winnings  = bet * mult
            bonus_note = " \U0001f525 **Том бооцоо +3x!**" if big_bet and base_mult < 10 else ""
            result    = f"\U0001f389 **JACKPOT!** {mult}x = **+{winnings:,} \u20ae**{bonus_note}"
            color     = discord.Color.gold()
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            # Big bet: 2.0x net instead of 1.5x
            match_mult = 2.0 if big_bet else 1.5
            winnings   = int(bet * (match_mult - 1))
            bonus_note = " \U0001f525 **Том бооцоо 2x!**" if big_bet else ""
            result     = f"\u2705 Хоёр ижил! {match_mult}x **+{winnings:,} \u20ae**{bonus_note}"
            color      = discord.Color.green()
        else:
            winnings = -bet
            result   = f"\u274c Таарсангүй! **-{bet:,} \u20ae**"
            color    = discord.Color.red()

        await update_balance(ctx.author.id, ctx.guild.id, winnings)
        await _update_game_stats(ctx.author.id, ctx.guild.id, bet, winnings)
        embed = discord.Embed(title="\U0001f3b0 Slot Machine", color=color)
        embed.add_field(name="Дүн",    value=f"[ {reels[0]} | {reels[1]} | {reels[2]} ]", inline=False)
        embed.add_field(name="Үр дүн", value=result, inline=False)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} \u20ae")
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /coinflip  — nerfed to 1.7x (was 2x)
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="coinflip", description="Зоос шидэх — 50/50 | <500k=1.7x | 500k+=2x")
    @app_commands.describe(choice="Таны сонголт", bet="Бооцооны дүн")
    @app_commands.choices(choice=[
        app_commands.Choice(name="\U0001f985 Толгой (Heads)", value="heads"),
        app_commands.Choice(name="\U0001fa99 Сүүл (Tails)",  value="tails"),
    ])
    async def coinflip(self, ctx: commands.Context, choice: str, bet: int):
        if bet < 100:
            await ctx.send("\u274c Хамгийн бага бооцоо **100 \u20ae**!", ephemeral=True)
            return
        user = await get_user(ctx.author.id, ctx.guild.id)
        if user["balance"] < bet:
            await ctx.send(
                f"\u274c Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} \u20ae**", ephemeral=True
            )
            return

        result = random.choice(["heads", "tails"])
        labels = {"heads": "\U0001f985 Толгой (Heads)", "tails": "\U0001fa99 Сүүл (Tails)"}

        if result == choice:
            if bet >= 1_000_000:
                winnings = bet          # 2.0x net (profit = bet)
                outcome  = f"\u2705 Зөв! **+{winnings:,} \u20ae** \U0001f525 **2x** (том бооцоо)"
            else:
                winnings = int(bet * 0.70)
                outcome  = f"\u2705 Зөв! **+{winnings:,} \u20ae** (1.7x)"
            color = discord.Color.green()
        else:
            winnings = -bet
            outcome  = f"\u274c Буруу! **-{bet:,} \u20ae**"
            color    = discord.Color.red()

        await update_balance(ctx.author.id, ctx.guild.id, winnings)
        await _update_game_stats(ctx.author.id, ctx.guild.id, bet, winnings)
        embed = discord.Embed(title="\U0001fa99 Зоос шидлээ!", color=color)
        embed.add_field(name="Таны сонголт",  value=labels[choice],  inline=True)
        embed.add_field(name="Үр дүн",        value=labels[result],  inline=True)
        embed.add_field(name="Ашиг/Алдагдал", value=outcome,         inline=False)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} \u20ae")
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /rps
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="rps", description="Чулуу-Цаас-Хайч — bot-той тоглох")
    @app_commands.describe(choice="Таны сонголт", bet="Бооцооны дүн (хожвол 1.5x)")
    @app_commands.choices(choice=[
        app_commands.Choice(name="\U0001faa8 Чулуу",  value="rock"),
        app_commands.Choice(name="\U0001f4c4 Цаас",   value="paper"),
        app_commands.Choice(name="\u2702\ufe0f Хайч", value="scissors"),
    ])
    async def rps(self, ctx: commands.Context, choice: str, bet: int):
        if bet < 100:
            await ctx.send("\u274c Хамгийн бага бооцоо **100 \u20ae**!", ephemeral=True)
            return
        user = await get_user(ctx.author.id, ctx.guild.id)
        if user["balance"] < bet:
            await ctx.send(
                f"\u274c Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} \u20ae**", ephemeral=True
            )
            return

        bot_choice = random.choice(["rock", "paper", "scissors"])
        labels = {"rock": "\U0001faa8 Чулуу", "paper": "\U0001f4c4 Цаас", "scissors": "\u2702\ufe0f Хайч"}
        wins = {("rock","scissors"), ("paper","rock"), ("scissors","paper")}

        if choice == bot_choice:
            winnings = 0
            outcome  = "\U0001f91d Тэнцлээ!"
            color    = discord.Color.blue()
        elif (choice, bot_choice) in wins:
            winnings = int(bet * 0.5)
            outcome  = f"\u2705 Та хожлоо! **+{winnings:,} \u20ae**"
            color    = discord.Color.green()
        else:
            winnings = -bet
            outcome  = f"\u274c Та хожигдлоо! **-{bet:,} \u20ae**"
            color    = discord.Color.red()

        await update_balance(ctx.author.id, ctx.guild.id, winnings)
        await _update_game_stats(ctx.author.id, ctx.guild.id, bet, winnings)
        embed = discord.Embed(title="\u2702\ufe0f Чулуу-Цаас-Хайч", color=color)
        embed.add_field(name="Таны сонголт",  value=labels[choice],     inline=True)
        embed.add_field(name="Bot-н сонголт", value=labels[bot_choice], inline=True)
        embed.add_field(name="Үр дүн",        value=outcome,            inline=False)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} \u20ae")
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /roulette  — nerfed: red/black/odd/even 2x->1.7x,
    #               green(0) 35x->25x, number 36x->30x
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="roulette", description="Рулетка — улаан/хар, сондгой/тэгш, ногоон, тоо (1–36)")
    @app_commands.describe(bet_type="Таны тавил", bet="Бооцооны дүн", number="Тодорхой тоо (1–36)")
    @app_commands.choices(bet_type=[
        app_commands.Choice(name="\U0001f534 Улаан (Red)   — 1.7x",  value="red"),
        app_commands.Choice(name="\u26ab Хар (Black)    — 1.7x",  value="black"),
        app_commands.Choice(name="\U0001f522 Сондгой (Odd) — 1.7x",  value="odd"),
        app_commands.Choice(name="\U0001f522 Тэгш (Even)   — 1.7x",  value="even"),
        app_commands.Choice(name="\U0001f7e2 Ногоон (0)    — 25x",   value="green"),
        app_commands.Choice(name="\U0001f3af Тоо (1-36)    — 30x",   value="number"),
    ])
    async def roulette(self, ctx: commands.Context,
                       bet_type: str, bet: int,
                       number: int = None):
        if bet < 100:
            await ctx.send("\u274c Хамгийн бага бооцоо **100 \u20ae**!", ephemeral=True)
            return
        if bet_type == "number":
            if number is None or not (1 <= number <= 36):
                await ctx.send(
                    "\u274c `number` горимд 1–36 хооронд тоо оруулна уу!", ephemeral=True
                )
                return

        user = await get_user(ctx.author.id, ctx.guild.id)
        if user["balance"] < bet:
            await ctx.send(
                f"\u274c Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} \u20ae**", ephemeral=True
            )
            return

        big_bet = bet >= 1_000_000
        spin = random.randint(0, 36)
        if spin == 0:
            spin_label = "\U0001f7e2 Ногоон (0)"
        elif spin in ROULETTE_RED:
            spin_label = f"\U0001f534 Улаан ({spin})"
        else:
            spin_label = f"\u26ab Хар ({spin})"

        won  = False
        mult = 1
        flat_mult = 2.0 if big_bet else 1.7
        if bet_type == "red"    and spin != 0 and spin in ROULETTE_RED:     won, mult = True, flat_mult
        elif bet_type == "black" and spin != 0 and spin not in ROULETTE_RED: won, mult = True, flat_mult
        elif bet_type == "odd"   and spin != 0 and spin % 2 == 1:           won, mult = True, flat_mult
        elif bet_type == "even"  and spin != 0 and spin % 2 == 0:           won, mult = True, flat_mult
        elif bet_type == "green" and spin == 0:                              won, mult = True, 25
        elif bet_type == "number" and spin == number:                        won, mult = True, 30

        if won:
            winnings   = int(bet * (mult - 1))
            bonus_note = " \U0001f525 **Том бооцоо 2x!**" if big_bet and mult == 2.0 else ""
            outcome    = f"\u2705 Хожлоо! **+{winnings:,} \u20ae** ({mult}x){bonus_note}"
        else:
            winnings = -bet
            outcome  = f"\u274c Хожигдлоо! **-{bet:,} \u20ae**"
        # Embed color reflects the landing pocket color
        if spin == 0:
            color = discord.Color.green()           # ногоон (0) — үргэлж ногоон
        elif spin in ROULETTE_RED:
            color = discord.Color.red() if won else discord.Color.dark_red()
        else:
            color = discord.Color.dark_gray() if won else discord.Color.from_rgb(30, 30, 30)

        await update_balance(ctx.author.id, ctx.guild.id, winnings)
        await _update_game_stats(ctx.author.id, ctx.guild.id, bet, winnings)
        embed = discord.Embed(title="\U0001f3a1 Рулетка", color=color)
        embed.add_field(name="\U0001f3b0 Унасан тоо", value=spin_label, inline=False)
        embed.add_field(name="Таны тавил",
                        value=f"{bet_type.upper()}" + (f" → {number}" if bet_type=="number" else ""),
                        inline=True)
        embed.add_field(name="Үр дүн", value=outcome, inline=True)
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} \u20ae")
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /shagai  — nerfed multipliers
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="shagai", description="Шагай шидэх — 4 шагай, Монгол уламжлалт тоглоом")
    async def shagai(self, ctx: commands.Context, bet: int):
        if bet < 100:
            await ctx.send("\u274c Хамгийн бага бооцоо **100 \u20ae**!", ephemeral=True)
            return
        user = await get_user(ctx.author.id, ctx.guild.id)
        if user["balance"] < bet:
            await ctx.send(
                f"\u274c Мөнгө хүрэлцэхгүй! Үлдэгдэл: **{user['balance']:,} \u20ae**", ephemeral=True
            )
            return

        dice = roll_shagai()
        mult, desc = evaluate_shagai(dice)
        dice_display = "  ".join(f"{SHAGAI_EMOJIS[d]} {d}" for d in dice)

        if mult > 1:
            winnings = int(bet * (mult - 1))
            outcome  = f"\u2705 {desc}\n**+{winnings:,} \u20ae**"
            color    = discord.Color.gold() if mult >= 50 else discord.Color.green()
        elif 0 < mult < 1:
            winnings = -int(bet * (1 - mult))
            outcome  = f"{desc}\n**{winnings:,} \u20ae**"
            color    = discord.Color.orange()
        elif mult == 1:
            winnings = 0
            outcome  = f"\U0001f91d {desc}\nМөнгө өөрчлөгдсөнгүй"
            color    = discord.Color.blue()
        else:
            winnings = -bet
            outcome  = f"{desc}\n**-{bet:,} \u20ae**"
            color    = discord.Color.red()

        await update_balance(ctx.author.id, ctx.guild.id, winnings)
        await _update_game_stats(ctx.author.id, ctx.guild.id, bet, winnings)

        embed = discord.Embed(title="\U0001f9b4 Шагай", color=color)
        embed.add_field(name="4 Шагайн дүн", value=dice_display, inline=False)
        embed.add_field(name="Үр дүн", value=outcome, inline=False)
        embed.add_field(
            name="\U0001f4ca Хожлын хүснэгт",
            value=(
                "```\n"
                "\u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510\n"
                "\u2502  4\u0445 \u041c\u043e\u0440\u044c          ->   100\u0445      \u2502\n"
                "\u2502  4\u0445 \u0422\u044d\u043c\u044d\u044d         ->    40\u0445      \u2502\n"
                "\u2502  4\u0445 \u042f\u043c\u0430\u0430          ->    12\u0445      \u2502\n"
                "\u2502  4\u0445 \u0425\u043e\u043d\u044c          ->     8\u0445      \u2502\n"
                "\u2502  \u0411\u0435\u0440\u0445 (4 \u04e9\u04e9\u0440)      ->     5\u0445      \u2502\n"
                "\u2502  3\u0445 \u041c\u043e\u0440\u044c          ->    15\u0445      \u2502\n"
                "\u2502  3\u0445 \u0422\u044d\u043c\u044d\u044d         ->     8\u0445      \u2502\n"
                "\u2502  3\u0445 \u042f\u043c\u0430\u0430/\u0425\u043e\u043d\u044c  -> -50% \u0430\u043b\u0434\u0430\u0433 \u2502\n"
                "\u2502  \u0411\u0443\u0441\u0430\u0434           ->     0\u0445      \u2502\n"
                "\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518\n"
                "```"
            ),
            inline=False
        )
        embed.set_footer(text=f"Шинэ үлдэгдэл: {user['balance'] + winnings:,} \u20ae")
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /battle
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="battle", description="Дайстай тулалдах RPG тулаан")
    async def battle(self, ctx: commands.Context):
        rpg = await get_rpg(ctx.author.id, ctx.guild.id)
        if rpg["hp"] <= 0:
            embed = discord.Embed(
                title="🚫 HP дууссан!",
                description="❤️ Таны HP **0** байна. Тулалдах боломжгүй!\n\n💊 `/heal` командаар эмчлүүлээрэй.",
                color=0x2b2d31
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        enemy     = random.choice(ENEMIES).copy()
        player_hp = rpg["hp"]
        max_hp    = rpg["max_hp"]
        log_atk   = []
        round_num = 1

        while player_hp > 0 and enemy["hp"] > 0:
            dmg_e = max(1, rpg["attack"] - random.randint(0,3) + random.randint(0,5))
            enemy["hp"] -= dmg_e
            log_atk.append(f"⚔️ Та **{dmg_e}** хохирол үзүүллээ")
            if enemy["hp"] <= 0:
                break
            dmg_p = max(1, enemy["attack"] - rpg["defense"] + random.randint(-2,3))
            player_hp -= dmg_p
            log_atk.append(f"💥 {enemy['name']} танд **{dmg_p}** хохирол үзүүллээ")
            round_num += 1
            if round_num > 10:
                break

        log_str = "\n".join(log_atk[-6:]) or "—"

        def hp_bar(cur, mx, length=10):
            filled = round(length * max(0, cur) / mx)
            return "▰" * filled + "▱" * (length - filled)

        # Зэвсэг/хуягын эдэлгээ
        durability_notes = []
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            for eq_type, default_stat, stat_col, name_col, default_name in [
                ("weapon", 10, "attack", "weapon", "Нударга"),
                ("armor",   5, "defense","armor",  "Хувцас"),
            ]:
                cur2 = await db.execute("""
                    SELECT i.item_id, i.quantity, s.name, s.effect_value
                    FROM inventory i JOIN shop s ON i.item_id = s.item_id
                    WHERE i.user_id=? AND i.guild_id=? AND s.item_type=?
                """, (ctx.author.id, ctx.guild.id, eq_type))
                eq_row = await cur2.fetchone()
                if eq_row:
                    new_qty = eq_row["quantity"] - 1
                    if new_qty <= 0:
                        await db.execute(
                            "DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?",
                            (eq_row["item_id"], ctx.author.id, ctx.guild.id)
                        )
                        await db.execute(
                            f"UPDATE rpg SET {stat_col}=?, {name_col}=? WHERE user_id=? AND guild_id=?",
                            (default_stat, default_name, ctx.author.id, ctx.guild.id)
                        )
                        durability_notes.append(f"💔 **{eq_row['name']}** эвдэрлээ!")
                    else:
                        await db.execute(
                            "UPDATE inventory SET quantity=? WHERE item_id=? AND user_id=? AND guild_id=?",
                            (new_qty, eq_row["item_id"], ctx.author.id, ctx.guild.id)
                        )
                        if new_qty <= 3:
                            durability_notes.append(f"⚠️ **{eq_row['name']}** эдэлгээ: **{new_qty}** тулаан үлдлээ")
            await db.commit()

        if enemy["hp"] <= 0:
            reward = random.randint(enemy["reward_min"], enemy["reward_max"])
            await update_balance(ctx.author.id, ctx.guild.id, reward)
            new_hp = max(1, player_hp)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE rpg SET hp=?, kills=kills+1 WHERE user_id=? AND guild_id=?",
                    (new_hp, ctx.author.id, ctx.guild.id)
                )
                await db.commit()
            rpg2       = await get_rpg(ctx.author.id, ctx.guild.id)
            total_kills = rpg2.get("kills", 1)
            bar_now    = hp_bar(new_hp, max_hp)
            embed = discord.Embed(
                title=f"⚔️  {enemy['name']}  ялагдлаа!",
                color=0x57f287
            )
            embed.add_field(
                name="📜 Тулааны дүн",
                value="```\n" + log_str + "\n```",
                inline=False
            )
            embed.add_field(name="💰 Шагнал",  value=f"**{reward:,} ₮**", inline=True)
            embed.add_field(name="❤️ HP",       value=f"`{bar_now}` {new_hp}/{max_hp}", inline=True)
            embed.add_field(name="💀 Алуулга", value=f"**{total_kills}** 💀", inline=True)
        else:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE rpg SET hp=0 WHERE user_id=? AND guild_id=?",
                    (ctx.author.id, ctx.guild.id)
                )
                await db.commit()
            bar_dead = hp_bar(0, max_hp)
            embed = discord.Embed(
                title=f"💀  {enemy['name']}  танийг ялав!",
                color=0xed4245
            )
            embed.add_field(
                name="📜 Тулааны дүн",
                value="```\n" + log_str + "\n```",
                inline=False
            )
            embed.add_field(
                name="❤️ HP",
                value=f"`{bar_dead}` 0/{max_hp}\n💊 `/heal` командаар эмчлүүлээрэй!",
                inline=False
            )

        if durability_notes:
            embed.add_field(
                name="🔧 Тоног төхөөрөмж",
                value="\n".join(durability_notes),
                inline=False
            )
        embed.set_footer(text=f"⚔️ {ctx.author.display_name}  •  {enemy['name']}")
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /heal  — checks if HP is already full
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="heal", description="HP-г бүрэн сэргээх (inventory-аас эмчилгээ ашиглана)")
    async def heal(self, ctx: commands.Context):
        # First check current HP
        rpg = await get_rpg(ctx.author.id, ctx.guild.id)
        if rpg["hp"] >= rpg["max_hp"]:
            await ctx.send(
                f"\u2764\ufe0f Таны HP аль хэдийн **{rpg['hp']}/{rpg['max_hp']}** дүүрэн байна!\n"
                "Эмчилгээ зарцуулахгүй.",
                ephemeral=True
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT i.item_id, i.quantity FROM inventory i
                JOIN shop s ON i.item_id = s.item_id
                WHERE i.user_id=? AND i.guild_id=? AND s.item_type='heal'
            """, (ctx.author.id, ctx.guild.id))
            heal_item = await cursor.fetchone()

        if not heal_item:
            await ctx.send(
                "\u274c Эмчилгээ байхгүй байна! `/shop other` дээрээс авна уу.", ephemeral=True
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE rpg SET hp=max_hp WHERE user_id=? AND guild_id=?",
                (ctx.author.id, ctx.guild.id)
            )
            if heal_item["quantity"] > 1:
                await db.execute(
                    "UPDATE inventory SET quantity=quantity-1 WHERE item_id=? AND user_id=? AND guild_id=?",
                    (heal_item["item_id"], ctx.author.id, ctx.guild.id)
                )
            else:
                await db.execute(
                    "DELETE FROM inventory WHERE item_id=? AND user_id=? AND guild_id=?",
                    (heal_item["item_id"], ctx.author.id, ctx.guild.id)
                )
            await db.commit()

        embed = discord.Embed(
            title="\u2764\ufe0f Эмчилгээ хийгдлээ!",
            description=f"HP **{rpg['max_hp']}** болж сэргэлээ!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # ══════════════════════════════════════════════════════════
    #  /rpg  — RPG status
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="rpg", description="RPG тоглогчийн статусыг харах")
    async def rpg_status(self, ctx: commands.Context):
        rpg = await get_rpg(ctx.author.id, ctx.guild.id)
        hp_bar = "\u2665" * (rpg["hp"] // 10) + "\u2661" * ((rpg["max_hp"] - rpg["hp"]) // 10)
        embed = discord.Embed(
            title=f"\u2694\ufe0f {ctx.author.display_name}-н RPG статус",
            color=discord.Color.purple()
        )
        embed.add_field(name="\u2764\ufe0f HP",        value=f"**{rpg['hp']}/{rpg['max_hp']}**\n{hp_bar}", inline=False)
        embed.add_field(name="\u2694\ufe0f Дайралт",   value=f"**{rpg['attack']}**",  inline=True)
        embed.add_field(name="\U0001f6e1\ufe0f Хамгаалалт", value=f"**{rpg['defense']}**", inline=True)
        embed.add_field(name="\U0001f5e1\ufe0f Зэвсэг", value=f"**{rpg['weapon']}**",  inline=True)
        embed.add_field(name="\U0001f9e5 Хуяг",         value=f"**{rpg['armor']}**",   inline=True)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="/battle тулалдах  •  /heal эмчлэх  •  /shop other зэвсэг авах")
        await ctx.send(embed=embed)


    # ══════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════
    #  /rlb  — RPG kills leaderboard
    # ══════════════════════════════════════════════════════════
    @commands.hybrid_command(name="rlb", description="Дайчдын самбар — хамгийн их алуулсан топ жагсаалт")
    async def rlb(self, ctx: commands.Context):
        await ctx.defer()

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.user_id, r.kills
                FROM rpg r
                WHERE r.guild_id=? AND r.kills > 0
                ORDER BY r.kills DESC LIMIT 15
            """, (ctx.guild.id,))
            rows = await cursor.fetchall()

        if not rows:
            embed = discord.Embed(
                title="⚔️  RPG Дайчдын Самбар",
                description="⚠️ Одоо хэн алуулга байхгүй байна. `/battle` тоглоод эхлээ!",
                color=0x5865f2
            )
            await ctx.send(embed=embed)
            return

        def get_title(rank):
            if rank == 1:  return "\U0001f451 Баатар"
            if rank <= 3:  return "⚡ Хатан зоригт"
            if rank <= 7:  return "⚔️ Дайчин"
            return "\U0001fa96 Цэрэг"

        def get_medal(rank):
            if rank == 1: return "\U0001f947"
            if rank == 2: return "\U0001f948"
            if rank == 3: return "\U0001f949"
            return f"`#{rank:>2}`"

        def kill_bar(kills, top, length=8):
            filled = round(length * kills / top) if top else 0
            return "▰" * filled + "▱" * (length - filled)

        top_kills = rows[0]["kills"]
        lines = []
        for i, row in enumerate(rows):
            rank  = i + 1
            member = ctx.guild.get_member(row["user_id"])
            name   = (member.display_name if member else f"ID:{row['user_id']}")[:16]
            kills = row["kills"]
            bar   = kill_bar(kills, top_kills)
            pct   = int(kills / top_kills * 100)
            lines.append(
                f"{get_medal(rank)}  **{get_title(rank)}**\n"
                f"└ `{name}`  •  **{kills}** \U0001f480  `{bar}` {pct}%"
            )

        col1 = "\n\n".join(lines[:8])
        col2 = "\n\n".join(lines[8:]) if len(lines) > 8 else None

        sep = "─" * 28
        desc = (
            f"{sep}\n"
            f"\U0001f451 **Баатар**  •  "
            f"⚡ **Хатан зоригт** (2–3)  •  "
            f"⚔️ **Дайчин** (4–7)  •  "
            f"\U0001fa96 **Цэрэг** (8+)\n"
            f"{sep}"
        )

        embed = discord.Embed(
            title="⚔️  RPG Дайчдын Самбар  ⚔️",
            description=desc,
            color=0x5865f2
        )
        embed.add_field(name="\U0001f3c6 Топ дайчид", value=col1, inline=bool(col2))
        if col2:
            embed.add_field(name="​", value=col2, inline=True)
        embed.set_footer(text=f"\U0001f480 Нийт {len(rows)} дайчин  •  /battle тоглоод эрэмжлэлээ!")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Games(bot))
