import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="🇰🇷 한국 주식 섹터 대시보드", layout="wide", initial_sidebar_state="expanded")

SECTOR_ETFS = {
    "반도체": "091160", "2차전지": "364990", "바이오": "244580",
    "은행": "091170", "자동차": "091180", "증권": "102970",
    "IT": "266370", "에너지화학": "117460", "철강": "117680",
    "건설": "117700", "운송": "140710", "미디어&엔터": "266360",
    "기계장비": "102960", "보험": "140700", "유통": "091220",
    "필수소비재": "266390", "임의소비재": "266400", "코스피200": "069500",
}
SECTOR_LIST = list(SECTOR_ETFS.keys()) + ["기타"]
WATCHLIST_FILE = "watchlist.json"
DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "local").lower() == "cloud"

def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

def is_market_open():
    now = get_kst_now()
    if now.weekday() >= 5:
        return False, "휴장 (주말)"
    mo = now.replace(hour=9, minute=0, second=0, microsecond=0)
    mc = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now < mo:
        return False, "장전 (09:00 개장 예정)"
    elif now > mc:
        return False, "장마감"
    return True, "장중"

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
            "현재가": int(ep),
            "등락률(%)": round((ep - sp) / sp * 100, 2),
            "거래대금(억)": round((df['Volume'] * df['Close']).mean() / 1e8, 1),
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
            "현재가": int(df['Close'].iloc[-1]),
            "등락률(%)": round(chg, 2),
            "거래대금(억)": round((df['Volume'].iloc[-1] * df['Close'].iloc[-1]) / 1e8, 1),
            "고가": int(df['High'].max()),
            "저가": int(df['Low'].min()),
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
    st.title("📈 한국 주식 섹터 & 관심종목 대시보드")
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
            if info and abs(info["등락률(%)"]) >= thr:
                direction = "📈 상승" if info["등락률(%)"] > 0 else "📉 하락"
                alerts.append(f"**{item['name']}** {direction} {info['등락률(%)']:+.2f}% (설정: {thr}%)")
    return alerts

alerts = check_alerts()
if alerts:
    st.info("🔔 **관심 종목 알림**\n\n" + "\n\n".join(alerts))

st.sidebar.header("⚙️ 설정")
period_days = st.sidebar.selectbox(
    "조회 기간",
    [("1일", 1), ("3일", 3), ("1주일", 5), ("2주일", 10), ("1개월", 20), ("3개월", 60)],
    format_func=lambda x: x[0],
    index=2,
)[1]

st.sidebar.divider()
st.sidebar.header("⭐ 관심 종목 등록")

with st.sidebar.form("add_watchlist", clear_on_submit=True):
    sector_sel = st.selectbox("섹터 선택", SECTOR_LIST)
    stock_input = st.text_input("종목명 또는 티커")
    alert_thr = st.number_input("알림 임계값 (%)", min_value=0.0, max_value=50.0, value=3.0, step=0.5,
                                help="이 종목의 등락률이 이 값 이상이면 상단에 알림이 표시됩니다. 0이면 알림 끄기")
    qty = st.number_input("보유 수량", min_value=0, value=0, step=1,
                          help="포트폴리오 수익률 계산에 사용됩니다. 없으면 0")
    buy_p = st.number_input("매수 단가 (원)", min_value=0, value=0, step=1000,
                            help="포트폴리오 수익률 계산에 사용됩니다. 없으면 0")
    if st.form_submit_button("➕ 등록") and stock_input:
        name, ticker = search_ticker(stock_input)
        if name and ticker:
            wl = st.session_state.watchlist
            if any(i["ticker"] == ticker for i in wl.get(sector_sel, [])):
                st.sidebar.warning(f"'{name}'은(는) 이미 등록되어 있습니다.")
            else:
                wl.setdefault(sector_sel, []).append(
                    {"name": name, "ticker": ticker, "alert_threshold": alert_thr, "quantity": qty, "buy_price": buy_p}
                )
                save_watchlist(wl)
                st.sidebar.success(f"✅ '{name}' 등록 완료!")
                st.rerun()
        else:
            st.sidebar.error("종목을 찾을 수 없습니다.")

if DEPLOY_MODE:
    st.sidebar.success("☁️ 배포 모드 (SQLite 저장)")
else:
    st.sidebar.info("💻 로컬 모드 (JSON 저장)")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📊 섹터 대시보드", "⭐ 관심 종목", "🔍 개별 종목 조회", "🏆 상위 종목 랭킹", "📉 코스닥 업종", "🏭 섹터별 상위 종목"]
)

