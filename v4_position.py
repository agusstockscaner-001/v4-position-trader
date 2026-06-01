"""
AI Stock Scanner v3 - Multi-Timeframe + Volume Akumulasi + Backtest
Data Yahoo Finance lewat Cloudflare Worker
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import quote

st.set_page_config(page_title="AI Stock Scanner", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

# ============================================================
PROXY = "https://yahoo-proxy.agusstockscaner.workers.dev/?url="
# ============================================================

st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1rem !important; max-width: 100%; }
    .stock-card { background: linear-gradient(135deg,#0f1520,#131929); border:1px solid #1a2535; border-radius:12px; padding:14px; margin-bottom:10px; }
    .priority-card { border:1px solid #2d5a3d; box-shadow:0 0 15px rgba(0,255,136,0.15); }
    .gem-card { border:1px solid #1a3a5a; }
    .trap-card { border:1px solid #5a1a1a; }
    .badge { display:inline-block; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:700; font-family:monospace; }
    .stButton button { width:100%; border-radius:8px; font-weight:600; }
    @media (max-width:768px){ .stock-card{padding:12px;font-size:13px;} h1{font-size:22px!important;} }
</style>
""", unsafe_allow_html=True)

SEKTOR = {
    "BANK": ["BBCA.JK","BBRI.JK","BMRI.JK","BBNI.JK","BBTN.JK","BRIS.JK"],
    "TELCO": ["TLKM.JK","ISAT.JK","EXCL.JK","TOWR.JK"],
    "TAMBANG": ["ADRO.JK","ITMG.JK","PTBA.JK","ANTM.JK","INCO.JK","MDKA.JK","AMMN.JK"],
    "KONSUMER": ["ICBP.JK","INDF.JK","CPIN.JK","JPFA.JK","AMRT.JK","UNVR.JK","MYOR.JK"],
    "ENERGI": ["PGAS.JK","MEDC.JK","ADMR.JK"],
    "INDUSTRI": ["ASII.JK","UNTR.JK","AKRA.JK","SMGR.JK","INTP.JK"],
    "PROPERTI": ["CTRA.JK","SMRA.JK","PWON.JK"],
    "KESEHATAN": ["KLBF.JK","SIDO.JK"],
    "RITEL": ["ACES.JK","MAPI.JK","MAPA.JK"],
    "TEKNOLOGI": ["GOTO.JK"],
}
WATCHLIST = [s for l in SEKTOR.values() for s in l]

@st.cache_data(ttl=300)
def fetch_chart(symbol, rng="1y"):
    yahoo = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d"
    try:
        r = requests.get(PROXY + quote(yahoo, safe=""), timeout=15)
        if r.status_code != 200: return None
        result = r.json()["chart"]["result"][0]
        q = result["indicators"]["quote"][0]
        clean = []
        for o,h,l,c,v in zip(q["open"],q["high"],q["low"],q["close"],q["volume"]):
            if all(x is not None for x in [o,h,l,c,v]) and o>0:
                clean.append((o,h,l,c,v))
        if len(clean) < 50: return None
        o,h,l,c,v = zip(*clean)
        return {"open":list(o),"high":list(h),"low":list(l),"close":list(c),"volume":list(v)}
    except Exception:
        return None

@st.cache_data(ttl=3600)
def fetch_fundamental(symbol):
    yahoo = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=defaultKeyStatistics,financialData,summaryDetail"
    try:
        r = requests.get(PROXY + quote(yahoo, safe=""), timeout=15)
        if r.status_code != 200: return None
        result = r.json()["quoteSummary"]["result"][0]
        ks = result.get("defaultKeyStatistics",{}); fd = result.get("financialData",{}); sd = result.get("summaryDetail",{})
        def safe(d,k):
            v = d.get(k,{}); return v.get("raw") if isinstance(v,dict) else None
        return {"per":safe(sd,"trailingPE") or safe(ks,"trailingPE"),"pbv":safe(ks,"priceToBook"),
                "roe":safe(fd,"returnOnEquity"),"der":safe(fd,"debtToEquity"),"eps_growth":safe(ks,"earningsQuarterlyGrowth")}
    except Exception:
        return None

def ema(d,p):
    if len(d)<p: return []
    out=[sum(d[:p])/p]; m=2/(p+1)
    for x in d[p:]: out.append((x-out[-1])*m+out[-1])
    return out
