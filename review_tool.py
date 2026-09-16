"""
Çevirileri satır satır onaylamak/düzeltmek için tarayıcı arayüzü.

Kullanım:
    python review_tool.py data/mbpp_tr_test.jsonl                  # tek dosya
    python review_tool.py "data/mbpp_tr_*.jsonl"                   # birden fazla dosya, arayüzde seçilir
    python review_tool.py "data/mbpp_tr_*.jsonl" --host 0.0.0.0    # aynı ağdaki başka bilgisayardan erişim
    python review_tool.py data/mbpp_tr_test.jsonl --export data/final/mbpp_tr_test.jsonl
    python review_tool.py "data/mbpp_tr_*.jsonl" --export-dir data/final

Kararlar <dosya>.decisions.json dosyasına her işlemde kaydedilir; araç
kapatılıp açıldığında kaldığı yerden devam eder. Dışa aktarma yalnızca
onaylanmış satırları, onaylanan Türkçe metinle birlikte yazar.

Araç ağa açıldığında (--host 127.0.0.1 dışında bir değer) adres gizli bir
token olmadan çalışmaz; token her başlatmada yeniden üretilir (sabit istenirse --token).
"""

import argparse
import glob
import hmac
import ipaddress
import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tr_rules import check

UI_PATH = Path(__file__).resolve().parent / "review_ui.html"


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class DecisionConflict(Exception):
    """Karar, istemcinin gördüğü halinden sonra başka bir yerden değiştirilmiş."""


