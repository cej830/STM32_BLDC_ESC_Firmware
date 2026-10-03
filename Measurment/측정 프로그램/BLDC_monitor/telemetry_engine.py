import os
import csv
import time
import threading
from collections import deque
import serial

import config
from packet_def import (
    PACKET_SIZE, HEADER_BYTE, TAIL_BYTE,
    TRIGGER_TIM_RACE, TRIGGER_TIMEOUT_FORCE, ZC_DETECTED,
    unpack_raw_packet
)
from zc_analyzer import ZCStabilityAnalyzer, diff_u16

class TelemetryEngine:
    def __init__(self):
        self.ser = None
        self.is_running = False
        self.thread = None
        
        self.analyzer = ZCStabilityAnalyzer()
        
        # 1. [기존 유지] 50us Raw 600개 버퍼 (스페이스바로 수동/타임아웃 캡처)
        self.raw_buffer = deque(maxlen=config.ROLLING_BUFFER_LEN)
        self.is_recording = False
        self.on_saved_callback = None

        # 2. [신규] 상시 백그라운드 100시퀀스(600행) 롤링 버퍼
        self.sequence_summary_buffer = deque(maxlen=config.SEQUENCE_BUFFER_LEN)
        self._current_cycle_steps = {}  # 1회전 동안 스텝 1~6의 ZC 데이터를 모으는 임시 공간
        self.sequence_counter = 0       # 1회전 누적 카운터

        self.stats = {
            "total_recv": 0,
            "sync_err": 0,
            "lost_total": 0,
            "lost_ol": 0,
            "lost_cl": 0,
            "recv_ol": 0,
            "recv_cl": 0,
            "avg_dt": 50.0,
            "race_9998": 0,
            "timeout_9999": 0,
            "step_seq_err": 0,
            "curr_step": 0,
            "curr_mode": "IDLE",
            "curr_zc_str": "Searching",
            "curr_trigger": 0,
            "curr_ccr": 0,
            "raw_e_rpm": 0.0,
            "filtered_e_rpm": 0.0
        }

        self._last_seq = None
        self._last_t_curr = None
        self._last_bemf = None
        self._last_step = None
        self._dt_history = deque(maxlen=100)

    def connect(self, port):
        try:
            self.ser = serial.Serial(port, config.DEFAULT_BAUDRATE, timeout=config.COMM_TIMEOUT)
            self.ser.reset_input_buffer()
            self.is_running = True
            self.thread = threading.Thread(target=self._rx_worker, daemon=True)
            self.thread.start()
            return True, "연결 성공"
        except Exception as e:
            return False, str(e)

    def disconnect(self):
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()

    # ---------------------------------------------------------
    # 1. 기존 Raw 600개 캡처 제어
    # ---------------------------------------------------------
    def set_recording(self, state):
        self.is_recording = state
        if state:
            self.raw_buffer.clear()

    def export_raw_csv(self, reason):
        if not self.raw_buffer:
            return None
        save_dir = "captures"
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"bldc_raw600_{reason}_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        data_list = list(self.raw_buffer)
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(data_list[0].keys()))
            writer.writeheader()
            writer.writerows(data_list)
        if self.on_saved_callback:
            self.on_saved_callback(filename, len(data_list), f"RAW 600개 [{reason}]")
        return filename

    # ---------------------------------------------------------
    # 2. [신규] 상시 누적된 시퀀스 100회전(600행) 즉시 저장
    # ---------------------------------------------------------
    def export_sequence_csv(self):
        if not self.sequence_summary_buffer:
            return None
        save_dir = "captures"
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"bldc_seq100_summary_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        data_list = list(self.sequence_summary_buffer)
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(data_list[0].keys()))
            writer.writeheader()
            writer.writerows(data_list)
        if self.on_saved_callback:
            self.on_saved_callback(filename, len(data_list), "시퀀스 100회전 요약")
        return filename

    def _rx_worker(self):
        while self.is_running:
            header = self.ser.read(1)
            if not header:
                # 타임아웃 감지 시 기존 Raw 버퍼 자동 저장
                if self.is_recording and len(self.raw_buffer) > 0:
                    self.export_raw_csv(reason="MOTOR_STOP_TIMEOUT")
                    self.is_recording = False
                continue

            if header[0] != HEADER_BYTE:
                self.stats["sync_err"] += 1
                continue

            payload = self.ser.read(PACKET_SIZE - 1)
            if len(payload) < PACKET_SIZE - 1 or payload[-1] != TAIL_BYTE:
                self.stats["sync_err"] += 1
                continue

            pkt = unpack_raw_packet(header + payload)
            self._handle_sample(pkt)

    def _handle_sample(self, pkt):
        self.stats["total_recv"] += 1
        seq = pkt["seq"]
        step = pkt["step"]
        is_cl = pkt["is_closed_loop"]
        trigger = pkt["delay_trigger"]

        if is_cl:
            self.stats["recv_cl"] += 1
        else:
            self.stats["recv_ol"] += 1

        if trigger == TRIGGER_TIMEOUT_FORCE:
            self.stats["timeout_9999"] += 1
        elif trigger == TRIGGER_TIM_RACE:
            self.stats["race_9998"] += 1

        # 유실 검사
        if self._last_seq is not None:
            diff = (seq - self._last_seq) & 0xFF
            if diff > 1:
                lost = diff - 1
                self.stats["lost_total"] += lost
                if is_cl:
                    self.stats["lost_cl"] += lost
                else:
                    self.stats["lost_ol"] += lost
        self._last_seq = seq

        # dt 주기
        dt = diff_u16(pkt["t_curr"], self._last_t_curr) if self._last_t_curr else 50
        self._dt_history.append(dt)
        self.stats["avg_dt"] = sum(self._dt_history) / len(self._dt_history)

        # 스텝 전환 감지
        if self._last_step is not None and step != self._last_step:
            self.analyzer.on_step_transition(step, pkt["t_start"])
            if step != ((self._last_step % 6) + 1):
                self.stats["step_seq_err"] += 1
        elif self._last_step is None:
            self.analyzer.on_step_transition(step, pkt["t_start"])

        # -------------------------------------------------------------
        # [핵심] ZC Event 발생 순간의 스냅샷을 1회전(시퀀스) 버퍼에 수집
        # -------------------------------------------------------------
        zc_eval = None
        if pkt["zc_event"] == ZC_DETECTED and trigger != TRIGGER_TIM_RACE and (1 <= step <= 6):
            zc_eval = self.analyzer.evaluate(step, pkt["t_start"], pkt["t_zc"])
            
            # 클로즈 루프일 때만 회전 데이터 정규화 수집
            if is_cl:
                node = self.analyzer.nodes[step]
                snap = {
                    "seq_cycle": self.sequence_counter,
                    "step": step,
                    "ccr": pkt["ccr"],
                    "e_rpm": int(self.analyzer.e_rpm),          # 1사이클(360도 ZC-to-ZC) 기반 전기적 RPM
                    "m_rpm": int(self.analyzer.m_rpm),          # 7극쌍 반영 실제 모터 기계적 RPM
                    "cycle_zc_us": self.analyzer.cycle_zc_period_us, # 전기각 1회전(360도) 순수 ZC 간격
                    "step_period_us": node.step_period,
                    "offset_avg_us": node.period_offset_us,
                    "zc_duration_us": node.curr_duration if node.curr_duration else 0,
                    "zc_pos_pct": round(node.zc_pos_pct, 1),
                    "diff_us": node.diff_us,
                    "status": node.status,
                    "risk_streak": node.risk_streak,
                    "max_risk": node.max_risk_streak,
                    "reject_total": node.reject_count
                }
                self._current_cycle_steps[step] = snap

                # 스텝 6개가 모두 채워졌거나, 스텝 6 완료 후 1이 들어와 1사이클이 끝난 경우
                if len(self._current_cycle_steps) == 6 or (step == 6 and 1 in self._current_cycle_steps):
                    for s_num in sorted(self._current_cycle_steps.keys()):
                        self.sequence_summary_buffer.append(self._current_cycle_steps[s_num])
                    
                    self._current_cycle_steps.clear()
                    self.sequence_counter += 1

        # 50us 원시 패킷 버퍼 (스페이스바 캡처용 기존 기능 100% 유지)
        if self.is_recording:
            record = {
                **pkt,
                "dt_us": dt,
                "bemf_prev": self._last_bemf if self._last_bemf else pkt["bemf_curr"],
                "zc_eval": zc_eval["status"] if zc_eval else "N/A",
                "zc_diff_us": zc_eval["diff_us"] if zc_eval else 0,
                "risk_streak": zc_eval["risk_streak"] if zc_eval else 0
            }
            self.raw_buffer.append(record)

        # 통계 최신화
        self.stats["curr_step"] = step
        self.stats["curr_mode"] = "CLOSED_LOOP" if is_cl else "OPEN_LOOP"
        self.stats["curr_trigger"] = trigger
        zc_map = {0: "Searching", 1: "DETECTED", 2: "TIMEOUT"}
        self.stats["curr_zc_str"] = zc_map.get(pkt["zc_event"], "Searching")

        self.stats["curr_ccr"] = pkt["ccr"]
        self.stats["e_rpm"] = int(self.analyzer.e_rpm)
        self.stats["m_rpm"] = int(self.analyzer.m_rpm)
        self.stats["cycle_zc_us"] = self.analyzer.cycle_zc_period_us

        self._last_step = step
        self._last_t_curr = pkt["t_curr"]
        self._last_bemf = pkt["bemf_curr"]