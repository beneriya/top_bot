import discord
from discord.ext import commands
from discord import app_commands

CATEGORIES = {
    "🎭 Дүр": {
        "emoji": "🎭",
        "description": "Роль-плэй дүр, нас, хүйс, ажил, мэргэжлийн курс",
        "commands": [
            ("/register",             "🎭", "Дүр үүсгэх — хүйс, чиг баримжаа, ажил сонгоно"),
            ("/mychar [@хүн]",        "👤", "Дүрийн мэдээлэл — нас, хүйс, ажил, курс харах"),
            ("/jobs",                 "💼", "Бүх ажлын жагсаалт, шаардлага, цалин харах"),
            ("/setjob <ажил>",        "🏷️", "Ажлаа сонгох (нас 16+, хүйс болон курс шалгана)"),
            ("/courses",              "📚", "Боломжит курсуудын жагсаалт харах"),
            ("/enroll <курс>",       "🎓", "Курст элсэж мэргэжлийн ажил нээх (төлбөртэй)"),
        ],
    },
    "💰 Economy": {
        "emoji": "💰",
        "description": "Мөнгө олох, шилжүүлэх, дэлгүүр, инвентори",
        "commands": [
            ("/balance [@хүн]",   "💵", "Pocket болон bank үлдэгдэл харах"),
            ("/work",               "💼", "Ажил хийж мөнгө олох (30 мин cooldown)"),
            ("/daily",              "🎁", "Өдөр тутмын урамшуулал авах (24 цаг cooldown)"),
            ("/transfer @хүн <дүн>", "💸", "Өөр хүнд мөнгө шилжүүлэх"),
            ("/shop [категори]",   "🏪", "Дэлгүүр харах — food / alcohol / gem / vehicle г.m"),
            ("/buy <ID> [тоо]",  "🛒", "Дэлгүүрээс бараа авах — /buy 93 эсвэл /buy 93 5"),
            ("/inventory",          "🎒", "Өөрийн эзэмшиж буй бүх зүйлс харах"),
            ("/richlist",           "🏆", "Серверийн TOP 10 баян хүмүүс"),
        ],
    },
    "🏦 Банк": {
        "emoji": "🏦",
        "description": "Банкны данс — хадгалах, гаргах, мэдээлэл",
        "commands": [
            ("/bank [@хүн]",        "🏦", "Pocket + Bank + Inventory нийт хөрөнгө харах"),
            ("/deposit <дүн>",      "📥", "Pocket мөнгийг банкинд хийх (rob-оос хамгаалагдана)"),
            ("/withdraw <дүн>",     "📤", "Банкнаас pocket-руу мөнгө гаргах"),
        ],
    },
    "🍽️ Хоол & Аз жаргал": {
        "emoji": "🍽️",
        "description": "Хоол идэж аз жаргалын түвшин нэмэх — ажлын цалинд нөлөөлөнө",
        "commands": [
            ("/happiness [@хүн]",   "❤️", "Аз жаргалын түвшин болон ажлын өгөөж харах"),
            ("/eat <ID>",              "🍽️", "Хоол идэж аз жаргал нэмэх (20/20 дүүрвэл penalty)"),
            ("/shop food",             "🏪", "Хоол, идшийн жагсаалт харах (8 төрөл)"),
        ],
    },
    "🦹 Гэмт хэрэг": {
        "emoji": "🦹",
        "description": "Хулгай, хак — эрсдэлтэй, шоронд орж болно",
        "commands": [
            ("/rob @хүн",           "🥷", "Хүний pocket-аас хулгай — 45% амжилт, 1ц cooldown"),
            ("/hack @хүн",          "💻", "Банк данс хак — зөвхөн Programmer, 35% амжилт, 2ц cooldown"),
            ("/eruuljuuleh",           "🚔", "Шоронгийн статус болон ранк харах"),
            ("/prisonlist",            "📋", "Одоо шоронд байгаа хүмүүсийн жагсаалт"),
        ],
    },
    "⭐ Түвшин": {
        "emoji": "⭐",
        "description": "XP цуглуулж түвшин ахиулах, профайл харах",
        "commands": [
            ("/profile [@хүн]",     "👤", "Дэлгэрэнгүй профайл — баланс, гэр бүл, хөрөнгө, шорон"),
            ("/top",                   "📊", "Серверийн идэвхийн TOP 10 жагсаалт"),
            ("/stats [@хүн]",       "📈", "Гишүүний статистик — тоглоом, мөнгө, аз жаргал"),
        ],
    },
    "⚔️ Тоглоом": {
        "emoji": "⚔️",
        "description": "RPG тулаан, slot, шагай болон бусад тоглоомууд",
        "commands": [
            ("/battle",               "⚔️", "RPG дайсантай тулалдах"),
            ("/rpg",                  "🧙", "RPG тоглогчийн статус, HP харах"),
            ("/heal",                 "💊", "HP сэргээх (inventory-аас heal item шаардана)"),
            ("/rlb",                  "🏆", "Дайчдын самбар — хамгийн их kill хийсэн TOP 15"),
            ("/slot <бооцоо>",      "🎰", "Slot machine — мөнгө боох"),
            ("/coinflip <сонголт> <бооцоо>", "🪙", "Зоос шидэх — 50/50, 1.7x"),
            ("/rps <сонголт> <бооцоо>", "✂️", "Чулуу-Цаас-Хайч — bot-той тоглох, 1.5x"),
            ("/roulette <тавил> <бооцоо>", "🎡", "Рулетка — улаан/хар/тоо — 1.7x ~ 30x"),
            ("/shagai <бооцоо>",    "🦴", "Шагай — Монгол уламжлалт 4 шагайн тоглоом"),
        ],
    },
    "👨‍👩‍👧 Гэр бүл": {
        "emoji": "👪",
        "description": "Гэрлэх, хүүхэд үрчлэх, байшин авах систем",
        "commands": [
            ("/marry @хүн",          "💍", "Гэрлэлтийн санал тавих (бөгж шаардана)"),
            ("/divorce",               "💔", "Гэрлэлт цуцлах"),
            ("/adopt @хүн",          "👶", "Хүүхэд үрчлэх (adoption paper шаардана)"),
            ("/family [@хүн]",       "🏠", "Гэр бүл болон үл хөдлөх хөрөнгөийн мэдээлэл"),
            ("/buyhouse",              "🏡", "Байшин авах — /shop realestate мэдээлэл харна"),
            ("/upgradehouse",          "🔨", "Байшингаа дараагийн түвшинд ахиулах"),
            ("/sellhouse",             "🏚️", "Байшингаа зарах — үнийн 60% буцаан авна"),
            ("/payschool",             "🎓", "Виртуал хүүхэдийг коллежд сургах (500,000 ₮)"),
        ],
    },
    "🍺 Архи & Мансуурал": {
        "emoji": "🍺",
        "description": "Архи ууж согтох, тамхи/вэйп татаж мансуурах",
        "commands": [
            ("/drink <ID>",            "🍺", "Архи ууж согтолтын түвшин нэмэх (MAX→шоронд)"),
            ("/smoke <ID>",            "💨", "Тамхи/вэйп татаж мансуурлын түвшин нэмэх"),
            ("/mystate",               "🧠", "Өөрийн согтолт болон мансуурлын түвшин харах"),
            ("/shop alcohol",          "🏪", "Архины жагсаалт (10 төрөл)"),
            ("/shop cigarette",        "🚬", "Тамхины жагсаалт (5 төрөл)"),
            ("/shop vape",             "💨", "Вэйпийн жагсаалт (5 төрөл)"),
        ],
    },
    "💍 Бөгж & Гоёл": {
        "emoji": "💍",
        "description": "Бөгж, цаг, хүзүүвч — гоёл чимэглэлийн зүйлс",
        "commands": [
            ("/shop ring",             "💍", "Бөгжний жагсаалт — 8 төрөл (хуванцараас бриллиант хүртэл)"),
            ("/shop accessory",        "⌚", "Гоёл чимэглэлийн жагсаалт — цаг, гинж, бугуйвч"),
            ("/buy <ID>",              "🛒", "Бөгж эсвэл гоёл чимэглэл авах"),
            ("/marry @хүн",          "💒", "Гэрлэхдээ бөгж шаардана — /shop ring"),
        ],
    },
    "💎 Үнэт чулуу & Хөрөнгө": {
        "emoji": "💎",
        "description": "Алт, алмаз, рубин болон хөдлөх/үл хөдлөх хөрөнгө",
        "commands": [
            ("/shop gem",              "💎", "Үнэт чулууны жагсаалт — 8 төрөл"),
            ("/shop vehicle",          "🚗", "Хөдлөх хөрөнгөийн жагсаалт — дугуйнаас нисдэг тэрэг"),
            ("/shop realestate",       "🏠", "Байшингийн үнэ, тайлбар харах"),
            ("/buy <ID>",              "🛒", "Үнэт чулуу эсвэл хөдлөх хөрөнгө авах"),
        ],
    },
    "🛡️ Admin": {
        "emoji": "🛡️",
        "description": "Серверийн удирдлагын командууд (зөвхөн Admin)",
        "commands": [
            ("/givemoney @хүн <дүн>",          "💸", "Хэрэглэгчид мөнгө нэмэх"),
            ("/releaseprison @хүн",             "🔓", "Эрүүлжүүлэхээс чөлөөлөх"),
            ("/giverole @хүн @role",            "✅", "Гишүүнд role олгох"),
            ("/removerole @хүн @role",          "❌", "Гишүүний role хасах"),
            ("/level_role_add <түвшин> @role",  "🎖️", "Тодорхой түвшинд автомат role тохируулах"),
            ("/adminsetage @хүн <нас>",         "🎂", "Дүрийн насыг тохируулах"),
            ("/adminsetgender @хүн <хүйс>",     "⚧️", "Дүрийн хүйсийг тохируулах"),
            ("/adminsetsexuality @хүн <чиг>",   "🌈", "Дүрийн чиг баримжаа тохируулах"),
            ("/adminsetjob @хүн <ажил>",        "💼", "Дүрийн ажлыг тохируулах"),
            ("/adminrevive @хүн",               "✨", "Нас барсан дүрийг амилуулах"),
            ("/adminkill @хүн",                 "💀", "Дүрийг нас барахад хүргэх"),
            ("/adminsetbalance @хүн <дүн>",     "💰", "Хэрэглэгчийн мөнгийг тохируулах"),
            ("/adminaddbalance @хүн <дүн>",     "➕", "Хэрэглэгчид мөнгө нэмэх/хасах"),
            ("/adminsetlevel @хүн <түвшин>",    "⭐", "Хэрэглэгчийн түвшин тохируулах"),
            ("/adminresetchar @хүн",             "🔄", "Дүрийн мэдээлэлийг шинэчлэх"),
            ("/adminsetprison @хүн <минут>",    "🚔", "Хэрэглэгчийг шоронд хийх"),
            ("/adminresetcooldown @хүн",         "⏱️", "Хэрэглэгчийн cooldown-уудыг арилгах"),
        ],
    },
}

