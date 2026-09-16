"""
MBPP (Mostly Basic Python Problems) dataset'ini Türkçeye çevirir.
Varsayılan motor DeepL API'dir (sözlüklü); --engine ollama ile yerel model kullanılabilir.

Kullanım:
    python translate_mbpp.py --hf-split test --out data/mbpp_tr_test.jsonl --no-review
    python translate_mbpp.py --split full --hf-split test --out data/full/mbpp_tr_test.jsonl \
        --no-review --reuse-from "data/mbpp_tr_*.jsonl"

MBPP lisansı: CC-BY-4.0 (google-research-datasets/mbpp)
Bu script sadece görev açıklamasını ('prompt' / 'text') çevirir;
diğer tüm alanlar (code, test_list, test_imports, test_setup_code, ...)
orijinal haliyle korunur.

Aynı --out dosyasıyla tekrar çalıştırıldığında zaten çevrilmiş task_id'ler
atlanır (kaldığı yerden devam). Başarısız satırlar <out>.failed.jsonl
dosyasına yazılır ve bir sonraki çalıştırmada yeniden denenir.

Her çeviri İngilizceye geri çevrilip orijinalle karşılaştırılır; sonuç
<out>.review.jsonl dosyasına yazılır. Anlamı kaymış olabilecek satırlar
"flagged": true ile işaretlenir (kapatmak için --no-review).

--reuse-from verilirse, İngilizce metni birebir aynı olan satırlarda o dosyaların
onaylı çevirileri kullanılır ve çıktının karar dosyasına onaylı olarak eklenir.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from datasets import load_dataset
from dotenv import load_dotenv

from tr_rules import normalize_tr

# DEEPL_API_KEY gibi değerler proje kökündeki .env dosyasından okunur.
# Terminalde ayarlanmış bir ortam değişkeni varsa o önceliklidir.
load_dotenv(Path(__file__).resolve().parent / ".env")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma3:4b"
# İlk istekte model belleğe yüklendiği için süre uzun tutuldu
REQUEST_TIMEOUT = 180

GLOSSARY = (
    "- Koddaki fonksiyon isimleri, değişken isimleri, string/sayı değerleri ve "
    "backtick içindeki ifadeler OLDUĞU GİBİ kalmalı.\n"
    "- Teknik terimler için şu karşılıkları kullan: list → liste, tuple → demet, "
    "dictionary → sözlük, set → küme, string → string, array → dizi, "
    "integer → tam sayı, element → eleman, occurrence → geçiş, "
    "duplicate → tekrar eden, lowercase → küçük harf, uppercase → büyük harf.\n"
)

# --- Şablon modu -----------------------------------------------------------
# MBPP cümlelerinin ~%99'u "Write a (python) function to/that/which ..." ile başlar.
# Modele sadece görev kısmı verilir, "... bir (Python) fonksiyonu yazın." kalıbı koddan eklenir.
TEMPLATE_RE = re.compile(
    r"^\s*write\s+an?\s+(?P<python>python\s+)?function\s+(?:to|that|which)\s+(?P<task>.+?)\s*\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)

CLAUSE_SYSTEM_PROMPT = (
    "Sen bir teknik çevirmensin. Sana bir Python fonksiyonunun ne yaptığını anlatan "
    "İngilizce bir ifade verilecek. Bunu, Türkçede 'bir fonksiyon' kelimelerinin "
    "ÖNÜNE gelecek bir sıfat-fiil öbeğine çevir.\n"
    "Kurallar:\n"
    "- Çıktı '-an' veya '-en' ekiyle biten bir fiille bitmeli (bulan, eden, döndüren, silen...).\n"
    "- 'fonksiyon', 'yazın' kelimelerini ve nokta işaretini EKLEME.\n"
    "- Anlamın tamamını koru; hiçbir koşulu, sayıyı veya ilişkiyi atlama.\n"
    + GLOSSARY
    + "- Yalnızca öbeği döndür; açıklama, alternatif veya tırnak ekleme.\n"
)

# Örnekler bilerek değerlendirme satırlarından farklı seçildi
CLAUSE_EXAMPLES = [
    ("find the maximum element in a given list",
     "verilen bir listedeki en büyük elemanı bulan"),
    ("check whether the given string is a palindrome or not",
     "verilen string'in palindrom olup olmadığını kontrol eden"),
    ("returns the number of vowels in a string",
     "bir string'deki sesli harflerin sayısını döndüren"),
    ("merge two sorted lists into a single sorted list",
     "sıralı iki listeyi tek bir sıralı liste halinde birleştiren"),
    ("count the elements of a tuple that are greater than k",
     "bir demetteki k'dan büyük elemanları sayan"),
    ("remove the first occurrence of a given word from a sentence",
     "verilen bir kelimenin cümledeki ilk geçişini silen"),
]

# --- Serbest mod -----------------------------------------------------------
# Şablona uymayan veya şablon modunda çevrilemeyen cümleler için
FULL_SYSTEM_PROMPT = (
    "Sen bir teknik çevirmensin. Sana verilen İngilizce Python programlama "
    "görevi açıklamasını doğal, akıcı Türkçe'ye çevir.\n"
    "Kurallar:\n"
    + GLOSSARY
    + "- Cümle yapısını doğal Türkçe'ye uyarla, kelime kelime çevirme. "
    "'Bir fonksiyon yazın ki ...' gibi İngilizce kalıplar kullanma; "
    "'... yapan bir fonksiyon yazın.' yapısını tercih et.\n"
    "- Anlamın tamamını koru; hiçbir koşulu, sayıyı veya ilişkiyi atlama.\n"
    "- Yalnızca çeviriyi tek parça halinde döndür. Açıklama, alternatif, "
    "giriş cümlesi veya tırnak işareti ekleme.\n"
)

FULL_EXAMPLES = [
    ("Write a function to find the maximum element in a given list.",
     "Verilen bir listedeki en büyük elemanı bulan bir fonksiyon yazın."),
    ("Given a list of integers, write a function that returns the sum of the even numbers.",
     "Tam sayılardan oluşan bir liste verildiğinde, listedeki çift sayıların toplamını "
     "döndüren bir fonksiyon yazın."),
    ("The input is a dictionary mapping names to ages. Write a function to return the "
     "names of people older than 30. The function should return a list.",
     "Girdi, isimleri yaşlarla eşleyen bir sözlüktür. 30 yaşından büyük kişilerin "
     "isimlerini döndüren bir fonksiyon yazın. Fonksiyon bir liste döndürmelidir."),
]

# Modelin sık eklediği önekler: "Türkçe çeviri:", "Çeviri:", "Translation:"
_PREFIX_RE = re.compile(r"^\s*(türkçe\s+çeviri|çeviri|translation)\s*:\s*", re.IGNORECASE)
_QUOTE_PAIRS = [('"', '"'), ("'", "'"), ("“", "”"), ("«", "»"), ("‘", "’")]
# Model kurala rağmen öbeğin sonuna "bir fonksiyon (yazın)" eklerse
_CLAUSE_TAIL_RE = re.compile(r"\s*\bbir\s+(python\s+)?fonksiyon(u)?(\s+yazın)?\s*\.?\s*$", re.IGNORECASE)
_CLAUSE_END_RE = re.compile(r"[a-zçğıöşü]*(y?an|y?en)$", re.IGNORECASE)


def clean_translation(text: str) -> str:
    """Model çıktısındaki önek, tırnak ve markdown kalıntılarını temizler."""
    text = text.strip()
    text = _PREFIX_RE.sub("", text).strip()
    # Tüm metni saran **kalın** veya tırnak işaretlerini kaldır
    if text.startswith("**") and text.endswith("**") and len(text) > 4:
        text = text[2:-2].strip()
    for open_q, close_q in _QUOTE_PAIRS:
        if len(text) >= 2 and text.startswith(open_q) and text.endswith(close_q):
            text = text[1:-1].strip()
            break
    return text


def tr_capitalize(text: str) -> str:
    """İlk harfi Türkçe kurallarına göre büyütür (i → İ)."""
    if not text:
        return text
    first = "İ" if text[0] == "i" else text[0].upper()
    return first + text[1:]


def build_messages(system: str, examples: list, text: str) -> list:
    messages = [{"role": "system", "content": system}]
    for en, tr in examples:
        messages.append({"role": "user", "content": en})
        messages.append({"role": "assistant", "content": tr})
    messages.append({"role": "user", "content": text})
    return messages


def call_with_retries(messages: list, validate, retries: int = 3) -> str:
    """Ollama'ya istek atar; validate(yanıt) -> (sonuç, hata) ile kontrol eder, gerekirse tekrar dener."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
            result, last_error = validate(clean_translation(content))
            if result is not None:
                return result
        except requests.RequestException as e:
            last_error = str(e)
        print(f"  [deneme {attempt}/{retries} başarısız: {last_error}]", file=sys.stderr)
        if attempt < retries:
            time.sleep(2)

    raise RuntimeError(f"Çeviri başarısız oldu ({retries} deneme sonrası): {last_error}")


