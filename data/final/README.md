---
license: cc-by-4.0
language:
- tr
- en
pretty_name: MBPP-TR
size_categories:
- n<1K
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
configs:
- config_name: default
  data_files:
  - split: train
    path: mbpp_tr_train.jsonl
  - split: test
    path: mbpp_tr_test.jsonl
  - split: validation
    path: mbpp_tr_validation.jsonl
  - split: prompt
    path: mbpp_tr_prompt.jsonl
---

# MBPP-TR

[MBPP (Mostly Basic Python Problems)](https://huggingface.co/datasets/google-research-datasets/mbpp)
veri setinin **sanitized** alt kümesinin Türkçe çevirisi. Her satırda görev açıklamasının
İngilizce aslı ve Türkçe çevirisi birlikte yer alır; kod ve testler orijinal veri setinden
değiştirilmeden aktarılmıştır.

*A Turkish translation of the sanitized subset of MBPP. Each row contains the original English
task description and its Turkish translation; code and tests are copied unchanged from the source.*

## Kullanım

```python
from datasets import load_dataset

ds = load_dataset("firatmio/mbpp-tr")
print(ds["test"][0]["prompt_tr"])
```

## Split'ler

| Split | Satır |
|---|---|
| train | 120 |
| test | 257 |
| validation | 43 |
| prompt | 7 |
| **Toplam** | **427** |

Split'ler ve `task_id`'ler orijinal MBPP sanitized ile birebir aynıdır.

## Alanlar

| Alan | Tür | Açıklama |
|---|---|---|
| `task_id` | int | Orijinal MBPP görev numarası |
| `prompt_en` | string | Orijinal İngilizce görev açıklaması |
| `prompt_tr` | string | Türkçe görev açıklaması |
| `code` | string | Orijinal çözüm kodu |
| `test_imports` | list[string] | Testlerden önce çalıştırılması gereken import satırları |
| `test_list` | list[string] | `assert` ifadeleri olarak testler |
| `source_file` | string | Orijinal veri setindeki kaynak dosya bilgisi |

Örnek:

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

Bir satırın testlerini çalıştırmak için `test_imports`, `code` ve `test_list` sırayla
çalıştırılmalıdır; bazı testler `test_imports` olmadan hata verir.

## Nasıl hazırlandı

1. **Taslak çeviri:** Görev açıklamaları DeepL API ile çevrildi. Terim tutarlılığı için
   bir DeepL sözlüğü kullanıldı (aşağıdaki terim tablosu) ve kesme işareti, hitap biçimi gibi
   anlamı değiştirmeyen düzeltmeler otomatik uygulandı.
2. **Otomatik kontroller:** Her çeviri; terim hataları, kaynaktaki sayıların, bağlantıların ve
   kod isimlerinin korunması gibi kurallarla tarandı. Test split'inde ayrıca geri çeviri
   (Türkçe → İngilizce) karşılaştırması yapıldı.
3. **İnceleme:** Her satır tek tek incelendi ve onaylandı ya da düzeltildi. İnceleme bir insan
   ve bir yapay zekâ modeli (Anthropic'in Claude modeli) tarafından paylaşıldı:

   | Split | Satır | Taslaktan düzeltilen | İnsan incelemesi | Yalnızca Claude incelemesi |
   |---|---|---|---|---|
   | train | 120 | 44 | 1 | 119 |
   | test | 257 | 115 | 163 | 94 |
   | validation | 43 | 13 | 0 | 43 |
   | prompt | 7 | 1 | 0 | 7 |
   | **Toplam** | **427** | **173** | **164** | **263** |

   "İnsan incelemesi" sütunu, kararı bir insanın verdiği veya bir insanın onayladığı metinde
   Claude'un sonradan yazım düzeltmesi yaptığı satırları içerir. **263 satır yalnızca Claude
   tarafından incelenmiştir**; bu satırlar bir insan tarafından tek tek kontrol edilmemiştir.
4. **Doğrulama:** Nihai dosyalar orijinal MBPP ile karşılaştırıldı: tüm `task_id`'ler mevcut,
   çeviri dışındaki bütün alanlar orijinalle birebir aynı ve 427 satırın tamamının kodu kendi
   testlerinden geçiyor.

## Çeviri kuralları

| İngilizce | Türkçe |
|---|---|
| function | fonksiyon |
| list / tuple / dictionary / set | liste / demet / sözlük / küme |
| string | string (ek alırken kesme işaretiyle: string'i, string'de) |
| array | dizi |
| integer | tam sayı |
| digit | rakam (basamak sayısı kastedildiğinde "basamak") |
| element | eleman |
| input | girdi |

- Görev cümleleri "… bulan bir fonksiyon yazın." gibi resmi hitapla çevrilmiştir.
- Fonksiyon/değişken isimleri, tırnak içindeki değerler, formüller ve bağlantılar olduğu gibi bırakılmıştır.

## Bilinen notlar

- **Kaynaktaki hatalar korunmuştur.** Örneğin "woodball" (Woodall sayısı) ve "lucid" (ludic
  sayıları) gibi yazım hataları, veri setinin aslına sadık kalması için düzeltilmemiştir.
- **Belirsiz kaynak metinler** anlamı değiştirmeden çevrilmiştir (ör. test 307 "get a colon of a
  tuple", test 259 "maximize the given two tuples"). Bu satırlarda anlamı netleştirmek için
  testlere bakılması önerilir.
- Train split'indeki bazı açıklamaların sonunda kaynak bağlantıları ve veri setini hazırlayanların
  notları bulunur (ör. train 753); bunlar da çevrilerek korunmuştur.
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
