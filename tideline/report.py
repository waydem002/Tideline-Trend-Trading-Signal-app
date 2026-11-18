"""Builds results/report.html: one self-contained file, no server, no internet needed."""
import json
from . import config as C


def _read(name):
    f = C.OUT_DIR / name
    return json.loads(f.read_text()) if f.exists() else None


def render():
    C.OUT_DIR.mkdir(exist_ok=True)
    blob = lambda x: json.dumps(x).replace("</", "<\\/")
    html = TEMPLATE.replace("__APP__", C.APP_NAME).replace("__B__", blob(_read("backtest.json"))).replace("__S__", blob(_read("state.json"))).replace("__R__", blob(_read("research.json"))).replace("__C__", blob(_read("combo.json"))).replace("__K__", blob(_read("risk.json"))).replace("__H__", blob(_read("history.json"))).replace("__W__", blob(_read("swing.json")))
    out = C.OUT_DIR / "report.html"
    out.write_text(html, encoding="utf-8")
    return str(out)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__APP__</title>
<style>
:root{--fog:#e9eff0;--paper:#f6f9f9;--ink:#10232f;--mute:#586d79;--tide:#1b6e85;--wash:rgba(27,110,133,.18);--good:#1d7548;--bad:#b0402f;--line:#cbd7da}
@media (prefers-color-scheme:dark){:root{--fog:#0b1923;--paper:#10242f;--ink:#e2edf0;--mute:#8fa5b1;--tide:#52b6cf;--wash:rgba(82,182,207,.2);--good:#58c48a;--bad:#e8785f;--line:#244050}}
*{box-sizing:border-box}body{margin:0;background:var(--fog);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:28px 20px 72px}
.serif{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:12px}
.brand{font-size:28px;font-weight:600;letter-spacing:.2px}.sub{color:var(--mute);font-size:14px}
h2{font-size:21px;margin:44px 0 6px;font-weight:600}p.note{color:var(--mute);margin:0 0 14px;max-width:70ch;font-size:15px}
.verdict{font-size:clamp(26px,4.4vw,40px);line-height:1.18;margin:30px 0 8px;max-width:22ch;font-weight:600}
.verdict.pass{color:var(--good)}.verdict.fail{color:var(--bad)}.verdict.close{color:var(--tide)}
.checks{list-style:none;padding:0;margin:14px 0 0;display:grid;gap:6px;max-width:640px}
.checks li{padding:8px 12px;background:var(--paper);border-left:4px solid var(--line);display:flex;justify-content:space-between;gap:12px;font-size:15px}
.checks li.ok{border-color:var(--good)}.checks li.no{border-color:var(--bad)}.checks b{font-weight:600}
.checks li.ok b{color:var(--good)}.checks li.no b{color:var(--bad)}
.nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:18px 24px;margin:20px 0 6px}
.nums div{border-top:2px solid var(--tide);padding-top:8px}.nums strong{display:block;font-size:30px;font-weight:600;font-variant-numeric:tabular-nums}.nums span{color:var(--mute);font-size:14px}
svg{width:100%;height:auto;display:block;background:var(--paper)}svg text{fill:var(--mute);font-size:11px}
.draw{stroke-dasharray:var(--len);stroke-dashoffset:var(--len);animation:d 1.6s ease-out forwards}@keyframes d{to{stroke-dashoffset:0}}
@media (prefers-reduced-motion:reduce){.draw{animation:none;stroke-dashoffset:0}}
.legend{font-size:13px;color:var(--mute);margin-top:6px}.legend i{display:inline-block;width:14px;height:8px;margin:0 6px 0 12px;background:var(--wash);border-top:2px solid var(--tide)}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:var(--paper);font-variant-numeric:tabular-nums;font-size:15px}
caption{text-align:left;color:var(--mute);padding:0 0 6px;font-size:14px}th,td{padding:8px 12px;text-align:right;border-bottom:1px solid var(--line)}th:first-child,td:first-child{text-align:left}th{font-weight:600}
.pos{color:var(--good)}.neg{color:var(--bad)}.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px}
.empty{padding:16px;background:var(--paper);color:var(--mute);border-left:4px solid var(--line)}code{background:var(--paper);padding:1px 6px}
footer{margin-top:48px;color:var(--mute);font-size:13px;max-width:70ch}
</style></head><body><main>
<header><div class="brand serif">__APP__</div><div class="sub" id="meta"></div></header>
<div id="app"></div>
<footer>Past results do not predict future results. This is a testing tool, not financial advice. Crypto can lose most of its value quickly, so only use money you can afford to lose.</footer>
</main>
<script>
const B=__B__, S=__S__, RS=__R__, CB=__C__, RK=__K__, HS=__H__, SW=__W__, $=id=>document.getElementById(id);
const pc=(x,d=1)=>(x*100).toFixed(d)+"%", R=x=>(x>=0?"+":"")+x.toFixed(2)+"R", cl=x=>x>0?"pos":x<0?"neg":"";
const px=x=>x>=100?x.toLocaleString(undefined,{maximumFractionDigits:2}):x>=1?x.toFixed(4):x.toFixed(6);
let h="";
if(!B){h+=`<h1 class="verdict serif close">No test results yet.</h1><p class="note">Run <code>python run.py backtest</code>, then open this page again.</p>`}
else{
 const m=B.metrics, bad=B.checks.filter(c=>!c.ok).length;
 $("meta").textContent=`Tested ${B.start} to ${B.end} on ${B.symbols.map(s=>s.replace("USDT","")).join(", ")}. Updated ${B.generated}.`;
 const head={pass:"The rules passed every test. Paper trade before using real money.",close:`Close, but not proven: ${bad} of ${B.checks.length} checks missed.`,fail:`Not proven: ${bad} of ${B.checks.length} checks missed. Do not trade this with real money yet.`}[B.verdict];
 h+=`<h1 class="verdict serif ${B.verdict}">${head}</h1>
 <p class="note">Every trade in the test paid ${pc(B.costs.fee,2)} fees and ${pc(B.costs.slippage,2)} slippage per side, risked ${pc(B.costs.risk,1)} of the account, and used the same code as the live scanner.</p>
 <ul class="checks">${B.checks.map(c=>`<li class="${c.ok?"ok":"no"}"><span>${c.label}</span><b>${c.ok?"Met":"Missed"}</b></li>`).join("")}</ul>
 <div class="nums">
  <div><strong>${m.n}</strong><span>trades</span></div>
  <div><strong>${pc(m.win,0)}</strong><span>won. Trend systems usually win under half</span></div>
  <div><strong class="${cl(m.avg_r)}">${R(m.avg_r)}</strong><span>average per trade. 1R is the amount you risk</span></div>
  <div><strong>${m.pf.toFixed(2)}</strong><span>profit factor. Above 1 means winners outweigh losers</span></div>
  <div><strong class="neg">${pc(m.mdd,0)}</strong><span>worst fall from a peak</span></div>
  <div><strong>${m.streak}</strong><span>most losses in a row</span></div>
 </div>
 <h2 class="serif">Account value</h2><p class="note">Starting at $10,000 and risking ${pc(B.costs.risk,1)} per trade. The shaded area is time spent below the previous peak, the part that tests your patience.</p><div id="chart"></div>
 <div class="legend"><i></i>Below previous peak</div>`;
 const rows=(a,f)=>a.map(f).join("");
 h+=`<h2 class="serif">Year by year</h2><p class="note">Trend systems have bad years. What matters is whether the good years pay for them.</p>
 <div class="wrap"><table><caption>Results by year</caption><tr><th>Year</th><th>Trades</th><th>Average per trade</th><th>Account change</th></tr>${rows(B.yearly,y=>`<tr><td>${y.year}</td><td>${y.n}</td><td class="${cl(y.avg_r)}">${R(y.avg_r)}</td><td class="${cl(y.ret)}">${pc(y.ret)}</td></tr>`)}</table></div>
 <div class="two"><div><h2 class="serif">By coin</h2><div class="wrap"><table><tr><th>Coin</th><th>Trades</th><th>Won</th><th>Average</th></tr>${rows(B.by_symbol,s=>`<tr><td>${s.symbol.replace("USDT","")}</td><td>${s.n}</td><td>${pc(s.win,0)}</td><td class="${cl(s.avg_r)}">${R(s.avg_r)}</td></tr>`)}</table></div></div>
 <div><h2 class="serif">Early versus recent</h2><div class="wrap"><table><tr><th>Period</th><th>Trades</th><th>Average</th><th>Profit factor</th></tr>
 <tr><td>First 60%</td><td>${B.split.early.n}</td><td class="${cl(B.split.early.avg_r)}">${R(B.split.early.avg_r)}</td><td>${B.split.early.pf.toFixed(2)}</td></tr>
 <tr><td>Latest 40%</td><td>${B.split.recent.n}</td><td class="${cl(B.split.recent.avg_r)}">${R(B.split.recent.avg_r)}</td><td>${B.split.recent.pf.toFixed(2)}</td></tr></table></div></div></div>
 <h2 class="serif">Does it survive small changes?</h2><p class="note">Average result per trade when two settings are nudged. A real edge stays positive across the grid. A lucky fit collapses when you move it.</p>
 <div class="wrap"><table><caption>Trend strength minimum (rows) and stop distance in ATR (columns)</caption><tr><th>Trend strength</th>${[1.6,2,2.4].map(s=>`<th>${s} ATR</th>`).join("")}</tr>
 ${[16,20,24].map(a=>`<tr><td>${a}</td>${[1.6,2,2.4].map(s=>{const g=B.grid.find(x=>x.adx==a&&x.stop==s);return `<td class="${cl(g.avg_r)}">${R(g.avg_r)}</td>`}).join("")}</tr>`).join("")}</table></div>`;
}
if(RS){
 const q=m=>`<td>${m.n}</td><td class="${cl(m.avg_r)}">${R(m.avg_r)}</td><td>${m.n?m.pf.toFixed(2):"-"}</td>`;
 h+=`<h2 class="serif">Rule search</h2><p class="verdict serif ${RS.verdict}" style="font-size:24px;max-width:none">${RS.headline}</p><p class="note">${RS.detail}</p>
 <p class="note">${RS.trials} combinations were tried. Each was ranked using only trades before ${RS.cut}. The later period stayed untouched until one winner was picked. Trying many combinations makes a lucky winner more likely, so treat even a pass as a reason to paper trade, not to go all in.</p>
 <div class="wrap"><table><caption>Learning period (before ${RS.cut}) and untouched period (after)</caption><tr><th>Rules</th><th>Coins</th><th>Trades</th><th>Average</th><th>Profit factor</th><th>Trades</th><th>Average</th><th>Profit factor</th></tr>
 ${RS.table.map(x=>`<tr><td>${x.name}${x.chosen?" (chosen)":""}</td><td>${x.universe}</td>${q(x.learn)}${q(x.oos)}</tr>`).join("")}</table></div>`;
}
if(CB){
 const q=m=>`<td>${m.n}</td><td class="${cl(m.ret)}">${pc(m.ret)}</td><td class="neg">${pc(m.mdd,0)}</td><td>${m.ratio.toFixed(1)}</td>`;
 h+=`<h2 class="serif">Two speeds together</h2><p class="verdict serif ${CB.verdict}" style="font-size:24px;max-width:none">${CB.headline}</p><p class="note">${CB.detail}</p>
 <div class="wrap"><table><caption>Same total risk cap for every row. Fall = worst drop from a peak. Ratio = account gain divided by that fall (higher is better).</caption><tr><th>Portfolio</th><th>Coins</th><th>Trades</th><th>Gain</th><th>Fall</th><th>Ratio</th><th>Trades</th><th>Gain</th><th>Fall</th><th>Ratio</th></tr>
 <tr><td></td><td></td><td colspan="4">Before ${CB.cut}</td><td colspan="4">After (untouched)</td></tr>
 ${CB.table.map(x=>`<tr><td>${x.name}</td><td>${x.universe}</td>${q(x.learn)}${q(x.oos)}</tr>`).join("")}</table></div>`;
}
if(RK){
 const p0=x=>pc(x,0);
 h+=`<h2 class="serif">Risk dial</h2><p class="note">${RK.system} on ${RK.trades} trades (${RK.per_year} a year). Gains and falls grow together as you risk more per trade. The last three columns simulate 3 years ahead by redrawing the system's own trades 5,000 times, with the winners shrunk to the weaker average of the untouched period (${RK.oos_avg_r>=0?"+":""}${RK.oos_avg_r}R per trade, against ${RK.avg_r>=0?"+":""}${RK.avg_r}R for the full history).</p>
 <div class="wrap"><table><caption>Risk per trade, result on the untouched period, and 3-year simulation</caption><tr><th>Risk per trade</th><th>Untouched gain</th><th>Untouched fall</th><th>Typical 3-year gain</th><th>Bad-luck 3-year gain (1 in 20)</th><th>Bad-luck fall (1 in 20)</th><th>Chance of losing money</th></tr>
 ${RK.rows.map(x=>`<tr><td>${pc(x.risk,1)}</td><td class="${cl(x.oos.ret)}">${pc(x.oos.ret)}</td><td class="neg">${p0(x.oos.mdd)}</td><td class="${cl(x.sim.median)}">${pc(x.sim.median)}</td><td class="${cl(x.sim.bad)}">${pc(x.sim.bad)}</td><td class="neg">${p0(x.sim.fall)}</td><td>${p0(x.sim.lose)}</td></tr>`).join("")}</table></div>`;
}
if(HS){
 const iv=x=>x.interval?`${R(x.interval[0])} to ${R(x.interval[1])}`:"-";
 h+=`<h2 class="serif">Earlier years</h2><p class="verdict serif ${HS.verdict}" style="font-size:24px;max-width:none">${HS.headline}</p><p class="note">${HS.detail}</p>
 <p class="note">These rules were chosen using data from 2019 onward, so trades before ${HS.cutoff} are fresh evidence. The market then was small and thin, so treat this as a warning light, not proof. Days with no trades were filled with flat candles (${Object.entries(HS.coins).map(([k,v])=>k.replace("USD","")+": "+v.filled_days+" days from "+v.start).join(", ")}).</p>
 <div class="wrap"><table><caption>Trades that began before ${HS.cutoff}</caption><tr><th>Rules</th><th>Coin</th><th>Trades</th><th>Won</th><th>Average</th><th>Likely range</th><th>Profit factor</th><th>Gain</th><th>Fall</th></tr>
 ${HS.rows.map(x=>`<tr><td>${x.name}</td><td>${x.coin}</td><td>${x.n}</td><td>${pc(x.win,0)}</td><td class="${cl(x.avg_r)}">${R(x.avg_r)}</td><td>${iv(x)}</td><td>${x.n?x.pf.toFixed(2):"-"}</td><td class="${cl(x.ret)}">${pc(x.ret,0)}</td><td class="neg">${pc(x.mdd,0)}</td></tr>`).join("")}</table></div>`;
}
if(SW){
 const t=m=>`<td>${m.n}</td><td class="${cl(m.avg_r)}">${R(m.avg_r)}</td><td>${m.n?m.pf.toFixed(2):"-"}</td><td class="${cl(m.short.avg_r)}">${m.short.n} (${R(m.short.avg_r)})</td>`;
 const q=m=>`<td class="${cl(m.ann)}">${pc(m.ann,0)}</td><td class="neg">${pc(m.mdd,0)}</td><td>${m.calmar.toFixed(1)}</td>`;
 h+=`<h2 class="serif">Swing and rotation (long and short)</h2><p class="note">${SW.trials} combinations tried. Chosen using only data before ${SW.cut}, then judged on the untouched period. Futures funding and fees are charged. Crypto derivatives for retail customers are restricted in the EU, so check what is legal for you first.</p>
 <p class="verdict serif ${SW.trade_verdict}" style="font-size:22px;max-width:none">Trade systems: ${SW.trade_headline}</p><p class="note">${SW.trade_detail}</p>
 <div class="wrap"><table><caption>Trend rules traded long and short. Short column: number of short trades and their average.</caption><tr><th>Rules</th><th>Trades</th><th>Average</th><th>Profit factor</th><th>Shorts</th><th>Trades</th><th>Average</th><th>Profit factor</th><th>Shorts</th></tr>
 <tr><td></td><td colspan="4">Before ${SW.cut}</td><td colspan="4">After (untouched)</td></tr>
 ${SW.trade_table.map(x=>`<tr><td>${x.name}${x.chosen?" (chosen)":""}</td>${t(x.learn)}${t(x.oos)}</tr>`).join("")}</table></div>
 <p class="verdict serif ${SW.rot_verdict}" style="font-size:22px;max-width:none;margin-top:26px">Rotation: ${SW.rot_headline}</p><p class="note">${SW.rot_detail}</p>
 <div class="wrap"><table><caption>Weekly rotation across 10 coins. Per year = average yearly gain. Fall = worst drop from a peak. Ratio = per year divided by fall.</caption><tr><th>Rules</th><th>Per year</th><th>Fall</th><th>Ratio</th><th>Per year</th><th>Fall</th><th>Ratio</th></tr>
 <tr><td></td><td colspan="3">Before ${SW.cut}</td><td colspan="3">After (untouched)</td></tr>
 ${SW.rot_table.map(x=>`<tr><td>${x.name}${x.chosen?" (chosen)":""}</td>${q(x.learn)}${q(x.oos)}</tr>`).join("")}
 <tr><td>For comparison: just holding BTC</td>${q(SW.hold.learn)}${q(SW.hold.oos)}</tr></table></div>`;
}
h+=`<h2 class="serif">Live signals</h2>`;
if(!S||(!S.orders.length&&!S.positions.length&&!S.closed.length)){h+=`<div class="empty">No signals yet. Start the scanner with <code>python run.py scan --loop</code>. It checks once each time a candle closes (once a day for the daily system).</div>`}
else{
 if(S.orders.length)h+=`<div class="wrap"><table><caption>Waiting for entry</caption><tr><th>Coin</th><th>Type</th><th>Entry order</th><th>Stop</th><th>Cancel after</th></tr>${S.orders.map(o=>`<tr><td>${o.symbol.replace("USDT","")}</td><td>${o.od.kind}</td><td>${o.od.trigger?px(o.od.trigger):"market"}</td><td>${px(o.od.stop)}</td><td>${o.od.expires_t.slice(0,16)}</td></tr>`).join("")}</table></div>`;
 if(S.positions.length)h+=`<div class="wrap" style="margin-top:14px"><table><caption>Open trades</caption><tr><th>Coin</th><th>Entry</th><th>Stop now</th><th>Candles open</th></tr>${S.positions.map(o=>`<tr><td>${o.symbol.replace("USDT","")}</td><td>${px(o.pos.entry)}</td><td>${px(o.pos.stop)}</td><td>${o.pos.bars}</td></tr>`).join("")}</table></div>`;
 if(S.closed.length){const c=S.closed.slice(-15).reverse(),done=S.closed.filter(x=>x.outcome!="not filled"&&x.outcome!="cancelled");
  h+=`<div class="wrap" style="margin-top:14px"><table><caption>Finished. ${done.length} real trades, total ${R(done.reduce((a,x)=>a+x.r,0))}</caption><tr><th>Coin</th><th>Closed</th><th>How it ended</th><th>Result</th></tr>${c.map(x=>`<tr><td>${x.symbol.replace("USDT","")}</td><td>${x.closed.slice(0,16)}</td><td>${x.outcome}</td><td class="${cl(x.r)}">${x.outcome=="not filled"||x.outcome=="cancelled"?"none":R(x.r)}</td></tr>`).join("")}</table></div>`}
}
$("app").innerHTML=h;
if(B&&B.equity.length>1){
 const W=900,H=280,l=58,r=10,t=10,b=24,P=B.equity,T=P.map(p=>+new Date(p[0])),V=P.map(p=>p[1]);
 const x0=T[0],x1=T[T.length-1],lo=Math.min(...V)*.97,hi=Math.max(...V)*1.03;
 const X=a=>l+(a-x0)/(x1-x0||1)*(W-l-r),Y=a=>H-b-(a-lo)/(hi-lo||1)*(H-t-b);
 let pk=0;const HW=V.map(a=>pk=Math.max(pk,a)),pt=(i,a)=>X(T[i]).toFixed(1)+","+Y(a).toFixed(1);
 const eq=V.map((a,i)=>pt(i,a)),hw=HW.map((a,i)=>pt(i,a));
 let g="";for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4;g+=`<line x1="${l}" x2="${W-r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${l-6}" y="${Y(v)+4}" text-anchor="end">$${Math.round(v).toLocaleString()}</text>`}
 let yr="";for(let y=new Date(x0).getUTCFullYear()+1;y<=new Date(x1).getUTCFullYear();y++){const a=Date.UTC(y,0,1);yr+=`<text x="${X(a)}" y="${H-6}" text-anchor="middle">${y}</text>`}
 $("chart").innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Account value over time">${g}${yr}<polygon points="${hw.join(" ")} ${eq.slice().reverse().join(" ")}" fill="var(--wash)"/><polyline points="${eq.join(" ")}" fill="none" stroke="var(--tide)" stroke-width="2.2" pathLength="1000" class="draw" style="--len:1000"/></svg>`;
}
</script></body></html>
"""
