import serial
import struct
import time

PORT = 'COM4'
BAUDRATE = 115200

# 22 Bytes 구조체 포맷 (<: Little-Endian, 타이트 패킹)
PACKET_FORMAT = "<B H H H H H H H B H H B B"
SAMPLE_SIZE = struct.calcsize(PACKET_FORMAT)  # 정확히 22 Bytes

EXPECTED_HEADER = 0xAA
EXPECTED_TAIL   = 0xBB

def main():
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=1)
        ser.reset_input_buffer()
        print(f"[{PORT}] 연결 성공. 정밀 동기화 텔레메트리 파싱 시작...")
    except Exception as e:
        print(f"포트 연결 오류: {e}")
        return

    buf = bytearray()
    print_counter = 0

    try:
        while True:
            data = ser.read(ser.in_waiting or 440)
            if not data:
                continue
            buf.extend(data)

            # 최소 1개 샘플(22바이트) 이상 쌓였을 때 검사
            while len(buf) >= SAMPLE_SIZE:
                # 1. 헤더(0xAA)와 테일(0xBB)이 정확한 위치에 모두 존재하는지 검증
                if buf[0] == EXPECTED_HEADER and buf[SAMPLE_SIZE - 1] == EXPECTED_TAIL:
                    sample_raw = buf[:SAMPLE_SIZE]
                    buf = buf[SAMPLE_SIZE:]

                    unpacked = struct.unpack(PACKET_FORMAT, sample_raw)

                    header      = unpacked[0]
                    phase_a     = unpacked[1]
                    phase_b     = unpacked[2]
                    phase_c     = unpacked[3]
                    vcom        = unpacked[4]
                    ccr_tgt     = unpacked[5]
                    ccr_cur     = unpacked[6]
                    laptime     = unpacked[7]
                    step_info   = unpacked[8]
                    d_tgt       = unpacked[9]
                    d_cur       = unpacked[10]
                    d_par       = unpacked[11]
                    tail        = unpacked[12]

                    print_counter += 1
                    if print_counter >= 200:  # 100Hz 주기로 화면 표시
                        print_counter = 0
                        step = (step_info & 0x0F) + 1
                        is_closed_loop = (step_info >> 4) & 0x01
                        loop_str = "CL" if is_closed_loop else "OL"

                        print(f"HDR:0x{header:02X} | Step:{step}({loop_str}) | "
                              f"A:{phase_a:4d} B:{phase_b:4d} C:{phase_c:4d} VCOM:{vcom:4d} | "
                              f"CCR:{ccr_cur:4d}/{ccr_tgt:4d} | Lap:{laptime:4d}us | "
                              f"D30:{d_cur:4d}/{d_tgt:4d} PAR:{d_par:2d} | TAIL:0x{tail:02X}")
                else:
                    # 헤더나 테일이 어긋난 경우 1바이트 버리고 다음 0xAA를 탐색
                    buf.pop(0)

    except KeyboardInterrupt:
        print("\n모니터링 종료")
    finally:
        ser.close()

if __name__ == '__main__':
    main()