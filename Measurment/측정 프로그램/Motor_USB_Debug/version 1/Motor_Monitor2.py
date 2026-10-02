import csv
import os
import struct
import threading
import queue
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports


# ============================================================
# 사용자 설정
# ============================================================

PACKET_SIZE = 22
HEADER = 0xAA
TAIL = 0xBB

CAPTURE_CYCLES = 100
CAPTURE_STEPS = CAPTURE_CYCLES * 6

# ΔTotal Avg 계산 시 사용할 최근 step 개수
TOTAL_AVG_WINDOW = 6

# CSV 저장 폴더
SAVE_DIR = "BLDC_Captures"

# USB CDC가 Virtual COM Port로 동작하는 경우 baudrate 자체는
# 실제 USB FS 전송속도를 결정하지 않는 경우가 많지만,
# pyserial open에는 값이 필요하므로 지정.
DEFAULT_BAUDRATE = 921600


# ============================================================
# 패킷 구조
#
# C:
#
# #pragma pack(push, 1)
# typedef struct
# {
#     uint8_t  header;
#
#     uint16_t phase_A;
#     uint16_t phase_B;
#     uint16_t phase_C;
#     uint16_t vcom_adc;
#
#     uint16_t ccr_target;
#     uint16_t ccr_current;
#
#     uint16_t step_laptime;
#     uint8_t  step_info;
#
#     uint16_t delay_target_edgree_30;
#     uint16_t delay_current_edgree_30;
#     uint8_t  delay_PAR;
#
#     uint8_t  tail;
#
# } MotorTelemetry_t;
# #pragma pack(pop)
#
# 총 22 byte
#
# STM32 = little endian
# ============================================================

PACKET_FORMAT = "<BHHHHHHHBHHBB"

assert struct.calcsize(PACKET_FORMAT) == PACKET_SIZE


@dataclass
class TelemetryPacket:
    """
    MCU에서 수신한 RAW telemetry packet 하나.
    """

    header: int

    phase_a: int
    phase_b: int
    phase_c: int
    vcom_adc: int

    ccr_target: int
    ccr_current: int

    step_laptime: int
    step_info: int

    delay_target: int
    delay_current: int
    delay_par: int

    tail: int

    # PC에서 계산
    step: int = 0
    is_closed_loop: bool = False

    bemf: float = 0.0
    sw_vcom: float = 0.0
    floating_phase: float = 0.0

    zc_detected: bool = False

    # Capture 후 붙이는 정보
    cycle: int = 0
    capture_step_index: int = 0
    sample_index: int = 0


@dataclass
class StepResult:
    """
    한 Step에 대한 분석 결과.

    Step 내부에는 여러 개의 20 kHz ADC sample이 존재하지만,
    분석 CSV에서는 한 Step = 한 행으로 압축한다.
    """

    cycle: int
    step: int
    capture_step_index: int

    ccr_target: int
    ccr_current: int

    zc_duration: int
    delay_target: int
    delay_current: int

    total_step: int
    zc_position: float

    delta_zc_prev: float = float("nan")
    delta_zc_same: float = float("nan")

    delta_total_prev: float = float("nan")
    delta_total_same: float = float("nan")
    delta_total_avg: float = float("nan")

    sample_count: int = 0


# ============================================================
# BEMF 계산
# ============================================================

def calc_bemf(step, phase_a, phase_b, phase_c):
    """
    MCU와 같은 개념으로 software VCOM을 만든다.

        sw_vcom = (A + B + C) / 3

    현재 six-step에서 floating phase - VCOM을 BEMF로 사용.

    사용자 프로젝트의 floating phase mapping:

        Step 1, 4 -> Phase C
        Step 2, 5 -> Phase B
        Step 3, 6 -> Phase A
    """

    sw_vcom = (phase_a + phase_b + phase_c) / 3.0

    if step in (1, 4):
        floating = phase_c

    elif step in (2, 5):
        floating = phase_b

    else:
        floating = phase_a

    bemf = float(floating - sw_vcom)

    return bemf, sw_vcom, float(floating)


