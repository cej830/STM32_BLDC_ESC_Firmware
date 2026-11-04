# 하드웨어·펌웨어 구조

STM32F103C8T6 기반 센서리스 BLDC ESC의 회로 구성, 주변장치 역할 및 제어 흐름을 정리한 문서다. 회로·4층 PCB와 C 기반 펌웨어를 구현하고, 12V에서 A2212/13T 1000kV 모터의 무부하 구동을 확인했다.

[프로젝트 개요·시험 결과](../../README.md)
## 하드웨어 구성

12V 입력으로 모터 구동부와 제어부에 전원을 공급한다. 제어부는 Buck 컨버터로 5V를 생성하고 LDO로 3.3V를 공급한다. 다이오드 OR 회로로 외부 5V 입력 경로를 구성했으며, USB 전원만으로 모터를 구동하지는 않는다.

| 블록 / 회로도 | 구성 및 역할 |
| --- | --- |
| Power · `power_block.kicad_sch` | 12V→5V Buck, 다이오드 OR, 3.3V LDO |
| MCU · `mcu_block.kicad_sch` | STM32F103C8T6 전원·클럭·리셋 및 주변 연결 |
| Inverter · `inverter_block.kicad_sch` | DRV8300, MOSFET 6개, 3상 출력 및 로우사이드 션트 |
| Sensing · `sensing_block.kicad_sch` | TLV3202 기반 BEMF 비교기, INA180A3 기반 션트 증폭 |
| Interface · `interface_block.kicad_sch` | 가변저항 및 스위치 입력 |
| Communication · `comm_block.kicad_sch` | USB·UART 인터페이스 및 관련 보호 회로 |

PCB는 1.6mm 두께의 4층 구조로 F.Cu, In1.Cu, In2.Cu, B.Cu를 사용했다. 회로·BOM 작성, 부품 배치·배선 및 bring-up을 직접 수행했으며, SMT 조립은 외주 제작했다.

[최상위 회로도](../../Images/SVG/STM32_ESC_HW.svg) · [Front 레이아웃](../../Images/PCB/front.PNG) · [Back 레이아웃](../../Images/PCB/back.PNG) · [조립 보드](../../Images/PCB/PCB3.jpg)

실물에는 USB 풀업 제어 MOSFET 제거·배선 패치와 Vcom 비교기 입력 커패시터 제거를 적용했다.

## 펌웨어 계층

C, STM32 HAL 및 레지스터 제어를 사용했다. 서비스 계층은 사용자 요청을 처리하고, 제어 알고리즘은 인터럽트에서 취득한 신호와 시간을 바탕으로 정류를 수행한다.

| 계층 | 주요 역할 | 소스 위치 |
| --- | --- | --- |
| Service | 시작·정지 요청 및 구동 서비스 관리 | [layer_2_Service](../../Core/Src/layer_2_Service) |
| Algorithm | 기동, 상태 전환, BEMF ZC 검출, 정류 시점 계산 | [layer_1_Algorithm](../../Core/Src/layer_1_Algorithm) |
| Driver | PWM 출력, ADC 취득, 타이머·비교기 입력 접근 | [layer_0_Driver](../../Core/Src/layer_0_Driver) |
| Utility | 텔레메트리 패킷, 링버퍼 및 USB 전송 | [my_Utility](../../Core/Src/my_Utility) |

### 주변장치 역할

| 주변장치 | 역할 |
| --- | --- |
| TIM1 | 3상 상보 PWM 출력. Center-aligned, PSC=0, ARR=1800. CH4 OC4REF를 ADC 트리거로 사용 |
| ADC1 | Injected conversion으로 상전압 A/B/C 취득 |
| ADC2 | Injected conversion으로 션트 A/B/C 취득. ADC1과 dual injected simultaneous 구성 |
| TIM2 | 외부 비교기 출력의 input capture 및 시간 기준. 카운터 단위 1µs |
| TIM3 | 계산한 지연 후 다음 정류 실행 |
| TIM4 | 비교기 경로의 ZC 검출 감시용 타이머 |
| USB CDC | 메인 루프에서 텔레메트리 배치 전송 |

TIM1 클럭 72MHz와 위 설정으로 계산한 PWM 주파수는 20kHz다. PWM 주파수와 USB 로그 전송률은 구분한다.

## 센서리스 제어 흐름

<p align="center">
  <img src="../../Images/Firmware/Senserless%20flow.drawio.svg" width="600" alt="센서리스 제어 흐름도">
</p>

### 기동 및 상태 전환

1. 시작 요청에 따라 구동부 초기화와 모터 정렬을 수행한다.
2. `OPEN_LOOP`에서 정해진 간격으로 six-step 정류를 진행한다.
3. 정류 간격을 10,000µs에서 6,000µs까지 줄인 뒤 `CLOSE_LOOP`로 전환한다.
4. `CLOSE_LOOP`의 사이클 카운터가 100에 도달하면 `CLOSE_LOCKIN`으로 전환한다.
5. `CLOSE_LOCKIN`에서는 CCR에 따라 ADC 또는 비교기 ZC 경로를 선택한다.


### Six-step 정류표

