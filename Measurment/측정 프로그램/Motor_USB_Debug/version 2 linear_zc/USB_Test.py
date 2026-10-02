import serial
import struct
import time

PACKET_FORMAT = "<B 4H 2H B 2h 4H 3H B B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)

HEADER_BYTE = 0xAA
TAIL_BYTE = 0xBB

PORT = "COM4"
BAUDRATE = 115200
TIMEOUT = 1.0


def parse_packet(raw_bytes):
    return struct.unpack(PACKET_FORMAT, raw_bytes)


def main():
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
        print(f"[{PORT}] 연결 완료. 8비트 시퀀스 카운터 기반 패킷 유실률 분석을 시작합니다.")
    except Exception as e:
        print(f"포트 연결 실패: {e}")
        return

    ser.reset_input_buffer()

    total_received = 0
    sync_errors = 0
    total_lost_packets = 0
    consecutive_loss_events = 0

    last_seq = None
    last_t_curr = None
    last_display_time = time.time()
    dt_history = []

    try:
        while True:
            # 1. 헤더 동기화
            header = ser.read(1)
            if not header:
                continue

            if header[0] != HEADER_BYTE:
                sync_errors += 1
                continue

            # 2. 페이로드 읽기
            payload = ser.read(PACKET_SIZE - 1)
            if len(payload) < PACKET_SIZE - 1:
                continue

            full_packet = header + payload

            # 3. 테일 검증
            if full_packet[-1] != TAIL_BYTE:
                sync_errors += 1
                continue

            # 4. 언패킹
            (
                hdr,
                phase_A, phase_B, phase_C, vcom_adc,
                ccr_target, ccr_current,
                info,
                BEMF_prev, BEMF_curr,
                t_start, t_prev, t_curr, t_zc,
                delay_target, delay_limited, delay_trigger,
                delay_PAR,  # <-- 8비트 시퀀스 카운터 (0 ~ 255)
                tail
            ) = parse_packet(full_packet)

            total_received += 1
            current_seq = delay_PAR

            # 5. 8비트 시퀀스 연속성 검증
            if last_seq is not None:
                # 8비트 롤오버 연산: (현재값 - 이전값) & 0xFF
                diff = (current_seq - last_seq) & 0xFF

                if diff == 1:
                    # 정상 수신 (연속)
                    pass
                elif diff == 0:
                    # 중복 패킷
                    print(f"\n[경고] 동일 시퀀스 중복 수신: SEQ={current_seq}")
                else:
                    # 패킷 유실 발생
                    lost_count = diff - 1
                    total_lost_packets += lost_count
                    consecutive_loss_events += 1

            last_seq = current_seq

            # 6. dt 주기 계산 (50us 기준)
            if last_t_curr is not None:
                dt = (t_curr - last_t_curr) & 0xFFFF
                dt_history.append(dt)
                if len(dt_history) > 100:
                    dt_history.pop(0)
            last_t_curr = t_curr

            # 7. 0.25초 주기 화면 출력
            now = time.time()
            if now - last_display_time >= 0.25:
                last_display_time = now
                avg_dt = (sum(dt_history) / len(dt_history)) if dt_history else 0.0

                # 유실률 계산 (%)
                total_expected = total_received + total_lost_packets
                loss_rate = (total_lost_packets / total_expected * 100.0) if total_expected > 0 else 0.0

                step = info & 0x0F
                is_closed_loop = (info >> 4) & 0x01
                zc_event = (info >> 5) & 0x01

                print("\033[H\033[J", end="")
                print("================== [BLDC 텔레메트리 유실률 정밀 분석] ==================")
                print(f"수신 통계     : 총 수신 {total_received} 개 | 동기화 에러: {sync_errors} 회")
                print(f"패킷 시퀀스   : 현재 SEQ=[{current_seq:3d}] | 유실 횟수(Event): {consecutive_loss_events} 회")
                print(f"총 유실 패킷  : {total_lost_packets} 개 누락 | 유실률: {loss_rate:.2f} %")
                print(f"50us 주기검증 : 최근 100샘플 평균 dt: {avg_dt:.1f} us")
                print("----------------------------------------------------------------------")
                loop_str = "CLOSED_LOOP" if is_closed_loop else "OPEN_LOOP"
                zc_str = "DETECTED!" if zc_event else "Searching"
                print(f"제어 상태     : Step [{step}] | 모드: [{loop_str}] | ZC: [{zc_str}]")
                print(f"상 전압(ADC)  : A={phase_A:4d} | B={phase_B:4d} | C={phase_C:4d} | VCOM={vcom_adc:4d}")
                print(f"타임스탬프    : Start={t_start:5d} | Prev={t_prev:5d} | Curr={t_curr:5d} | ZC={t_zc:5d}")
                print(f"딜레이(us)    : Target={delay_target:5d} | Limited={delay_limited:5d} | Trigger={delay_trigger:5d}")
                print("======================================================================")

    except KeyboardInterrupt:
        print("\n수신을 중단합니다.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()