import sys
import time
import struct
import threading
import collections
import csv

import serial
import numpy as np

from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg


# =============================================================================
# 1. 사용자 설정 / MCU 패킷 규격
# =============================================================================
# MCU 쪽 MotorTelemetry_t가 바뀌면 가장 먼저 이 부분을 수정하면 됩니다.
PORT = "COM4"
BAUDRATE = 115200

# MCU 구조체가 __attribute__((packed)) 또는 #pragma pack(1)처럼
# padding 없이 전송된다는 전제입니다.
#
# uint8_t  header
# uint16_t phase_A, phase_B, phase_C, vcom_adc
# uint16_t ccr_target, ccr_current, step_laptime
# uint8_t  step_info
# uint16_t delay_target_edgree_30, delay_current_edgree_30
# uint8_t  delay_PAR
# uint8_t  tail
PACKET_FORMAT = "<B H H H H H H H B H H B B"
SAMPLE_SIZE = struct.calcsize(PACKET_FORMAT)       # 22 byte

EXPECTED_HEADER = 0xAA
EXPECTED_TAIL = 0xBB

# ADC/BEMF 분석기의 명목 샘플 주기.
# 현재 MCU가 약 20 kHz로 샘플링하므로 50 us.
SAMPLE_PERIOD_US = 50

# ---- PC측 ZC 품질 분석 기준 -------------------------------------------------
# ZC가 전체 step의 이 범위를 벗어나면 위치 이상으로 기록합니다.
# 0.20~0.80은 일부러 넓게 잡은 "명백한 이상 탐지" 범위입니다.
ZC_RATIO_MIN = 0.20
ZC_RATIO_MAX = 0.80

# 같은 Step의 이전 전기주기 ZC와 비교할 때:
# 1 sample 이하는 NORMAL, 2 sample 이하는 WATCH, 그 이상은 ANOMALY.
#
# 중요:
# 이 값들은 아직 MCU의 최종 VALID/RISK/REJECT 기준이 아닙니다.
# 먼저 PC에서 실제 분포를 관찰하기 위한 분석 기준입니다.
SAME_STEP_NORMAL_SAMPLES = 1.0
SAME_STEP_WATCH_SAMPLES = 2.0

# 특이 케이스 상세 화면에 저장할 최근 샘플 수.
# 400 sample * 50 us = 약 20 ms
SNAPSHOT_SAMPLES = 400


# =============================================================================
# 2. 공용 함수
# =============================================================================
def calc_bemf(step, phase_a, phase_b, phase_c):
    """
    MCU와 같은 개념으로 software VCOM을 만들고,
    현재 six-step에서 floating phase - VCOM 을 BEMF로 사용합니다.

    기존 프로그램의 phase mapping을 그대로 유지했습니다.
    """
    sw_vcom = (phase_a + phase_b + phase_c) / 3.0

    if step in (1, 4):
        floating = phase_c
    elif step in (2, 5):
        floating = phase_b
    else:
        floating = phase_a

    return float(floating - sw_vcom), sw_vcom, floating


def classify_same_step_delta(delta_us):
    """
    같은 step의 이전 전기주기와 비교한 ZC 변화량을
    샘플 개수 단위로 분류합니다.

    예:
      50 us  = 1 sample
      100 us = 2 samples
    """
    if delta_us is None:
        return "FIRST"

    samples = abs(delta_us) / float(SAMPLE_PERIOD_US)

    if samples <= SAME_STEP_NORMAL_SAMPLES:
        return "NORMAL"
    if samples <= SAME_STEP_WATCH_SAMPLES:
        return "WATCH"
    return "ANOMALY"