def translate_clause(task: str, is_python: bool) -> str:
    """Şablon modu: görev kısmını sıfat-fiil öbeğine çevirip kalıbın içine yerleştirir."""

    def validate(clause):
        clause = _CLAUSE_TAIL_RE.sub("", clause).rstrip(" .")
        if not clause:
            return None, "Boş yanıt döndü"
        if "\n" in clause:
            return None, f"Çok satırlı yanıt döndü: {clause[:80]!r}"
        if not _CLAUSE_END_RE.search(clause.split()[-1]):
            return None, f"Öbek -an/-en ile bitmiyor: {clause[:80]!r}"
        return clause, None

    clause = call_with_retries(build_messages(CLAUSE_SYSTEM_PROMPT, CLAUSE_EXAMPLES, task), validate)
    function_word = "Python fonksiyonu" if is_python else "fonksiyon"
    return tr_capitalize(f"{clause} bir {function_word} yazın.")


def translate_full(text: str) -> str:
    """Serbest mod: cümlenin tamamını örnekli prompt ile çevirir."""
    source_is_single_line = "\n" not in text.strip()

    def validate(translation):
        if not translation:
            return None, "Boş yanıt döndü"
        if source_is_single_line and "\n" in translation:
            # Tek satırlık kaynağa çok satırlı yanıt: büyük ihtimalle açıklama/alternatif eklenmiş
            return None, f"Çok satırlı yanıt döndü: {translation[:80]!r}"
        return translation, None

    return call_with_retries(build_messages(FULL_SYSTEM_PROMPT, FULL_EXAMPLES, text), validate)


