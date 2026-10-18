# ESC Monitor — Shunt A/B/C 텔레메트리

기준 FW 커밋: `462d3e0`. Monitor는 아래 **27바이트** 패킷을 수신합니다.
현재 기준 커밋의 FW는 21바이트이므로, IDE에서 FW를 수정·빌드·다운로드한 뒤 사용하세요.
기존 21바이트 패킷 자동 인식은 지원하지 않습니다.

## FW 패킷 배치

`MotorTelemetry_t`의 기존 필드 순서와 `#pragma pack(push, 1)`을 유지하고,
`cnt_ic` 다음, `tail` 바로 앞에 다음 필드를 추가합니다.

```c
uint16_t shunt_a;
uint16_t shunt_b;
uint16_t shunt_c;
uint8_t  tail;
```

`Packing_Motor_Log()`에서도 각 필드에 원하는 시점의 shunt 측정값을 대입해야 합니다.
이 변경에서는 FW 소스를 수정하지 않았습니다.

| 바이트 오프셋 | 필드 | 형식 |
| --- | --- | --- |
| 0 | header (0xAA) | uint8_t |
| 1–2 | ccr_current | uint16_t |
| 3 | info | uint8_t |
| 4–5 | BEMF_curr | int16_t |
| 6–7 | timestamp_start | uint16_t |
| 8–9 | timestamp_curr | uint16_t |
| 10–11 | timestamp_zc | uint16_t |
| 12–13 | delay_limited | uint16_t |
| 14–15 | delay_trigger | uint16_t |
| 16 | delay_PAR | uint8_t |
| 17–18 | ts_tim | uint16_t |
| 19 | cnt_ic | uint8_t |
| 20–21 | shunt_a | uint16_t |
| 22–23 | shunt_b | uint16_t |
| 24–25 | shunt_c | uint16_t |
| 26 | tail (0xBB) | uint8_t |

다중 바이트 값은 little-endian이며 패딩이 없습니다. C 필드 이름은 달라도
타입·순서·크기가 일치해야 합니다. `sizeof(MotorTelemetry_t)`는 27이어야 합니다.

## 표시 및 저장

- 화면: 가장 최근 수신한 A/B/C 원시값과 선택한 로우사이드 상의 전류 추정값(A), 통전 경로를 표시합니다.
- RAW CSV: 캡처 중 수신한 각 샘플에 `shunt_a`, `shunt_b`, `shunt_c`를 저장합니다.
- 시퀀스 CSV: 기존 ZC 평가 조건을 만족한 샘플의 A/B/C를 저장합니다. 평균이나 피크값이 아닙니다.
- CSV는 실행 위치의 `captures` 폴더에 저장됩니다.

실행: pyserial과 Tkinter가 설치된 Python에서 `python ESC_Monitor/main.py`.
검증: `python -m unittest discover -s ESC_Monitor -p "test_*.py"`.

## 로우사이드 전류 환산

사용자 확인 기준: ADC 12비트(0–4095), 기준 전압 3.3V, 무전류 출력 약 0V,
shunt 저항 0.010Ω / 2W, 증폭기 gain 100.
패킷의 uint16_t는 운반용 타입이며 ADC 해상도가 16비트라는 의미는 아닙니다.

`I[A] = (raw - zero_adc) × 3.3 / 4095 / (100 × 0.010)`

여기서는 0–4095를 0–3.3V로 대응시키는 끝점 기준 환산을 사용합니다.
증폭 출력 1V ≈ 1A, 1 ADC count ≈ 0.806mA입니다.
12V 전원 전압과 저항의 2W 정격은 이 환산식에 들어가지 않습니다.
실제 기준 전압과 상별 무전류 오프셋은 `config.py`의 `CURRENT_ADC_VREF_V`,
`SHUNT_ZERO_ADC`에서 보정할 수 있습니다.

| Step | PWM 공급 상 | 측정할 로우사이드 shunt |
| --- | --- | --- |
| 1 | A | B |
| 2 | A | C |
| 3 | B | C |
| 4 | B | A |
| 5 | C | A |
| 6 | C | B |

매핑은 FW의 `sixstep()`과 일치합니다. GUI 경로는 이 스텝의 구동 명령을 나타내며,
PWM OFF 재순환 구간을 포함한 실제 순간 스위치 상태를 재구성한 것은 아닙니다.

RAW/시퀀스 CSV에 `drive_phase`, `low_side_phase`, `current_raw`,
`shunt_amp_voltage_v`(증폭 출력 전압), `current_a`, `current_status`가 추가됩니다.
RAW는 각 수신 샘플, 시퀀스는 기존 ZC 평가 샘플 기준이며, 평균/RMS/전원 입력 전류가 아닙니다.
GUI는 100ms마다 최신 샘플을 표시하므로 빠른 스텝별 변화는 RAW CSV에서 확인하세요.

`ESTIMATE`는 수치 환산 가능이라는 의미이며 PWM 샘플링 타이밍 검증을 의미하지 않습니다.
ADC=0은 `ADC_LOW_RAIL`, ADC=4095는 `ADC_HIGH_RAIL`로 표시합니다.
상한에서 표시되는 약 3.3A는 환산 상한이며 실제 전류가 더 클 수 있고,
증폭기 출력 한계에 따라 그 이전에도 포화될 수 있습니다.
0–4095 밖의 코드는 `ADC_OUT_OF_RANGE`, 1–6 밖의 스텝은 `INVALID_STEP`이며
전류는 GUI에서 `---`, CSV에서 빈 칸으로 남깁니다. 원시값은 보존합니다.
오프셋 보정 결과의 음수는 잘라내지 않지만 이것만으로 역전류가 확인되는 것은 아닙니다.

유효한 전류 측정에는 shunt 전류가 흐르고 증폭 출력이 안정된 시점의 ADC 샘플이 필요합니다.
패킷에는 PWM 내 샘플 위치나 측정 유효 플래그가 없어 Monitor에서 이를 검증할 수 없습니다.
FW는 A/B/C 값과 step을 같은 샘플에 대응되도록 전달해야 합니다.
참고: [ST의 low-side shunt/PWM 동기 샘플링 설명](https://www.st.com/resource/en/product_training/STM32L4_WDG_TIMERS_GPTIM.pdf).
