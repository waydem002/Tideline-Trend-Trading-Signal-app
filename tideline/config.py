import os
from pathlib import Path

APP_NAME = "Tideline"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "results"


def _load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


_load_env()

# Only large, liquid pairs. Thin coins produce noisy signals and bad fills.
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
TIMEFRAME = "4h"
HISTORY_START = "2019-01-01"

# Costs per side, as a fraction of price. Deliberately a bit pessimistic.
FEE = 0.001
SLIPPAGE = 0.0005

# Risk rules
RISK_PER_TRADE = 0.005   # 0.5% of account risked per trade
MAX_OPEN = 3             # at most 3 trades (orders + positions) at once -> 1.5% total risk
START_EQUITY = 10_000.0

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ACCOUNT_BALANCE = float(os.environ.get("ACCOUNT_BALANCE", "1000"))
