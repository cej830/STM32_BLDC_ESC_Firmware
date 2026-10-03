# ==========================================
# 통신 및 버퍼 설정
# ==========================================
DEFAULT_PORT = "COM4"
DEFAULT_BAUDRATE = 115200
COMM_TIMEOUT = 0.05       # 50ms (모터 정지 감지 기준)
ROLLING_BUFFER_LEN = 600  # 최근 유지할 최대 샘플 수

# ==========================================
# zc_duration (t_zc - t_start) 판정 임계치
# ==========================================
LIMIT_US_VALID = 50        # 40us 이하 편차 -> VALID
LIMIT_US_RISK = 150         # 90us 이하 편차 -> RISK (초과시 REJECT)

# RISK가 연속 몇 회 터져야 REJECT 1회로 판정할 것인가
REJECT_COUNT = 8             # 연속 5회 초과 시 REJECT 발생

THRESHOLD_PCT_VALID = 8.0  # 8.0% 이하 변동 -> VALID
THRESHOLD_PCT_RISK = 18.0  # 18.0% 이하 변동 -> RISK

# UI 갱신 주기
GUI_REFRESH_INTERVAL_MS = 100  # 100ms (10Hz)