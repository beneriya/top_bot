import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from database import DB_PATH, get_user
from datetime import datetime

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Гишүүний дэлгэрэнгүй статистик")
    async def stats(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user = await get_user(target.id, interaction.guild_id)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM users WHERE guild_id=? AND balance > ?",
                (interaction.guild_id, user["balance"])
            )
            row = await cursor.fetchone()
            rank = row[0] + 1

        # ── Мориитой тоглоомын статистик ────────────────────────
        g_wins   = user["game_wins"]        if "game_wins"        in user.keys() else 0
        g_losses = user["game_losses"]      if "game_losses"      in user.keys() else 0
        g_won    = user["game_won_amount"]  if "game_won_amount"  in user.keys() else 0
        g_lost   = user["game_lost_amount"] if "game_lost_amount" in user.keys() else 0
        g_wager  = user["game_wagered"]     if "game_wagered"     in user.keys() else 0

        g_played = g_wins + g_losses
        win_rate = (g_wins / g_played * 100) if g_played > 0 else 0
        net      = g_won - g_lost

        if g_played == 0:
            luck = "❓ Тоглоогүй"
        elif win_rate >= 65:
            luck = "🍀 Маш азтай"
        elif win_rate >= 55:
            luck = "😊 Азтай"
        elif win_rate >= 45:
            luck = "😐 Дундаж"
        elif win_rate >= 35:
            luck = "😬 Дутуу азтай"
        else:
            luck = "💀 Азгүй"

        net_str = f"+{net:,} ₮" if net >= 0 else f"{net:,} ₮"

        tension   = user["tension"]   if "tension"   in user.keys() else 0
        bank_bal  = user["bank"]      if "bank"      in user.keys() else 0
        happiness = user["happiness"] if "happiness" in user.keys() else 10
        h_filled = round(10 * happiness / 20)
        h_bar    = "█" * h_filled + "░" * (10 - h_filled)
        t_bar    = "⚡" * tension + "▫️" * max(0, 6 - tension)
        h_emoji  = "😊" if happiness >= 15 else ("😐" if happiness >= 8 else "😔")
        joined   = target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "—"
        embed = discord.Embed(
            title=f"📊  {target.display_name}",
            color=0x5865F2
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="⭐ Түвшин",     value=f"**{user['level']}**",       inline=True)
        embed.add_field(name="✨ XP",          value=f"**{user['xp']:,}**",        inline=True)
        embed.add_field(name="🏆 Зэрэгэлэл",  value=f"**#{rank}**",               inline=True)
        embed.add_field(name="💰 Pocket",    value=f"**{user['balance']:,} ₮**", inline=True)
        embed.add_field(name="🏦 Bank",      value=f"**{bank_bal:,} ₮**",        inline=True)
        embed.add_field(name="💬 Мессэж",     value=f"**{user['messages']:,}**",  inline=True)
        embed.add_field(
            name=f"{h_emoji} Аз жаргал",
            value=f"`{h_bar}` **{happiness}/20**",
            inline=True
        )
        embed.add_field(name="⚡ Тэнсэн", value=f"**{tension}/6**  {t_bar}", inline=True)
        embed.add_field(name="📅 Нэгдсэн",   value=joined, inline=True)
        win_bar_f = round(10 * g_wins / g_played) if g_played else 0
        win_bar   = "✅" * win_bar_f + "❌" * (10 - win_bar_f)
        embed.add_field(
            name="────────────────────────",
            value=(
                f"🎲 **Мориитой тоглоом**  •  {g_played:,} тоглолт  •  {luck}\n"
                f"`{win_bar}` {win_rate:.1f}% win rate  •  ✅ {g_wins:,}  │  ❌ {g_losses:,}\n"
                f"💸 Урсгасан: **{g_wager:,} ₮**  •  📉 Цэвэр: **{net_str}**"
            ),
            inline=False
        )
        embed.set_footer(text=f"TOP Bot  •  /stats  •  {joined} нэгдсэн")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Серверийн статистик харах")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*), SUM(messages), SUM(balance) FROM users WHERE guild_id=?",
                (guild.id,)
            )
            row = await cursor.fetchone()

        created = guild.created_at.strftime("%Y-%m-%d")
        embed = discord.Embed(
            title=f"🌐  {guild.name}",
            color=0x5865F2
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.add_field(name="👥 Гишүүд",      value=f"**{guild.member_count:,}**",    inline=True)
        embed.add_field(name="💬 Каналууд",    value=f"**{len(guild.channels):,}**",   inline=True)
        embed.add_field(name="🎭 Roles",       value=f"**{len(guild.roles):,}**",      inline=True)
        embed.add_field(name="📨 Нийт мессеж", value=f"**{row[1] or 0:,}**",           inline=True)
        embed.add_field(name="💰 Эдийн засаг", value=f"**{row[2] or 0:,} ₮**",         inline=True)
        embed.add_field(name="📅 Үүссэн",      value=created,                           inline=True)
        embed.set_footer(text="TOP Bot  •  /serverinfo")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="active", description="Серверийн хамгийн идэвхтэй гишүүд")
    async def most_active(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT user_id, messages FROM users WHERE guild_id=? ORDER BY messages DESC LIMIT 10",
                (interaction.guild_id,)
            )
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("⚠️ Мэдээлэл байхгүй.", ephemeral=True)
            return
        top_msg = rows[0]["messages"] or 1
        medals  = ["🥇", "🥈", "🥉"]
        def mbar(n, mx, length=8):
            filled = round(length * n / mx) if mx else 0
            return "█" * filled + "░" * (length - filled)
        lines = []
        for i, row in enumerate(rows):
            m   = interaction.guild.get_member(row["user_id"])
            nm  = (m.display_name if m else f"User#{row['user_id']}")[:16]
            med = medals[i] if i < 3 else f"`#{i+1:>2}`"
            bar = mbar(row["messages"], top_msg)
            pct = int(row["messages"] / top_msg * 100)
            lines.append(f"{med}  `{bar}` **{row['messages']:,}**  •  {nm}")
        embed = discord.Embed(
            title="💬  Хамгийн идэвхтэй гишүүд",
            description="\n".join(lines),
            color=0x57F287
        )
        embed.set_footer(text="TOP Bot  •  /active  •  Мессежний тоогоор эрэмбэлсэн")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
