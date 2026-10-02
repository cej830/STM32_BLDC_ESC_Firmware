import csv
import msvcrt  # Windows 키 입력 감지용
import os
import struct
import time
import serial

# ==============================================================================
# 1. 패킷 포맷 설정 (수정된 18바이트 구조체)
# ==============================================================================
# 구조체 바이트 배치:
#  B : uint8_t  header            (0xAA)
#  H : uint16_t ccr_current
#  B : uint8_t  info               (Step, OL/CL, ZC_event)
#  h : int16_t  BEMF_curr          (부호 있는 16비트 정수)
#  H : uint16_t timestamp_start
#  H : uint16_t timestamp_curr
#  H : uint16_t timestamp_zc
#  H : uint16_t delay_limited
#  H : uint16_t delay_trigger
#  B : uint8_t  delay_PAR          (8비트 시퀀스 카운터 0~255)
#  B : uint8_t  tail              (0xBB)
PACKET_FORMAT = "<B H B h 5H B B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 정확히 18 바이트

HEADER_BYTE = 0xAA
TAIL_BYTE = 0xBB

PORT = "COM4"
BAUDRATE = 115200  # USB CDC 가상 COM 포트에서는 보레이트 설정 무관하게 풀스피드로 동작
TIMEOUT = 0.05  # 모터 정지(스트림 중단) 감지를 위한 타임아웃 (50ms)

MAX_CAPTURE_SAMPLES = 600  # 스페이스바 트리거 시 캡처할 최대 샘플 수


