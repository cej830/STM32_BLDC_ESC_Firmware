import csv
from collections import deque
import msvcrt
import struct
import time
import serial

# ==============================================================================
# 1. 패킷 및 통신 설정 (18 Byte 고정)
# ==============================================================================
PACKET_FORMAT = "<B H B h 5H B B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 18 Byte

HEADER_BYTE = 0xAA
TAIL_BYTE = 0xBB

PORT = "COM4"
BAUDRATE = 115200
TIMEOUT = 0.05
MAX_BUFFER_LEN = 600

# ==============================================================================
# 2. zc_duration 판정 임계치 설정 (사용자 지정 영역)
# ==============================================================================
# 절대 편차 기준 (us 단위) - 0이면 퍼센트(%) 기준만 사용
LIMIT_US_VALID = 40  # 직전 회전 동일 스텝 대비 편차가 40us 이하이면 VALID
LIMIT_US_RISK = 90  # 직전 회전 동일 스텝 대비 편차가 90us 이하이면 RISK (초과는 REJECT)

# 상대 변동률 기준 (% 단위)
THRESHOLD_PCT_VALID = 8.0  # 8% 이하 변동 -> VALID
THRESHOLD_PCT_RISK = 18.0  # 18% 이하 변동 -> RISK (초과는 REJECT)


def parse_packet(raw_bytes):
    return struct.unpack(PACKET_FORMAT, raw_bytes)


def evaluate_zc_duration(diff_us, diff_pct):
    """지정한 us 및 % 임계치를 기반으로 VALID / RISK / REJECT 판정"""
    # 1. 절대 편차(us) 또는 비율(%) 중 엄격한 기준 적용
    if diff_us <= LIMIT_US_VALID and diff_pct <= THRESHOLD_PCT_VALID:
        return "VALID"
    elif diff_us <= LIMIT_US_RISK and diff_pct <= THRESHOLD_PCT_RISK:
        return "RISK"
    else:
        return "REJECT"


def save_to_csv(data_deque, trigger_reason="USER_TRIGGER"):
    if not data_deque:
        return
    data_list = list(data_deque)
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    filename = f"bldc_telemetry_{trigger_reason}_{timestamp_str}.csv"
    fieldnames = list(data_list[0].keys())

    try:
        with open(
            filename, mode="w", newline="", encoding="utf-8-sig"
        ) as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data_list)
        print(f"\n[CSV 저장 완료] {filename} ({len(data_list)}개 샘플)")
    except Exception as e:
        print(f"\n[저장 실패] {e}")


