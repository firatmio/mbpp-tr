"""
Çevrilen JSONL dosyasından rastgele N örnek gösterir.
Kalite kontrolü için: çevirileri gözden geçirmeden HF'ye yükleme.

Kullanım:
    python spot_check.py data/mbpp_tr_part1.jsonl --n 10
    python spot_check.py data/mbpp_tr_part1.jsonl --flagged   # geri çeviri kontrolünün işaretledikleri
"""

import argparse
import json
import random
from pathlib import Path


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str, help="JSONL dosya yolu")
    parser.add_argument("--n", type=int, default=10, help="Gösterilecek örnek sayısı")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--flagged", action="store_true",
                        help="Sadece geri çeviri kontrolünün işaretlediği satırları göster")
    args = parser.parse_args()

    records = read_jsonl(args.file)
    if not records:
        print("Dosyada kayıt yok.")
        return

    review_path = Path(args.file + ".review.jsonl")
    # Kesintili çalıştırmalarda aynı task_id birden fazla kez yazılmış olabilir; sonuncusu geçerli
    reviews = {r["task_id"]: r for r in read_jsonl(review_path)} if review_path.exists() else {}

    if args.flagged:
        if not reviews:
            print(f"İnceleme dosyası bulunamadı: {review_path}")
            return
        sample = [r for r in records if reviews.get(r["task_id"], {}).get("flagged")]
    else:
        random.seed(args.seed)
        sample = random.sample(records, min(args.n, len(records)))

    for r in sample:
        print("=" * 70)
        print(f"task_id: {r['task_id']}")
        print(f"EN: {r['prompt_en']}")
        print(f"TR: {r['prompt_tr']}")
        review = reviews.get(r["task_id"])
        if review:
            print(f"Geri çeviri: {review['back_translation']}")
            if review["flagged"]:
                for reason in review["reasons"]:
                    print(f"  ⚠ {reason}")
        print()

    print("=" * 70)
    label = "işaretli" if args.flagged else "rastgele"
    print(f"\nToplam {len(records)} kayıt, {len(sample)} {label} kayıt gösterildi.")


if __name__ == "__main__":
    main()
