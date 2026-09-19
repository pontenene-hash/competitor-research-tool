from __future__ import annotations

import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from ipaddress import ip_address
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TIMEOUT = 12
USER_AGENT = "Mozilla/5.0 (compatible; CompetitorResearchTool/1.0; +https://example.com/bot)"
MAX_BYTES = 5_000_000


@dataclass
class SearchItem:
    rank: int
    title: str
    url: str


@dataclass
class AnalysisResult:
    rank: int
    title: str
    url: str
    headings: str
    estimated_chars: int | None
    status: str


def is_safe_public_url(url: str) -> bool:
    """Block local/private addresses before fetching third-party pages."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
            addr = ip_address(info[4][0])
            if not addr.is_global:
                return False
    except (socket.gaierror, ValueError):
        return False
    return True


def search_google_pse(keyword: str, api_key: str, cx: str) -> list[SearchItem]:
    response = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": api_key, "cx": cx, "q": keyword, "num": 10, "hl": "ja", "gl": "jp"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return [
        SearchItem(i, item.get("title", ""), item.get("link", ""))
        for i, item in enumerate(response.json().get("items", []), 1)
    ]


def search_serper(keyword: str, api_key: str) -> list[SearchItem]:
    response = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": keyword, "gl": "jp", "hl": "ja", "num": 10},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    organic = response.json().get("organic", [])[:10]
    return [
        SearchItem(i, item.get("title", ""), item.get("link", ""))
        for i, item in enumerate(organic, 1)
    ]


def visible_text_and_headings(html: bytes) -> tuple[str, int]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    heading_lines = []
    for heading in soup.find_all(["h2", "h3"]):
        text = re.sub(r"\s+", " ", heading.get_text(" ", strip=True))
        if text:
            heading_lines.append(f"{heading.name.upper()}｜{text}")

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = re.sub(r"\s+", "", main.get_text(" ", strip=True))
    return "\n".join(heading_lines) or "見出しを取得できませんでした", len(text)


def analyze_page(item: SearchItem) -> AnalysisResult:
    if not is_safe_public_url(item.url):
        return AnalysisResult(item.rank, item.title, item.url, "—", None, "安全上取得できないURL")
    try:
        with requests.get(
            item.url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"},
            timeout=TIMEOUT,
            stream=True,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                raise ValueError("HTMLページではありません")
            chunks, size = [], 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("ページ容量が上限を超えました")
                chunks.append(chunk)
        headings, chars = visible_text_and_headings(b"".join(chunks))
        return AnalysisResult(item.rank, item.title, item.url, headings, chars, "取得完了")
    except Exception as exc:  # one failed site must not stop the full report
        return AnalysisResult(item.rank, item.title, item.url, "取得できませんでした", None, str(exc)[:80])


def analyze_all(items: list[SearchItem]) -> list[AnalysisResult]:
    results: list[AnalysisResult] = []
    progress = st.progress(0, text="競合ページを分析しています…")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(analyze_page, item): item for item in items}
        for completed, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            progress.progress(completed / len(items), text=f"{completed}/{len(items)}件を分析しました")
    progress.empty()
    return sorted(results, key=lambda row: row.rank)


def demo_results(keyword: str) -> list[AnalysisResult]:
    labels = ["完全ガイド", "初心者向け解説", "専門家が解説", "選び方", "よくある質問"]
    return [
        AnalysisResult(
            i,
            f"{keyword}｜{labels[(i - 1) % len(labels)]}（デモ）",
            f"https://example.com/demo-{i}",
            f"H2｜{keyword}とは\nH3｜よくある悩み{i}\nH2｜選び方とポイント\nH3｜注意点",
            3200 + i * 430,
            "デモデータ",
        )
        for i in range(1, 11)
    ]


def render_results(results: list[AnalysisResult], keyword: str) -> None:
    ok_count = sum(r.estimated_chars is not None for r in results)
    avg = int(sum(r.estimated_chars or 0 for r in results) / ok_count) if ok_count else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("検索結果", f"{len(results)}件")
    c2.metric("本文取得", f"{ok_count}件")
    c3.metric("平均推定文字数", f"{avg:,}文字" if avg else "—")

    frame = pd.DataFrame([asdict(result) for result in results]).rename(
        columns={
            "rank": "順位", "title": "サイトのタイトル", "url": "URL",
            "headings": "H2・H3見出し一覧", "estimated_chars": "推定文字数", "status": "取得状況",
        }
    )
    frame["推定文字数"] = frame["推定文字数"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    st.markdown('<div class="desktop-results">', unsafe_allow_html=True)
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config={
            "順位": st.column_config.NumberColumn(width="small"),
            "サイトのタイトル": st.column_config.TextColumn(width="medium"),
            "URL": st.column_config.LinkColumn(width="medium", display_text="ページを開く"),
            "H2・H3見出し一覧": st.column_config.TextColumn(width="large"),
            "推定文字数": st.column_config.TextColumn(width="small"),
            "取得状況": st.column_config.TextColumn(width="small"),
        },
        height=560,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # A vertical card layout is much easier to read than a wide table on iPhone.
    st.markdown('<div class="mobile-results">', unsafe_allow_html=True)
    for result in results:
        char_count = f"{result.estimated_chars:,}文字" if result.estimated_chars is not None else "—"
        with st.expander(f"{result.rank}位｜{result.title}", expanded=result.rank == 1):
            st.link_button("ページを開く", result.url, use_container_width=True)
            st.caption(f"推定文字数：{char_count}　／　{result.status}")
            st.text(result.headings)
    st.markdown('</div>', unsafe_allow_html=True)
    csv = frame.to_csv(index=False).encode("utf-8-sig")
    st.download_button("CSVをダウンロード", csv, f"competitor_{keyword}.csv", "text/csv", use_container_width=True)


st.set_page_config(page_title="SEO競合リサーチ", page_icon="🔎", layout="wide")
st.markdown("""
<style>
    .block-container {max-width: 1450px; padding-top: 2rem;}
    [data-testid="stMetric"] {background:#f7f8fc; border:1px solid #e7e9f2; padding:16px; border-radius:14px;}
    .hero {padding:24px 28px; border-radius:18px; color:white; margin-bottom:20px;
           background:linear-gradient(120deg,#3138a0,#6857df 55%,#8e69ec); box-shadow:0 14px 30px #4139a426;}
    .hero h1 {font-size:2rem; margin:0 0 6px 0;} .hero p {margin:0; opacity:.9;}
    .mobile-results {display:none;}
    @media (max-width: 700px) {
        .block-container {padding:1rem .85rem 4rem;}
        .hero {padding:20px 18px; border-radius:16px; margin-bottom:14px;}
        .hero h1 {font-size:1.55rem;}
        .hero p {font-size:.9rem; line-height:1.55;}
        [data-testid="stMetric"] {padding:10px;}
        [data-testid="stMetricLabel"] {font-size:.75rem;}
        [data-testid="stMetricValue"] {font-size:1.15rem;}
        .desktop-results {display:none;}
        .mobile-results {display:block;}
        .stDownloadButton button, .stFormSubmitButton button {min-height:48px; font-size:1rem;}
    }
</style>
<div class="hero"><h1>SEO競合リサーチ</h1><p>Google上位10サイトの構成とボリュームを、まとめて可視化します。</p></div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("検索設定（本番利用）")
    provider = st.selectbox("検索データの取得方法", ["デモモード", "Serper API", "Google Programmable Search"])
    st.caption("本番利用では検索APIを選択してください。キーは保存されません。")
    if provider == "Serper API":
        serper_key = st.text_input("Serper APIキー", value=os.getenv("SERPER_API_KEY", ""), type="password")
    elif provider == "Google Programmable Search":
        google_key = st.text_input("Google APIキー", value=os.getenv("GOOGLE_API_KEY", ""), type="password")
        google_cx = st.text_input("検索エンジンID（CX）", value=os.getenv("GOOGLE_CX", ""), type="password")
    st.divider()
    st.info("文字数はHTMLからメニュー等を除いた本文テキストの推定値です。JavaScript描画やアクセス制限のあるページは取得できない場合があります。")

st.caption("📱 iPhoneでは左上の ＞ を押すと検索APIの設定を開けます。")

with st.form("search_form"):
    keyword = st.text_input("検索キーワード", placeholder="例：せんげん台 整体", max_chars=100)
    submitted = st.form_submit_button("分析開始", type="primary", use_container_width=True)

if submitted:
    if not keyword.strip():
        st.warning("検索キーワードを入力してください。")
    else:
        try:
            with st.spinner("Google検索結果を取得しています…"):
                if provider == "デモモード":
                    results = demo_results(keyword.strip())
                    st.info("現在はデモデータを表示しています。実データ取得にはサイドバーで検索APIを選択してください。")
                elif provider == "Serper API":
                    if not serper_key:
                        raise ValueError("Serper APIキーを入力してください。")
                    items = search_serper(keyword.strip(), serper_key)
                    results = analyze_all(items) if items else []
                else:
                    if not google_key or not google_cx:
                        raise ValueError("Google APIキーと検索エンジンID（CX）を入力してください。")
                    items = search_google_pse(keyword.strip(), google_key, google_cx)
                    results = analyze_all(items) if items else []
            if results:
                render_results(results, keyword.strip())
            else:
                st.warning("検索結果が見つかりませんでした。設定またはキーワードを確認してください。")
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "不明"
            st.error(f"検索APIでエラーが発生しました（HTTP {code}）。APIキー・利用上限・設定をご確認ください。")
        except Exception as exc:
            st.error(str(exc))

if not submitted:
    st.caption("キーワードを入力して「分析開始」を押してください。初回はデモモードですぐに画面を確認できます。")
