import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
from pykrx import stock
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="KRX Sector Dashboard", layout="wide", initial_sidebar_state="expanded")

SECTOR_ETFS = {
    "Semiconductor": "091160", "Battery": "364990", "Bio": "244580",
    "Bank": "091170", "Auto": "091180", "Securities": "102970",
    "IT": "266370", "EnergyChem": "117460", "Steel": "117680",
    "Construction": "117700", "Transport": "140710", "MediaEnter": "266360",
    "Machinery": "102960", "Insurance": "140700", "Distribution": "091220",
    "Staples": "266390", "Discretionary": "266400", "KOSPI200": "069500",
}
SECTOR_LIST = list(SECTOR_ETFS.keys()) + ["Other"]
WATCHLIST_FILE = "watchlist.json"
WATCHLIST_DB = "watchlist.db"
DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "local").lower() == "cloud"

def get_kst_now(): return datetime.utcnow() + timedelta(hours=9)
def is_market_open():
    now = get_kst_now()
    if now.weekday() >= 5: return False, "Closed (Weekend)"
    mo = now.replace(hour=9, minute=0, second=0, microsecond=0)
    mc = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now < mo: return False, "Pre-market"
    elif now > mc: return False, "Market Closed"
    return True, "Market Open"
def get_nearest_business_day(d):
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d

def load_watchlist():
    if DEPLOY_MODE:
        try:
            import sqlite3
            conn = sqlite3.connect(WATCHLIST_DB)
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS watchlist (sector TEXT, name TEXT, ticker TEXT, alert_threshold REAL DEFAULT 3.0, quantity INTEGER DEFAULT 0, buy_price REAL DEFAULT 0, PRIMARY KEY (sector, ticker))")
            conn.commit()
            c.execute("SELECT sector, name, ticker, alert_threshold, quantity, buy_price FROM watchlist")
            rows = c.fetchall(); conn.close()
            result = {s: [] for s in SECTOR_LIST}
            for r in rows: result[r[0]].append({"name": r[1], "ticker": r[2], "alert_threshold": r[3], "quantity": r[4], "buy_price": r[5]})
            return result
        except: pass
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for s in SECTOR_LIST:
                for item in data.get(s, []):
                    item.setdefault("alert_threshold", 3.0); item.setdefault("quantity", 0); item.setdefault("buy_price", 0)
            return data
    return {s: [] for s in SECTOR_LIST}

def save_watchlist(wl):
    if DEPLOY_MODE:
        try:
            import sqlite3
            conn = sqlite3.connect(WATCHLIST_DB)
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS watchlist (sector TEXT, name TEXT, ticker TEXT, alert_threshold REAL DEFAULT 3.0, quantity INTEGER DEFAULT 0, buy_price REAL DEFAULT 0, PRIMARY KEY (sector, ticker))")
            c.execute("DELETE FROM watchlist")
            for s, items in wl.items():
                for item in items:
                    c.execute("INSERT INTO watchlist VALUES (?,?,?,?,?,?)", (s, item["name"], item["ticker"], item.get("alert_threshold", 3.0), item.get("quantity", 0), item.get("buy_price", 0)))
            conn.commit(); conn.close(); return
        except: pass
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

def init_watchlist():
    if "watchlist" not in st.session_state: st.session_state.watchlist = load_watchlist()
init_watchlist()

