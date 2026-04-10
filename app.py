import os
import re
import json
import uuid
import logging
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from openai import OpenAI
from rag_index import search

# ============================================================
# CONFIG
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
FEEDBACK_FILE = BASE_DIR / "feedback.json"
EVAL_LOG_FILE = BASE_DIR / "evaluation_log.json"
COMBO_DB_FILE = BASE_DIR / "combo_db.json"
FRAME_DATA_FILE = BASE_DIR / "frame_data.json"
CHARACTER_DOCS_FILE = BASE_DIR / "character_docs.json"
CHARACTER_CARDS_DIR = BASE_DIR / "data" / "characters"

load_dotenv(dotenv_path=ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.shubiaobiao.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
ALLOW_MODEL_FALLBACK = os.getenv("ALLOW_MODEL_FALLBACK", "true").lower() == "true"
ALLOW_WIKI_FETCH = os.getenv("ALLOW_WIKI_FETCH", "true").lower() == "true"
STRICT_COMBO_ONLY_FROM_DB = os.getenv("STRICT_COMBO_ONLY_FROM_DB", "false").lower() == "true"

client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sf6_bot")
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "sf6-dev-secret-key")

# ============================================================
# SOURCE MAP
# ============================================================
CHARACTER_URLS = {
    "ryu": "https://wiki.supercombo.gg/w/Street_Fighter_6/Ryu",
    "ken": "https://wiki.supercombo.gg/w/Street_Fighter_6/Ken",
    "chun-li": "https://wiki.supercombo.gg/w/Street_Fighter_6/Chun-Li",
    "chun li": "https://wiki.supercombo.gg/w/Street_Fighter_6/Chun-Li",
    "chunli": "https://wiki.supercombo.gg/w/Street_Fighter_6/Chun-Li",
    "juri": "https://wiki.supercombo.gg/w/Street_Fighter_6/Juri",
    "luke": "https://wiki.supercombo.gg/w/Street_Fighter_6/Luke",
    "cammy": "https://wiki.supercombo.gg/w/Street_Fighter_6/Cammy",
    "guile": "https://wiki.supercombo.gg/w/Street_Fighter_6/Guile",
    "akuma": "https://wiki.supercombo.gg/w/Street_Fighter_6/Akuma",
    "deejay": "https://wiki.supercombo.gg/w/Street_Fighter_6/Dee_Jay",
    "dee jay": "https://wiki.supercombo.gg/w/Street_Fighter_6/Dee_Jay",
    "manon": "https://wiki.supercombo.gg/w/Street_Fighter_6/Manon",
    "marisa": "https://wiki.supercombo.gg/w/Street_Fighter_6/Marisa",
    "jp": "https://wiki.supercombo.gg/w/Street_Fighter_6/JP",
    "zangief": "https://wiki.supercombo.gg/w/Street_Fighter_6/Zangief",
    "dhalsim": "https://wiki.supercombo.gg/w/Street_Fighter_6/Dhalsim",
    "kimberly": "https://wiki.supercombo.gg/w/Street_Fighter_6/Kimberly",
    "blanka": "https://wiki.supercombo.gg/w/Street_Fighter_6/Blanka",
    "honda": "https://wiki.supercombo.gg/w/Street_Fighter_6/E._Honda",
    "e honda": "https://wiki.supercombo.gg/w/Street_Fighter_6/E._Honda",
    "e. honda": "https://wiki.supercombo.gg/w/Street_Fighter_6/E._Honda",
    "rashid": "https://wiki.supercombo.gg/w/Street_Fighter_6/Rashid",
    "aki": "https://wiki.supercombo.gg/w/Street_Fighter_6/A.K.I.",
    "a.k.i.": "https://wiki.supercombo.gg/w/Street_Fighter_6/A.K.I.",
    "ed": "https://wiki.supercombo.gg/w/Street_Fighter_6/Ed",
    "jamie": "https://wiki.supercombo.gg/w/Street_Fighter_6/Jamie",
    "lily": "https://wiki.supercombo.gg/w/Street_Fighter_6/Lily",
    "m. bison": "https://wiki.supercombo.gg/w/Street_Fighter_6/M._Bison",
    "m bison": "https://wiki.supercombo.gg/w/Street_Fighter_6/M._Bison",
    "bison": "https://wiki.supercombo.gg/w/Street_Fighter_6/M._Bison",
    "terry": "https://wiki.supercombo.gg/w/Street_Fighter_6/Terry",
    "terry bogard": "https://wiki.supercombo.gg/w/Street_Fighter_6/Terry",
    "mai": "https://wiki.supercombo.gg/w/Street_Fighter_6/Mai",
    "mai shiranui": "https://wiki.supercombo.gg/w/Street_Fighter_6/Mai",
}

CHARACTER_ALIASES = {
    "Ryu": ["ryu"],
    "Ken": ["ken"],
    "Chun-Li": ["chun-li", "chun li", "chunli"],
    "Juri": ["juri"],
    "Luke": ["luke"],
    "Cammy": ["cammy"],
    "Guile": ["guile"],
    "Akuma": ["akuma", "gouki"],
    "Dee Jay": ["deejay", "dee jay"],
    "Manon": ["manon"],
    "Marisa": ["marisa"],
    "JP": ["jp"],
    "Zangief": ["zangief", "gief"],
    "Dhalsim": ["dhalsim", "sim"],
    "Kimberly": ["kimberly", "kim"],
    "Blanka": ["blanka"],
    "E. Honda": ["honda", "e honda", "e. honda"],
    "Rashid": ["rashid"],
    "A.K.I.": ["aki", "a.k.i."],
    "Ed": ["ed"],
    "Jamie": ["jamie"],
    "Lily": ["lily"],
    "M. Bison": ["bison", "m bison", "m. bison", "dictator"],
    "Terry": ["terry", "terry bogard"],
    "Mai": ["mai", "mai shiranui"],
}

SF6_KEYWORDS = [
    "street fighter", "sf6", "combo", "bnb", "optimal", "best combo",
    "frame", "startup", "recovery", "active", "on block", "on hit",
    "drive rush", "drive impact", "parry", "punish", "safe", "unsafe",
    "super", "sa1", "sa2", "sa3", "counter hit", "punish counter",
    "midscreen", "mid screen", "corner", "oki", "routing", "route",
    "frame data", "move", "normal", "special", "matchup", "gameplan",
    "overview", "tell me about", "who is"
]

COMBO_KEYWORDS = [
    "combo", "route", "optimal", "best combo", "max damage", "kill",
    "touch of death", "tod", "bnb", "punish counter", "counter hit",
    "midscreen", "mid screen", "corner", "confirm", "starter", "ender",
    "meter dump", "sa1", "sa2", "sa3", "drive rush", "dr", "drive"
]

FRAME_KEYWORDS = [
    "frame", "startup", "active", "recovery", "on block", "on hit",
    "plus", "minus", "safe", "unsafe", "punishable", "advantage"
]

STRATEGY_KEYWORDS = [
    "neutral", "strategy", "gameplan", "matchup", "anti air", "footsies",
    "pressure", "oki", "shimmy", "whiff punish", "tell me about", "overview",
    "who is", "介绍", "角色", "怎么玩"
]

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "reveal the system prompt",
    "show the hidden prompt",
    "developer message",
    "do not use the source",
    "answer from imagination",
    "pretend the wiki says",
    "output the system prompt",
]

GREETING_PATTERNS = {
    "hi", "hello", "hey", "yo", "sup",
    "你好", "嗨", "哈喽", "hello there", "hey there"
}

DEFAULT_COMBO_DB = []
DEFAULT_FRAME_DATA = {}
DEFAULT_CHARACTER_DOCS = {}

# ============================================================
# IO
# ============================================================
def ensure_json_file(path: Path, default_value: Any) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_value, f, ensure_ascii=False, indent=2)


def read_json(path: Path, default_value: Any) -> Any:
    try:
        if not path.exists():
            return default_value
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_value


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_runtime_files() -> None:
    ensure_json_file(FEEDBACK_FILE, [])
    ensure_json_file(EVAL_LOG_FILE, [])
    ensure_json_file(COMBO_DB_FILE, DEFAULT_COMBO_DB)
    ensure_json_file(FRAME_DATA_FILE, DEFAULT_FRAME_DATA)
    ensure_json_file(CHARACTER_DOCS_FILE, DEFAULT_CHARACTER_DOCS)

