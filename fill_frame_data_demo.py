import json
from pathlib import Path

FRAME_DATA_FILE = Path("frame_data.json")

# 按招式类别给一套“演示用估算模板”
ESTIMATES = {
    "5LP": {"startup": 4, "active": 2, "recovery": 8,  "on_block": -1, "on_hit": 3},
    "5LK": {"startup": 5, "active": 2, "recovery": 10, "on_block": -2, "on_hit": 2},
    "5MP": {"startup": 6, "active": 3, "recovery": 12, "on_block": -2, "on_hit": 4},
    "5MK": {"startup": 8, "active": 3, "recovery": 15, "on_block": -4, "on_hit": 1},
    "5HP": {"startup": 10, "active": 3, "recovery": 21, "on_block": -2, "on_hit": 3},
    "5HK": {"startup": 12, "active": 3, "recovery": 24, "on_block": -5, "on_hit": 2},

    "2LP": {"startup": 4, "active": 2, "recovery": 8,  "on_block": -1, "on_hit": 3},
    "2LK": {"startup": 5, "active": 2, "recovery": 10, "on_block": -2, "on_hit": 1},
    "2MP": {"startup": 6, "active": 3, "recovery": 12, "on_block": -1, "on_hit": 4},
    "2MK": {"startup": 7, "active": 3, "recovery": 17, "on_block": -6, "on_hit": -1},
    "2HP": {"startup": 8, "active": 4, "recovery": 20, "on_block": -5, "on_hit": 2},
    "2HK": {"startup": 9, "active": 3, "recovery": 21, "on_block": -8, "on_hit": "KD"},

    "JLP": {"startup": 4, "active": 4, "recovery": None, "on_block": None, "on_hit": None},
    "JLK": {"startup": 5, "active": 5, "recovery": None, "on_block": None, "on_hit": None},
    "JMP": {"startup": 6, "active": 6, "recovery": None, "on_block": None, "on_hit": None},
    "JMK": {"startup": 7, "active": 6, "recovery": None, "on_block": None, "on_hit": None},
    "JHP": {"startup": 8, "active": 7, "recovery": None, "on_block": None, "on_hit": None},
    "JHK": {"startup": 9, "active": 7, "recovery": None, "on_block": None, "on_hit": None},
}

def fill_entry(move_name: str, entry: dict) -> dict:
    template = ESTIMATES.get(move_name)
    if not template:
        return entry

    # 只填空，不覆盖已有值
    for key, value in template.items():
        if entry.get(key) is None:
            entry[key] = value

    # notes
    notes = entry.get("notes")
    if not isinstance(notes, list):
        entry["notes"] = []
    if "Demo estimate, not verified frame data." not in entry["notes"]:
        entry["notes"].append("Demo estimate, not verified frame data.")

    # source
    if entry.get("source") in (None, "", "unfilled"):
        entry["source"] = "estimated_generated"

    return entry

def main():
    if not FRAME_DATA_FILE.exists():
        print(f"找不到文件: {FRAME_DATA_FILE.resolve()}")
        return

    with open(FRAME_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    filled_count = 0

    for character_name, character_data in data.items():
        moves = character_data.get("moves", {})
        for move_name, entry in moves.items():
            before = json.dumps(entry, ensure_ascii=False, sort_keys=True)
            fill_entry(move_name, entry)
            after = json.dumps(entry, ensure_ascii=False, sort_keys=True)
            if before != after:
                filled_count += 1

        metadata = character_data.get("metadata", {})
        metadata["status"] = "demo_estimated"
        metadata["last_updated"] = "2026-04-03"
        character_data["metadata"] = metadata

    with open(FRAME_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"完成。共补全/更新 {filled_count} 条 move 数据。")
    print("所有自动补的数据都已标记 source = estimated_generated")

if __name__ == "__main__":
    main()