def parse_packet(raw_bytes):
    return struct.unpack(PACKET_FORMAT, raw_bytes)


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

    # 전체 / 오픈루프 / 클로즈루프 유실률 분리 추적
    lost_total = 0
    lost_open_loop = 0
    lost_closed_loop = 0

    recv_open_loop = 0
    recv_closed_loop = 0

    # --- 이전 상태 복원용 변수 (PC 메모리에서 유지) ---
    last_seq = None
    last_t_curr = None
    last_bemf = None
    last_step = None
    step_sequence_errors = 0

    dt_history = []
    last_display_time = time.time()

    # --- 캡처 관련 변수 ---
    is_capturing = False
    capture_buffer = []

    print("======================================================================")
    print(" [안내] 실시간 유실 모니터링 중 | [SPACEBAR] 누르면 최대 600샘플 캡처")
    print("======================================================================")

    try:
        while True:
            # ------------------------------------------------------------------
            # A. 스페이스바 키 입력 감지 (Windows 논블로킹)
            # ------------------------------------------------------------------
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b" ":
                    if not is_capturing:
                        is_capturing = True
                        capture_buffer.clear()
                        print("\n>>> [캡처 시작] 최대 600개 샘플 수집 중...")

            # ------------------------------------------------------------------
            # B. 패킷 헤더 동기화 및 바이트 수신
            # ------------------------------------------------------------------
            header = ser.read(1)
            if not header:
                # 데이터가 안 들어옴 -> 모터가 멈췄거나 통신 차단됨
                if is_capturing and len(capture_buffer) > 0:
                    print(
                        f"\n>>> [모터 정지 감지] 데이터 유입 중단으로 조기 캡처 완료 ({len(capture_buffer)}개)"
                    )
                    save_to_csv(capture_buffer)
                    is_capturing = False
                    capture_buffer.clear()
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
            # C. 패킷 파싱 (18 Byte 언패킹)
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
                delay_par,  # 8비트 시퀀스 번호 (0~255)
                tail,
            ) = parse_packet(full_packet)

            total_received += 1
            current_seq = delay_par

            # 비트필드 분해: Step(bit 0~3), Mode(bit 4), ZC_Event(bit 5)
            step = info & 0x0F
            is_closed_loop = (info >> 4) & 0x01
            zc_event = (info >> 5) & 0x01

            if is_closed_loop:
                recv_closed_loop += 1
            else:
                recv_open_loop += 1

            # ------------------------------------------------------------------
            # D. PC 내부 연산 1: 8비트 시퀀스 기반 유실 검증 (모드별 분리 집계)
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

            # ------------------------------------------------------------------
            # E. PC 내부 연산 2: 샘플 간 dt 및 이전 BEMF(Prev) 복원
            # ------------------------------------------------------------------
            dt = (
                (t_curr - last_t_curr) & 0xFFFF
                if last_t_curr is not None
                else 50
            )
            dt_history.append(dt)
            if len(dt_history) > 100:
                dt_history.pop(0)

            # 이전 샘플의 BEMF 값 (제거했던 BEMF_prev 대체)
            bemf_prev = last_bemf if last_bemf is not None else bemf_curr
            t_prev = last_t_curr if last_t_curr is not None else t_curr

            # 스텝 시퀀스 에러 검증 (1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 1)
            if last_step is not None and step != last_step:
                expected_step = (last_step % 6) + 1
                if step != expected_step:
                    step_sequence_errors += 1

            last_step = step
            last_t_curr = t_curr
            last_bemf = bemf_curr

            # ------------------------------------------------------------------
            # F. CSV 캡처 버퍼링 (트리거 동작 시)
            # ------------------------------------------------------------------
            if is_capturing:
                capture_buffer.append(
                    {
                        "seq": current_seq,
                        "step": step,
                        "mode": "CLOSED_LOOP" if is_closed_loop else "OPEN_LOOP",
                        "zc_event": zc_event,
                        "ccr": ccr_current,
                        "bemf_prev": bemf_prev,  # PC에서 복원한 값
                        "bemf_curr": bemf_curr,
                        "t_start": t_start,
                        "t_prev": t_prev,  # PC에서 복원한 값
                        "t_curr": t_curr,
                        "dt_us": dt,
                        "t_zc": t_zc,
                        "delay_limited": delay_limited,
                        "delay_trigger": delay_trigger,
                    }
                )

                if len(capture_buffer) >= MAX_CAPTURE_SAMPLES:
                    print(
                        f"\n>>> [캡처 완료] 최대치 {MAX_CAPTURE_SAMPLES}개 수집 완료. CSV로 저장합니다."
                    )
                    save_to_csv(capture_buffer)
                    is_capturing = False
                    capture_buffer.clear()

            # ------------------------------------------------------------------
            # G. 실시간 모니터링 대시보드 (0.25초 주기)
            # ------------------------------------------------------------------
            now = time.time()
            if now - last_display_time >= 0.25:
                last_display_time = now
                avg_dt = (
                    (sum(dt_history) / len(dt_history)) if dt_history else 0.0
                )

                # 모드별 유실률 계산
                ol_total = recv_open_loop + lost_open_loop
                cl_total = recv_closed_loop + lost_closed_loop
                all_total = total_received + lost_total

                loss_rate_all = (
                    (lost_total / all_total * 100.0) if all_total > 0 else 0.0
                )
                loss_rate_ol = (
                    (lost_open_loop / ol_total * 100.0)
                    if ol_total > 0
                    else 0.0
                )
                loss_rate_cl = (
                    (lost_closed_loop / cl_total * 100.0)
                    if cl_total > 0
                    else 0.0
                )

                print("\033[H\033[J", end="")
                print(
                    "================== [BLDC 텔레메트리 스트림 검증 및 캡처] =================="
                )
                print(
                    f"수신 통계     : 총 수신 {total_received} 개 | 동기화 에러: {sync_errors} 회 | 스텝 시퀀스 에러: {step_sequence_errors} 회"
                )
                print(
                    f"전체 유실률   : {loss_rate_all:5.2f} % ({lost_total} 개 누락)"
                )
                print(
                    f"구간별 유실률 : [OPEN-LOOP] {loss_rate_ol:5.2f} %  |  [CLOSED-LOOP] {loss_rate_cl:5.2f} %"
                )
                print(f"50us 주기검증 : 최근 100샘플 평균 dt: {avg_dt:5.1f} us")
                print(
                    "--------------------------------------------------------------------------"
                )
                loop_str = "CLOSED_LOOP" if is_closed_loop else "OPEN_LOOP"
                zc_str = "DETECTED!" if zc_event else "Searching"
                print(
                    f"제어 상태     : Step [{step}] | 모드: [{loop_str}] | ZC: [{zc_str}] | CCR: {ccr_current}"
                )
                print(
                    f"BEMF 비교     : Prev={bemf_prev:5d} -> Curr={bemf_curr:5d} (Zero-Crossing 관측)"
                )
                print(
                    f"타임스탬프    : Start={t_start:5d} | Prev={t_prev:5d} | Curr={t_curr:5d} | ZC={t_zc:5d}"
                )
                print(
                    f"딜레이(us)    : Limited={delay_limited:5d} | Trigger={delay_trigger:5d}"
                )
                print(
                    "--------------------------------------------------------------------------"
                )
                cap_status = (
                    f"수집 중 ({len(capture_buffer)}/{MAX_CAPTURE_SAMPLES})"
                    if is_capturing
                    else "대기 중 (SPACEBAR를 누르면 캡처)"
                )
                print(f"캡처 상태     : [{cap_status}]")
                print(
                    "=========================================================================="
                )

    except KeyboardInterrupt:
        print("\n수신을 중단합니다.")
    finally:
        ser.close()


def save_to_csv(data_list):
    if not data_list:
        return

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    filename = f"bldc_telemetry_{timestamp_str}.csv"

    fieldnames = list(data_list[0].keys())

    try:
        with open(
            filename, mode="w", newline="", encoding="utf-8-sig"
        ) as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data_list)
        print(
            f"\n[저장 완료] 파일명: {filename} (총 {len(data_list)}개 행 저장됨)"
        )
    except Exception as e:
        print(f"\n[저장 실패] {e}")


if __name__ == "__main__":
    main()