def is_zero_crossing(step, prev_bemf, current_bemf):
    """
    ZC 검출.

    현재 프로젝트 기준:
        Step 1, 3, 5 : Falling ZC
        Step 2, 4, 6 : Rising ZC

    현재는 선형보간하지 않는다.

    즉 부호가 바뀐 '현재 sample'의 step_laptime을
    ZC Duration으로 사용한다.
    """

    if prev_bemf is None:
        return False

    # Odd step -> Falling
    if step in (1, 3, 5):
        return prev_bemf > 0.0 and current_bemf <= 0.0

    # Even step -> Rising
    else:
        return prev_bemf < 0.0 and current_bemf >= 0.0


# ============================================================
# 패킷 파서
# ============================================================

def decode_packet(data):
    """
    정확히 22 byte짜리 packet을 TelemetryPacket으로 변환.
    """

    if len(data) != PACKET_SIZE:
        return None

    values = struct.unpack(PACKET_FORMAT, data)

    packet = TelemetryPacket(
        header=values[0],

        phase_a=values[1],
        phase_b=values[2],
        phase_c=values[3],
        vcom_adc=values[4],

        ccr_target=values[5],
        ccr_current=values[6],

        step_laptime=values[7],
        step_info=values[8],

        delay_target=values[9],
        delay_current=values[10],
        delay_par=values[11],

        tail=values[12],
    )

    if packet.header != HEADER:
        return None

    if packet.tail != TAIL:
        return None

    # MCU:
    #
    # step_info = current_step - 1;
    #
    # 따라서 하위 nibble:
    #   0 -> Step 1
    #   ...
    #   5 -> Step 6

    packet.step = (packet.step_info & 0x0F) + 1

    # bit4 = 1이면 OPEN_LOOP이 아닌 상태
    packet.is_closed_loop = bool(packet.step_info & 0x10)

    if not (1 <= packet.step <= 6):
        return None

    packet.bemf, packet.sw_vcom, packet.floating_phase = calc_bemf(
        packet.step,
        packet.phase_a,
        packet.phase_b,
        packet.phase_c
    )

    return packet


# ============================================================
# Serial Receiver
# ============================================================

class SerialReceiver(threading.Thread):
    """
    Serial 수신 전용 thread.

    중요한 점:
        GUI thread에서 serial.read()를 하면 GUI가 멈출 수 있다.

    따라서:
        Serial Thread -> Queue -> GUI/Main processing

    구조로 사용한다.
    """

    def __init__(self, ser, rx_queue, status_queue):
        super().__init__(daemon=True)

        self.ser = ser
        self.rx_queue = rx_queue
        self.status_queue = status_queue

        self.running = True

        # 아직 완성되지 않은 USB 데이터 저장
        self.buffer = bytearray()

        self.valid_packet_count = 0
        self.invalid_byte_count = 0

    def stop(self):
        self.running = False

    def run(self):

        try:
            while self.running:

                # USB에 현재 들어온 데이터가 있으면 한꺼번에 읽는다.
                waiting = self.ser.in_waiting

                if waiting > 0:
                    data = self.ser.read(waiting)
                else:
                    data = self.ser.read(1)

                if not data:
                    continue

                self.buffer.extend(data)

                self.parse_buffer()

        except Exception as e:
            self.status_queue.put(("serial_error", str(e)))

    def parse_buffer(self):
        """
        byte stream에서

            0xAA ... 22 bytes ... 0xBB

        packet을 계속 찾아낸다.

        데이터가 중간부터 들어오기 시작해도 HEADER를 찾아
        synchronization을 다시 맞춘다.
        """

        while len(self.buffer) >= PACKET_SIZE:

            # 첫 byte가 header가 아니라면 header 검색
            if self.buffer[0] != HEADER:

                try:
                    header_pos = self.buffer.index(HEADER)

                    self.invalid_byte_count += header_pos
                    del self.buffer[:header_pos]

                except ValueError:
                    # buffer 안에 header 자체가 없음
                    self.invalid_byte_count += len(self.buffer)
                    self.buffer.clear()
                    return

            if len(self.buffer) < PACKET_SIZE:
                return

            candidate = bytes(self.buffer[:PACKET_SIZE])

            # 마지막 byte까지 검증
            if candidate[-1] != TAIL:
                # 잘못된 0xAA를 잡은 경우 한 byte 버리고 다시 sync
                del self.buffer[0]
                self.invalid_byte_count += 1
                continue

            packet = decode_packet(candidate)

            if packet is None:
                del self.buffer[0]
                self.invalid_byte_count += 1
                continue

            # 정상 packet
            del self.buffer[:PACKET_SIZE]

            self.valid_packet_count += 1

            self.rx_queue.put(packet)