# =============================================================================
# 3. 백그라운드 Serial 수신 + 분석 Worker
# =============================================================================
class TelemetryWorker(threading.Thread):
    """
    Serial 수신은 GUI thread와 분리합니다.

    큰 흐름:
        Serial packet 수신
          -> packet decode
          -> BEMF 계산
          -> step 전환 검출
          -> 완료된 step 분석
          -> 실시간/기동/특이케이스 버퍼 갱신

    GUI는 이 worker가 만든 데이터만 읽어서 화면에 표시합니다.
    """

    def __init__(self, port, baudrate):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.running = True
        self.last_error = ""

        # ---------------------------------------------------------------------
        # Page 1: 실시간 표시용 버퍼
        # ---------------------------------------------------------------------
        self.rt_bemf = collections.deque(maxlen=1500)
        self.rt_step = collections.deque(maxlen=1500)

        # Step 1~6의 가장 최근 완성 파형
        self.step_waves = {i: [] for i in range(1, 7)}
        self.step_zc_laps = {i: 0 for i in range(1, 7)}
        self.step_d30_laps = {i: 0 for i in range(1, 7)}
        self.step_durations = {
            i: collections.deque(maxlen=30) for i in range(1, 7)
        }

        # ---------------------------------------------------------------------
        # Page 2: Open-loop -> Closed-loop 기동 캡처
        # ---------------------------------------------------------------------
        self.capture_startup = False
        self.startup_done = False
        self.startup_log = []
        self.stable_counter = 0

        # ---------------------------------------------------------------------
        # Page 3: Closed-loop ZC 분석
        # ---------------------------------------------------------------------
        self.anomaly_events = []
        self.anomaly_counter = 0
        self.recent_stream = collections.deque(maxlen=SNAPSHOT_SAMPLES)

        # "직전 step"과 "같은 step의 이전 전기주기"를 둘 다 저장합니다.
        #
        # 직전 step 비교:
        #   ST1 -> ST2처럼 서로 다른 step 특성이 섞일 수 있음.
        #
        # same-step 비교:
        #   이전 ST1 -> 현재 ST1처럼 한 전기주기 전 동일 step 비교.
        #   현재 우리가 MCU의 VALID/RISK 기준 후보로 더 관심 있는 값.
        self.prev_any_step_zc_lap = None
        self.last_zc_by_step = {i: None for i in range(1, 7)}

        # 최근 완료 step들의 분석 결과.
        # NORMAL까지 모두 보관하므로 PC에서 분포를 관찰할 수 있습니다.
        self.zc_history = collections.deque(maxlen=5000)

        # ---------------------------------------------------------------------
        # 현재 step 내부 상태
        # ---------------------------------------------------------------------
        self.prev_step = 0
        self.current_step_buffer = []

        # ZC 검출용 previous BEMF는 "step마다" 초기화해야 합니다.
        # 이전 step의 마지막 BEMF와 새 step의 첫 BEMF를 비교하면
        # 가짜 crossing을 만들 수 있기 때문입니다.
        self.prev_bemf_in_step = None

        self.zc_detected_this_step = False
        self.current_zc_lap = 0

        # 현재 GUI dashboard 상태
        self.status = {
            "step": 0,
            "ccr": 0,
            "erpm": 0,
            "is_cl": False,
            "vcom_err": 0.0,
            "anomaly_count": 0,
        }

    # -------------------------------------------------------------------------
    # 완료된 한 step을 분석
    # -------------------------------------------------------------------------
    def _finish_previous_step(self, next_packet_d_cur, next_packet_is_cl):
        """
        step 번호가 바뀌는 순간 직전 step을 닫습니다.

        기존 프로그램은 total_step_time = actual_zc + d_cur 를 계산할 때
        step이 이미 바뀐 '새 packet의 d_cur'를 사용할 수 있었습니다.
        여기서는 현재 step에서 마지막으로 받은 d_cur를 sample_dict에
        저장해 두었다가 그 값을 사용합니다.
        """
        if self.prev_step not in range(1, 7):
            return
        if len(self.current_step_buffer) <= 2:
            return

        # 최신 완성 파형 저장
        self.step_waves[self.prev_step] = list(self.current_step_buffer)

        if not self.zc_detected_this_step:
            return

        actual_zc = int(self.current_zc_lap)

        # current_step_samples의 마지막 packet은 직전 step 소속입니다.
        # 그 시점의 d_cur를 사용해야 직전 step의 ZC + 30도 delay가 됩니다.
        last_sample = self.current_step_samples[-1]
        d_cur = int(last_sample["d_cur"])
        is_cl = bool(last_sample["is_cl"])
        ccr = int(last_sample["ccr"])

        total_step_time = actual_zc + d_cur
        if total_step_time <= 0:
            return

        self.step_durations[self.prev_step].append(total_step_time)

        # ZC가 step 전체에서 어디에 위치했는가?
        # 0.513 -> step의 51.3% 지점.
        # 이것은 "중앙 편차"가 아니라 "ZC 위치 비율"입니다.
        zc_ratio = actual_zc / float(total_step_time)
        center_error_pct = abs(zc_ratio - 0.5) * 100.0

        # ---------------------------------------------------------------------
        # A) 직전 step과 비교
        # ---------------------------------------------------------------------
        prev_step_zc = self.prev_any_step_zc_lap
        if prev_step_zc is None:
            prev_delta_us = None
            prev_delta_samples = None
        else:
            prev_delta_us = actual_zc - prev_step_zc
            prev_delta_samples = prev_delta_us / float(SAMPLE_PERIOD_US)

        # ---------------------------------------------------------------------
        # B) 같은 step의 이전 전기주기와 비교
        # ---------------------------------------------------------------------
        same_step_prev_zc = self.last_zc_by_step[self.prev_step]
        if same_step_prev_zc is None:
            same_delta_us = None
            same_delta_samples = None
        else:
            same_delta_us = actual_zc - same_step_prev_zc
            same_delta_samples = same_delta_us / float(SAMPLE_PERIOD_US)

        quality = classify_same_step_delta(same_delta_us)

        # ZC 위치가 너무 앞/뒤에 있는지 별도 판단
        ratio_anomaly = (zc_ratio < ZC_RATIO_MIN) or (zc_ratio > ZC_RATIO_MAX)

        # 원인을 사람이 바로 알 수 있도록 문자열로 저장합니다.
        reasons = []
        if ratio_anomaly:
            reasons.append("ZC_POSITION")
        if quality == "WATCH":
            reasons.append("SAME_STEP_WATCH")
        elif quality == "ANOMALY":
            reasons.append("SAME_STEP_JITTER")

        # FIRST는 비교 대상이 없을 뿐 이상이 아닙니다.
        reason_text = " + ".join(reasons) if reasons else quality

        record = {
            "step": self.prev_step,
            "ccr": ccr,
            "zc_lap_us": actual_zc,
            "delay_30_us": d_cur,
            "step_total_us": total_step_time,
            "zc_position_pct": zc_ratio * 100.0,
            "center_error_pct": center_error_pct,

            "prev_step_zc_us": prev_step_zc,
            "prev_step_delta_us": prev_delta_us,
            "prev_step_delta_samples": prev_delta_samples,

            "same_step_prev_zc_us": same_step_prev_zc,
            "same_step_delta_us": same_delta_us,
            "same_step_delta_samples": same_delta_samples,

            "quality": quality,
            "reason": reason_text,
        }
        self.zc_history.append(record)

        # Page 3에는 WATCH/ANOMALY 또는 ZC 위치 이상만 넣습니다.
        # NORMAL 51% 같은 데이터가 수백 건씩 "이상"으로 쌓이는 문제를 제거합니다.
        if is_cl and (ratio_anomaly or quality in ("WATCH", "ANOMALY")):
            self.anomaly_counter += 1
            event = dict(record)
            event["id"] = self.anomaly_counter
            event["data"] = list(self.recent_stream)
            self.anomaly_events.append(event)

        # 다음 비교를 위한 기준 갱신.
        # PC 분석은 WATCH/ANOMALY도 실제 측정값으로 계속 추적합니다.
        self.prev_any_step_zc_lap = actual_zc
        self.last_zc_by_step[self.prev_step] = actual_zc

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
            ser.reset_input_buffer()
        except Exception as e:
            self.last_error = f"포트 열기 실패 ({self.port}): {e}"
            print("[ERROR]", self.last_error)
            return

        stream = bytearray()

        # 현재 step에 속한 packet들의 원본 분석값.
        self.current_step_samples = []

        while self.running:
            try:
                waiting = ser.in_waiting
                if waiting > 0:
                    stream.extend(ser.read(waiting))
                else:
                    time.sleep(0.001)
                    continue

                # stream 안에 여러 packet이 들어왔을 수 있으므로 가능한 만큼 처리
                while len(stream) >= SAMPLE_SIZE:
                    # Header/Tail이 맞으면 22 byte packet 하나를 소비
                    if (
                        stream[0] == EXPECTED_HEADER
                        and stream[SAMPLE_SIZE - 1] == EXPECTED_TAIL
                    ):
                        packet = bytes(stream[:SAMPLE_SIZE])
                        del stream[:SAMPLE_SIZE]

                        d = struct.unpack(PACKET_FORMAT, packet)

                        pa, pb, pc, vcom_adc = d[1], d[2], d[3], d[4]
                        ccr_tgt, ccr_cur, laptime = d[5], d[6], d[7]
                        step_info = d[8]
                        d_tgt, d_cur, par = d[9], d[10], d[11]

                        # 기존 프로그램의 encoding을 유지:
                        # 하위 4bit 값이 0~5이고 화면에서는 Step 1~6으로 사용.
                        step = (step_info & 0x0F) + 1
                        is_cl = bool((step_info >> 4) & 0x01)

                        bemf, sw_vcom, floating = calc_bemf(step, pa, pb, pc)

                        vcom_err = (
                            abs(float(vcom_adc) - sw_vcom)
                            / (abs(sw_vcom) + 1.0)
                            * 100.0
                        )

                        sample_dict = {
                            "step": step,
                            "is_cl": is_cl,
                            "bemf": bemf,
                            "sw_vcom": sw_vcom,
                            "flt": floating,
                            "vcom_adc": vcom_adc,
                            "laptime": laptime,
                            "d_cur": d_cur,
                            "d_tgt": d_tgt,
                            "par": par,
                            "ccr": ccr_cur,
                            "ccr_target": ccr_tgt,
                        }
                        self.recent_stream.append(sample_dict)

                        # =====================================================
                        # A. Step 전환 처리
                        # =====================================================
                        if step != self.prev_step:
                            # 새 step의 첫 packet을 처리하기 전에
                            # 직전 step을 먼저 완성/분석합니다.
                            self._finish_previous_step(d_cur, is_cl)

                            # 새 step 상태 초기화
                            self.prev_step = step
                            self.current_step_buffer = []
                            self.current_step_samples = []
                            self.zc_detected_this_step = False
                            self.current_zc_lap = 0
                            self.prev_bemf_in_step = None

                        # 현재 packet은 현재 step에 저장
                        self.current_step_buffer.append(bemf)
                        self.current_step_samples.append(sample_dict)

                        # =====================================================
                        # B. PC측 ZC 검출
                        # =====================================================
                        # 첫 BEMF sample은 기준값만 저장.
                        # 두 번째 sample부터 부호 교차를 검사합니다.
                        if self.prev_bemf_in_step is not None:
                            if not self.zc_detected_this_step:
                                crossed = (
                                    (self.prev_bemf_in_step < 0 and bemf >= 0)
                                    or
                                    (self.prev_bemf_in_step > 0 and bemf <= 0)
                                )
                                if crossed:
                                    self.zc_detected_this_step = True
                                    self.current_zc_lap = int(laptime)
                                    self.step_zc_laps[step] = int(laptime)
                                    self.step_d30_laps[step] = int(laptime + d_cur)

                        self.prev_bemf_in_step = bemf

                        # =====================================================
                        # C. Open -> Closed 기동 캡처
                        # =====================================================
                        if not is_cl:
                            if not self.capture_startup and not self.startup_done:
                                self.capture_startup = True
                                self.startup_log = []
                                self.stable_counter = 0

                            if self.capture_startup:
                                self.startup_log.append(sample_dict)

                        else:
                            if self.capture_startup:
                                self.startup_log.append(sample_dict)

                                # 기존 로직 유지:
                                # target/current 30도 delay 오차가 50 us 이내인 상태가
                                # 200 sample 이상 이어지면 기동 캡처 완료.
                                if abs(int(d_tgt) - int(d_cur)) <= 50:
                                    self.stable_counter += 1
                                    if self.stable_counter > 200:
                                        self.capture_startup = False
                                        self.startup_done = True
                                else:
                                    self.stable_counter = 0

                        # =====================================================
                        # D. 실시간 표시용 상태
                        # =====================================================
                        self.rt_bemf.append(bemf)
                        self.rt_step.append(step)

                        # 기존 계산을 유지합니다.
                        erpm = int(60000000 / (d_cur * 6)) if d_cur > 0 else 0

                        self.status = {
                            "step": step,
                            "ccr": ccr_cur,
                            "erpm": erpm,
                            "is_cl": is_cl,
                            "vcom_err": vcom_err,
                            "anomaly_count": self.anomaly_counter,
                        }

                    else:
                        # 동기화가 깨졌으면 한 byte 버리고 다시 Header/Tail 탐색
                        del stream[0]

            except Exception as e:
                self.last_error = str(e)
                print("[ERROR] Telemetry worker:", e)
                break

        try:
            ser.close()
        except Exception:
            pass

    def stop(self):
        self.running = False


