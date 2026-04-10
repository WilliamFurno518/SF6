import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


# =========================================================
# Config
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON_DIR = os.path.join(BASE_DIR, "data", "characters")
OUTPUT_IMAGE_DIR = os.path.join(BASE_DIR, "static", "images")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# 角色列表，你可以自己继续加
CHARACTERS = [
    ("Ryu", "https://wiki.supercombo.gg/w/Street_Fighter_6/Ryu"),
    ("Ken", "https://wiki.supercombo.gg/w/Street_Fighter_6/Ken"),
    ("Chun-Li", "https://wiki.supercombo.gg/w/Street_Fighter_6/Chun-Li"),
    ("Luke", "https://wiki.supercombo.gg/w/Street_Fighter_6/Luke"),
    ("Jamie", "https://wiki.supercombo.gg/w/Street_Fighter_6/Jamie"),
    ("Guile", "https://wiki.supercombo.gg/w/Street_Fighter_6/Guile"),
    ("Kimberly", "https://wiki.supercombo.gg/w/Street_Fighter_6/Kimberly"),
    ("Juri", "https://wiki.supercombo.gg/w/Street_Fighter_6/Juri"),
    ("Dhalsim", "https://wiki.supercombo.gg/w/Street_Fighter_6/Dhalsim"),
    ("E. Honda", "https://wiki.supercombo.gg/w/Street_Fighter_6/E._Honda"),
    ("Blanka", "https://wiki.supercombo.gg/w/Street_Fighter_6/Blanka"),
    ("Dee Jay", "https://wiki.supercombo.gg/w/Street_Fighter_6/Dee_Jay"),
    ("Manon", "https://wiki.supercombo.gg/w/Street_Fighter_6/Manon"),
    ("Marisa", "https://wiki.supercombo.gg/w/Street_Fighter_6/Marisa"),
    ("JP", "https://wiki.supercombo.gg/w/Street_Fighter_6/JP"),
    ("Cammy", "https://wiki.supercombo.gg/w/Street_Fighter_6/Cammy"),
    ("Zangief", "https://wiki.supercombo.gg/w/Street_Fighter_6/Zangief"),
    ("Lily", "https://wiki.supercombo.gg/w/Street_Fighter_6/Lily"),
    ("Rashid", "https://wiki.supercombo.gg/w/Street_Fighter_6/Rashid"),
    ("A.K.I.", "https://wiki.supercombo.gg/w/Street_Fighter_6/A.K.I."),
    ("Ed", "https://wiki.supercombo.gg/w/Street_Fighter_6/Ed"),
    ("Akuma", "https://wiki.supercombo.gg/w/Street_Fighter_6/Akuma"),
    ("M. Bison", "https://wiki.supercombo.gg/w/Street_Fighter_6/M._Bison"),
    ("Terry", "https://wiki.supercombo.gg/w/Street_Fighter_6/Terry"),
    ("Mai", "https://wiki.supercombo.gg/w/Street_Fighter_6/Mai"),
]

# 你发给我的那张图对应的关键模板
DEFAULT_STATS_TEMPLATE = {
    "Basic": {
        "Life Points": ""
    },
    "Ground Movement": {
        "Forward Walk Speed": "",
        "Backward Walk Speed": "",
        "Forward Dash Speed": "",
        "Backward Dash Speed": "",
        "Forward Dash Distance": "",
        "Backward Dash Distance": "",
        "Drive Rush Min. Distance (Throw)": "",
        "Drive Rush Min. Distance (Block)": "",
        "Drive Rush Max Distance": ""
    },
    "Jumping": {
        "Jump Speed": "",
        "Jump Apex": "",
        "Forward Jump Distance": "",
        "Backward Jump Distance": ""
    },
    "Throws": {
        "Throw Range": "",
        "Throw Hurtbox": ""
    }
}

DEFAULT_PROFILE_TEMPLATE = {
    "Japanese Name": "",
    "Fighting Style": "",
    "Birthday": "",
    "Height": "",
    "Weight": "",
    "Likes": "",
    "Hates": "",
    "Occupation": "",
    "Homeland": ""
}


# =========================================================
# Helpers
# =========================================================

def ensure_dirs() -> None:
    os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)
    os.makedirs(OUTPUT_IMAGE_DIR, exist_ok=True)


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = s.replace("&", "and")
    s = s.replace(".", "")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def clean_text(text: str) -> str:
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_key(text: str) -> str:
    text = clean_text(text)
    text = text.replace("：", ":")
    text = re.sub(r"\s+", " ", text)
    return text


