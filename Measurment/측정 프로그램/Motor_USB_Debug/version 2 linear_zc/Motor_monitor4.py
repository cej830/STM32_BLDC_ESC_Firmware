import serial
import struct
import time
import os
import csv
import msvcrt  # Windows 키 입력 감지용
from collections import deque

# ==============================================================================
# 1. 18바이트 패킷 구조체 정의
# ==============================================================================
#  B : uint8_t  header (0xAA)
#  H : uint16_t ccr_current
#  B : uint8_t  info (Step, OL/CL, ZC_event)
#  h : int16_t  BEMF_curr
#  H : uint16_t timestamp_start
#  H : uint16_t timestamp_curr
#  H : uint16_t timestamp_zc
#  H : uint16_t delay_limited
#  H : uint16_t delay_trigger
#  B : uint8_t  delay_PAR (8비트 시퀀스 번호)
#  B : uint8_t  tail (0xBB)
PACKET_FORMAT = "<B H B h 5H B B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 정확히 18 Byte

HEADER_BYTE = 0xAA
TAIL_BYTE = 0xBB

PORT = "COM4"
BAUDRATE = 115200
TIMEOUT = 0.05  # 모터 정지 감지용 타임아웃 (50ms 동안 데이터 없으면 정지로 간주)

MAX_BUFFER_LEN = 600  # 최근 유지할 최대 샘플 수 (50us 기준 약 30ms 분량)


def parse_packet(raw_bytes):
    return struct.unpack(PACKET_FORMAT, raw_bytes)


def save_to_csv(data_deque, trigger_reason="USER_TRIGGER"):
    if not data_deque:
        print("\n[알림] 저장할 수집 데이터가 없습니다.")
        return

    data_list = list(data_deque)
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    filename = f"bldc_telemetry_{trigger_reason}_{timestamp_str}.csv"
    fieldnames = list(data_list[0].keys())

    try:
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data_list)
        print(f"\n======================================================================")
        print(f" [CSV 저장 완료] 파일명: {filename}")
        print(f" 저장 사유: {trigger_reason} | 저장된 샘플 수: {len(data_list)} 개")
        print(f"======================================================================\n")
    except Exception as e:
        print(f"\n[저장 실패] {e}")


