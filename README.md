# MBPP-TR

[MBPP (Mostly Basic Python Problems)](https://huggingface.co/datasets/google-research-datasets/mbpp) veri setinin
görev açıklamalarını Türkçeye çevirmek, çevirileri incelemek ve nihai veri setini doğrulamak için araçlar.

Yayımlanan veri seti `data/final/` klasöründedir; veri seti kartı (Hugging Face README'si)
[data/final/README.md](data/final/README.md) dosyasıdır.

## Neden

Türkçe kod-instruction veri seti kaynakları kısıtlı. Bu proje, İngilizce MBPP veri setini
temel alarak Türkçe soru → Python kodu formatında bir veri seti üretmeyi amaçlıyor.

## Kurulum

```bash
pip install -r requirements.txt
```

Geri çeviri kontrolü veya `--engine ollama` kullanılacaksa [Ollama](https://ollama.com)
kurulu ve çalışıyor olmalı, `gemma3:4b` modeli çekilmiş olmalı:

```bash
ollama pull gemma3:4b
```

### Çeviri motoru

Varsayılan motor [DeepL API](https://www.deepl.com/pro-api). Ücretsiz katman ayda
500.000 karakter veriyor; MBPP'nin tamamı (sanitized + full, tüm split'ler) yaklaşık
116.000 karakter, geri çeviri kontrolüyle yaklaşık 232.000 karakter tutuyor.
Anahtarı proje kökündeki `.env` dosyasına yazın (bu dosya `.gitignore`'da):

```
DEEPL_API_KEY="anahtarınız:fx"
```

Terminalde `DEEPL_API_KEY` ortam değişkeni ayarlıysa `.env` yerine o kullanılır.

Terimlerin tutarlı çevrilmesi için script DeepL hesabında bir sözlük (glossary) oluşturur.
Ücretsiz katman tek sözlüğe izin verdiği için sözlük içeriği değiştiğinde script'in
oluşturduğu eski `mbpp-tr-*` sözlüğü silinip yenisi kurulur.

Yerel model kullanmak için `--engine ollama`. Hangi motor seçilirse seçilsin,
geri çeviri karşılaştırması yerel Ollama modeliyle yapılır.

## Kullanım

```bash
# İlk 50 satırı çevir
python translate_mbpp.py --start 0 --end 50 --out data/mbpp_tr_part1.jsonl

# Kalite kontrolü - rastgele 10 örneği gözden geçir
python spot_check.py data/mbpp_tr_part1.jsonl --n 10
```

### Seçenekler

| Argüman | Varsayılan | Açıklama |
|---|---|---|
| `--split` | `sanitized` | MBPP config'i: `sanitized` (427 görev) veya `full` (974 görev) |
| `--hf-split` | `test` | `train`, `test`, `validation` veya `prompt` |
| `--start` / `--end` | tümü | Çevrilecek index aralığı (`end` dahil değil) |
| `--overwrite` | kapalı | Mevcut çıktıyı silip baştan başlar |
| `--engine` | `deepl` | Çeviri motoru: `deepl` veya `ollama` |
| `--no-review` | kapalı | Geri çeviri kontrolünü atlar |

### Geri çeviri kontrolü

Her çeviri aynı modelle İngilizceye geri çevrilir ve orijinalle karşılaştırılır
(model yargısı + "twice", "first", sayılar gibi kritik kelimelerin kontrolü).
Sonuçlar `<out>.review.jsonl` dosyasına yazılır. İşaretlenen satırları görmek için:

```bash
python spot_check.py data/mbpp_tr_part1.jsonl --flagged
```

Kontrol anlam kaymalarını yakalamak içindir; dilbilgisi hatalarını yakalamaz ve
yanlış alarm verebilir. Elle incelemenin yerini tutmaz.

Varsayılan ayarlar yalnızca `test` split'ini çevirir. Tüm veri seti için her split'i
ayrı ayrı çalıştırın:

```bash
python translate_mbpp.py --hf-split train --out data/mbpp_tr_train.jsonl
python translate_mbpp.py --hf-split validation --out data/mbpp_tr_validation.jsonl
python translate_mbpp.py --hf-split prompt --out data/mbpp_tr_prompt.jsonl
```

### Kesinti ve tekrar deneme

Aynı `--out` dosyasıyla komutu tekrar çalıştırırsanız zaten çevrilmiş `task_id`'ler
atlanır, script kaldığı yerden devam eder. Çevrilemeyen satırlar
`<out>.failed.jsonl` dosyasına yazılır ve bir sonraki çalıştırmada yeniden denenir.

## İnceleme ve onay

Otomatik çeviriler taslaktır; nihai veri setine yalnızca onaylanmış satırlar girer.
Onay aracı tarayıcıda açılır:

```bash
python review_tool.py data/mbpp_tr_test.jsonl
```

- İngilizce metin, düzenlenebilir Türkçe taslak, geri çeviri, kod ve testler bir arada gösterilir.
- Terim ve yazım uyarıları (`tr_rules.py`) siz yazarken güncellenir.
- <kbd>Ctrl</kbd>+<kbd>Enter</kbd> onaylar ve sonraki satıra geçer; <kbd>Alt</kbd>+<kbd>S</kbd> notla birlikte "sorunlu" işaretler.
- Kararlar her işlemde `<dosya>.decisions.json` dosyasına yazılır; araç kapatılıp açıldığında kaldığı yerden devam eder.

Birden fazla dosya verilirse arayüzde açılır menüden seçilir.

**Aynı ağdaki başka bir bilgisayardan inceleme:** `--host 0.0.0.0` ile başlatın. Araç,
adresi gizli bir token ile birlikte terminale yazar; token olmadan erişim reddedilir.
Windows ilk seferde güvenlik duvarı izni sorar, yalnızca **Özel ağ** için izin verin.
Aynı satır iki yerden değiştirilirse ikinci kayıt reddedilir ve sayfa güncel hali yükler.

```powershell
python review_tool.py data/mbpp_tr_test.jsonl data/mbpp_tr_train.jsonl data/mbpp_tr_validation.jsonl data/mbpp_tr_prompt.jsonl --host 0.0.0.0
```

Her kararda kimin incelediği (`reviewer`: `human`, `claude` veya `human+claude`) saklanır.

Onaylı satırları nihai veri setine aktarmak için:

```bash
python review_tool.py data/mbpp_tr_test.jsonl data/mbpp_tr_train.jsonl data/mbpp_tr_validation.jsonl data/mbpp_tr_prompt.jsonl --export-dir data/final
```

Yalnızca onaylanmış satırlar, onaylanan Türkçe metinle yazılır.

## Doğrulama

```bash
python validate_final.py data/final
```

Nihai dosyaları orijinal MBPP ile karşılaştırır: eksik/fazla/tekrar eden `task_id`,
orijinalden farklılaşmış alanlar, boş çeviriler ve bozulmuş bağlantılar hata sayılır.
Ayrıca her satırın `code`'u kendi testleriyle ayrı bir süreçte çalıştırılır.

## Veri Formatı

`sanitized` config'inden üretilen bir satır:

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

`prompt_en`/`prompt_tr` dışındaki tüm alanlar orijinal MBPP'den değişmeden aktarılır.
`sanitized` config'inde `test_imports`, `full` config'inde `test_setup_code` ve
`challenge_test_list` alanları da korunur. Testleri çalıştırırken bu alanları
kullanın, bazı testler bunlar olmadan hata verir.

## Lisans

Bu proje CC-BY-4.0 lisanslı [MBPP](https://huggingface.co/datasets/google-research-datasets/mbpp)
veri setinin türetilmiş bir çalışmasıdır. Orijinal kaynağa atıf zorunludur.
Bu repo da CC-BY-4.0 ile yayınlanmaktadır.

## Kalite Notu

Taslaklar makine çevirisidir. Yayımlanan satırların nasıl incelendiği (insan / Claude
dağılımı dahil) veri seti kartında belgelenmiştir.