def fetch_html(url: str, timeout: int = 20) -> Tuple[Optional[str], str]:
    """
    返回: (html, status)
    status:
      - ok
      - blocked
      - http_xxx
      - error
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        html = resp.text or ""

        if resp.status_code != 200:
            return None, f"http_{resp.status_code}"

        lowered = html.lower()
        if (
            "access denied" in lowered
            or "anubis" in lowered
            or "oh noes" in lowered
            or "protected by" in lowered
        ):
            return None, "blocked"

        return html, "ok"
    except Exception:
        return None, "error"


def extract_intro(soup: BeautifulSoup) -> str:
    content = soup.select_one("div.mw-parser-output")
    if content:
        for child in content.find_all("p", recursive=False):
            txt = clean_text(child.get_text(" ", strip=True))
            if txt:
                return txt

    p = soup.find("p")
    if p:
        return clean_text(p.get_text(" ", strip=True))
    return ""


def absolutize_url(src: str) -> str:
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return "https://wiki.supercombo.gg" + src
    return src


def extract_main_image_url(soup: BeautifulSoup) -> str:
    selectors = [
        "table.infobox img",
        ".infobox img",
        ".portable-infobox img",
        ".mw-parser-output img",
        "img"
    ]
    for sel in selectors:
        img = soup.select_one(sel)
        if img and img.get("src"):
            return absolutize_url(img.get("src", "").strip())
    return ""


def download_image(image_url: str, slug: str) -> str:
    """
    下载成功则返回前端可用路径 /static/images/xxx.jpg
    失败返回空字符串
    """
    if not image_url:
        return ""

    try:
        resp = requests.get(image_url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return ""

        ext = ".jpg"
        lower_url = image_url.lower()
        if ".png" in lower_url:
            ext = ".png"
        elif ".webp" in lower_url:
            ext = ".webp"
        elif ".jpeg" in lower_url:
            ext = ".jpeg"

        filename = f"{slug}{ext}"
        save_path = os.path.join(OUTPUT_IMAGE_DIR, filename)

        with open(save_path, "wb") as f:
            f.write(resp.content)

        return f"/static/images/{filename}"
    except Exception:
        return ""


def table_rows_to_pairs(table) -> List[Tuple[str, str]]:
    pairs = []
    rows = table.find_all("tr")
    for row in rows:
        headers = row.find_all(["th", "td"])
        cells = [clean_text(c.get_text(" ", strip=True)) for c in headers]
        cells = [c for c in cells if c]

        if len(cells) == 2:
            left, right = cells[0], cells[1]
            pairs.append((left, right))
        elif len(cells) > 2:
            # 尝试只取第一列和最后一列
            pairs.append((cells[0], cells[-1]))

    return pairs


def is_section_header(text: str) -> bool:
    if not text:
        return False
    # 单独一列的大标题通常是 section header
    # 例如 Ground Movement / Jumping / Throws
    if len(text) <= 40 and ":" not in text and not re.search(r"\d", text):
        return True
    return False


def merge_pairs_into_sections(
    pairs: List[Tuple[str, str]],
    default_template: Dict[str, Dict[str, str]]
) -> Dict[str, Dict[str, str]]:
    """
    将表格 key-value 尝试整理为 sections
    """
    result = json.loads(json.dumps(default_template))  # 深拷贝
    current_section = "Misc"

    if current_section not in result:
        result[current_section] = {}

    for left, right in pairs:
        l = normalize_key(left)
        r = clean_text(right)

        # 有些表格可能会出现单独标题行
        if l and not r and is_section_header(l):
            current_section = l
            if current_section not in result:
                result[current_section] = {}
            continue

        # 若 left 已经是模板里的 known key，则分配到对应 section
        matched = False
        for sec_name, sec_data in result.items():
            if l in sec_data:
                result[sec_name][l] = r
                matched = True
                break

        if matched:
            continue

        # Life Points 放到 Basic
        if l == "Life Points":
            if "Basic" not in result:
                result["Basic"] = {}
            result["Basic"][l] = r
            continue

        # 常见 section 名字判断
        lower_l = l.lower()
        if "walk speed" in lower_l or "dash speed" in lower_l or "dash distance" in lower_l or "drive rush" in lower_l:
            if "Ground Movement" not in result:
                result["Ground Movement"] = {}
            result["Ground Movement"][l] = r
            continue

        if "jump" in lower_l:
            if "Jumping" not in result:
                result["Jumping"] = {}
            result["Jumping"][l] = r
            continue

        if "throw" in lower_l:
            if "Throws" not in result:
                result["Throws"] = {}
            result["Throws"][l] = r
            continue

        # 兜底到当前 section
        if current_section not in result:
            result[current_section] = {}
        result[current_section][l] = r

    return result


def extract_profile_from_infobox(soup: BeautifulSoup) -> Dict[str, str]:
    """
    尝试从 infobox 中抓角色基本资料
    """
    profile = dict(DEFAULT_PROFILE_TEMPLATE)
    candidate_tables = soup.select("table.infobox, .portable-infobox, table")

    for table in candidate_tables:
        pairs = table_rows_to_pairs(table)
        if not pairs:
            continue

        for left, right in pairs:
            left_norm = normalize_key(left)
            if left_norm in profile and not profile[left_norm]:
                profile[left_norm] = right

    return profile


def extract_stats_tables(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    """
    尝试从页面所有表格里抽出数值数据
    """
    best_pairs: List[Tuple[str, str]] = []

    for table in soup.find_all("table"):
        pairs = table_rows_to_pairs(table)
        if not pairs:
            continue

        keys_text = " | ".join([p[0].lower() for p in pairs])

        score = 0
        keywords = [
            "life points", "walk speed", "dash speed", "dash distance",
            "drive rush", "jump", "throw range", "throw hurtbox"
        ]
        for kw in keywords:
            if kw in keys_text:
                score += 1

        if score >= 2 and len(pairs) > len(best_pairs):
            best_pairs = pairs

    return merge_pairs_into_sections(best_pairs, DEFAULT_STATS_TEMPLATE)


def build_empty_card(name: str, url: str) -> Dict:
    slug = slugify(name)
    return {
        "name": name,
        "slug": slug,
        "source": url,
        "intro": "",
        "image": "",
        "image_original_url": "",
        "profile": dict(DEFAULT_PROFILE_TEMPLATE),
        "stats_sections": json.loads(json.dumps(DEFAULT_STATS_TEMPLATE)),
        "crawl_status": "template_only"
    }


def build_card_from_html(name: str, url: str, html: str) -> Dict:
    slug = slugify(name)
    soup = BeautifulSoup(html, "html.parser")

    intro = extract_intro(soup)
    image_url = extract_main_image_url(soup)
    local_image = download_image(image_url, slug)

    profile = extract_profile_from_infobox(soup)
    stats_sections = extract_stats_tables(soup)

    card = {
        "name": name,
        "slug": slug,
        "source": url,
        "intro": intro,
        "image": local_image,
        "image_original_url": image_url,
        "profile": profile,
        "stats_sections": stats_sections,
        "crawl_status": "ok"
    }

    return card


def save_card(card: Dict) -> None:
    filename = f"{card['slug']}.json"
    save_path = os.path.join(OUTPUT_JSON_DIR, filename)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)


def main() -> None:
    ensure_dirs()

    success_count = 0
    template_count = 0

    print("开始生成 SF6 角色资料卡...\n")

    for idx, (name, url) in enumerate(CHARACTERS, start=1):
        slug = slugify(name)
        print(f"[{idx}/{len(CHARACTERS)}] 处理角色: {name}")

        html, status = fetch_html(url)

        if status == "ok" and html:
            try:
                card = build_card_from_html(name, url, html)
                if not card["image"] and card["image_original_url"]:
                    print(f"  - 找到原图链接，但下载失败: {card['image_original_url']}")
                print("  - 页面读取成功")
                success_count += 1
            except Exception as e:
                print(f"  - 解析失败，改为生成模板: {e}")
                card = build_empty_card(name, url)
                card["crawl_status"] = "parse_failed_template"
                template_count += 1
        else:
            print(f"  - 页面无法读取，状态: {status}，已生成模板")
            card = build_empty_card(name, url)
            card["crawl_status"] = status
            template_count += 1

        save_card(card)
        print(f"  - 已保存: data/characters/{slug}.json\n")

        time.sleep(1.2)

    print("完成。")
    print(f"成功解析页面: {success_count}")
    print(f"生成手填模板: {template_count}")
    print(f"JSON 输出目录: {OUTPUT_JSON_DIR}")
    print(f"图片输出目录: {OUTPUT_IMAGE_DIR}")


if __name__ == "__main__":
    main()