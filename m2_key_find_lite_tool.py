import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
import json
import pandas as pd
import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 1. API 설정 (st.secrets 사용 권장)
# ==========================================
# 실제 배포 시에는 Streamlit Cloud의 Secrets 설정을 이용하세요.
AD_CUSTOMER_ID = '4242379'
AD_ACCESS_LICENSE = '0100000000be60fd64d572d7bbd6fb5003c04aa9fe6968d0512dd5dd9111328f3ca2ae9eb5'
AD_SECRET_KEY = 'AQAAAAC+YP1k1XLXu9b7UAPASqn+j7RoBGxd+yeQ35LFZBgkuw=='
SEARCH_CLIENT_ID = 'FlFFNqzQOrBJIu1W1wX4'
SEARCH_CLIENT_SECRET = 'XMeMWgMHsN'

# ==========================================
# 2. 기능 함수 정의 (기존 로직 유지)
# ==========================================

def get_naver_autocomplete_keywords(keyword):
    url = f"https://ac.search.naver.com/nx/ac?q={keyword}&con=1&frm=nv&ans=2&r_format=json&r_enc=UTF-8&st=100"
    try:
        res = requests.get(url, timeout=5)
        items = res.json().get('items')
        if items: return [item[0] for item in items[0]]
        return []
    except: return []

def get_ad_header(method, uri):
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}.{method}.{uri}"
    hash = hmac.new(AD_SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    signature = base64.b64encode(hash).decode('utf-8')
    return {'Content-Type': 'application/json; charset=UTF-8', 'X-Timestamp': timestamp, 'X-API-KEY': AD_ACCESS_LICENSE, 'X-Customer': str(AD_CUSTOMER_ID), 'X-Signature': signature}

def fetch_extended_naver_stats(keywords):
    BASE_URL = 'https://api.searchad.naver.com'
    uri = "/keywordstool"
    extended_data = {}
    unique_kws = list(set([k.replace(" ", "") for k in keywords if k]))
    
    # 웹 UI를 위한 프로그레스 바 생성
    progress_bar = st.progress(0)
    for i in range(0, len(unique_kws), 5):
        chunk = unique_kws[i:i+5]
        params = {'hintKeywords': ",".join(chunk), 'showDetail': '1'}
        headers = get_ad_header('GET', uri)
        try:
            res = requests.get(BASE_URL + uri, params=params, headers=headers, timeout=10)
            if res.status_code == 200:
                for item in res.json().get('keywordList', []):
                    kw = item['relKeyword']
                    pc = 5 if item.get('monthlyPcQcCnt') == '< 10' else int(item.get('monthlyPcQcCnt', 0))
                    mo = 5 if item.get('monthlyMobileQcCnt') == '< 10' else int(item.get('monthlyMobileQcCnt', 0))
                    extended_data[kw] = pc + mo
            time.sleep(0.1)
        except: continue
        progress_bar.progress((i + 5) / len(unique_kws) if (i + 5) < len(unique_kws) else 1.0)
    return extended_data

def get_blog_count(keyword):
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {"X-Naver-Client-Id": SEARCH_CLIENT_ID, "X-Naver-Client-Secret": SEARCH_CLIENT_SECRET}
    params = {"query": keyword, "display": 1}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        return res.json().get('total', 0)
    except: return 0

# ==========================================
# 3. Streamlit 웹 화면 구성
# ==========================================

st.set_page_config(page_title="네이버 키워드 분석기", layout="wide")
st.title("🔍 네이버 키워드 경쟁도 분석 도구")

seed = st.text_input("분석할 키워드를 입력하세요", placeholder="예: 무선 이어폰")

if st.button("분석 시작"):
    if seed:
        with st.spinner('데이터 수집 및 분석 중...'):
            # 1. 기초 키워드 확보
            st.info("[1/3] 네이버 자동완성 키워드 추출 중...")
            ac_pool = get_naver_autocomplete_keywords(seed)
            target_list = list(set([seed] + ac_pool))
            st.write(f"✅ 분석 대상: {len(target_list)}개 확보")

            # 2. 검색량 조회
            st.info("[2/3] 키워드별 검색량 조회 중...")
            naver_stats = fetch_extended_naver_stats(target_list)
            
            # 3. 경쟁도 분석 (병렬 처리)
            st.info("[3/3] 블로그 발행량 및 경쟁도 병렬 분석 중...")
            final_results = []
            
            def process_keyword(kw):
                vol = naver_stats.get(kw.replace(" ", ""), 5)
                if vol == 0: vol = 5
                blog_cnt = get_blog_count(kw)
                ratio = round(blog_cnt / vol, 2)
                return [kw, vol, blog_cnt, ratio]

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(process_keyword, kw): kw for kw in target_list}
                for future in as_completed(futures):
                    final_results.append(future.result())

            # 4. 결과 정리 및 출력
            df = pd.DataFrame(final_results, columns=['키워드', '총검색량', '블로그수', '경쟁률'])
            main_row = df[df['키워드'] == seed]
            other_rows = df[df['키워드'] != seed].sort_values(by=['경쟁률', '총검색량'], ascending=[True, False])
            display_df = pd.concat([main_row, other_rows])

            st.success(f"🏆 '{seed}' 분석 완료!")
            st.dataframe(display_df, use_container_width=True)
            
            # 5. CSV 다운로드 버튼 추가
            csv = display_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="분석 결과 CSV 다운로드",
                data=csv,
                file_name=f"analysis_{seed}.csv",
                mime="text/csv",
            )
    else:
        st.warning("키워드를 입력해 주세요.")