def rsi(d,p=14):
    if len(d)<p+1: return 50
    g=l=0
    for i in range(1,p+1):
        x=d[-i]-d[-i-1]
        if x>=0: g+=x
        else: l+=abs(x)
    ag,al=g/p,l/p
    if al==0: return 100
    return 100-(100/(1+ag/al))
def macd(d):
    e12,e26=ema(d,12),ema(d,26)
    if not e12 or not e26: return 0,0,0
    n=min(len(e12),len(e26))
    m=[e12[-n+i]-e26[-n+i] for i in range(n)]
    s=ema(m,9)
    h=m[-1]-(s[-1] if s else 0)
    hp=(m[-2]-s[-2]) if len(m)>1 and len(s)>1 else 0
    return m[-1],(s[-1] if s else 0),h-hp

def score_fund(f):
    if not f: return 50,"N/A"
    sc,n=0,0
    if f.get("per") and f["per"]>0:
        per=f["per"]; sc+=90 if per<10 else 80 if per<15 else 65 if per<20 else 45 if per<30 else 25; n+=1
    if f.get("pbv") and f["pbv"]>0:
        pbv=f["pbv"]; sc+=95 if pbv<1 else 80 if pbv<2 else 60 if pbv<3 else 40 if pbv<5 else 20; n+=1
    if f.get("roe") is not None:
        roe=f["roe"]*100; sc+=95 if roe>20 else 80 if roe>15 else 60 if roe>10 else 40 if roe>5 else 25 if roe>0 else 5; n+=1
    if f.get("der") is not None:
        der=f["der"]; sc+=90 if der<50 else 75 if der<100 else 55 if der<150 else 35 if der<200 else 15; n+=1
    if n==0: return 50,"N/A"
    fin=sc/n
    lbl="💎 EXCELLENT" if fin>=75 else "✅ GOOD" if fin>=60 else "⚠️ FAIR" if fin>=45 else "❌ POOR"
    return fin,lbl

def weekly_trend(cl):
    weekly = cl[::5]
    if len(weekly) < 10: return "NETRAL", 0
    we10 = ema(weekly, 10)
    if not we10: return "NETRAL", 0
    if weekly[-1] > we10[-1]: return "BULLISH", 3
    return "BEARISH", -2

def detect_accumulation(cl, vol):
    if len(vol) < 20: return False, 0
    recent_vol = sum(vol[-5:]) / 5
    older_vol = sum(vol[-20:-5]) / 15
    vol_rising = recent_vol > older_vol * 1.2
    pc5 = (cl[-1] - cl[-6]) / cl[-6] * 100 if len(cl) >= 6 else 0
    if vol_rising and -3 < pc5 < 5:
        return True, 5
    return False, 0

def detect_breakout(cl, hi, vol):
    if len(hi) < 21: return False, 0
    resistance = max(hi[-21:-1])
    avg_vol = sum(vol[-20:]) / 20
    if cl[-1] > resistance and vol[-1] > avg_vol * 1.5:
        return True, 6
    return False, 0

# ─── HELPER CEPAT untuk BACKTEST (hitung indikator sekali, bukan tiap hari) ───
def ema_series(d, p):
    """Return full EMA array aligned to d (None untuk index < p-1)."""
    if len(d) < p: return [None]*len(d)
    out = [None]*(p-1)
    sma = sum(d[:p])/p
    out.append(sma)
    m = 2/(p+1)
    prev = sma
    for x in d[p:]:
        prev = (x-prev)*m+prev
        out.append(prev)
    return out

def rsi_series(d, p=14):
    """Return full RSI array aligned to d."""
    out = [None]*len(d)
    if len(d) < p+1: return out
    gains=losses=0
    for i in range(1,p+1):
        ch = d[i]-d[i-1]
        if ch>=0: gains+=ch
        else: losses+=abs(ch)
    ag=gains/p; al=losses/p
    out[p] = 100 if al==0 else 100-(100/(1+ag/al))
    for i in range(p+1,len(d)):
        ch = d[i]-d[i-1]
        g = ch if ch>0 else 0
        l = abs(ch) if ch<0 else 0
        ag = (ag*(p-1)+g)/p
        al = (al*(p-1)+l)/p
        out[i] = 100 if al==0 else 100-(100/(1+ag/al))
    return out