class ReviewStore:
    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.name = data_path.name
        self.decisions_path = data_path.with_name(data_path.name + ".decisions.json")
        self.lock = threading.Lock()

        records = read_jsonl(data_path)
        if not records:
            raise SystemExit(f"Kayıt bulunamadı: {data_path}")
        # Kesintili çalıştırmalarda aynı task_id tekrar yazılmış olabilir; sonuncusu geçerli
        self.records = {r["task_id"]: r for r in records}
        self.review = {r["task_id"]: r for r in read_jsonl(data_path.with_name(data_path.name + ".review.jsonl"))}

        self.decisions = {}
        if self.decisions_path.exists():
            self.decisions = {int(k): v for k, v in
                              json.loads(self.decisions_path.read_text(encoding="utf-8")).items()}

    def summary(self) -> dict:
        statuses = [d["status"] for d in self.decisions.values()]
        return {
            "name": self.name,
            "total": len(self.records),
            "approved": statuses.count("approved"),
            "problem": statuses.count("problem"),
        }

    def items(self) -> list:
        items = []
        for task_id, r in self.records.items():
            rv = self.review.get(task_id, {})
            items.append({
                "task_id": task_id,
                "prompt_en": r["prompt_en"],
                "draft_tr": r["prompt_tr"],
                "code": r.get("code", ""),
                "test_list": r.get("test_list", []),
                "test_imports": r.get("test_imports") or [],
                "test_setup_code": r.get("test_setup_code") or "",
                "back_translation": rv.get("back_translation"),
                "review_reasons": rv.get("reasons", []) if rv.get("flagged") else [],
                "warnings": check(r["prompt_en"], r["prompt_tr"]),
            })
        return items

    def save_decision(self, task_id: int, status: str, final_tr: str, note: str,
                      expected_updated_at) -> dict:
        if task_id not in self.records:
            raise KeyError(task_id)
        if status not in ("approved", "problem", "pending"):
            raise ValueError(status)
        with self.lock:
            current = self.decisions.get(task_id)
            if (current["updated_at"] if current else None) != expected_updated_at:
                raise DecisionConflict(task_id)

            # Zaten onaylı bir satır metni ve notu değiştirilmeden tekrar onaylanırsa hiçbir şey yazılmaz.
            # Aksi halde Ctrl+Enter ile hızla geçilen satırlar "insan inceledi" diye yeniden etiketlenir
            # ve kimin incelediği / çevirinin nereden alındığı bilgisi kaybolurdu.
            if (status == "approved" and current and current["status"] == "approved"
                    and final_tr.strip() == current["final_tr"]
                    and note.strip() == (current.get("note") or "")):
                return current

            if status == "pending":
                self.decisions.pop(task_id, None)
                decision = None
            else:
                decision = {
                    "status": status,
                    "final_tr": final_tr.strip(),
                    # Taslak sonradan yeniden çevrilirse arayüz bunu fark edebilsin diye saklanır
                    "draft_tr": self.records[task_id]["prompt_tr"],
                    "edited": final_tr.strip() != self.records[task_id]["prompt_tr"],
                    "note": note.strip(),
                    # Arayüzden verilen kararlar insan kararıdır; Claude'un toplu kararlarından ayrılır
                    "reviewer": "human",
                    "updated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                }
                # Metin değişmediyse, çevirinin başka bir dosyadaki onaylı çeviriden alındığı bilgisi korunur
                if current and current.get("reused_from") and decision["final_tr"] == current["final_tr"]:
                    decision["reused_from"] = current["reused_from"]
                self.decisions[task_id] = decision
            # Önce geçici dosyaya yaz, sonra değiştir: yazma yarıda kesilirse eski kararlar bozulmaz
            tmp = self.decisions_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({str(k): v for k, v in sorted(self.decisions.items())},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.decisions_path)
        return decision

    def export(self, out_path: Path) -> None:
        approved = []
        stale = []
        for task_id, r in self.records.items():
            d = self.decisions.get(task_id)
            if not d or d["status"] != "approved":
                continue
            if d["draft_tr"] != r["prompt_tr"]:
                stale.append(task_id)
            record = dict(r)
            record["prompt_tr"] = d["final_tr"]
            approved.append(record)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for record in approved:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        total = len(self.records)
        print(f"{self.name}: {len(approved)}/{total} onaylı satır yazıldı → {out_path}")
        if len(approved) < total:
            print(f"  Uyarı: {total - len(approved)} satır henüz onaylanmadı ve dışarıda bırakıldı.")
        if stale:
            print(f"  Uyarı: {len(stale)} satırın taslağı onaydan sonra değişmiş, kontrol edin: {stale}")


def make_handler(stores: dict, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # terminali her istekle kirletme

        def _send(self, status: int, body, content_type="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            # Token adreste taşındığı için başka sitelere Referer ile sızmasın
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self, url) -> bool:
            if token is None:
                return True
            given = self.headers.get("X-Review-Token") or parse_qs(url.query).get("token", [""])[0]
            return hmac.compare_digest(given.encode(), token.encode())

        def _store(self, name: str) -> ReviewStore:
            if name not in stores:
                raise KeyError(f"dosya: {name}")
            return stores[name]

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self):
            url = urlparse(self.path)
            if not self._authorized(url):
                self._send(403, "Erişim reddedildi: adresi token ile birlikte açın.".encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            try:
                if url.path == "/":
                    self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")
                elif url.path == "/api/files":
                    self._send(200, {"files": [s.summary() for s in stores.values()]})
                elif url.path == "/api/data":
                    store = self._store(parse_qs(url.query).get("file", [""])[0])
                    self._send(200, {
                        "file": store.name,
                        "items": store.items(),
                        "decisions": {str(k): v for k, v in store.decisions.items()},
                    })
                else:
                    self._send(404, {"error": "bulunamadı"})
            except KeyError as e:
                self._send(404, {"error": f"bulunamadı: {e}"})

        def do_POST(self):
            url = urlparse(self.path)
            if not self._authorized(url):
                self._send(403, {"error": "erişim reddedildi"})
                return
            try:
                body = self._read_json()
                if url.path == "/api/decision":
                    store = self._store(body["file"])
                    decision = store.save_decision(
                        int(body["task_id"]), body["status"], body.get("final_tr", ""),
                        body.get("note", ""), body.get("expected_updated_at"))
                    self._send(200, {"decision": decision})
                elif url.path == "/api/check":
                    self._send(200, {"warnings": check(body.get("en", ""), body.get("tr", ""))})
                else:
                    self._send(404, {"error": "bulunamadı"})
            except DecisionConflict:
                self._send(409, {"error": "Bu satır başka bir yerden değiştirilmiş."})
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                self._send(400, {"error": f"geçersiz istek: {e}"})

    return Handler


def lan_addresses() -> list:
    """Bu bilgisayarın yerel ağ IPv4 adresleri (ağa paket gönderilmez)."""
    addrs = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP connect paket göndermez, sadece çıkış arayüzünü seçer
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        addrs.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(a for a in addrs if ipaddress.ip_address(a).is_private and not a.startswith("127."))


def expand_paths(patterns: list) -> list:
    # PowerShell joker karakterleri Python'a açmadan geçirir; burada açılır
    paths = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern)) if any(c in pattern for c in "*?[") else [pattern]
        paths.extend(Path(m) for m in matches)
    # Yardımcı dosyaları (.review.jsonl, .failed.jsonl) ve tekrarları ele
    seen, result = set(), []
    for p in paths:
        if p.name.count(".jsonl") != 1 or not p.name.endswith(".jsonl") or p.resolve() in seen:
            continue
        seen.add(p.resolve())
        result.append(p)
    return result