def translate_text(text: str) -> str:
    """Şablona uyan tek cümlelik görevleri şablon moduyla, diğerlerini serbest modla çevirir."""
    m = TEMPLATE_RE.match(text)
    # Görev kısmında başka cümle varsa ("... list. The function should ...") şablon uygulanmaz
    if m and not re.search(r"[.!?]\s+\S", m.group("task")):
        try:
            return translate_clause(m.group("task"), bool(m.group("python")))
        except RuntimeError as e:
            print(f"  Şablon modu başarısız, serbest moda geçiliyor: {e}", file=sys.stderr)
    return translate_full(text)


# --- DeepL -----------------------------------------------------------------
# API anahtarı DEEPL_API_KEY ortam değişkeninden okunur. ":fx" ile biten
# anahtarlar ücretsiz katmana aittir (ayda 500.000 karakter).

DEEPL_CONTEXT = "Python programming task description from a coding benchmark."

# Sözlük: DeepL'in terimleri tutarlı çevirmesi için (örn. string → "dize" yerine "string")
DEEPL_GLOSSARY = {
    "function": "fonksiyon",
    "functions": "fonksiyonlar",
    "input": "girdi",
    "list": "liste",
    "lists": "listeler",
    "tuple": "demet",
    "tuples": "demetler",
    "dictionary": "sözlük",
    "string": "string",
    "strings": "string'ler",
    "array": "dizi",
    "integer": "tam sayı",
    "integers": "tam sayılar",
    "digit": "rakam",
    "digits": "rakamlar",
    "element": "eleman",
    "elements": "elemanlar",
    "substring": "alt string",
    "substrings": "alt string'ler",
    "sublist": "alt liste",
    "sublists": "alt listeler",
    "lowercase": "küçük harf",
    "uppercase": "büyük harf",
}


