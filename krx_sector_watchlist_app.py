import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="KRX Stock Dashboard", layout="wide", initial_sidebar_state="expanded")

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
DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "local").lower() == "cloud"

def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

def is_market_open():
    now = get_kst_now()
    if now.weekday() >= 5:
        return False, "Closed (Weekend)"
    mo = now.replace(hour=9, minute=0, second=0, microsecond=0)
    mc = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now < mo:
        return False, "Pre-market"
    elif now > mc:
        return False, "Market Closed"
    return True, "Market Open"

def load_watchlist():
    if DEPLOY_MODE:
        try:
            import sqlite3
            conn = sqlite3.connect("watchlist.db")
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS watchlist (sector TEXT, name TEXT, ticker TEXT, alert_threshold REAL DEFAULT 3.0, quantity INTEGER DEFAULT 0, buy_price REAL DEFAULT 0, PRIMARY KEY (sector, ticker))")
            conn.commit()
            c.execute("SELECT sector, name, ticker, alert_threshold, quantity, buy_price FROM watchlist")
            rows = c.fetchall()
            conn.close()
            result = {s: [] for s in SECTOR_LIST}
            for r in rows:
                result[r[0]].append({"name": r[1], "ticker": r[2], "alert_threshold": r[3], "quantity": r[4], "buy_price": r[5]})
            return result
        except:
            pass
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for s in SECTOR_LIST:
                for item in data.get(s, []):
                    item.setdefault("alert_threshold", 3.0)
                    item.setdefault("quantity", 0)
                    item.setdefault("buy_price", 0)
            return data
    return {s: [] for s in SECTOR_LIST}

def save_watchlist(wl):
    if DEPLOY_MODE:
        try:
            import sqlite3
            conn = sqlite3.connect("watchlist.db")
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS watchlist (sector TEXT, name TEXT, ticker TEXT, alert_threshold REAL DEFAULT 3.0, quantity INTEGER DEFAULT 0, buy_price REAL DEFAULT 0, PRIMARY KEY (sector, ticker))")
            c.execute("DELETE FROM watchlist")
            for s, items in wl.items():
                for item in items:
                    c.execute("INSERT INTO watchlist VALUES (?,?,?,?,?,?)", (s, item["name"], item["ticker"], item.get("alert_threshold", 3.0), item.get("quantity", 0), item.get("buy_price", 0)))
            conn.commit()
            conn.close()
            return
        except:
            pass
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

def init_watchlist():
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = load_watchlist()

init_watchlist()

