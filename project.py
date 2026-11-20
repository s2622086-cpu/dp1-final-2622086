import sqlite3
import time
import re
import requests
from bs4 import BeautifulSoup

DB_NAME = "google_repos.db"

print("=== プログラム開始（既存データを引き継いで続行します） ===")

# 1. データベースとテーブルの準備（既存データを消さないように IF NOT EXISTS に変更）
conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS repositories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        language TEXT,
        stars INTEGER
    )
""")
conn.commit()

current_total = cur.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
print(f"現在のDB保存件数: {current_total} 件からスタートします！")

def parse_stars(star_str):
    if not star_str:
        return 0
    s = star_str.strip().lower().replace(",", "")
    try:
        if s.endswith("k"):
            return int(float(s[:-1]) * 1000)
        elif s.endswith("m"):
            return int(float(s[:-1]) * 1000000)
        return int(s)
    except ValueError:
        return 0

# 2. スクレイピング処理（連続429時は自動で10分休憩する安全設計）
base_url = "https://github.com/search"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
}

search_patterns = [
    {"s": "stars", "o": "desc"},
    {"s": "stars", "o": "asc"},
    {"s": "updated", "o": "desc"},
    {"s": "updated", "o": "asc"},
    {"s": "forks", "o": "desc"},
]

consecutive_429 = 0  # 連続して429になった回数をカウント

for pattern in search_patterns:
    page = 1
    while page <= 100:
        print(f"ソート({pattern['s']}/{pattern['o']}) Page {page} を取得中...")
        params = {
            "q": "org:google",
            "type": "repositories",
            "s": pattern["s"],
            "o": pattern["o"],
            "p": page
        }
        res = requests.get(base_url, params=params, headers=headers)

        # 課題要件: 必ず time.sleep(1) を入れる（制限緩和のため余裕を持って3秒待機）
        time.sleep(1)
        time.sleep(2)

        if res.status_code == 429:
            consecutive_429 += 1
            if consecutive_429 >= 2:
                print(f"アクセス制限(429)が連続したため、10分間（600秒）自動休憩に入ります...（現在 {time.strftime('%H:%M:%S')}）")
                time.sleep(600)
                consecutive_429 = 0
            else:
                print("アクセス制限(429)のため60秒待機してリトライします...")
                time.sleep(60)
            continue

        # 成功したら連続429カウントをリセット
        consecutive_429 = 0

        if res.status_code != 200:
            print(f"取得終了 (Status: {res.status_code})")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        repo_links = [
            a for a in soup.select('a[href^="/google/"]')
            if a.get("href", "").count("/") == 2
            and not a.get("href", "").startswith("/google/search")
        ]

        if not repo_links:
            print("このソート順の最終ページに到達しました。")
            break

        new_count = 0
        for a in repo_links:
            full_name = a.get("href").strip("/")
            repo_name = full_name.split("/")[-1]

            card = a
            for _ in range(5):
                if card.parent:
                    card = card.parent

            # スター数の抽出
            star_tag = card.select_one(f'a[href="/{full_name}/stargazers"]')
            if star_tag:
                stars = parse_stars(star_tag.get_text(strip=True))
            else:
                texts = [t.strip() for t in card.stripped_strings]
                stars = 0
                for t in texts:
                    if re.fullmatch(r"[\d,]+(\.\d+)?[km]?", t.lower()):
                        stars = parse_stars(t)
                        break

            # 主要な言語の抽出
            lang_tag = card.select_one('span[aria-label*="language"], span.repo-language-color + span')
            if lang_tag:
                language = lang_tag.get_text(strip=True)
            else:
                language = None
                texts = [t.strip() for t in card.stripped_strings]
                for i, t in enumerate(texts):
                    if t == "·" and i > 0:
                        candidate = texts[i - 1]
                        if not re.fullmatch(r"[\d,]+(\.\d+)?[km]?", candidate.lower()) and candidate not in ["Updated", "Public"]:
                            language = candidate
                            break

            cur.execute(
                "INSERT OR IGNORE INTO repositories (name, language, stars) VALUES (?, ?, ?)",
                (repo_name, language, stars)
            )
            if cur.rowcount > 0:
                new_count += 1

        conn.commit()
        total_now = cur.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
        print(f"  -> 新規 {new_count} 件保存（現在のDB合計: {total_now} 件）")

        if new_count == 0 and page > 5:
            print("新規データがなくなったため次のパターンへ移動します。")
            break

        page += 1

# 3. 保存したデータをSELECT文で表示
cur.execute("SELECT id, name, language, stars FROM repositories")
rows = cur.fetchall()

print(f"\n=== 保存データ一覧（全 {len(rows)} 件） ===")
for row in rows:
    print(f"ID: {row[0]} | リポジトリ名: {row[1]} | 言語: {row[2]} | スター数: {row[3]}")

conn.close()
