import aiosqlite
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "bot.db")

# HOUSES нь config.py-д тодорхойлогдсон — дагалдуулан export хийнэ
from config import HOUSES  # noqa: E402  (circular-safe: config has no bot imports)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:

        # ── bot_config ───────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # ── users ────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id             INTEGER,
                guild_id            INTEGER,
                balance             INTEGER DEFAULT 0,
                xp                  INTEGER DEFAULT 0,
                level               INTEGER DEFAULT 1,
                messages            INTEGER DEFAULT 0,
                last_work           TEXT    DEFAULT NULL,
                last_daily          TEXT    DEFAULT NULL,
                sogto_level         INTEGER DEFAULT 0,
                mansuuralt_level    INTEGER DEFAULT 0,
                prison_until        TEXT    DEFAULT NULL,
                prison_count        INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        for col in [
            "ALTER TABLE users ADD COLUMN sogto_level INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN mansuuralt_level INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN prison_until TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN prison_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN game_wins INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN game_losses INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN game_won_amount INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN game_lost_amount INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN game_wagered INTEGER DEFAULT 0",
            # Bank & happiness system
            "ALTER TABLE users ADD COLUMN bank INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN happiness INTEGER DEFAULT 10",
            "ALTER TABLE users ADD COLUMN happiness_updated TEXT DEFAULT NULL",
            # Tension / crime system
            "ALTER TABLE users ADD COLUMN tension INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN rob_cooldown TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN hack_cooldown TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN prison_reason TEXT DEFAULT NULL",
            "ALTER TABLE rpg ADD COLUMN kills INTEGER DEFAULT 0",
        ]:
            try: await db.execute(col)
            except: pass

        # ── shop ─────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop (
                item_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT,
                description  TEXT,
                price        INTEGER,
                emoji        TEXT,
                item_type    TEXT,
                effect_type  TEXT    DEFAULT NULL,
                effect_value INTEGER DEFAULT 0
            )
        """)
        for col in [
            "ALTER TABLE shop ADD COLUMN effect_type TEXT DEFAULT NULL",
            "ALTER TABLE shop ADD COLUMN effect_value INTEGER DEFAULT 0",
        ]:
            try: await db.execute(col)
            except: pass

        # ── inventory ────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER,
                guild_id INTEGER,
                item_id  INTEGER,
                quantity INTEGER DEFAULT 1
            )
        """)

        # ── family ───────────────────────────────────────────────
        # Migration: хуучин схем user_id л PK байсан → (user_id, guild_id) PK болгоно
        _fam = await (await db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='family'"
        )).fetchone()
        if _fam and "user_id     INTEGER PRIMARY KEY" in _fam[0]:
            # Шинэ хүснэгт үүсгэж, өгөгдлийг хуулаад, хуучныг устгана
            await db.execute("""
                CREATE TABLE family_new (
                    user_id           INTEGER NOT NULL,
                    guild_id          INTEGER NOT NULL DEFAULT 0,
                    spouse_id         INTEGER DEFAULT NULL,
                    parent_id         INTEGER DEFAULT NULL,
                    house_level       INTEGER DEFAULT 0,
                    children          TEXT    DEFAULT '[]',
                    last_child_prompt TEXT    DEFAULT NULL,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            await db.execute("""
                INSERT OR IGNORE INTO family_new
                    (user_id, guild_id, spouse_id, parent_id, house_level, children)
                SELECT user_id, COALESCE(guild_id, 0),
                       spouse_id, parent_id, house_level, children
                FROM family
            """)
            await db.execute("DROP TABLE family")
            await db.execute("ALTER TABLE family_new RENAME TO family")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS family (
                user_id           INTEGER NOT NULL,
                guild_id          INTEGER NOT NULL,
                spouse_id         INTEGER DEFAULT NULL,
                parent_id         INTEGER DEFAULT NULL,
                house_level       INTEGER DEFAULT 0,
                children          TEXT    DEFAULT '[]',
                last_child_prompt TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        # ── rpg ──────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rpg (
                user_id  INTEGER PRIMARY KEY,
                guild_id INTEGER,
                hp       INTEGER DEFAULT 100,
                max_hp   INTEGER DEFAULT 100,
                attack   INTEGER DEFAULT 10,
                defense  INTEGER DEFAULT 5,
                weapon   TEXT    DEFAULT 'Нударга',
                armor    TEXT    DEFAULT 'Хувцас'
            )
        """)

        # ── reaction_roles ───────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reaction_roles (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                emoji      TEXT,
                role_id    INTEGER
            )
        """)

        # ── level_roles ──────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS level_roles (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                level    INTEGER,
                role_id  INTEGER
            )
        """)

        # ── character_info ────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS character_info (
                user_id        INTEGER NOT NULL,
                guild_id       INTEGER NOT NULL,
                gender         TEXT NOT NULL,
                sexuality      TEXT NOT NULL,
                birth_date     TEXT DEFAULT NULL,
                birth_time     TEXT DEFAULT NULL,
                death_age      INTEGER NOT NULL,
                job_id         TEXT DEFAULT NULL,
                last_milestone INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        for col in [
            "ALTER TABLE character_info ADD COLUMN birth_time TEXT DEFAULT NULL",
            "ALTER TABLE character_info ADD COLUMN last_milestone INTEGER DEFAULT 0",
            "ALTER TABLE character_info ADD COLUMN last_setjob TEXT DEFAULT NULL",
            "ALTER TABLE character_info ADD COLUMN death_notified INTEGER DEFAULT 0",
        ]:
            try: await db.execute(col)
            except: pass

        # ── user_courses ──────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_courses (
                user_id      INTEGER NOT NULL,
                guild_id     INTEGER NOT NULL,
                course_name  TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id, course_name)
            )
        """)

        # ── virtual_children ──────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS virtual_children (
                child_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                parent1_id   INTEGER NOT NULL,
                parent2_id   INTEGER NOT NULL,
                name         TEXT NOT NULL,
                gender       TEXT NOT NULL,
                birth_time   TEXT NOT NULL,
                college      INTEGER DEFAULT 0,
                custodian_id INTEGER DEFAULT NULL
            )
        """)

        # ── child_calc — tracks per-parent economics ──────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS child_calc (
                child_id  INTEGER NOT NULL,
                parent_id INTEGER NOT NULL,
                last_calc TEXT NOT NULL,
                PRIMARY KEY (child_id, parent_id)
            )
        """)

        # ── child_votes — pending birth decisions ─────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS child_votes (
                vote_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                parent1_id INTEGER NOT NULL,
                parent2_id INTEGER NOT NULL,
                p1_vote    INTEGER DEFAULT NULL,
                p2_vote    INTEGER DEFAULT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # ── family extras ─────────────────────────────────────────
        for col in [
            "ALTER TABLE family ADD COLUMN last_child_prompt TEXT DEFAULT NULL",
        ]:
            try: await db.execute(col)
            except: pass

        # ══════════════════════════════════════════════════════════
        #  SHOP SEED v2 — emoji тусад нь, нэрэнд emoji байхгүй,
        #                 тэнцвэртэй үнэ
        # ══════════════════════════════════════════════════════════
        cur = await db.execute("SELECT value FROM bot_config WHERE key='shop_version'")
        row = await cur.fetchone()
        if not row or int(row[0]) < 2:
            await db.execute("DELETE FROM shop")
            await db.execute("DELETE FROM inventory")

            # (name, description, price, emoji, item_type, effect_type, effect_value)
            items: list[tuple] = []

            # ── Бөгж (ring) ──────────────────────────────────────
            items += [
                ("Хуванцар бөгж",   "Хамгийн хямд хуванцар бөгж",              500,         "💍","ring",None,0),
                ("Эрхийн бөгж",     "Энгийн амлалтын бөгж",                   2_000,        "🌸","ring",None,0),
                ("Мөнгөн бөгж",     "Цэвэр мөнгөөр хийсэн бөгж",             8_000,        "⚪","ring",None,0),
                ("Алтан бөгж",      "Шар алтаар хийсэн гоёмсог бөгж",        25_000,       "🟡","ring",None,0),
                ("Классик бөгж",    "Сонгодог алтан гэрлэлтийн бөгж",        60_000,       "💍","ring",None,0),
                ("Сваровски бөгж",  "Сваровски чулуутай тансаг бөгж",        200_000,      "💠","ring",None,0),
                ("Рубин бөгж",      "Ховор рубин чулуутай бөгж",             400_000,      "🔴","ring",None,0),
                ("Бриллиант бөгж",  "Хамгийн үнэтэй бриллиант бөгж",      1_000_000,      "💎","ring",None,0),
            ]

            # ── Архи (alcohol) ────────────────────────────────────
            items += [
                ("Хөнгөн Пиво",  "Гэрийн нам гүм пиво",                   200,  "🍺","alcohol","sogto",1),
                ("Хар Пиво",     "Хар хүчтэй пиво",                       350,  "🍺","alcohol","sogto",2),
                ("Цагаан Дарс",  "Нарийн цагаан дарс",                    500,  "🍷","alcohol","sogto",2),
                ("Улаан Дарс",   "Тансаг улаан дарс",                     600,  "🍷","alcohol","sogto",2),
                ("Шампань",      "Тэмдэглэлт шампань",                    700,  "🥂","alcohol","sogto",2),
                ("Вотка",        "Цэвэр орос вотка",                      900,  "🍸","alcohol","sogto",3),
                ("Виски",        "Scotch whiskey — 12 жилийн",          1_200,  "🥃","alcohol","sogto",3),
                ("Текила",       "Мексик текила",                       1_000,  "🍹","alcohol","sogto",3),
                ("Бренди",       "Франц бренди — тансаг",               1_500,  "🥃","alcohol","sogto",4),
                ("Прэмиум Архи", "Хамгийн үнэтэй, хамгийн хүчтэй архи",3_000,  "👑","alcohol","sogto",5),
            ]

            # ── Тамхи (cigarette) ─────────────────────────────────
            items += [
                ("Уинстон",       "Хямд, найдвартай тамхи",            250, "🚬","cigarette","mansuuralt",1),
                ("Марлборо",      "Дэлхийн алдартай Marlboro",          300, "🚬","cigarette","mansuuralt",2),
                ("Кэмэл",         "Тэмээний зуран Camel",               350, "🚬","cigarette","mansuuralt",2),
                ("Парламент",     "Эрхэм Parliament — хүндэт тамхи",   450, "🚬","cigarette","mansuuralt",3),
                ("Марлборо Голд", "Алтан Marlboro — онцгой холимог",   550, "🚬","cigarette","mansuuralt",3),
            ]

            # ── Вэйп (vape) ───────────────────────────────────────
            items += [
                ("Энгийн Вэйп",  "Анхны вэйп — энгийн хийн",       800, "💨","vape","mansuuralt",2),
                ("Мятны Вэйп",   "Цэвэр мятны амтлагч вэйп",     1_000, "💨","vape","mansuuralt",3),
                ("Жимсний Вэйп", "Солонго жимсний холимог вэйп",  1_200, "💨","vape","mansuuralt",3),
                ("Мөсний Вэйп",  "Хөлдөөсөн мөс мэт вэйп",       1_500, "💨","vape","mansuuralt",4),
                ("Прэмиум Вэйп", "Хамгийн дээд зэргийн вэйп",    2_000, "💨","vape","mansuuralt",5),
            ]

            # ── Аксессуар (accessory) ─────────────────────────────
            items += [
                ("Мөнгөн цаг",        "Мөнгөн цаг — элэгдэлгүй",            20_000, "⌚", "accessory",None,0),
                ("Алтан цаг",          "Rolex загвартай алтан цаг",          100_000, "🕰️","accessory",None,0),
                ("Мөнгөн гинж",        "Нимгэн мөнгөн гинж хүзүүвч",         12_000, "⛓️","accessory",None,0),
                ("Алтан гинж",         "Зузаан алтан гинж хүзүүвч",           60_000, "🔗","accessory",None,0),
                ("Сваровски бугуйвч",  "Сваровски чулуутай бугуйвч",          45_000, "📿","accessory",None,0),
                ("Загварлаг шил",      "Нарны загварлаг нүдний шил",           8_000, "🕶️","accessory",None,0),
            ]

            # ── Үнэт чулуу (gem) ──────────────────────────────────
            items += [
                ("Зэс",     "Хамгийн хямд металл",           1_000, "🟤","gem",None,0),
                ("Мөнгө",   "Цэвэр мөнгөн блок",             3_000, "⚪","gem",None,0),
                ("Алт",     "Алтан блок — итгэлтэй хөрөнгө",15_000, "🟡","gem",None,0),
                ("Гранат",  "Улаан гранат чулуу",            12_000, "❤️","gem",None,0),
                ("Рубин",   "Ховор улаан рубин",             50_000, "🔴","gem",None,0),
                ("Изумруд", "Ногоон изумруд чулуу",          80_000, "💚","gem",None,0),
                ("Сапфир",  "Цэнхэр сапфир — ховор чулуу", 120_000, "💙","gem",None,0),
                ("Алмаз",   "Хамгийн үнэтэй алмаз чулуу",  300_000, "💎","gem",None,0),
            ]

            # ── Хөдлөх хөрөнгө (vehicle) ─────────────────────────
            items += [
                ("Дугуй",             "Хот дотор явах хурдан дугуй",           15_000, "🚲","vehicle",None,0),
                ("Машин",             "Тав тухтай хувийн машин",              500_000, "🚗","vehicle",None,0),
                ("Спорт машин",       "Хурдны спорт машин",                 2_000_000, "🏎️","vehicle",None,0),
                ("Онгоцны тасалбар",  "Нисэх онгоцны нэг удаагийн тасалбар", 300_000, "✈️","vehicle",None,0),
                ("Завь",              "Голын завь — усан аялал",              800_000, "🛥️","vehicle",None,0),
                ("Нисдэг тэрэг",      "Нисдэг тэрэг — тансаг тээвэр",      5_000_000, "🚁","vehicle",None,0),
            ]

            # ── RPG & Бусад ───────────────────────────────────────
            items += [
                ("Илд",               "RPG дайн дахь халдлагыг +10 нэмнэ",  15_000, "⚔️","weapon",  None,0),
                ("Хуяг",              "RPG дайн дахь хамгаалалтыг +10 нэмнэ",15_000,"🛡️","armor",   None,0),
                ("Эмчилгээ",          "HP-г бүрэн сэргээнэ",                  3_000, "❤️","heal",    None,0),
                ("Азын тасалбар",     "Slot machine-д нэг удаа тоглох эрх",   2_000, "🎰","ticket",  None,0),
                ("Үрчлэлтийн бичиг", "Хүүхэд үрчлэхэд шаардлагатай бичиг", 10_000, "🍼","adoption",None,0),
            ]

            await db.executemany(
                "INSERT INTO shop (name,description,price,emoji,item_type,effect_type,effect_value)"
                " VALUES (?,?,?,?,?,?,?)",
                items
            )
            await db.execute(
                "INSERT OR REPLACE INTO bot_config (key,value) VALUES ('shop_version','2')"
            )

        # ── Fix weapon/armor effect_value (was 0, should be 10) ──────
        cur_wfix = await db.execute("SELECT value FROM bot_config WHERE key='shop_weapon_fix'")
        row_wfix = await cur_wfix.fetchone()
        if not row_wfix:
            await db.execute("UPDATE shop SET effect_value=10 WHERE item_type='weapon' AND effect_value=0")
            await db.execute("UPDATE shop SET effect_value=10 WHERE item_type='armor'  AND effect_value=0")
            await db.execute("INSERT OR REPLACE INTO bot_config (key,value) VALUES ('shop_weapon_fix','1')")

        # ── Food items (shop_food_v1) ─────────────────────────────────
        cur_food = await db.execute("SELECT value FROM bot_config WHERE key='shop_food_v1'")
        row_food = await cur_food.fetchone()
        if not row_food:
            food_items = [
                ("Ус",            "Цэвэр ус — хамгийн энгийн хоол",           100,  "\U0001f4a7", "food", "happiness", 2),
                ("Ундаа",         "Исгэлэн зөөлөн ундаа",                     200,  "\U0001f964", "food", "happiness", 3),
                ("Жимсний шүүс",  "Шинэхэн жимсний шүүс",                     350,  "\U0001f34a", "food", "happiness", 4),
                ("Фаст фуд",      "Хурдан, амттай фаст фуд",                  300,  "\U0001f354", "food", "happiness", 4),
                ("Хоол",          "Гэрийн дулаан хоол",                       500,  "\U0001f37d️", "food", "happiness", 5),
                ("Пицца",         "Итальян шинэхэн пицца",                    800,  "\U0001f355", "food", "happiness", 7),
                ("Бялуу",         "Чихэрлэг тансаг бялуу",                  1_000,  "\U0001f382", "food", "happiness", 8),
                ("Тансаг хоол",   "5 одтой ресторанны тансаг хоол",          2_500,  "\U0001f371", "food", "happiness", 12),
            ]
            await db.executemany(
                "INSERT INTO shop (name,description,price,emoji,item_type,effect_type,effect_value)"
                " VALUES (?,?,?,?,?,?,?)",
                food_items
            )
            await db.execute("INSERT OR REPLACE INTO bot_config (key,value) VALUES ('shop_food_v1','1')")

        await db.commit()



# ── Helper functions ─────────────────────────────────────────────

async def get_user(user_id: int, guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE user_id=? AND guild_id=?", (user_id, guild_id)
        )
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, guild_id) VALUES (?,?)", (user_id, guild_id)
            )
            await db.commit()
            cur = await db.execute(
                "SELECT * FROM users WHERE user_id=? AND guild_id=?", (user_id, guild_id)
            )
            row = await cur.fetchone()
        return dict(row)


async def update_balance(user_id: int, guild_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = MIN(1000000000, MAX(0, balance + ?)) WHERE user_id=? AND guild_id=?",
            (amount, user_id, guild_id)
        )
        await db.commit()


async def get_family(user_id: int, guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM family WHERE user_id=? AND guild_id=?", (user_id, guild_id)
        )
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO family (user_id, guild_id) VALUES (?,?)", (user_id, guild_id)
            )
            await db.commit()
            cur = await db.execute(
                "SELECT * FROM family WHERE user_id=? AND guild_id=?", (user_id, guild_id)
            )
            row = await cur.fetchone()
        return dict(row)


async def get_rpg(user_id: int, guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM rpg WHERE user_id=? AND guild_id=?", (user_id, guild_id)
        )
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO rpg (user_id, guild_id) VALUES (?,?)", (user_id, guild_id)
            )
            await db.commit()
            cur = await db.execute(
                "SELECT * FROM rpg WHERE user_id=? AND guild_id=?", (user_id, guild_id)
            )
            row = await cur.fetchone()
        return dict(row)


async def get_happiness(user_id: int, guild_id: int) -> int:
    """Get current happiness level with time-based decay (3 per real hour)."""
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT happiness, happiness_updated FROM users WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        )
        row = await cur.fetchone()
        if not row:
            return 10
        happiness         = row["happiness"] if row["happiness"] is not None else 10
        happiness_updated = row["happiness_updated"]
        if happiness_updated:
            last       = datetime.fromisoformat(happiness_updated)
            hours_pass = (datetime.utcnow() - last).total_seconds() / 3600
            decay      = int(hours_pass * 3)
            happiness  = max(0, happiness - decay)
        await db.execute(
            "UPDATE users SET happiness=?, happiness_updated=? WHERE user_id=? AND guild_id=?",
            (happiness, datetime.utcnow().isoformat(), user_id, guild_id)
        )
        await db.commit()
        return happiness
