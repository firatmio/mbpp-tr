# MBPP-TR

[MBPP (Mostly Basic Python Problems)](https://huggingface.co/datasets/google-research-datasets/mbpp)
veri setinin Türkçe çevirisi ve bu çeviriyi üretmek, incelemek ve doğrulamak için kullanılan araçlar.

- **Veri seti:** https://huggingface.co/datasets/firatmio/mbpp-tr
- **Veri seti kartı:** [data/final/README.md](data/final/README.md)

| Config | Satır | Durum |
|---|---|---|
| `sanitized` | 427 | Yayımlandı (`data/final/sanitized/`) |
| `full` | 974 | Yayımlandı (`data/final/full/`) |

```python
from datasets import load_dataset

sanitized = load_dataset("firatmio/mbpp-tr")          # varsayılan
full = load_dataset("firatmio/mbpp-tr", "full")
```

## Süreç

```
MBPP (Hugging Face)
   │  translate_mbpp.py   DeepL taslağı + sözlük + otomatik düzeltmeler (tr_rules.py)
   ▼
data/.../mbpp_tr_<split>.jsonl                  taslaklar
   │  review_tool.py      satır satır onay / düzeltme
   ▼
data/.../mbpp_tr_<split>.jsonl.decisions.json   kararlar
   │  review_tool.py --export-dir
   ▼
data/final/<config>/mbpp_tr_<split>.jsonl       yalnızca onaylı satırlar
   │  validate_final.py   orijinalle karşılaştırma + testleri çalıştırma
   ▼
Hugging Face
```

## Kurulum

```bash
pip install -r requirements.txt
```

Çeviri için bir [DeepL API](https://www.deepl.com/pro-api) anahtarı gerekir. Ücretsiz katman ayda
500.000 karakter verir; MBPP'nin tamamı (sanitized + full) yaklaşık 116.000 karakterdir.
Anahtarı proje kökündeki `.env` dosyasına yazın (bu dosya `.gitignore`'dadır):

```
DEEPL_API_KEY="anahtarınız:fx"
```

Terminalde `DEEPL_API_KEY` ortam değişkeni ayarlıysa `.env` yerine o kullanılır.

[Ollama](https://ollama.com) yalnızca isteğe bağlı iki özellik için gerekir: yerel modelle çeviri
(`--engine ollama`) ve geri çeviri kontrolü. İkisi de varsayılan akışta kullanılmaz.

## 1. Çeviri

Her split ayrı çevrilir:

```bash
# sanitized
python translate_mbpp.py --hf-split test --out data/mbpp_tr_test.jsonl --no-review

# full: İngilizce metni sanitized ile birebir aynı olan satırlar onaylı çeviriden alınır
python translate_mbpp.py --split full --hf-split test --out data/full/mbpp_tr_test.jsonl \
    --no-review --reuse-from "data/mbpp_tr_*.jsonl"
```

| Argüman | Varsayılan | Açıklama |
|---|---|---|
| `--split` | `sanitized` | MBPP config'i: `sanitized` (427 satır) veya `full` (974 satır) |
| `--hf-split` | `test` | `train`, `test`, `validation` veya `prompt` |
| `--out` | (zorunlu) | Taslak JSONL dosyası |
| `--start` / `--end` | tümü | Çevrilecek index aralığı (`end` dahil değil) |
| `--reuse-from` | yok | Onaylı çevirileri yeniden kullanılacak taslak dosyaları (joker karakter kullanılabilir) |
| `--no-review` | kapalı | Geri çeviri kontrolünü atlar (önerilir; aşağıya bakın) |
| `--engine` | `deepl` | `deepl` veya `ollama` |
| `--overwrite` | kapalı | Mevcut çıktıyı silip baştan başlar |

- **Kaldığı yerden devam:** Aynı `--out` ile tekrar çalıştırınca zaten çevrilmiş satırlar atlanır.
  Çevrilemeyenler `<out>.failed.jsonl` dosyasına yazılır ve sonraki çalıştırmada yeniden denenir.
  DeepL kotası dolarsa script temiz şekilde durur.
- **Sözlük:** Terim tutarlılığı için DeepL hesabında bir sözlük (glossary) oluşturulur
  (function → fonksiyon, tuple → demet, digit → rakam…). Ücretsiz katman tek sözlüğe izin verdiği
  için içerik değişince script'in oluşturduğu eski `mbpp-tr-*` sözlüğü silinip yenisi kurulur.
- **Otomatik düzeltmeler:** Anlamı değiştirmeyen düzeltmeler çeviriden sonra uygulanır
  (string'i/string'de kesme işareti, "yazınız" → "yazın" gibi). Kurallar [tr_rules.py](tr_rules.py) dosyasındadır;
  bağlantıların içine dokunulmaz.
- **Geri çeviri kontrolü:** `--no-review` verilmezse her çeviri İngilizceye geri çevrilip yerel bir
  modelle orijinalle karşılaştırılır. Sanitized çevirisinde çok yanlış alarm verdiği ve gerçek
  hataları kaçırdığı görüldü; inceleme adımının yerini tutmaz.

## 2. İnceleme

```bash
python review_tool.py data/mbpp_tr_test.jsonl data/mbpp_tr_train.jsonl data/mbpp_tr_validation.jsonl data/mbpp_tr_prompt.jsonl
```

Tarayıcıda bir onay arayüzü açılır:

- İngilizce metin, düzenlenebilir Türkçe taslak, kod ve testler bir arada gösterilir.
- Terim ve yazım uyarıları siz yazarken güncellenir.
- <kbd>Ctrl</kbd>+<kbd>Enter</kbd> onaylar ve sonraki satıra geçer; <kbd>Alt</kbd>+<kbd>S</kbd> notla birlikte "sorunlu" işaretler;
  <kbd>Alt</kbd>+<kbd>←</kbd>/<kbd>→</kbd> satırlar arasında gezinir.
- Birden fazla dosya verilirse üstteki menüden seçilir. Filtreler: bekleyenler, otomatik uyarılılar,
  sorunlular, onaylılar, Claude'un onayladıkları.
- Kararlar her işlemde `<dosya>.decisions.json` dosyasına yazılır; araç kapatılıp açılınca kaldığı yerden devam eder.
  Her kararda kimin incelediği (`reviewer`: `human`, `claude`, `human+claude`) saklanır.
  Zaten onaylı bir satırı metnini ve notunu değiştirmeden tekrar onaylamak hiçbir şey kaydetmez;
  böylece hızla geçilen satırlar "insan inceledi" olarak yeniden etiketlenmez.

**Aynı ağdaki başka bir bilgisayardan:** `--host 0.0.0.0` ekleyin. Araç, gizli bir token içeren adresi
terminale yazar; token olmadan erişim reddedilir. Windows güvenlik duvarında yalnızca **Özel ağ** için
izin verin. Aynı satır iki yerden değiştirilirse ikinci kayıt reddedilir ve sayfa güncel hali yükler.

> Araç açıkken karar dosyalarını başka bir yoldan (script vb.) değiştirmeyin; araç hafızasındaki
> kararlarla dosyanın üzerine yazabilir.

## 3. Dışa aktarma

```bash
# sanitized
python review_tool.py data/mbpp_tr_test.jsonl data/mbpp_tr_train.jsonl data/mbpp_tr_validation.jsonl data/mbpp_tr_prompt.jsonl --export-dir data/final/sanitized

# full
python review_tool.py data/full/mbpp_tr_test.jsonl data/full/mbpp_tr_train.jsonl data/full/mbpp_tr_validation.jsonl data/full/mbpp_tr_prompt.jsonl --export-dir data/final/full
```

Yalnızca onaylanmış satırlar, onaylanan Türkçe metinle yazılır. Onaylanmamış satır kalırsa uyarı verilir.

## 4. Doğrulama

```bash
python validate_final.py data/final/sanitized --split sanitized
python validate_final.py data/final/full --split full
```

Nihai dosyalar orijinal MBPP ile karşılaştırılır. Şunlar hata sayılır ve script 1 koduyla çıkar:

- eksik, fazla veya tekrar eden `task_id`
- `prompt_en` veya çeviri dışındaki herhangi bir alanın orijinalden farklı olması
- boş çeviri, bozulmuş bağlantı
- orijinalde geçen bir testin çeviride başarısız olması (her satırın `code`'u kendi testleriyle ayrı bir süreçte çalıştırılır)

## 5. Yayınlama

```bash
hf upload firatmio/mbpp-tr data/final . --repo-type dataset
```

Veri seti kartı (`data/final/README.md`) iki config'i ve split'lerini dosyalarla eşleştirir; alan
türleri de kartta (`dataset_info`) açıkça tanımlıdır. Bu tanım olmadan, çoğu satırda boş olan liste
alanları yüzünden `load_dataset` hata verir. Alan eklenir veya değişirse kart da güncellenmelidir.
Yüklemeden önce yerelde deneyin:

```bash
python -c "from datasets import load_dataset; print(load_dataset('data/final', 'full'))"
```

Kartta değişiklik yapılırsa hem bu repoya commit edilmeli hem de Hugging Face'e yüklenmelidir.

## Dosya yapısı

| Yol | İçerik |
|---|---|
| `translate_mbpp.py` | Çeviri |
| `tr_rules.py` | Otomatik düzeltmeler ve inceleme uyarıları |
| `review_tool.py`, `review_ui.html` | Onay aracı |
| `validate_final.py` | Doğrulama |
| `spot_check.py` | Taslaklardan rastgele örnek gösterme |
| `data/mbpp_tr_<split>.jsonl` | Sanitized taslakları ve kararları (inceleme geçmişi) |
| `data/full/` | Full config taslakları ve kararları |
| `data/final/sanitized/`, `data/final/full/` | Yayımlanan veri seti |
| `data/final/README.md` | Veri seti kartı |

## Veri formatı

```json
{
  "task_id": 11,
  "prompt_en": "Write a python function to remove first and last occurrence of a given character from the string.",
  "prompt_tr": "Verilen bir karakterin bir string'deki ilk ve son geçtiği yerleri kaldıran bir Python fonksiyonu yazın.",
  "code": "def remove_Occ(s,ch): ...",
  "source_file": "Benchmark Questions Verification V2.ipynb",
  "test_imports": [],
  "test_list": ["assert remove_Occ(\"hello\",\"l\") == \"heo\"", "..."]
}
```

`prompt_en`/`prompt_tr` dışındaki tüm alanlar orijinal MBPP'den değişmeden aktarılır. `full` config'inde
`test_imports` yerine `test_setup_code` ve `challenge_test_list` alanları bulunur.

## Lisans

Bu proje, CC-BY-4.0 lisanslı [MBPP](https://huggingface.co/datasets/google-research-datasets/mbpp) veri setinin
türetilmiş bir çalışmasıdır ve CC-BY-4.0 ile yayımlanır. Kullanırken orijinal çalışmaya
([Austin et al., 2021](https://arxiv.org/abs/2108.07732)) atıf yapınız.