@st.cache_data(ttl=300)
def get_sector_performance(ticker, days):
    try:
        end = get_kst_now(); start = end - timedelta(days=days + 15)
        df = fdr.DataReader(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
        if len(df) < 2: return None
        sp = df['Close'].iloc[0]; ep = df['Close'].iloc[-1]
        return {"price": int(ep), "change_pct": round((ep-sp)/sp*100, 2), "volume_bil": round((df['Volume']*df['Close']).mean()/1e8, 1)}
    except: return None

@st.cache_data(ttl=300)
def get_stock_data(ticker, days):
    try:
        end = get_kst_now(); start = end - timedelta(days=days + 15)
        df = fdr.DataReader(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
        if len(df) < 2: return None, None
        chg = (df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100
        info = {"price": int(df['Close'].iloc[-1]), "change_pct": round(chg, 2), "volume_bil": round((df['Volume'].iloc[-1]*df['Close'].iloc[-1])/1e8, 1), "high": int(df['High'].max()), "low": int(df['Low'].min())}
        return info, df
    except: return None, None

@st.cache_data(ttl=300)
def search_ticker(name_or_code):
    try:
        kospi = fdr.StockListing('KOSPI'); kosdaq = fdr.StockListing('KOSDAQ')
        all_list = pd.concat([kospi, kosdaq])
        matched = all_list[(all_list['Name'].str.contains(name_or_code, case=False, na=False)) | (all_list['Code'].str.contains(name_or_code, na=False))]
        if len(matched) == 0: return None, None
        return matched.iloc[0]['Name'], matched.iloc[0]['Code']
    except: return None, None

@st.cache_data(ttl=300)
def get_fundamental(ticker):
    try:
        today = get_nearest_business_day(datetime.strptime(get_kst_now().strftime('%Y%m%d'), '%Y%m%d')).strftime('%Y%m%d')
        for market in ['KOSPI', 'KOSDAQ']:
            try:
                df = stock.get_market_fundamental_by_ticker(today, market=market)
                if ticker in df.index:
                    row = df.loc[ticker]
                    return {"PER": round(row['PER'], 2) if 'PER' in row else None, "PBR": round(row['PBR'], 2) if 'PBR' in row else None, "DIV": round(row['DIV'], 2) if 'DIV' in row else None, "EPS": round(row['EPS'], 0) if 'EPS' in row else None, "BPS": round(row['BPS'], 0) if 'BPS' in row else None}
            except: continue
        return None
    except: return None

@st.cache_data(ttl=300)
def get_net_purchase(ticker, days):
    try:
        end = get_kst_now(); start = end - timedelta(days=days + 15)
        end_str = get_nearest_business_day(end).strftime('%Y%m%d'); start_str = get_nearest_business_day(start).strftime('%Y%m%d')
        result = {}
        for market in ['KOSPI', 'KOSDAQ']:
            try:
                for investor in ['Foreign', 'Institutional']:
                    df = stock.get_market_net_purchases_of_equities_by_ticker(start_str, end_str, market, investor)
                    if ticker in df.index:
                        result[f"{investor}_net_bil"] = round(df.loc[ticker, '순매수거래대금'] / 1e8, 1)
                if result: return result
            except: continue
        return result if result else None
    except: return None

@st.cache_data(ttl=300)
def get_top_stocks_by_market_cap(limit=200):
    try:
        today = get_nearest_business_day(datetime.strptime(get_kst_now().strftime('%Y%m%d'), '%Y%m%d')).strftime('%Y%m%d')
        all_stocks = []
        for market in ['KOSPI', 'KOSDAQ']:
            try:
                df = stock.get_market_ohlcv_by_ticker(today, market=market)
                df = df[['종가', '등락률', '거래대금', '시가총액']].copy()
                df['market'] = market; df['ticker'] = df.index; all_stocks.append(df)
            except: continue
        if not all_stocks: return None
        combined = pd.concat(all_stocks).sort_values('시가총액', ascending=False).head(limit).reset_index(drop=True)
        name_map = {}
        for market in ['KOSPI', 'KOSDAQ']:
            try:
                listing = fdr.StockListing(market)
                for _, row in listing.iterrows(): name_map[row['Code']] = row['Name']
            except: continue
        combined['name'] = combined['ticker'].map(name_map)
        return combined
    except: return None

@st.cache_data(ttl=300)
def get_kosdaq_sectors():
    try:
        tickers = stock.get_index_ticker_list(market="KOSDAQ")
        sectors = []
        for t in tickers: sectors.append({"code": t, "name": stock.get_index_ticker_name(t)})
        return pd.DataFrame(sectors)
    except: return None

@st.cache_data(ttl=300)
def get_kosdaq_sector_performance(ticker, days):
    try:
        end = get_kst_now(); start = end - timedelta(days=days + 15)
        end_str = get_nearest_business_day(end).strftime('%Y%m%d'); start_str = get_nearest_business_day(start).strftime('%Y%m%d')
        df = stock.get_index_ohlcv_by_date(start_str, end_str, ticker, market="KOSDAQ")
        if len(df) < 2: return None
        change = (df['종가'].iloc[-1] - df['종가'].iloc[0]) / df['종가'].iloc[0] * 100
        return {"index": round(df['종가'].iloc[-1], 2), "change_pct": round(change, 2)}
    except: return None

st_autorefresh(interval=60*1000, limit=None, key="clock_refresh")
now_kst = get_kst_now(); market_open, market_status = is_market_open(); status_color = "🟢" if market_open else "🔴"
hc1, hc2 = st.columns([4, 1])
with hc1: st.title("KRX Sector & Watchlist Dashboard")
with hc2: st.markdown(f'<div style="text-align:right;padding-top:10px;"><span style="font-size:1.1rem;font-weight:bold;">{now_kst.strftime("%Y-%m-%d %H:%M")}</span><br><span style="font-size:0.9rem;">{status_color} {market_status}</span></div>', unsafe_allow_html=True)

def check_alerts():
    alerts = []
    for s, items in st.session_state.watchlist.items():
        for item in items:
            thr = item.get("alert_threshold", 3.0)
            if thr <= 0: continue
            info, _ = get_stock_data(item["ticker"], 1)
            if info and abs(info["change_pct"]) >= thr:
                direction = "UP" if info["change_pct"] > 0 else "DOWN"
                alerts.append(f"**{item['name']}** {direction} {info['change_pct']:+.2f}% (threshold: {thr}%)")
    return alerts
alerts = check_alerts()
if alerts: st.info("🔔 **Alerts**\\n\\n" + "\\n\\n".join(alerts))

st.sidebar.header("⚙️ Settings")
period_days = st.sidebar.selectbox("Period", [("1D",1),("3D",3),("1W",5),("2W",10),("1M",20),("3M",60)], format_func=lambda x:x[0], index=2)[1]
st.sidebar.divider(); st.sidebar.header("⭐ Add Watchlist")
with st.sidebar.form("add_watchlist", clear_on_submit=True):
    sector_sel = st.selectbox("Sector", SECTOR_LIST)
    stock_input = st.text_input("Stock name or ticker")
    alert_thr = st.number_input("Alert threshold (%)", min_value=0.0, max_value=50.0, value=3.0, step=0.5)
    qty = st.number_input("Quantity", min_value=0, value=0, step=1)
    buy_p = st.number_input("Buy price (KRW)", min_value=0, value=0, step=1000)
    if st.form_submit_button("➕ Add") and stock_input:
        name, ticker = search_ticker(stock_input)
        if name and ticker:
            wl = st.session_state.watchlist
            if any(i["ticker"]==ticker for i in wl.get(sector_sel,[])): st.sidebar.warning(f"{name} already exists")
            else:
                wl.setdefault(sector_sel, []).append({"name":name,"ticker":ticker,"alert_threshold":alert_thr,"quantity":qty,"buy_price":buy_p})
                save_watchlist(wl); st.sidebar.success(f"✅ {name} added!"); st.rerun()
        else: st.sidebar.error("Stock not found")
if DEPLOY_MODE: st.sidebar.success("Cloud mode (SQLite)")
else: st.sidebar.info("Local mode (JSON)")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Sector Dashboard", "⭐ Watchlist", "🔍 Stock Search", "🏆 Top Ranking", "📉 KOSDAQ Sectors", "🏭 Sector Top10"])

with tab1:
    st.subheader(f"KOSPI Sector ETF Performance ({period_days}D)")
    progress = st.progress(0); results = []
    for i, (name, ticker) in enumerate(SECTOR_ETFS.items()):
        data = get_sector_performance(ticker, period_days)
        if data: results.append({"Sector": name, "Ticker": ticker, **data})
        progress.progress((i+1)/len(SECTOR_ETFS))
    progress.empty()
    if results:
        df = pd.DataFrame(results).sort_values("change_pct", ascending=False)
        cols = st.columns(3); medals = ["🥇","🥈","🥉"]
        for idx in range(min(3, len(df))):
            row = df.iloc[idx]
            with cols[idx]: st.metric(label=f"{medals[idx]} {row['Sector']}", value=f"{row['price']:,} KRW", delta=f"{row['change_pct']:+.2f}%")
        st.divider(); st.subheader("🗺️ Sector Heatmap")
        heatmap_cols = st.columns(6)
        for idx, (_, row) in enumerate(df.iterrows()):
            col_idx = idx % 6; change = row["change_pct"]
            if change > 0: bg = f"rgba(34,197,94,{min(change/10,1.0)})"; tc = "#fff" if change > 5 else "#000"
            elif change < 0: bg = f"rgba(239,68,68,{min(abs(change)/10,1.0)})"; tc = "#fff" if change < -5 else "#000"
            else: bg = "#9ca3af"; tc = "#000"
            with heatmap_cols[col_idx]: st.markdown(f'<div style="background-color:{bg};padding:12px;border-radius:8px;text-align:center;margin-bottom:8px;"><div style="font-weight:bold;font-size:0.9rem;color:{tc};">{row["Sector"]}</div><div style="font-size:1.1rem;font-weight:bold;color:{tc};">{change:+.2f}%</div></div>', unsafe_allow_html=True)
        st.divider()
        def color_change(val):
            if isinstance(val, (int, float)):
                if val > 0: return "color: #22c55e; font-weight: bold"
                elif val < 0: return "color: #ef4444; font-weight: bold"
            return ""
        st.dataframe(df.style.map(color_change, subset=["change_pct"]), use_container_width=True, hide_index=True)
        df["color"] = df["change_pct"].apply(lambda x: "Up" if x > 0 else "Down" if x < 0 else "Flat")
        fig = px.bar(df, x="Sector", y="change_pct", color="color", color_discrete_map={"Up":"#22c55e","Down":"#ef4444","Flat":"#9ca3af"}, text="change_pct", height=500)
        fig.update_traces(texttemplate="%{text}%", textposition="outside"); fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("📈 Top 5 Sector Trend")
        top5 = df.head(5)["Sector"].tolist(); end = get_kst_now(); start = end - timedelta(days=period_days + 15)
        fig_line = go.Figure()
        for sector in top5:
            ticker = SECTOR_ETFS[sector]
            try:
                hist = fdr.DataReader(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
                if len(hist) > 0:
                    norm = hist['Close'] / hist['Close'].iloc[0] * 100
                    fig_line.add_trace(go.Scatter(x=norm.index, y=norm.values, mode='lines', name=sector))
            except: pass
        fig_line.update_layout(title="Relative Return (Start=100)", xaxis_title="Date", yaxis_title="Relative Return", height=400, hovermode='x unified')
        st.plotly_chart(fig_line, use_container_width=True)
    else: st.warning("Failed to load sector data.")

with tab2:
    st.subheader("⭐ My Watchlist")
    wl = st.session_state.watchlist; has_any = any(len(items) > 0 for items in wl.values())
    if not has_any: st.info("No watchlist items yet. Add from sidebar!")
    else:
        total_buy = 0; total_eval = 0; sector_summary = []
        for sector in SECTOR_LIST:
            items = wl.get(sector, [])
            if len(items) == 0: continue
            sb = 0; se = 0
            for item in items:
                q = item.get("quantity", 0); bp = item.get("buy_price", 0)
                if q > 0 and bp > 0:
                    info, _ = get_stock_data(item["ticker"], 1)
                    if info: sb += q * bp; se += q * info["price"]
            if sb > 0:
                sr = (se - sb) / sb * 100
                sector_summary.append({"Sector": sector, "Buy": sb, "Eval": se, "Return": round(sr, 2)})
                total_buy += sb; total_eval += se
        if total_buy > 0:
            st.subheader("💼 Portfolio Summary")
            tr = (total_eval - total_buy) / total_buy * 100; profit = total_eval - total_buy
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Buy", f"{total_buy:,.0f} KRW"); c2.metric("Total Eval", f"{total_eval:,.0f} KRW")
            c3.metric("Total Return", f"{tr:+.2f}%", delta=f"{profit:+,.0f} KRW"); c4.metric("Holdings", f"{sum(len(wl[s]) for s in SECTOR_LIST)}")
            fig_pie = px.pie(pd.DataFrame(sector_summary), values="Eval", names="Sector", title="Sector Allocation", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True); st.divider()
        for sector in SECTOR_LIST:
            items = wl.get(sector, [])
            if len(items) == 0: continue
            with st.expander(f"📂 {sector} ({len(items)})", expanded=True):
                stock_results = []
                for item in items:
                    info, _ = get_stock_data(item["ticker"], period_days); fund = get_fundamental(item["ticker"])
                    if info:
                        row = {"Name": item["name"], "Ticker": item["ticker"], **info, "Alert(%)": item.get("alert_threshold", 3.0), "Qty": item.get("quantity", 0), "Buy": item.get("buy_price", 0)}
                        if fund: row.update(fund)
                        q = item.get("quantity", 0); bp = item.get("buy_price", 0)
                        if q > 0 and bp > 0:
                            row["Profit(KRW)"] = int(q * info["price"] - q * bp)
                            row["Profit(%)"] = round((q * info["price"] - q * bp) / (q * bp) * 100, 2)
                        else: row["Profit(KRW)"] = "-"; row["Profit(%)"] = "-"
                        stock_results.append(row)
                    else:
                        stock_results.append({"Name": item["name"], "Ticker": item["ticker"], "price": "-", "change_pct": "-", "volume_bil": "-", "high": "-", "low": "-", "Alert(%)": item.get("alert_threshold", 3.0), "Qty": item.get("quantity", 0), "Buy": item.get("buy_price", 0), "Profit(KRW)": "-", "Profit(%)": "-"})
                if stock_results:
                    df_wl = pd.DataFrame(stock_results)
                    def color_wl(val):
                        if isinstance(val, (int, float)):
                            if val > 0: return "color: #22c55e; font-weight: bold"
                            elif val < 0: return "color: #ef4444; font-weight: bold"
                        return ""
                    dc = ["Name", "Ticker", "price", "change_pct", "volume_bil", "high", "low"]
                    if any(c in df_wl.columns for c in ["PER", "PBR", "DIV"]): dc += ["PER", "PBR", "DIV"]
                    dc += ["Qty", "Buy", "Profit(KRW)", "Profit(%)", "Alert(%)"]
                    dc = [c for c in dc if c in df_wl.columns]
                    st.dataframe(df_wl[dc].style.map(color_wl, subset=["change_pct", "Profit(%)"]), use_container_width=True, hide_index=True)
                    cols = st.columns(min(len(items), 4))
                    for idx, item in enumerate(items):
                        with cols[idx % 4]:
                            if st.button(f"🗑️ Delete {item['name']}", key=f"del_{sector}_{item['ticker']}"):
                                wl[sector] = [i for i in wl[sector] if i["ticker"] != item["ticker"]]
                                save_watchlist(wl); st.rerun()
        st.divider()
        cr1, cr2 = st.columns(2)
        with cr1:
            if st.button("🗑️ Reset All", type="secondary"):
                st.session_state.watchlist = {s: [] for s in SECTOR_LIST}; save_watchlist(st.session_state.watchlist); st.rerun()
        with cr2:
            wl_json = json.dumps(st.session_state.watchlist, ensure_ascii=False, indent=2)
            st.download_button("💾 Backup", data=wl_json, file_name="watchlist_backup.json", mime="application/json")

with tab3:
    st.subheader("🔍 Stock Detail Search")
    c1, c2 = st.columns([3, 1])
    with c1: stock_input = st.text_input("Stock name or ticker (e.g. Samsung, 005930)", "Samsung", key="tab3_stock")
    with c2: search_btn = st.button("🔎 Search", use_container_width=True, key="tab3_search")
    if search_btn and stock_input:
        name, ticker = search_ticker(stock_input)
        if name and ticker:
            info, df_hist = get_stock_data(ticker, period_days); fund = get_fundamental(ticker); net_purchase = get_net_purchase(ticker, period_days)
            if info and df_hist is not None:
                st.success(f"📌 {name} ({ticker})")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Price", f"{info['price']:,} KRW"); c2.metric("Change", f"{info['change_pct']:+.2f}%")
                c3.metric("High", f"{info['high']:,} KRW"); c4.metric("Low", f"{info['low']:,} KRW")
                if fund:
                    st.subheader("📋 Fundamental")
                    f1, f2, f3, f4, f5 = st.columns(5)
                    f1.metric("PER", fund.get("PER", "-")); f2.metric("PBR", fund.get("PBR", "-"))
                    f3.metric("DIV", f"{fund.get('DIV', '-')}%" if fund.get('DIV') is not None else "-")
                    f4.metric("EPS", f"{fund.get('EPS', '-'):,}" if fund.get('EPS') is not None else "-")
                    f5.metric("BPS", f"{fund.get('BPS', '-'):,}" if fund.get('BPS') is not None else "-")
                if net_purchase:
                    st.subheader("📊 Foreign/Institutional Net Purchase")
                    s1, s2 = st.columns(2)
                    with s1: foreign = net_purchase.get("Foreign_net_bil", "-"); st.metric("Foreign", f"{foreign:+.1f}B" if isinstance(foreign, (int, float)) else str(foreign))
                    with s2: inst = net_purchase.get("Institutional_net_bil", "-"); st.metric("Institutional", f"{inst:+.1f}B" if isinstance(inst, (int, float)) else str(inst))
                fig = go.Figure(data=[go.Candlestick(x=df_hist.index, open=df_hist['Open'], high=df_hist['High'], low=df_hist['Low'], close=df_hist['Close'], name=name)])
                fig.update_layout(title=f"{name} Candlestick ({period_days}D)", xaxis_title="Date", yaxis_title="Price (KRW)", height=500, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
                fig_vol = px.bar(df_hist, x=df_hist.index, y='Volume', title="Volume", height=200)
                st.plotly_chart(fig_vol, use_container_width=True)
                st.divider()
                add_sector = st.selectbox("Add to watchlist sector", SECTOR_LIST, key="add_sector_detail")
                ca1, ca2, ca3 = st.columns(3)
                with ca1: add_alert = st.number_input("Alert threshold (%)", min_value=0.0, value=3.0, step=0.5, key="add_alert_detail")
                with ca2: add_qty = st.number_input("Quantity", min_value=0, value=0, step=1, key="add_qty_detail")
                with ca3: add_buy = st.number_input("Buy price", min_value=0, value=0, step=1000, key="add_buy_detail")
                if st.button("⭐ Add to Watchlist", key="add_btn_detail"):
                    wl = st.session_state.watchlist
                    if any(i["ticker"]==ticker for i in wl.get(add_sector, [])): st.warning("Already in watchlist")
                    else:
                        wl.setdefault(add_sector, []).append({"name":name,"ticker":ticker,"alert_threshold":add_alert,"quantity":add_qty,"buy_price":add_buy})
                        save_watchlist(wl); st.success(f"✅ {name} added to {add_sector}!"); st.rerun()
            else: st.error("Failed to load stock data")
        else: st.error("Stock not found")

with tab4:
    st.subheader(f"🏆 Top 20 by {period_days}D Return (Market Cap Top 200)")
    top_df = get_top_stocks_by_market_cap(200)
    if top_df is not None and not top_df.empty:
        progress = st.progress(0); ranking_results = []
        for i, row in top_df.iterrows():
            ticker = row['ticker']; info, _ = get_stock_data(ticker, period_days)
            if info: ranking_results.append({"Rank": len(ranking_results)+1, "Name": row['name'], "Ticker": ticker, "Market": row['market'], "Price": info['price'], f"{period_days}D_Return": info['change_pct'], "Volume_B": info['volume_bil'], "Cap_B": row['시가총액']/1e8})
            progress.progress(min((i+1)/len(top_df), 1.0))
        progress.empty()
        if ranking_results:
            rank_df = pd.DataFrame(ranking_results).sort_values(f"{period_days}D_Return", ascending=False).head(20)
            rank_df['Rank'] = range(1, len(rank_df)+1)
            def color_rank(val):
                if isinstance(val, (int, float)):
                    if val > 0: return "color: #22c55e; font-weight: bold"
                    elif val < 0: return "color: #ef4444; font-weight: bold"
                return ""
            st.dataframe(rank_df.style.map(color_rank, subset=[f"{period_days}D_Return"]), use_container_width=True, hide_index=True)
            fig_rank = px.bar(rank_df, x="Name", y=f"{period_days}D_Return", color=f"{period_days}D_Return", color_continuous_scale=["#ef4444", "#9ca3af", "#22c55e"], text=f"{period_days}D_Return", height=600)
            fig_rank.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
            st.plotly_chart(fig_rank, use_container_width=True)
        else: st.warning("Ranking calculation failed")
    else: st.warning("Market cap data failed to load")

with tab5:
    st.subheader(f"📉 KOSDAQ Sector Indices ({period_days}D)")
    kosdaq_sectors = get_kosdaq_sectors()
    if kosdaq_sectors is not None:
        progress = st.progress(0); kosdaq_results = []
        for i, row in kosdaq_sectors.iterrows():
            perf = get_kosdaq_sector_performance(row['code'], period_days)
            if perf: kosdaq_results.append({"Name": row['name'], "Code": row['code'], **perf})
            progress.progress(min((i+1)/len(kosdaq_sectors), 1.0))
        progress.empty()
        if kosdaq_results:
            kdq_df = pd.DataFrame(kosdaq_results).sort_values("change_pct", ascending=False)
            def color_kdq(val):
                if isinstance(val, (int, float)):
                    if val > 0: return "color: #22c55e; font-weight: bold"
                    elif val < 0: return "color: #ef4444; font-weight: bold"
                return ""
            st.dataframe(kdq_df.style.map(color_kdq, subset=["change_pct"]), use_container_width=True, hide_index=True)
            fig_kdq = px.bar(kdq_df, x="Name", y="change_pct", color="change_pct", color_continuous_scale=["#ef4444", "#9ca3af", "#22c55e"], text="change_pct", height=600)
            fig_kdq.update_traces(texttemplate="%{text:.2f}%", textposition="outside"); fig_kdq.update_layout(showlegend=False)
            st.plotly_chart(fig_kdq, use_container_width=True)
        else: st.warning("KOSDAQ sector data failed")
    else: st.warning("KOSDAQ sector list failed")

with tab6:
    st.subheader("🏭 Sector Top 10 by Market Cap")
    st.caption("Select a sector to see top 10 stocks by market cap in that industry")
    selected = st.selectbox("Sector", list(SECTOR_ETFS.keys()), key="sector_map_select")
    if selected:
        st.markdown(f"### 📌 {selected} Top 10")
        st.info("Note: Sector-to-industry mapping uses KRX Dept data. Some sectors may not have exact matches.")
        st.warning("This feature requires KRX industry classification data which may not be available for all sectors in pykrx.")

st.divider()
st.caption("Data: FinanceDataReader, pykrx (KRX) | Personal use only")