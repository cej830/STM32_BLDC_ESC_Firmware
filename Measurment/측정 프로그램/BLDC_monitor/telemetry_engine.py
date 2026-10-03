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
        self.rolling_buffer = deque(maxlen=config.ROLLING_BUFFER_LEN)
        self.is_recording = False
        
        # 캡처 저장 완료 이벤트 콜백 (UI 알림용)
        self.on_saved_callback = None

        # 시스템 통계
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
            "curr_trigger": 0
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

    def set_recording(self, state):
        self.is_recording = state
        if state:
            self.rolling_buffer.clear()

    def export_csv(self, reason):
        if not self.rolling_buffer:
            return None

        # 'captures' 폴더 자동 생성 및 저장
        save_dir = "captures"
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"bldc_{reason}_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        
        data_list = list(self.rolling_buffer)
        fieldnames = list(data_list[0].keys())

        with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data_list)

        if self.on_saved_callback:
            self.on_saved_callback(filename, len(data_list), reason)

        return filename

    def _rx_worker(self):
        while self.is_running:
            header = self.ser.read(1)
            if not header:
                # 타임아웃 발생 -> 모터가 멈췄거나 통신 차단
                if self.is_recording and len(self.rolling_buffer) > 0:
                    self.export_csv(reason="MOTOR_STOP_TIMEOUT")
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

        # 특수 샘플 카운트
        if trigger == TRIGGER_TIMEOUT_FORCE:
            self.stats["timeout_9999"] += 1
        elif trigger == TRIGGER_TIM_RACE:
            self.stats["race_9998"] += 1

        # 시퀀스 유실 계산
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

        # 주기 계산
        dt = diff_u16(pkt["t_curr"], self._last_t_curr) if self._last_t_curr else 50
        self._dt_history.append(dt)
        self.stats["avg_dt"] = sum(self._dt_history) / len(self._dt_history)

        # 스텝 순환 무결성 검증
        if self._last_step is not None and step != self._last_step:
            if step != ((self._last_step % 6) + 1):
                self.stats["step_seq_err"] += 1

        # ZC 판정 수행 (9998 레이스 침투 샘플 제외)
        zc_eval = None
        if pkt["zc_event"] == ZC_DETECTED and trigger != TRIGGER_TIM_RACE and (1 <= step <= 6):
            zc_eval = self.analyzer.evaluate(step, pkt["t_start"], pkt["t_zc"])

        # 스텝 전환 감지 -> 스텝 전체 길이 계산 트리거
        if self._last_step is not None and step != self._last_step:
            self.analyzer.on_step_transition(step, pkt["t_start"])
            if step != ((self._last_step % 6) + 1):
                self.stats["step_seq_err"] += 1
        elif self._last_step is None:
            self.analyzer.on_step_transition(step, pkt["t_start"])



        # 실시간 상태 갱신
        self.stats["curr_step"] = step
        self.stats["curr_mode"] = "CLOSED_LOOP" if is_cl else "OPEN_LOOP"
        self.stats["curr_trigger"] = trigger
        zc_map = {0: "Searching", 1: "DETECTED", 2: "TIMEOUT"}
        self.stats["curr_zc_str"] = zc_map.get(pkt["zc_event"], "Searching")
        self.stats["curr_ccr"] = pkt["ccr"] # 현재 CCR 실시간 기록 추가

        # 롤링 버퍼 레코드 추가
        if self.is_recording:
            record = {
                **pkt,
                "dt_us": dt,
                "bemf_prev": self._last_bemf if self._last_bemf else pkt["bemf_curr"],
                "zc_eval": zc_eval["status"] if zc_eval else "N/A",
                "zc_diff_pct": zc_eval["diff_pct"] if zc_eval else 0.0,
                "risk_streak": zc_eval["risk_streak"] if zc_eval else 0
            }
            self.rolling_buffer.append(record)

        self._last_step = step
        self._last_t_curr = pkt["t_curr"]
        self._last_bemf = pkt["bemf_curr"]