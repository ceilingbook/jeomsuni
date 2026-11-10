"""사전 오픈 API에서 낱말 카드 데이터(cards.json)를 만든다.

준비 (cmd, 한 번만):
    setx OPENDICT_KEY 우리말샘_인증키
    setx KRDICT_KEY 한국어기초사전_인증키
    (입력 후 cmd 창을 닫고 새로 연다)

실행:
    cd C:\\jeomsuni
    chcp 65001
    python make_cards.py

이미 cards.json에 있는 낱말은 건너뛴다. 다시 받고 싶은 낱말은 cards.json에서 그 카드를 지운 뒤 실행한다.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

OPENDICT_URL = "https://opendict.korean.go.kr/api/search"
KRDICT_URL = "https://krdict.korean.go.kr/api/search"
OUTPUT_FILE = "cards.json"
BLOCKLIST_FILE = "금지어.txt"
REQUEST_DELAY = 0.3

# 카드로 만들 낱말과, 학생이 검색할 수 있는 다른 표기
WORDS = {
    "마름": [],
    "쌩이질": ["생이질"],
    "배재": [],
    "면두": [],
    "호드기": [],
    "삭정이": [],
    "홰": ["횃소리"],
    "대강이": [],
    "봉당": [],
    "울섶": [],
    "두엄": [],
    "감때사납다": ["감때사나운"],
}


def configure_console():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")


def request_xml(url, params):
    """API를 호출해 응답 글자를 돌려준다."""
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=20) as response:
        return response.read().decode("utf-8")


def parse_items(xml_text):
    """응답에서 item 목록을 꺼낸다. 오류 응답이면 ValueError를 낸다."""
    root = ET.fromstring(xml_text)
    if root.tag == "error":
        code = root.findtext("error_code") or "?"
        message = (root.findtext("message") or "").strip()
        raise ValueError(f"{code} {message}")
    return root.findall(".//item")


def clean_word(word):
    """표제어에 붙은 ^, - 표시를 지운다."""
    return re.sub(r"[\^\-]", "", (word or "").strip())


def read_translations(sense):
    """sense 안의 번역을 {언어: {word, dfn}} 으로 읽는다."""
    result = {}
    for node in sense.findall("translation"):
        lang = (node.findtext("trans_lang") or "").strip()
        word = (node.findtext("trans_word") or "").strip()
        dfn = (node.findtext("trans_dfn") or "").strip()
        if lang and (word or dfn):
            result[lang] = {"word": word, "dfn": dfn}
    return result


def read_entries(item, source):
    """item 하나에서 뜻(sense)마다 항목을 만든다."""
    entries = []
    for sense in item.findall("sense"):
        definition = (sense.findtext("definition") or "").strip()
        if not definition:
            continue
        entry = {
            "source": source,
            "pos": (item.findtext("pos") or "").strip(),
            "type": (sense.findtext("type") or "").strip(),
            "level": (item.findtext("word_grade") or "").strip(),
            "definition": definition,
            "link": (sense.findtext("link") or item.findtext("link") or "").strip(),
            "translations": read_translations(sense),
        }
        entries.append(entry)
    return entries


def pick_exact(items, word, source):
    """표제어가 검색어와 똑같은 item의 뜻만 모은다."""
    entries = []
    for item in items:
        if clean_word(item.findtext("word")) == word:
            entries.extend(read_entries(item, source))
    return entries


def show_response_head(xml_text):
    """결과가 0건일 때 원인을 알 수 있게 응답 앞부분을 한 줄로 보여 준다. 인증키는 응답에 없다."""
    head = re.sub(r"\s+", " ", xml_text)[:300]
    print(f"  (응답 앞부분) {head}")


def fetch_opendict(key, word):
    xml_text = request_xml(
        OPENDICT_URL,
        {"key": key, "q": word, "req_type": "xml", "part": "word", "num": 50},
    )
    entries = pick_exact(parse_items(xml_text), word, "우리말샘")
    if not entries:
        show_response_head(xml_text)
    return entries


def fetch_krdict(key, word):
    xml_text = request_xml(
        KRDICT_URL,
        {"key": key, "q": word, "part": "word", "translated": "y",
         "trans_lang": "0", "num": 20},
    )
    return pick_exact(parse_items(xml_text), word, "한국어기초사전")


def load_banned_words(path):
    """금지어.txt의 [강한말], [짧은말] 항목을 읽는다. 파일이 없으면 빈 목록."""
    if not os.path.exists(path):
        return []
    words, section = [], None
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
            elif section in ("강한말", "짧은말"):
                words.append(line.lower())
    return words


def has_banned_word(text, banned_words):
    lowered = text.lower()
    return any(word in lowered for word in banned_words)


def mark_blocked(entries, banned_words):
    """금지어가 들어 있는 풀이는 사이트에서 보이지 않게 표시한다."""
    for entry in entries:
        if has_banned_word(entry["definition"], banned_words):
            entry["blocked"] = True
    return entries


def build_card(word, aliases, entries):
    return {
        "word": word,
        "aliases": aliases,
        "scene": "",
        "easy": "",
        "reviewed": False,
        "entries": entries,
    }


def load_existing(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("cards", [])


def save_cards(path, cards):
    data = {
        "updated": date.today().isoformat(),
        "sources": ["국립국어원 한국어기초사전", "국립국어원 우리말샘"],
        "cards": cards,
    }
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def collect_entries(word, fetchers, banned_words):
    """사전마다 풀이를 받아 한 목록으로 합친다. 실패한 사전은 안내만 하고 넘어간다."""
    entries = []
    for source, (key, fetch) in fetchers.items():
        try:
            found = fetch(key, word)
        except Exception as error:
            print(f"  [오류] {source}: {type(error).__name__} {str(error)[:120]}")
            continue
        print(f"  {source}: {len(found)}건")
        entries.extend(mark_blocked(found, banned_words))
        time.sleep(REQUEST_DELAY)
    return entries


def main():
    configure_console()
    keys = {
        "우리말샘": (os.environ.get("OPENDICT_KEY", "").strip(), fetch_opendict),
        "한국어기초사전": (os.environ.get("KRDICT_KEY", "").strip(), fetch_krdict),
    }
    fetchers = {name: pair for name, pair in keys.items() if pair[0]}
    if not fetchers:
        print("환경 변수 OPENDICT_KEY, KRDICT_KEY가 없습니다. 안내를 다시 확인해 주세요.")
        return
    for name in keys:
        if name not in fetchers:
            print(f"[알림] {name} 키가 없어서 이 사전은 건너뜁니다.")

    banned_words = load_banned_words(BLOCKLIST_FILE)
    cards = load_existing(OUTPUT_FILE)
    done = {card["word"] for card in cards}

    for word, aliases in WORDS.items():
        if word in done:
            print(f"{word}: 이미 있어서 건너뜀")
            continue
        print(f"{word}:")
        entries = collect_entries(word, fetchers, banned_words)
        cards.append(build_card(word, aliases, entries))

    save_cards(OUTPUT_FILE, cards)
    print(f"\n{OUTPUT_FILE}에 카드 {len(cards)}장을 저장했어요.")
    print("scene(동백꽃 속 장면), easy(쉬운 풀이)는 직접 채우고, 확인한 카드는 reviewed를 true로 바꾸세요.")


if __name__ == "__main__":
    main()