with tab1:
    st.subheader(f"KOSPI 섹터 ETF 성과 ({period_days}일 기준)")
    progress = st.progress(0)
    results = []
    for i, (name, ticker) in enumerate(SECTOR_ETFS.items()):
        data = get_sector_performance(ticker, period_days)
        if data:
            results.append({"섹터": name, "티커": ticker, **data})
        progress.progress((i + 1) / len(SECTOR_ETFS))
    progress.empty()

    if results:
        df = pd.DataFrame(results).sort_values("등락률(%)", ascending=False)
        cols = st.columns(3)
        medals = ["🥇", "🥈", "🥉"]
        for idx in range(min(3, len(df))):
            row = df.iloc[idx]
            with cols[idx]:
                st.metric(
                    label=f"{medals[idx]} {row['섹터']}",
                    value=f"{row['현재가']:,}원",
                    delta=f"{row['등락률(%)']:+.2f}%",
                )
        st.divider()
        st.subheader("🗺️ 섹터 히트맵")
        heatmap_cols = st.columns(6)
        for idx, (_, row) in enumerate(df.iterrows()):
            col_idx = idx % 6
            change = row["등락률(%)"]
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
                    f'<div style="font-weight:bold;font-size:0.9rem;color:{tc};">{row["섹터"]}</div>'
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
            df.style.map(color_change, subset=["등락률(%)"]),
            use_container_width=True,
            hide_index=True,
        )

        df["색상"] = df["등락률(%)"].apply(lambda x: "상승" if x > 0 else "하락" if x < 0 else "보합")
        fig = px.bar(
            df,
            x="섹터",
            y="등락률(%)",
            color="색상",
            color_discrete_map={"상승": "#22c55e", "하락": "#ef4444", "보합": "#9ca3af"},
            text="등락률(%)",
            height=500,
        )
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📈 상위 5개 섹터 추이")
        top5 = df.head(5)["섹터"].tolist()
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
            title="상대 수익률 추이 (시작일=100)",
            xaxis_title="날짜",
            yaxis_title="상대 수익률",
            height=400,
            hovermode="x unified",
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.warning("섹터 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")