def macd_series(d):
    """Return (macd_line array, signal array) aligned to d."""
    e12 = ema_series(d,12); e26 = ema_series(d,26)
    macd_line = [ (e12[i]-e26[i]) if (e12[i] is not None and e26[i] is not None) else None for i in range(len(d)) ]
    valid = [m for m in macd_line if m is not None]
    sig_valid = ema_series(valid,9) if len(valid)>=9 else []
    signal = [None]*len(d)
    # map signal back to original index
    first_valid = next((i for i,m in enumerate(macd_line) if m is not None), len(d))
    for k,sv in enumerate(sig_valid):
        idx = first_valid + k
        if idx < len(d): signal[idx] = sv
    return macd_line, signal


def analyze(symbol, mbonus, market_regime):
    d = fetch_chart(symbol)
    if not d: return None
    op,hi,lo,cl,vol = d["open"],d["high"],d["low"],d["close"],d["volume"]
    harga = cl[-1]
    e20,e50 = ema(cl,20),ema(cl,50)
    if not e20 or not e50: return None
    avgv = sum(vol[-20:])/20
    vr = vol[-1]/avgv if avgv>0 else 0
    rv = rsi(cl)
    ml,ms,hist_mom = macd(cl)

    score = 0
    detail = []
    if harga>e20[-1]: score+=3; detail.append(("Harga > EMA20 (tren pendek naik)", +3))
    else: detail.append(("Harga < EMA20 (di bawah tren pendek)", 0))
    if harga>e50[-1]: score+=3; detail.append(("Harga > EMA50 (tren menengah naik)", +3))
    else: detail.append(("Harga < EMA50 (di bawah tren menengah)", 0))
    if e20[-1]>e50[-1]: score+=4; detail.append(("EMA20 > EMA50 (golden alignment)", +4))
    else: detail.append(("EMA20 < EMA50 (tren melemah)", 0))
    if 45<=rv<=68: score+=4; detail.append((f"RSI {rv:.0f} (zona ideal 45-68)", +4))
    elif rv>75: score-=4; detail.append((f"RSI {rv:.0f} (overbought >75)", -4))
    else: detail.append((f"RSI {rv:.0f} (di luar zona ideal)", 0))
    if ml>ms: score+=4; detail.append(("MACD di atas signal (momentum naik)", +4))
    else: detail.append(("MACD di bawah signal (momentum lemah)", 0))
    if hist_mom>0: score+=2; detail.append(("Momentum MACD menguat", +2))
    if vr>=1.8: score+=5; detail.append((f"Volume {vr:.1f}x (lonjakan kuat)", +5))
    elif vr>=1.3: score+=3; detail.append((f"Volume {vr:.1f}x (di atas rata-rata)", +3))
    else: detail.append((f"Volume {vr:.1f}x (normal/rendah)", 0))

    wtrend, wbonus = weekly_trend(cl)
    score += wbonus
    detail.append((f"Tren mingguan: {wtrend}", wbonus))
    is_accum, accum_bonus = detect_accumulation(cl, vol)
    score += accum_bonus
    if accum_bonus: detail.append(("🐋 Akumulasi terdeteksi", accum_bonus))
    is_breakout, bo_bonus = detect_breakout(cl, hi, vol)
    score += bo_bonus
    if bo_bonus: detail.append(("🚀 Breakout terkonfirmasi", bo_bonus))

    if market_regime == "🔴 BEARISH":
        if harga > e20[-1] and wtrend == "BULLISH":
            score += 3; detail.append(("Kuat saat market bearish", +3))
        else:
            score += mbonus; detail.append(("Penalti market bearish", mbonus))
    else:
        score += mbonus
        if mbonus: detail.append(("Bonus market regime", mbonus))

    sup = min(lo[-20:]); res = max(hi[-21:-1])
    rr = (res-harga)/(harga-sup) if harga>sup else 0
    crange = hi[-1]-lo[-1]
    if crange<=0: return None
    cpos = (cl[-1]-lo[-1])/crange
    nearhigh = cpos>=0.7

    of = 0
    if nearhigh: of+=3; detail.append(("Candle ditutup dekat high", +3))
    if vr>=1.5: of+=3; detail.append(("Volume mendukung orderflow", +3))
    if cl[-1]>op[-1]: of+=2; detail.append(("Candle hijau (close > open)", +2))

    upper = hi[-1]-cl[-1]; body = abs(cl[-1]-op[-1])
    dist = vr>=2 and upper>body and cpos<0.5
    if dist: score-=6; detail.append(("⚠️ Distribusi (bandar jualan)", -6))
    fake = hi[-1]>res and harga<res and vr>=1.3
    if fake: score-=7; detail.append(("⚠️ Fake breakout (jebakan)", -7))

    # ─── FITUR BARU 1: BIG MONEY FLOW (nilai transaksi Rp) ───
    value_trx = harga * vol[-1]
    avg_value = harga * avgv
    value_ratio = value_trx/avg_value if avg_value>0 else 0
    big_money = "NORMAL"
    if value_trx >= 100_000_000_000 and value_ratio >= 1.8:
        score += 6; big_money = "🐋 EXTREME FLOW"; detail.append(("🐋 Big Money: EXTREME FLOW", +6))
    elif value_trx >= 40_000_000_000 and value_ratio >= 1.5:
        score += 4; big_money = "🐳 STRONG FLOW"; detail.append(("🐳 Big Money: STRONG FLOW", +4))
    elif value_trx >= 15_000_000_000 and value_ratio >= 1.3:
        score += 2; big_money = "🟢 HEALTHY FLOW"; detail.append(("🟢 Big Money: HEALTHY FLOW", +2))

    # ─── FITUR BARU 2: ENTRY GRADING (hindari FOMO) ───
    dist_ema20 = (harga - e20[-1])/e20[-1]*100
    if dist_ema20 > 5:
        score -= 4; entry_grade = "D ❌ FOMO"; detail.append(("❌ Entry FOMO (harga jauh di atas EMA20)", -4))
    elif dist_ema20 > 3:
        score -= 2; entry_grade = "C ⚠️ Tinggi"; detail.append(("⚠️ Entry agak tinggi", -2))
    elif dist_ema20 < 1.5:
        score += 2; entry_grade = "A ✅ Sniper"; detail.append(("✅ Entry Sniper (dekat EMA20)", +2))
    else:
        entry_grade = "B ✅ Bagus"

    fp = score + of
    fund = fetch_fundamental(symbol)
    fs,fl = score_fund(fund)
    if fs<30: fp-=8

    # Tag kualitas (dihitung dulu, jadi syarat keputusan)
    tags = []
    if is_accum: tags.append("🐋 Akumulasi")
    if is_breakout: tags.append("🚀 Breakout")
    if wtrend=="BULLISH": tags.append("📈 Weekly Bull")
    if hist_mom>0: tags.append("⚡ MACD↑")
    if big_money != "NORMAL": tags.append(big_money)

    # Syarat kualitas: ada akumulasi ATAU breakout = jejak "smart money"
    smart_money = is_accum or is_breakout

    # ─── KEPUTUSAN (DI-TUNING: LEBIH LONGGAR) ───
    if fake or dist: dec="🚫 AVOID"
    elif fp>=28 and rr>=1.4 and fs>=45 and smart_money: dec="🔥 PRIORITY BUY"
    elif fp>=20 and rr>=1.2 and fs>=40 and (smart_money or wtrend=="BULLISH"): dec="🎯 SWING TARGET"
    elif fp>=12: dec="👀 WATCH"
    else: dec="🚫 AVOID"

    if fake or dist or fs<30: risk="HIGH"
    elif rr>=1.8 and nearhigh and fs>=60 and smart_money: risk="LOW"
    else: risk="MEDIUM"

    conf = max(0,min(95,int(fp*2.3+(fs-50)*0.2)))
    tpct = ((res-harga)/harga)*100
    slpct = ((harga-sup)/harga)*100

    flow = "🐋 ACCUMULATION" if is_accum else "⚠️ DISTRIBUTION" if dist else "NORMAL"
    sector = next((s for s,l in SEKTOR.items() if symbol in l),"LAINNYA")
    return {"symbol":symbol.replace(".JK",""),"sector":sector,"harga":harga,
            "change":(cl[-1]-cl[-2])/cl[-2]*100,"fp":fp,"rr":rr,"conf":conf,"risk":risk,
            "flow":flow,"dec":dec,"fs":fs,"fl":fl,"tpct":tpct,"slpct":slpct,"rsi":rv,"vr":vr,
            "is_gem":fp>=22 and fs>=70,"is_trap":fp>=22 and fs<40,"chart":cl[-30:],
            "tags":tags,"wtrend":wtrend,"is_accum":is_accum,"is_breakout":is_breakout,
            "entry_grade":entry_grade,"big_money":big_money,"value_trx":value_trx,"detail":detail}

