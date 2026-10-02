# BLDC ESC 소프트웨어·하드웨어 진행 검토

후속 검토 안내: A2212/13T 1000KV, 12V/5A 전원 제한, 2A slow-blow 조건의 추가 검토에서 PC13/PC14 LED current-source 연결 문제가 확인되었다. TVS 보호 여유는 사용자가 V1 예외로 수용했다. 최신 발주 판단은 [모터 조건별 하드웨어 재검토](</C:/Users/luke8/STM32CubeIDE/workspace_2.2.0/BLDC_ESC_Based_On_HW_Test/HARDWARE_A2212_REVIEW_2026-09-06.md>)를 우선한다.

검토일: 2026-09-06. 디스크에 저장된 현재 파일 기준이다. 소스 코드, 회로도, PCB, BOM, 기존 제조용 ZIP은 수정하지 않았다. 빌드 산출물과 검사 보고서만 생성·갱신했다. 실제 보드에 프로그램을 기록하거나 모터를 구동하지 않았다. 문서와 코드의 주석은 검토 자료로만 취급했다.

## 현재 단계

이 프로젝트는 STM32F103C8T6 기반의 12V 센서리스 BLDC 실험용 ESC이다. ADC 기반 6-step 정류, 외부 비교기 검증, 3상 전류 관찰을 한 보드에서 진행하도록 구성되어 있다.

- SW: 오픈루프 기동과 ADC 기반 폐루프 정류 구현 및 실험 로그 확보. 안정 기동·연속 운전·부하 변화 대응·보호 기능 검증은 남아 있다.
- HW: 계층 회로도, 4층 PCB 배치·배선, BOM, 제조용 Gerber/Drill ZIP까지 준비되어 있다.
- 제조 데이터의 형상 일치와 배선 규칙 검사는 양호하다. 전기적 보호 여유와 구매 부품의 실물 풋프린트 일치까지 확인된 양산 완료 상태로 판단할 근거는 없다.
- 실험 CSV가 현재 맞춤 PCB에서 측정되었다는 연결 근거, 제작·실장 완료 사진이나 검사 기록은 확인하지 못했다.

## SW 구조와 동작

| 부분 | 확인한 역할 |
|---|---|
| Core/Src/main.c | 72MHz 시스템 클럭, ADC1/2, TIM1/2/3, UART1, USB PCD 초기화와 서비스 루프 |
| layer_0_Driver | 상보 PWM 및 floating 출력 제어, ADC ISR, 정류 지연 타이머, UART, 가변저항 DMA |
| layer_1_Algorithm | 6-step 상태, 오픈루프 가속, BEMF 부호 변화 검출, ZC 후 30도 지연 계산 |
| layer_2_Service | 버튼 시작·정지, 모터 상태 머신, UART 입력·출력 |
| my_Utility | 1µs 시간 기준, 링 버퍼, 모터 로그 |
| Measurment | Python 수집 프로그램, 오픈루프·폐루프 CSV와 파형 이미지 |
| External_Comparator_Version | STM32F030C8용 별도 이전/비교용 프로젝트. 현재 F103 메인 빌드와 분리되어 있음 |

구동 순서는 IDLE → 시작 요청 → 100ms 정렬 → 오픈루프 → 폐루프 → STOP → IDLE이다. 오픈루프의 스텝 간격은 15ms에서 시작하여 전기각 3회전마다 100µs씩 줄고 8ms에서 전환한다. 현재 상수로 계산하면 오픈루프 구간은 약 14.55초이다.

TIM1은 center-aligned 20kHz 상보 PWM이며 ARR=1800, 시작 CCR=300으로 명목 듀티는 16.7%이다. ADC1 injected 4채널로 A/B/C/Vcom을 읽는다. PWM의 OC4REF를 ADC 트리거로 사용하고, 정류 후 100µs 블랭킹을 둔다. floating 상 전압에서 Vcom을 뺀 BEMF의 방향별 부호 변화로 ZC를 검출한다. TIM2는 1µs·16비트 시간 기준이고, TIM3는 다음 정류 지연에 쓰인다. 16비트 차 연산으로 단일 래핑을 처리한다.

