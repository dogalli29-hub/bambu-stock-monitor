#!/usr/bin/env python3
"""
🎯 Bambu Lab PLA Matte — Bot de surveillance de stock
Vérifie toutes les 15 min et envoie un message Telegram si un coloris revient en stock.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
# URL de l'API Shopify du produit (format JSON caché, toujours dispo)
PRODUCT_URL = "https://eu.store.bambulab.com/products/pla-matte.json"

# Fichier qui mémorise l'état précédent (géré automatiquement)
STATE_FILE = "state.json"

# Variables d'environnement injectées par GitHub Actions Secrets
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# ──────────────────────────────────────────────────────────────────────────────


def fetch_product():
    """Récupère les données produit depuis l'API Shopify de Bambu Lab."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Referer": "https://eu.store.bambulab.com/",
    }
    req = urllib.request.Request(PRODUCT_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("product", {})
    except urllib.error.HTTPError as e:
        print(f"❌ Erreur HTTP {e.code} en accédant à la boutique.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Impossible de joindre la boutique : {e}")
        sys.exit(1)


def send_telegram(message: str):
    """Envoie un message via l'API Telegram Bot."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Variables Telegram non configurées — message non envoyé.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print("✅ Message Telegram envoyé !")
                return True
            else:
                print(f"⚠️  Telegram a répondu : {result}")
                return False
    except Exception as e:
        print(f"❌ Erreur envoi Telegram : {e}")
        return False


def load_state() -> dict:
    """Charge l'état précédent (coloris en stock connus)."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    """Sauvegarde le nouvel état."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    print(f"🔍 Vérification du stock — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"📦 URL : {PRODUCT_URL}\n")

    product    = fetch_product()
    variants   = product.get("variants", [])
    title      = product.get("title", "PLA Matte")

    if not variants:
        print("⚠️  Aucune variante trouvée. La structure du site a peut-être changé.")
        sys.exit(0)

    # État actuel : {variant_id: {"title": ..., "available": bool}}
    current_state = {}
    for v in variants:
        current_state[str(v["id"])] = {
            "title":     v.get("title", "?"),
            "available": v.get("available", False),
            "price":     v.get("price", "?")
        }

    # Affiche l'état en console (visible dans les logs GitHub Actions)
    in_stock  = [v for v in current_state.values() if v["available"]]
    out_stock = [v for v in current_state.values() if not v["available"]]
    print(f"✅ En stock    ({len(in_stock)}) : {', '.join(v['title'] for v in in_stock) or 'aucun'}")
    print(f"❌ Rupture      ({len(out_stock)}) : {', '.join(v['title'] for v in out_stock) or 'aucun'}")

    # Comparaison avec l'état précédent
    previous_state = load_state()
    newly_available = []

    for vid, info in current_state.items():
        was_available = previous_state.get(vid, {}).get("available", False)
        is_available  = info["available"]

        if is_available and not was_available:
            newly_available.append(info)

    # Sauvegarde dans tous les cas
    save_state(current_state)

    # Notification si du nouveau stock est apparu
    if newly_available:
        colors = "\n".join(f"  • {v['title']} — {v['price']} €" for v in newly_available)
        msg = (
            f"🎉 <b>RESTOCK BAMBU LAB !</b>\n\n"
            f"Le filament <b>{title}</b> est de nouveau disponible :\n\n"
            f"{colors}\n\n"
            f"🛒 <a href='https://eu.store.bambulab.com/products/pla-matte-filament'>Commander maintenant</a>\n\n"
            f"⏰ Détecté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
        )
        print(f"\n🚨 NOUVEAU STOCK DÉTECTÉ : {[v['title'] for v in newly_available]}")
        send_telegram(msg)
    else:
        print("\n😴 Pas de changement — aucune notification envoyée.")

    # Si c'est la première exécution et qu'il y a déjà du stock, on notifie quand même
    if not previous_state and in_stock:
        colors = "\n".join(f"  • {v['title']} — {v['price']} €" for v in in_stock)
        msg = (
            f"🤖 <b>Bot démarré — Stock actuel</b>\n\n"
            f"Filament <b>{title}</b> actuellement en stock :\n\n"
            f"{colors}\n\n"
            f"🛒 <a href='https://eu.store.bambulab.com/products/pla-matte-filament'>Commander maintenant</a>"
        )
        print("\n📢 Première exécution — envoi de l'état initial.")
        send_telegram(msg)


if __name__ == "__main__":
    main()