# =============================================================================
# 4. GUI
# =============================================================================
class BldcMasterDiagnosticApp(QtWidgets.QMainWindow):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.is_paused = False

        self.setWindowTitle("BLDC ESC 종합 정밀 진단 시스템")
        self.resize(1550, 900)

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_page1 = QtWidgets.QWidget()
        self.tab_page2 = QtWidgets.QWidget()
        self.tab_page3 = QtWidgets.QWidget()

        self.tabs.addTab(self.tab_page1, "기본 화면")
        self.tabs.addTab(self.tab_page2, "OPEN → CLOSED 기동")
        self.tabs.addTab(self.tab_page3, "ZC 품질 분석")

        self.setup_page1()
        self.setup_page2()
        self.setup_page3()

        # GUI는 약 60 Hz로 갱신.
        # Serial parsing은 worker thread에서 따로 동작합니다.
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(16)

    # -------------------------------------------------------------------------
    # Page 1
    # -------------------------------------------------------------------------
    def setup_page1(self):
        root_layout = QtWidgets.QHBoxLayout(self.tab_page1)
        left_layout = QtWidgets.QVBoxLayout()

        pg.setConfigOptions(antialias=False)

        self.gw_main = pg.GraphicsLayoutWidget()
        self.p_main = self.gw_main.addPlot(
            title="실시간 BEMF (Floating Phase - sw_VCOM)"
        )
        self.p_main.showGrid(x=True, y=True, alpha=0.3)
        self.p_main.addLine(
            y=0, pen=pg.mkPen("r", width=1.5, style=QtCore.Qt.DashLine)
        )
        self.curve_main = self.p_main.plot(
            pen=pg.mkPen("#00FFCC", width=1.5)
        )
        left_layout.addWidget(self.gw_main, stretch=4)

        # 6개 step의 가장 최근 파형
        self.gw_steps = pg.GraphicsLayoutWidget()
        self.step_plots = {}
        self.step_curves = {}
        self.step_zc_lines = {}
        self.step_d30_lines = {}

        for i in range(1, 7):
            row = 0 if i <= 3 else 1
            col = (i - 1) % 3

            p = self.gw_steps.addPlot(
                row=row, col=col, title=f"STEP {i}"
            )
            p.showGrid(x=True, y=True, alpha=0.2)
            p.addLine(
                y=0,
                pen=pg.mkPen("gray", width=1, style=QtCore.Qt.DotLine),
            )

            zc_line = p.addLine(x=0, pen=pg.mkPen("y", width=1.5))
            d30_line = p.addLine(
                x=0,
                pen=pg.mkPen(
                    "#FF00FF", width=1.5, style=QtCore.Qt.DashLine
                ),
            )
            curve = p.plot(
                pen=pg.mkPen(
                    "#FFFF00" if i % 2 else "#00FFFF", width=1.3
                )
            )

            self.step_plots[i] = p
            self.step_curves[i] = curve
            self.step_zc_lines[i] = zc_line
            self.step_d30_lines[i] = d30_line

        left_layout.addWidget(self.gw_steps, stretch=5)
        root_layout.addLayout(left_layout, stretch=8)

        # 오른쪽 dashboard
        right_panel = QtWidgets.QFrame()
        right_panel.setFrameShape(QtWidgets.QFrame.StyledPanel)
        right_panel.setStyleSheet(
            "background-color:#1E1E1E; border-radius:6px; padding:10px;"
        )
        rp = QtWidgets.QVBoxLayout(right_panel)

        title = QtWidgets.QLabel("시스템 계측 현황")
        title.setStyleSheet(
            "font-size:16px; font-weight:bold; color:white;"
        )
        rp.addWidget(title)

        self.lbl_step_ccr = QtWidgets.QLabel("STEP: - | CCR: -")
        self.lbl_erpm = QtWidgets.QLabel("eRPM: -")
        self.lbl_vcom_err = QtWidgets.QLabel("VCOM 오차율: -")
        self.lbl_anomaly = QtWidgets.QLabel("WATCH/이상: 0")
        self.lbl_stats = QtWidgets.QLabel("스텝 평균 시간:\n-")

        for lbl in [
            self.lbl_step_ccr,
            self.lbl_erpm,
            self.lbl_vcom_err,
            self.lbl_anomaly,
            self.lbl_stats,
        ]:
            lbl.setStyleSheet(
                "font-size:13px; color:#00FFCC; padding:6px;"
                "background-color:#2A2A2A; border-radius:4px;"
            )
            rp.addWidget(lbl)

        rp.addStretch()

        self.btn_pause = QtWidgets.QPushButton("일시정지 (Space)")
        self.btn_pause.clicked.connect(self.toggle_pause)
        rp.addWidget(self.btn_pause)

        root_layout.addWidget(right_panel, stretch=2)

    # -------------------------------------------------------------------------
    # Page 2
    # -------------------------------------------------------------------------
    def setup_page2(self):
        layout = QtWidgets.QVBoxLayout(self.tab_page2)

        ctrl = QtWidgets.QHBoxLayout()
        self.lbl_p2_state = QtWidgets.QLabel("기동 데이터 수집 대기 중...")
        ctrl.addWidget(self.lbl_p2_state)

        self.btn_save_p2 = QtWidgets.QPushButton("기동 로그 CSV 저장")
        self.btn_save_p2.clicked.connect(self.save_p2_csv)
        ctrl.addWidget(self.btn_save_p2)

        self.btn_reset_p2 = QtWidgets.QPushButton("재캡처 준비")
        self.btn_reset_p2.clicked.connect(self.reset_p2_capture)
        ctrl.addWidget(self.btn_reset_p2)

        layout.addLayout(ctrl)

        self.gw_p2 = pg.GraphicsLayoutWidget()

        self.p2_plot1 = self.gw_p2.addPlot(title="기동 전 과정 BEMF")
        self.p2_plot1.showGrid(x=True, y=True, alpha=0.3)
        self.curve_p2_bemf = self.p2_plot1.plot(
            pen=pg.mkPen("#00FFCC", width=1.2)
        )

        self.gw_p2.nextRow()

        self.p2_plot2 = self.gw_p2.addPlot(
            title="30도 delay 수렴 (target / current)"
        )
        self.p2_plot2.showGrid(x=True, y=True, alpha=0.3)
        self.curve_p2_delay = self.p2_plot2.plot(
            pen=pg.mkPen("#FFCC00", width=1.5)
        )
        self.p2_plot2.setXLink(self.p2_plot1)

        layout.addWidget(self.gw_p2)

    # -------------------------------------------------------------------------
    # Page 3
    # -------------------------------------------------------------------------
    def setup_page3(self):
        """
        기존 Page 3의 핵심 수정점:

        1) '중앙 편차(비율)' -> 'Step 내 ZC 위치'
        2) 직전 step 변화와 동일 step 이전-cycle 변화를 동시에 표시
        3) 50 us를 1 sample로 환산해 몇 sample 차이인지 표시
        4) 왜 목록에 들어왔는지 원인(WATCH/JITTER/POSITION)을 표시
        """
        layout = QtWidgets.QHBoxLayout(self.tab_page3)

        left = QtWidgets.QVBoxLayout()

        explanation = QtWidgets.QLabel(
            "ZC 품질 분석\n"
            "• 위치(%) = ZC시각 / (ZC시각 + 30° delay)\n"
            "• ΔSame = 같은 Step의 이전 전기주기 대비 변화\n"
            "• 50 us = 1 sample 기준\n"
            "• WATCH: >1 sample, ANOMALY: >2 sample (현재 PC 분석용 임시 기준)"
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("font-size:12px; font-weight:bold;")
        left.addWidget(explanation)

        # 열이 많아졌기 때문에 10 columns 사용
        headers = [
            "ID",
            "Step",
            "CCR",
            "ZC",
            "ZC 위치",
            "중앙오차",
            "ΔPrev",
            "ΔSame",
            "ΔSame(sample)",
            "판정/원인",
        ]

        self.table_anomalies = QtWidgets.QTableWidget(0, len(headers))
        self.table_anomalies.setHorizontalHeaderLabels(headers)
        self.table_anomalies.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        self.table_anomalies.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection
        )
        self.table_anomalies.clicked.connect(self.display_anomaly_detail)

        header = self.table_anomalies.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)

        left.addWidget(self.table_anomalies)

        button_row = QtWidgets.QHBoxLayout()

        self.btn_save_p3 = QtWidgets.QPushButton("선택 사례 CSV 저장")
        self.btn_save_p3.clicked.connect(self.save_p3_csv)
        button_row.addWidget(self.btn_save_p3)

        self.btn_save_summary = QtWidgets.QPushButton("ZC 분석 전체 CSV 저장")
        self.btn_save_summary.clicked.connect(self.save_zc_summary_csv)
        button_row.addWidget(self.btn_save_summary)

        left.addLayout(button_row)
        layout.addLayout(left, stretch=6)

        # 오른쪽: 선택한 이벤트의 최근 BEMF snapshot
        self.gw_p3 = pg.GraphicsLayoutWidget()
        self.p3_plot = self.gw_p3.addPlot(
            title="선택 ZC 사례 주변 BEMF"
        )
        self.p3_plot.showGrid(x=True, y=True, alpha=0.3)
        self.p3_plot.addLine(
            y=0, pen=pg.mkPen("r", style=QtCore.Qt.DashLine)
        )
        self.curve_p3_detail = self.p3_plot.plot(
            pen=pg.mkPen("#FF3366", width=1.5)
        )

        layout.addWidget(self.gw_p3, stretch=4)

    # -------------------------------------------------------------------------
    # GUI update
    # -------------------------------------------------------------------------
    def update_gui(self):
        if self.is_paused:
            return

        st = self.worker.status

        mode = "CLOSED" if st["is_cl"] else "OPEN"
        self.lbl_step_ccr.setText(
            f"STEP: {st['step']} ({mode})\nCCR: {st['ccr']}"
        )
        self.lbl_erpm.setText(f"eRPM: {st['erpm']}")
        self.lbl_vcom_err.setText(
            f"VCOM 오차율: {st['vcom_err']:.1f}%"
        )
        self.lbl_anomaly.setText(
            f"WATCH/이상: {st['anomaly_count']} 건"
        )

        stats_txt = "스텝 평균 지속시간:\n"
        for s in range(1, 7):
            durs = self.worker.step_durations[s]
            avg_d = np.mean(durs) if durs else 0
            stats_txt += f"S{s}: {int(avg_d)}us "
            if s == 3:
                stats_txt += "\n"
        self.lbl_stats.setText(stats_txt)

        # Page 1
        if len(self.worker.rt_bemf) > 50:
            self.curve_main.setData(np.array(self.worker.rt_bemf))

        for s in range(1, 7):
            wave = self.worker.step_waves[s]
            if len(wave) > 2:
                self.step_curves[s].setData(np.array(wave))

                # GUI x축은 sample index이므로 us -> sample index 변환
                zc_idx = self.worker.step_zc_laps[s] / SAMPLE_PERIOD_US
                d30_idx = self.worker.step_d30_laps[s] / SAMPLE_PERIOD_US

                self.step_zc_lines[s].setValue(zc_idx)
                self.step_d30_lines[s].setValue(d30_idx)
                self.step_plots[s].setTitle(
                    f"STEP {s} (약 {len(wave)*SAMPLE_PERIOD_US} us)"
                )

        # Page 2
        if self.worker.startup_done and self.worker.startup_log:
            self.lbl_p2_state.setText(
                f"기동 캡처 완료 ({len(self.worker.startup_log)} samples)"
            )
            bemf_all = [p["bemf"] for p in self.worker.startup_log]
            dcur_all = [p["d_cur"] for p in self.worker.startup_log]
            self.curve_p2_bemf.setData(np.array(bemf_all))
            self.curve_p2_delay.setData(np.array(dcur_all))

        # Page 3: 새 event만 table에 추가
        events = self.worker.anomaly_events
        if len(events) > self.table_anomalies.rowCount():
            start = self.table_anomalies.rowCount()
            self.table_anomalies.setRowCount(len(events))

            for row in range(start, len(events)):
                ev = events[row]

                values = [
                    str(ev["id"]),
                    f"S{ev['step']}",
                    str(ev["ccr"]),
                    f"{ev['zc_lap_us']} us",
                    f"{ev['zc_position_pct']:.1f}%",
                    f"{ev['center_error_pct']:.1f}%",
                    self._fmt_delta(ev["prev_step_delta_us"], "us"),
                    self._fmt_delta(ev["same_step_delta_us"], "us"),
                    self._fmt_delta(ev["same_step_delta_samples"], ""),
                    ev["reason"],
                ]

                for col, value in enumerate(values):
                    self.table_anomalies.setItem(
                        row, col, QtWidgets.QTableWidgetItem(value)
                    )

    @staticmethod
    def _fmt_delta(value, unit):
        if value is None:
            return "-"
        if isinstance(value, float):
            text = f"{value:+.2f}"
        else:
            text = f"{value:+d}"
        return f"{text} {unit}".strip()

    # -------------------------------------------------------------------------
    # UI handlers
    # -------------------------------------------------------------------------
    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.btn_pause.setText(
            "재개 (Space)" if self.is_paused else "일시정지 (Space)"
        )

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Space:
            self.toggle_pause()
        else:
            super().keyPressEvent(event)

    def reset_p2_capture(self):
        self.worker.startup_done = False
        self.worker.capture_startup = False
        self.worker.startup_log = []
        self.worker.stable_counter = 0
        self.lbl_p2_state.setText("새로운 기동 시퀀스를 대기 중입니다...")

    def save_p2_csv(self):
        if not self.worker.startup_log:
            QtWidgets.QMessageBox.warning(
                self, "경고", "저장할 기동 데이터가 없습니다."
            )
            return

        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "기동 로그 CSV 저장",
            "motor_startup_log.csv",
            "CSV Files (*.csv)",
        )
        if not fname:
            return

        with open(fname, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=self.worker.startup_log[0].keys()
            )
            writer.writeheader()
            writer.writerows(self.worker.startup_log)

    def display_anomaly_detail(self):
        row = self.table_anomalies.currentRow()
        if row < 0 or row >= len(self.worker.anomaly_events):
            return

        ev = self.worker.anomaly_events[row]
        bemf_data = [p["bemf"] for p in ev["data"]]
        self.curve_p3_detail.setData(np.array(bemf_data))

        same_text = (
            "-"
            if ev["same_step_delta_samples"] is None
            else f"{ev['same_step_delta_samples']:+.2f} sample"
        )

        self.p3_plot.setTitle(
            f"#{ev['id']} | Step {ev['step']} | CCR {ev['ccr']} | "
            f"ZC {ev['zc_lap_us']} us | 위치 {ev['zc_position_pct']:.1f}% | "
            f"ΔSame {same_text} | {ev['reason']}"
        )

    def save_p3_csv(self):
        """
        선택한 이벤트 주변의 raw sample snapshot 저장.
        파형을 나중에 Excel/Python에서 다시 볼 때 사용합니다.
        """
        row = self.table_anomalies.currentRow()
        if row < 0 or row >= len(self.worker.anomaly_events):
            QtWidgets.QMessageBox.warning(
                self, "경고", "저장할 사례를 선택하세요."
            )
            return

        ev = self.worker.anomaly_events[row]
        if not ev["data"]:
            return

        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "선택 사례 CSV 저장",
            f"zc_event_{ev['id']}.csv",
            "CSV Files (*.csv)",
        )
        if not fname:
            return

        with open(fname, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=ev["data"][0].keys())
            writer.writeheader()
            writer.writerows(ev["data"])

    def save_zc_summary_csv(self):
        """
        NORMAL을 포함한 모든 완료 ZC의 분석값을 저장합니다.

        이 파일이 MCU의 VALID/RISK/REJECT 범위를 정할 때 가장 중요합니다.
        특히 아래 열을 비교하면 됩니다.

          same_step_delta_us
          same_step_delta_samples
          zc_position_pct
          CCR
          Step
        """
        history = list(self.worker.zc_history)
        if not history:
            QtWidgets.QMessageBox.warning(
                self, "경고", "저장할 ZC 분석 데이터가 없습니다."
            )
            return

        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "ZC 전체 분석 CSV 저장",
            "zc_analysis_summary.csv",
            "CSV Files (*.csv)",
        )
        if not fname:
            return

        with open(fname, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=history[0].keys())
            writer.writeheader()
            writer.writerows(history)

        QtWidgets.QMessageBox.information(
            self,
            "완료",
            "NORMAL을 포함한 전체 ZC 분석 데이터를 저장했습니다.",
        )

    def closeEvent(self, event):
        self.worker.stop()
        self.worker.join(timeout=1.0)
        event.accept()


# =============================================================================
# 5. Program entry
# =============================================================================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    worker = TelemetryWorker(PORT, BAUDRATE)
    worker.start()

    window = BldcMasterDiagnosticApp(worker)
    window.show()

    sys.exit(app.exec_())