TOTAL_COMMANDS = sum(len(v["commands"]) for v in CATEGORIES.values())


def make_home_embed(bot_user=None):
    embed = discord.Embed(
        title="👑 TOP Bot — Командын тусламж",
        description=(
            "Доорх **Category** сонгоод командуудыг харна уу!\n"
            f"📋 Нийт **{TOTAL_COMMANDS}** команд  •  🗂️ **{len(CATEGORIES)}** категори"
        ),
        color=0x5865F2,
    )
    for cat, data in CATEGORIES.items():
        embed.add_field(
            name=cat,
            value=f"*{data['description'][:55]}*\n`{len(data['commands'])} команд`",
            inline=True,
        )
    if bot_user:
        embed.set_thumbnail(url=bot_user.display_avatar.url)
    embed.set_footer(text="TOP Bot  •  /help командаар нүүр хуудас руу буцна")
    return embed


def make_category_embed(cat_name: str, data: dict, bot_user=None):
    embed = discord.Embed(
        title=cat_name,
        description=data["description"],
        color=0x5865F2,
    )
    cmds = data["commands"]
    mid  = (len(cmds) + 1) // 2
    for chunk in [cmds[:mid], cmds[mid:]]:
        if not chunk:
            continue
        lines = []
        for cmd, emoji, desc in chunk:
            lines.append(f"`{cmd}`\n{emoji}  {desc}")
        embed.add_field(name="\u200b", value="\n\n".join(lines), inline=True)
    if bot_user:
        embed.set_thumbnail(url=bot_user.display_avatar.url)
    embed.set_footer(text="TOP Bot  •  /help командаар нүүр хуудас руу буцна")
    return embed


