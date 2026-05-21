import discord
from discord.ext import commands
from discord import app_commands

# ═══════════════════════════════════════════════════════════════
#  CATEGORIES  —  (command, emoji, description)
# ═══════════════════════════════════════════════════════════════
CATEGORIES = {
    "🎭 Дүр": {
        "emoji": "🎭",
        "description": "Роль-плэй дүр, нас, хүйс, ажил, мэргэжлийн курс",
        "commands": [
            ("/register",              "🎭", "Дүр үүсгэх — хүйс, чиг баримжаа, нас сонгоно"),
            ("/mychar [@хүн]",         "👤", "Дүрийн мэдээлэл — нас, хүйс, ажил, курс харах"),
            ("/jobs",                  "💼", "Бүх ажлын жагсаалт, шаардлага, цалин харах"),
            ("/setjob <ажил>",         "🏷️", "Ажлаа сонгох (нас 16+, хүйс болон курс шалгана)"),
            ("/courses",               "📚", "Боломжит курсуудын жагсаалт харах"),
            ("/enroll <курс>",         "🎓", "Курст элсэж мэргэжлийн ажил нээх (төлбөртэй)"),
        ],
    },
    "💰 Economy": {
        "emoji": "💰",
        "description": "Мөнгө, ажил, дэлгүүр, баялгийн систем",
        "commands": [
            ("/balance [@хүн]",          "💵", "Өөрийн эсвэл хүний мөнгөн үлдэгдэл харах"),
            ("/work",                    "💼", "Ажил хийж мөнгө олох (30мин cooldown)"),
            ("/daily",                   "🎁", "Өдөр тутмын урамшуулал авах (24ц cooldown)"),
            ("/transfer @хүн <дүн>",     "💸", "Өөр хүнд мөнгө шилжүүлэх"),
            ("/shop [категори]",          "🏪", "Дэлгүүр харах — категори сонгоход нарийвчилсан харагдана"),
            ("/buy <ID>",                "🛒", "Дэлгүүрээс бараа худалдаж авах"),
            ("/inventory",               "🎒", "Өөрийн эзэмшиж буй бүх зүйлс харах"),
            ("/richlist",                "🏆", "Серверийн TOP 10 баян хүмүүс"),
        ]
    },
    "⭐ Түвшин": {
        "emoji": "⭐",
        "description": "XP цуглуулж түвшин ахиулах, профайл харах",
        "commands": [
            ("/profile [@хүн]",          "👤", "Баланс, гэр бүл, хөрөнгө, шорон зэрэг дэлгэрэнгүй профайл"),
            ("/top",                     "📊", "Серверийн идэвхийн TOP 10 жагсаалт"),
        ]
    },
    "⚔️ Тоглоом": {
        "emoji": "⚔️",
        "description": "RPG тулаан, slot, зоос, шагай болон бусад тоглоомууд",
        "commands": [
            ("/battle",                  "⚔️", "RPG дайсантай тулалдах"),
            ("/rpg",                     "🧙", "RPG тоглогчийн статус, HP харах"),
            ("/heal",                    "💊", "HP сэргээх (inventory-аас эмчилгээ шаардана)"),
            ("/slot <бооцоо>",           "🎰", "Slot machine — мөнгө боох"),
            ("/coinflip <heads/tails> <бооцоо>", "🪙", "Зоос шидэх — 50/50, 2x"),
            ("/rps <сонголт> <бооцоо>",  "✂️", "Чулуу-Цаас-Хайч — bot-той тоглох"),
            ("/roulette <тавил> <бооцоо>","🎡","Рулетка — улаан/хар/сондгой/тэгш/тоо"),
            ("/shagai <бооцоо>",         "🦴", "Шагай шидэх — Монгол уламжлалт 4 шагайн тоглоом"),
        ]
    },
    "👨‍👩‍👧 Гэр бүл": {
        "emoji": "👨‍👩‍👧",
        "description": "Гэрлэх, хүүхэд үрчлэх, байшин авах систем",
        "commands": [
            ("/marry @хүн",              "💍", "Гэрлэлтийн санал тавих (бөгж шаардана) — товч дарж зөвшөөрнө"),
            ("/divorce",                 "💔", "Гэрлэлт цуцлах"),
            ("/adopt @хүн",              "👶", "Хүүхэд үрчлэх (adoption paper шаардана) — товч дарж зөвшөөрнө"),
            ("/family [@хүн]",           "🏠", "Гэр бүл болон үл хөдлөх хөрөнгийн мэдээлэл харах"),
            ("/buyhouse",                "🏡", "Жижиг байшин авах (10,000,000 ₮)"),
            ("/upgradehouse",            "🔨", "Байшинг дараагийн түвшинд ахиулах (60% зарж нэмэлт төлнө)"),
            ("/sellhouse",               "🏚️", "Байшингаа зарах — үнийн 60% буцаан авна"),
            ("/payschool",               "🎓", "Виртуал хүүхдийг коллежд сургах (500,000 ₮) — цалин нэмэгдэнэ"),
        ]
    },
    "🍺 Архи & Мансуурал": {
        "emoji": "🍺",
        "description": "Архи ууж согтох, тамхи/вэйп татаж мансуурах систем",
        "commands": [
            ("/drink <ID>",              "🍺", "Inventory-аас архи ууж согтолтын түвшин нэмэх"),
            ("/smoke <ID>",              "💨", "Inventory-аас тамхи/вэйп татаж мансуурлын түвшин нэмэх"),
            ("/mystate",                 "🧠", "Өөрийн согтолт болон мансуурлын одоогийн түвшин харах"),
            ("/eruuljuuleh",             "🚔", "Шоронгийн статус болон ранк харах"),
            ("/prisonlist",              "📋", "Одоо эрүүлжүүлэхэд байгаа хүмүүсийн жагсаалт"),
            ("/shop alcohol",            "🏪", "Архины жагсаалт харах (10 төрөл)"),
            ("/shop cigarette",          "🏪", "Тамхины жагсаалт харах (5 төрөл)"),
            ("/shop vape",               "🏪", "Вэйпийн жагсаалт харах (5 төрөл)"),
        ]
    },
    "💍 Бөгж & Аксессуар": {
        "emoji": "💍",
        "description": "Бөгж, цаг, хүзүүвч гинж — гоёл чимэглэлийн зүйлс",
        "commands": [
            ("/shop ring",               "💍", "Бөгжний жагсаалт — 8 төрөл (хуванцараас бриллиант хүртэл)"),
            ("/shop accessory",          "⌚", "Гоёл чимэглэлийн жагсаалт — цаг, гинж, бугуйвч г.м"),
            ("/buy <ID>",                "🛒", "Бөгж эсвэл гоёл чимэглэл худалдаж авах"),
            ("/inventory",               "🎒", "Өөрийн эзэмшиж буй бөгж, гоёл чимэглэл харах"),
            ("/marry @хүн",              "💒", "Гэрлэхдээ бөгж шаарддаг — /shop ring дээрээс авна уу"),
        ]
    },
    "💎 Үнэт чулуу & Хөрөнгө": {
        "emoji": "💎",
        "description": "Алт, алмаз, рубин болон хөдлөх/үл хөдлөх хөрөнгийн систем",
        "commands": [
            ("/shop gem",                "💎", "Үнэт чулууны жагсаалт (8 төрөл)"),
            ("/shop vehicle",            "🚗", "Хөдлөх хөрөнгийн жагсаалт (дугуй → нисдэг тэрэг)"),
            ("/shop realestate",         "🏠", "Үл хөдлөх хөрөнгийн мэдээлэл харах"),
            ("/buy <ID>",                "🛒", "Үнэт чулуу эсвэл хөдлөх хөрөнгө авах"),
            ("/buyhouse",                "🏡", "Байшин авах (/shop realestate мэдээллийг харна уу)"),
        ]
    },
    "📊 Статистик": {
        "emoji": "📊",
        "description": "Серверийн болон гишүүдийн статистик мэдээлэл",
        "commands": [
            ("/stats [@хүн]",            "📈", "Гишүүний дэлгэрэнгүй статистик"),
            ("/active",                  "🔥", "Серверийн хамгийн идэвхтэй гишүүд"),
            ("/serverinfo",              "🖥️", "Серверийн ерөнхий мэдээлэл харах"),
        ]
    },
    "🛡️ Admin": {
        "emoji": "🛡️",
        "description": "Серверийн удирдлагын командууд (зөвхөн админ)",
        "commands": [
            ("/givemoney @хүн <дүн>",             "💸", "Хэрэглэгчид мөнгө нэмэх"),
            ("/releaseprison @хүн",               "🔓", "Хэрэглэгчийг эрүүлжүүлэхээс чөлөөлөх"),
            ("/giverole @хүн @role",              "✅", "Гишүүнд role олгох"),
            ("/removerole @хүн @role",             "❌", "Гишүүний role хасах"),
            ("/level_role_add <түвшин> @role",     "🎖️", "Тодорхой түвшинд автомат role тохируулах"),
            ("/adminsetage @хүн <нас>",           "🎂", "Дүрийн насыг тохируулах"),
            ("/adminsetgender @хүн <хүйс>",       "⚧️", "Дүрийн хүйсийг тохируулах"),
            ("/adminsetsexuality @хүн <чиг>",     "🌈", "Дүрийн чиг баримжаа тохируулах"),
            ("/adminsetjob @хүн <ажил>",          "💼", "Дүрийн ажлыг тохируулах"),
            ("/adminrevive @хүн",                 "✨", "Нас барсан дүрийг амилуулах"),
            ("/adminkill @хүн",                   "💀", "Дүрийг нас барахад хүргэх"),
            ("/adminsetbalance @хүн <дүн>",       "💰", "Хэрэглэгчийн мөнгийг тохируулах"),
            ("/adminaddbalance @хүн <дүн>",       "➕", "Хэрэглэгчид мөнгө нэмэх/хасах"),
            ("/adminsetlevel @хүн <түвшин>",      "⭐", "Хэрэглэгчийн түвшин тохируулах"),
            ("/adminresetchar @хүн",              "🔄", "Дүрийн мэдээллийг шинэчлэх"),
            ("/adminsetprison @хүн <минут>",      "🚔", "Хэрэглэгчийг эрүүлжүүлэхэд хийх"),
            ("/adminresetcooldown @хүн",          "⏱️", "Хэрэглэгчийн cooldown-уудыг арилгах"),
        ]
    },
}