def regime():
    d = fetch_chart("^JKSE", rng="6mo")
    if not d: return "UNKNOWN",0
    cl = d["close"]; e20,e50 = ema(cl,20),ema(cl,50)
    if not e20 or not e50: return "UNKNOWN",0
    h = cl[-1]
    if h>e20[-1]>e50[-1]: return "🟢 STRONG BULLISH",4
    elif h>e50[-1]: return "🟡 NEUTRAL",0
    return "🔴 BEARISH",-4

@st.cache_data(ttl=3600)
def backtest_symbol(symbol, target_pct=15, sl_pct=8, hold_days=40):
  try:
    d = fetch_chart(symbol, rng="2y")
    if not d: return None
    cl,hi,lo,vol = d["close"],d["high"],d["low"],d["volume"]
    n = len(cl)
    if n < 150: return None
    # POSITION TRADING: pakai EMA50 & EMA100 (tren menengah-panjang)
    e50s = ema_series(cl,50)
    e100s = ema_series(cl,100)
    rsis = rsi_series(cl)
    macd_line, macd_sig = macd_series(cl)
    wins=total=losses=0
    for i in range(120, n-hold_days, 5):  # step 5 hari (lebih jarang, sesuai timeframe)
        if e50s[i] is None or e100s[i] is None or rsis[i] is None: continue
        if macd_line[i] is None or macd_sig[i] is None: continue
        e50=e50s[i]; e100=e100s[i]; rv=rsis[i]; ml=macd_line[i]; ms=macd_sig[i]
        avgv = sum(vol[i-50:i])/50  # rata-rata 50 hari (lebih stabil)
        vr = vol[i]/avgv if avgv>0 else 0
        # Akumulasi jangka menengah (volume 30 hari vs 60 hari)
        rec_vol = sum(vol[i-30:i])/30; old_vol = sum(vol[i-60:i-30])/30
        pc30 = (cl[i]-cl[i-30])/cl[i-30]*100 if i>=30 else 0
        is_accum = old_vol>0 and rec_vol > old_vol*1.15 and pc30 > -5
        # Weekly bullish: tren 60 hari naik (penting untuk position trading)
        wk_bull_strong = cl[i] > cl[i-60] * 1.05 if i>=60 else False  # naik >5% dalam 3 bulan
        # Tren menengah confirmed: harga > EMA50 > EMA100 (golden alignment menengah)
        trend_strong = cl[i] > e50 > e100
        # R/R untuk position: support 30 hari, target dari resistance 60 hari atau proyeksi 15%
        sup = min(lo[i-30:i])
        res = max(hi[i-60:i])
        if res <= cl[i]*1.05: res = cl[i]*1.15  # target proyeksi +15%
        risk = cl[i]-sup
        rr = (res-cl[i])/risk if risk>0 else 0
        # anti-FOMO untuk position: max 15% di atas EMA50 (tren menengah)
        not_fomo = (cl[i]-e50)/e50*100 <= 15
        # SINYAL POSITION: tren menengah kuat + weekly konfirmasi + RSI sehat + R/R OK
        sig = (trend_strong
               and 40<=rv<=70
               and ml>ms
               and wk_bull_strong
               and (is_accum or vr>=1.2)
               and rr>=1.3
               and not_fomo)
        if sig:
            entry = cl[i]
            # Cek 40 hari ke depan: kena target dulu atau stop loss dulu?
            future_high = max(hi[i+1:i+1+hold_days])
            future_low = min(lo[i+1:i+1+hold_days])
            gain_max = (future_high-entry)/entry*100
            loss_max = (future_low-entry)/entry*100
            total+=1
            # Menang kalau naik ≥target SEBELUM kena stop loss
            if gain_max >= target_pct and loss_max > -sl_pct:
                wins+=1
            elif loss_max <= -sl_pct:
                losses+=1
    if total==0: return None
    return {"symbol":symbol.replace(".JK",""),"total":total,"wins":wins,
            "losses":losses,"win_rate":wins/total*100}
  except Exception:
    return None

