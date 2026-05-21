"""
backup.py — bot.db автомат нөөцлөлт
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Хэрэглэх: python backup.py
  • bot.db-г  backups/bot_YYYY-MM-DD_HH-MM.db  нэрээр хуулна
  • 7 хоногоос хуучин backup файлуудыг автоматаар устгана
  • Windows Task Scheduler-т өдөр бүр ажиллуулна уу

Task Scheduler тохируулга:
  Action: python "C:\\Users\\Lenovo\\Documents\\discord_arman\\bot\\backup.py"
  Trigger: Өдөр бүр 03:00
"""

import shutil
import os
import glob
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── Тохируулга ────────────────────────────────────────────────────
DB_PATH      = os.getenv("DB_PATH", "bot.db")
BACKUP_DIR   = "backups"
KEEP_DAYS    = 7           # Хэдэн хоногийн backup хадгалах

# ── Файлын зам ────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_full  = os.path.join(BASE_DIR, DB_PATH)
bak_dir  = os.path.join(BASE_DIR, BACKUP_DIR)

def run_backup():
    # 1. backups/ фолдер үүсгэх
    os.makedirs(bak_dir, exist_ok=True)

    if not os.path.exists(db_full):
        print(f"[BACKUP] ❌ {DB_PATH} олдсонгүй — нөөцлөлт амжилтгүй болов.")
        return

    # 2. Шинэ backup файл үүсгэх
    ts       = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dst      = os.path.join(bak_dir, f"bot_{ts}.db")
    shutil.copy2(db_full, dst)
    size_kb  = os.path.getsize(dst) // 1024
    print(f"[BACKUP] ✅ Нөөцлөгдлөө → {dst}  ({size_kb} KB)")

    # 3. Хуучин backup-уудыг цэвэрлэх
    cutoff   = datetime.now() - timedelta(days=KEEP_DAYS)
    removed  = 0
    for f in glob.glob(os.path.join(bak_dir, "bot_*.db")):
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        if mtime < cutoff:
            os.remove(f)
            removed += 1
            print(f"[BACKUP] 🗑️  Устгагдлаа: {os.path.basename(f)}")

    if removed == 0:
        print(f"[BACKUP] ℹ️  Хуучин файл байхгүй ({KEEP_DAYS} хоногоос хуучин).")
    else:
        print(f"[BACKUP] 🗑️  {removed} хуучин backup устгагдлаа.")

    # 4. Одоогийн backup-уудыг жагсаах
    files = sorted(glob.glob(os.path.join(bak_dir, "bot_*.db")))
    print(f"[BACKUP] 📦 Нийт {len(files)} backup хадгалагдаж байна.")

if __name__ == "__main__":
    run_backup()
