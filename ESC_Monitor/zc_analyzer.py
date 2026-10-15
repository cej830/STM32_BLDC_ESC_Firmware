import config

def diff_u16(curr, prev):
    """16비트 오버플로우/언더플로우 보정 (curr - prev)"""
    return (curr - prev) & 0xFFFF

def signed_diff_u16(val_a, val_b):
    """16비트 타이머 기준 두 시점의 부호 있는 시간차 (val_a - val_b)"""
    diff = (val_a - val_b) & 0xFFFF
    if diff > 0x7FFF:
        return diff - 0x10000
    return diff

class StepNode:
    def __init__(self, step_id):
        self.step_id = step_id
        self.prev_duration = None
        self.curr_duration = None
        self.diff_us = 0
        self.status = "INIT"

        self.last_t_start = None
        self.step_period = 0
        self.zc_pos_pct = 50.0
        self.period_offset_us = 0

        # ADC 선형보간 vs 비교기 인풋캡쳐 분석 필드
        self.last_t_zc_adc = 0       # ADC 보간 ts_zc
        self.last_ts_tim = 0         # 비교기 IC ts_tim
        self.err_adc_vs_comp_us = 0  # (t_zc_adc - ts_tim) 시간차 (us)
        self.cnt_ic = 0              # 비교기 엣지 발생 횟수

class ZCStabilityAnalyzer:
    def __init__(self):
        self.nodes = {s: StepNode(s) for s in range(1, 7)}
        self.last_step_num = None
        self.avg_step_period = 0.0

        self.global_risk_streak = 0
        self.global_max_risk_streak = 0
        self.global_reject_count = 0

        self.last_cycle_t_zc = None
        self.cycle_zc_period_us = 0
        self.e_rpm = 0.0
        self.m_rpm = 0.0

    def on_step_transition(self, new_step, t_start):
        if self.last_step_num is not None and 1 <= self.last_step_num <= 6:
            prev_node = self.nodes[self.last_step_num]
            if prev_node.last_t_start is not None:
                period = diff_u16(t_start, prev_node.last_t_start)
                if 40 <= period <= 30000:
                    prev_node.step_period = period

            valid_periods = [self.nodes[s].step_period for s in range(1, 7) if self.nodes[s].step_period > 0]
            if len(valid_periods) == 6:
                self.avg_step_period = sum(valid_periods) / 6.0
                for s in range(1, 7):
                    self.nodes[s].period_offset_us = int(self.nodes[s].step_period - self.avg_step_period)

        self.last_step_num = new_step
        if 1 <= new_step <= 6:
            self.nodes[new_step].last_t_start = t_start

    def evaluate(self, step, t_start, t_zc, ts_tim, cnt_ic):
        if not (1 <= step <= 6):
            return None

        node = self.nodes[step]
        duration = diff_u16(t_zc, t_start)
        if node.step_period > 0:
            node.zc_pos_pct = (duration / node.step_period) * 100.0

        # 1. ADC 보간값 vs 비교기 인풋캡쳐 시간차 계산
        node.last_t_zc_adc = t_zc
        node.last_ts_tim = ts_tim
        node.cnt_ic = cnt_ic

        if ts_tim > 0:
            # 양수: ADC 보간 ZC가 비교기보다 늦게 검출됨 (딜레이)
            # 음수: ADC 보간 ZC가 비교기보다 일찍 검출됨
            node.err_adc_vs_comp_us = signed_diff_u16(t_zc, ts_tim)
        else:
            node.err_adc_vs_comp_us = 0

        # 2. 1회전(전기각 360도) 주기 및 RPM 산출
        if step == 1:
            if self.last_cycle_t_zc is not None:
                self.cycle_zc_period_us = diff_u16(t_zc, self.last_cycle_t_zc)
                if 100 <= self.cycle_zc_period_us <= 60000:
                    self.e_rpm = 60000000.0 / self.cycle_zc_period_us
                    self.m_rpm = self.e_rpm / config.MOTOR_POLE_PAIRS
            self.last_cycle_t_zc = t_zc

        # 3. 회전 간 안정성 판정
        if node.curr_duration is not None:
            node.prev_duration = node.curr_duration
            node.curr_duration = duration
            node.diff_us = abs(node.curr_duration - node.prev_duration)

            if node.diff_us <= config.LIMIT_US_VALID:
                node.status = "VALID"
                self.global_risk_streak = 0
            else:
                node.status = "RISK"
                self.global_risk_streak += 1
                if self.global_risk_streak > self.global_max_risk_streak:
                    self.global_max_risk_streak = self.global_risk_streak

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
            "err_adc_vs_comp_us": node.err_adc_vs_comp_us,
            "cnt_ic": cnt_ic,
            "diff_us": node.diff_us,
            "status": node.status
        }