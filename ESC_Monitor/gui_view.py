import tkinter as tk
from tkinter import ttk

class DashboardView:
    def __init__(self, root):
        self.root = root
        self.root.title("BLDC Telemetry & ZC Stability Monitor")
        self.root.geometry("1400x900")

        style = ttk.Style(root)
        style.configure(".", font=("맑은 고딕", 11))
        style.configure("Treeview", font=("맑은 고딕", 12), rowheight=34)
        style.configure("Treeview.Heading", font=("맑은 고딕", 11, "bold"))
        self._build_top_panel()
        self._build_stream_status_panel()
        self._build_zc_table_panel()
        self._build_log_console()

    def _build_top_panel(self):
        frame = ttk.LabelFrame(self.root, text="통신 및 캡처 제어")
        frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame, text="Port:").pack(side=tk.LEFT, padx=5)
        self.ent_port = ttk.Entry(frame, width=8)
        self.ent_port.insert(0, "COM4")
        self.ent_port.pack(side=tk.LEFT, padx=5)

        self.btn_connect = ttk.Button(frame, text="연결")
        self.btn_connect.pack(side=tk.LEFT, padx=5)

        self.btn_record = ttk.Button(frame, text="● Raw 600개 캡처 (Space)", state=tk.DISABLED)
        self.btn_record.pack(side=tk.LEFT, padx=10)

        self.btn_save_seq = ttk.Button(frame, text="💾 100회전 시퀀스 로그 저장", state=tk.DISABLED)
        self.btn_save_seq.pack(side=tk.LEFT, padx=10)

        self.lbl_rec_mode = ttk.Label(frame, text="대기 중", foreground="gray")
        self.lbl_rec_mode.pack(side=tk.LEFT, padx=5)

    def _build_stream_status_panel(self):
        frame = ttk.LabelFrame(self.root, text="스트림 통계 및 실시간 모터 상태")
        frame.pack(fill=tk.X, padx=10, pady=5)

        self.lbl_stream = ttk.Label(
            frame,
            text="수신: 0개 | 전체 유실률: 0.00% (OL: 0.00% / CL: 0.00%) | 평균 dt: 0.0us | 스텝에러: 0",
            font=("맑은 고딕", 12, "bold")
        )
        self.lbl_stream.pack(anchor=tk.W, padx=10, pady=2)

        self.lbl_source = ttk.Label(frame, text="검출 경로: 수신 대기", font=("맑은 고딕", 16, "bold"))
        self.lbl_source.pack(anchor=tk.W, padx=10, pady=6)

        # 모터 상태 및 MCU 에러/트리거 플래그 통합 모니터
        self.lbl_flags = ttk.Label(
            frame,
            text="모터 상태: CCR: [   0] | Step: [-] IDLE | ZC: [NOT_YET] | 타임아웃(9999)=0 | 강제정지(9997/9996)=0/0",
            font=("맑은 고딕", 12)
        )
        self.lbl_flags.configure(justify=tk.LEFT)
        self.lbl_flags.pack(anchor=tk.W, padx=10, pady=4)

        self.lbl_shunt = ttk.Label(
            frame,
            text="Shunt (raw uint16): A: --- | B: --- | C: ---",
            font=("맑은 고딕", 12)
        )
        self.lbl_shunt.pack(anchor=tk.W, padx=10, pady=2)

        self.lbl_current = ttk.Label(
            frame, text="듀티: --- % | 최신 ADC 전류 추정: --- A", justify=tk.LEFT,
            font=("맑은 고딕", 12, "bold")
        )
        self.lbl_current.pack(anchor=tk.W, padx=10, pady=2)

        # 리스크 모니터 및 ALREADY 카운트 전용 서브 프레임
        sub_frame = ttk.Frame(frame)
        sub_frame.pack(fill=tk.X, padx=10, pady=2)

        self.lbl_global_risk = ttk.Label(
            sub_frame,
            text="PC 타이밍 진단: 연속 RISK: [ 0/8] | 역대 최대 연속 RISK: [ 0] | 총 REJECT: [0회]",
            font=("맑은 고딕", 12, "bold"),
            foreground="blue"
        )
        self.lbl_global_risk.pack(side=tk.LEFT)

        diag_frame = ttk.Frame(frame)
        diag_frame.pack(fill=tk.X, padx=10, pady=2)

        self.lbl_zc_quality = ttk.Label(
            diag_frame,
            text="ESC 센싱 진단: 평가수: 0회 | 정상 검출(DETECT): 0.0% | 조기 교차(ALREADY): 0.0% | 데드밴드(PASS): 0.0%",
            font=("맑은 고딕", 12, "bold"),
            foreground="#8A2BE2"
        )
        self.lbl_zc_quality.pack(side=tk.LEFT)

        self.btn_reset_quality = ttk.Button(diag_frame, text="비율 초기화")
        self.btn_reset_quality.pack(side=tk.LEFT, padx=10)

        self.lbl_already = ttk.Label(
            sub_frame,
            text=" |  ALREADY 발생: 0회",
            font=("맑은 고딕", 12, "bold"),
            foreground="#D9534F"
        )
        self.lbl_already.pack(side=tk.LEFT, padx=5)

        self.btn_reset_already = ttk.Button(sub_frame, text="초기화")
        self.btn_reset_already.pack(side=tk.LEFT, padx=5)

    def _build_zc_table_panel(self):
        frame = ttk.LabelFrame(self.root, text="스텝별 ZC 타이밍 · 현재 검출 경로의 데이터 (us)")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = (
            "step", "step_period", "zc_duration", "zc_center",
            "ts_zc_adc", "ts_tim_comp", "err_comp", "cnt_ic", "status"
        )
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=7)

        headers = {
            "step": "스텝",
            "step_period": "스텝 총길이",
            "zc_duration": "ZC 발생시간",
            "zc_center": "ZC 위치(%)",
            "ts_zc_adc": "ZC 시각",
            "ts_tim_comp": "비교기 ts_tim",
            "err_comp": "ADC−COMP (us)",
            "cnt_ic": "비교기 엣지수",
            "status": "판정"
        }

        widths = {
            "step": 75, "step_period": 110, "zc_duration": 110, "zc_center": 95,
            "ts_zc_adc": 115, "ts_tim_comp": 115, "err_comp": 135, "cnt_ic": 95, "status": 90
        }

        for c, text in headers.items():
            self.tree.heading(c, text=text)
            self.tree.column(c, anchor=tk.CENTER, width=widths[c])

        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tree.tag_configure("VALID", foreground="green")
        self.tree.tag_configure("RISK", foreground="darkorange", font=("맑은 고딕", 12, "bold"))
        self.tree.tag_configure("REJECT", foreground="red", font=("맑은 고딕", 12, "bold"))

        for s in range(1, 7):
            self.tree.insert("", tk.END, iid=str(s), values=(
                f"Step {s}", "---", "---", "---", "---", "---", "---", 0, "INIT"
            ))

    def _build_log_console(self):
        frame = ttk.LabelFrame(self.root, text="이벤트 로그 및 단축키 안내 [Space: 캡처 트리거]")
        frame.pack(fill=tk.X, padx=10, pady=5)

        self.txt_log = tk.Text(frame, height=4, state=tk.DISABLED, bg="#F5F5F5", font=("맑은 고딕", 11))
        self.txt_log.pack(fill=tk.X, padx=5, pady=3)

    def append_log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, f">> {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)
