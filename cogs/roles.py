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

    @app_commands.command(name="giverole", description="Гишүүнд role өгөх [Admin]")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def give_role(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.add_roles(role)
        await interaction.response.send_message(f"✅ {member.mention}-д {role.mention} role өгөгдлөө!")

    @app_commands.command(name="removerole", description="Гишүүний role-г авах [Admin]")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_role(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.remove_roles(role)
        await interaction.response.send_message(f"✅ {member.mention}-ийн {role.mention} role авагдлаа!")

async def setup(bot):
    await bot.add_cog(Roles(bot))
