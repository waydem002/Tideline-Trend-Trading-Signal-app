"""Guided Telegram setup: finds your chat id for you and writes the .env file."""
import os
import time
import requests
from . import config as C


def set_keys(path, base, kv):
    """Write KEY=value pairs into `path`, starting from `base` if `path` does not exist yet."""
    src = path if path.exists() else base
    lines = src.read_text().splitlines() if src.exists() else []
    seen, out = set(), []
    for ln in lines:
        k = ln.split("=", 1)[0].strip()
        if k in kv and not ln.strip().startswith("#") and "=" in ln:
            out.append(f"{k}={kv[k]}")
            seen.add(k)
        else:
            out.append(ln)
    out += [f"{k}={v}" for k, v in kv.items() if k not in seen]
    path.write_text("\n".join(out) + "\n")
    os.chmod(path, 0o600)  # only you can read it


def chat_id_from(updates):
    for u in reversed(updates.get("result", [])):
        msg = u.get("message") or u.get("channel_post") or {}
        if msg.get("chat", {}).get("id") is not None:
            return str(msg["chat"]["id"])
    return None


def run():
    print("1. In Telegram, open @BotFather, send /newbot and follow the steps. It gives you a token.")
    token = input("2. Paste the token here and press Enter: ").strip()
    input("3. Open your new bot in Telegram, press Start, send it any message, then press Enter here... ")
    chat = None
    for attempt in range(3):
        try:
            data = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
        except Exception as e:  # never print the exception: it contains the token
            print("Could not reach Telegram:", e.__class__.__name__)
            return
        if not data.get("ok"):
            print("Telegram did not accept that token. Copy it again from @BotFather and retry.")
            return
        chat = chat_id_from(data)
        if chat:
            break
        input("I do not see a message yet. Send one to your bot, then press Enter... ")
    if not chat:
        print("Still no message found. Run this setup again after messaging your bot.")
        return
    bal = input("4. How many USDT do you plan to trade with? (used only to size alerts) [1000]: ").strip() or "1000"
    set_keys(C.ROOT / ".env", C.ROOT / ".env.example",
             {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat, "ACCOUNT_BALANCE": bal})
    C.TELEGRAM_BOT_TOKEN, C.TELEGRAM_CHAT_ID = token, chat
    from .scanner import send
    ok = send(f"{C.APP_NAME} is connected. Alerts will arrive here.")
    print("Done. Your settings are saved in the hidden file .env." if ok else "Saved, but the test message failed. Check the message above.")