fmtp = lambda p:"Rp "+format(round(p),",")

c1,c2 = st.columns([3,1])
with c1:
    st.markdown("# 🎯 🎯 V4 Position Trader")
    st.caption(f"LQ45 · Position 1-2 bulan · Target 15% · EMA50/100 + Weekly Bullish · {datetime.now().strftime('%d %b %Y · %H:%M')}")
with c2:
    if st.button("🔄 Refresh", use_container_width=True, type="primary"):
        st.cache_data.clear(); st.rerun()

reg,bonus = regime()
if reg=="UNKNOWN":
    st.error("⚠️ Gagal ambil data IHSG. Coba Refresh.")
else:
    st.info(f"**Market Regime IHSG:** {reg}")

if 'results' not in st.session_state:
    st.session_state.results=None
if st.session_state.results is None:
    prog = st.progress(0,text="Memindai saham...")
    res=[]
    for i,s in enumerate(WATCHLIST):
        prog.progress((i+1)/len(WATCHLIST),text=f"Scanning {s}... ({i+1}/{len(WATCHLIST)})")
        r = analyze(s,bonus,reg)
        if r: res.append(r)
    prog.empty()
    # ─── FITUR BARU 3: SECTOR ROTATION ───
    # Hitung total skor per sektor, sektor terkuat dapat highlight + bonus confidence
    sektor_total = {}
    for r in res:
        sektor_total[r["sector"]] = sektor_total.get(r["sector"],0) + r["fp"]
    top_sektor = sorted(sektor_total.items(), key=lambda x:x[1], reverse=True)[:3]
    top_sektor_names = [s[0] for s in top_sektor]
    # Beri bonus ke saham di sektor terkuat (rotasi sektor)
    for r in res:
        if r["sector"] in top_sektor_names:
            r["conf"] = min(95, r["conf"]+5)
            r["in_hot_sector"] = True
            if "🔥 Hot Sector" not in r["tags"]: r["tags"].append("🔥 Hot Sector")
        else:
            r["in_hot_sector"] = False
    st.session_state.top_sektor = top_sektor
    st.session_state.results = sorted(res,key=lambda x:x["conf"],reverse=True)
