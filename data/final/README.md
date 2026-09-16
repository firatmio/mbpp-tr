---
license: cc-by-4.0
language:
- tr
- en
pretty_name: MBPP-TR
size_categories:
- 1K<n<10K
source_datasets:
- google-research-datasets/mbpp
task_categories:
- text-generation
tags:
- code
- python
- mbpp
- turkish
- program-synthesis
# Alan türleri açıkça tanımlı: çoğu satırda boş olan liste alanlarının (ör. test_imports)
# türü otomatik tahminde "null" çıkıp yüklemeyi bozmasın diye
dataset_info:
- config_name: sanitized
  features:
  - name: task_id
    dtype: int64
  - name: prompt_en
    dtype: string
  - name: prompt_tr
    dtype: string
  - name: source_file
    dtype: string
  - name: code
    dtype: string
  - name: test_imports
    sequence: string
  - name: test_list
    sequence: string
- config_name: full
  features:
  - name: task_id
    dtype: int64
  - name: prompt_en
    dtype: string
  - name: prompt_tr
    dtype: string
  - name: code
    dtype: string
  - name: test_list
    sequence: string
  - name: test_setup_code
    dtype: string
  - name: challenge_test_list
    sequence: string
configs:
- config_name: sanitized
  default: true
  data_files:
  - split: train
    path: sanitized/mbpp_tr_train.jsonl
  - split: test
    path: sanitized/mbpp_tr_test.jsonl
  - split: validation
    path: sanitized/mbpp_tr_validation.jsonl
  - split: prompt
    path: sanitized/mbpp_tr_prompt.jsonl
- config_name: full
  data_files:
  - split: train
    path: full/mbpp_tr_train.jsonl
  - split: test
    path: full/mbpp_tr_test.jsonl
  - split: validation
    path: full/mbpp_tr_validation.jsonl
  - split: prompt
    path: full/mbpp_tr_prompt.jsonl
---

# MBPP-TR

