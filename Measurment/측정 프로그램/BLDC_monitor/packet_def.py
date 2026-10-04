import struct

PACKET_FORMAT = "<B H B h 5H B B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 18 Byte

HEADER_BYTE = 0xAA
TAIL_BYTE = 0xBB


# 모터 제어 상태 매핑
MOTOR_STATE_MAP = {
    0: "OPEN_LOOP",
    1: "CLOSE_LOOP",
    2: "CLOSE_LOCKIN"
}


# ZC 이벤트 매핑
ZC_EVENT_MAP = {
    0: "NOT_YET",
    1: "DETECTED",
    2: "ALREADY_OCCUR",
    3: "PASS"
}


# ZC 상태 정의
ZC_SEARCHING = 0
ZC_DETECTED = 1
ZC_TIMEOUT = 2

# 특수 플래그 정의
TRIGGER_TIMEOUT_FORCE = 9999    # 최종 타임아웃 강제 정류 마커

TRIGGER_TIM_RACE = 9998         # ADC 진행 중 TIM 인터럽트 침투 (제외 대상)
TRIGGER_RISK_FORCE = 9997       # 최종 RISK 누적으로 인한 정지
TRIGGER_REJECT_FORCE = 9996     # 최종 REJECT 범위 duration 으로 인한 정지

def unpack_raw_packet(raw_bytes):
    """18바이트 바이너리 데이터를 딕셔너리로 언패킹"""
    unpacked = struct.unpack(PACKET_FORMAT, raw_bytes)
    info = unpacked[2]
    
    # 비트 필드 디코딩
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
        "t_zc": unpacked[6],
        "delay_limited": unpacked[7],
        "delay_trigger": unpacked[8],
        "seq": unpacked[9],
        "tail": unpacked[10]
    }