# ============================================================
# Capture / 분석
# ============================================================

class CaptureManager:

    STATE_IDLE = 0
    STATE_ARMED = 1
    STATE_CAPTURING = 2

    def __init__(self):

        self.state = self.STATE_IDLE

        # 모든 RAW sample
        self.raw_packets = []

        # 완료된 step별 결과
        self.step_results = []

        # 현재 step의 RAW sample
        self.current_step_samples = []

        self.current_step = None

        # ZC 검출용
        self.prev_bemf = None
        self.zc_found = False
        self.zc_packet = None

        # 캡처 시작 전 step 변화 검출
        self.last_stream_step = None

        # capture 전체 sample index
        self.sample_index = 0

        # 현재 capture에서 완료된 step 개수
        self.completed_steps = 0

        # 최근 Total Step
        self.recent_total = deque(maxlen=TOTAL_AVG_WINDOW)

        # Step별 직전 cycle 데이터
        self.last_same_step = {}

        # 직전 step
        self.previous_result = None

        self.capture_complete_callback = None

    def arm(self):
        """
        SPACE를 눌렀을 때 호출.

        즉시 캡처하지 않고,
        '다음 Step 1 진입'을 기다린다.
        """

        self.reset_capture()

        self.state = self.STATE_ARMED

        print("Capture ARMED - waiting for next Step 1...")

    def reset_capture(self):

        self.raw_packets.clear()
        self.step_results.clear()

        self.current_step_samples.clear()

        self.current_step = None

        self.prev_bemf = None
        self.zc_found = False
        self.zc_packet = None

        self.sample_index = 0
        self.completed_steps = 0

        self.recent_total.clear()
        self.last_same_step.clear()
        self.previous_result = None

    def cancel(self):
        self.state = self.STATE_IDLE
        self.reset_capture()

    def process_packet(self, packet):
        """
        들어오는 모든 packet에 대해 호출된다.
        """

        # ----------------------------------------------------
        # ARMED
        # ----------------------------------------------------

        if self.state == self.STATE_ARMED:

            # Step 1의 중간부터 시작하면 안 된다.
            #
            # 따라서 이전 packet이 Step 1이 아니었고,
            # 이번 packet이 Step 1인 순간을 기다린다.

            if (
                packet.step == 1
                and self.last_stream_step is not None
                and self.last_stream_step != 1
            ):
                self.start_capture(packet)

            self.last_stream_step = packet.step

            return

        # ----------------------------------------------------
        # IDLE
        # ----------------------------------------------------

        if self.state != self.STATE_CAPTURING:
            self.last_stream_step = packet.step
            return

        # ----------------------------------------------------
        # CAPTURING
        # ----------------------------------------------------

        self.sample_index += 1
        packet.sample_index = self.sample_index

        # 최초 packet
        if self.current_step is None:
            self.current_step = packet.step

        # Step이 변경됨
        if packet.step != self.current_step:

            # 방금까지 모았던 이전 step 완료
            self.finish_current_step()

            # 600 step 완료
            if self.completed_steps >= CAPTURE_STEPS:

                self.state = self.STATE_IDLE

                if self.capture_complete_callback:
                    self.capture_complete_callback()

                self.last_stream_step = packet.step
                return

            # 새로운 step 준비
            self.current_step = packet.step
            self.current_step_samples = []

            self.prev_bemf = None
            self.zc_found = False
            self.zc_packet = None

        # 현재 packet을 현재 step에 추가
        self.process_step_sample(packet)

        self.raw_packets.append(packet)

        self.last_stream_step = packet.step

    def start_capture(self, first_packet):

        print("Capture START")

        self.state = self.STATE_CAPTURING

        self.current_step = 1

        self.current_step_samples = []

        self.prev_bemf = None
        self.zc_found = False
        self.zc_packet = None

        self.sample_index = 1

        first_packet.sample_index = self.sample_index

        self.process_step_sample(first_packet)

        self.raw_packets.append(first_packet)

    def process_step_sample(self, packet):

        # 아직 ZC를 찾지 않았다면 검사
        if not self.zc_found:

            if is_zero_crossing(
                packet.step,
                self.prev_bemf,
                packet.bemf
            ):
                packet.zc_detected = True

                self.zc_found = True
                self.zc_packet = packet

        self.prev_bemf = packet.bemf

        self.current_step_samples.append(packet)

    def finish_current_step(self):
        """
        한 Step이 끝났을 때 호출.

        해당 Step에서 찾은 ZC sample을 이용하여
        StepResult 한 행을 만든다.
        """

        if not self.current_step_samples:
            return

        self.completed_steps += 1

        step_number = self.current_step

        # 1~600
        step_index = self.completed_steps

        # 1~100
        cycle = ((step_index - 1) // 6) + 1

        # RAW packet에도 cycle / step index 기록
        for p in self.current_step_samples:
            p.cycle = cycle
            p.capture_step_index = step_index

        # ZC를 찾지 못한 Step
        if self.zc_packet is None:

            print(
                f"[WARNING] "
                f"Cycle={cycle}, Step={step_number}: ZC not found"
            )

            # 분석 행을 만들 수 없으므로 일단 skip
            return

        zc_duration = self.zc_packet.step_laptime

        delay_target = self.zc_packet.delay_target
        delay_current = self.zc_packet.delay_current

        ccr_target = self.zc_packet.ccr_target
        ccr_current = self.zc_packet.ccr_current

        # ----------------------------------------------------
        # 사용자가 지정한 Total Step 정의
        #
        # Total Step = ZC Duration + 실제 적용된 current delay
        # ----------------------------------------------------

        total_step = zc_duration + delay_current

        if total_step > 0:
            zc_position = (
                zc_duration / total_step
            ) * 100.0
        else:
            zc_position = float("nan")

        result = StepResult(
            cycle=cycle,
            step=step_number,
            capture_step_index=step_index,

            ccr_target=ccr_target,
            ccr_current=ccr_current,

            zc_duration=zc_duration,

            delay_target=delay_target,
            delay_current=delay_current,

            total_step=total_step,
            zc_position=zc_position,

            sample_count=len(self.current_step_samples)
        )

        # ----------------------------------------------------
        # Δ Prev
        # 직전 Step과 비교
        # ----------------------------------------------------

        if self.previous_result is not None:

            result.delta_zc_prev = (
                result.zc_duration
                - self.previous_result.zc_duration
            )

            result.delta_total_prev = (
                result.total_step
                - self.previous_result.total_step
            )

        # ----------------------------------------------------
        # Δ Same
        #
        # 이전 electrical cycle의 동일 Step과 비교.
        #
        # S1 -> 이전 S1
        # S2 -> 이전 S2
        # ...
        # ----------------------------------------------------

        if step_number in self.last_same_step:

            old = self.last_same_step[step_number]

            result.delta_zc_same = (
                result.zc_duration
                - old.zc_duration
            )

            result.delta_total_same = (
                result.total_step
                - old.total_step
            )

        # ----------------------------------------------------
        # Δ Total Avg
        #
        # 현재 Step을 넣기 전 최근 N개 step의 평균과 비교.
        # ----------------------------------------------------

        if len(self.recent_total) > 0:

            avg_total = (
                sum(self.recent_total)
                / len(self.recent_total)
            )

            result.delta_total_avg = (
                result.total_step - avg_total
            )

        # 분석 결과 저장
        self.step_results.append(result)

        # 다음 비교를 위해 상태 업데이트
        self.previous_result = result
        self.last_same_step[step_number] = result

        self.recent_total.append(result.total_step)


# ============================================================
# CSV 저장
# ============================================================

def save_capture_csv(capture_manager):

    os.makedirs(SAVE_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    raw_path = os.path.join(
        SAVE_DIR,
        f"capture_{timestamp}_raw.csv"
    )

    analysis_path = os.path.join(
        SAVE_DIR,
        f"capture_{timestamp}_analysis.csv"
    )

    # --------------------------------------------------------
    # RAW CSV
    # --------------------------------------------------------

    with open(
        raw_path,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "sample_index",
            "cycle",
            "capture_step_index",

            "step",
            "closed_loop",

            "phase_A",
            "phase_B",
            "phase_C",

            "vcom_adc",
            "sw_vcom",
            "floating_phase",
            "bemf",

            "ccr_target",
            "ccr_current",

            "step_laptime_us",

            "delay_target_us",
            "delay_current_us",
            "delay_PAR",

            "zc_detected"
        ])

        for p in capture_manager.raw_packets:

            writer.writerow([
                p.sample_index,
                p.cycle,
                p.capture_step_index,

                p.step,
                int(p.is_closed_loop),

                p.phase_a,
                p.phase_b,
                p.phase_c,

                p.vcom_adc,
                f"{p.sw_vcom:.3f}",
                f"{p.floating_phase:.3f}",
                f"{p.bemf:.3f}",

                p.ccr_target,
                p.ccr_current,

                p.step_laptime,

                p.delay_target,
                p.delay_current,
                p.delay_par,

                int(p.zc_detected)
            ])

    # --------------------------------------------------------
    # Analysis CSV
    # --------------------------------------------------------

    with open(
        analysis_path,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "cycle",
            "step",
            "capture_step_index",

            "ccr_target",
            "ccr_current",

            "zc_duration_us",

            "delay_target_us",
            "delay_current_us",

            "total_step_us",

            "zc_position_percent",

            "delta_zc_prev_us",
            "delta_zc_same_us",

            "delta_total_prev_us",
            "delta_total_same_us",
            "delta_total_avg_us",

            "raw_sample_count"
        ])

        for r in capture_manager.step_results:

            writer.writerow([
                r.cycle,
                r.step,
                r.capture_step_index,

                r.ccr_target,
                r.ccr_current,

                r.zc_duration,

                r.delay_target,
                r.delay_current,

                r.total_step,

                f"{r.zc_position:.3f}",

                csv_number(r.delta_zc_prev),
                csv_number(r.delta_zc_same),

                csv_number(r.delta_total_prev),
                csv_number(r.delta_total_same),
                csv_number(r.delta_total_avg),

                r.sample_count
            ])

    return raw_path, analysis_path


