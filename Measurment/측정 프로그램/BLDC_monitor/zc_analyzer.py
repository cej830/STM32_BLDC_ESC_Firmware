import config

def diff_u16(curr, prev):
    """16비트 오버플로우/언더플로우 보정 (curr - prev)"""
    return (curr - prev) & 0xFFFF

class StepNode:
    def __init__(self, step_id):
        self.step_id = step_id
        self.prev_duration = None     # 1회전 전(360도 전) 동일 스텝의 duration
        self.curr_duration = None     # 이번 회전 동일 스텝의 duration
        self.diff_us = 0              # 순수 시간 편차 (us)
        self.status = "INIT"          # VALID / RISK / REJECT / SYNCING

        # 스텝 전체 길이 및 센터링 관련
        self.last_t_start = None       # 스텝 시작 CNT
        self.step_period = 0           # 스텝 전체 길이
        self.zc_pos_pct = 50.0         # ZC 발생 위치 백분율 (duration / step_period * 100)
        self.period_offset_us = 0      # 6개 스텝 평균 대비 편차 (us)

class ZCStabilityAnalyzer:
    def __init__(self):
        self.nodes = {s: StepNode(s) for s in range(1, 7)}
        self.last_step_num = None
        self.avg_step_period = 0.0

        # [신규] 모든 스텝이 공유하는 단일 글로벌 리스크 카운터
        self.global_risk_streak = 0
        self.global_max_risk_streak = 0
        self.global_reject_count = 0

        # [1사이클 ZC-to-ZC 추적 변수]
        self.last_cycle_t_zc = None
        self.cycle_zc_period_us = 0
        self.e_rpm = 0.0
        self.m_rpm = 0.0

    def on_step_transition(self, new_step, t_start):
        """스텝 전환 시 이전 스텝 길이 및 6스텝 평균 계산"""
        if self.last_step_num is not None and 1 <= self.last_step_num <= 6:
            prev_node = self.nodes[self.last_step_num]
            if prev_node.last_t_start is not None:
                period = diff_u16(t_start, prev_node.last_t_start)
                if 200 <= period <= 30000:
                    prev_node.step_period = period
                    if prev_node.curr_duration is not None and prev_node.curr_duration > 0:
                        prev_node.zc_pos_pct = (prev_node.curr_duration / period) * 100.0

            valid_periods = [self.nodes[s].step_period for s in range(1, 7) if self.nodes[s].step_period > 0]
            if len(valid_periods) == 6:
                self.avg_step_period = sum(valid_periods) / 6.0
                for s in range(1, 7):
                    self.nodes[s].period_offset_us = int(self.nodes[s].step_period - self.avg_step_period)

        self.last_step_num = new_step
        if 1 <= new_step <= 6:
            self.nodes[new_step].last_t_start = t_start

    def evaluate(self, step, t_start, t_zc):
        if not (1 <= step <= 6):
            return None

        node = self.nodes[step]
        duration = diff_u16(t_zc, t_start)

        if step == 1:
            if self.last_cycle_t_zc is not None:
                # 360도 전기각 1회전 순수 ZC 시간 (16비트 롤오버 보정)
                self.cycle_zc_period_us = diff_u16(t_zc, self.last_cycle_t_zc)

                # [수정] 최소 주기를 1000 -> 100으로 변경 (최대 600,000 E-RPM / 약 85,000 M-RPM까지 커버)
                if 100 <= self.cycle_zc_period_us <= 60000:
                    # 1. 순수 1사이클 ZC 기반 E-RPM
                    self.e_rpm = 60000000.0 / self.cycle_zc_period_us

                    # 2. 극쌍 수(config.MOTOR_POLE_PAIRS = 7)를 반영한 기계적 M-RPM
                    self.m_rpm = self.e_rpm / config.MOTOR_POLE_PAIRS

            self.last_cycle_t_zc = t_zc

        # 스텝별 stability 판정 및 글로벌 리스크 누적
        if node.curr_duration is not None:
            node.prev_duration = node.curr_duration
            node.curr_duration = duration
            node.diff_us = abs(node.curr_duration - node.prev_duration)

            if node.diff_us <= config.LIMIT_US_VALID:
                node.status = "VALID"
                # 정상 통과 시 글로벌 연속 리스크 즉시 초기화
                self.global_risk_streak = 0
            else:
                # LIMIT_US_VALID 초과 시 RISK 판정
                node.status = "RISK"
                self.global_risk_streak += 1

                if self.global_risk_streak > self.global_max_risk_streak:
                    self.global_max_risk_streak = self.global_risk_streak

                # 글로벌 연속 리스크가 REJECT_COUNT에 도달하면 REJECT 처리
                if self.global_risk_streak >= config.REJECT_COUNT:
                    node.status = "REJECT"
                    self.global_reject_count += 1
                    self.global_risk_streak = 0
        else:
            node.curr_duration = duration
            node.status = "SYNCING"

        return {
            "step": step,
            "zc_duration": duration,
            "prev_duration": node.prev_duration,
            "diff_us": node.diff_us,
            "status": node.status,
            "global_risk_streak": self.global_risk_streak,
            "global_max_risk_streak": self.global_max_risk_streak,
            "global_reject_count": self.global_reject_count
        }