#!/usr/bin/env python3
"""
Bambu Lab PLA Matte - Bot de surveillance de stock
"""

import json, os, sys, re, urllib.request, urllib.error
from datetime import datetime

PRODUCT_URL = "https://eu.store.bambulab.com/products/pla-matte"
STATE_FILE  = "state.json"
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def fetch_html():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(PRODUCT_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"Erreur HTTP {e.code}")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur reseau : {e}")
        sys.exit(1)


def parse_variants(html):
    patterns = [
        r'"variants"\s*:\s*(\[.*?\])\s*(?:,\s*"[a-z]|\})',
        r'var\s+meta\s*=\s*(\{.*?"variants".*?\})\s*;',
        r'"product"\s*:\s*(\{.*?"variants".*?\})',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                raw = m.group(1)
                if raw.startswith("{"):
                    data = json.loads(raw)
                    variants = data.get("variants", [])
                else:
                    variants = json.loads(raw)
                if variants:
                    return variants
            except Exception:
                continue
    return []


def detect_stock_from_html(html):
    sold_out_count = len(re.findall(r'sold.?out|rupture|indisponible|out.?of.?stock', html, re.I))
    add_cart_count = len(re.findall(r'add.?to.?cart|ajouter.?au.?panier|add to bag', html, re.I))
    return add_cart_count > 0, sold_out_count, add_cart_count


def send_telegram(message):
    print(f"Telegram - token present: {bool(TELEGRAM_TOKEN)} (longueur: {len(TELEGRAM_TOKEN)})")
    print(f"Telegram - chat_id present: {bool(TELEGRAM_CHAT_ID)} (longueur: {len(TELEGRAM_CHAT_ID)})")

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Secrets Telegram non configures.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print("Telegram envoye !")
            else:
                print(f"Telegram refuse : {result}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Telegram HTTP {e.code} : {body}")
    except Exception as e:
        print(f"Telegram erreur : {e}")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    print(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} - {PRODUCT_URL}\n")

    html = fetch_html()
    print(f"Page recuperee ({len(html)} caracteres)")

    variants = parse_variants(html)
    previous = load_state()

    if variants:
        print(f"{len(variants)} variante(s) trouvee(s)")
        current = {
            str(v.get("id", i)): {
                "title":     v.get("title", v.get("name", f"Coloris {i+1}")),
                "available": v.get("available", False),
                "price":     str(v.get("price", "?")),
            }
            for i, v in enumerate(variants)
        }
        in_stock  = [v for v in current.values() if v["available"]]
        out_stock = [v for v in current.values() if not v["available"]]
        print(f"En stock ({len(in_stock)}) : {', '.join(v['title'] for v in in_stock) or 'aucun'}")
        print(f"Rupture  ({len(out_stock)}) : {', '.join(v['title'] for v in out_stock) or 'aucun'}")

        newly = [
            info for vid, info in current.items()
            if info["available"] and not previous.get(vid, {}).get("available", False)
        ]
        save_state(current)

        if newly:
            lines = "\n".join(f"  - {v['title']}" for v in newly)
            send_telegram(
                f"RESTOCK Bambu Lab PLA Matte !\n\n"
                f"Coloris disponibles :\n{lines}\n\n"
                f"Commander : {PRODUCT_URL}\n"
                f"Detecte le {datetime.now().strftime('%d/%m/%Y a %H:%M')}"
            )
        elif not previous and in_stock:
            lines = "\n".join(f"  - {v['title']}" for v in in_stock)
            send_telegram(
                f"Bot demarre - Stock actuel\n\n"
                f"Coloris en stock :\n{lines}\n\n"
                f"Voir la boutique : {PRODUCT_URL}"
            )
        else:
            print("Pas de changement.")

    else:
        print("JSON embarque non trouve - analyse HTML brute")
        has_stock, sold, cart = detect_stock_from_html(html)
        print(f"add to cart : {cart} fois | sold out : {sold} fois")

        was_available = previous.get("fallback", {}).get("available", False)
        save_state({"fallback": {"available": has_stock, "title": "PLA Matte"}})

        if has_stock and not was_available:
            send_telegram(
                f"RESTOCK Bambu Lab PLA Matte !\n\n"
                f"Du stock est disponible sur la boutique.\n\n"
                f"Commander : {PRODUCT_URL}\n"
                f"Detecte le {datetime.now().strftime('%d/%m/%Y a %H:%M')}"
            )
        elif has_stock and not previous:
            send_telegram(
                f"Bot demarre - Stock actuel\n\n"
                f"Du stock semble disponible.\n\n"
                f"Voir : {PRODUCT_URL}"
            )
        elif has_stock:
            print("En stock mais deja connu.")
        else:
            print("Toujours en rupture.")


if __name__ == "__main__":
    main()
