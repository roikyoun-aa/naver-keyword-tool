# -*- coding: utf-8 -*-
import time
import hashlib
import hmac
import base64
import requests
import json
import pandas as pd
import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed # 병렬 처리를 위한 라이브러리
#import keyboard
import time


# ==========================================
# 네이버 자동생성 키워드 + 자체 확장 api 사용하여 경쟁도 분석 결과를 병렬로 빠르게 처리
# ==========================================
GEMINI_API_KEY = "AIzaSyCkwGe91wy_3frUAZmEjzrQSV_Bus1kG7o"
AD_CUSTOMER_ID = '4242379'
AD_ACCESS_LICENSE = '0100000000be60fd64d572d7bbd6fb5003c04aa9fe6968d0512dd5dd9111328f3ca2ae9eb5'
AD_SECRET_KEY = 'AQAAAAC+YP1k1XLXu9b7UAPASqn+j7RoBGxd+yeQ35LFZBgkuw=='
SEARCH_CLIENT_ID = 'FlFFNqzQOrBJIu1W1wX4'
SEARCH_CLIENT_SECRET = 'XMeMWgMHsN'

# ==========================================
# 2. 기능 함수 정의
# ==========================================

def get_naver_autocomplete_keywords(keyword):
    """네이버 실시간 자동완성 추출"""
    url = f"https://ac.search.naver.com/nx/ac?q={keyword}&con=1&frm=nv&ans=2&r_format=json&r_enc=UTF-8&st=100"
    try:
        res = requests.get(url, timeout=5)
        items = res.json().get('items')
        if items: return [item[0] for item in items[0]]
        return []
    except: return []

def get_ad_header(method, uri):
    """광고 API 헤더 생성"""
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}.{method}.{uri}"
    hash = hmac.new(AD_SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    signature = base64.b64encode(hash).decode('utf-8')
    return {'Content-Type': 'application/json; charset=UTF-8', 'X-Timestamp': timestamp, 'X-API-KEY': AD_ACCESS_LICENSE, 'X-Customer': str(AD_CUSTOMER_ID), 'X-Signature': signature}

def fetch_extended_naver_stats(keywords):
    """네이버 광고 API를 통한 검색량 수집"""
    BASE_URL = 'https://api.searchad.naver.com'
    uri = "/keywordstool"
    extended_data = {}
    unique_kws = list(set([k.replace(" ", "") for k in keywords if k]))
    
    for i in tqdm(range(0, len(unique_kws), 5), desc="🔍 네이버 통계 데이터 수집 중"):
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
    return extended_data

def get_blog_count(keyword):
    """블로그 발행량 조회"""
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {"X-Naver-Client-Id": SEARCH_CLIENT_ID, "X-Naver-Client-Secret": SEARCH_CLIENT_SECRET}
    params = {"query": keyword, "display": 1}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        return res.json().get('total', 0)
    except: return 0

# ==========================================
# 3. 메인 프로세스 (병렬 처리 적용)
# ==========================================

def main():
    print("프로그램이 시작되었습니다. 종료하려면 'ESC'를 누르세요.")
    while True:
        seed = input("🔍 분석할 키워드를 입력하세요: ").strip()
        if not seed: return

        # 1. 기초 키워드 확보
        print(f"\n[1/3] 네이버 자동완성 키워드 추출 중...")
        ac_pool = get_naver_autocomplete_keywords(seed)
        target_list = list(set([seed] + ac_pool))
        print(f"      ✅ 분석 대상: {len(target_list)}개 확보")

        # 2. 검색량 조회
        print(f"\n[2/3] 확보된 키워드들의 실제 검색량 조회 중...")
        naver_stats = fetch_extended_naver_stats(target_list)
        
        # 3. 경쟁도 분석 (병렬 처리 핵심 구간)
        print(f"\n[3/3] 블로그 발행량 및 경쟁도 병렬 분석 중...")
        final_results = []
        
        # 병렬 처리를 위한 개별 작업 함수
        def process_keyword(kw):
            vol = naver_stats.get(kw.replace(" ", ""), 5) # 광고 API는 공백없이 반환되므로 보정
            if vol == 0: vol = 5
            blog_cnt = get_blog_count(kw)
            ratio = round(blog_cnt / vol, 2)
            return [kw, vol, blog_cnt, ratio]

        # ThreadPoolExecutor를 사용한 병렬 처리
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 작업들을 큐에 등록
            futures = {executor.submit(process_keyword, kw): kw for kw in target_list}
            
            # 완료되는 순서대로 결과 수집 및 진행바 표시
            for future in tqdm(as_completed(futures), total=len(target_list), desc="📊 병렬 분석 진행"):
                final_results.append(future.result())

        # 4. 결과 정리 및 저장
        df = pd.DataFrame(final_results, columns=['키워드', '총검색량', '블로그수', '경쟁률'])
        
        # 메인 키워드 강조 및 정렬
        main_row = df[df['키워드'] == seed]
        other_rows = df[df['키워드'] != seed].sort_values(by=['경쟁률', '총검색량'], ascending=[True, False])
        
        # 출력용 데이터프레임 (메인 키워드를 맨 위로)
        display_df = pd.concat([main_row, other_rows])

        print("\n" + "="*60)
        print(f"🏆 '{seed}' 분석 결과 (메인 키워드 상단 배치)")
        print("="*60)
        print(display_df.to_string(index=False))
        # ESC 키가 눌렸는지 확인
        if keyboard.is_pressed('esc'):
            print("\nESC 입력 감지. 프로그램을 종료합니다.")
            break

       # now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        #filename = f"병렬필터분석_{seed}_{now}.csv"
        #display_df.to_csv(filename, index=False, encoding='utf-8-sig')
        #print(f"\n✅ 저장 완료: {filename}")

if __name__ == '__main__':

    main()
