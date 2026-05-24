import discord
from discord.ext import commands
from discord import app_commands
from config import MANAGER_ROLE_NAME, OWNER_ID

def _is_admin_or_manager(member: discord.Member, author_id: int) -> bool:
    if member.guild_permissions.administrator or author_id == OWNER_ID:
        return True
    return any(r.name == MANAGER_ROLE_NAME for r in member.roles)

def _is_admin(member: discord.Member, author_id: int) -> bool:
    return member.guild_permissions.administrator or author_id == OWNER_ID

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
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

    @commands.hybrid_command(name="giverole", description="Гишүүнд role өгөх [Admin/Manager]")
    async def give_role(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        m = ctx.guild.get_member(ctx.author.id)
        if not m or not _is_admin_or_manager(m, ctx.author.id):
            await ctx.send(f"🚫 Зөвхөн **Admin** эсвэл **{MANAGER_ROLE_NAME}** ашиглах боломжтой!", ephemeral=True)
            return
        if role.name == MANAGER_ROLE_NAME and not _is_admin(m, ctx.author.id):
            await ctx.send(f"🚫 **{MANAGER_ROLE_NAME}** role-г зөвхөн **Admin** өгч болно!", ephemeral=True)
            return
        await member.add_roles(role)
        await ctx.send(f"✅ {member.mention}-д {role.mention} role өгөгдлөө!")

    @commands.hybrid_command(name="removerole", description="Гишүүний role-г авах [Admin/Manager]")
    async def remove_role(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        m = ctx.guild.get_member(ctx.author.id)
        if not m or not _is_admin_or_manager(m, ctx.author.id):
            await ctx.send(f"🚫 Зөвхөн **Admin** эсвэл **{MANAGER_ROLE_NAME}** ашиглах боломжгүй!", ephemeral=True)
            return
        if role.name == MANAGER_ROLE_NAME and not _is_admin(m, ctx.author.id):
            await ctx.send(f"🚫 **{MANAGER_ROLE_NAME}** role-г зөвхөн **Admin** хасч болно!", ephemeral=True)
            return
        await member.remove_roles(role)
        await ctx.send(f"✅ {member.mention}-ийн {role.mention} role авагдлаа!")

async def setup(bot):
    await bot.add_cog(Roles(bot))
