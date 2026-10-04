import tkinter as tk
from tkinter import messagebox

import config
from telemetry_engine import TelemetryEngine
from gui_view import DashboardView

class BLDCApp:
    def __init__(self, root):
        self.root = root
        self.view = DashboardView(root)
        self.engine = TelemetryEngine()

        self.view.btn_connect.config(command=self._on_connect_clicked)
        self.view.btn_record.config(command=self._on_record_clicked)
        self.root.bind("<space>", lambda e: self._on_record_clicked())

        self.view.btn_save_seq.config(command=self._on_save_sequence_clicked)
        self.engine.on_saved_callback = self._on_csv_saved

        self.view.btn_reset_already.config(command=self._on_reset_already_clicked)

        self.view.btn_reset_quality.config(command=self._on_reset_quality_clicked)

        self._schedule_refresh()

    def _on_reset_quality_clicked(self):
        self.engine.reset_zc_quality_stats()
        self.view.append_log("ZC 이벤트 비율 통계가 초기화되었습니다.")
    
    
    def _on_reset_already_clicked(self):
        self.engine.reset_already_count()
        self.view.append_log("ALREADY 카운터가 0으로 초기화되었습니다.")

    def _on_save_sequence_clicked(self):
        if not self.engine.is_running:
            return
        fname = self.engine.export_sequence_csv()
        if fname:
            self.view.append_log(f"100회전 시퀀스 요약본 저장 완료: {fname}")
        else:
            self.view.append_log("아직 수집된 클로즈루프 시퀀스 데이터가 부족합니다.")

    def _on_connect_clicked(self):
        if not self.engine.is_running:
            port = self.view.ent_port.get().strip()
            ok, msg = self.engine.connect(port)
            if ok:
                self.view.btn_connect.config(text="연결 해제")
                self.view.btn_record.config(state=tk.NORMAL)
                self.view.btn_save_seq.config(state=tk.NORMAL)
                self.view.append_log(f"[{port}] 시리얼 스트림 수신 시작")
            else:
                messagebox.showerror("오류", f"포트 열기 실패: {msg}")
        else:
            self.engine.disconnect()
            self.view.btn_connect.config(text="연결")
            self.view.btn_record.config(state=tk.DISABLED)
            self.view.btn_save_seq.config(state=tk.DISABLED)
            self.view.lbl_rec_mode.config(text="대기 중", foreground="gray")
            self.view.append_log("연결 해제됨")

    def _on_record_clicked(self):
        if not self.engine.is_running:
            return

        if not self.engine.is_recording:
            self.engine.set_recording(True)
            self.view.btn_record.config(text="■ 캡처 중지 및 저장")
            self.view.lbl_rec_mode.config(text="● REC 수집 중 (최신 600개 유지)", foreground="red")
            self.view.append_log("롤링 캡처 시작 (최대 600개 유지 중...)")
        else:
            self.engine.set_recording(False)
            self.view.btn_record.config(text="● 롤링 캡처 시작 (최신 600개)")
            self.view.lbl_rec_mode.config(text="저장 중...", foreground="blue")
            self.engine.export_raw_csv(reason="MANUAL_STOP")

    def _on_csv_saved(self, filepath, count, reason):
        self.view.btn_record.config(text="● 롤링 캡처 시작 (최신 600개)")
        self.view.lbl_rec_mode.config(text="대기 중", foreground="gray")
        self.view.append_log(f"[{reason}] CSV 저장 완료: {filepath} ({count}개 샘플)")

    def _schedule_refresh(self):
        self._update_ui_state()
        self.root.after(config.GUI_REFRESH_INTERVAL_MS, self._schedule_refresh)

    def _update_ui_state(self):
        if not self.engine.is_running:
            return

        s = self.engine.stats
        tot = s["total_recv"] + s["lost_total"]
        loss_all = (s["lost_total"] / tot * 100.0) if tot > 0 else 0.0

        ol_tot = s["recv_ol"] + s["lost_ol"]
        cl_tot = s["recv_cl"] + s["lost_cl"]
        loss_ol = (s["lost_ol"] / ol_tot * 100.0) if ol_tot > 0 else 0.0
        loss_cl = (s["lost_cl"] / cl_tot * 100.0) if cl_tot > 0 else 0.0

        curr_ccr = s.get("curr_ccr", 0)
        e_rpm = s.get("e_rpm", 0)
        m_rpm = s.get("m_rpm", 0)
        zc_cycle_us = s.get("cycle_zc_us", 0)

        al_cnt = s.get("already_count", 0)
        self.view.lbl_already.config(text=f" |  ALREADY 발생: {al_cnt:,}회")

        q = self.engine.zc_quality_stats
        p_det = q["pct_detected"]
        p_alr = q["pct_already"]
        p_pas = q["pct_pass"]
        total_eval = q["total_eval"]

        # ALREADY 비율이 30%를 넘으면 샘플링 속도 한계 경고 (빨간색)
        color = "red" if p_alr >= 30.0 else ("darkorange" if p_alr >= 10.0 else "#8A2BE2")
        self.view.lbl_zc_quality.config(
            text=f"ESC 센싱 진단: 평가수: {total_eval:,}회 | 정상(DETECT): {p_det:4.1f}% | 조기통과(ALREADY): {p_alr:4.1f}% | 데드밴드(PASS): {p_pas:4.1f}%",
            foreground=color
        )

        # 1. 스트림 유실 및 통신 현황
        self.view.lbl_stream.config(
            text=f"수신: {s['total_recv']}개 | 전체 유실률: {loss_all:4.2f}% (OL: {loss_ol:4.2f}% / CL: {loss_cl:4.2f}%) | "
                 f"평균 dt: {s['avg_dt']:4.1f}us | 스텝에러: {s['step_seq_err']}회"
        )

        # 2. 모터 제어 상태 및 트리거 현황
        self.view.lbl_flags.config(
            text=f"모터 상태: CCR:[{curr_ccr:4d}] | M-RPM:[{m_rpm:5d} RPM] (전기각 E-RPM:{e_rpm:5d}, 360°ZC:{zc_cycle_us}us) | "
                 f"Step:[{s['curr_step']}] {s['curr_mode']} [{s['curr_zc_str']}] | "
                 f"TIM침투(9998)={s['race_9998']} | 타임아웃(9999)={s['timeout_9999']} | 강제정지(9997/9996)={s['risk_force_9997']}/{s['reject_force_9996']}"
        )

        # 3. 단일 글로벌 리스크 상태
        g_streak = self.engine.analyzer.global_risk_streak
        g_max = self.engine.analyzer.global_max_risk_streak
        g_reject = self.engine.analyzer.global_reject_count
        
        streak_color = "red" if g_streak >= (config.REJECT_COUNT // 2) else ("darkorange" if g_streak > 0 else "blue")
        self.view.lbl_global_risk.config(
            text=f"탈조 방지 모니터: 연속 RISK: [{g_streak:2d}/{config.REJECT_COUNT}] | 역대 최대 연속 RISK: [{g_max:2d}] | 총 REJECT: [{g_reject}회]",
            foreground=streak_color
        )

        # 4. 스텝 1~6 테이블 갱신
        avg_p = self.engine.analyzer.avg_step_period
        for s_idx in range(1, 7):
            node = self.engine.analyzer.nodes[s_idx]
            
            period_str = f"{node.step_period} us" if node.step_period > 0 else "---"
            offset_str = f"{node.period_offset_us:+d} us" if avg_p > 0 else "---"
            dur_str = f"{node.curr_duration} us" if node.curr_duration is not None else "---"
            center_str = f"{node.zc_pos_pct:4.1f} %" if node.step_period > 0 else "---"
            diff_us_str = f"{node.diff_us} us" if node.prev_duration is not None else "---"

            self.view.tree.item(
                str(s_idx),
                values=(
                    f"Step {s_idx}",
                    period_str,
                    offset_str,
                    dur_str,
                    center_str,
                    diff_us_str,
                    node.status
                ),
                tags=(node.status,)
            )

if __name__ == "__main__":
    root = tk.Tk()
    app = BLDCApp(root)
    root.mainloop()