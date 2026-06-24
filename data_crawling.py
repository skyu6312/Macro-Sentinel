import sqlite3
import datetime
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf

# ==========================================
# 1. 로컬 DB 연결 및 테이블 초기화 (SQLite)
# ==========================================
conn = sqlite3.connect('macro_sentinel.db')
cursor = conn.cursor()

# 위의 SQL 스키마를 SQLite 문법에 맞춰 생성
cursor.executescript('''
CREATE TABLE IF NOT EXISTS countries (
    country_id TEXT PRIMARY KEY,
    country_name TEXT NOT NULL,
    currency TEXT
);

CREATE TABLE IF NOT EXISTS indicator_master (
    indicator_id TEXT PRIMARY KEY,
    indicator_name TEXT NOT NULL,
    frequency TEXT NOT NULL,
    source TEXT
);

CREATE TABLE IF NOT EXISTS macro_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id TEXT,
    indicator_id TEXT,
    record_date TEXT NOT NULL,
    value REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(country_id) REFERENCES countries(country_id),
    FOREIGN KEY(indicator_id) REFERENCES indicator_master(indicator_id),
    UNIQUE(country_id, indicator_id, record_date)
);
''')

# ==========================================
# 2. 마스터(기본) 데이터 세팅 (Seed Data)
# ==========================================
# 국가 정보 입력
cursor.executescript('''
INSERT OR IGNORE INTO countries (country_id, country_name, currency) 
VALUES ('US', 'United States', 'USD');
''')

# 수집할 3대 핵심 지표 정의 (기준금리, 소비자물가지수, 10년-2년 장단기 금리차)
indicators = [
    ('FEDFUNDS', 'Federal Funds Effective Rate (기준금리)', 'Monthly', 'FRED'),
    ('CPIAUCSL', 'Consumer Price Index (소비자물가지수)', 'Monthly', 'FRED'),
    ('T10Y2Y', '10-Year Treasury Constant Maturity Minus 2-Year', 'Daily', 'FRED')
]
cursor.executemany('''
INSERT OR IGNORE INTO indicator_master (indicator_id, indicator_name, frequency, source)
VALUES (?, ?, ?, ?);
''', indicators)
conn.commit()

# ==========================================
# 3. 데이터 추출 (Extract) & 적재 (Load)
# ==========================================
start_date = datetime.datetime(2010, 1, 1)
end_date = datetime.date.today()

print("🚀 FRED로부터 매크로 데이터 수집을 시작합니다...")

for ind_id, _, _, _ in indicators:
    try:
        # FRED API로부터 데이터 다운로드 (Pandas DataFrame)
        df = web.DataReader(ind_id, 'fred', start_date, end_date)
        df = df.dropna().reset_index()
        
        # DB에 넣기 좋게 가공 (Transform)
        # 튜플 형태의 리스트로 변환: [('US', 'FEDFUNDS', '2023-10-01', 5.33), ...]
        db_data = [
            ('US', ind_id, row['DATE'].strftime('%Y-%m-%d'), float(row[ind_id]))
            for _, row in df.iterrows()
        ]
        
        # DB에 대량 삽입 (Load)
        cursor.executemany('''
        INSERT OR IGNORE INTO macro_history (country_id, indicator_id, record_date, value)
        VALUES (?, ?, ?, ?);
        ''', db_data)
        conn.commit()
        print(f"✅ 지표 [{ind_id}] 적재 완료: {len(db_data)}개의 레코드")
        
    except Exception as e:
        print(f"❌ 지표 [{ind_id}] 수집 실패: {e}")

# 데이터가 잘 들어갔는지 SQL 쿼리로 슬쩍 확인해보기
df_check = pd.read_sql_query('''
SELECT h.record_date, m.indicator_name, h.value 
FROM macro_history h
JOIN indicator_master m ON h.indicator_id = m.indicator_id
LIMIT 5;
''', conn)

print("\n📊 데이터베이스 적재 결과 샘플 (SQL JOIN 결과):")
print(df_check)

conn.close()