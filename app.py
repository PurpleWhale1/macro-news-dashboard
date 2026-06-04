import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import plotly.graph_objects as go
from groq import Groq

# ============================================================
# [0. 페이지 설정]
# ============================================================
st.set_page_config(
    page_title="경제 뉴스 AI 인텔리전스",
    page_icon="📈",
    layout="wide"
)

st.markdown("""
<style>
    .reportview-container .main .block-container { padding-top: 2rem; }
    .stChatMessage { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# [1. 세션 상태 초기화 (앱 시작 시 한 번만 실행)]
# ============================================================
_defaults = {
    "news_list": [],
    "current_article": None,
    "ai_report": None,
    "article_body": None,
    "chat_history": [],
    "sentiment_score": 50,
    "bookmarks": [],
    "score_history": [],
}
for _key, _val in _defaults.items():
    st.session_state.setdefault(_key, _val)

# ============================================================
# [2. Groq 클라이언트 초기화]
# ※ 사용 방법: 사이드바 상단에서 Groq API 키를 직접 입력하세요.
#   무료 발급: https://console.groq.com
# ============================================================
def get_groq_client(api_key: str):
    return Groq(api_key=api_key)

# ============================================================
# [3. 네이버 뉴스 RSS 크롤링]
# ============================================================
# 네이버 경제 뉴스 RSS 카테고리 매핑 (sid1=101 경제 섹션 기준)
RSS_URLS = {
    "경제 전체":  "https://rss.news.naver.com/main/rss/category/rss.nhn?sid1=101",
    "증권":       "https://rss.news.naver.com/main/rss/category/rss.nhn?sid1=101&sid2=258",
    "금융":       "https://rss.news.naver.com/main/rss/category/rss.nhn?sid1=101&sid2=259",
    "부동산":     "https://rss.news.naver.com/main/rss/category/rss.nhn?sid1=101&sid2=260",
    "국제경제":   "https://rss.news.naver.com/main/rss/category/rss.nhn?sid1=101&sid2=262",
}

@st.cache_data(ttl=300)  # 5분 캐시 (과도한 요청 방지)
def get_news_from_rss(rss_url: str, max_items: int = 15) -> list[dict]:
    """RSS URL에서 뉴스 목록을 가져옵니다."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")[:max_items]
        news_data = []
        for item in items:
            title = item.find("title")
            link  = item.find("link") or item.find("originalLink")
            pub   = item.find("pubDate")
            desc  = item.find("description")
            if not (title and link):
                continue
            news_data.append({
                "title":       title.get_text(strip=True).replace("<![CDATA[", "").replace("]]>", ""),
                "link":        link.get_text(strip=True),
                "pub_date":    pub.get_text(strip=True)[:16] if pub else "",
                "description": BeautifulSoup(
                    desc.get_text(strip=True) if desc else "", "html.parser"
                ).get_text()[:100] + "..." if desc else "",
            })
        return news_data
    except Exception as e:
        st.error(f"RSS 뉴스 불러오기 실패: {e}")
        return []

@st.cache_data(ttl=600)  # 10분 캐시
def get_article_content(url: str) -> str:
    """기사 본문을 크롤링합니다."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # 네이버 뉴스 본문 셀렉터 (여러 케이스 대응)
        for selector in [
            "div#dic_area",          # 네이버 뉴스 일반
            "div.newsct_article",    # 네이버 뉴스 뷰어
            "div#articleBodyContents",
            "article",
        ]:
            content = soup.select_one(selector)
            if content:
                return "\n".join(
                    line.strip()
                    for line in content.get_text(separator="\n").split("\n")
                    if line.strip()
                )
        return "본문을 가져오지 못했습니다. 원문 링크를 직접 확인해 주세요."
    except Exception as e:
        return f"본문 크롤링 오류: {e}"

# ============================================================
# [4. AI 분석 함수 (Groq)]
# ============================================================
def analyze_news_with_groq(client: Groq, title: str, content: str) -> str:
    """Groq API를 이용해 기사를 분석합니다."""
    prompt = f"""
아래 경제 뉴스를 분석해줘.

[제목]: {title}
[본문]: {content[:2000]}

다음 양식에 맞춰 한국어로 답변해줘:

### 📝 핵심 세 줄 요약
- 
- 
- 

### 💡 투자자를 위한 한 줄 코멘트
- 

### 📉 시장 영향도 분석
- 

### 🌡️ 감성 점수 (0: 극단적 악재 ~ 100: 극단적 호재)
[SCORE](0~100 사이 숫자만)[/SCORE]
"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # 무료 고성능 모델
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=1024,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 분석 오류: {e}\n\nGroq API 키를 확인해 주세요."


