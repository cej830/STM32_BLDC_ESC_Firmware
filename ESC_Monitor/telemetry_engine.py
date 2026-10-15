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


        self.zc_quality_stats = {
            "total_eval": 0,
            "detected_cnt": 0,
            "already_cnt": 0,
            "pass_cnt": 0,
            "pct_detected": 0.0,
            "pct_already": 0.0,
            "pct_pass": 0.0
        }

        # CCR 구간별(200단위 윈도우) 통계: {ccr_bucket: [total, detected, already, pass]}
        self.ccr_quality_buckets = {}

        self._last_seq = None
        self._last_t_curr = None
        self._last_bemf = None
        self._last_step = None
        self._dt_history = deque(maxlen=100)

    def reset_already_count(self):
        self.stats["already_count"] = 0

    def reset_zc_quality_stats(self):
        """이벤트 품질 통계 초기화"""
        self.zc_quality_stats = {
            "total_eval": 0,
            "detected_cnt": 0,
            "already_cnt": 0,
            "pass_cnt": 0,
            "pct_detected": 0.0,
            "pct_already": 0.0,
            "pct_pass": 0.0
        }
        self.ccr_quality_buckets.clear()

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

    # telemetry_engine.py _handle_sample() 내부 발췌

    def _handle_sample(self, pkt):
        self.stats["total_recv"] += 1
        step = pkt["step"]
        motor_state = pkt["motor_state_raw"]
        zc_event = pkt["zc_event"]
        trigger = pkt["delay_trigger"]
        ccr = pkt["ccr"]

        is_cl = (motor_state in (1, 2))
        if is_cl:
            self.stats["recv_cl"] += 1
        else:
            self.stats["recv_ol"] += 1

        if zc_event == 2:
            self.stats["already_count"] += 1

        # 품질 통계
        if zc_event in (1, 2, 3):
            q = self.zc_quality_stats
            q["total_eval"] += 1
            if zc_event == 1:
                q["detected_cnt"] += 1
            elif zc_event == 2:
                q["already_cnt"] += 1
            elif zc_event == 3:
                q["pass_cnt"] += 1

            if q["total_eval"] > 0:
                q["pct_detected"] = (q["detected_cnt"] / q["total_eval"]) * 100.0
                q["pct_already"] = (q["already_cnt"] / q["total_eval"]) * 100.0
                q["pct_pass"] = (q["pass_cnt"] / q["total_eval"]) * 100.0

        # 스텝 전환
        if self._last_step is not None and step != self._last_step:
            self.analyzer.on_step_transition(step, pkt["t_start"])
            if step != ((self._last_step % 6) + 1):
                self.stats["step_seq_err"] += 1
        elif self._last_step is None:
            self.analyzer.on_step_transition(step, pkt["t_start"])

        # ZC 평가 (DETECTED = 1)
        zc_eval = None
        if zc_event == 1 and trigger != TRIGGER_TIM_RACE and (1 <= step <= 6):
            zc_eval = self.analyzer.evaluate(
                step, 
                pkt["t_start"], 
                pkt["t_zc"], 
                pkt["ts_tim"], 
                pkt["cnt_ic"]
            )
            
            node = self.analyzer.nodes[step]
            # 100회전 시퀀스 로그에 비교기 및 오차 데이터 기록
            snap = {
                "seq_cycle": self.sequence_counter,
                "step": step,
                "ccr": pkt["ccr"],
                "motor_state": pkt["motor_state_str"],
                "e_rpm": int(self.analyzer.e_rpm),
                "m_rpm": int(self.analyzer.m_rpm),
                "step_period_us": node.step_period,
                "ts_zc_adc": pkt["t_zc"],
                "ts_tim_comp": pkt["ts_tim"],
                "err_adc_vs_comp_us": node.err_adc_vs_comp_us,
                "cnt_ic": pkt["cnt_ic"],
                "zc_duration_us": node.curr_duration if node.curr_duration else 0,
                "zc_pos_pct": round(node.zc_pos_pct, 1),
                "diff_us": node.diff_us,
                "status": node.status
            }
            # Step 1을 새로운 전기각 1사이클의 시작점으로 사용
            if step == 1:
                # 이전 사이클이 완성되지 않은 채 남아있으면 폐기
                self._current_cycle_steps.clear()

            # 현재 step 저장
            self._current_cycle_steps[step] = snap

            # Step 6까지 왔고 1~6이 모두 존재할 때만 한 사이클로 저장
            if step == 6:
                if all(s in self._current_cycle_steps for s in range(1, 7)):
                    for s_num in range(1, 7):
                        self.sequence_summary_buffer.append(
                            self._current_cycle_steps[s_num]
                        )

                    self.sequence_counter += 1
                    self._current_cycle_steps.clear()           

        # 50us 원시 패킷 버퍼
        if self.is_recording:
            record = {
                **pkt,
                "err_adc_vs_comp_us": self.analyzer.nodes[step].err_adc_vs_comp_us if (1 <= step <= 6) else 0,
                "zc_eval": zc_eval["status"] if zc_eval else "N/A"
            }
            self.raw_buffer.append(record)

        self.stats["curr_step"] = step
        self.stats["curr_mode"] = pkt["motor_state_str"]
        self.stats["curr_zc_str"] = pkt["zc_event_str"]
        self.stats["curr_ccr"] = pkt["ccr"]
        self.stats["e_rpm"] = int(self.analyzer.e_rpm)
        self.stats["m_rpm"] = int(self.analyzer.m_rpm)
        self.stats["cycle_zc_us"] = self.analyzer.cycle_zc_period_us

        self._last_step = step
        self._last_t_curr = pkt["t_curr"]
        self._last_bemf = pkt["bemf_curr"]