여기서 폐루프는 BEMF에 정류 시점을 동기화한다는 의미이다. 목표 RPM을 유지하는 속도 PI 제어나 전류 제어가 완성되었다는 의미는 아니다.

### 아직 연결되지 않은 기능

- 외부 비교기: TIM2 입력 캡처와 콜백 골격은 있으나 Ready_IC_Channel(), Set_IC_Channel_Enable() 본문이 주석 처리되어 있다. 현재 정류 판단은 ADC ZC가 담당한다.
- 속도/듀티 명령: 가변저항의 DMA 수집은 있으나 target_CCR 갱신 호출이 주석 처리되어 있다. 현재 target_CCR은 300으로 유지된다.
- UART CLI: 문자 수집·에코는 있지만 명령 파싱과 제어 호출이 주석 처리되어 있다.
- 전류 센싱: ADC2 GPIO는 3상용으로 잡혀 있지만 실제 변환 설정은 채널 6 하나이고, ADC2 시작·3상 수집·전류 제한 처리를 찾지 못했다.
- USB: PCD 초기화는 있으나 USB 장치 클래스/디스크립터/CDC 서비스 구현을 찾지 못했다.
- 과전류·버스 과전압·온도 보호 및 독립 watchdog 기반 정지 처리를 찾지 못했다. TIM1 Break도 비활성이다.

### 빌드 및 로그 검증

설치된 STM32CubeIDE GNU Tools for STM32 14.3 계열과 프로젝트 Debug makefile로 증분 빌드했다. 종료 코드 0이며 미사용 Check_ZC_from_Hysteresis 경고 1건이 출력되었다. 보드 다운로드는 하지 않았다.

- text 25,088B + data 100B: 약 25.2KB Flash 사용.
- map 기준 실제 .data + .bss: 15,184B.
- 최소 heap/stack 예약 1,536B까지 포함한 RAM 배치: 16,720B / 20,480B = 약 81.6%.
- CloseLoop_LOG 하나가 13,200B를 차지한다. 향후 통신/보호 기능 확장 시 로그 용량을 먼저 검토할 필요가 있다. 정적 링크 성공만으로 실제 최대 스택 사용량까지 검증되지는 않는다.

폐루프 실험 1~8 CSV를 읽었다. 실험 6/7은 각각 600행에 ZC 표시 1회이며 최대 laptime은 29,956µs / 29,971µs이다. 코드의 30ms 타임아웃에 가까운 ZC 미검출 구간이 있다는 증거다. 실험 8에는 600행과 ZC 9회가 있다. 이 자료만으로 장시간 안정 회전을 주장할 수는 없다. 각 실험과 현재 소스의 정확한 버전 대응 관계도 명시되어 있지 않다.

### SW 수정 우선 항목

1. **전류 제한 및 독립 정지 경로.** 현재 시간 초과 검사가 ADC ISR 안에서만 동작한다. ADC 인터럽트 자체가 끊기는 상황은 이 검사만으로 다루기 어렵다. 하드웨어 전류 측정을 펌웨어와 연결하고 기동 중에도 유효한 정지 조건을 정의해야 한다.
2. **로그 버퍼와 시간 순서.** MAX_OPENLOOP_LOG=0인데 OPENLOOP_Log_Push()는 먼저 배열에 쓴다. 현재 OpenLoopflag가 0이라 실행되지 않지만, 로그 활성화 시 즉시 배열 범위를 벗어난다. 폐루프 로그도 덮어쓰기 후 항상 0번부터 출력하므로 래핑 이후 CSV 순서가 실제 시간 순서와 달라진다.
3. **ZC 견고성.** 활성 경로는 단순 부호 교차 검출이다. 히스테리시스 함수는 미사용이며 bemf 인자가 uint16_t여서 음수 첫 샘플의 초기 상태를 잘못 판별할 수 있다. 활성화 전에 int16_t 일관성과 노이즈 필터를 함께 점검해야 한다.
4. **Dead-time 설명과 설정 불일치.** 코드 주석은 2µs이나 DTG=144(0x90), CKD=1, 72MHz이면 (64+16)×2/72MHz ≈ 2.22µs이다. 원하는 실제 게이트 파형과 드라이버 지연을 기준으로 확인할 항목이다.
5. **정지 요청 상태 경쟁.** 오픈루프의 마지막 지연 중 버튼 ISR이 MOTOR_STOP을 써도 함수가 1을 반환한 뒤 main이 MOTOR_RUN_CLOSELOOP으로 덮어쓸 수 있다. 전환 전에 정지 요청을 재확인하는 방식이 필요하다.
6. **정류 순간 출력 갱신.** CCER 활성화와 CCR 쓰기가 개별 호출로 이루어진다. 프리로드 반영 시점과 재활성화 시 이전 CCR의 영향은 오실로스코프로 확인해야 한다. 이번 정적 검토로 shoot-through 발생을 확인한 것은 아니다.