def chat_with_groq(client: Groq, article_content: str, chat_history: list, user_question: str) -> str:
    """Groq API를 이용해 기사 관련 질문에 답변합니다. (멀티턴 대화 지원)"""
    # 시스템 메시지에 기사 본문을 포함
    system_msg = {
        "role": "system",
        "content": (
            "너는 경제 뉴스 전문 분석가야. "
            "아래 기사 본문을 참고해서 사용자 질문에 한국어로 친절하고 정확하게 답변해줘.\n\n"
            f"[기사 본문]\n{article_content[:2000]}"
        )
    }
    # 이전 대화 히스토리 + 현재 질문을 messages 배열로 구성
    messages = [system_msg] + chat_history + [{"role": "user", "content": user_question}]
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.5,
            max_tokens=512,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"답변 오류: {e}"

# ============================================================
# [5. 게이지 차트]
# ============================================================
def draw_gauge_chart(score: int) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": "시장 감성 온도", "font": {"size": 18, "color": "gray"}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "darkblue"},
            "bar": {"color": "#4B4B4B", "thickness": 0.2},
            "bgcolor": "white",
            "borderwidth": 2,
            "bordercolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0, 40],  "color": "rgba(255, 99, 132, 0.7)"},
                {"range": [40, 60], "color": "rgba(255, 206, 86, 0.7)"},
                {"range": [60, 100],"color": "rgba(75, 192, 192, 0.7)"},
            ],
        }
    ))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=50, b=20))
    return fig

# ============================================================
# [6. 감성 점수 히스토리 차트]
# ============================================================
def draw_score_history_chart(history: list[dict]) -> go.Figure:
    titles = [h["title"][:15] + "..." for h in history]
    scores = [h["score"] for h in history]
    colors = [
        "rgba(75,192,192,0.8)" if s >= 60
        else "rgba(255,206,86,0.8)" if s >= 40
        else "rgba(255,99,132,0.8)"
        for s in scores
    ]
    fig = go.Figure(go.Bar(
        x=list(range(len(scores))),
        y=scores,
        marker_color=colors,
        text=scores,
        textposition="outside",
        hovertext=titles,
        hoverinfo="text+y",
    ))
    fig.update_layout(
        title="📊 분석 기사 감성 점수 추이",
        xaxis_title="분석 순서",
        yaxis=dict(range=[0, 110]),
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False,
    )
    return fig

# ============================================================
# [7. 메인 UI]
# ============================================================
st.title("📈 AI 경제 인사이트 대시보드")
st.markdown("네이버 경제 뉴스를 실시간으로 불러와 Groq AI로 심층 분석합니다.")
st.divider()

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")

    # API 키 입력
    api_key = st.text_input(
        "🔑 Groq API Key",
        type="password",
        placeholder="gsk_xxxxxxxxxxxxxx",
        help="https://console.groq.com 에서 무료로 발급받으세요.",
    )
    if not api_key:
        st.warning("API 키를 입력해야 AI 분석 기능을 사용할 수 있습니다.")

    st.divider()

    # 카테고리 선택
    category = st.selectbox("📂 뉴스 카테고리", list(RSS_URLS.keys()))
    rss_url  = RSS_URLS[category]

    # 표시 개수
    max_items = st.slider("기사 수", min_value=5, max_value=20, value=10, step=5)

    # 새로고침 버튼
    if st.button("🔄 뉴스 목록 새로고침", use_container_width=True):
        # 캐시 무효화 후 재로딩
        get_news_from_rss.clear()
        with st.spinner("뉴스를 불러오는 중..."):
            st.session_state.news_list    = get_news_from_rss(rss_url, max_items)
            st.session_state.current_article = None
            st.session_state.ai_report    = None

    st.divider()

    # 북마크 영역
    if st.session_state.bookmarks:
        st.header("📌 북마크한 기사")
        for bm in st.session_state.bookmarks:
            st.markdown(f"- [{bm['title'][:25]}...]({bm['link']})")
    else:
        st.caption("북마크한 기사가 없습니다.")

# 최초 접속 시 뉴스 자동 로드
if not st.session_state.news_list:
    with st.spinner("최초 뉴스를 불러오는 중..."):
        st.session_state.news_list = get_news_from_rss(RSS_URLS["경제 전체"], 10)

# --- 메인 컨텐츠 ---
if not st.session_state.news_list:
    st.info("사이드바의 '🔄 뉴스 목록 새로고침' 버튼을 눌러주세요.")
    st.stop()

# 뉴스 목록 표시
news_titles = [f"{i+1:02d}. {n['title']}" for i, n in enumerate(st.session_state.news_list)]
selected_label = st.sidebar.radio("📰 기사 선택", news_titles)
selected_idx   = news_titles.index(selected_label)
selected_news  = st.session_state.news_list[selected_idx]