class DeepLQuotaExceeded(Exception):
    """Aylık karakter kotası doldu; çalıştırma durdurulmalı."""


class DeepLClient:
    def __init__(self, api_key: str):
        self.base_url = "https://api-free.deepl.com" if api_key.endswith(":fx") else "https://api.deepl.com"
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"DeepL-Auth-Key {api_key}"
        self.glossary_id = None

    def _request(self, method: str, path: str, retries: int = 5, **kwargs) -> dict:
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.request(method, self.base_url + path, timeout=60, **kwargs)
                if resp.status_code == 456:
                    # 456 hem karakter kotası hem sözlük sayısı sınırı için dönüyor
                    if "glossar" in resp.text.lower():
                        raise RuntimeError(f"DeepL sözlük sınırı: {resp.text[:200]}")
                    raise DeepLQuotaExceeded("DeepL aylık karakter kotası doldu")
                if resp.status_code == 403:
                    raise RuntimeError("DeepL API anahtarı geçersiz (403)")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                else:
                    if resp.status_code >= 400:
                        raise RuntimeError(f"DeepL hatası HTTP {resp.status_code}: {resp.text[:200]}")
                    return resp.json() if resp.content else {}
            except requests.RequestException as e:
                last_error = str(e)
            wait = 2 ** attempt
            print(f"  [DeepL deneme {attempt}/{retries} başarısız: {last_error}, {wait}s bekleniyor]",
                  file=sys.stderr)
            time.sleep(wait)
        raise RuntimeError(f"DeepL isteği başarısız oldu ({retries} deneme sonrası): {last_error}")

    def usage(self) -> dict:
        return self._request("GET", "/v2/usage")

    def ensure_glossary(self, entries: dict) -> None:
        """Sözlüğü oluşturur; aynı içerikli sözlük hesapta zaten varsa onu kullanır.

        Ücretsiz katman tek sözlüğe izin verdiği için bu script'in oluşturduğu
        eski sürümler ("mbpp-tr-" önekli) yenisi kurulmadan önce silinir.
        """
        tsv = "\n".join(f"{src}\t{tgt}" for src, tgt in entries.items())
        name = "mbpp-tr-" + hashlib.sha256(tsv.encode("utf-8")).hexdigest()[:8]
        try:
            for g in self._request("GET", "/v2/glossaries").get("glossaries", []):
                if g["name"] == name and g["source_lang"] == "en" and g["target_lang"] == "tr":
                    self.glossary_id = g["glossary_id"]
                    return
                if g["name"].startswith("mbpp-tr-"):
                    print(f"Eski sözlük siliniyor: {g['name']}")
                    self._request("DELETE", f"/v2/glossaries/{g['glossary_id']}")
            created = self._request("POST", "/v2/glossaries", json={
                "name": name, "source_lang": "en", "target_lang": "tr",
                "entries": tsv, "entries_format": "tsv",
            })
            self.glossary_id = created["glossary_id"]
        except RuntimeError as e:
            print(f"Uyarı: DeepL sözlüğü oluşturulamadı, sözlüksüz devam ediliyor: {e}", file=sys.stderr)

    def translate(self, text: str, source_lang: str, target_lang: str, use_glossary: bool = True) -> str:
        body = {
            "text": [text],
            "source_lang": source_lang,
            "target_lang": target_lang,
            "context": DEEPL_CONTEXT,
            "model_type": "quality_optimized",
            "formality": "prefer_more",  # "yazın" gibi resmi hitap
        }
        if use_glossary and self.glossary_id:
            body["glossary_id"] = self.glossary_id
        translation = self._request("POST", "/v2/translate", json=body)["translations"][0]["text"].strip()
        if not translation:
            raise RuntimeError("DeepL boş yanıt döndü")
        return translation


