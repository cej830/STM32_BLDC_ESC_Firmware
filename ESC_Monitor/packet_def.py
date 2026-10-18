import struct

# < : Little-Endian
# B  : header (0xAA)
# H  : ccr_current (uint16_t)
# B  : info (uint8_t)
# h  : BEMF_curr (int16_t)
# 5H : timestamp_start, timestamp_curr, timestamp_zc, delay_limited, delay_trigger (각 uint16_t)
# B  : delay_PAR (uint8_t)
# H  : ts_tim (uint16_t, 비교기 타이머 인풋캡쳐 타임스탬프)
# B  : cnt_ic (uint8_t, 비교기 엣지 발생 횟수)
# 3H : shunt_a, shunt_b, shunt_c (각 uint16_t, 원시값)
# B  : tail (0xBB)
# FW의 packed MotorTelemetry_t에서 cnt_ic 다음, tail 직전에 A/B/C 순서로 배치.
# 총 크기: 기존 21 + 6 = 27 바이트
PACKET_FORMAT = "<B H B h 5H B H B 3H B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 27 Byte

HEADER_BYTE = 0xAA
TAIL_BYTE = 0xBB

MOTOR_STATE_MAP = {
    0: "OPEN_LOOP",
    1: "CLOSE_LOOP",
    2: "CLOSE_LOCKIN"
}

ZC_EVENT_MAP = {
    0: "NOT_YET",
    1: "DETECTED",
    2: "ALREADY_OCCUR",
    3: "PASS"
}

TRIGGER_TIMEOUT_FORCE = 9999
TRIGGER_TIM_RACE = 9998
TRIGGER_RISK_FORCE = 9997
TRIGGER_REJECT_FORCE = 9996

def unpack_raw_packet(raw_bytes):
    unpacked = struct.unpack(PACKET_FORMAT, raw_bytes)
    info = unpacked[2]

    step = info & 0x0F
    motor_state_raw = (info >> 4) & 0x03
    zc_event_raw = (info >> 6) & 0x03

    return {
        "header": unpacked[0],
        "ccr": unpacked[1],
        "info_raw": info,
        "step": step,
        "motor_state_raw": motor_state_raw,
        "motor_state_str": MOTOR_STATE_MAP.get(motor_state_raw, "UNKNOWN"),
        "zc_event": zc_event_raw,
        "zc_event_str": ZC_EVENT_MAP.get(zc_event_raw, "UNKNOWN"),
        "bemf_curr": unpacked[3],
        "t_start": unpacked[4],
        "t_curr": unpacked[5],
        "t_zc": unpacked[6],             # ADC 선형보간 ts_zc
        "delay_limited": unpacked[7],
        "delay_trigger": unpacked[8],
        "delay_par": unpacked[9],
        "ts_tim": unpacked[10],           # 비교기 인풋캡쳐 ts_tim
        "cnt_ic": unpacked[11],           # 비교기 엣지 카운트
        "shunt_a": unpacked[12],
        "shunt_b": unpacked[13],
        "shunt_c": unpacked[14],
        "tail": unpacked[15]
    }
