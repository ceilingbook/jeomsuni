"""cards.json을 첫 글자(초성)별 파일로 쪼개 data/ 폴더에 만든다.

사이트는 cards.json 전체가 아니라 data/manifest.json(목록)과, 검색한 글자의 파일 하나만 불러온다.
cards.json은 계속 직접 고치는 원본이다. 고친 뒤에는 이 스크립트를 다시 실행한다.

실행 (cmd):
    cd /d C:\\jeomsuni && chcp 65001 && python build_shards.py

data/ 폴더 안의 *.json은 이 스크립트가 매번 새로 만든다. 직접 고치지 않는다.
"""
import json
import os
import sys
from datetime import date

SOURCE_FILE = "cards.json"
OUTPUT_DIR = "data"
SIZE_WARN_KB = 300

INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
# 된소리는 같은 예사소리 묶음에 합친다. (쌩이질과 생이질이 같은 파일에 들어간다)
MERGE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
# 한글 파일 이름이 주소에서 깨지지 않도록 영문 이름을 쓴다.
FILE_NAMES = {
    "ㄱ": "g", "ㄴ": "n", "ㄷ": "d", "ㄹ": "r", "ㅁ": "m", "ㅂ": "b", "ㅅ": "s",
    "ㅇ": "o", "ㅈ": "j", "ㅊ": "ch", "ㅋ": "k", "ㅌ": "t", "ㅍ": "p", "ㅎ": "h",
    "etc": "etc",
}


def configure_console():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")


def initial_of(text):
    """첫 글자의 초성을 돌려준다. 한글이 아니면 'etc'."""
    text = (text or "").strip()
    if not text:
        return "etc"
    ch = text[0]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        jamo = INITIALS[(code - 0xAC00) // 588]
    elif ch in INITIALS:
        jamo = ch
    else:
        return "etc"
    return MERGE.get(jamo, jamo)


def load_cards(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("cards", [])


def group_cards(cards):
    """초성별로 {cards: [...], aliases: {별칭: 낱말}} 를 모은다."""
    groups = {}
    for card in cards:
        group = groups.setdefault(initial_of(card["word"]), {"cards": [], "aliases": {}})
        group["cards"].append(card)
        for alias in card.get("aliases", []):
            alias_group = groups.setdefault(initial_of(alias), {"cards": [], "aliases": {}})
            alias_group["aliases"][alias] = card["word"]
    return groups


def clear_old_files(folder):
    """이 스크립트가 만든 예전 *.json만 지운다."""
    if not os.path.isdir(folder):
        return
    for name in os.listdir(folder):
        if name.endswith(".json"):
            os.remove(os.path.join(folder, name))


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def write_shards(groups, folder):
    """초성별 파일을 쓰고, 목록(manifest)에 넣을 정보를 돌려준다."""
    os.makedirs(folder, exist_ok=True)
    clear_old_files(folder)
    info = {}
    for initial, group in sorted(groups.items()):
        file_name = FILE_NAMES[initial] + ".json"
        path = os.path.join(folder, file_name)
        write_json(path, {"initial": initial, **group})
        info[initial] = {"file": file_name, "count": len(group["cards"])}
        size_kb = os.path.getsize(path) / 1024
        warning = "  <- 크면 두 글자 단위로 나누는 것을 고려" if size_kb > SIZE_WARN_KB else ""
        print(f"  {initial} -> {file_name}: 카드 {len(group['cards'])}장, {size_kb:.1f}KB{warning}")
    return info


def write_manifest(folder, info, total):
    manifest = {"updated": date.today().isoformat(), "total": total, "initials": info}
    write_json(os.path.join(folder, "manifest.json"), manifest)


def main():
    configure_console()
    if not os.path.exists(SOURCE_FILE):
        print(f"{SOURCE_FILE} 파일이 이 폴더에 없습니다.")
        return
    cards = load_cards(SOURCE_FILE)
    groups = group_cards(cards)
    print(f"카드 {len(cards)}장을 {len(groups)}개 파일로 나눕니다.")
    info = write_shards(groups, OUTPUT_DIR)
    write_manifest(OUTPUT_DIR, info, len(cards))
    print(f"\n{OUTPUT_DIR} 폴더에 만들었어요. 이 폴더를 저장소에 올리세요.")


if __name__ == "__main__":
    main()
