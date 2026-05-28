import discord
from discord.ext import commands
from discord import app_commands

APPLY_CHANNEL_ID = 1505175243042590813


class ApplyView(discord.ui.View):
    def __init__(self, applicant_id: int):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success, custom_id="apply_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = await interaction.client.fetch_user(self.applicant_id)
            await user.send(
                embed=discord.Embed(
                    title="✅ Хүсэлт зөвшөөрөгдлөө!",
                    description="Таны элсэлтийн хүсэлт **зөвшөөрөгдлөө**.",
                    color=discord.Color.green()
                )
            )
        except Exception:
            pass
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ Зөвшөөрсөн: {interaction.user.display_name}")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("✅ Хүсэлт зөвшөөрөгдлөө.", ephemeral=True)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id="apply_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = await interaction.client.fetch_user(self.applicant_id)
            await user.send(
                embed=discord.Embed(
                    title="❌ Хүсэлт татгалзагдлаа",
                    description="Таны элсэлтийн хүсэлт **татгалзагдлаа**.",
                    color=discord.Color.red()
                )
            )
        except Exception:
            pass
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = discord.Color.red()
        embed.set_footer(text=f"❌ Татгалзсан: {interaction.user.display_name}")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("❌ Хүсэлт татгалзагдлаа.", ephemeral=True)


class Apply(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Persistent view бүртгэх
        bot.add_view(ApplyView(0))

    @commands.hybrid_command(name="apply", description="Серверт элсэх хүсэлт илгээх")
    async def apply(self, ctx: commands.Context):
        channel = self.bot.get_channel(APPLY_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(APPLY_CHANNEL_ID)
            except Exception:
                await ctx.send("❌ Хүсэлт илгээх channel олдсонгүй.", ephemeral=True)
                return

        embed = discord.Embed(
            title="📋 Шинэ элсэлтийн хүсэлт",
            color=0x5865F2
        )
        embed.add_field(name="👤 Хэрэглэгч", value=f"{ctx.author.mention}\n`{ctx.author}`", inline=True)
        embed.add_field(name="🆔 ID", value=f"`{ctx.author.id}`", inline=True)
        if ctx.guild:
            embed.add_field(name="🌐 Сервер", value=ctx.guild.name, inline=True)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = ApplyView(ctx.author.id)
        try:
            await channel.send(embed=embed, view=view)
        except Exception as e:
            await ctx.send("❌ Хүсэлт илгээхэд алдаа гарлаа.", ephemeral=True)
            return

        await ctx.send(
            embed=discord.Embed(
                title="📨 Хүсэлт илгээгдлээ!",
                description="Таны хүсэлт амжилттай илгээгдлээ.\nХариу DM-ээр ирнэ.",
                color=discord.Color.blurple()
            ),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Apply(bot))