results = st.session_state.results or []
top_sektor = st.session_state.get("top_sektor", [])

# Tampilkan sektor terkuat
if top_sektor:
    sektor_txt = " · ".join([f"{s[0]} ({int(v)})" for s,v in [(t,t[1]) for t in top_sektor]])
    st.caption(f"🔥 **Sektor Terkuat Hari Ini:** " + " · ".join([f"{s[0]}" for s in top_sektor]))

def card(s,cls="stock-card"):
    color = {"🔥 PRIORITY BUY":"#00ff88","🎯 SWING TARGET":"#4da6ff","👀 WATCH":"#ffd32a","🚫 AVOID":"#ff4757"}.get(s["dec"],"#888")
    tp = s["harga"]*(1+s["tpct"]/100); sl = s["harga"]*(1-s["slpct"]/100)
    cc = "#00ff88" if s["change"]>=0 else "#ff4757"; cs = "+" if s["change"]>=0 else ""
    tags_html = " ".join([f'<span class="badge" style="background:#1a3a2a;color:#7fffd4;">{t}</span>' for t in s.get("tags",[])])
    st.markdown(f"""<div class="stock-card {cls}">
    <div style="display:flex;justify-content:space-between;margin-bottom:10px;">
    <div><div style="font-size:20px;font-weight:800;color:#fff;">{s['symbol']}</div>
    <div style="font-size:11px;color:#888;">{s['sector']}</div></div>
    <div style="text-align:right;"><div style="font-size:18px;font-weight:700;color:#fff;">{fmtp(s['harga'])}</div>
    <div style="font-size:12px;color:{cc};">{cs}{s['change']:.2f}%</div></div></div>
    <div style="background:#0a0d14;border-radius:8px;padding:10px;margin-bottom:10px;">
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center;">
    <div><div style="font-size:10px;color:#666;">CONFIDENCE</div><div style="font-size:18px;font-weight:700;color:{color};">{s['conf']}%</div></div>
    <div><div style="font-size:10px;color:#666;">TARGET</div><div style="font-size:16px;font-weight:700;color:#00ff88;">+{s['tpct']:.1f}%</div></div>
    <div><div style="font-size:10px;color:#666;">R/R</div><div style="font-size:16px;font-weight:700;color:#ffd32a;">{s['rr']:.1f}x</div></div></div></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;font-size:12px;">
    <div style="background:#0a0d14;padding:6px 10px;border-radius:6px;"><span style="color:#666;">🎯 Target:</span> <span style="color:#fff;">{fmtp(tp)}</span></div>
    <div style="background:#0a0d14;padding:6px 10px;border-radius:6px;"><span style="color:#666;">🛑 Stop:</span> <span style="color:#fff;">{fmtp(sl)}</span></div></div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px;">
    <span class="badge" style="background:{color}22;color:{color};border:1px solid {color}66;">{s['dec']}</span>
    <span class="badge" style="background:#2a4060;color:#ccc;">Fund: {s['fl']}</span>
    <span class="badge" style="background:#2a4060;color:#ccc;">Risk: {s['risk']}</span></div>
    <div style="margin-bottom:6px;">{tags_html}</div>
    <div style="font-size:11px;color:#666;">RSI: {s['rsi']:.0f} · Vol: {s['vr']:.1f}x · Entry: {s.get('entry_grade','-')} · Weekly: {s['wtrend']} · Flow: {s['flow']}</div></div>""",unsafe_allow_html=True)

