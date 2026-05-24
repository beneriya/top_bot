import discord
from discord.ext import commands
from discord import app_commands

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Шинэ гишүүнд тавтай морилох мессеж
        for channel in member.guild.text_channels:
            if "general" in channel.name.lower() or "нийтлэг" in channel.name.lower():
                embed = discord.Embed(
                    title="👋 Тавтай морил!",
                    description=f"{member.mention} серверт нэгдлээ! Нийт гишүүн: **{member.guild.member_count}**",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
                break

    @commands.hybrid_command(name="giverole", description="Гишүүнд role өгөх [Admin]")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def give_role(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        await member.add_roles(role)
        await ctx.send(f"✅ {member.mention}-д {role.mention} role өгөгдлөө!")

    @commands.hybrid_command(name="removerole", description="Гишүүний role-г авах [Admin]")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_role(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        await member.remove_roles(role)
        await ctx.send(f"✅ {member.mention}-ийн {role.mention} role авагдлаа!")

async def setup(bot):
    await bot.add_cog(Roles(bot))