[MBPP (Mostly Basic Python Problems)](https://huggingface.co/datasets/google-research-datasets/mbpp)
veri setinin Türkçe çevirisi. Orijinal veri setindeki gibi iki config içerir: `sanitized` ve `full`.
Her satırda görev açıklamasının İngilizce aslı ve Türkçe çevirisi birlikte yer alır; kod ve testler
orijinal veri setinden değiştirilmeden aktarılmıştır.

*A Turkish translation of MBPP with both the `sanitized` and `full` configs. Each row contains the
original English task description and its Turkish translation; code and tests are copied unchanged
from the source.*

## Dataset Sources

- **Repository (çeviri, inceleme ve doğrulama araçları):** https://github.com/firatmio/mbpp-tr
- **Kaynak veri seti:** https://huggingface.co/datasets/google-research-datasets/mbpp
- **Kaynak makale:** [Program Synthesis with Large Language Models](https://arxiv.org/abs/2108.07732)

## Kullanım

```python
from datasets import load_dataset

sanitized = load_dataset("firatmio/mbpp-tr")          # varsayılan: sanitized
full = load_dataset("firatmio/mbpp-tr", "full")

print(sanitized["test"][0]["prompt_tr"])
```

## Config'ler ve split'ler

| Split | `sanitized` | `full` |
|---|---|---|
| train | 120 | 374 |
| test | 257 | 500 |
| validation | 43 | 90 |
| prompt | 7 | 10 |
| **Toplam** | **427** | **974** |

- **`sanitized`:** Orijinal yazarların elle gözden geçirip görev açıklamalarını netleştirdiği alt küme.
  Değerlendirmelerde en çok kullanılan config budur.
- **`full`:** Tüm görevler, orijinal (daha kısa ve bazen belirsiz) açıklamalarıyla.

Split'ler ve `task_id`'ler her iki config'de de orijinal MBPP ile birebir aynıdır. Aynı `task_id`'nin
İngilizce açıklaması iki config'de farklı olabildiği için Türkçe çevirileri de farklı olabilir.

## Alanlar

| Alan | Config | Tür | Açıklama |
|---|---|---|---|
| `task_id` | ikisi | int | Orijinal MBPP görev numarası |
| `prompt_en` | ikisi | string | Orijinal İngilizce görev açıklaması (`sanitized`'de `prompt`, `full`'da `text` alanı) |
| `prompt_tr` | ikisi | string | Türkçe görev açıklaması |
| `code` | ikisi | string | Orijinal çözüm kodu |
| `test_list` | ikisi | list[string] | `assert` ifadeleri olarak testler |
| `test_imports` | sanitized | list[string] | Testlerden önce çalıştırılması gereken import satırları |
| `source_file` | sanitized | string | Orijinal veri setindeki kaynak dosya bilgisi |
| `test_setup_code` | full | string | Testlerden önce çalıştırılması gereken kurulum kodu |
| `challenge_test_list` | full | list[string] | Ek (daha zor) testler |

Örnek (`sanitized`):

```json
{
  "task_id": 11,
  "prompt_en": "Write a python function to remove first and last occurrence of a given character from the string.",
  "prompt_tr": "Verilen bir karakterin bir string'deki ilk ve son geçtiği yerleri kaldıran bir Python fonksiyonu yazın.",
  "code": "def remove_Occ(s,ch): ...",
  "test_imports": [],
  "test_list": ["assert remove_Occ(\"hello\",\"l\") == \"heo\"", "..."],
  "source_file": "Benchmark Questions Verification V2.ipynb"
}
```

Bir satırın testlerini çalıştırmak için önce `test_imports` (sanitized) veya `test_setup_code` (full),
ardından `code` ve `test_list` çalıştırılmalıdır.

## Nasıl hazırlandı

1. **Taslak çeviri:** Görev açıklamaları DeepL API ile çevrildi. Terim tutarlılığı için bir DeepL
   sözlüğü kullanıldı (aşağıdaki terim tablosu) ve kesme işareti, hitap biçimi gibi anlamı
   değiştirmeyen düzeltmeler otomatik uygulandı.
2. **Yeniden kullanım (full):** `full` config'inde İngilizce açıklaması `sanitized` ile birebir aynı
   olan 189 satırda, `sanitized` için onaylanmış çeviri kullanıldı.
3. **Otomatik kontroller:** Her çeviri; terim hataları, kaynaktaki sayıların, bağlantıların ve kod
   isimlerinin korunması gibi kurallarla tarandı. `sanitized` test split'inde ayrıca geri çeviri
   (Türkçe → İngilizce) karşılaştırması yapıldı.
4. **İnceleme:** Her satır tek tek incelendi ve onaylandı ya da düzeltildi. İnceleme bir insan ve bir
   yapay zekâ modeli (Anthropic'in Claude modeli) tarafından paylaşıldı.

   **`sanitized`**

   | Split | Satır | DeepL taslağından düzeltilen | İnsan incelemesi | Yalnızca Claude incelemesi |
   |---|---|---|---|---|
   | train | 120 | 44 | 1 | 119 |
   | test | 257 | 115 | 163 | 94 |
   | validation | 43 | 13 | 0 | 43 |
   | prompt | 7 | 1 | 0 | 7 |
   | **Toplam** | **427** | **173** | **164** | **263** |

   **`full`**

   | Split | Satır | `sanitized`'den alınan | Yeni çevrilen | Yeni çevrilenlerden düzeltilen | İnsan incelemesi | Yalnızca Claude incelemesi |
   |---|---|---|---|---|---|---|
   | train | 374 | 44 | 330 | 114 | 0 | 374 |
   | test | 500 | 129 | 371 | 124 | 82 | 418 |
   | validation | 90 | 14 | 76 | 25 | 0 | 90 |
   | prompt | 10 | 2 | 8 | 6 | 0 | 10 |
   | **Toplam** | **974** | **189** | **785** | **269** | **82** | **892** |

   "İnsan incelemesi" sütunu, kararı bir insanın verdiği veya bir insanın onayladığı metinde Claude'un
   sonradan yazım düzeltmesi yaptığı satırları içerir. `full` config'inde bu satırların tamamı
   `sanitized`'den alınan çevirilerdir. **`sanitized`'de 263, `full`'da 892 satır yalnızca Claude
   tarafından incelenmiştir**; bu satırlar bir insan tarafından tek tek kontrol edilmemiştir.
5. **Doğrulama:** Nihai dosyalar orijinal MBPP ile karşılaştırıldı: tüm `task_id`'ler mevcut ve
   çeviri dışındaki bütün alanlar orijinalle birebir aynı. Her satırın kodu kendi testleriyle
   çalıştırıldı: `sanitized`'de 427/427, `full`'da 973/974 satır geçiyor. Geçmeyen tek satır
   (`full` test 180) orijinal MBPP'de de başarısızdır.

## Çeviri kuralları

| İngilizce | Türkçe |
|---|---|
| function | fonksiyon |
| list / tuple / dictionary / set | liste / demet / sözlük / küme |
| string | string (ek alırken kesme işaretiyle: string'i, string'de) |
| substring / sublist | alt string / alt liste |
| array | dizi |
| integer | tam sayı |
| digit | rakam (basamak sayısı kastedildiğinde "basamak") |
| element | eleman |
| input | girdi |
| recursion | özyineleme |
| set bit / unset bit | 1 olan bit / 0 olan bit |
| heap queue algorithm | heap kuyruğu algoritması |

- Görev cümleleri "… bulan bir fonksiyon yazın." gibi resmi hitapla çevrilmiştir.
- Fonksiyon/değişken isimleri, tırnak içindeki değerler, formüller ve bağlantılar olduğu gibi bırakılmıştır.

## Bilinen notlar

- **Kaynaktaki hatalar korunmuştur.** Örneğin "woodball" (Woodall sayısı), "lucid" (ludic
  sayıları) ve "from o to n" gibi yazım hataları, veri setinin aslına sadık kalması için
  düzeltilmemiştir.
- **Belirsiz kaynak metinler** anlamı değiştirmeden çevrilmiştir (ör. `sanitized` test 307 "get a
  colon of a tuple", test 259 "maximize the given two tuples"). Bu satırlarda anlamı netleştirmek
  için testlere bakılması önerilir.
- **`full` config'indeki bazı açıklamalarda kaynaktan gelen biçim kalıntıları vardır** (ör. test 118
  "[link text](https://…", test 111 ve 172 "* list item"). Bu kalıntılar da korunmuştur.
- `sanitized` train split'indeki bazı açıklamaların sonunda kaynak bağlantıları ve veri setini
  hazırlayanların notları bulunur (ör. train 753); bunlar da çevrilerek korunmuştur.
- Bir açıklama İngilizcede "print" dese de testler dönüş değerini kontrol edebilir; bu
  tutarsızlıklar orijinal veri setinden gelir.

## Lisans ve atıf

Bu veri seti, CC-BY-4.0 lisanslı
[google-research-datasets/mbpp](https://huggingface.co/datasets/google-research-datasets/mbpp)
veri setinin türetilmiş bir çalışmasıdır ve aynı lisansla (CC-BY-4.0) yayımlanır.
Kullanırken orijinal çalışmaya atıf yapınız:

```bibtex
@article{austin2021program,
  title   = {Program Synthesis with Large Language Models},
  author  = {Austin, Jacob and others},
  journal = {arXiv preprint arXiv:2108.07732},
  year    = {2021}
}
```
