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
LIMIT_US_VALID = 100        # 이하 편차 -> VALID
LIMIT_US_RISK = 500         # 이상 -> 바로 REJECT 

# RISK가 연속 몇 회 터져야 REJECT 1회로 판정할 것인가
REJECT_COUNT = 8             # 연속 5회 초과 시 REJECT 발생


# [신규] 시퀀스 요약 버퍼 설정
SEQUENCE_CYCLES_LEN = 100     # 백그라운드에 유지할 전기각 회전수 (100바퀴 = 600행)
SEQUENCE_BUFFER_LEN = SEQUENCE_CYCLES_LEN * 6


# ==========================================
# 모터 하드웨어 스펙
# ==========================================
MOTOR_KV = 1000          # 1000 KV
MOTOR_POLES = 14         # 14극
MOTOR_POLE_PAIRS = MOTOR_POLES // 2  # 7극쌍


# UI 갱신 주기
GUI_REFRESH_INTERVAL_MS = 100  # 100ms (10Hz)