def main():
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
        print(f"[{PORT}] 연결 완료 (패킷 크기: {PACKET_SIZE} Byte)")
    except Exception as e:
        print(f"포트 연결 실패: {e}")
        return

    ser.reset_input_buffer()

    # --- 누적 통계 변수 ---
    total_received = 0
    sync_errors = 0
    lost_total = 0
    lost_open_loop = 0
    lost_closed_loop = 0
    recv_open_loop = 0
    recv_closed_loop = 0

    # --- PC 메모리 기반 이전 상태 복원 변수 ---
    last_seq = None
    last_t_curr = None
    last_bemf = None
    last_step = None
    step_sequence_errors = 0

    dt_history = []
    last_display_time = time.time()

    # --- 600샘플 롤링 버퍼 및 상태 변수 ---
    rolling_buffer = deque(maxlen=MAX_BUFFER_LEN)
    is_recording = False

    print("======================================================================")
    print(" [조작법]")
    print("  1. SPACE를 처음 누르면 : [기록 시작] (최근 600개 롤링 수집)")
    print("  2. SPACE를 다시 누르면 : [기록 정지] -> 직전 600개 즉시 CSV 저장")
    print("  3. 기록 중 모터가 멈추면: [타임아웃 감지] -> 멈춘 직전 600개 자동 CSV 저장")
    print("======================================================================")

    try:
        while True:
            # ------------------------------------------------------------------
            # 1. 키보드 스페이스바 입력 감지
            # ------------------------------------------------------------------
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b" ":
                    if not is_recording:
                        # [기록 시작]
                        is_recording = True
                        rolling_buffer.clear()
                        print("\n>>> [기록 활성화] 실시간 롤링 버퍼 수집 시작...")
                    else:
                        # [사용자가 수동으로 멈춤 -> 직전 600개 저장]
                        is_recording = False
                        save_to_csv(rolling_buffer, trigger_reason="MANUAL_STOP")
                        rolling_buffer.clear()

            # ------------------------------------------------------------------
            # 2. 바이트 수신 및 모터 정지(타임아웃) 판별
            # ------------------------------------------------------------------
            header = ser.read(1)
            if not header:
                # TIMEOUT(50ms) 동안 데이터 유입이 없음 -> 모터가 멈춘 상태
                if is_recording and len(rolling_buffer) > 0:
                    print("\n>>> [모터 정지 감지] 데이터 유입 중단 발생!")
                    save_to_csv(rolling_buffer, trigger_reason="MOTOR_STOP_TIMEOUT")
                    is_recording = False
                    rolling_buffer.clear()
                continue

            if header[0] != HEADER_BYTE:
                sync_errors += 1
                continue

            payload = ser.read(PACKET_SIZE - 1)
            if len(payload) < PACKET_SIZE - 1:
                sync_errors += 1
                continue

            full_packet = header + payload
            if full_packet[-1] != TAIL_BYTE:
                sync_errors += 1
                continue

            # ------------------------------------------------------------------
            # 3. 18 Byte 언패킹
            # ------------------------------------------------------------------
            (
                hdr,
                ccr_current,
                info,
                bemf_curr,
                t_start,
                t_curr,
                t_zc,
                delay_limited,
                delay_trigger,
                delay_par,
                tail,
            ) = parse_packet(full_packet)

            total_received += 1
            current_seq = delay_par

            # 제어 상태 비트필드 분해
            step = info & 0x0F
            is_closed_loop = (info >> 4) & 0x01
            zc_event = (info >> 5) & 0x01

            if is_closed_loop:
                recv_closed_loop += 1
            else:
                recv_open_loop += 1

            # ------------------------------------------------------------------
            # 4. 시퀀스 유실 및 주기 계산
            # ------------------------------------------------------------------
            lost_count = 0
            if last_seq is not None:
                diff = (current_seq - last_seq) & 0xFF
                if diff > 1:
                    lost_count = diff - 1
                    lost_total += lost_count
                    if is_closed_loop:
                        lost_closed_loop += lost_count
                    else:
                        lost_open_loop += lost_count
            last_seq = current_seq

            dt = ((t_curr - last_t_curr) & 0xFFFF) if last_t_curr is not None else 50
            dt_history.append(dt)
            if len(dt_history) > 100:
                dt_history.pop(0)

            # PC 메모리에서 이전 샘플값 복원
            bemf_prev = last_bemf if last_bemf is not None else bemf_curr
            t_prev = last_t_curr if last_t_curr is not None else t_curr

            if last_step is not None and step != last_step:
                expected_step = (last_step % 6) + 1
                if step != expected_step:
                    step_sequence_errors += 1

            last_step = step
            last_t_curr = t_curr
            last_bemf = bemf_curr

            # ------------------------------------------------------------------
            # 5. 롤링 버퍼 갱신 (기록 중일 때 최신 600개 유지)
            # ------------------------------------------------------------------
            if is_recording:
                rolling_buffer.append(
                    {
                        "seq": current_seq,
                        "step": step,
                        "mode": "CLOSED_LOOP" if is_closed_loop else "OPEN_LOOP",
                        "zc_event": zc_event,
                        "ccr": ccr_current,
                        "bemf_prev": bemf_prev,
                        "bemf_curr": bemf_curr,
                        "t_start": t_start,
                        "t_prev": t_prev,
                        "t_curr": t_curr,
                        "dt_us": dt,
                        "t_zc": t_zc,
                        "delay_limited": delay_limited,
                        "delay_trigger": delay_trigger,
                    }
                )

            # ------------------------------------------------------------------
            # 6. 실시간 대시보드 렌더링 (0.25초 주기)
            # ------------------------------------------------------------------
            now = time.time()
            if now - last_display_time >= 0.25:
                last_display_time = now
                avg_dt = (sum(dt_history) / len(dt_history)) if dt_history else 0.0

                ol_total = recv_open_loop + lost_open_loop
                cl_total = recv_closed_loop + lost_closed_loop
                all_total = total_received + lost_total

                loss_rate_all = (lost_total / all_total * 100.0) if all_total > 0 else 0.0
                loss_rate_ol = (lost_open_loop / ol_total * 100.0) if ol_total > 0 else 0.0
                loss_rate_cl = (lost_closed_loop / cl_total * 100.0) if cl_total > 0 else 0.0

                print("\033[H\033[J", end="")
                print("================== [BLDC 텔레메트리 스트림 검증 및 캡처] ==================")
                print(f"수신 통계     : 총 수신 {total_received} 개 | 동기화 에러: {sync_errors} 회 | 스텝 시퀀스 에러: {step_sequence_errors} 회")
                print(f"전체 유실률   : {loss_rate_all:5.2f} % ({lost_total} 개 누락)")
                print(f"구간별 유실률 : [OPEN-LOOP] {loss_rate_ol:5.2f} %  |  [CLOSED-LOOP] {loss_rate_cl:5.2f} %")
                print(f"50us 주기검증 : 최근 100샘플 평균 dt: {avg_dt:5.1f} us")
                print("--------------------------------------------------------------------------")
                loop_str = "CLOSED_LOOP" if is_closed_loop else "OPEN_LOOP"
                zc_str = "DETECTED!" if zc_event else "Searching"
                print(f"제어 상태     : Step [{step}] | 모드: [{loop_str}] | ZC: [{zc_str}] | CCR: {ccr_current}")
                print(f"BEMF 비교     : Prev={bemf_prev:5d} -> Curr={bemf_curr:5d} (Zero-Crossing 관측)")
                print(f"타임스탬프    : Start={t_start:5d} | Prev={t_prev:5d} | Curr={t_curr:5d} | ZC={t_zc:5d}")
                print(f"딜레이(us)    : Limited={delay_limited:5d} | Trigger={delay_trigger:5d}")
                print("--------------------------------------------------------------------------")
                if is_recording:
                    rec_status = f"● REC 수집 중 (최신 {len(rolling_buffer)} / {MAX_BUFFER_LEN} 개 유지)"
                else:
                    rec_status = "○ 대기 중 (SPACE를 누르면 롤링 버퍼 녹화 시작)"
                print(f"캡처 모드     : {rec_status}")
                print("==========================================================================")

    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()