근거: [제어 알고리즘](<C:/Users/luke8/STM32CubeIDE/workspace_2.2.0/BLDC_ESC_Based_On_HW_Test/Core/Src/layer_1_Algorithm/algorithm_BLDC_Control.c>), [상태 머신](<C:/Users/luke8/STM32CubeIDE/workspace_2.2.0/BLDC_ESC_Based_On_HW_Test/Core/Src/layer_2_Service/service_BLDC.c>), [로그](<C:/Users/luke8/STM32CubeIDE/workspace_2.2.0/BLDC_ESC_Based_On_HW_Test/Core/Src/my_Utility/utility_Log_BLDC.c>), [타이머 설정](<C:/Users/luke8/STM32CubeIDE/workspace_2.2.0/BLDC_ESC_Based_On_HW_Test/Core/Src/main.c:374>), [ST RM0008의 DTG 정의](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf).

## HW 구성과 SW 연결

| 블록 | 현재 설계 |
|---|---|
| 입력 전원 | 12V, F1 2A slow-blow fuse, SMBJ13A TVS, 100µF/220µF 버스 커패시터 |
| 로직 전원 | TPS560430 buck → 다이오드 OR의 +5V → TPS7A2033 3.3V LDO. USB/UART 5V 입력도 OR 구성 |
| MCU | STM32F103C8T6, 8MHz crystal, SWD, reset, BOOT0 설정 |
| 인버터 | DRV8300DPWR, IRFH7440TRPBF 6개, 게이트 저항 47Ω, bootstrap 1µF 3개 |
| BEMF | 3상 저항 분압, RC 필터, 저항 합성 Vcom, TLV3202 2개 중 3채널 |
| 전류 | 로우사이드 션트 10mΩ 3개, INA180A3 3개, 출력 RC |
| 사용자/측정 | 버튼 2개와 reset, 가변저항 2개, UART, Mini-USB, 18개 테스트 포인트 |

| 기능 | 회로도 MCU 핀 | 펌웨어 일치 |
|---|---|---|
| PWM A/B/C high | PA8 / PA9 / PA10 | 일치 |
| PWM A/B/C low | PB13 / PB14 / PB15 | 일치 |
| Phase A/B/C, Vcom | PA0 / PA1 / PA2 / PA3 | 일치 |
| 비교기 A/B/C | PA15 / PB3 / PB10 | TIM2 remap 일치, 현재 캡처 활성화 로직 비활성 |
| 션트 A/B/C | PA6 / PA7 / PB0 | 핀 지정 일치, 실측·보호 기능 미완료 |
| 가변저항 | PA4 / PA5 | DMA 수집 있음 |
| UART TX/RX | PB6 / PB7 | USART1 remap 일치 |
| 사용자 버튼 | PB11 / PB12 | 1번 시작·정지 처리, 2번 입력 설정 |
| USB D-/D+ | PA11 / PA12 | 물리 설정, 장치 스택 미완료 |

PC13은 SW에서 LED_GREEN으로 이름 붙였지만 회로도에서는 YELLOW LED이다. 기능 충돌보다는 이름 정리 항목이다. SW의 PB0/PB1 BSRR 디버그 쓰기는 남아 있으나 PB0은 실제 ADC_ShuntC이고 PB1의 출력 모드 설정은 찾지 못했다. 디버그 파형 용도로 사용하려면 보드 핀맵에 맞춰 정리해야 한다.

## PCB·ERC·DRC