# --- Geri çeviri kontrolü --------------------------------------------------
# Çeviri İngilizceye geri çevrilir ve orijinalle karşılaştırılır. Amaç çeviriyi
# düzeltmek değil, anlamı kaymış olabilecek satırları elle incelemek için işaretlemek.

BACK_SYSTEM_PROMPT = (
    "You are a translator. Translate the given Turkish programming task description "
    "into English as literally as possible. Do NOT fix, complete or improve the meaning; "
    "if something is missing or wrong in the Turkish text, keep it missing or wrong. "
    "Return only the translation."
)

JUDGE_SYSTEM_PROMPT = (
    "You compare two English programming task descriptions, A and B. Decide whether "
    "a programmer would implement exactly the same function for both.\n"
    "Check carefully: numbers and multipliers (twice, half), comparisons (less, more, "
    "largest, smallest), negations, conditions, return values, and which input plays which role.\n"
    "Ignore wording, word order and synonyms.\n"
    "Answer with SAME or DIFFERENT on the first line. If DIFFERENT, give a short reason on the second line."
)

# Kelime farklarını SAME, anlam farklarını DIFFERENT sayan örnekler
JUDGE_EXAMPLES = [
    ("A: Write a function to remove all whitespaces from the given string.\n"
     "B: Write a function that deletes all spaces in a given string.",
     "SAME"),
    ("A: Write a function to count the frequency of each element in a list.\n"
     "B: Write a function that counts how many times each item appears in a list.",
     "SAME"),
    ("A: Write a function to check if a number is three times its square root.\n"
     "B: Write a function that checks if a number is its square root.",
     "DIFFERENT\nB drops 'three times'."),
    ("A: Write a function to find the second largest number in a list.\n"
     "B: Write a function that finds the largest number in a list.",
     "DIFFERENT\nB asks for the largest instead of the second largest."),
    ("A: Write a function to sort a list of strings by their length.\n"
     "B: Write a function that sorts a list of strings alphabetically.",
     "DIFFERENT\nSort key differs: length vs alphabetical."),
]

# Çeviride düşmesi anlamı değiştiren kelimeler; orijinalde olup geri çeviride
# olmayanlar işaretlenir. Model yargısına ek olarak deterministik bir güvenlik ağı.
_KEY_TERMS = {
    "twice": ("twice", "double", "two times"),
    "half": ("half",),
    "triple": ("triple", "three times"),
    "not": ("not", "n't", "no ", "without"),
    "first": ("first",),
    "last": ("last", "final"),
    "second": ("second",),
    "less": ("less", "fewer", "smaller", "lower"),
    "greater": ("greater", "more", "larger", "bigger", "higher"),
    "even": ("even",),
    "odd": ("odd",),
    "ascending": ("ascending", "increasing"),
    "descending": ("descending", "decreasing"),
    "duplicate": ("duplicate", "repeat"),
    "maximum": ("maximum", "max", "largest", "greatest", "biggest"),
    "minimum": ("minimum", "min", "smallest", "least"),
}


def missing_key_terms(original: str, back: str) -> list:
    # "check if X or not" kalıbındaki "not" anlam taşımaz
    orig_l = " " + re.sub(r"\bor not\b", "", original.lower()) + " "
    back_l = f" {back.lower()} "
    missing = []
    for term, variants in _KEY_TERMS.items():
        in_orig = re.search(rf"\b{term}\b", orig_l) is not None
        if in_orig and not any(v in back_l for v in variants):
            missing.append(term)
    # Orijinaldeki sayılar geri çeviride de olmalı
    for num in set(re.findall(r"\b\d+\b", original)):
        if not re.search(rf"\b{num}\b", back):
            missing.append(num)
    return missing


