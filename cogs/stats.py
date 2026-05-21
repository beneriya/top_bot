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

        embed = discord.Embed(
            title=f"📊 {target.display_name}-н статистик",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="⭐ Түвшин", value=f"**{user['level']}**", inline=True)
        embed.add_field(name="💰 Үлдэгдэл", value=f"**{user['balance']:,} ₮**", inline=True)
        embed.add_field(name="🏆 Зэрэглэл", value=f"**#{rank}**", inline=True)
        embed.add_field(name="💬 Нийт мессеж", value=f"**{user['messages']:,}**", inline=True)
        embed.add_field(name="✨ XP", value=f"**{user['xp']}**", inline=True)
        joined = target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "Тодорхойгүй"
        embed.add_field(name="📅 Нэгдсэн огноо", value=joined, inline=True)
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

        embed = discord.Embed(title=f"🌐 {guild.name}", color=discord.Color.blue())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.add_field(name="👥 Нийт гишүүн", value=f"**{guild.member_count}**", inline=True)
        embed.add_field(name="💬 Нийт каналууд", value=f"**{len(guild.channels)}**", inline=True)
        embed.add_field(name="🎭 Нийт role", value=f"**{len(guild.roles)}**", inline=True)
        embed.add_field(name="📨 Нийт мессеж", value=f"**{row[1] or 0:,}**", inline=True)
        embed.add_field(name="💰 Нийт эдийн засаг", value=f"**{row[2] or 0:,} ₮**", inline=True)
        created = guild.created_at.strftime("%Y-%m-%d")
        embed.add_field(name="📅 Үүссэн огноо", value=created, inline=True)
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

        embed = discord.Embed(title="💬 Хамгийн идэвхтэй гишүүд TOP 10", color=discord.Color.green())
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"ID:{row['user_id']}"
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            embed.add_field(
                name=f"{medal} {name}",
                value=f"💬 **{row['messages']:,}** мессеж",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
