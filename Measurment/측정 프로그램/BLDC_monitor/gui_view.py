import tkinter as tk
from tkinter import ttk

class DashboardView:
    def __init__(self, root):
        self.root = root
        self.root.title("BLDC Telemetry & ZC Stability Monitor")
        self.root.geometry("1060x680") # 가로 폭을 살짝 넓혀 가독성 확보

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

        # 1. 기존 50us Raw 600개 수동 캡처 버튼
        self.btn_record = ttk.Button(frame, text="● Raw 600개 캡처 (Space)", state=tk.DISABLED)
        self.btn_record.pack(side=tk.LEFT, padx=10)

        # 2. [신규] 상시 수집된 100회전(600행) 요약 즉시 추출 버튼
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
            font=("Consolas", 10, "bold")
        )
        self.lbl_stream.pack(anchor=tk.W, padx=10, pady=2)

        # CCR 표시가 포함된 상태 레이블
        self.lbl_flags = ttk.Label(
            frame, 
            text="모터 상태: CCR: [   0] | Step: [-] IDLE | ZC: [Searching] | TIM침투(9998)=0회 | 타임아웃(9999)=0회", 
            font=("Consolas", 10)
        )
        self.lbl_flags.pack(anchor=tk.W, padx=10, pady=2)

    def _build_zc_table_panel(self):
        frame = ttk.LabelFrame(self.root, text="스텝별 ZC 타이밍 분석 & 모터 위상 대칭성 (이상적 ZC위치 = 50.0%)")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 9개 컬럼으로 확장
        cols = (
            "step", "step_period", "offset_avg", "zc_duration", 
            "zc_center", "diff_us", "status", "streak", "max_risk", "reject_total"
        )
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=7)

        headers = {
            "step": "스텝",
            "step_period": "스텝 총길이",
            "offset_avg": "평균대비 편차",
            "zc_duration": "ZC발생시간",
            "zc_center": "ZC 위치(%)",
            "diff_us": "회전간 편차",
            "status": "판정",
            "streak": "연속 RISK",
            "max_risk": "최대 RISK",
            "reject_total": "총 REJECT"
        }
        
        widths = {
            "step": 75, "step_period": 95, "offset_avg": 95, "zc_duration": 95,
            "zc_center": 90, "diff_us": 90, "status": 80, "streak": 85,
            "max_risk": 85, "reject_total": 85
        }

        for c, text in headers.items():
            self.tree.heading(c, text=text)
            self.tree.column(c, anchor=tk.CENTER, width=widths[c])

        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 상태별 컬러 태그
        self.tree.tag_configure("VALID", foreground="green")
        self.tree.tag_configure("RISK", foreground="darkorange", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("REJECT", foreground="red", font=("Segoe UI", 9, "bold"))

        for s in range(1, 7):
            self.tree.insert("", tk.END, iid=str(s), values=(
                f"Step {s}", "---", "---", "---", "---", "---", "INIT", "0/5", "0", "0"
            ))

    def _build_log_console(self):
        frame = ttk.LabelFrame(self.root, text="이벤트 로그 및 단축키 안내 [Space: 캡처 트리거]")
        frame.pack(fill=tk.X, padx=10, pady=5)

        self.txt_log = tk.Text(frame, height=4, state=tk.DISABLED, bg="#F5F5F5", font=("Consolas", 9))
        self.txt_log.pack(fill=tk.X, padx=5, pady=3)

    def append_log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, f">> {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)