class CategorySelect(discord.ui.Select):
    def __init__(self, bot_user):
        self.bot_user = bot_user
        options = [
            discord.SelectOption(
                label=cat,
                emoji=data["emoji"],
                description=data["description"][:50],
            )
            for cat, data in CATEGORIES.items()
        ]
        super().__init__(
            placeholder="📂  Category сонгоно уу...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        data     = CATEGORIES[selected]
        embed    = make_category_embed(selected, data, self.bot_user)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot_user, invite_url: str = ""):
        super().__init__(timeout=180)
        self.bot_user = bot_user
        self.add_item(CategorySelect(bot_user))

    @discord.ui.button(label="🏠  Нүүр", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_home_embed(self.bot_user)
        await interaction.response.edit_message(embed=embed, view=self)


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Бүх командын жагсаалт харах")
    async def help(self, interaction: discord.Interaction):
        client_id  = self.bot.user.id
        invite_url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={client_id}"
            f"&permissions=2147609664"
            f"&scope=bot+applications.commands"
        )
        embed = make_home_embed(self.bot.user)
        view  = HelpView(self.bot.user, invite_url)

        # Invite товч динамикаар нэмэх
        invite_btn = discord.ui.Button(
            label="🔗  Серверт нэмэх",
            style=discord.ButtonStyle.link,
            url=invite_url,
            row=1,
        )
        view.add_item(invite_btn)

        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