def back_translate_ollama(translation: str) -> str:
    def non_empty(text):
        return (text, None) if text else (None, "Boş yanıt döndü")

    return call_with_retries(
        [{"role": "system", "content": BACK_SYSTEM_PROMPT}, {"role": "user", "content": translation}],
        non_empty,
    )


def review_translation(original: str, translation: str, back_translate=back_translate_ollama) -> dict:
    """Çeviriyi geri çevirip orijinalle karşılaştırır, inceleme kaydı döndürür.

    Geri çeviri motoru değiştirilebilir; karşılaştırma her zaman yerel modelle yapılır.
    """
    back = back_translate(translation)

    def parse_verdict(text):
        first, _, rest = text.partition("\n")
        verdict = first.strip().strip("*").upper()
        if verdict.startswith("SAME"):
            return ("SAME", ""), None
        if verdict.startswith("DIFFERENT"):
            return ("DIFFERENT", rest.strip()), None
        return None, f"Geçersiz karar: {text[:80]!r}"

    verdict, judge_reason = call_with_retries(
        build_messages(JUDGE_SYSTEM_PROMPT, JUDGE_EXAMPLES, f"A: {original}\nB: {back}"),
        parse_verdict,
    )

    reasons = []
    if verdict == "DIFFERENT":
        reasons.append(f"model: {judge_reason or 'farklı'}")
    missing = missing_key_terms(original, back)
    if missing:
        reasons.append(f"geri çeviride eksik: {', '.join(missing)}")
    return {"back_translation": back, "flagged": bool(reasons), "reasons": reasons}


def load_done_task_ids(out_path: Path) -> set:
    """Mevcut çıktı dosyasındaki task_id'leri döndürür.

    Önceki çalıştırma yazma sırasında kesildiyse dosyanın sonundaki yarım
    satır kesilip atılır; aksi halde append edilen yeni kayıt bozulurdu.
    """
    if not out_path.exists():
        return set()

    raw = out_path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        cut = raw.rfind(b"\n") + 1
        print(f"Uyarı: {out_path} sonunda yarım satır bulundu, siliniyor.", file=sys.stderr)
        raw = raw[:cut]
        out_path.write_bytes(raw)

    done = set()
    for line_no, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            done.add(json.loads(line)["task_id"])
        except (json.JSONDecodeError, KeyError):
            print(f"Uyarı: {out_path}:{line_no} okunamadı, yok sayılıyor.", file=sys.stderr)
    return done


def load_approved_translations(patterns: list) -> dict:
    """Daha önce onaylanmış çevirileri task_id → {prompt_en, prompt_tr, reviewer} olarak yükler.

    Taslak dosyaları (ör. data/mbpp_tr_test.jsonl) verilir; onaylar yanlarındaki
    .decisions.json dosyalarından okunur.
    """
    approved = {}
    for pattern in patterns:
        for path in sorted(Path(p) for p in glob.glob(pattern)):
            decisions_path = path.with_name(path.name + ".decisions.json")
            if not path.name.endswith(".jsonl") or not decisions_path.exists():
                continue
            decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    d = decisions.get(str(r["task_id"]))
                    if d and d["status"] == "approved":
                        approved[r["task_id"]] = {
                            "prompt_en": r["prompt_en"],
                            "prompt_tr": d["final_tr"],
                            "reviewer": d.get("reviewer") or "human",
                            "source": path.name,
                        }
    return approved


