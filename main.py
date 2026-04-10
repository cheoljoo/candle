import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime

def analyze_kospi200_trend():
    print("KOSPI 200 종목 분석을 시작합니다. 잠시만 기다려주세요...")
    
    # 1. KOSPI 200 종목 리스트 가져오기
    df_krx = fdr.StockListing('KOSPI')
    # KOSPI 200 구성 종목을 정확히 필터링하기 위해 보통은 인덱스 정보를 쓰지만, 
    # 여기서는 예시로 KOSPI 상위 종목 혹은 특정 리스트를 가정합니다.
    # FDR에서 직접적인 KOSPI 200 리스트를 제공하지 않을 경우 상위 200개를 예시로 합니다.
    kospi200_list = df_krx.head(200) 

    results = []

    for index, row in kospi200_list.iterrows():
        symbol = row['Code']
        name = row['Name']
        
        try:
            # 2. 일봉 데이터 → 월봉으로 리샘플링 (충분한 기간 확보)
            df_daily = fdr.DataReader(symbol)
            if df_daily is None or df_daily.empty:
                continue
            df_monthly = df_daily['Close'].resample('ME').last().dropna()
            
            if len(df_monthly) < 10:
                continue
                
            # 3. 현재가 및 10월 이평선 계산 (종가 기준)
            current_price = df_daily.iloc[-1]['Close']  # 최근 일봉 종가 (현재가)
            
            # 주가 3,000원 이상 필터링
            if current_price < 3000:
                continue
                
            # 10월 이동평균 계산 (최근 10개 월봉 종가의 평균)
            ma10 = df_monthly.rolling(window=10).mean().iloc[-1]
            
            # 4. 위치 및 백분율 계산
            diff_ratio = ((current_price - ma10) / ma10) * 100
            status = "위(매수/보유)" if current_price > ma10 else "아래(관망/매도)"
            
            results.append({
                '종목명': name,
                '현재가': int(current_price),
                '10월이평': round(ma10, 2),
                '상태': status,
                '이격률(%)': round(diff_ratio, 2)
            })
            
        except Exception as e:
            continue

    # 결과 출력
    result_df = pd.DataFrame(results)
    if result_df.empty:
        print("분석된 결과가 없습니다.")
        return
    # 이격률 순으로 정렬 (상승 추세가 강한 순)
    result_df = result_df.sort_values(by='이격률(%)', ascending=False)
    
    print(f"\n기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print(result_df.to_string(index=False))
    
    # 파일로 저장하고 싶다면 아래 주석 해제
    # result_df.to_csv("kospi200_trend_analysis.csv", encoding='utf-8-sig')

if __name__ == "__main__":
    analyze_kospi200_trend()
