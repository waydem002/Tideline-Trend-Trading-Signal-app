# Tideline

A rules-based trend signal lab for BTC, ETH, SOL, BNB and XRP on 4-hour candles.
It does three things, in this order, and you should not skip steps:

1. **Tests the rules on years of real history**, including fees and slippage, and tells you plainly whether they hold up.
2. **Sends Telegram alerts** when a setup appears: where to enter, where the stop goes, what to do at each target.
3. **Follows every signal to its true outcome**, so after a month you know what it actually did.

Free to run. No API keys for market data. Not financial advice, and no system can promise profit.

## Set up (once)

```bash
cd tideline_app
python3 -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then add your Telegram details
```

Telegram: run `python run.py setup`. It walks you through making a bot with @BotFather, finds your chat id, writes the hidden `.env` file, and sends a test message.
(On a Mac, press Cmd+Shift+. in Finder to show hidden files.) Check it any time with `python run.py telegram-test`. It should say `[sent to Telegram]`.

## Step 1: test before you trade

```bash
python run.py backtest
```

This downloads about 7 years of candles, tests the rules, and writes **results/report.html**. Open it in your browser.
The first line tells you in plain words whether the rules passed. If they did not, **do not trade them**.
Come back with the report and we adjust the rules, not your account.

### If step 1 fails: let the data pick the rules, fairly

```bash
python run.py research
```

This compares 6 rule families on 5 and 10 coins (12 combinations), including slower daily-candle trend systems that ride big moves instead of taking quick profits. It picks a winner using only data **before 2024**, then judges that winner on 2024 onward, which it never touched. The result appears in the "Rule search" section of `results/report.html`, next to what simply holding BTC would have done.

`python run.py history` runs the daily rules on BTC and ETH data from before 2019, years the rules were never fitted to. It uses Bitstamp's free public candles.

`python run.py swing` tests trend rules traded long and short, and a weekly rotation that holds the strongest coins and can short the weakest, with futures funding charged. Check what derivatives are legal for you in Germany before using any result.

To test whether running a slow daily system and a faster 4h system together beats either alone, run `python run.py combo`. Every portfolio is held to the same 2.5% total open-risk cap, so a mix can't win just by risking more.

Two honest caveats. Trend systems hit few take-profits: they win about 35 to 45% of the time and earn through a few large winners, so long losing streaks are normal. And the 10-coin list is made of coins that are big today, which flatters history a little (survivorship bias).

## Step 2: paper trade for 6 to 8 weeks

```bash
python run.py scan --loop
```

Leave it running (a Mac that sleeps will miss candles; a cheap always-on machine is better).
It wakes after every 4-hour candle closes, sends alerts, and logs outcomes. Refresh `results/report.html` any time.
Place **no real orders** during this stage. Compare the live results to the backtest.

## Step 3: go live small

Only if the backtest passed and the paper results look like it. Start at a quarter of your intended size.
Alerts size each trade to risk 0.5% of `ACCOUNT_BALANCE`.

## The system that runs live: daily 100-day breakout

| Part | Rule |
|---|---|
| Coins | BTC, ETH, SOL, BNB, XRP (spot, long only) |
| Entry | A daily candle closes above its highest high of the last 100 days, and above its 200-day average. Buy at market. |
| Stop | 3 ATR below the entry. Never lower it. |
| Exit | There is no fixed take-profit. The stop trails 4 ATR behind the highest price since entry and only moves up. You are out when it is hit. |
| Risk | 0.5% of your account per trade, up to 5 trades at once. |

`python run.py scan --loop` checks once a day, just after midnight UTC. It messages you to buy, then each time the stop should be raised, then when the trade ends. Place a real stop-loss order on the exchange and raise it when told. If a signal arrives and the price has already run more than 1 ATR above the alert, skip it.

The daily Telegram message also says which coin is closest to a signal and how far away it is. `python run.py status` shows how far each coin is from triggering a signal, so a quiet scanner is easy to understand.

`python run.py risk` shows what each risk size (0.5% to 3%) could have earned and how bad bad luck could get. Gains and falls scale together, so choose a size you could stay calm through. Do not change it during paper trading.

Fixed in this version: when a trade was still open at the end of the data, the old backtest could count extra overlapping trades on that coin. Re-run `backtest`, `research`, `combo` and `risk` to refresh your numbers; they may shift slightly.

## The original 4h rules (failed testing, kept for reference)

| Part | Rule |
|---|---|
| Trend filter | Daily price above its 200-day average and the 50-day above the 200-day (long only on spot). 4h trend strength (ADX) at least 20. |
| Pullback entry | Price dips to the zone between the 20 and 50 averages, RSI drops to 45 or lower then recovers, the candle closes green above the 20 average. A buy-stop is placed just above it and cancelled after 3 candles. |
| Breakout entry | After a quiet stretch, a close above the 20-candle high on 1.5x average volume. |
| Stop | Below the recent swing low or 2 ATR from entry, whichever is farther. Trades with a stop under 1 or over 3 ATR are skipped. |
| Exits | 40% at +1R then stop to break-even, 30% at +2R, the rest trails 3 ATR behind the highest price. Also exits on two closes under the 50 average, or after 30 candles with no +1R. |
| Risk | 0.5% per trade, at most 3 trades at once (1.5% total), . Your own rules, which you must follow by hand: stop for the day at a 1.5% loss and for the week at 3%. |

"R" means the amount you risk on one trade. +2R means you made twice what you risked.

## What changed from the old system

- One shared engine runs both the test and the live scanner, so what you test is what you trade.
- Trade outcomes are recorded correctly. The old tracker crashed on a CSV column mismatch and logged nothing.
- Targets are close enough to be hit (+1R, +2R) and no signal "expires" after the fact.
- 5 liquid coins instead of 40, on one timeframe, with a market-regime filter.
- Secrets are never printed to logs. Keep `.env` out of any zip you share.
- No news page, no servers, no four terminals. One report file and one scanner command.

## Honest limits

- Spot trading cannot short, so in a bear market the system sits in cash. Shorts exist in the code (`shorts=True` in `engine.py`) but test them separately before use on futures.
- Candle data cannot show what happened inside a candle. When a stop and a target are both touched in one candle, the test assumes the stop came first, which is the pessimistic choice.
- Run the tests with `python tests/test_tideline.py`.