t1,t2,t3,t4,t5,t6,t7 = st.tabs(["🔥 Hotlist","💎 Hidden Gem","⚠️ Value Trap","📊 Semua","🔬 Detail Analisa","🧪 Backtest","ℹ️ Info"])
with t1:
    hot = [s for s in results if "PRIORITY BUY" in s["dec"] or "SWING TARGET" in s["dec"]]
    st.markdown(f"### 🔥 {len(hot)} Sinyal Buy")
    st.caption("Tag 🐋 Akumulasi / 🚀 Breakout / 📈 Weekly Bull = kualitas lebih tinggi")
    if not hot: st.info("Tidak ada sinyal kuat saat ini.")
    for s in hot: card(s,"priority-card")
with t2:
    gems = [s for s in results if s["is_gem"]]
    st.markdown(f"### 💎 {len(gems)} Hidden Gem")
    if not gems: st.info("Belum ada hidden gem.")
    for s in gems: card(s,"gem-card")
with t3:
    traps = [s for s in results if s["is_trap"]]
    st.markdown(f"### ⚠️ {len(traps)} Value Trap")
    if not traps: st.info("Tidak ada value trap.")
    for s in traps: card(s,"trap-card")
with t4:
    st.markdown(f"### 📊 Semua ({len(results)})")
    mc = st.slider("Min Confidence",0,95,40,5)
    fil = [s for s in results if s["conf"]>=mc]
    if fil:
        df = pd.DataFrame([{"Saham":s["symbol"],"Sektor":s["sector"],"Harga":fmtp(s["harga"]),
            "Conf%":s["conf"],"Target%":f"+{s['tpct']:.1f}","R/R":f"{s['rr']:.1f}x",
            "Weekly":s["wtrend"],"Sinyal":s["dec"].split()[1] if " " in s["dec"] else s["dec"]} for s in fil])
        st.dataframe(df,use_container_width=True,hide_index=True,height=500)
