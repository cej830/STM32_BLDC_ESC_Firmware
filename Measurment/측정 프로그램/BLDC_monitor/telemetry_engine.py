import os
import csv
import time
import threading
from collections import deque
import serial

import config
from packet_def import (
    PACKET_SIZE, HEADER_BYTE, TAIL_BYTE,
    TRIGGER_TIM_RACE, TRIGGER_TIMEOUT_FORCE,
    TRIGGER_RISK_FORCE, TRIGGER_REJECT_FORCE,
    ZC_EVENT_MAP, MOTOR_STATE_MAP,
    unpack_raw_packet
)
from zc_analyzer import ZCStabilityAnalyzer, diff_u16

class TelemetryEngine:
    def __init__(self):
        self.ser = None
        self.is_running = False
        self.thread = None
        
        self.analyzer = ZCStabilityAnalyzer()
        
        # 1. 50us Raw 버퍼
        self.raw_buffer = deque(maxlen=config.ROLLING_BUFFER_LEN)
        self.is_recording = False
        self.on_saved_callback = None

        # 2. 상시 백그라운드 100시퀀스(600행) 롤링 버퍼
        self.sequence_summary_buffer = deque(maxlen=config.SEQUENCE_BUFFER_LEN)
        self._current_cycle_steps = {}
        self.sequence_counter = 0

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
            "risk_force_9997": 0,
            "reject_force_9996": 0,
            "already_count": 0,
            "step_seq_err": 0,
            "curr_step": 0,
            "curr_mode": "IDLE",
            "curr_zc_str": "NOT_YET",
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

    def reset_already_count(self):
        self.stats["already_count"] = 0

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

    # main.py 호환용 별칭
    export_csv = export_raw_csv

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
        motor_state = pkt["motor_state_raw"]
        zc_event = pkt["zc_event"]
        trigger = pkt["delay_trigger"]

        if zc_event == 2:
            self.stats["already_count"] += 1

        # CLOSE_LOOP(1) 또는 CLOSE_LOCKIN(2)를 클로즈드 루프로 처리
        is_cl = (motor_state in (1, 2))

        if is_cl:
            self.stats["recv_cl"] += 1
        else:
            self.stats["recv_ol"] += 1

        # 특수 인터럽트/트리거 플래그 집계
        if trigger == TRIGGER_TIMEOUT_FORCE:
            self.stats["timeout_9999"] += 1
        elif trigger == TRIGGER_TIM_RACE:
            self.stats["race_9998"] += 1
        elif trigger == TRIGGER_RISK_FORCE:
            self.stats["risk_force_9997"] += 1
        elif trigger == TRIGGER_REJECT_FORCE:
            self.stats["reject_force_9996"] += 1

        # 패킷 유실 검사
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

        # dt 계산
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

        # ZC 이벤트 평가: DETECTED(1) 발생 시 판정 로직 수행
        zc_eval = None
        if zc_event == 1 and trigger != TRIGGER_TIM_RACE and (1 <= step <= 6):
            zc_eval = self.analyzer.evaluate(step, pkt["t_start"], pkt["t_zc"])
            
            if is_cl:
                node = self.analyzer.nodes[step]
                snap = {
                    "seq_cycle": self.sequence_counter,
                    "step": step,
                    "ccr": pkt["ccr"],
                    "motor_state": pkt["motor_state_str"],
                    "zc_event": pkt["zc_event_str"],
                    "e_rpm": int(self.analyzer.e_rpm),
                    "m_rpm": int(self.analyzer.m_rpm),
                    "cycle_zc_us": self.analyzer.cycle_zc_period_us,
                    "step_period_us": node.step_period,
                    "offset_avg_us": node.period_offset_us,
                    "zc_duration_us": node.curr_duration if node.curr_duration else 0,
                    "zc_pos_pct": round(node.zc_pos_pct, 1),
                    "diff_us": node.diff_us,
                    "status": node.status,
                    "global_risk_streak": self.analyzer.global_risk_streak,
                    "global_max_risk": self.analyzer.global_max_risk_streak,
                    "global_reject_total": self.analyzer.global_reject_count
                }
                self._current_cycle_steps[step] = snap

                if len(self._current_cycle_steps) == 6 or (step == 6 and 1 in self._current_cycle_steps):
                    for s_num in sorted(self._current_cycle_steps.keys()):
                        self.sequence_summary_buffer.append(self._current_cycle_steps[s_num])
                    self._current_cycle_steps.clear()
                    self.sequence_counter += 1

        # 50us 원시 패킷 버퍼 (RAW 로그)
        if self.is_recording:
            record = {
                **pkt,
                "dt_us": dt,
                "bemf_prev": self._last_bemf if self._last_bemf else pkt["bemf_curr"],
                "zc_eval": zc_eval["status"] if zc_eval else "N/A",
                "zc_diff_us": zc_eval["diff_us"] if zc_eval else 0,
                "global_risk_streak": self.analyzer.global_risk_streak
            }
            self.raw_buffer.append(record)

        # UI 통계 갱신 데이터
        self.stats["curr_step"] = step
        self.stats["curr_mode"] = pkt["motor_state_str"]
        self.stats["curr_zc_str"] = pkt["zc_event_str"]
        self.stats["curr_trigger"] = trigger
        self.stats["curr_ccr"] = pkt["ccr"]
        self.stats["e_rpm"] = int(self.analyzer.e_rpm)
        self.stats["m_rpm"] = int(self.analyzer.m_rpm)
        self.stats["cycle_zc_us"] = self.analyzer.cycle_zc_period_us

        self._last_step = step
        self._last_t_curr = pkt["t_curr"]
        self._last_bemf = pkt["bemf_curr"]