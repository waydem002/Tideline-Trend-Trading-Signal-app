"""Tideline command line.
  python run.py backtest        download history, test the rules, build results/report.html
  python run.py scan            check the latest closed candle once
  python run.py scan --loop     keep running, once per 4h candle
  python run.py research        compare rule sets fairly (learning vs untouched period)
  python run.py combo           test the slow and fast trend systems alone and together
  python run.py history         test the same rules on years before 2019 (fresh evidence)
  python run.py swing           test long-and-short and weekly-rotation ideas with futures costs
  python run.py status          how close each coin is to a signal right now
  python run.py risk            show gains and worst-case falls at different risk sizes
  python run.py report          rebuild results/report.html
  python run.py setup           connect Telegram (creates the .env file for you)
  python run.py telegram-test   send a test message to your Telegram
"""
import sys
from tideline import config as C


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "backtest":
        from tideline.data import load
        from tideline.engine import P, prepare
        from tideline.backtest import full_report, save
        from tideline.report import render
        prepared = {}
        for s in C.SYMBOLS:
            print("Downloading", s, "...")
            prepared[s] = prepare(load(s))
        print("Testing the rules (this takes a minute)...")
        out, tr = full_report(prepared, P())
        save(out, tr)
        path = render()
        m = out["metrics"]
        print(f"\nTrades {m['n']}   win rate {m['win']:.0%}   average {m['avg_r']:+.2f}R   profit factor {m['pf']:.2f}   worst drawdown {m['mdd']:.0%}")
        print("Verdict:", out["verdict"].upper())
        for c in out["checks"]:
            print(" ", "met   " if c["ok"] else "missed", c["label"])
        print("\nOpen this file in your browser:", path)
    elif cmd == "scan":
        from tideline import scanner
        scanner.loop() if "--loop" in sys.argv else scanner.cycle()
    elif cmd == "research":
        from tideline import research
        from tideline.report import render
        out = research.run()
        research.save(out)
        print("\n" + out["headline"] + "\n" + out["detail"])
        print(f"({out['trials']} combinations tried)")
        print("\nOpen this file in your browser:", render())
    elif cmd == "combo":
        from tideline import combo
        from tideline.report import render
        out = combo.run()
        combo.save(out)
        print("\n" + out["headline"] + "\n" + out["detail"])
        print("\nOpen this file in your browser:", render())
    elif cmd == "setup":
        from tideline import setup_telegram
        setup_telegram.run()
    elif cmd == "history":
        from tideline import history
        from tideline.report import render
        out = history.run()
        history.save(out)
        print("\n" + out["headline"] + "\n" + out["detail"])
        print("\nOpen this file in your browser:", render())
    elif cmd == "swing":
        from tideline import swing
        from tideline.report import render
        out = swing.run()
        swing.save(out)
        print("\nTRADE SYSTEMS: " + out["trade_headline"] + "\n" + out["trade_detail"])
        print("\nROTATION: " + out["rot_headline"] + "\n" + out["rot_detail"])
        print(f"\n({out['trials']} combinations tried)\nOpen this file in your browser:", render())
    elif cmd == "status":
        from tideline import status
        status.run()
    elif cmd == "risk":
        from tideline import risk
        from tideline.report import render
        out = risk.run()
        risk.save(out)
        print(f"{out['system']}: {out['trades']} trades ({out['per_year']} a year), average {out['avg_r']:+.2f}R, recent {out['oos_avg_r']}R")
        print("risk/trade  untouched gain  untouched fall  typical 3y  bad-luck 3y  bad-luck fall  chance of loss")
        for x in out["rows"]:
            print(f"{x['risk']*100:>6.1f}%   {x['oos']['ret']*100:>12.1f}%  {x['oos']['mdd']*100:>13.1f}%  {x['sim']['median']*100:>9.1f}%  {x['sim']['bad']*100:>10.1f}%  {x['sim']['fall']*100:>12.1f}%  {x['sim']['lose']*100:>12.0f}%")
        print("\nOpen this file in your browser:", render())
    elif cmd == "report":
        from tideline.report import render
        print("Open:", render())
    elif cmd == "telegram-test":
        from tideline.scanner import send
        send(f"{C.APP_NAME} test message. If you can read this, alerts work.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
