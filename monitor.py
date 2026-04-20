#!/usr/bin/env python3
"""
🎯 Bambu Lab PLA Matte — Bot de surveillance de stock
Scrape la page produit et envoie une alerte Telegram au restock.
"""

import json, os, sys, re, urllib.request, urllib.error
from datetime import datetime

PRODUCT_URL  = "https://eu.store.bambulab.com/products/pla-matte"
STATE_FILE   = "state.json"
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


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
        print(f"❌ Erreur HTTP {e.code}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur réseau : {e}")
        sys.exit(1)


def parse_variants(html):
    """Extrait les variantes depuis le JSON embarqué dans la page Shopify."""
    # Shopify embarque le JSON produit dans un bloc <script> de la page
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
                # Si on a capturé un objet produit entier
                if raw.startswith("{"):
                    data = json.loads(raw)
                    variants = data.get("variants", [])
                else:
                    variants = json.loads(raw)
                if variants:
                    return variants
            except Exception:
                continue

    # Fallback : chercher "available" dans les données Shopify globales
    m = re.search(r'ShopifyAnalytics\.meta\s*=\s*(\{.*?\})\s*;', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            variants = data.get("product", {}).get("variants", [])
            if variants:
                return variants
        except Exception:
            pass

    return []


def detect_stock_from_html(html):
    """
    Méthode de secours : détecte si au moins un coloris est dispo
    en cherchant des marqueurs dans le HTML.
    """
    sold_out_count = len(re.findall(r'sold.?out|rupture|indisponible|out.?of.?stock', html, re.I))
    add_cart_count = len(re.findall(r'add.?to.?cart|ajouter.?au.?panier|add to bag', html, re.I))
    return add_cart_count > 0, sold_out_count, add_cart_count


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Secrets Telegram non configurés.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            print("✅ Telegram envoyé !" if result.get("ok") else f"⚠️  Telegram : {result}")
    except Exception as e:
        print(f"❌ Telegram : {e}")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    print(f"🔍 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} — {PRODUCT_URL}\n")

    html = fetch_html()
    print(f"📄 Page récupérée ({len(html)} caractères)")

    variants = parse_variants(html)
    previous = load_state()

    if variants:
        print(f"📦 {len(variants)} variante(s) trouvée(s) via JSON embarqué")
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
        print(f"✅ En stock ({len(in_stock)}) : {', '.join(v['title'] for v in in_stock) or 'aucun'}")
        print(f"❌ Rupture  ({len(out_stock)}) : {', '.join(v['title'] for v in out_stock) or 'aucun'}")

        newly = [
            info for vid, info in current.items()
            if info["available"] and not previous.get(vid, {}).get("available", False)
        ]
        save_state(current)

        if newly:
            lines = "\n".join(f"  • {v['title']}" for v in newly)
            send_telegram(
                f"🎉 <b>RESTOCK Bambu Lab PLA Matte !</b>\n\n"
                f"Coloris disponibles :\n{lines}\n\n"
                f"🛒 <a href='{PRODUCT_URL}'>Commander maintenant</a>\n"
                f"⏰ {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
            )
        elif not previous and in_stock:
            lines = "\n".join(f"  • {v['title']}" for v in in_stock)
            send_telegram(
                f"🤖 <b>Bot démarré</b>\n\nActuellement en stock :\n{lines}\n\n"
                f"🛒 <a href='{PRODUCT_URL}'>Voir la boutique</a>"
            )
        else:
            print("😴 Pas de changement.")

    else:
        # Fallback HTML brut
        print("⚠️  JSON embarqué non trouvé — analyse HTML brute")
        has_stock, sold, cart = detect_stock_from_html(html)
        print(f"   'add to cart' : {cart} fois | 'sold out' : {sold} fois")

        was_available = previous.get("fallback", {}).get("available", False)
        save_state({"fallback": {"available": has_stock, "title": "PLA Matte"}})

        if has_stock and not was_available:
            send_telegram(
                f"🎉 <b>RESTOCK Bambu Lab PLA Matte !</b>\n\n"
                f"Du stock semble disponible sur la boutique.\n\n"
                f"🛒 <a href='{PRODUCT_URL}'>Vérifier maintenant</a>\n"
                f"⏰ {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
            )
        elif has_stock:
            print("😴 En stock mais déjà connu.")
        else:
            print("😴 Toujours en rupture.")


if __name__ == "__main__":
    main()