def csv_number(value):

    if value != value:  # NaN
        return ""

    return f"{value:.3f}"


# ============================================================
# GUI
# ============================================================

class BLDCLoggerApp:

    def __init__(self, root):

        self.root = root

        self.root.title("BLDC 100-Cycle Capture Analyzer")
        self.root.geometry("620x570")

        # Serial
        self.ser = None
        self.receiver = None

        self.rx_queue = queue.Queue()
        self.status_queue = queue.Queue()

        # Capture
        self.capture = CaptureManager()
        self.capture.capture_complete_callback = (
            self.on_capture_complete_from_worker
        )

        self.capture_complete_pending = False

        # packet rate 계산
        self.packet_counter = 0
        self.last_rate_time = time.time()
        self.packet_rate = 0.0

        self.latest_packet = None

        self.build_gui()

        self.refresh_ports()

        # Keyboard
        self.root.bind("<space>", self.on_space)

        # GUI polling
        self.root.after(5, self.process_queues)

    # ========================================================
    # GUI 생성
    # ========================================================

    def build_gui(self):

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        # ----------------------------------------------------
        # Connection
        # ----------------------------------------------------

        connection_frame = ttk.LabelFrame(
            main,
            text="USB Connection",
            padding=10
        )

        connection_frame.pack(fill="x")

        ttk.Label(
            connection_frame,
            text="COM Port:"
        ).grid(row=0, column=0, padx=5)

        self.port_combo = ttk.Combobox(
            connection_frame,
            width=15,
            state="readonly"
        )

        self.port_combo.grid(
            row=0,
            column=1,
            padx=5
        )

        ttk.Button(
            connection_frame,
            text="Refresh",
            command=self.refresh_ports
        ).grid(row=0, column=2, padx=5)

        self.connect_button = ttk.Button(
            connection_frame,
            text="Connect",
            command=self.toggle_connection
        )

        self.connect_button.grid(
            row=0,
            column=3,
            padx=5
        )

        # ----------------------------------------------------
        # Live Status
        # ----------------------------------------------------

        live_frame = ttk.LabelFrame(
            main,
            text="Live Status",
            padding=10
        )

        live_frame.pack(
            fill="x",
            pady=(12, 0)
        )

        self.connection_var = tk.StringVar(
            value="DISCONNECTED"
        )

        self.state_var = tk.StringVar(value="-")
        self.step_var = tk.StringVar(value="-")
        self.ccr_var = tk.StringVar(value="-")
        self.rate_var = tk.StringVar(value="0 packet/s")

        labels = [
            ("USB", self.connection_var),
            ("Motor State", self.state_var),
            ("Step", self.step_var),
            ("CCR", self.ccr_var),
            ("RX Rate", self.rate_var),
        ]

        for i, (name, variable) in enumerate(labels):

            ttk.Label(
                live_frame,
                text=name + ":",
                width=15
            ).grid(
                row=i,
                column=0,
                sticky="w"
            )

            ttk.Label(
                live_frame,
                textvariable=variable
            ).grid(
                row=i,
                column=1,
                sticky="w"
            )

        # ----------------------------------------------------
        # Capture
        # ----------------------------------------------------

        capture_frame = ttk.LabelFrame(
            main,
            text="Capture",
            padding=10
        )

        capture_frame.pack(
            fill="x",
            pady=(12, 0)
        )

        self.capture_state_var = tk.StringVar(
            value="IDLE"
        )

        ttk.Label(
            capture_frame,
            textvariable=self.capture_state_var,
            font=("Arial", 12, "bold")
        ).pack()

        self.progress = ttk.Progressbar(
            capture_frame,
            maximum=CAPTURE_STEPS,
            mode="determinate"
        )

        self.progress.pack(
            fill="x",
            pady=8
        )

        self.progress_var = tk.StringVar(
            value="0 / 600 Steps"
        )

        ttk.Label(
            capture_frame,
            textvariable=self.progress_var
        ).pack()

        self.sample_count_var = tk.StringVar(
            value="RAW Samples: 0"
        )

        ttk.Label(
            capture_frame,
            textvariable=self.sample_count_var
        ).pack()

        self.capture_button = ttk.Button(
            capture_frame,
            text="Capture 100 Cycles (SPACE)",
            command=self.start_capture
        )

        self.capture_button.pack(pady=8)

        # ----------------------------------------------------
        # Last Capture Summary
        # ----------------------------------------------------

        result_frame = ttk.LabelFrame(
            main,
            text="Last Capture",
            padding=10
        )

        result_frame.pack(
            fill="both",
            expand=True,
            pady=(12, 0)
        )

        self.result_text = tk.Text(
            result_frame,
            height=10,
            width=70
        )

        self.result_text.pack(
            fill="both",
            expand=True
        )

        self.result_text.insert(
            "end",
            "No capture yet.\n"
        )

        self.result_text.configure(state="disabled")

    # ========================================================
    # COM
    # ========================================================

    def refresh_ports(self):

        ports = [
            p.device
            for p in serial.tools.list_ports.comports()
        ]

        self.port_combo["values"] = ports

        if ports and not self.port_combo.get():
            self.port_combo.current(0)

    def toggle_connection(self):

        if self.ser and self.ser.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):

        port = self.port_combo.get()

        if not port:
            messagebox.showerror(
                "Error",
                "COM port를 선택하세요."
            )
            return

        try:

            self.ser = serial.Serial(
                port=port,
                baudrate=DEFAULT_BAUDRATE,
                timeout=0.02
            )

            self.receiver = SerialReceiver(
                self.ser,
                self.rx_queue,
                self.status_queue
            )

            self.receiver.start()

            self.connection_var.set("CONNECTED")
            self.connect_button.config(text="Disconnect")

        except Exception as e:

            messagebox.showerror(
                "Serial Error",
                str(e)
            )

    def disconnect(self):

        if self.receiver:
            self.receiver.stop()
            self.receiver = None

        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass

        self.ser = None

        self.connection_var.set("DISCONNECTED")
        self.connect_button.config(text="Connect")

    # ========================================================
    # Capture
    # ========================================================

    def on_space(self, event):

        # Space가 widget을 누르는 기본 동작을 방지
        self.start_capture()

        return "break"

    def start_capture(self):

        if not self.ser or not self.ser.is_open:

            messagebox.showwarning(
                "USB",
                "먼저 USB COM 포트에 연결하세요."
            )

            return

        if self.capture.state != CaptureManager.STATE_IDLE:

            return

        self.capture.arm()

        self.capture_state_var.set(
            "ARMED - Waiting for next Step 1"
        )

        self.progress["value"] = 0

        self.progress_var.set(
            f"0 / {CAPTURE_STEPS} Steps"
        )

        self.sample_count_var.set(
            "RAW Samples: 0"
        )

    def on_capture_complete_from_worker(self):
        """
        현재 구현에서는 CaptureManager가 GUI thread에서 처리되지만,
        이후 thread 구조를 바꿔도 안전하도록 pending flag만 사용.
        """

        self.capture_complete_pending = True

    def finish_capture_gui(self):

        self.capture_state_var.set(
            "CAPTURE COMPLETE"
        )

        self.progress["value"] = CAPTURE_STEPS

        raw_path, analysis_path = save_capture_csv(
            self.capture
        )

        self.show_capture_summary(
            raw_path,
            analysis_path
        )

    # ========================================================
    # 분석 Summary
    # ========================================================

    def show_capture_summary(
        self,
        raw_path,
        analysis_path
    ):

        results = self.capture.step_results

        if not results:
            return

        zc_positions = [
            r.zc_position
            for r in results
        ]

        totals = [
            r.total_step
            for r in results
        ]

        dzc_same = [
            abs(r.delta_zc_same)
            for r in results
            if r.delta_zc_same == r.delta_zc_same
        ]

        dtotal_same = [
            abs(r.delta_total_same)
            for r in results
            if r.delta_total_same == r.delta_total_same
        ]

        mean_zc_pos = (
            sum(zc_positions) / len(zc_positions)
        )

        mean_total = (
            sum(totals) / len(totals)
        )

        max_dzc_same = (
            max(dzc_same)
            if dzc_same else 0
        )

        max_dtotal_same = (
            max(dtotal_same)
            if dtotal_same else 0
        )

        text = (
            f"Captured Steps       : "
            f"{self.capture.completed_steps}\n"

            f"Valid ZC Steps       : "
            f"{len(results)}\n"

            f"RAW Samples          : "
            f"{len(self.capture.raw_packets)}\n\n"

            f"Mean ZC Position     : "
            f"{mean_zc_pos:.3f} %\n"

            f"Mean Total Step      : "
            f"{mean_total:.3f} us\n"

            f"Max |ΔZC Same|       : "
            f"{max_dzc_same:.3f} us\n"

            f"Max |ΔTotal Same|    : "
            f"{max_dtotal_same:.3f} us\n\n"

            f"RAW CSV:\n"
            f"{raw_path}\n\n"

            f"Analysis CSV:\n"
            f"{analysis_path}\n"
        )
        
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("end", text)
        self.result_text.configure(state="disabled")

    # ========================================================
    # Queue Polling & UI Update Loop
    # ========================================================

    def process_queues(self):
        """
        Serial 수신 스레드에서 들어오는 패킷과 상태 메시지를
        GUI 스레드에서 주기적으로 꺼내어 처리.
        """
        # 1. 상태 및 에러 큐 확인
        try:
            while True:
                msg_type, msg_val = self.status_queue.get_nowait()
                if msg_type == "serial_error":
                    messagebox.showerror("Serial Port Error", msg_val)
                    self.disconnect()
        except queue.Empty:
            pass

        # 2. 패킷 큐 처리
        packets_processed = 0
        max_batch = 1000  # 한 주기에 최대 처리할 패킷 수 (GUI 프리징 방지)

        try:
            while packets_processed < max_batch:
                packet = self.rx_queue.get_nowait()
                packets_processed += 1
                self.packet_counter += 1
                self.latest_packet = packet

                # Capture 매니저에 패킷 전달
                self.capture.process_packet(packet)

        except queue.Empty:
            pass

        # 3. 실시간 수신율(Packet Rate) 계산 (0.5초 주기 갱신)
        now = time.time()
        dt = now - self.last_rate_time
        if dt >= 0.5:
            self.packet_rate = self.packet_counter / dt
            self.rate_var.set(f"{self.packet_rate:.1f} packet/s")
            self.packet_counter = 0
            self.last_rate_time = now

        # 4. 실시간 상태 라벨 갱신
        if self.latest_packet is not None:
            p = self.latest_packet
            mode_str = "CLOSED LOOP" if p.is_closed_loop else "OPEN LOOP"
            self.state_var.set(mode_str)
            self.step_var.set(f"Step {p.step}")
            self.ccr_var.set(f"Cur: {p.ccr_current} / Tgt: {p.ccr_target}")

        # 5. 캡처 진행률 갱신
        if self.capture.state == CaptureManager.STATE_ARMED:
            self.capture_state_var.set("ARMED - Waiting for next Step 1")
            self.progress["value"] = 0
            self.progress_var.set(f"0 / {CAPTURE_STEPS} Steps")
            self.sample_count_var.set("RAW Samples: 0")

        elif self.capture.state == CaptureManager.STATE_CAPTURING:
            self.capture_state_var.set("CAPTURING...")
            self.progress["value"] = self.capture.completed_steps
            self.progress_var.set(
                f"{self.capture.completed_steps} / {CAPTURE_STEPS} Steps"
            )
            self.sample_count_var.set(
                f"RAW Samples: {len(self.capture.raw_packets)}"
            )

        # 6. 캡처 완료 처리
        if self.capture_complete_pending:
            self.capture_complete_pending = False
            self.finish_capture_gui()

        # 5ms 후 다음 폴링 스케줄링
        self.root.after(5, self.process_queues)

    def on_close(self):
        """앱 종료 시 통신 스레드 및 포트 정리"""
        if self.receiver:
            self.receiver.stop()
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.root.destroy()


# ============================================================
# 프로그램 시작점
# ============================================================

def main():
    root = tk.Tk()
    app = BLDCLoggerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()