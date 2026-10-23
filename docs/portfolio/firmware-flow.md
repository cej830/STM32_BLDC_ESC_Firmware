# ESC V1 펌웨어 동작 블록다이어그램

검토일: 2026-10-20. 기준: HEAD `3955bdf` 및 현재 작업 트리의 펌웨어 소스.
코드 구조를 설명하는 문서이며, 실기 성능이나 보호 동작 검증을 의미하지 않는다.

## 1. 전체 제어·데이터 흐름

```mermaid
flowchart TB
    BTN["사용자 버튼 / EXTI"] --> REQ["시작·정지 요청"]
    subgraph MAIN["메인 루프"]
        SVC["Service_BLDC_Run<br/>시작·정지 처리 / 오류 감시"]
        POT["Polling_Conversion_Target<br/>데드밴드 → Median → EMA<br/>목표 CCR 220~1750"]
        USB["Service_Telemetry_Run<br/>로그 묶음 전송"]
    end
    REQ --> SVC
    SVC -->|시작| START["Algo_BLDC_Startup<br/>상태 초기화 / Step 1 / CCR 220"]
    START --> T3["TIM3 ISR<br/>다음 Step / 6-step 정류"]
    T3 --> PWM["TIM1 CH1~3<br/>약 20 kHz 상보 PWM"]
    PWM --> MOTOR["게이트 드라이버 / 인버터 / 모터"]
    PWM -.-> TRIG["TIM1 CH4 / TRGO<br/>PWM 동기 샘플링"]
    TRIG --> DUAL["Dual injected simultaneous<br/>ADC1: Phase A/B/C<br/>ADC2: Shunt A/B/C"]
    MOTOR -->|상전압·Shunt 증폭 출력| DUAL
    DUAL --> ADC["ADC1 JEOC ISR<br/>ADC 소스일 때 BEMF ZC 처리"]
    ADC -->|유효 ZC / 보간·예측 시각| DELAY["ZC 간격 기반 30도 지연 계산<br/>변화량 제한 / 처리 지연 보정"]
    ADC --> SHUNT["Shunt raw 저장 / Getter<br/>ADC 모드·blanking 통과 시 갱신"]
    MOTOR -->|상전압과 Vcom 비교| COMP["외부 비교기"]
    COMP --> T2["TIM2 Input Capture ISR<br/>비교기 소스일 때 ZC 처리"]
    T2 -->|유효 ZC / 캡처 시각 보정| DELAY
    DELAY -->|다음 정류 예약| T3
    T3 -->|오픈루프: 설정 간격으로 재예약| T3
    TICK["SysTick / 약 1 ms"] --> REG["ADC1 Regular 2채널<br/>가변저항 / DMA"]
    REG --> POT
    POT -->|목표 듀티| T3
    ADC --> LOG["텔레메트리 링버퍼"]
    T2 --> LOG
    LOG --> USB
    USB --> PC["USB CDC / ESC_Monitor<br/>파형·RPM·CSV"]
    T3 -->|비교기 모드에서 감시 시작| T4["TIM4 / 300 us<br/>ZC 누락 감시"]
    T2 -->|blanking 통과 엣지에서 감시 해제| T4
    T4 -->|타임아웃| FAULT["출력 정지 / 오류 코드 / 로그"]
    ADC -->|타임아웃·검출 이상| FAULT
    T2 -->|ZC 유효성 거부| FAULT
    FAULT --> SVC
    SVC -->|정지 요청 처리| STOP["PWM 정지 / IDLE 복귀"]
```

화살표는 제어 요청 또는 데이터 흐름이다. 메인 루프는 세 서비스를 순차 실행하며 정류 계산은 인터럽트에서 수행한다.
TIM2는 1 us 타임베이스와 비교기 입력 캡처에 함께 사용된다.

## 2. 기동·운전 상태

```mermaid
flowchart TD
    IDLE["IDLE"] -->|버튼| REQUEST["START_REQUEST"]
    REQUEST --> INIT["오류 해제 / 100 ms 대기<br/>PWM 트리거 시작 / 알고리즘 초기화"]
    INIT --> OL["OPEN_LOOP<br/>CCR 220 / 강제 6-step<br/>정류 간격 10 ms → 6 ms"]
    OL -->|램프 종료| CL["CLOSE_LOOP<br/>ADC BEMF 기반 정류"]
    CL -->|Step 1 진입 100회| LOCK["CLOSE_LOCKIN"]
    LOCK --> SOURCE{"정류 경계의 CCR"}
    SOURCE -->|1300 미만| ADCMODE["ADC ZC"]
    SOURCE -->|1300 이상| COMPMODE["비교기 ZC / TIM2 캡처"]
    ADCMODE --> NEXT["ZC 기반 지연 → TIM3 → 다음 정류"]
    COMPMODE --> NEXT
    NEXT --> LOCK
    RUNSTOP["운전 중 버튼 정지 또는 오류"] --> STOP["출력 정지"]
    STOP --> IDLE
```