| Step | PWM 공급 상 | 로우사이드 귀환 상 | 플로팅 상 / BEMF 관측 상 |
| --- | --- | --- | --- |
| 1 | A | B | C |
| 2 | A | C | B |
| 3 | B | C | A |
| 4 | B | A | C |
| 5 | C | A | B |
| 6 | C | B | A |

`sixstep()`에서 각 상의 CCR과 출력 활성 상태를 갱신한다. 플로팅 상은 메인·상보 출력을 모두 비활성화한다.

### ADC 및 비교기 ZC 검출

**ADC 경로:** PWM에 동기화해 상전압을 취득하고 swBEMF를 계산한다. 정류 직후 blanking 구간을 제외한 샘플에서 ZC를 판정하고, 샘플 사이의 ZC 시각을 선형보간으로 추정한다.

**비교기 경로:** 플로팅 상과 Vcom의 비교 결과를 TIM2 input capture로 취득한다. 스텝에 따라 캡처 채널과 상승·하강 에지를 선택한다.

두 경로는 검출한 ZC 시각을 바탕으로 다음 정류 지연을 계산하고 TIM3를 설정한다. 타이머 이벤트가 발생하면 다음 six-step 출력을 적용한다.

| 구분 | 현재 구현값 |
| --- | --- |
| ADC 샘플링 위치 | CCR < 900: TIM1 CCR4=ARR−1 / CCR ≥ 900: CCR4=1 |
| `CLOSE_LOCKIN` ZC 경로 | CCR < 1300: ADC / CCR ≥ 1300: 비교기 |

경로 선택 기준은 RPM이 아닌 CCR이다. 위 임계값은 구현 설정이며, 전 운전 구간에 대한 최적값 검증은 수행하지 않았다.

## 텔레메트리 및 PC 모니터

제어 중 생성한 로그를 링버퍼에 저장하고, 메인 루프에서 USB CDC로 전송한다. PC 모니터는 패킷을 해석해 운전 데이터를 표시하고 CSV로 저장한다.

| 항목 | 구성 |
| --- | --- |
| 패킷 | `MotorTelemetry_t`, 1바이트 패킹, 총 27바이트 |
| 주요 데이터 | CCR, 스텝·운전 상태, BEMF, 타임스탬프, 정류 지연, 비교기 캡처 정보, 션트 raw 값 |
| 션트 필드 | `tail` 직전 `uint16_t shunt_A`, `shunt_B`, `shunt_C` |
| 링버퍼 | 64슬롯 중 63개 사용. 한 슬롯은 full/empty 구분용 |
| USB 전송 | 송신 가능 상태에서 최대 16패킷을 묶어 전송 |
| PC 처리 | 그래프·추정 RPM 표시, raw 및 요약 CSV 저장 |

버퍼가 가득 차면 새 로그를 저장하지 못하므로, 무손실 연속 취득을 보장하는 구조는 아니다.

### 션트 전류 환산

PC 모니터는 정류표의 로우사이드 귀환 상에 해당하는 션트 값을 선택한다. 예를 들어 Step 1에서는 B상 션트를 사용한다.

```text
I_est = (ADC_raw − ADC_offset) × 3.3 / 4095 / (0.010 × 100)
```

12비트 ADC, 기준 전압 3.3V, 션트 10mΩ, 증폭률 100배를 기준으로 환산한다. 현재 상별 오프셋 설정은 0이다. 샘플링 시점의 유효성과 기준 계측기 대비 정확도는 미검증이며, 표시값은 상전류 실측값으로 확정하지 않는다.

[PC 모니터 사용법](../../ESC_Monitor/README.md) · [패킷 해석](../../ESC_Monitor/packet_def.py) · [전류 환산](../../ESC_Monitor/current_sensing.py)

## 시험 자료 및 한계

구동 영상, PC 모니터 화면 및 저·중·고듀티의 Step 1·2 파형은 [README의 시험 결과](../../README.md#testing)에 제시했다. 오실로스코프 채널은 스텝 GPIO, 플로팅 상, Vcom, 비교기 출력으로 구성했다.

12V 무부하 조건에서 노브 조절 및 ARR=1800 / CCR=1750 구동을 확인했다. CCR/ARR 비율은 설정값이며 실제 게이트 ON 시간 측정값과 구분한다. 모터 발열과 특정 CCR의 구동음이 남아 있으며, 전류 정확도·부하 기동·장시간 운전·효율·보호 성능은 미검증이다.

## 핵심 소스

- [주변장치 초기화 및 메인 루프](../../Core/Src/main.c)
- [구동 서비스](../../Core/Src/layer_2_Service/service_BLDC.c)
- [센서리스 제어 및 six-step 정류](../../Core/Src/layer_1_Algorithm/algorithm_BLDC_Control.c)
- [비교기 처리](../../Core/Src/layer_1_Algorithm/algorithm_Comparator.c)
- [PWM·상 출력 제어](../../Core/Src/layer_0_Driver/driver_GateDriver.c)
- [ADC·타이머 하드웨어 접근](../../Core/Src/layer_0_Driver/driver_BLDC_HW.c)
- [텔레메트리 구조체](../../Core/Inc/my_Utility/utility_Log_BLDC.h)
- [로그 큐·USB 전송](../../Core/Src/my_Utility/utility_Log_BLDC.c)