with tab2:
    st.subheader("⭐ 내 관심 종목")
    wl = st.session_state.watchlist
    has_any = any(len(items) > 0 for items in wl.values())

    if not has_any:
        st.info("아직 등록된 관심 종목이 없습니다. 왼쪽 사이드바에서 등록해주세요!")
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
                        se += q * info["현재가"]
            if sb > 0:
                sr = (se - sb) / sb * 100
                sector_summary.append({"섹터": sector, "매수금액": sb, "평가금액": se, "수익률(%)": round(sr, 2)})
                total_buy += sb
                total_eval += se

        if total_buy > 0:
            st.subheader("💼 포트폴리오 요약")
            tr = (total_eval - total_buy) / total_buy * 100
            profit = total_eval - total_buy
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 매수금액", f"{total_buy:,.0f}원")
            c2.metric("총 평가금액", f"{total_eval:,.0f}원")
            c3.metric("총 수익률", f"{tr:+.2f}%", delta=f"{profit:+,.0f}원")
            c4.metric("보유 종목 수", f"{sum(len(wl[s]) for s in SECTOR_LIST)}개")
            fig_pie = px.pie(
                pd.DataFrame(sector_summary),
                values="평가금액",
                names="섹터",
                title="섹터별 평가금액 비중",
                hole=0.4,
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            st.divider()

        for sector in SECTOR_LIST:
            items = wl.get(sector, [])
            if len(items) == 0:
                continue
            with st.expander(f"📂 {sector} ({len(items)}개)", expanded=True):
                stock_results = []
                for item in items:
                    info, _ = get_stock_data(item["ticker"], period_days)
                    if info:
                        row = {
                            "종목명": item["name"],
                            "티커": item["ticker"],
                            **info,
                            "알림(%)": item.get("alert_threshold", 3.0),
                            "수량": item.get("quantity", 0),
                            "매수가": item.get("buy_price", 0),
                        }
                        q = item.get("quantity", 0)
                        bp = item.get("buy_price", 0)
                        if q > 0 and bp > 0:
                            row["수익(원)"] = int(q * info["현재가"] - q * bp)
                            row["수익률(%)"] = round((q * info["현재가"] - q * bp) / (q * bp) * 100, 2)
                        else:
                            row["수익(원)"] = "-"
                            row["수익률(%)"] = "-"
                        stock_results.append(row)
                    else:
                        stock_results.append(
                            {
                                "종목명": item["name"],
                                "티커": item["ticker"],
                                "현재가": "-",
                                "등락률(%)": "-",
                                "거래대금(억)": "-",
                                "고가": "-",
                                "저가": "-",
                                "알림(%)": item.get("alert_threshold", 3.0),
                                "수량": item.get("quantity", 0),
                                "매수가": item.get("buy_price", 0),
                                "수익(원)": "-",
                                "수익률(%)": "-",
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
                        "종목명",
                        "티커",
                        "현재가",
                        "등락률(%)",
                        "거래대금(억)",
                        "고가",
                        "저가",
                        "수량",
                        "매수가",
                        "수익(원)",
                        "수익률(%)",
                        "알림(%)",
                    ]
                    dc = [c for c in dc if c in df_wl.columns]
                    st.dataframe(
                        df_wl[dc].style.map(color_wl, subset=["등락률(%)", "수익률(%)"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                    cols = st.columns(min(len(items), 4))
                    for idx, item in enumerate(items):
                        with cols[idx % 4]:
                            if st.button(
                                f"🗑️ {item['name']} 삭제",
                                key=f"del_{sector}_{item['ticker']}",
                            ):
                                wl[sector] = [i for i in wl[sector] if i["ticker"] != item["ticker"]]
                                save_watchlist(wl)
                                st.rerun()

        st.divider()
        cr1, cr2 = st.columns(2)
        with cr1:
            if st.button("🗑️ 전체 관심 종목 초기화", type="secondary"):
                st.session_state.watchlist = {s: [] for s in SECTOR_LIST}
                save_watchlist(st.session_state.watchlist)
                st.rerun()
        with cr2:
            wl_json = json.dumps(st.session_state.watchlist, ensure_ascii=False, indent=2)
            st.download_button(
                "💾 관심 종목 백업 다운로드",
                data=wl_json,
                file_name="watchlist_backup.json",
                mime="application/json",
            )

with tab3:
    st.subheader("🔍 개별 종목 상세 조회")
    c1, c2 = st.columns([3, 1])
    with c1:
        stock_input = st.text_input(
            "종목명 또는 티커 입력 (예: 삼성전자, 005930)",
            "삼성전자",
            key="tab3_stock",
        )
    with c2:
        search_btn = st.button("🔎 조회", use_container_width=True, key="tab3_search")

    if search_btn and stock_input:
        name, ticker = search_ticker(stock_input)
        if name and ticker:
            info, df_hist = get_stock_data(ticker, period_days)
            if info and df_hist is not None:
                st.success(f"📌 {name} ({ticker})")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("현재가", f"{info['현재가']:,}원")
                c2.metric("등락률", f"{info['등락률(%)']:+.2f}%")
                c3.metric("고가", f"{info['고가']:,}원")
                c4.metric("저가", f"{info['저가']:,}원")

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
                    title=f"{name} 캔들 차트 ({period_days}일)",
                    xaxis_title="날짜",
                    yaxis_title="가격 (원)",
                    height=500,
                    xaxis_rangeslider_visible=False,
                )
                st.plotly_chart(fig, use_container_width=True)

                fig_vol = px.bar(df_hist, x=df_hist.index, y="Volume", title="거래량", height=200)
                st.plotly_chart(fig_vol, use_container_width=True)

                st.divider()
                add_sector = st.selectbox(
                    "관심 종목에 추가할 섹터 선택",
                    SECTOR_LIST,
                    key="add_sector_detail",
                )
                ca1, ca2, ca3 = st.columns(3)
                with ca1:
                    add_alert = st.number_input(
                        "알림 임계값 (%)",
                        min_value=0.0,
                        value=3.0,
                        step=0.5,
                        key="add_alert_detail",
                    )
                with ca2:
                    add_qty = st.number_input(
                        "보유 수량",
                        min_value=0,
                        value=0,
                        step=1,
                        key="add_qty_detail",
                    )
                with ca3:
                    add_buy = st.number_input(
                        "매수 단가 (원)",
                        min_value=0,
                        value=0,
                        step=1000,
                        key="add_buy_detail",
                    )
                if st.button("⭐ 관심 종목에 추가", key="add_btn_detail"):
                    wl = st.session_state.watchlist
                    if any(i["ticker"] == ticker for i in wl.get(add_sector, [])):
                        st.warning("이미 등록된 종목입니다.")
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
                        st.success(f"✅ '{name}'을(를) [{add_sector}] 섹터에 추가했습니다!")
                        st.rerun()
            else:
                st.error("주가 데이터를 불러올 수 없습니다.")
        else:
            st.error("종목을 찾을 수 없습니다.")

with tab4:
    st.subheader("🏆 시총 상위 200개 중 기간별 상승률 TOP 20")
    st.info("준비 중입니다. pykrx 데이터 소스가 필요합니다.")

with tab5:
    st.subheader("📉 코스닥 업종별 지수 등락률")
    st.info("준비 중입니다. pykrx 데이터 소스가 필요합니다.")

with tab6:
    st.subheader("🏭 섹터별 시총 상위 10개 종목")
    st.info("준비 중입니다. pykrx 데이터 소스가 필요합니다.")

st.divider()
st.caption("📌 데이터 출처: FinanceDataReader | 개인용 비상업적 사용")