현재 PCB는 외곽 중심선 기준 약 100×100mm, 4층, 1.6mm이다. gbrjob의 100.05mm 표기는 외곽 선폭을 포함한 경계로 해석된다. F.Cu/In1.Cu/In2.Cu/B.Cu 구성에 각 동박은 설정상 35µm이다. 내부층은 In1 GND, In2 +12V/+3.3V 영역이며, 외부층에 신호·전력 패턴과 폴리곤이 있다.

166 footprints, 1,538 segments, 801 vias, 29 zones를 확인했다. zones 수에는 keepout 등 구리 충진이 아닌 영역도 포함된다. 저장된 3D 이미지에는 MCU/인터페이스, 비교기, 우측 3상 전력부와 다수 측정점이 구분되어 보인다. 3D 이미지는 실물 제작 증거가 아니다.

현재 파일로 KiCad 9.0.1 검사를 다시 실행했다.

- DRC 배선 규칙 위반 0건.
- 미연결 0건.
- 회로도/PCB parity 경고 1건: TVS1. 회로도/BOM은 SMBJ13A, PCB Value는 SMBJxxA.
- ERC 오류 0건, 경고 11건: endpoint_off_grid 4건, multiple_net_names 7건.
- 프로젝트에서 footprint filter/type mismatch, 일부 courtyard 검사 등이 ignore로 설정되어 있다. 따라서 DRC 0은 현재 설정의 통과 의미이며 실장 호환성을 보증하지 않는다.
- 물리적 열 성능, 목표 전류에서의 전력 루프·그라운드 바운스, 션트 Kelvin 리턴의 오차, 스위칭 오버슈트는 실측 검증이 필요하다.

근거: [DRC](<F:/Embedded systems_study/Kicad_project/STM32_ESC_HW/review_20260906_drc.json>), [ERC](<F:/Embedded systems_study/Kicad_project/STM32_ESC_HW/final_review_erc.json>), [현재 넷리스트](<F:/Embedded systems_study/Kicad_project/STM32_ESC_HW/final_review_netlist.xml>).

## BOM 및 제조 파일

BOM CSV는 60개 그룹, 166개 reference이다. 4개 mounting hole은 제외 표기가 있어 구매/실장 대상으로는 162개다. 수량과 reference 개수 일치, reference 중복 없음, PCB에만 있거나 BOM에만 있는 reference 없음. BOM과 현재 넷리스트의 Value도 일치한다. PCB와의 Value 차이는 TVS1 하나이며 풋프린트 문자열은 전부 일치한다.

주의할 점은 '문자열 일치'와 '구매 부품의 물리적 호환'이 다르다는 것이다.

- J7: 구매 번호 U-M-M5SS-W-2와 풋프린트 이름 Lumberg_2486_01이 서로 다른 제품을 가리킨다. 호환 불가로 확정한 것은 아니지만, 제조사 도면의 신호 패드·실드 패드·위치 결정 핀을 겹쳐 확인해야 한다.
- IRFH7440는 Generic PQFN 풋프린트, DRV8300/스위치/퓨즈/인덕터/가변저항 등은 my_lib 풋프린트를 사용한다. 최종 구매 번호와 패드 도면 검증 이력을 확보하는 편이 좋다.
- J5/J6는 제조사/MPN이 비어 있다. 범용 핀헤더를 직접 조달할 경우 사양 기반 선택이 가능하지만, 구매/실장 업체 제출 시에는 실제 부품을 지정해야 한다.
- H1~H4는 제외 표기를 존중하여 구매 수량에서 제외해야 한다.
- SMBJ13A의 BOM 4kW 표기는 8/20µs 조건이다. 10/1000µs 조건은 600W이고 클램프 전압도 펄스 조건에 따라 달라진다. 파형 조건을 함께 쓰는 것이 정확하다.

최종 ZIP에는 구리 4층, 양면 mask/paste/silk, 외곽선 등 11개 거버와 PTH/NPTH drill 및 drill map이 있다. 별도 출력한 현재 PCB와 다음을 비교했다.

