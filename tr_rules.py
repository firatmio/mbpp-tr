"""
Türkçe çeviriler için ortak kurallar: otomatik düzeltmeler ve inceleme uyarıları.

translate_mbpp.py çeviriden sonra normalize_tr() uygular;
review_tool.py her satır için check() uyarılarını gösterir.
"""

import re

_TR_LOWER = "a-zçğıöşü"

# Türkçe cins isimler: eklerinden kesme işaretiyle ayrılmaz ("demet'te" değil "demette")
_TR_NOUNS = r"(?:[Dd]emet|[Ll]iste|[Ss]özlük|[Kk]üme|[Dd]izi|[Ee]leman|[Ss]ayı|[Ff]onksiyon|[Rr]akam|[Kk]arakter|[Kk]elime|[Cc]ümle|[Mm]atris)"


_URL_RE = re.compile(r"https?://\S+")


def _outside_urls(text: str, fn) -> str:
    """fn'i yalnızca URL olmayan parçalara uygular; URL'ler olduğu gibi kalır."""
    parts, last = [], 0
    for m in _URL_RE.finditer(text):
        parts.append(fn(text[last:m.start()]))
        parts.append(m.group())
        last = m.end()
    parts.append(fn(text[last:]))
    return "".join(parts)


def _normalize_fragment(text: str) -> str:
    # "stringi", "stringde" → "string'i", "string'de" (kesme işareti tutarlılığı).
    # İngilizce çoğul "strings" hariç tutulur.
    text = re.sub(rf"\b([Ss]tring)(?!s\b)(?=[{_TR_LOWER}])", r"\1'", text)
    # "demet'te" → "demette"; ekin kendisi değişmediği için kesmeyi silmek yeterli
    text = re.sub(rf"\b({_TR_NOUNS})'(?=[{_TR_LOWER}])", r"\1", text)
    # Hitap tutarlılığı: DeepL bazen "yazınız" üretiyor, veri setinde "yazın" kullanılıyor
    text = re.sub(r"\byazınız\b", "yazın", text)
    return text


def normalize_tr(text: str) -> str:
    """Anlamı değiştirmeyen, güvenle otomatik yapılabilecek düzeltmeler."""
    return _outside_urls(text, _normalize_fragment)


# (desen, uyarı) — eşleşme hata demek değil, incelerken bakılması gereken yer demek
LINT_RULES = [
    (r"\b[İi]şlev", "Terim: 'işlev' yerine 'fonksiyon' kullanın."),
    (r"\b[Tt]amsayı", "Yazım: 'tamsayı' yerine 'tam sayı'."),
    (r"\b[Bb]asamak", "Terim: 'digit' kastediliyorsa 'rakam' olmalı."),
    (r"\b[Dd]ize", "Terim: 'dize' yerine 'string' kullanın (alt dize → alt string)."),
    (r"\b[Dd]izgi|\b[Dd]izge", "Terim: 'dizgi/dizge' yerine 'string' kullanın."),
    (r"\bk'nc", "Yazım: 'k'ncı' yerine 'k'ıncı'."),
    (r"\bsözlükü\b", "Yazım: 'sözlükü' yerine 'sözlüğü'."),
    (r"(?<!\()\b[Tt]uple", "Terim: 'tuple' yerine 'demet' kullanın ('demet (tuple)' şeklindeki açıklama serbest)."),
    (rf"\b{_TR_NOUNS}'(?=[{_TR_LOWER}])", "Yazım: Türkçe kelimeye kesme işareti gelmez (demet'te → demette)."),
    (r"\b[Gg]eçim", "Kelime hatası: 'geçim' yaşam/geçinme demek; 'occurrence' için 'geçtiği yer' veya 'tekrar' olmalı."),
    (r"\b[Gg]eçiş","Doğallık: 'occurrence' için 'geçtiği yer' veya 'tekrar' gibi bir ifade daha doğal."),
    (r"\b[Gg]iriş\b|\b[Gg]iriş(?:i|in|e|te|ten)\b", "Terim: 'input' için 'girdi' kullanın."),
    (rf"\b[Ss]tring(?=[{_TR_LOWER}])", "Yazım: 'string' ile ek arasında kesme işareti olmalı (string'i)."),
    (r"\byazın ki\b", "Doğallık: 'Bir fonksiyon yazın ki…' İngilizce kalıbı."),
]


def check(en: str, tr: str) -> list:
    """İnceleme uyarılarını döndürür."""
    # Kurallar URL'lerin içindeki kelimelere (ör. .../tuple-list/) takılmasın
    tr_text = _URL_RE.sub(" ", tr)
    warnings = [msg for pattern, msg in LINT_RULES if re.search(pattern, tr_text)]

    for url in _URL_RE.findall(en):
        if url not in tr:
            warnings.append(f"Kaynaktaki bağlantı çeviride aynen geçmiyor: {url}")

    if not tr.strip():
        warnings.append("Çeviri boş.")
        return warnings

    # Kaynaktaki sayılar çeviride de olmalı
    en_text = _URL_RE.sub(" ", en)
    missing_nums = sorted(set(re.findall(r"\d+(?:\.\d+)?", en_text)) - set(re.findall(r"\d+(?:\.\d+)?", tr_text)))
    if missing_nums:
        warnings.append(f"Kaynaktaki sayılar çeviride yok: {', '.join(missing_nums)}")

    # Tırnak/backtick içindeki kod parçaları olduğu gibi kalmalı
    quoted = re.findall(r"`([^`]+)`|'([^'\s]{1,40})'|\"([^\"]{1,40})\"", en_text)
    for parts in quoted:
        token = next(p for p in parts if p)
        if token not in tr:
            warnings.append(f"Kaynaktaki '{token}' ifadesi çeviride aynen geçmiyor.")

    # Kaynaktaki snake_case / camelCase isimler çevrilmemeli
    for ident in set(re.findall(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b", en_text)):
        if ident not in tr:
            warnings.append(f"Kaynaktaki '{ident}' ismi çeviride aynen geçmiyor.")

    return warnings