서비스 상태와 알고리즘 상태는 별개이다. 서비스는 기동 요청 처리 후 `MOTOR_RUN_CLOSELOOP`를 사용하지만,
알고리즘은 그동안 `OPEN_LOOP → CLOSE_LOOP → CLOSE_LOCKIN`을 진행한다.
100 ms 대기는 `Algo_BLDC_Startup()`보다 앞에 있으므로 정렬 유지 시간으로 표현하지 않았다.

## 3. CLOSE_LOCKIN에서 TIM3 ISR의 실제 순서

```mermaid
flowchart TD
    IRQ["TIM3 ISR 진입"] --> STEP["TIM3 정지 / Step 증가"]
    STEP --> SOURCE["현재 CCR로 ZC 소스 선택<br/>1300 미만 ADC / 이상 비교기"]
    SOURCE --> APPLY["sixstep에 현재 CCR 적용<br/>Step 시작 시각 기록 / ZC 탐색 준비"]
    APPLY --> WD["TIM4 정지<br/>비교기 모드이면 300 us 감시 시작"]
    WD --> SAMPLE["ADC 샘플 위치 선택<br/>CCR 900 미만: 로우사이드 플랫<br/>CCR 900 이상: 하이사이드 플랫"]
    SAMPLE --> FOLLOW["가변저항 추종 처리<br/>초기 목표값 225 이하이면 추종 허용<br/>추종 중 Step 1·ZC_VALID일 때 CCR ±1"]
    FOLLOW --> CAP["비교기 기록 초기화<br/>해당 부유상의 캡처 채널·엣지 설정"]
    CAP --> EXIT["ISR 종료 / ZC 대기"]
```

현재 CCR 증감은 매 정류가 아니라 전기 1주기의 Step 1에서 수행한다.
`sixstep()` 이후 소프트웨어 CCR을 갱신하므로 변경값은 다음 정류에서 전달된다.
CCR preload에 기록한 값은 TIM1 업데이트 이벤트에서 실제 비교값으로 반영된다.

## 4. 구현 범위와 읽을 때 주의할 점

- BEMF = 부유상 전압 − (Phase A + Phase B + Phase C) / 3.
- ADC 입력은 Phase 3채널, Shunt 3채널이며 Vcom은 ADC injected 시퀀스에 포함하지 않는다.
- ADC 검출은 30 us blanking 후 진행한다. 정상 영교차는 선형 보간하고, 이미 지나간 영교차는 이전 기록을 이용한 보완 경로가 있다.
- ADC 탐색 타임아웃은 5 ms, 비교기 감시는 TIM4의 300 us 설정이다. 후자는 MCU 독립 watchdog이 아니다.
- 비교기는 CLOSE_LOCKIN의 ADC 소스 구간에서도 캡처 자료를 얻지만, 정류 기준으로 사용하는 것은 비교기 소스 구간이다.
- Shunt 변환 하드웨어는 PWM 트리거에 연동되지만 `Update_Shunt()`는 ADC 소스·blanking 통과 뒤에만 호출된다. 비교기 소스 구간에서 Getter의 값은 최신값이 아닐 수 있다.
- Shunt 데이터는 관측·로그 용도이며, 전류 피드백 제어나 검증된 과전류 보호로 표현하지 않는다.
- RPM은 PC가 ZC 기록과 극쌍 수로 계산한다. FW는 목표 RPM 추종 제어를 수행하지 않는다.
- UART CLI 코드는 존재하지만 메인 루프 호출은 주석 처리되어 있다.

## 소스 대응

| 블록 | 파일 |
|---|---|
| 초기화·메인 루프·주변장치 설정 | `Core/Src/main.c` |
| 시작·정지 서비스 | `Core/Src/layer_2_Service/service_BLDC.c` |
| 기동·ZC 처리·CCR 추종·Shunt 저장 | `Core/Src/layer_1_Algorithm/algorithm_BLDC_Control.c` |
| 비교기 캡처 관리 | `Core/Src/layer_1_Algorithm/algorithm_Comparator.c` |
| ADC·타이머 ISR 연결 / 출력 정지 | `Core/Src/layer_0_Driver/driver_BLDC_HW.c` |
| PWM 채널 제어 | `Core/Src/layer_0_Driver/driver_GateDriver.c` |
| Regular ADC DMA | `Core/Src/layer_0_Driver/driver_ADC_Potentiometer.c` |
| 가변저항 필터 | `Core/Src/layer_1_Algorithm/algorithm_ADC_Control.c` |
| 로그 큐·USB 전송 | `Core/Src/my_Utility/utility_Log_BLDC.c` |
