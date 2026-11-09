# -*- coding: utf-8 -*-
"""PChome 商品價格查詢與視覺化 (Streamlit)

執行方式:
    pip install -r requirements.txt
    streamlit run app.py
"""
import time

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_URL = "https://ecshweb.pchome.com.tw/search/v3.3/all/results"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

st.set_page_config(page_title="PChome 價格查詢", page_icon="🛒", layout="wide")
st.title("🛒 PChome 商品價格查詢與視覺化")


# ---------- 爬蟲 (原 CODE01) ----------
@st.cache_data(ttl=600, show_spinner=False)
def fetch_page(keyword: str, page: int, sort: str) -> list:
    """抓取單一頁資料，回傳商品 list。"""
    params = {"q": keyword, "page": page, "sort": sort}
    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("prods") or []


def fetch_all(keyword: str, pages: int, sort: str, delay: float) -> pd.DataFrame:
    frames = []
    bar = st.progress(0.0, text="開始抓取…")
    for i in range(1, pages + 1):
        prods = fetch_page(keyword, i, sort)
        if not prods:  # 沒有更多資料就提前結束
            st.info(f"第 {i} 頁沒有資料，已停止。")
            break
        frames.append(pd.DataFrame(prods))
        bar.progress(i / pages, text=f"已抓取第 {i}/{pages} 頁")
        if i < pages:
            time.sleep(delay)  # 避免請求過於頻繁
    bar.empty()
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------- 資料處理 (原 CODE02) ----------
def clean(df: pd.DataFrame) -> pd.DataFrame:
    keep = [c for c in ["name", "price", "originPrice", "cateId"] if c in df.columns]
    out = df[keep].copy()
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out = out.dropna(subset=["price"]).reset_index(drop=True)
    if "cateId" not in out.columns:
        out["cateId"] = "未分類"
    out["cateId"] = out["cateId"].fillna("未分類").astype(str)
    return out


def add_price_range(df: pd.DataFrame, bins: int = 5) -> pd.DataFrame:
    df = df.copy()
    if df["price"].nunique() < 2:
        df["價格區間"] = "單一價位"
        return df
    try:
        df["價格區間"] = pd.qcut(df["price"], q=min(bins, df["price"].nunique()),
                               duplicates="drop").astype(str)
    except ValueError:
        df["價格區間"] = pd.cut(df["price"], bins=bins).astype(str)
    return df


# ---------- 側邊欄輸入 ----------
with st.sidebar:
    st.header("查詢條件")
    keyword = st.text_input("商品關鍵字", value="電源")
    pages = st.number_input("抓取頁數 (每頁約 20 筆)", min_value=1, max_value=20, value=2, step=1)
    sort_label = st.selectbox("排序方式", ["銷量高→低", "價格低→高", "價格高→低"])
    sort = {"銷量高→低": "sale/dc", "價格低→高": "prc/ac", "價格高→低": "prc/dc"}[sort_label]
    delay = st.slider("每頁間隔秒數", 0.0, 10.0, 1.0, 0.5)
    chart_type = st.radio("圖表類型", ["圓餅圖", "折線圖", "旭日圖"])
    run = st.button("🔍 查詢", type="primary", use_container_width=True)

if run:
    if not keyword.strip():
        st.warning("請輸入商品關鍵字。")
        st.stop()
    try:
        raw = fetch_all(keyword.strip(), int(pages), sort, delay)
    except requests.RequestException as e:
        st.error(f"請求失敗：{e}")
        st.stop()
    if raw.empty:
        st.warning("查無資料，請換個關鍵字試試。")
        st.stop()
    st.session_state["df"] = clean(raw)
    st.session_state["kw"] = keyword.strip()

df = st.session_state.get("df")
if df is None:
    st.info("請在左側輸入關鍵字與頁數，然後按「查詢」。")
    st.stop()

kw = st.session_state["kw"]
mean_price = df["price"].mean()

# ---------- 統計指標 ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("商品數", f"{len(df):,}")
c2.metric("平均價格", f"{mean_price:,.0f}")
c3.metric("最高價格", f"{df['price'].max():,.0f}")
c4.metric("最低價格", f"{df['price'].min():,.0f}")

# ---------- 圖表 ----------
# 使用 Plotly：圖表在瀏覽器端渲染，使用瀏覽器內建字型，不需另外安裝中文字型
if chart_type == "圓餅圖":
    d = add_price_range(df)
    cnt = d["價格區間"].value_counts().reset_index()
    cnt.columns = ["價格區間", "商品數"]
    fig = px.pie(cnt, names="價格區間", values="商品數", title=f"PChome「{kw}」價格區間分布", hole=0.3)

elif chart_type == "折線圖":
    n = st.slider("顯示前幾筆商品", 5, len(df), min(70, len(df))) if len(df) > 5 else len(df)
    d = df.head(n).copy()
    d["序號"] = d.index + 1
    fig = px.line(d, x="序號", y="price", hover_name="name", markers=True,
                  title=f"PChome「{kw}」商品售價", labels={"序號": "商品序號", "price": "價格"})
    fig.add_hline(y=mean_price, line_dash="dash", line_color="red",
                  annotation_text=f"平均 {mean_price:,.0f}")

else:  # 旭日圖
    d = add_price_range(df)
    top_n = st.slider("顯示商品筆數", 10, max(10, len(d)), min(60, len(d)))
    d = d.head(top_n).copy()
    d["商品"] = [f"{i + 1}. {n[:12]}" for i, n in enumerate(d["name"].astype(str))]
    d["分類"] = d["cateId"].str[:4]
    fig = px.sunburst(d, path=["價格區間", "分類", "商品"], values="price",
                      title=f"PChome「{kw}」價格區間 › 分類 › 商品")

fig.update_layout(height=650, font=dict(size=14))
st.plotly_chart(fig, use_container_width=True)

# ---------- 資料表與下載 ----------
with st.expander("查看資料表"):
    st.dataframe(df, use_container_width=True)
st.download_button("⬇️ 下載 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"PCHOME_{kw}.csv", mime="text/csv")
