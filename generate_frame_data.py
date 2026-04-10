import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FRAME_DATA_FILE = BASE_DIR / "frame_data.json"

ROSTER = [
    "Ryu", "Ken", "Chun-Li", "Juri", "Luke", "Cammy", "Guile", "Akuma",
    "Dee Jay", "Manon", "Marisa", "JP", "Zangief", "Dhalsim", "Kimberly",
    "Blanka", "E. Honda", "Rashid", "A.K.I.", "Ed", "Jamie", "Lily",
    "M. Bison", "Terry", "Mai", "Elena", "Sagat"
]

DEFAULT_MOVES = {
    "5LP": {"aliases": ["LP", "st.LP", "s.LP", "standing light punch"]},
    "5LK": {"aliases": ["LK", "st.LK", "s.LK", "standing light kick"]},
    "5MP": {"aliases": ["MP", "st.MP", "s.MP", "standing medium punch"]},
    "5MK": {"aliases": ["MK", "st.MK", "s.MK", "standing medium kick"]},
    "5HP": {"aliases": ["HP", "st.HP", "s.HP", "standing heavy punch"]},
    "5HK": {"aliases": ["HK", "st.HK", "s.HK", "standing heavy kick"]},

    "2LP": {"aliases": ["cr.LP", "c.LP", "crouching light punch"]},
    "2LK": {"aliases": ["cr.LK", "c.LK", "crouching light kick"]},
    "2MP": {"aliases": ["cr.MP", "c.MP", "crouching medium punch"]},
    "2MK": {"aliases": ["cr.MK", "c.MK", "crouching medium kick"]},
    "2HP": {"aliases": ["cr.HP", "c.HP", "crouching heavy punch"]},
    "2HK": {"aliases": ["cr.HK", "c.HK", "crouching heavy kick"]},

    "JLP": {"aliases": ["j.LP", "jumping light punch"]},
    "JLK": {"aliases": ["j.LK", "jumping light kick"]},
    "JMP": {"aliases": ["j.MP", "jumping medium punch"]},
    "JMK": {"aliases": ["j.MK", "jumping medium kick"]},
    "JHP": {"aliases": ["j.HP", "jumping heavy punch"]},
    "JHK": {"aliases": ["j.HK", "jumping heavy kick"]}
}

# 你可以在这里放你目前已知的具体数值
KNOWN_DATA = {
    "Ryu": {
        "moves": {
            "2MK": {
                "startup": 7,
                "on_block": -6,
                "on_hit": -1,
                "aliases": ["cr.MK", "c.MK", "crouching medium kick"],
                "source": "manual_verified"
            }
        }
    }
}

def build_character_block(name: str) -> dict:
    return {
        "character": name,
        "stats": {
            "health": None,
            "pre_jump": None,
            "walk_speed_forward": None,
            "walk_speed_back": None
        },
        "moves": {
            move_name: {
                "startup": None,
                "active": None,
                "recovery": None,
                "on_block": None,
                "on_hit": None,
                "notes": [],
                "source": "unfilled",
                **move_template
            }
            for move_name, move_template in DEFAULT_MOVES.items()
        },
        "metadata": {
            "status": "skeleton",
            "last_updated": None
        }
    }

def deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base

def main():
    output = {}
    for character in ROSTER:
        output[character] = build_character_block(character)

    for character, patch in KNOWN_DATA.items():
        if character in output:
            deep_merge(output[character], patch)
        else:
            output[character] = patch

    with open(FRAME_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Generated: {FRAME_DATA_FILE}")

if __name__ == "__main__":
    main()