def main():
    parser = argparse.ArgumentParser(description="Çeviri onay aracı")
    parser.add_argument("files", nargs="+", help="Çeviri JSONL dosyaları (joker karakter kullanılabilir)")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Dinlenecek adres; aynı ağdan erişim için 0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", type=str, default=None,
                        help="Ağa açıkken kullanılacak sabit token (verilmezse rastgele üretilir)")
    parser.add_argument("--export", type=str, default=None,
                        help="Tek dosyanın onaylı satırlarını bu dosyaya yaz ve çık")
    parser.add_argument("--export-dir", type=str, default=None,
                        help="Tüm dosyaların onaylı satırlarını bu klasöre aynı isimlerle yaz ve çık")
    parser.add_argument("--no-browser", action="store_true", help="Tarayıcıyı otomatik açma")
    args = parser.parse_args()

    paths = expand_paths(args.files)
    if not paths:
        parser.error("Eşleşen çeviri dosyası bulunamadı")
    stores = {}
    for p in paths:
        store = ReviewStore(p)
        if store.name in stores:
            parser.error(f"Aynı isimde iki dosya verildi: {store.name}")
        stores[store.name] = store

    if args.export:
        if len(stores) != 1:
            parser.error("--export tek dosya ile kullanılır; birden fazla dosya için --export-dir")
        next(iter(stores.values())).export(Path(args.export))
        return
    if args.export_dir:
        for store in stores.values():
            store.export(Path(args.export_dir) / store.name)
        return

    is_local = ipaddress.ip_address(args.host).is_loopback if args.host != "localhost" else True
    # Ağa açıkken token zorunlu; --token verilmişse yerelde de istenir
    token = args.token or (None if is_local else secrets.token_urlsafe(16))

    server = ThreadingHTTPServer((args.host, args.port), make_handler(stores, token))
    query = f"?token={token}" if token else ""

    for s in stores.values():
        info = s.summary()
        print(f"  {info['name']}: {info['total']} satır, {info['approved']} onaylı, {info['problem']} sorunlu")
    local_url = f"http://127.0.0.1:{args.port}/{query}"
    print(f"\nBu bilgisayardan: {local_url}")
    if not is_local:
        addrs = lan_addresses() if args.host == "0.0.0.0" else [args.host]
        for addr in addrs:
            print(f"Aynı ağdaki başka bilgisayardan: http://{addr}:{args.port}/{query}")
        print("Adresi (token dahil) yalnızca inceleme yapacak kişiyle paylaşın.")
    print("Kapatmak için Ctrl+C", flush=True)

    if not args.no_browser:
        webbrowser.open(local_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatıldı. Kararlar kaydedildi.")
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
