import struct

PACKET_FORMAT = "<B H B h 5H B B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 18 Byte

HEADER_BYTE = 0xAA
TAIL_BYTE = 0xBB

# 특수 플래그 정의
TRIGGER_TIM_RACE = 9998        # ADC 진행 중 TIM 인터럽트 침투 (제외 대상)
TRIGGER_TIMEOUT_FORCE = 9999   # 최종 타임아웃 강제 정류 마커

# ZC 상태 정의
ZC_SEARCHING = 0
ZC_DETECTED = 1
ZC_TIMEOUT = 2

def unpack_raw_packet(raw_bytes):
    """18바이트 바이너리 데이터를 딕셔너리로 언패킹"""
    unpacked = struct.unpack(PACKET_FORMAT, raw_bytes)
    info = unpacked[2]
    
    return {
        "header": unpacked[0],
        "ccr": unpacked[1],
        "step": info & 0x0F,
        "is_closed_loop": (info >> 4) & 0x01,
        "zc_event": (info >> 5) & 0x03,
        "bemf_curr": unpacked[3],
        "t_start": unpacked[4],
        "t_curr": unpacked[5],
        "t_zc": unpacked[6],
        "delay_limited": unpacked[7],
        "delay_trigger": unpacked[8],
        "seq": unpacked[9],
        "tail": unpacked[10]
    }