@st.cache_data(ttl=300)
def get_sector_performance(ticker, days):
    try:
        end = get_kst_now()
        start = end - timedelta(days=days + 15)
        df = fdr.DataReader(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
        if len(df) < 2:
            return None
        sp = df['Close'].iloc[0]
        ep = df['Close'].iloc[-1]
        return {
            "price": int(ep),
            "change_pct": round((ep - sp) / sp * 100, 2),
            "volume_bil": round((df['Volume'] * df['Close']).mean() / 1e8, 1),
        }
    except:
        return None

@st.cache_data(ttl=300)
def get_stock_data(ticker, days):
    try:
        end = get_kst_now()
        start = end - timedelta(days=days + 15)
        df = fdr.DataReader(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
        if len(df) < 2:
            return None, None
        chg = (df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100
        info = {
            "price": int(df['Close'].iloc[-1]),
            "change_pct": round(chg, 2),
            "volume_bil": round((df['Volume'].iloc[-1] * df['Close'].iloc[-1]) / 1e8, 1),
            "high": int(df['High'].max()),
            "low": int(df['Low'].min()),
        }
        return info, df
    except:
        return None, None

@st.cache_data(ttl=300)
def search_ticker(name_or_code):
    try:
        kospi = fdr.StockListing('KOSPI')
        kosdaq = fdr.StockListing('KOSDAQ')
        all_list = pd.concat([kospi, kosdaq])
        matched = all_list[
            (all_list['Name'].str.contains(name_or_code, case=False, na=False)) |
            (all_list['Code'].str.contains(name_or_code, na=False))
        ]
        if len(matched) == 0:
            return None, None
        return matched.iloc[0]['Name'], matched.iloc[0]['Code']
    except:
        return None, None

st_autorefresh(interval=60 * 1000, limit=None, key="clock_refresh")
now_kst = get_kst_now()
market_open, market_status = is_market_open()
status_color = "🟢" if market_open else "🔴"

hc1, hc2 = st.columns([4, 1])
with hc1:
    st.title("KRX Sector & Watchlist Dashboard")
with hc2:
    st.markdown(
        f'<div style="text-align:right;padding-top:10px;">'
        f'<span style="font-size:1.1rem;font-weight:bold;">{now_kst.strftime("%Y-%m-%d %H:%M")}</span><br>'
        f'<span style="font-size:0.9rem;">{status_color} {market_status}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

def check_alerts():
    alerts = []
    for s, items in st.session_state.watchlist.items():
        for item in items:
            thr = item.get("alert_threshold", 3.0)
            if thr <= 0:
                continue
            info, _ = get_stock_data(item["ticker"], 1)
            if info and abs(info["change_pct"]) >= thr:
                direction = "UP" if info["change_pct"] > 0 else "DOWN"
                alerts.append(f"**{item['name']}** {direction} {info['change_pct']:+.2f}% (threshold: {thr}%)")
    return alerts

alerts = check_alerts()
if alerts:
    st.info("🔔 **Alerts**\n\n" + "\n\n".join(alerts))

st.sidebar.header("⚙️ Settings")
period_days = st.sidebar.selectbox(
    "Period",
    [("1D", 1), ("3D", 3), ("1W", 5), ("2W", 10), ("1M", 20), ("3M", 60)],
    format_func=lambda x: x[0],
    index=2,
)[1]

st.sidebar.divider()
st.sidebar.header("⭐ Add Watchlist")

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
            if any(i["ticker"] == ticker for i in wl.get(sector_sel, [])):
                st.sidebar.warning(f"{name} already exists")
            else:
                wl.setdefault(sector_sel, []).append(
                    {"name": name, "ticker": ticker, "alert_threshold": alert_thr, "quantity": qty, "buy_price": buy_p}
                )
                save_watchlist(wl)
                st.sidebar.success(f"✅ {name} added!")
                st.rerun()
        else:
            st.sidebar.error("Stock not found")

if DEPLOY_MODE:
    st.sidebar.success("Cloud mode (SQLite)")
else:
    st.sidebar.info("Local mode (JSON)")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📊 Sector", "⭐ Watchlist", "🔍 Search", "🏆 Ranking", "📉 KOSDAQ", "🏭 Top10"]
)

with tab1:
    st.subheader(f"KOSPI Sector ETF Performance ({period_days}D)")
    progress = st.progress(0)
    results = []
    for i, (name, ticker) in enumerate(SECTOR_ETFS.items()):
        data = get_sector_performance(ticker, period_days)
        if data:
            results.append({"Sector": name, "Ticker": ticker, **data})
        progress.progress((i + 1) / len(SECTOR_ETFS))
    progress.empty()

    if results:
        df = pd.DataFrame(results).sort_values("change_pct", ascending=False)
        cols = st.columns(3)
        medals = ["🥇", "🥈", "🥉"]
        for idx in range(min(3, len(df))):
            row = df.iloc[idx]
            with cols[idx]:
                st.metric(
                    label=f"{medals[idx]} {row['Sector']}",
                    value=f"{row['price']:,} KRW",
                    delta=f"{row['change_pct']:+.2f}%",
                )
        st.divider()
        st.subheader("🗺️ Sector Heatmap")
        heatmap_cols = st.columns(6)
        for idx, (_, row) in enumerate(df.iterrows()):
            col_idx = idx % 6
            change = row["change_pct"]
            if change > 0:
                bg = f"rgba(34,197,94,{min(change / 10, 1.0)})"
                tc = "#fff" if change > 5 else "#000"
            elif change < 0:
                bg = f"rgba(239,68,68,{min(abs(change) / 10, 1.0)})"
                tc = "#fff" if change < -5 else "#000"
            else:
                bg = "#9ca3af"
                tc = "#000"
            with heatmap_cols[col_idx]:
                st.markdown(
                    f'<div style="background-color:{bg};padding:12px;border-radius:8px;text-align:center;margin-bottom:8px;">'
                    f'<div style="font-weight:bold;font-size:0.9rem;color:{tc};">{row["Sector"]}</div>'
                    f'<div style="font-size:1.1rem;font-weight:bold;color:{tc};">{change:+.2f}%</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.divider()

        def color_change(val):
            if isinstance(val, (int, float)):
                if val > 0:
                    return "color: #22c55e; font-weight: bold"
                elif val < 0:
                    return "color: #ef4444; font-weight: bold"
            return ""

        st.dataframe(
            df.style.map(color_change, subset=["change_pct"]),
            use_container_width=True,
            hide_index=True,
        )

        df["color"] = df["change_pct"].apply(lambda x: "Up" if x > 0 else "Down" if x < 0 else "Flat")
        fig = px.bar(
            df,
            x="Sector",
            y="change_pct",
            color="color",
            color_discrete_map={"Up": "#22c55e", "Down": "#ef4444", "Flat": "#9ca3af"},
            text="change_pct",
            height=500,
        )
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📈 Top 5 Sector Trend")
        top5 = df.head(5)["Sector"].tolist()
        end = get_kst_now()
        start = end - timedelta(days=period_days + 15)
        fig_line = go.Figure()
        for sector in top5:
            ticker = SECTOR_ETFS[sector]
            try:
                hist = fdr.DataReader(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
                if len(hist) > 0:
                    norm = hist['Close'] / hist['Close'].iloc[0] * 100
                    fig_line.add_trace(go.Scatter(x=norm.index, y=norm.values, mode="lines", name=sector))
            except:
                pass
        fig_line.update_layout(
            title="Relative Return (Start=100)",
            xaxis_title="Date",
            yaxis_title="Relative Return",
            height=400,
            hovermode="x unified",
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.warning("Failed to load sector data.")

with tab2:
    st.subheader("⭐ My Watchlist")
    wl = st.session_state.watchlist
    has_any = any(len(items) > 0 for items in wl.values())

    if not has_any:
        st.info("No watchlist items yet. Add from sidebar!")
    else:
        total_buy = 0
        total_eval = 0
        sector_summary = []
        for sector in SECTOR_LIST:
            items = wl.get(sector, [])
            if len(items) == 0:
                continue
            sb = 0
            se = 0
            for item in items:
                q = item.get("quantity", 0)
                bp = item.get("buy_price", 0)
                if q > 0 and bp > 0:
                    info, _ = get_stock_data(item["ticker"], 1)
                    if info:
                        sb += q * bp
                        se += q * info["price"]
            if sb > 0:
                sr = (se - sb) / sb * 100
                sector_summary.append({"Sector": sector, "Buy": sb, "Eval": se, "Return": round(sr, 2)})
                total_buy += sb
                total_eval += se

        if total_buy > 0:
            st.subheader("💼 Portfolio Summary")
            tr = (total_eval - total_buy) / total_buy * 100
            profit = total_eval - total_buy
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Buy", f"{total_buy:,.0f} KRW")
            c2.metric("Total Eval", f"{total_eval:,.0f} KRW")
            c3.metric("Total Return", f"{tr:+.2f}%", delta=f"{profit:+,.0f} KRW")
            c4.metric("Holdings", f"{sum(len(wl[s]) for s in SECTOR_LIST)}")
            fig_pie = px.pie(
                pd.DataFrame(sector_summary),
                values="Eval",
                names="Sector",
                title="Sector Allocation",
                hole=0.4,
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            st.divider()

        for sector in SECTOR_LIST:
            items = wl.get(sector, [])
            if len(items) == 0:
                continue
            with st.expander(f"📂 {sector} ({len(items)})", expanded=True):
                stock_results = []
                for item in items:
                    info, _ = get_stock_data(item["ticker"], period_days)
                    if info:
                        row = {
                            "Name": item["name"],
                            "Ticker": item["ticker"],
                            **info,
                            "Alert(%)": item.get("alert_threshold", 3.0),
                            "Qty": item.get("quantity", 0),
                            "Buy": item.get("buy_price", 0),
                        }
                        q = item.get("quantity", 0)
                        bp = item.get("buy_price", 0)
                        if q > 0 and bp > 0:
                            row["Profit(KRW)"] = int(q * info["price"] - q * bp)
                            row["Profit(%)"] = round((q * info["price"] - q * bp) / (q * bp) * 100, 2)
                        else:
                            row["Profit(KRW)"] = "-"
                            row["Profit(%)"] = "-"
                        stock_results.append(row)
                    else:
                        stock_results.append(
                            {
                                "Name": item["name"],
                                "Ticker": item["ticker"],
                                "price": "-",
                                "change_pct": "-",
                                "volume_bil": "-",
                                "high": "-",
                                "low": "-",
                                "Alert(%)": item.get("alert_threshold", 3.0),
                                "Qty": item.get("quantity", 0),
                                "Buy": item.get("buy_price", 0),
                                "Profit(KRW)": "-",
                                "Profit(%)": "-",
                            }
                        )

                if stock_results:
                    df_wl = pd.DataFrame(stock_results)

                    def color_wl(val):
                        if isinstance(val, (int, float)):
                            if val > 0:
                                return "color: #22c55e; font-weight: bold"
                            elif val < 0:
                                return "color: #ef4444; font-weight: bold"
                        return ""

                    dc = [
                        "Name",
                        "Ticker",
                        "price",
                        "change_pct",
                        "volume_bil",
                        "high",
                        "low",
                        "Qty",
                        "Buy",
                        "Profit(KRW)",
                        "Profit(%)",
                        "Alert(%)",
                    ]
                    dc = [c for c in dc if c in df_wl.columns]
                    st.dataframe(
                        df_wl[dc].style.map(color_wl, subset=["change_pct", "Profit(%)"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                    cols = st.columns(min(len(items), 4))
                    for idx, item in enumerate(items):
                        with cols[idx % 4]:
                            if st.button(
                                f"🗑️ Delete {item['name']}",
                                key=f"del_{sector}_{item['ticker']}",
                            ):
                                wl[sector] = [i for i in wl[sector] if i["ticker"] != item["ticker"]]
                                save_watchlist(wl)
                                st.rerun()

        st.divider()
        cr1, cr2 = st.columns(2)
        with cr1:
            if st.button("🗑️ Reset All", type="secondary"):
                st.session_state.watchlist = {s: [] for s in SECTOR_LIST}
                save_watchlist(st.session_state.watchlist)
                st.rerun()
        with cr2:
            wl_json = json.dumps(st.session_state.watchlist, ensure_ascii=False, indent=2)
            st.download_button(
                "💾 Backup",
                data=wl_json,
                file_name="watchlist_backup.json",
                mime="application/json",
            )

with tab3:
    st.subheader("🔍 Stock Detail Search")
    c1, c2 = st.columns([3, 1])
    with c1:
        stock_input = st.text_input(
            "Stock name or ticker (e.g. Samsung, 005930)",
            "Samsung",
            key="tab3_stock",
        )
    with c2:
        search_btn = st.button("🔎 Search", use_container_width=True, key="tab3_search")

    if search_btn and stock_input:
        name, ticker = search_ticker(stock_input)
        if name and ticker:
            info, df_hist = get_stock_data(ticker, period_days)
            if info and df_hist is not None:
                st.success(f"📌 {name} ({ticker})")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Price", f"{info['price']:,} KRW")
                c2.metric("Change", f"{info['change_pct']:+.2f}%")
                c3.metric("High", f"{info['high']:,} KRW")
                c4.metric("Low", f"{info['low']:,} KRW")

                fig = go.Figure(
                    data=[
                        go.Candlestick(
                            x=df_hist.index,
                            open=df_hist["Open"],
                            high=df_hist["High"],
                            low=df_hist["Low"],
                            close=df_hist["Close"],
                            name=name,
                        )
                    ]
                )
                fig.update_layout(
                    title=f"{name} Candlestick ({period_days}D)",
                    xaxis_title="Date",
                    yaxis_title="Price (KRW)",
                    height=500,
                    xaxis_rangeslider_visible=False,
                )
                st.plotly_chart(fig, use_container_width=True)

                fig_vol = px.bar(df_hist, x=df_hist.index, y="Volume", title="Volume", height=200)
                st.plotly_chart(fig_vol, use_container_width=True)

                st.divider()
                add_sector = st.selectbox(
                    "Add to watchlist sector",
                    SECTOR_LIST,
                    key="add_sector_detail",
                )
                ca1, ca2, ca3 = st.columns(3)
                with ca1:
                    add_alert = st.number_input(
                        "Alert threshold (%)",
                        min_value=0.0,
                        value=3.0,
                        step=0.5,
                        key="add_alert_detail",
                    )
                with ca2:
                    add_qty = st.number_input(
                        "Quantity",
                        min_value=0,
                        value=0,
                        step=1,
                        key="add_qty_detail",
                    )
                with ca3:
                    add_buy = st.number_input(
                        "Buy price",
                        min_value=0,
                        value=0,
                        step=1000,
                        key="add_buy_detail",
                    )
                if st.button("⭐ Add to Watchlist", key="add_btn_detail"):
                    wl = st.session_state.watchlist
                    if any(i["ticker"] == ticker for i in wl.get(add_sector, [])):
                        st.warning("Already in watchlist")
                    else:
                        wl.setdefault(add_sector, []).append(
                            {
                                "name": name,
                                "ticker": ticker,
                                "alert_threshold": add_alert,
                                "quantity": add_qty,
                                "buy_price": add_buy,
                            }
                        )
                        save_watchlist(wl)
                        st.success(f"✅ {name} added to {add_sector}!")
                        st.rerun()
            else:
                st.error("Failed to load stock data")
        else:
            st.error("Stock not found")

with tab4:
    st.subheader("🏆 Top 20 Ranking")
    st.info("Coming soon - Market cap ranking requires additional data source")

with tab5:
    st.subheader("📉 KOSDAQ Sectors")
    st.info("Coming soon - KOSDAQ sector indices require additional data source")

with tab6:
    st.subheader("🏭 Sector Top 10")
    st.info("Coming soon - Sector stock mapping requires additional data source")

st.divider()
st.caption("Data: FinanceDataReader | Personal use only")