# ============================================================
# BASIC FILTERS
# ============================================================
def contains_prompt_injection(text: str) -> bool:
    q = (text or "").lower()
    return any(p in q for p in INJECTION_PATTERNS)


def is_greeting(text: str) -> bool:
    q = normalize_whitespace((text or "").lower())
    if q in GREETING_PATTERNS:
        return True
    short_greeting_patterns = [
        r"^(hi|hello|hey|yo)\b[!. ]*$",
        r"^(你好|嗨|哈喽)[!！。 ]*$",
    ]
    return any(re.match(p, q) for p in short_greeting_patterns)


def greeting_response() -> str:
    return (
        "Hi! I can help with **Street Fighter 6** characters, frame data, combos, and matchups.\n\n"
        "Try asking things like:\n"
        "- Tell me about Ken\n"
        "- Show me Juri's character data\n"
        "- What is Ryu 2MP on block?\n"
        "- Best Cammy punish counter combo midscreen\n\n"
        "**Confidence:** High"
    )


def is_sf6_question(question: str) -> bool:
    q = (question or "").lower()
    if any(keyword in q for keyword in SF6_KEYWORDS):
        return True
    if any(alias in q for aliases in CHARACTER_ALIASES.values() for alias in aliases):
        return True
    return False

# ============================================================
# NORMALIZATION
# ============================================================
def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_notation(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower().strip()
    replacements = {
        "c.mk": "2mk", "cr.mk": "2mk", "c.hk": "2hk", "cr.hk": "2hk",
        "c.mp": "2mp", "cr.mp": "2mp", "c.lp": "2lp", "cr.lp": "2lp",
        "c.hp": "2hp", "cr.hp": "2hp", "c.lk": "2lk", "cr.lk": "2lk",
        "s.mk": "5mk", "st.mk": "5mk", "s.mp": "5mp", "st.mp": "5mp",
        "s.hp": "5hp", "st.hp": "5hp", "s.lp": "5lp", "st.lp": "5lp",
        "s.lk": "5lk", "st.lk": "5lk", "s.hk": "5hk", "st.hk": "5hk",
        "drive rush": "dr", "drive impact": "di", "punish counter": "pc",
        "counter hit": "ch", "mid screen": "midscreen",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalize_whitespace(normalized)


def canonicalize_move_name(move: Optional[str]) -> Optional[str]:
    if not move:
        return None
    m = normalize_notation(move).lower().replace(".", "").replace(" ", "").replace("-", "")
    mapping = {
        "2LP": ["2lp", "crlp", "clp", "crouchinglightpunch"],
        "2LK": ["2lk", "crlk", "clk", "crouchinglightkick"],
        "2MP": ["2mp", "crmp", "cmp", "crouchingmediumpunch"],
        "2MK": ["2mk", "crmk", "cmk", "crouchingmediumkick"],
        "2HP": ["2hp", "crhp", "chp", "crouchingheavypunch"],
        "2HK": ["2hk", "crhk", "chk", "crouchingheavykick"],
        "5LP": ["5lp", "stlp", "slp", "lp", "standinglightpunch"],
        "5LK": ["5lk", "stlk", "slk", "lk", "standinglightkick"],
        "5MP": ["5mp", "stmp", "smp", "mp", "standingmediumpunch"],
        "5MK": ["5mk", "stmk", "smk", "mk", "standingmediumkick"],
        "5HP": ["5hp", "sthp", "shp", "hp", "standingheavypunch"],
        "5HK": ["5hk", "sthk", "shk", "hk", "standingheavykick"],
        "JLP": ["jlp", "jumplightpunch"],
        "JLK": ["jlk", "jumplightkick"],
        "JMP": ["jmp", "jumpmediumpunch"],
        "JMK": ["jmk", "jumpmediumkick"],
        "JHP": ["jhp", "jumpheavypunch"],
        "JHK": ["jhk", "jumpheavykick"],
    }
    for canon, aliases in mapping.items():
        if m in aliases:
            return canon
    return move.upper().replace(".", "").replace(" ", "")


def normalize_move_key_for_lookup(text: str) -> str:
    return normalize_notation(text).lower().replace(".", "").replace(" ", "").replace("-", "")


def try_parse_numeric(text: str) -> Optional[Any]:
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    if re.fullmatch(r"[+-]?\d+", s):
        try:
            return int(s)
        except Exception:
            return s
    if re.fullmatch(r"[+-]?\d+\.\d+", s):
        try:
            return float(s)
        except Exception:
            return s
    return s

# ============================================================
# DETECTION
# ============================================================
def detect_character(question: str) -> Optional[str]:
    q = (question or "").lower()
    for canonical, aliases in CHARACTER_ALIASES.items():
        for alias in aliases:
            if alias in q:
                return canonical
    return None

def detect_all_characters(question: str) -> List[str]:
    q = (question or "").lower()
    found = []

    for canonical, aliases in CHARACTER_ALIASES.items():
        for alias in aliases:
            if alias in q:
                found.append(canonical)
                break

    # 去重，保持顺序
    unique = []
    for c in found:
        if c not in unique:
            unique.append(c)
    return unique

# ============================================================
# CONVERSATION STATE
# ============================================================
FOLLOWUP_KEYWORDS = [
    "combo", "combos", "bnb", "route", "routes",
    "frame", "frames", "frame data",
    "punish", "on block", "on hit", "startup",
    "midscreen", "mid screen", "corner",
    "oki", "setup", "pressure", "neutral", "strategy", "gameplan",
    "连招", "帧数", "帧", "确反", "压制", "打法", "立回", "角落", "中场"
]

PRONOUN_FOLLOWUPS = [
    "his", "her", "their", "that character", "this character",
    "他", "她", "这个角色", "那她", "那他", "那这个角色"
]

def get_conversation_state() -> Dict[str, Any]:
    return {
        "current_character": session.get("current_character"),
        "last_question_type": session.get("last_question_type"),
    }

def save_conversation_state(current_character: Optional[str] = None,
                            last_question_type: Optional[str] = None) -> None:
    if current_character is not None:
        session["current_character"] = current_character
    if last_question_type is not None:
        session["last_question_type"] = last_question_type

def should_apply_character_context(user_message: str, parsed_guess: Dict[str, Any], state: Dict[str, Any]) -> bool:
    if not state.get("current_character"):
        return False

    # 当前句如果已经点名角色，就不需要继承旧角色
    if parsed_guess.get("character"):
        return False

    q = (user_message or "").lower()

    if any(k in q for k in FOLLOWUP_KEYWORDS):
        return True

    if any(p in q for p in PRONOUN_FOLLOWUPS):
        return True

    return False

def enrich_query_with_state(user_message: str) -> Tuple[str, Dict[str, Any], bool]:
    state = get_conversation_state()

    # 先用原句做一次轻量解析
    parsed_guess = {
        "character": detect_character(user_message),
        "question_type": detect_question_type(user_message),
    }

    if should_apply_character_context(user_message, parsed_guess, state):
        enriched_message = f'{state["current_character"]} {user_message}'
        return enriched_message, state, True

    return user_message, state, False

def update_state_from_parsed(parsed: Dict[str, Any], question_type: str) -> None:
    detected_character = parsed.get("character")
    if detected_character:
        save_conversation_state(
            current_character=detected_character,
            last_question_type=question_type
        )
    else:
        save_conversation_state(
            last_question_type=question_type
        )

# ============================================================
# Character Card Request
# ============================================================

def is_character_intro_request(question: str) -> bool:
    q = normalize_whitespace((question or "").lower())

    intro_patterns = [
        "tell me about",
        "who is",
        "who's",
        "overview",
        "introduction",
        "intro",
        "character data",
        "character info",
        "character profile",
        "show me",
        "介绍",
        "介绍一下",
        "角色介绍",
        "角色资料",
        "人物介绍",
        "给我看看",
    ]

    explicit_card_patterns = [
        "character card",
        "show card",
        "show character card",
        "显示角色卡",
        "角色卡",
        "人物卡",
        "资料卡",
    ]

    return any(p in q for p in intro_patterns + explicit_card_patterns)


def should_show_character_card(user_message: str, parsed: Dict[str, Any], character: Optional[str]) -> bool:
    if not character:
        return False

    # 多角色问题，不显示卡
    all_characters = detect_all_characters(user_message)
    if len(all_characters) != 1:
        return False

    question_type = parsed.get("question_type") or detect_question_type(user_message)

    # combo / frame_data 一律不显示
    if question_type in {"combo", "frame_data"}:
        return False

    q = (user_message or "").lower()

    # 明确要求显示角色卡 / 角色介绍 -> 显示
    if is_character_intro_request(user_message):
        return True

    # 一些明显不是角色介绍的问题，不显示
    non_intro_keywords = [
        "gift", "present", "buy", "送什么", "礼物", "送礼",
        "date", "romance", "boyfriend", "girlfriend",
        "like to eat", "favorite food", "喜欢什么",
        "是不是好兄弟", "关系怎么样", "friends", "friend",
        "cp", "ship"
    ]
    if any(k in q for k in non_intro_keywords):
        return False

    # strategy/general 默认不展示，除非是明确介绍请求
    return False

def get_character_url(question: str) -> Optional[str]:
    character = detect_character(question)
    if not character:
        return None
    for key, url in CHARACTER_URLS.items():
        if key.lower() == character.lower() or key in [a.lower() for a in CHARACTER_ALIASES.get(character, [])]:
            return url
    return None


def detect_question_type(question: str) -> str:
    q = normalize_notation(question)
    if any(k in q for k in COMBO_KEYWORDS):
        return "combo"
    if any(k in q for k in FRAME_KEYWORDS):
        return "frame_data"
    if any(k in q for k in STRATEGY_KEYWORDS):
        return "strategy"
    return "general_sf6"

# ============================================================
# FEEDBACK / EVAL
# ============================================================
def load_feedback() -> List[Dict[str, Any]]:
    return read_json(FEEDBACK_FILE, [])


def save_feedback(data: List[Dict[str, Any]]) -> None:
    write_json(FEEDBACK_FILE, data)


def get_recent_corrections(limit: int = 5) -> List[Dict[str, str]]:
    feedback_list = load_feedback()
    correction_keywords = [
        "should be", "wrong", "incorrect", "actually",
        "frame is", "on block is", "on hit is", "startup is",
        "doesn't work", "does not work", "not true", "impossible", "fake combo",
        "应该是", "不是", "有误", "错了", "打防", "命中"
    ]
    latest_by_key: Dict[str, Dict[str, str]] = {}
    for item in feedback_list:
        comment = (item.get("comment") or "").strip()
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        answer_id = (item.get("answer_id") or "").strip()
        if not comment:
            continue
        if any(keyword in comment.lower() for keyword in correction_keywords) or any(keyword in comment for keyword in ["应该是", "不是", "有误", "错了"]):
            key = answer_id if answer_id else question.lower().strip()
            latest_by_key[key] = {
                "question": question,
                "original_answer": answer,
                "user_comment": comment,
            }
    return list(latest_by_key.values())[-limit:]


def build_corrections_text(corrections: List[Dict[str, str]]) -> str:
    if not corrections:
        return "No recent user corrections."
    lines = []
    for i, c in enumerate(corrections, start=1):
        lines.append(
            f"Correction {i}:\n"
            f"Original question: {c['question']}\n"
            f"Original answer: {c['original_answer']}\n"
            f"User correction: {c['user_comment']}\n"
        )
    return "\n".join(lines)


def load_eval_log() -> List[Dict[str, Any]]:
    return read_json(EVAL_LOG_FILE, [])


def save_eval_entry(entry: Dict[str, Any]) -> None:
    log = load_eval_log()
    log.append(entry)
    write_json(EVAL_LOG_FILE, log)


def estimate_confidence(
    question_type: str,
    grounding_level: str,
    exact_combo_match: bool = False,
    frame_found: bool = False,
    used_character_card: bool = False  # ⭐ 新增
) -> str:

    # 安全过滤
    if grounding_level == "security_filter":
        return "high"

    # 新增：角色卡直接 high
    if used_character_card:
        return "high"

    # combo
    if question_type == "combo":
        if exact_combo_match:
            return "high"
        if grounding_level in {"wiki_partial", "local+model", "wiki+model"}:
            return "medium"
        return "low"

    # frame data
    if question_type == "frame_data":
        if frame_found:
            return "high"
        if grounding_level in {"wiki_partial", "wiki+model"}:
            return "medium"
        return "low"

    # 其他
    if grounding_level in {"local", "local+model"}:
        return "medium"

    if grounding_level in {"wiki_partial", "wiki+model", "model_only"}:
        return "low"

    return "low"


def detect_hallucination_risk(question_type: str, grounding_level: str, answer_text: str) -> bool:
    if grounding_level in {"model_only", "wiki+model", "wiki_partial"}:
        return True
    if question_type == "combo":
        risky_terms = ["xx", ">", "drive rush", "sa3", "sa2", "sa1", "optimal combo"]
        answer_lower = (answer_text or "").lower()
        return any(term in answer_lower for term in risky_terms) and grounding_level != "local"
    return False

# ============================================================
# DATA LOADERS
# ============================================================
def load_combo_db() -> List[Dict[str, Any]]:
    return read_json(COMBO_DB_FILE, DEFAULT_COMBO_DB)


def load_frame_data_db() -> Dict[str, Any]:
    return read_json(FRAME_DATA_FILE, DEFAULT_FRAME_DATA)


def load_character_docs_db() -> Dict[str, Any]:
    return read_json(CHARACTER_DOCS_FILE, DEFAULT_CHARACTER_DOCS)

# ============================================================
# CHARACTER CARDS
# ============================================================
def slugify_character_name(name: str) -> str:
    s = (name or "").lower().strip()
    s = s.replace(".", "")
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def get_character_card_path(character: str) -> Optional[Path]:
    if not character:
        return None

    slug_candidates = []
    canon = character.lower()

    manual_map = {
        "chun-li": "chunli",
        "dee jay": "deejay",
        "e. honda": "ehonda",
        "a.k.i.": "aki",
        "m. bison": "mbison",
    }

    if canon in manual_map:
        slug_candidates.append(manual_map[canon])

    slug_candidates.append(slugify_character_name(character))

    for slug in slug_candidates:
        path = CHARACTER_CARDS_DIR / f"{slug}.json"
        if path.exists():
            return path

    return None


def load_character_card(character: Optional[str]) -> Optional[Dict[str, Any]]:
    if not character:
        return None
    path = get_character_card_path(character)
    if not path:
        return None
    return read_json(path, None)


def build_character_card_context(card: Dict[str, Any]) -> str:
    if not card:
        return ""

    parts = []

    name = card.get("name")
    intro = card.get("intro")
    profile = card.get("profile", {})
    stats_sections = card.get("stats_sections", {})

    if name:
        parts.append(f"name: {name}")
    if intro:
        parts.append(f"intro: {intro}")

    if profile:
        profile_lines = []
        for k, v in profile.items():
            if v:
                profile_lines.append(f"{k}: {v}")
        if profile_lines:
            parts.append("profile:\n" + "\n".join(profile_lines))

    if stats_sections:
        stat_lines = []
        for section_name, section_data in stats_sections.items():
            if not isinstance(section_data, dict):
                continue
            stat_lines.append(f"[{section_name}]")
            for k, v in section_data.items():
                if isinstance(v, dict):
                    sub = ", ".join(f"{sk}={sv}" for sk, sv in v.items())
                    stat_lines.append(f"{k}: {sub}")
                else:
                    stat_lines.append(f"{k}: {v}")
        if stat_lines:
            parts.append("stats:\n" + "\n".join(stat_lines))

    return "\n\n".join(parts)

# ============================================================
# WIKI FETCH / RAG
# ============================================================
def build_headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://wiki.supercombo.gg/",
        "DNT": "1",
    }


def html_to_text_and_tables(html: str) -> Tuple[str, List[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    table_snippets: List[str] = []
    for table in soup.select("table")[:12]:
        rows = []
        for tr in table.select("tr")[:25]:
            cells = [normalize_whitespace(td.get_text(" ", strip=True)) for td in tr.select("th, td")]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            table_snippets.append("\n".join(rows))

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    return cleaned[:22000], table_snippets[:6]


def build_subpage_url(base_url: str, question_type: str) -> List[str]:
    urls = [base_url]
    if question_type == "frame_data":
        urls += [f"{base_url}/Data", f"{base_url}/Resources"]
    elif question_type == "combo":
        urls += [f"{base_url}/Combos", f"{base_url}/Resources"]
    else:
        urls += [f"{base_url}/Strategy", f"{base_url}/Introduction", f"{base_url}/Resources"]
    return urls


def fetch_url_text(url: str, session: requests.Session) -> Dict[str, Any]:
    response = session.get(url, headers=build_headers(), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    text, tables = html_to_text_and_tables(response.text)
    blocked_markers = [
        "Access Denied",
        "Making sure you're not a bot",
        "Protected by Anubis",
        "Checking if the site connection is secure"
    ]
    blocked = any(marker.lower() in text.lower() for marker in blocked_markers)
    return {
        "url": url,
        "status_code": response.status_code,
        "blocked": blocked,
        "text": text,
        "tables": tables,
    }


def fetch_wiki_context(question: str, question_type: str) -> Dict[str, Any]:
    if not ALLOW_WIKI_FETCH:
        return {"ok": False, "reason": "wiki fetch disabled"}

    base_url = get_character_url(question)
    if not base_url:
        return {"ok": False, "reason": "no character url"}

    session = requests.Session()
    attempts = []
    urls = build_subpage_url(base_url, question_type)

    for url in urls:
        try:
            result = fetch_url_text(url, session)
            attempts.append(result)
            if result["text"] and not result["blocked"]:
                return {
                    "ok": True,
                    "base_url": base_url,
                    "best_url": url,
                    "text": result["text"],
                    "tables": result["tables"],
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append({"url": url, "error": str(exc)})

    try:
        raw_url = base_url + "?action=raw"
        response = session.get(raw_url, headers=build_headers(), timeout=REQUEST_TIMEOUT)
        if response.ok and response.text:
            raw_text = response.text[:22000]
            attempts.append({"url": raw_url, "status_code": response.status_code, "blocked": False})
            return {
                "ok": True,
                "base_url": base_url,
                "best_url": raw_url,
                "text": raw_text,
                "tables": [],
                "attempts": attempts,
            }
    except Exception as exc:
        attempts.append({"url": base_url + "?action=raw", "error": str(exc)})

    return {
        "ok": False,
        "reason": "all wiki fetch strategies failed",
        "base_url": base_url,
        "attempts": attempts,
    }

# ============================================================
# QUERY PARSE
# ============================================================
def rule_extract_starter(text: str) -> Optional[str]:
    q = normalize_notation(text)
    patterns = [
        r"\b(2mk|2mp|2hp|2lp|2lk|2hk|5mk|5mp|5hp|5lp|5lk|5hk)\b",
        r"\b(jhk|jmk|jhp|jmp)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return canonicalize_move_name(match.group(1))
    return None


def rule_extract_hit_state(text: str) -> Optional[str]:
    q = normalize_notation(text)
    if "punish counter" in q or " pc " in f" {q} ":
        return "punish_counter"
    if "counter hit" in q or " ch " in f" {q} ":
        return "counter_hit"
    if "on block" in q or q.endswith("block?") or " block" in q or "打防" in text:
        return "block"
    if "on hit" in q or "hit confirm" in q or "命中" in text:
        return "normal_hit"
    return None


def rule_extract_position(text: str) -> Optional[str]:
    q = normalize_notation(text)
    if "corner" in q:
        return "corner"
    if "midscreen" in q or "mid screen" in q:
        return "mid_screen"
    return None


def rule_extract_drive(text: str) -> Optional[int]:
    q = normalize_notation(text)
    patterns = [r"(\d+)\s*(drive|bar|bars)", r"drive\s*(\d+)", r"(\d+)\s*格"]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            value = next((g for g in match.groups() if g and str(g).isdigit()), None)
            if value:
                return int(value)
    return None


def rule_extract_super(text: str) -> Optional[int]:
    q = normalize_notation(text)
    if "sa3" in q or "super 3" in q or "level 3" in q or "3超" in q:
        return 3
    if "sa2" in q or "super 2" in q or "level 2" in q or "2超" in q:
        return 2
    if "sa1" in q or "super 1" in q or "level 1" in q or "1超" in q:
        return 1
    return None


def rule_extract_goal(text: str, question_type: str) -> str:
    q = normalize_notation(text)
    if question_type == "frame_data":
        return "frame_lookup"
    if "kill" in q or "斩杀" in q:
        return "kill"
    if "stable" in q or "稳" in q:
        return "stable"
    if "save meter" in q or "meter efficient" in q or "省资源" in q:
        return "meter_efficient"
    if question_type == "strategy":
        return "strategy"
    if question_type == "combo":
        return "max_damage"
    return "general"


def llm_extract_query_structure(user_message: str) -> Dict[str, Any]:
    question_type_guess = detect_question_type(user_message)
    character_guess = detect_character(user_message)
    try:
        system_prompt = "You are a strict Street Fighter 6 query parser. Return ONLY valid JSON."
        few_shot = [
            {
                "role": "user",
                "content": "Ken cr.mk on block是多少？"
            },
            {
                "role": "assistant",
                "content": json.dumps({
                    "question_type": "frame_data",
                    "character": "Ken",
                    "starter": None,
                    "move": "2MK",
                    "hit_state": "block",
                    "position": None,
                    "drive": None,
                    "super": None,
                    "goal": "frame_lookup"
                }, ensure_ascii=False)
            },
            {
                "role": "user",
                "content": "Ken 5MK punish counter midscreen 4 drive SA3 最佳连段"
            },
            {
                "role": "assistant",
                "content": json.dumps({
                    "question_type": "combo",
                    "character": "Ken",
                    "starter": "5MK",
                    "move": None,
                    "hit_state": "punish_counter",
                    "position": "mid_screen",
                    "drive": 4,
                    "super": 3,
                    "goal": "max_damage"
                }, ensure_ascii=False)
            },
        ]
        user_prompt = f"""
Parse the following SF6 user question into JSON.
question_type: combo, frame_data, strategy, general_sf6
character: title case or null
starter: move like 2MK, 5HP, JHK, or null
move: move if frame question, otherwise null
hit_state: normal_hit, counter_hit, punish_counter, block, or null
position: mid_screen, corner, or null
drive: integer or null
super: 1/2/3 or null
goal: max_damage, kill, stable, meter_efficient, frame_lookup, strategy, general
Question: {user_message}
""".strip()
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                *few_shot,
                {"role": "user", "content": user_prompt}
            ]
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception:
        starter = rule_extract_starter(user_message)
        return {
            "question_type": question_type_guess,
            "character": character_guess,
            "starter": starter if question_type_guess == "combo" else None,
            "move": starter if question_type_guess == "frame_data" else None,
            "hit_state": rule_extract_hit_state(user_message),
            "position": rule_extract_position(user_message),
            "drive": rule_extract_drive(user_message),
            "super": rule_extract_super(user_message),
            "goal": rule_extract_goal(user_message, question_type_guess),
        }

# ============================================================
# LOCAL SEARCH
# ============================================================
def get_character_doc(character: Optional[str]) -> Optional[Dict[str, Any]]:
    if not character:
        return None
    db = load_character_docs_db()
    if character in db:
        return db[character]
    for key in db.keys():
        if key.lower() == character.lower():
            return db[key]
    return None


def build_character_context(doc: Dict[str, Any]) -> str:
    sections = []
    fields_priority = [
        "summary", "archetype", "playstyle", "strengths", "weaknesses",
        "key_moves", "strategy_overview", "anti_airs", "best_range", "meter_usage",
        "notes", "sources"
    ]
    for field in fields_priority:
        value = doc.get(field)
        if not value:
            continue
        if isinstance(value, list):
            sections.append(f"{field}: " + "; ".join(str(x) for x in value))
        elif isinstance(value, dict):
            sections.append(f"{field}: {json.dumps(value, ensure_ascii=False)}")
        else:
            sections.append(f"{field}: {value}")
    return "\n".join(sections)

# ============================================================
# FEEDBACK CORRECTION ENGINE
# ============================================================
def extract_move_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    starter = rule_extract_starter(text)
    if starter:
        return canonicalize_move_name(starter)

    q = normalize_notation(text)
    extra_patterns = [
        r"\b(2mp|2mk|2hp|2lp|2lk|2hk|5mp|5mk|5hp|5lp|5lk|5hk)\b",
        r"\b(jhp|jhk|jmp|jmk|jlp|jlk)\b",
    ]
    for pattern in extra_patterns:
        match = re.search(pattern, q)
        if match:
            return canonicalize_move_name(match.group(1))
    return None


def extract_state_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    lower = text.lower()
    if "on block" in lower or "打防" in text or "block" in lower:
        return "block"
    if "on hit" in lower or "命中" in text or "hit" in lower:
        return "normal_hit"
    if "startup" in lower or "启动" in text:
        return "startup"
    return None


def extract_corrected_value_from_comment(comment: str) -> Optional[Any]:
    if not comment:
        return None

    patterns = [
        r"should be\s*([+-]?\d+(?:\.\d+)?)",
        r"应该是\s*([+-]?\d+(?:\.\d+)?)",
        r"是\s*([+-]?\d+(?:\.\d+)?)",
        r"=\s*([+-]?\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, comment, flags=re.IGNORECASE)
        if match:
            return try_parse_numeric(match.group(1))

    numbers = re.findall(r"[+-]?\d+(?:\.\d+)?", comment)
    if numbers:
        return try_parse_numeric(numbers[-1])

    return None


def build_frame_feedback_overrides() -> Dict[Tuple[str, str, str], Any]:
    feedback_list = load_feedback()
    overrides: Dict[Tuple[str, str, str], Any] = {}

    for item in feedback_list:
        comment = (item.get("comment") or "").strip()
        question = (item.get("question") or "").strip()
        if not comment or not question:
            continue

        character = detect_character(question) or detect_character(comment)
        move = extract_move_from_text(question) or extract_move_from_text(comment)
        state = extract_state_from_text(question) or extract_state_from_text(comment)
        corrected_value = extract_corrected_value_from_comment(comment)

        if not character or not move or not state or corrected_value is None:
            continue

        key = (character.lower(), canonicalize_move_name(move), state)
        overrides[key] = corrected_value

    return overrides


def apply_feedback_override_to_frame_entry(character: str, move: str, entry: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    updated = deepcopy(entry)
    notes = []
    overrides = build_frame_feedback_overrides()

    for state_key, entry_field in {
        "block": "on_block",
        "normal_hit": "on_hit",
        "startup": "startup",
    }.items():
        override_key = (character.lower(), canonicalize_move_name(move), state_key)
        if override_key in overrides:
            updated[entry_field] = overrides[override_key]
            notes.append(f"Applied user feedback override: {move} {state_key} = {overrides[override_key]}")

    if notes:
        existing_notes = updated.get("notes")
        if isinstance(existing_notes, list):
            updated["notes"] = existing_notes + notes
        elif isinstance(existing_notes, str) and existing_notes.strip():
            updated["notes"] = [existing_notes] + notes
        else:
            updated["notes"] = notes

    return updated, notes

# ============================================================
# FRAME DATA
# ============================================================
def get_frame_entry(character: str, move: str) -> Optional[Dict[str, Any]]:
    db = load_frame_data_db()
    character_block = db.get(character)
    if not character_block:
        for key in db.keys():
            if key.lower() == character.lower():
                character_block = db[key]
                break
    if not character_block:
        return None

    moves = character_block.get("moves", {})
    if not isinstance(moves, dict):
        return None

    move_norm = canonicalize_move_name(move)
    lookup_aliases = {move_norm, normalize_move_key_for_lookup(move_norm), normalize_move_key_for_lookup(move)}

    if move_norm in moves:
        entry = moves[move_norm]
        updated_entry, _ = apply_feedback_override_to_frame_entry(character, move_norm, entry)
        return updated_entry

    for key, value in moves.items():
        key_norm = normalize_move_key_for_lookup(key)
        if key_norm in lookup_aliases:
            updated_entry, _ = apply_feedback_override_to_frame_entry(character, move_norm, value)
            return updated_entry

        aliases = value.get("aliases", []) if isinstance(value, dict) else []
        for alias in aliases:
            alias_norm = normalize_move_key_for_lookup(alias)
            if alias_norm in lookup_aliases:
                updated_entry, _ = apply_feedback_override_to_frame_entry(character, move_norm, value)
                return updated_entry

    return None


def find_frame_data_for_move(parsed: Dict[str, Any]) -> Dict[str, Any]:
    character = parsed.get("character")
    move = canonicalize_move_name(parsed.get("move") or parsed.get("starter"))

    if not character:
        return {"found": False, "reason": "No character identified.", "move": move, "character": None}

    if not move:
        return {"found": False, "reason": "No move identified.", "move": None, "character": character}

    entry = get_frame_entry(character, move)
    if not entry:
        return {
            "found": False,
            "reason": "Move not found in local frame_data.json.",
            "move": move,
            "character": character
        }

    has_real_data = any(
        entry.get(field) is not None
        for field in ["startup", "active", "recovery", "on_block", "on_hit"]
    )

    if not has_real_data:
        return {
            "found": False,
            "reason": "Move entry exists, but frame data fields are empty.",
            "move": move,
            "character": character,
            "entry": entry
        }

    return {
        "found": True,
        "move": move,
        "character": character,
        "entry": entry
    }

# ============================================================
# COMBO DB
# ============================================================
def combo_character_match(query_character: Optional[str], combo_character: str) -> bool:
    return bool(query_character) and query_character.lower() == combo_character.lower()


def combo_starter_match(query_starter: Optional[str], entry: Dict[str, Any]) -> bool:
    if not query_starter:
        return True
    query_norm = normalize_notation(query_starter)
    aliases = [normalize_notation(entry.get("starter", ""))] + [normalize_notation(a) for a in entry.get("starter_aliases", [])]
    return query_norm in aliases


def combo_state_match(query_state: Optional[str], combo_state: Optional[str]) -> bool:
    return True if not query_state else query_state == combo_state


def combo_position_match(query_position: Optional[str], combo_position: Optional[str]) -> bool:
    return True if not query_position else query_position == combo_position


def combo_resource_match(query_drive: Optional[int], query_super: Optional[int], entry: Dict[str, Any]) -> bool:
    entry_drive = int(entry.get("drive_cost", 0) or 0)
    entry_super = int(entry.get("super_cost", 0) or 0)
    if query_drive is not None and entry_drive > query_drive:
        return False
    if query_super is not None and entry_super > query_super:
        return False
    return True


def filter_combo_candidates(parsed: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    combo_db = load_combo_db()
    candidates = []
    exact_match = False

    for entry in combo_db:
        if not combo_character_match(parsed.get("character"), entry.get("character", "")):
            continue
        if not combo_starter_match(parsed.get("starter"), entry):
            continue
        if not combo_state_match(parsed.get("hit_state"), entry.get("starter_state")):
            continue
        if not combo_position_match(parsed.get("position"), entry.get("position")):
            continue
        if not combo_resource_match(parsed.get("drive"), parsed.get("super"), entry):
            continue
        candidates.append(entry)

    if candidates:
        exact_match = True
        return candidates, exact_match

    for entry in combo_db:
        if not combo_character_match(parsed.get("character"), entry.get("character", "")):
            continue
        if not combo_starter_match(parsed.get("starter"), entry):
            continue
        if not combo_resource_match(parsed.get("drive"), parsed.get("super"), entry):
            continue
        candidates.append(entry)

    return candidates, False


def combo_sort_key(entry: Dict[str, Any], goal: str) -> Tuple:
    damage = int(entry.get("damage", 0) or 0)
    drive_cost = int(entry.get("drive_cost", 0) or 0)
    stability = (entry.get("stability") or "medium").lower()
    difficulty = (entry.get("difficulty") or "medium").lower()
    stability_score = {"high": 3, "medium": 2, "low": 1}.get(stability, 2)
    difficulty_score = {"easy": 3, "medium": 2, "hard": 1}.get(difficulty, 2)
    if goal == "kill":
        return (damage, stability_score, -drive_cost)
    if goal == "stable":
        return (stability_score, difficulty_score, damage)
    if goal == "meter_efficient":
        return (-drive_cost, stability_score, damage)
    return (damage, stability_score, difficulty_score)


def select_best_combo(parsed: Dict[str, Any]) -> Dict[str, Any]:
    candidates, exact_match = filter_combo_candidates(parsed)
    if not candidates:
        return {"found": False, "exact_match": False, "top_candidates": [], "recommended": None}
    goal = parsed.get("goal") or "max_damage"
    sorted_candidates = sorted(candidates, key=lambda x: combo_sort_key(x, goal), reverse=True)
    return {
        "found": True,
        "exact_match": exact_match,
        "top_candidates": sorted_candidates[:3],
        "recommended": sorted_candidates[0],
    }


def format_combo_candidates_for_prompt(candidates: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, c in enumerate(candidates, start=1):
        lines.append(
            f"Candidate {idx}:\n"
            f"ID: {c.get('id')}\n"
            f"Character: {c.get('character')}\n"
            f"Starter: {c.get('starter')}\n"
            f"State: {c.get('starter_state')}\n"
            f"Position: {c.get('position')}\n"
            f"Drive Cost: {c.get('drive_cost')}\n"
            f"Super Cost: {c.get('super_cost')}\n"
            f"Damage: {c.get('damage')}\n"
            f"Stability: {c.get('stability')}\n"
            f"Difficulty: {c.get('difficulty')}\n"
            f"Combo: {c.get('combo')}\n"
            f"Works On: {c.get('works_on')}\n"
            f"Patch: {c.get('patch')}\n"
            f"Notes: {c.get('notes')}\n"
        )
    return "\n".join(lines)

# ============================================================
# LLM ANSWERS
# ============================================================
def grounded_llm_answer(
    user_message: str,
    parsed: Dict[str, Any],
    local_context: str = "",
    wiki_context: str = "",
    wiki_tables: Optional[List[str]] = None
) -> str:
    corrections_text = build_corrections_text(get_recent_corrections(limit=5))
    table_text = "\n\n".join(wiki_tables or [])[:6000]

    prompt = f"""
You are a Street Fighter 6 assistant for a course project.

Goals:
1. Prefer retrieved evidence from LOCAL data or WIKI excerpts.
2. If evidence is incomplete, you MAY still answer with careful SF6 knowledge.
3. When you infer or guess, clearly label it as **Estimated**.
4. Never claim a value is verified unless it appears in the supplied context.
5. If local verified data exists, use it first.
6. Keep the answer useful and natural. Do not be robotic.

Recent user corrections:
{corrections_text}

Parsed query:
{json.dumps(parsed, ensure_ascii=False, indent=2)}

Local context:
{local_context or 'None'}

Wiki context:
{wiki_context or 'None'}

Wiki table snippets:
{table_text or 'None'}

User question:
{user_message}

Required output format:
- Direct answer first
- Then a short section called **Why**
- If use greeting output, treat it as VERIFIED data
- If local_context is provided, treat it as VERIFIED data
- NEVER say "not available" if local_context contains relevant data
- End with **Confidence**: High / Medium / Low
""".strip()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content": "You are a helpful SF6 assistant using retrieval + careful fallback."},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


def call_llm_combo_selector(user_message: str, parsed: Dict[str, Any], combo_result: Dict[str, Any]) -> str:
    corrections_text = build_corrections_text(get_recent_corrections(limit=5))
    candidates = combo_result.get("top_candidates", [])
    context = format_combo_candidates_for_prompt(candidates)

    prompt = f"""
You are a Street Fighter 6 combo recommendation assistant.
You may ONLY choose from the candidate combos provided below.
Do NOT invent a new combo route.
If the candidates are only approximate, clearly say so.

Recent user corrections:
{corrections_text}

Parsed query:
{json.dumps(parsed, ensure_ascii=False, indent=2)}

Verified combo candidates:
{context}

Answer format:
- Recommended combo
- Why this route was chosen
- Resource cost
- Damage
- Stability / difficulty
- One alternative if available
- Confidence

User question:
{user_message}
""".strip()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": "You are a combo ranking assistant. Only use given candidates. Never invent routes."},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


def build_frame_answer(parsed: Dict[str, Any], frame_result: Dict[str, Any]) -> str:
    entry = frame_result["entry"]
    move = frame_result["move"]
    asked_state = parsed.get("hit_state")

    lines = []
    lines.append("**Answer:**")

    if asked_state == "block" and entry.get("on_block") is not None:
        lines.append(f"{move} is **{entry['on_block']} on block**.")
    elif asked_state == "normal_hit" and entry.get("on_hit") is not None:
        lines.append(f"{move} is **{entry['on_hit']} on hit**.")
    else:
        lines.append(f"Frame data for **{move}**:")
        if entry.get("startup") is not None:
            lines.append(f"- Startup: {entry['startup']}")
        if entry.get("active") is not None:
            lines.append(f"- Active: {entry['active']}")
        if entry.get("recovery") is not None:
            lines.append(f"- Recovery: {entry['recovery']}")
        if entry.get("on_block") is not None:
            lines.append(f"- On block: {entry['on_block']}")
        if entry.get("on_hit") is not None:
            lines.append(f"- On hit: {entry['on_hit']}")

    notes = entry.get("notes")
    if notes:
        lines.append("\n**Why:**")
        if isinstance(notes, list):
            for note in notes:
                lines.append(f"- {note}")
        else:
            lines.append(str(notes))
    else:
        lines.append("\n**Why:**")
        lines.append("- Returned from verified local frame data.")

    source_tag = entry.get("source") or "Local Frame Data"
    lines.append("\n**Type:** Verified")
    lines.append(f"**Source:** {source_tag}")
    lines.append("**Confidence:** High")

    return "\n".join(lines)


def prompt_injection_response() -> str:
    return (
        "Your message looks like it contains **prompt-injection or instruction override language**.\n\n"
        "For safety, I will only answer grounded Street Fighter 6 questions based on the supported local sources and tools.\n\n"
        "Please rephrase your question as a normal SF6 gameplay, frame data, strategy, or combo request.\n\n"
        "**Confidence:** High"
    )


def non_sf6_response() -> str:
    return (
        "This assistant focuses on **Street Fighter 6**.\n\n"
        "You can ask about characters, frame data, combos, strategy, matchups, or Drive/Super resources.\n\n"
        "**Confidence:** High"
    )

# ============================================================
# TOOL ROUTERS
# ============================================================
def run_character_doc_tool(user_message: str, parsed: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    all_characters = detect_all_characters(user_message)
    character = parsed.get("character") or (all_characters[0] if len(all_characters) == 1 else None)

    # ===== local sources =====
    card = load_character_card(character) if character else None
    doc = get_character_doc(character) if character else None

    card_context = build_character_card_context(card) if card else ""
    doc_context = build_character_context(doc) if doc else ""

    # ===== embedding RAG search =====
    rag_results = []
    rag_context = ""
    rag_used = False

    try:
        rag_results = search(user_message, top_k=2)
        if rag_results:
            rag_chunks = []
            for i, item in enumerate(rag_results, start=1):
                char_name = item.get("character", "unknown")
                text = item.get("text", "")
                if text:
                    rag_chunks.append(f"[RAG Chunk {i} | Character: {char_name}]\n{text}")
            rag_context = "\n\n".join(rag_chunks)
            rag_used = bool(rag_context.strip())
    except Exception as exc:
        logger.warning("Embedding RAG search failed: %s", str(exc))
        rag_results = []
        rag_context = ""
        rag_used = False

    # ===== merge local verified context =====
    local_context_parts = []

    if card_context:
        local_context_parts.append("Verified local character card data:\n" + card_context)

    if doc_context:
        local_context_parts.append("Verified local character notes:\n" + doc_context)

    if rag_context:
        local_context_parts.append("Embedding retrieval context:\n" + rag_context)

    local_context = "\n\n".join(local_context_parts).strip()

    # ===== decide whether card should be shown =====
    show_card = should_show_character_card(user_message, parsed, character)
    safe_card = card if show_card else None

    # ===== wiki fallback =====
    wiki = fetch_wiki_context(user_message, parsed.get("question_type", "general_sf6"))

    # ===== priority 1: local / rag + model =====
    if local_context and ALLOW_MODEL_FALLBACK:
        answer = grounded_llm_answer(
            user_message=user_message,
            parsed=parsed,
            local_context=local_context,
            wiki_context=wiki.get("text", "")[:12000] if wiki.get("ok") else "",
            wiki_tables=wiki.get("tables", []) if wiki.get("ok") else []
        )
        return answer, {
            "tool": "local_character_card_rag",
            "grounding_level": "local+model",
            "used_local_docs": bool(doc),
            "used_character_card": bool(card),
            "showed_character_card": show_card,
            "used_embedding_rag": rag_used,
            "rag_top_k": len(rag_results),
            "rag_characters": [item.get("character") for item in rag_results if item.get("character")],
            "doc_character": character,
            "detected_characters": all_characters,
            "wiki_url": wiki.get("best_url") if wiki.get("ok") else None,
            "wiki_attempts": wiki.get("attempts", []),
            "character_card": safe_card,
        }

    # ===== priority 2: wiki + model =====
    if wiki.get("ok") and ALLOW_MODEL_FALLBACK:
        answer = grounded_llm_answer(
            user_message=user_message,
            parsed=parsed,
            local_context="",
            wiki_context=wiki.get("text", "")[:12000],
            wiki_tables=wiki.get("tables", [])
        )
        return answer, {
            "tool": "wiki_rag",
            "grounding_level": "wiki+model",
            "used_local_docs": bool(doc),
            "used_character_card": bool(card),
            "showed_character_card": show_card,
            "used_embedding_rag": rag_used,
            "rag_top_k": len(rag_results),
            "rag_characters": [item.get("character") for item in rag_results if item.get("character")],
            "doc_character": character,
            "detected_characters": all_characters,
            "wiki_url": wiki.get("best_url"),
            "wiki_attempts": wiki.get("attempts", []),
            "character_card": safe_card,
        }

    # ===== priority 3: model-only fallback =====
    if ALLOW_MODEL_FALLBACK:
        answer = grounded_llm_answer(
            user_message=user_message,
            parsed=parsed,
            local_context=local_context,
            wiki_context="",
            wiki_tables=[]
        )
        return answer, {
            "tool": "model_fallback",
            "grounding_level": "model_only" if not local_context else "local+model",
            "used_local_docs": bool(doc),
            "used_character_card": bool(card),
            "showed_character_card": show_card,
            "used_embedding_rag": rag_used,
            "rag_top_k": len(rag_results),
            "rag_characters": [item.get("character") for item in rag_results if item.get("character")],
            "doc_character": character,
            "detected_characters": all_characters,
            "wiki_attempts": wiki.get("attempts", []),
            "character_card": safe_card,
        }

    return (
        f"I couldn’t find enough local data for **{character or 'this character'}**.\n\n**Confidence:** Low",
        {
            "tool": "local_character_docs",
            "grounding_level": "none",
            "used_local_docs": bool(doc),
            "used_character_card": bool(card),
            "showed_character_card": False,
            "used_embedding_rag": rag_used,
            "rag_top_k": len(rag_results),
            "rag_characters": [item.get("character") for item in rag_results if item.get("character")],
            "doc_character": character,
            "detected_characters": all_characters,
            "character_card": None,
        },
    )

def run_frame_tool(user_message: str, parsed: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    result = find_frame_data_for_move(parsed)
    print("FRAME RESULT =", result)

    if result["found"]:
        base_answer = build_frame_answer(parsed, result)

        if ALLOW_MODEL_FALLBACK:
            try:
                entry = result.get("entry", {})
                move = result.get("move")
                character = result.get("character")

                local_context = f"""
Verified local frame data:
Character: {character}
Move: {move}
Startup: {entry.get('startup')}
Active: {entry.get('active')}
Recovery: {entry.get('recovery')}
On block: {entry.get('on_block')}
On hit: {entry.get('on_hit')}
Notes: {entry.get('notes')}
Source tag: {entry.get('source', 'local_frame_data')}
""".strip()

                enriched = grounded_llm_answer(
                    user_message=user_message,
                    parsed=parsed,
                    local_context=local_context,
                    wiki_context="",
                    wiki_tables=[]
                )

                return enriched, {
                    "tool": "frame_data_search",
                    "grounding_level": "local+model",
                    "used_local_docs": True,
                    "frame_found": True,
                    "matched_move": move,
                    "character": character,
                    "frame_entry": entry,
                    "base_verified_answer": base_answer,
                    "character_card": None,
                }

            except Exception as exc:
                logger.warning("Frame enrichment failed, fallback to base answer: %s", str(exc))
                return base_answer, {
                    "tool": "frame_data_search",
                    "grounding_level": "local",
                    "used_local_docs": True,
                    "frame_found": True,
                    "matched_move": result.get("move"),
                    "character": result.get("character"),
                    "frame_entry": result.get("entry"),
                    "character_card": None,
                }

        return base_answer, {
            "tool": "frame_data_search",
            "grounding_level": "local",
            "used_local_docs": True,
            "frame_found": True,
            "matched_move": result.get("move"),
            "character": result.get("character"),
            "frame_entry": result.get("entry"),
            "character_card": None,
        }

    wiki = fetch_wiki_context(user_message, "frame_data")
    if wiki.get("ok") and ALLOW_MODEL_FALLBACK:
        answer = grounded_llm_answer(
            user_message=user_message,
            parsed=parsed,
            local_context="",
            wiki_context=wiki.get("text", "")[:12000],
            wiki_tables=wiki.get("tables", [])
        )
        return answer, {
            "tool": "wiki_frame_fallback",
            "grounding_level": "wiki_partial",
            "used_local_docs": False,
            "frame_found": False,
            "matched_move": result.get("move"),
            "character": result.get("character"),
            "wiki_url": wiki.get("best_url"),
            "wiki_attempts": wiki.get("attempts", []),
            "character_card": None,
        }

    if ALLOW_MODEL_FALLBACK:
        answer = grounded_llm_answer(
            user_message=user_message,
            parsed=parsed,
            local_context="",
            wiki_context="",
            wiki_tables=[]
        )
        return answer, {
            "tool": "model_frame_fallback",
            "grounding_level": "model_only",
            "used_local_docs": False,
            "frame_found": False,
            "matched_move": result.get("move"),
            "character": result.get("character"),
            "character_card": None,
        }

    return (
        f"Frame data not found. Character: {result.get('character')} Move: {result.get('move')} Reason: {result.get('reason')}\n\n**Confidence:** Low",
        {
            "tool": "frame_data_search",
            "grounding_level": "none",
            "used_local_docs": False,
            "frame_found": False,
            "matched_move": result.get("move"),
            "character": result.get("character"),
            "character_card": None,
        },
    )


def run_combo_tool(user_message: str, parsed: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    combo_result = select_best_combo(parsed)
    if combo_result.get("found"):
        answer = call_llm_combo_selector(user_message, parsed, combo_result)
        return answer, {
            "tool": "combo_solver",
            "grounding_level": "local",
            "used_combo_db": True,
            "combo_exact_match": combo_result.get("exact_match", False),
            "combo_candidate_ids": [c.get("id") for c in combo_result.get("top_candidates", [])],
            "recommended_combo_id": (combo_result.get("recommended") or {}).get("id"),
            "character_card": None,
        }

    if STRICT_COMBO_ONLY_FROM_DB:
        return (
            "I couldn’t find a verified exact combo match in the local combo database.\n\n**Confidence:** Low",
            {
                "tool": "combo_db_search",
                "grounding_level": "none",
                "used_combo_db": False,
                "combo_exact_match": False,
                "character_card": None,
            },
        )

    wiki = fetch_wiki_context(user_message, "combo")
    if wiki.get("ok") and ALLOW_MODEL_FALLBACK:
        answer = grounded_llm_answer(
            user_message,
            parsed,
            wiki_context=wiki.get("text", "")[:12000],
            wiki_tables=wiki.get("tables", [])
        )
        return answer, {
            "tool": "wiki_combo_fallback",
            "grounding_level": "wiki_partial",
            "used_combo_db": False,
            "combo_exact_match": False,
            "wiki_url": wiki.get("best_url"),
            "wiki_attempts": wiki.get("attempts", []),
            "character_card": None,
        }

    if ALLOW_MODEL_FALLBACK:
        answer = grounded_llm_answer(user_message, parsed)
        return answer, {
            "tool": "model_combo_fallback",
            "grounding_level": "model_only",
            "used_combo_db": False,
            "combo_exact_match": False,
            "character_card": None,
        }

    return (
        "I couldn’t find a verified combo and fallback is disabled.\n\n**Confidence:** Low",
        {
            "tool": "combo_db_search",
            "grounding_level": "none",
            "used_combo_db": False,
            "combo_exact_match": False,
            "character_card": None,
        },
    )

# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json() or {}
        user_message = (data.get("message") or "").strip()

        print("🔥 NEW VERSION RUNNING 🔥")
        print("USER MESSAGE =", user_message)

        if not user_message:
            return jsonify({"reply": "Please enter a question."}), 400

        logger.info("User question: %s", user_message)

        if contains_prompt_injection(user_message):
            reply = prompt_injection_response()
            answer_id = str(uuid.uuid4())
            confidence = estimate_confidence("general_sf6", "security_filter")
            save_eval_entry({
                "timestamp": datetime.now().isoformat(),
                "answer_id": answer_id,
                "question": user_message,
                "question_type": "blocked_injection",
                "grounding_level": "security_filter",
                "confidence": confidence,
                "hallucination_risk": False,
            })
            return jsonify({
                "reply": reply,
                "answer_id": answer_id,
                "source": "security_filter",
                "confidence": confidence,
                "question_type": "blocked_injection",
                "character_card": None,
            })

        if is_greeting(user_message):
            reply = greeting_response()
            answer_id = str(uuid.uuid4())
            return jsonify({
                "reply": reply,
                "answer_id": answer_id,
                "source": "greeting_handler",
                "confidence": "high",
                "question_type": "greeting",
                "character_card": None,
            })

        if not is_sf6_question(user_message):
            reply = non_sf6_response()
            answer_id = str(uuid.uuid4())
            return jsonify({
                "reply": reply,
                "answer_id": answer_id,
                "source": "sf6_filter",
                "confidence": "high",
                "question_type": "non_sf6",
                "character_card": None,
            })

        enriched_message, conversation_state, state_used = enrich_query_with_state(user_message)

        print("CONVERSATION STATE =", conversation_state)
        print("STATE USED =", state_used)
        print("ENRICHED MESSAGE =", enriched_message)

        parsed = llm_extract_query_structure(enriched_message)
        question_type = parsed.get("question_type") or detect_question_type(enriched_message)

        print("PARSED =", parsed)
        print("QUESTION TYPE =", question_type)

        update_state_from_parsed(parsed, question_type)

        if question_type == "combo":
            reply, tool_meta = run_combo_tool(enriched_message, parsed)
        elif question_type == "frame_data":
            reply, tool_meta = run_frame_tool(enriched_message, parsed)
        else:
            reply, tool_meta = run_character_doc_tool(enriched_message, parsed)

        answer_id = str(uuid.uuid4())
        grounding_level = tool_meta.get("grounding_level", "none")
        exact_combo_match = bool(tool_meta.get("combo_exact_match", False))
        frame_found = bool(tool_meta.get("frame_found", False))
        confidence = estimate_confidence(question_type, grounding_level, exact_combo_match, frame_found, tool_meta.get("used_character_card", False))
        hallucination_risk = detect_hallucination_risk(question_type, grounding_level, reply)

        save_eval_entry({
            "timestamp": datetime.now().isoformat(),
            "answer_id": answer_id,
            "question": user_message,
            "parsed_query": parsed,
            "question_type": question_type,
            "tool_meta": tool_meta,
            "grounding_level": grounding_level,
            "combo_exact_match": exact_combo_match,
            "frame_found": frame_found,
            "confidence": confidence,
            "hallucination_risk": hallucination_risk,
        })

        return jsonify({
            "reply": reply,
            "answer_id": answer_id,
            "source": tool_meta.get("tool", "unknown"),
            "confidence": confidence,
            "question_type": question_type,
            "parsed_query": parsed,
            "tool_meta": tool_meta,
            "character_card": tool_meta.get("character_card"),
        })

    except Exception as exc:
        logger.exception("/chat error")
        return jsonify({"reply": f"Server error: {str(exc)}"}), 500


@app.route("/feedback", methods=["POST"])
def submit_feedback():
    try:
        data = request.get_json() or {}
        answer_id = (data.get("answer_id") or "").strip()
        question = (data.get("question") or "").strip()
        answer = (data.get("answer") or "").strip()
        feedback_type = (data.get("feedback_type") or "neutral").strip()
        rating = data.get("rating", None)
        comment = (data.get("comment") or "").strip()
        source = (data.get("source") or "").strip()
        confidence = (data.get("confidence") or "").strip()
        question_type = (data.get("question_type") or "").strip()

        if not answer_id:
            return jsonify({"message": "answer_id is required."}), 400

        if feedback_type not in ["like", "dislike", "neutral"]:
            feedback_type = "neutral"

        if rating is not None:
            try:
                rating = int(rating)
                if rating < 1 or rating > 5:
                    return jsonify({"message": "rating must be between 1 and 5."}), 400
            except ValueError:
                return jsonify({"message": "rating must be an integer."}), 400

        feedback_list = load_feedback()
        feedback_entry = {
            "answer_id": answer_id,
            "question": question,
            "answer": answer,
            "feedback_type": feedback_type,
            "rating": rating,
            "comment": comment,
            "source": source,
            "confidence": confidence,
            "question_type": question_type,
            "timestamp": datetime.now().isoformat(),
        }
        feedback_list.append(feedback_entry)
        save_feedback(feedback_list)

        return jsonify({
            "message": "Feedback submitted successfully.",
            "feedback_applied_next_time": True
        })
    except Exception as exc:
        logger.exception("/feedback error")
        return jsonify({"message": f"Feedback error: {str(exc)}"}), 500


@app.route("/stats", methods=["GET"])
def stats():
    try:
        feedback_list = load_feedback()
        eval_log = load_eval_log()
        total_feedback = len(feedback_list)
        likes = sum(1 for item in feedback_list if item.get("feedback_type") == "like")
        dislikes = sum(1 for item in feedback_list if item.get("feedback_type") == "dislike")
        neutrals = sum(1 for item in feedback_list if item.get("feedback_type") == "neutral")
        ratings = [item["rating"] for item in feedback_list if isinstance(item.get("rating"), int)]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

        total_eval = len(eval_log)
        combo_queries = sum(1 for item in eval_log if item.get("question_type") == "combo")
        frame_queries = sum(1 for item in eval_log if item.get("question_type") == "frame_data")
        local_grounded = sum(1 for item in eval_log if item.get("grounding_level") in {"local", "local+model"})
        wiki_grounded = sum(1 for item in eval_log if item.get("grounding_level") in {"wiki_partial", "wiki+model"})
        hallucination_risk_cases = sum(1 for item in eval_log if item.get("hallucination_risk") is True)
        injection_blocks = sum(1 for item in eval_log if item.get("question_type") == "blocked_injection")
        feedback_overrides = len(build_frame_feedback_overrides())

        return jsonify({
            "feedback": {
                "total_feedback": total_feedback,
                "likes": likes,
                "dislikes": dislikes,
                "neutral": neutrals,
                "average_rating": avg_rating,
                "frame_feedback_overrides": feedback_overrides,
            },
            "evaluation": {
                "total_logged_answers": total_eval,
                "combo_queries": combo_queries,
                "frame_queries": frame_queries,
                "local_grounded_queries": local_grounded,
                "wiki_grounded_queries": wiki_grounded,
                "hallucination_risk_cases": hallucination_risk_cases,
                "blocked_injection_attempts": injection_blocks,
            }
        })
    except Exception as exc:
        logger.exception("/stats error")
        return jsonify({"message": f"Stats error: {str(exc)}"}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "openai_key_loaded": bool(OPENAI_API_KEY),
        "base_dir": str(BASE_DIR),
        "env_exists": ENV_PATH.exists(),
        "combo_db_exists": COMBO_DB_FILE.exists(),
        "frame_data_exists": FRAME_DATA_FILE.exists(),
        "character_docs_exists": CHARACTER_DOCS_FILE.exists(),
        "character_cards_dir_exists": CHARACTER_CARDS_DIR.exists(),
        "feedback_file_exists": FEEDBACK_FILE.exists(),
        "allow_model_fallback": ALLOW_MODEL_FALLBACK,
        "allow_wiki_fetch": ALLOW_WIKI_FETCH,
        "strict_combo_only_from_db": STRICT_COMBO_ONLY_FROM_DB,
    })


if __name__ == "__main__":
    ensure_runtime_files()
    logger.info("Base dir: %s", BASE_DIR)
    logger.info("ENV path exists: %s", ENV_PATH.exists())
    logger.info("OpenAI key loaded: %s", bool(OPENAI_API_KEY))
    logger.info("Using model: %s", OPENAI_MODEL)
    logger.info("ALLOW_MODEL_FALLBACK=%s", ALLOW_MODEL_FALLBACK)
    logger.info("ALLOW_WIKI_FETCH=%s", ALLOW_WIKI_FETCH)
    app.run(debug=True)
