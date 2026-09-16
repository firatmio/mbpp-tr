"""
Dışa aktarılan nihai veri setini orijinal MBPP ile karşılaştırarak doğrular.

Kullanım:
    python validate_final.py data/final --split sanitized

Kontroller:
  1. Her split'te orijinaldeki tüm task_id'ler var, fazlası yok, tekrar yok.
  2. prompt_en ve çeviri dışındaki tüm alanlar orijinalle birebir aynı.
  3. prompt_tr boş değil; kaynaktaki bağlantılar korunmuş; tr_rules uyarıları listelenir.
  4. Her satırın code'u kendi testlerinden geçiyor (ayrı süreçte, zaman aşımıyla).
     Orijinal veri setinde de geçmeyen testler ayrıca belirtilir.

Hata varsa çıkış kodu 1 olur.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from datasets import load_dataset

from tr_rules import check

HF_SPLITS = ["train", "test", "validation", "prompt"]
TEST_TIMEOUT = 20


def read_jsonl(path: Path) -> list:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_program(row: dict) -> str:
    parts = []
    parts.extend(row.get("test_imports") or [])
    parts.append(row["code"])
    if row.get("test_setup_code"):
        parts.append(row["test_setup_code"])
    parts.extend(row["test_list"])
    return "\n".join(parts) + "\n"


def run_tests(row: dict, workdir: Path) -> tuple:
    """(geçti mi, hata özeti) döndürür. Kod ayrı bir Python sürecinde çalışır."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", build_program(row)],
            cwd=workdir, capture_output=True, text=True, timeout=TEST_TIMEOUT,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"zaman aşımı ({TEST_TIMEOUT}s)"
    if proc.returncode == 0:
        return True, ""
    last = (proc.stderr.strip().splitlines() or ["bilinmeyen hata"])[-1]
    return False, last[:200]


def main():
    parser = argparse.ArgumentParser(description="Nihai veri setini doğrula")
    parser.add_argument("final_dir", type=str, help="Dışa aktarılmış dosyaların klasörü")
    parser.add_argument("--split", type=str, default="sanitized", choices=["sanitized", "full"])
    parser.add_argument("--prefix", type=str, default="mbpp_tr_", help="Dosya adı öneki")
    parser.add_argument("--skip-tests", action="store_true", help="Kod/test çalıştırmayı atla")
    args = parser.parse_args()

    final_dir = Path(args.final_dir)
    errors, notes = [], []
    to_run = []  # (split, task_id, çevrilmiş satır, orijinal satır)

    for hf_split in HF_SPLITS:
        path = final_dir / f"{args.prefix}{hf_split}.jsonl"
        if not path.exists():
            errors.append(f"[{hf_split}] dosya yok: {path}")
            continue

        original = {r["task_id"]: r for r in load_dataset("google-research-datasets/mbpp", args.split, split=hf_split)}
        rows = read_jsonl(path)
        ids = [r["task_id"] for r in rows]
        source_key = "prompt" if args.split == "sanitized" else "text"

        dupes = sorted({i for i in ids if ids.count(i) > 1})
        missing = sorted(set(original) - set(ids))
        extra = sorted(set(ids) - set(original))
        if dupes:
            errors.append(f"[{hf_split}] tekrar eden task_id: {dupes}")
        if missing:
            errors.append(f"[{hf_split}] eksik task_id ({len(missing)}): {missing}")
        if extra:
            errors.append(f"[{hf_split}] orijinalde olmayan task_id: {extra}")

        warned = 0
        for r in rows:
            tid = r["task_id"]
            orig = original.get(tid)
            if orig is None:
                continue

            if r.get("prompt_en") != orig[source_key]:
                errors.append(f"[{hf_split}] {tid}: prompt_en orijinalden farklı")
            expected_keys = (set(orig) - {source_key}) | {"prompt_en", "prompt_tr"}
            if set(r) != expected_keys:
                errors.append(f"[{hf_split}] {tid}: alan seti farklı: "
                              f"eksik {sorted(expected_keys - set(r))}, fazla {sorted(set(r) - expected_keys)}")
            for key in set(orig) - {source_key}:
                if key in r and r[key] != orig[key]:
                    errors.append(f"[{hf_split}] {tid}: '{key}' alanı orijinalden farklı")

            tr = r.get("prompt_tr") or ""
            if not tr.strip():
                errors.append(f"[{hf_split}] {tid}: prompt_tr boş")
            warnings = check(orig[source_key], tr)
            url_warnings = [w for w in warnings if "bağlantı" in w]
            if url_warnings:
                errors.extend(f"[{hf_split}] {tid}: {w}" for w in url_warnings)
            other = [w for w in warnings if w not in url_warnings]
            if other:
                warned += 1
                notes.append(f"[{hf_split}] {tid}: {'; '.join(other)}")

            to_run.append((hf_split, tid, r, orig))

        print(f"{hf_split:10} {len(rows):4} satır (orijinal {len(original)}), uyarılı {warned}")

    if not args.skip_tests and to_run:
        print(f"\n{len(to_run)} satırın testleri çalıştırılıyor...")
        with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=8) as pool:
            workdir = Path(tmp)
            results = list(pool.map(lambda item: (item, run_tests(item[2], workdir)), to_run))
            failed = [(item, err) for item, (ok, err) in results if not ok]
            # Başarısız olanları orijinal satırla tekrar dene: sorun bizde mi, veri setinde mi?
            for (hf_split, tid, r, orig), err in failed:
                orig_ok, _ = run_tests(orig, workdir)
                if orig_ok:
                    errors.append(f"[{hf_split}] {tid}: test başarısız ama orijinalde geçiyor: {err}")
                else:
                    notes.append(f"[{hf_split}] {tid}: test orijinal veri setinde de başarısız: {err}")
        print(f"Test sonucu: {len(to_run) - len(failed)}/{len(to_run)} geçti")

    if notes:
        print("\nNotlar (hata değil):")
        for n in notes:
            print("  " + n)
    if errors:
        print(f"\nHATALAR ({len(errors)}):")
        for e in errors:
            print("  " + e)
        sys.exit(1)
    print("\nDoğrulama başarılı.")


if __name__ == "__main__":
    main()
