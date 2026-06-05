import streamlit as st
import requests
from bs4 import BeautifulSoup
import g4f
import re
import plotly.graph_objects as go

# [1. 페이지 설정]
st.set_page_config(page_title="경제 뉴스 AI 인텔리전스", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .reportview-container .main .block-container{ padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# [2. 크롤링 함수 (URL과 페이지 파라미터 추가)]
def get_news_list(base_url, page):
    """지정된 URL과 페이지 번호에서 뉴스를 긁어옵니다."""
    # url 뒤에 ?page=번호 를 붙여서 최종 URL을 완성합니다.
    url = f"{base_url}?page={page}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.select('.news-list li')
        news_data = []
        for article in articles:
            title_element = article.select_one('.news-tit a')
            if not title_element: continue
            link = title_element['href']
            if not link.startswith('http'): link = "https://www.hankyung.com" + link
            news_data.append({"title": title_element.text.strip(), "link": link})
            if len(news_data) == 15: break
        return news_data
    except Exception as e: 
        st.error(f"목록을 불러오는 중 에러가 발생했습니다: {e}")
        return []

def get_article_content(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        content_div = soup.find('div', id='articletxt')
        if content_div:
            return "\n".join([line.strip() for line in content_div.get_text(separator="\n").split('\n') if line.strip()])
        return "본문 없음"
    except: return "에러"

# [3. 게이지 차트 생성 함수 (Plotly)]
def draw_gauge_chart(score):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': "시장 감성 온도", 'font': {'size': 20, 'color': 'gray'}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "#4B4B4B", 'thickness': 0.2}, 
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "rgba(0,0,0,0)", 
            'steps': [
                {'range': [0, 40], 'color': "rgba(255, 99, 132, 0.7)"},
                {'range': [40, 60], 'color': "rgba(255, 206, 86, 0.7)"},
                {'range': [60, 100], 'color': "rgba(75, 192, 192, 0.7)"}
            ],
        }
    ))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
    return fig

# [4. AI 분석 함수]
def analyze_news_with_ai(title, content):
    truncated_content = content[:1500] 
    prompt = f"""
    아래 경제 뉴스를 분석해줘.

    [제목]: {title}
    [본문]: {truncated_content}

    양식:
    ### 📝 핵심 세 줄 요약
    - 
    - 
    - 

    ### 💡 투자자를 위한 한 줄 코멘트
    - 

    ### 📉 시장 영향도 분석
    - 

    ### 🌡️ 감성 점수 (0점: 극단적 악재 ~ 100점: 극단적 호재)
    [SCORE](여기에 숫자만 0~100 사이로 적어줘)[/SCORE]
    """
    try:
        return g4f.ChatCompletion.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
    except Exception as e: return f"AI 분석 오류: {e}"

def chat_with_ai(article_content, previous_chat, user_question):
    prompt = f"[기사 본문]: {article_content[:1500]}\n[사용자 질문]: {user_question}"
    try:
        return g4f.ChatCompletion.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
    except: return "오류가 발생했습니다."

# [5. 메인 UI 구성]
st.title("📈 AI 경제 인사이트 대시보드")
st.markdown("관심 있는 섹션과 페이지를 자유롭게 탐색하며 경제 흐름을 파악하세요.")
st.divider()

# --- 사이드바 설정 영역 (업데이트 됨) ---
with st.sidebar:
    st.header("⚙️ 탐색 설정")
    
    # 1. 카테고리 선택 및 동적 URL 생성
    category = st.selectbox(
        "뉴스 섹션 선택", 
        ["거시경제", "경제정책", "증권", "부동산", "URL 직접 입력..."]
    )
    
    if category == "거시경제":
        target_url = "https://www.hankyung.com/economy/macro"
    elif category == "경제정책":
        target_url = "https://www.hankyung.com/economy/economic-policy"
    elif category == "증권":
        target_url = "https://www.hankyung.com/finance"
    elif category == "부동산":
        target_url = "https://www.hankyung.com/realestate"
    else:
        # 웹사이트 주소가 바뀌거나 다른 섹션을 보고 싶을 때 대비
        target_url = st.text_input("크롤링할 기본 URL을 입력하세요:", value="https://www.hankyung.com/economy/macro")
    
    # 2. 페이지 번호 선택
    page_num = st.number_input("페이지 번호", min_value=0, value=1, step=1)
    
    # 3. 뉴스 목록 업데이트 버튼
    if st.button("🔄 뉴스 목록 새로고침", use_container_width=True):
        with st.spinner("뉴스를 불러오는 중..."):
            st.session_state.news_list = get_news_list(target_url, page_num)
            # 목록이 바뀌면 기존 선택된 기사 정보도 초기화
            st.session_state.current_article = None
            st.session_state.ai_report = None
            
    st.divider()
    st.header("📌 오늘의 주요 뉴스")

# 최초 접속 시 뉴스 목록 로드
if "news_list" not in st.session_state:
    with st.spinner("최초 뉴스를 불러오는 중..."): 
        st.session_state.news_list = get_news_list("https://www.hankyung.com/economy/macro", 1)

# 뉴스 목록이 있을 경우 표시
if st.session_state.get("news_list"):
    news_titles = [f"{i+1:02d}. {n['title']}" for i, n in enumerate(st.session_state.news_list)]
    selection = st.sidebar.radio("기사를 선택하세요:", news_titles)

    selected_idx = news_titles.index(selection)
    selected_news = st.session_state.news_list[selected_idx]
    
    col1, col2 = st.columns([4, 1])
    with col1: st.subheader(selected_news['title'])
    with col2: st.markdown(f"[🔗 기사 원문]({selected_news['link']})")

    if "current_article" not in st.session_state or st.session_state.current_article != selected_news['title']:
        st.session_state.current_article = selected_news['title']
        st.session_state.ai_report = None
        st.session_state.article_body = None
        st.session_state.chat_history = []
        st.session_state.sentiment_score = 50

    if st.button("✨ 이 기사 AI 심층 분석하기", use_container_width=True):
        st.session_state.article_body = get_article_content(selected_news['link'])
        with st.spinner("AI가 기사를 분석하고 감성 지수를 산출 중입니다..."):
            raw_report = analyze_news_with_ai(selected_news['title'], st.session_state.article_body)
            score_match = re.search(r'\[SCORE\]\s*(\d+)\s*\[/SCORE\]', raw_report)
            if score_match:
                st.session_state.sentiment_score = int(score_match.group(1))
                clean_report = re.sub(r'### 🌡️ 감성 점수.*$', '', raw_report, flags=re.MULTILINE|re.DOTALL)
                st.session_state.ai_report = clean_report.strip()
            else:
                st.session_state.ai_report = raw_report 

    if st.session_state.ai_report:
        report_col, gauge_col = st.columns([7, 3])
        with report_col:
            with st.container(border=True): st.markdown(st.session_state.ai_report)
        with gauge_col:
            with st.container(border=True):
                fig = draw_gauge_chart(st.session_state.sentiment_score)
                st.plotly_chart(fig, use_container_width=True)
            
        st.divider()
        st.subheader("💬 기사 관련 Q&A")
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]): st.markdown(message["content"])

        if prompt := st.chat_input("이 기사와 관련된 궁금한 점을 물어보세요!"):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("답변을 생각 중입니다..."):
                    answer = chat_with_ai(st.session_state.article_body, st.session_state.chat_history, prompt)
                    st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
else:
    st.info("사이드바에서 '🔄 뉴스 목록 새로고침' 버튼을 눌러주세요.")