# ═══════════════════════════════════════════════════════════════
#  EMBED builders
# ═══════════════════════════════════════════════════════════════

def make_home_embed(bot_user=None):
    embed = discord.Embed(
        title="👑 TOP Bot — Тусламж",
        description="Доорх **Category** сонгоод командуудыг харна уу!",
        color=0x5865F2
    )
    for cat, data in CATEGORIES.items():
        embed.add_field(
            name=cat,
            value=f"*{data['description']}*\n`{len(data['commands'])} команд`",
            inline=True
        )
    if bot_user:
        embed.set_thumbnail(url=bot_user.display_avatar.url)
    embed.set_footer(text="TOP Bot  •  /help командаар нүүр хуудас руу буцна")
    return embed

def make_category_embed(cat_name, data, bot_user=None):
    embed = discord.Embed(
        title=f"{cat_name} commands",
        description=data["description"],
        color=0x5865F2
    )
    lines = []
    for cmd, emoji, desc in data["commands"]:
        lines.append(f"`{cmd}`\n{emoji}  {desc}")
    embed.add_field(name="​", value="\n\n".join(lines), inline=False)
    if bot_user:
        embed.set_thumbnail(url=bot_user.display_avatar.url)
    embed.set_footer(text="TOP Bot  •  /help командаар нүүр хуудас руу буцна")
    return embed

# ═══════════════════════════════════════════════════════════════
#  UI Components
# ═══════════════════════════════════════════════════════════════

class CategorySelect(discord.ui.Select):
    def __init__(self, bot_user):
        self.bot_user = bot_user
        options = [
            discord.SelectOption(
                label=cat,
                emoji=data["emoji"],
                description=data["description"][:50]
            )
            for cat, data in CATEGORIES.items()
        ]
        super().__init__(
            placeholder="📂  Category сонгоно уу...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        data  = CATEGORIES[selected]
        embed = make_category_embed(selected, data, self.bot_user)
        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, bot_user):
        super().__init__(timeout=180)
        self.bot_user = bot_user
        self.add_item(CategorySelect(bot_user))

    @discord.ui.button(label="🏠  Нүүр", style=discord.ButtonStyle.secondary, row=1)
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_home_embed(self.bot_user)
        await interaction.response.edit_message(embed=embed, view=self)

# ═══════════════════════════════════════════════════════════════
#  Cog
# ═══════════════════════════════════════════════════════════════

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Бүх командын жагсаалт харах")
    async def help(self, interaction: discord.Interaction):
        embed = make_home_embed(self.bot.user)
        view  = HelpView(self.bot.user)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Help(bot))