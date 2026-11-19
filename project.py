import sqlite3
import time
import requests
from bs4 import BeautifulSoup

# 1. データベースの準備
DB_NAME = "google_repos.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # テストしやすいように毎回テーブルを作り直す場合（追記したい場合は DROP を消す）
    cur.execute("DROP TABLE IF EXISTS repositories")
    cur.execute("""
        CREATE TABLE repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            language TEXT,
            stars INTEGER
        )
    """)
    conn.commit()
    conn.close()

# スター数の文字列（例: "1,234", "1.2k"）を整数に変換する補助関数
def parse_stars(star_str):
    if not star_str:
        return 0
    s = star_str.strip().replace(",", "")
    if s.endswith("k"):
        return int(float(s[:-1]) * 1000)
    elif s.endswith("m"):
        return int(float(s[:-1]) * 1000000)
    try:
        return int(s)
    except ValueError:
        return 0

# 2. スクレイピング処理（全件取得）
def scrape_google_repos():
    base_url = "https://github.com/orgs/google/repositories"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    page = 1
    while True:
        print(f"Fetching page {page}...")
        params = {"page": page}
        response = requests.get(base_url, params=params, headers=headers)
        
        # サーバーへの負荷軽減のため必ず1秒待機
        time.sleep(1)
        
        if response.status_code != 200:
            print(f"アクセス失敗: ステータスコード {response.status_code}")
            break
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # リポジトリのリスト要素を取得（※GitHubのHTML構造に応じて調整が必要な箇所）
        # orgs/google/repositories の場合は li タグ内にリポジトリ情報が並ぶ
        repo_items = soup.select("li.Box-row, div[data-testid='results-list'] > div")
        
        # リポジトリが見つからなくなったら終了
        if not repo_items:
            print("全ページの取得が完了しました。")
            break
            
        count_in_page = 0
        for item in repo_items:
            # リポジトリ名の取得
            name_tag = item.select_one("a[itemprop='name codeRepository'], h3 a, h4 a")
            if not name_tag:
                continue
            repo_name = name_tag.get_text(strip=True)
            
            # 主要な言語の取得
            lang_tag = item.select_one("span[itemprop='programmingLanguage']")
            language = lang_tag.get_text(strip=True) if lang_tag else None
            
            # スター数の取得
            star_tag = item.select_one("a[href$='/stargazers']")
            stars = parse_stars(star_tag.get_text(strip=True)) if star_tag else 0
            
            # DBへ保存
            cur.execute(
                "INSERT INTO repositories (name, language, stars) VALUES (?, ?, ?)",
                (repo_name, language, stars)
            )
            count_in_page += 1
            
        conn.commit()
        print(f"  -> {count_in_page} 件保存しました。")
        
        # 1件も取れなかった場合は構造が変わっているか最終ページなので終了
        if count_in_page == 0:
            break
            
        page += 1

    conn.close()

# 3. SELECT文で表示
def show_data():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM repositories")
    total = cur.fetchone()[0]
    print(f"\n=== 保存された総件数: {total} 件 ===")
    
    # 例としてスター数が多い順に上位20件を表示（全件出す場合は LIMIT 20 を外す）
    cur.execute("SELECT id, name, language, stars FROM repositories ORDER BY stars DESC LIMIT 20")
    rows = cur.fetchall()
    for row in rows:
        print(row)
        
    conn.close()

if __name__ == "__main__":
    init_db()
    scrape_google_repos()
    show_data()