def main():
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
        print(f"[{PORT}] 연결 완료 (패킷: {PACKET_SIZE}B)")
    except Exception as e:
        print(f"포트 연결 실패: {e}")
        return

    ser.reset_input_buffer()

    total_received = 0
    sync_errors = 0
    lost_total = 0
    lost_open_loop = 0
    lost_closed_loop = 0
    recv_open_loop = 0
    recv_closed_loop = 0

    last_seq = None
    last_t_curr = None
    last_bemf = None
    last_step = None
    step_sequence_errors = 0

    # 스텝 1~6별 zc_duration (t_zc - t_start) 추적기
    # prev_duration: 직전 회전 동일 스텝 zc_duration
    # curr_duration: 현재 회전 동일 스텝 zc_duration
    step_zc_tracker = {
        s: {
            "prev_duration": None,
            "curr_duration": None,
            "diff_us": 0,
            "diff_pct": 0.0,
            "status": "INIT",
        }
        for s in range(1, 7)
    }

    cnt_timeout_9999 = 0
    cnt_race_9998 = 0

    dt_history = []
    last_display_time = time.time()

    rolling_buffer = deque(maxlen=MAX_BUFFER_LEN)
    is_recording = False

    try:
        while True:
            # 1. 키보드 스페이스바 입력 감지
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b" ":
                    if not is_recording:
                        is_recording = True
                        rolling_buffer.clear()
                        print("\n>>> [기록 활성화] 롤링 버퍼 수집 시작")
                    else:
                        is_recording = False
                        save_to_csv(
                            rolling_buffer, trigger_reason="MANUAL_STOP"
                        )
                        rolling_buffer.clear()

            # 2. 바이트 수신 및 모터 타임아웃 정지 감지
            header = ser.read(1)
            if not header:
                if is_recording and len(rolling_buffer) > 0:
                    print("\n>>> [모터 정지 감지] 데이터 유입 중단!")
                    save_to_csv(
                        rolling_buffer, trigger_reason="MOTOR_STOP_TIMEOUT"
                    )
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

            # 3. 언패킹
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

            step = info & 0x0F
            is_closed_loop = (info >> 4) & 0x01
            zc_event = (info >> 5) & 0x03  # 0:탐색, 1:정상검출, 2:타임아웃

            if is_closed_loop:
                recv_closed_loop += 1
            else:
                recv_open_loop += 1

            # 특수 플래그 카운트
            if delay_trigger == 9999:
                cnt_timeout_9999 += 1
            elif delay_trigger == 9998:
                cnt_race_9998 += 1

            # 4. 시퀀스 유실 계산
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

            dt = (
                ((t_curr - last_t_curr) & 0xFFFF)
                if last_t_curr is not None
                else 50
            )
            dt_history.append(dt)
            if len(dt_history) > 100:
                dt_history.pop(0)

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
            # 5. 핵심: zc_duration (t_zc - t_start) 스텝별 추적 및 판정
            # ------------------------------------------------------------------
            current_zc_duration = 0
            eval_status = "N/A"
            diff_us = 0
            diff_pct = 0.0

            # 정상 ZC 검출(1)이고 침투 예외(9998)가 아닐 때만 갱신
            if zc_event == 1 and delay_trigger != 9998 and 1 <= step <= 6:
                # 스텝 시작(t_start)부터 보간 ZC(t_zc)까지 걸린 시간 계산 (16비트 보정)
                current_zc_duration = (t_zc - t_start) & 0xFFFF

                node = step_zc_tracker[step]
                if node["curr_duration"] is not None:
                    # 이전 회전의 값을 prev로 밀어냄
                    node["prev_duration"] = node["curr_duration"]
                    node["curr_duration"] = current_zc_duration

                    # 과거 vs 현재 편차 계산
                    diff_us = abs(
                        node["curr_duration"] - node["prev_duration"]
                    )
                    diff_pct = (
                        (diff_us / node["prev_duration"]) * 100.0
                        if node["prev_duration"] > 0
                        else 0.0
                    )

                    # 설정된 임계치 기준 Valid / Risk / Reject 평가
                    eval_status = evaluate_zc_duration(diff_us, diff_pct)

                    node["diff_us"] = diff_us
                    node["diff_pct"] = diff_pct
                    node["status"] = eval_status
                else:
                    # 첫 측정 시 초기화
                    node["curr_duration"] = current_zc_duration
                    node["status"] = "SYNCING"

            # 6. 롤링 버퍼 저장 (CSV 레코드)
            if is_recording:
                rolling_buffer.append(
                    {
                        "seq": current_seq,
                        "step": step,
                        "mode": (
                            "CLOSED_LOOP" if is_closed_loop else "OPEN_LOOP"
                        ),
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
                        "step_zc_duration": current_zc_duration,
                        "eval_status": eval_status,
                        "diff_us": diff_us,
                        "diff_pct": round(diff_pct, 2),
                    }
                )

            # ------------------------------------------------------------------
            # 7. 대시보드 렌더링 (0.25초 주기)
            # ------------------------------------------------------------------
            now = time.time()
            if now - last_display_time >= 0.25:
                last_display_time = now
                avg_dt = (
                    (sum(dt_history) / len(dt_history)) if dt_history else 0.0
                )

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
                    "================== [BLDC 텔레메트리 & zc_duration 실시간 정밀 분석] =================="
                )
                print(
                    f"수신 통계     : 총 {total_received} 개 | 전체 유실률: {loss_rate_all:5.2f}% (OL:{loss_rate_ol:4.1f}% / CL:{loss_rate_cl:4.1f}%)"
                )
                print(
                    f"특수 이벤트   : TIM침투(9998): {cnt_race_9998:4d} 회 | 최종타임아웃(9999): {cnt_timeout_9999:4d} 회"
                )
                print(
                    f"주기 검증     : 최근 평균 dt: {avg_dt:5.1f} us | 스텝 시퀀스 에러: {step_sequence_errors} 회"
                )
                print(
                    f"판정 임계 기준: [VALID] <= {LIMIT_US_VALID}us / {THRESHOLD_PCT_VALID}% | [RISK] <= {LIMIT_US_RISK}us / {THRESHOLD_PCT_RISK}% | [REJECT] 초과"
                )
                print(
                    "------------------------------------------------------------------------------------"
                )
                loop_str = "CLOSED_LOOP" if is_closed_loop else "OPEN_LOOP"
                zc_str = (
                    "DETECTED"
                    if zc_event == 1
                    else ("TIMEOUT" if zc_event == 2 else "Searching")
                )
                print(
                    f"현재 상태     : Step [{step}] | [{loop_str}] | ZC: [{zc_str}] | Trigger: {delay_trigger}"
                )
                print(
                    "--------------- [스텝별 zc_duration (t_zc - t_start) 과거 vs 현재 비교] ---------------"
                )

                for s in range(1, 7):
                    n = step_zc_tracker[s]
                    prev_str = (
                        f"{n['prev_duration']:4d}us"
                        if n["prev_duration"] is not None
                        else " ---us"
                    )
                    curr_str = (
                        f"{n['curr_duration']:4d}us"
                        if n["curr_duration"] is not None
                        else " ---us"
                    )
                    diff_str = (
                        f"{n['diff_us']:3d}us ({n['diff_pct']:4.1f}%)"
                        if n["prev_duration"] is not None
                        else "  --- us ( ---%)"
                    )

                    # 상태별 표시 색상 대체 (텍스트 태그)
                    stat_tag = f"[{n['status']:^8}]"
                    print(
                        f" Step {s} : 과거={prev_str} -> 현재={curr_str} | 편차={diff_str} | 판정: {stat_tag}"
                    )

                print(
                    "------------------------------------------------------------------------------------"
                )
                rec_status = (
                    f"● REC 수집 중 (최근 {len(rolling_buffer)} / {MAX_BUFFER_LEN} 개 유지)"
                    if is_recording
                    else "○ 대기 중 (SPACE 누르면 롤링 버퍼 캡처)"
                )
                print(f"캡처 모드     : {rec_status}")
                print(
                    "===================================================================================="
                )

    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()