# 기사 변경 시 상태 초기화
if st.session_state.current_article != selected_news["title"]:
    st.session_state.current_article = selected_news["title"]
    st.session_state.ai_report       = None
    st.session_state.article_body    = None
    st.session_state.chat_history    = []
    st.session_state.sentiment_score = 50

# 기사 헤더
col_title, col_link, col_bookmark = st.columns([5, 1, 1])
with col_title:
    st.subheader(selected_news["title"])
    if selected_news.get("pub_date"):
        st.caption(f"🕐 {selected_news['pub_date']}")
with col_link:
    st.markdown(f"[🔗 원문]({selected_news['link']})")
with col_bookmark:
    is_bookmarked = any(bm["title"] == selected_news["title"] for bm in st.session_state.bookmarks)
    if st.button("★ 해제" if is_bookmarked else "☆ 북마크"):
        if is_bookmarked:
            st.session_state.bookmarks = [
                bm for bm in st.session_state.bookmarks if bm["title"] != selected_news["title"]
            ]
        else:
            st.session_state.bookmarks.append(selected_news)
        st.rerun()

# 기사 요약 미리보기
if selected_news.get("description"):
    with st.expander("📄 기사 미리보기"):
        st.write(selected_news["description"])

# AI 분석 버튼
if st.button("✨ AI 심층 분석", use_container_width=True, type="primary"):
    if not api_key:
        st.error("사이드바에서 Groq API 키를 먼저 입력해 주세요.")
    else:
        with st.spinner("기사 본문을 가져오는 중..."):
            st.session_state.article_body = get_article_content(selected_news["link"])
        with st.spinner("AI가 기사를 분석 중입니다... (10~20초 소요)"):
            client = get_groq_client(api_key)
            raw_report = analyze_news_with_groq(
                client, selected_news["title"], st.session_state.article_body
            )
            # 감성 점수 파싱
            score_match = re.search(r'\[SCORE\]\s*(\d+)\s*\[/SCORE\]', raw_report)
            if score_match:
                st.session_state.sentiment_score = min(100, max(0, int(score_match.group(1))))
                clean_report = re.sub(
                    r'### 🌡️ 감성 점수.*$', '', raw_report,
                    flags=re.MULTILINE | re.DOTALL
                ).strip()
                st.session_state.ai_report = clean_report
            else:
                st.session_state.ai_report = raw_report

            # 점수 히스토리에 추가 (중복 제거)
            if not any(h["title"] == selected_news["title"] for h in st.session_state.score_history):
                st.session_state.score_history.append({
                    "title": selected_news["title"],
                    "score": st.session_state.sentiment_score,
                })

# AI 분석 결과 출력
if st.session_state.ai_report:
    report_col, gauge_col = st.columns([7, 3])
    with report_col:
        with st.container(border=True):
            st.markdown(st.session_state.ai_report)
    with gauge_col:
        with st.container(border=True):
            fig = draw_gauge_chart(st.session_state.sentiment_score)
            st.plotly_chart(fig, use_container_width=True)
            score = st.session_state.sentiment_score
            if score >= 60:
                st.success(f"🟢 호재 ({score}점)")
            elif score >= 40:
                st.warning(f"🟡 중립 ({score}점)")
            else:
                st.error(f"🔴 악재 ({score}점)")

    st.divider()

    # 감성 점수 히스토리 차트
    if len(st.session_state.score_history) > 1:
        with st.expander("📊 분석 기사 감성 추이 보기"):
            st.plotly_chart(
                draw_score_history_chart(st.session_state.score_history),
                use_container_width=True
            )

    st.divider()

    # Q&A 챗봇 (멀티턴)
    st.subheader("💬 기사 관련 Q&A")
    st.caption("이 기사에 대해 궁금한 점을 자유롭게 물어보세요.")

    for message in st.session_state.chat_history:
        if message["role"] != "system":
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if user_input := st.chat_input("예: 이 기사가 삼성전자 주가에 미치는 영향은?"):
        if not api_key:
            st.error("Groq API 키를 입력해 주세요.")
        else:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("답변 생성 중..."):
                    client = get_groq_client(api_key)
                    answer = chat_with_groq(
                        client,
                        st.session_state.article_body,
                        [m for m in st.session_state.chat_history if m["role"] != "system"],
                        user_input
                    )
                    st.markdown(answer)

            st.session_state.chat_history.append({"role": "assistant", "content": answer})

            # 대화 초기화 버튼
            if st.button("🗑️ 대화 초기화"):
                st.session_state.chat_history = []
                st.rerun()