- 11개 거버: aperture 번호·생성시각·출력 순서를 정규화하고 draw/flash/region, aperture macro를 대조했다. 도형·좌표·개수가 일치했다.
- 드릴: G85 slot과 G00/G01 routing 표기 차이를 정규화했다. 원형 홀/슬롯 총 852개가 직경·좌표·도금 분류까지 일치했다.
- 최종 ZIP의 거버는 gerber 폴더의 개별 파일과도 일치했다.
- gerber/STM32_ESC_HW-job.gbrjob은 내부층을 L5/L7로 표기하지만 실제 거버는 L2/L3이다. gbrjob은 최종 ZIP에 없으므로 현재 ZIP 제조 데이터와 구분해야 한다. 함께 제출하려면 새로 생성해야 한다.
- 자동 실장을 위한 centroid/pick-and-place 파일은 찾지 못했다. PCB 제작 파일은 준비되어 있으나 자동 실장 발주 패키지는 추가 정리가 필요하다.

검토용 재출력 드릴은 비교 목적의 혼합 도금 파일이며, 기존의 분리된 PTH/NPTH 제조 ZIP을 대체하도록 만든 것이 아니다.

## HW 전기적 확인 우선순위

### 1. GVDD 보호 여유

넷리스트에서 DRV8300의 GVDD가 +12V 버스에 직접 연결되어 있다. DRV8300 GVDD 절대 최대는 21.5V이고, SMBJ13A는 정해진 큰 펄스 전류에서 21.5V(10/1000µs) 또는 27.2V(8/20µs)의 클램프 사양을 갖는다. 따라서 TVS가 있다는 사실만으로 GVDD 보호 여유가 확보되었다고 볼 수 없다. 실제 서지 전류·배선 인덕턴스·회생 조건에서 최대 GVDD를 측정하거나 보호 구성을 재검토해야 한다. 정상 12V 인가 자체가 최대 정격을 초과한다는 의미는 아니다.

### 2. 전류 측정 범위와 F1

10mΩ × INA180A3 gain 100 = 1V/A이다. 3.3V 공급/ADC 기준에서 이상적인 범위도 3.3A이며, 실제 선형 범위는 출력 swing 여유 때문에 그보다 작다. 이는 모터 버스 평균 전류와 동일한 값이 아니라 각 low-side shunt의 순간 측정 범위다. F1의 2A 정격과 함께 목표 모터의 기동·스톨·상전류 요구를 대조해야 한다. 2W 션트나 MOSFET 전류 정격만으로 보드 허용 전류를 결정할 수 없다.

### 3. BEMF와 전력부 실측

분압/RC/Vcom 회로와 ADC 샘플링 시점이 함께 ZC를 결정한다. 기동 전환 직후에는 작은 BEMF, RC 지연, 정류 노이즈가 크게 작용한다. 기존 로그의 ZC 미검출 구간을 기준으로 게이트 파형, floating phase, Vcom, 비교기 출력과 ADC 시점을 동시에 측정하면 원인을 좁힐 수 있다. 실제 모터 파라미터·부하·공급 조건이 없으므로 최종 blanking/필터/전류 제한값은 여기서 확정하지 않았다.

외부 근거: [TI DRV8300 데이터시트](https://www.ti.com/lit/ds/symlink/drv8300.pdf?HQS=dis-dk-null-digikeymode-dsf-pf-null-wwe&ts=1746565298242), [ST SMBJ13A 데이터시트](https://www.st.com/resource/en/datasheet/smbj13a.pdf), [TI INA180](https://www.ti.com/product/INA180), [Lumberg 2486 01 도면](https://downloads.lumberg.com/datenblaetter/en/2486_01.pdf).

## 다음 진행 순서

1. TVS1을 회로도에서 PCB로 동기화하고, GVDD 보호 여유와 J7/주요 custom 풋프린트를 검토한다.
2. 구매 BOM에서 mounting hole 제외를 반영하고 J5/J6를 지정한다. 자동 실장을 의뢰한다면 위치 파일과 조립 방향 자료를 준비한다.
3. 펌웨어의 로그 버퍼·출력 순서·정지 요청 경합을 먼저 수정하고 실험마다 코드 버전과 조건을 기록한다.
4. 3상 전류 수집과 기동/운전 중 과전류 정지를 구현한 뒤, 정렬→오픈루프→폐루프 전환을 검증한다.
5. ADC ZC와 비교기 ZC를 같은 조건에서 비교하고, 반복 기동·연속 운전·부하 변화 시험을 통해 제어 완료를 판정한다.
