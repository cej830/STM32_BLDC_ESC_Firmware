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
        self.risk_streak = 0          # 연속 RISK 누적 횟수
        self.max_risk_streak = 0      # 역대 최대 연속 RISK 기록
        self.reject_count = 0         # REJECT 누적 발생 횟수

        # 스텝 전체 길이 및 센터링 관련
        self.last_t_start = None       # 스텝 시작 CNT
        self.step_period = 0           # 스텝 전체 길이 (다음 스텝 시작 - 이번 스텝 시작)
        self.zc_pos_pct = 50.0         # ZC 발생 위치 백분율 (duration / step_period * 100)
        self.period_offset_us = 0      # 6개 스텝 평균 대비 편차 (us)


class ZCStabilityAnalyzer:
    def __init__(self):
        self.nodes = {s: StepNode(s) for s in range(1, 7)}
        self.last_step_num = None
        self.avg_step_period = 0.0     # 6스텝 평균 주기

    def on_step_transition(self, new_step, t_start):
        """스텝이 전환되는 순간(정류 시점), 직전 스텝의 전체 길이(step_period)를 확정"""
        if self.last_step_num is not None and 1 <= self.last_step_num <= 6:
            prev_node = self.nodes[self.last_step_num]
            if prev_node.last_t_start is not None:
                # 직전 스텝의 전체 길이 = 이번 스텝 t_start - 직전 스텝 t_start
                period = diff_u16(t_start, prev_node.last_t_start)
                # 비정상적인 값(모터 정지 등) 제외 필터링 (300us ~ 20000us)
                if 300 <= period <= 20000:
                    prev_node.step_period = period
                    
                    # ZC가 해당 스텝 전체 길이의 몇 % 지점에서 터졌는지 계산 (이상적 목표: 50.0%)
                    if prev_node.curr_duration is not None and prev_node.curr_duration > 0:
                        prev_node.zc_pos_pct = (prev_node.curr_duration / period) * 100.0

            # 6개 스텝 전체 평균 주기 계산 및 스텝별 편차 갱신
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
        # 스텝 시작 시점부터 보간 ZC 발생 시점까지 걸린 순수 시간 (us)
        duration = diff_u16(t_zc, t_start)

        if node.curr_duration is not None:
            # 1. 이전 값과 현재 값 갱신 (지연 방지를 위해 즉시 추종)
            node.prev_duration = node.curr_duration
            node.curr_duration = duration

            # 2. 순수 절대 시간 차이 계산 (나눗셈 연산 배제)
            node.diff_us = abs(node.curr_duration - node.prev_duration)

            # 3. 임계치 및 연속 초과 판정 로직
            if node.diff_us <= config.LIMIT_US_VALID:
                # [정상 범위: VALID]
                node.status = "VALID"
                node.risk_streak = 0

            elif node.diff_us <= config.LIMIT_US_RISK:
                # [주의 범위: RISK]
                node.status = "RISK"
                node.risk_streak += 1
                if node.risk_streak > node.max_risk_streak:
                    node.max_risk_streak = node.risk_streak

                # 설정된 config.REJECT_COUNT(예: 5) 이상 연속 발생했는지 검사
                if node.risk_streak >= config.REJECT_COUNT:
                    node.status = "REJECT"
                    node.reject_count += 1
                    node.risk_streak = 0  # 다음 판정을 위해 streak 리셋
                else:
                    node.status = "RISK"

            else:
                # [LIMIT_US_RISK 초과: 극단적 편차]
                # 극단적인 노이즈/탈조 조짐도 즉시 셧다운하지 않고 streak에 가산
                node.risk_streak += 1
                if node.risk_streak > node.max_risk_streak:
                    node.max_risk_streak = node.risk_streak

                if node.risk_streak >= config.REJECT_COUNT:
                    node.status = "REJECT"
                    node.reject_count += 1
                    node.risk_streak = 0
                else:
                    node.status = "RISK"

        else:
            # 최초 실행 동기화
            node.curr_duration = duration
            node.status = "SYNCING"

        return {
            "step": step,
            "zc_duration": duration,
            "prev_duration": node.prev_duration,
            "diff_us": node.diff_us,
            "diff_pct": 0.0,
            "status": node.status,
            "risk_streak": node.risk_streak,
            "max_risk_streak": node.max_risk_streak,
            "reject_count": node.reject_count
        }