with t5:
    st.markdown("### 🔬 Detail Analisa Teknikal")
    st.caption("Rincian skor per indikator + fitur AI v4 (Big Money, Entry Grade). Pahami KENAPA sinyal muncul.")
    if results:
        nama_list = [f"{s['symbol']} — {s['dec']} (Conf {s['conf']}%)" for s in results]
        pilih = st.selectbox("Pilih saham untuk dianalisa:", range(len(results)),
                             format_func=lambda i: nama_list[i])
        s = results[pilih]
        cc1,cc2,cc3,cc4 = st.columns(4)
        cc1.metric("Harga", fmtp(s["harga"]), f"{s['change']:+.2f}%")
        cc2.metric("Confidence", f"{s['conf']}%")
        cc3.metric("Target", f"+{s['tpct']:.1f}%")
        cc4.metric("R/R", f"{s['rr']:.1f}x")
        st.markdown(f"**Sinyal:** {s['dec']} · **Sektor:** {s['sector']} · **Weekly:** {s['wtrend']} · **Fundamental:** {s['fl']}")
        # Fitur khusus v4
        st.markdown(f"**🎯 Entry Grade:** {s.get('entry_grade','-')} · **💰 Big Money:** {s.get('big_money','NORMAL')}")
        st.markdown("---")
        st.markdown("#### 📊 Rincian Skor per Indikator")
        detail = s.get("detail",[])
        if detail:
            rows = []
            for nama, poin in detail:
                emoji = "🟢" if poin>0 else "🔴" if poin<0 else "⚪"
                rows.append({"":emoji,"Indikator":nama,"Poin":f"{poin:+d}" if poin!=0 else "0"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(460, 40*(len(rows)+1)))
            st.markdown(f"### Total Skor Teknikal: **{s['fp']:.0f}** poin")
            st.caption(f"Skor teknikal {s['fp']:.0f} + fundamental ({s['fl']}) → Confidence {s['conf']}%. Sinyal akhir: {s['dec']}")
            st.markdown("---")
            st.markdown("#### 💡 Cara Baca")
            st.markdown("""
            - 🟢 **Poin plus** = faktor mendukung kenaikan
            - 🔴 **Poin minus** = faktor risiko (overbought, distribusi, FOMO, fake breakout)
            - ⚪ **Nol** = netral

            **Khusus v4:** Entry Grade A/B = waktu masuk bagus; C/D = harga sudah tinggi (rawan FOMO).
            Big Money FLOW = ada aliran dana besar (jejak institusi/bandar).
            """)
        else:
            st.info("Rincian tidak tersedia untuk saham ini.")
    else:
        st.info("Belum ada data. Klik Refresh dulu.")
with t6:
    st.markdown("### 🧪 Backtest Strategi")
    st.caption("Uji: berapa % sinyal historis yang BENAR naik ≥15% dalam 40 hari kerja (~2 bulan, data 2 tahun). Win rate JUJUR.")
    if st.button("▶️ Jalankan Backtest (±2 menit)"):
        prog2 = st.progress(0,text="Backtesting...")
        bt=[]; gagal=[]
        for i,s in enumerate(WATCHLIST):
            prog2.progress((i+1)/len(WATCHLIST),text=f"Backtest {s}... ({i+1}/{len(WATCHLIST)})")
            try:
                r = backtest_symbol(s)
                if r and r["total"]>=1: bt.append(r)
            except Exception:
                gagal.append(s.replace(".JK",""))
                continue
        prog2.empty()
        if gagal:
            st.caption(f"ℹ️ {len(gagal)} saham dilewati (data tidak lengkap): {', '.join(gagal)}")
        if bt:
            tt = sum(r["total"] for r in bt); tw = sum(r["wins"] for r in bt)
            wr = tw/tt*100 if tt else 0
            st.metric("📊 Win Rate Keseluruhan", f"{wr:.1f}%", f"{tw}/{tt} trades")
            st.caption(f"Dari {tt} sinyal historis, {tw} berhasil naik ≥15% dalam 40 hari.")
            df_bt = pd.DataFrame([{"Saham":r["symbol"],"Total Sinyal":r["total"],
                "Menang":r["wins"],"Win Rate":f"{r['win_rate']:.0f}%"} for r in sorted(bt,key=lambda x:x["win_rate"],reverse=True)])
            st.dataframe(df_bt,use_container_width=True,hide_index=True,height=400)
            if wr < 50:
                st.warning("⚠️ Win rate di bawah 50%. Strategi belum andal — jangan over-trade.")
            elif wr < 60:
                st.info("Win rate 50-60% — wajar untuk swing. Manajemen risiko tetap kunci.")
            else:
                st.success("Win rate di atas 60% — bagus, tapi tetap pakai stop loss. Masa lalu ≠ jaminan masa depan.")
        else:
            st.warning("Tidak ada hasil backtest. Coba Refresh & jalankan lagi.")
with t7:
    st.markdown("""
    ### ℹ️ Apa yang Baru di v3
    
    **Filter baru untuk sinyal lebih akurat:**
    - 🐋 **Volume Akumulasi** — deteksi bandar mengumpulkan saham (volume naik + harga stabil)
    - 🚀 **Breakout Konfirmasi** — harga tembus resistance + volume besar
    - 📈 **Multi-Timeframe** — cek tren mingguan, bukan cuma harian
    - ⚡ **MACD Momentum** — deteksi momentum menguat
    - 🧪 **Backtest** — uji win rate strategi di data 1 tahun (jujur!)
    
    **Tag pada kartu** menunjukkan kekuatan sinyal. Makin banyak tag = makin kuat.
    
    ### 🎯 Cara Pakai untuk Cari Kenaikan
    1. Cek tab **Hotlist** — fokus yang punya tag 🐋/🚀/📈
    2. Jalankan **Backtest** dulu untuk tahu win rate realistis
    3. Pilih saham dengan **R/R ≥ 1.5** (reward > risiko)
    4. Konfirmasi dengan volume & berita
    
    ### ⚠️ Disclaimer Penting
    - **TIDAK ADA** yang bisa prediksi pasti saham naik
    - Confidence & backtest = probabilitas, BUKAN jaminan
    - Win rate realistis swing: 55-65% (bahkan profesional)
    - **Selalu pakai stop loss** — ~40% sinyal akan salah
    - Manajemen risiko > akurasi prediksi
    - Tools edukasi, keputusan & risiko di tangan kamu
    - Jangan investasi uang yang tidak siap rugi
    """)