def save_reused_decisions(out_path: Path, reused: dict) -> None:
    """Yeniden kullanılan çevirileri çıktının karar dosyasına onaylı olarak ekler (mevcut kararlara dokunmaz)."""
    if not reused:
        return
    decisions_path = out_path.with_name(out_path.name + ".decisions.json")
    decisions = (json.loads(decisions_path.read_text(encoding="utf-8"))
                 if decisions_path.exists() else {})
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    for task_id, src in reused.items():
        decisions.setdefault(str(task_id), {
            "status": "approved",
            "final_tr": src["prompt_tr"],
            "draft_tr": src["prompt_tr"],
            "edited": False,
            "note": f"İngilizce metni birebir aynı olan onaylı çeviriden alındı: {src['source']}",
            "reviewer": src["reviewer"],
            "reused_from": src["source"],
            "updated_at": now,
        })
    tmp = decisions_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(sorted(decisions.items(), key=lambda kv: int(kv[0]))),
                              ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, decisions_path)


def main():
    parser = argparse.ArgumentParser(description="MBPP dataset'ini Türkçe'ye çevirir")
    parser.add_argument("--start", type=int, default=0, help="Başlangıç index'i")
    parser.add_argument("--end", type=int, default=None, help="Bitiş index'i (dahil değil)")
    parser.add_argument("--out", type=str, required=True, help="Çıktı JSONL dosya yolu")
    parser.add_argument("--split", type=str, default="sanitized", choices=["sanitized", "full"],
                        help="MBPP config'i (sanitized/full)")
    parser.add_argument("--hf-split", type=str, default="test",
                        choices=["train", "test", "validation", "prompt"],
                        help="HF dataset split'i")
    parser.add_argument("--overwrite", action="store_true",
                        help="Mevcut çıktı dosyasını silip baştan başla")
    parser.add_argument("--no-review", action="store_true",
                        help="Geri çeviri kontrolünü atla")
    parser.add_argument("--engine", type=str, default="deepl", choices=["deepl", "ollama"],
                        help="Çeviri motoru (deepl için DEEPL_API_KEY ortam değişkeni gerekir)")
    parser.add_argument("--reuse-from", nargs="+", default=[],
                        help="İngilizce metni birebir aynı satırlarda bu taslak dosyalarının onaylı "
                             "çevirilerini kullan (ör. \"data/mbpp_tr_*.jsonl\")")
    args = parser.parse_args()

    if args.start < 0:
        parser.error("--start negatif olamaz")

    if args.engine == "deepl":
        api_key = os.environ.get("DEEPL_API_KEY")
        if not api_key:
            parser.error("--engine deepl için DEEPL_API_KEY ortam değişkenini ayarlayın")
        deepl = DeepLClient(api_key)
        usage = deepl.usage()
        print(f"DeepL kullanımı: {usage.get('character_count', '?')} / "
              f"{usage.get('character_limit', '?')} karakter")
        deepl.ensure_glossary(DEEPL_GLOSSARY)
        print(f"DeepL sözlüğü: {deepl.glossary_id or 'yok'}")
        translate = lambda text: deepl.translate(text, "EN", "TR")
        # Geri çeviride sözlük kullanılmaz; sözlük yalnızca EN→TR yönünde tanımlı
        back_translate = lambda text: deepl.translate(text, "TR", "EN", use_glossary=False)
    else:
        translate = translate_text
        back_translate = back_translate_ollama

    print(f"MBPP dataset yükleniyor ({args.split}/{args.hf_split})...")
    ds = load_dataset("google-research-datasets/mbpp", args.split, split=args.hf_split)

    end = min(args.end if args.end is not None else len(ds), len(ds))
    if args.start >= end:
        print(f"Çevrilecek satır yok (start={args.start}, end={end}, dataset boyutu={len(ds)}).")
        return
    subset = ds.select(range(args.start, end))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    failed_path = out_path.with_name(out_path.name + ".failed.jsonl")
    review_path = out_path.with_name(out_path.name + ".review.jsonl")

    if args.overwrite:
        out_path.unlink(missing_ok=True)
        review_path.unlink(missing_ok=True)
    done_ids = load_done_task_ids(out_path)
    # Başarısızlar her çalıştırmada yeniden denendiği için liste de baştan tutulur
    failed_path.unlink(missing_ok=True)

    print(f"{len(subset)} satır ({args.start}-{end}), {len(done_ids)} tanesi zaten çevrilmiş. "
          f"Çıktı: {out_path}")

    approved = load_approved_translations(args.reuse_from)
    if args.reuse_from:
        print(f"Yeniden kullanılabilecek {len(approved)} onaylı çeviri yüklendi.")

    translated = skipped = flagged = 0
    failed = []
    reused = {}
    try:
        with out_path.open("a", encoding="utf-8") as f, review_path.open("a", encoding="utf-8") as rf:
            for i, row in enumerate(subset):
                task_id = row["task_id"]
                if task_id in done_ids:
                    skipped += 1
                    continue

                # 'sanitized' config'te alan adı 'prompt', 'full' config'te 'text'
                source_key = "prompt" if "prompt" in row else "text"
                source_text = row[source_key]
                # Çeviri dışındaki tüm orijinal alanlar (test_imports, test_setup_code vb.) korunur
                extra_fields = {k: v for k, v in row.items() if k not in ("task_id", source_key)}

                # İngilizce metin birebir aynıysa onaylı çeviri kullanılır; DeepL'e gönderilmez
                prior = approved.get(task_id)
                if prior and prior["prompt_en"].strip() == source_text.strip():
                    record = {"task_id": task_id, "prompt_en": source_text, "prompt_tr": prior["prompt_tr"]}
                    record.update(extra_fields)
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    reused[task_id] = prior
                    continue

                print(f"[{i + 1}/{len(subset)}] task_id={task_id} çevriliyor...")

                try:
                    prompt_tr = normalize_tr(translate(source_text))
                except DeepLQuotaExceeded as e:
                    print(f"  DURDURULDU: {e}. Kalan satırlar için kota yenilenince aynı komutu çalıştırın.",
                          file=sys.stderr)
                    break
                except RuntimeError as e:
                    print(f"  HATA, atlanıyor: {e}", file=sys.stderr)
                    failed.append({"task_id": task_id, "error": str(e)})
                    continue

                record = {"task_id": task_id, "prompt_en": source_text, "prompt_tr": prompt_tr}
                record.update(extra_fields)

                if not args.no_review:
                    try:
                        review = review_translation(source_text, prompt_tr, back_translate)
                    except (RuntimeError, DeepLQuotaExceeded) as e:
                        # Kontrol yapılamadıysa çeviri yine kaydedilir ama incelemeye düşer
                        review = {"back_translation": None, "flagged": True,
                                  "reasons": [f"kontrol başarısız: {e}"]}
                    if review["flagged"]:
                        flagged += 1
                        print(f"  İŞARETLENDİ: {'; '.join(review['reasons'])}")
                    review_record = {"task_id": task_id, "prompt_en": source_text, "prompt_tr": prompt_tr}
                    review_record.update(review)
                    rf.write(json.dumps(review_record, ensure_ascii=False) + "\n")
                    rf.flush()

                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()  # her satırdan sonra diske yaz, kesinti olursa veri kaybolmasın
                translated += 1
    finally:
        # Kota dolması veya Ctrl+C durumunda da yeniden kullanılan satırların onayları kaydedilsin
        save_reused_decisions(out_path, reused)

    # Geri çeviri kapalıyken boş kalan inceleme dosyası bırakılmaz
    if review_path.exists() and review_path.stat().st_size == 0:
        review_path.unlink()

    if failed:
        with failed_path.open("w", encoding="utf-8") as ff:
            for item in failed:
                ff.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\nTamamlandı. Çevrilen: {translated}, onaylı çeviriden alınan: {len(reused)}, "
          f"zaten var: {skipped}, başarısız: {len(failed)}")
    print(f"Sonuçlar: {out_path}")
    if not args.no_review:
        print(f"İnceleme gereken: {flagged} satır ({review_path}). "
              f"Görmek için: python spot_check.py {out_path} --flagged")
    if failed:
        print(f"Başarısız task_id'ler: {failed_path} "
              f"(aynı komutu tekrar çalıştırınca yeniden denenir)")


if __name__ == "__main__":
    main()
