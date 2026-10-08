/*
 * algorithm_ADC_Control.h
 *
 *  Created on: 2026. 10. 5.
 *      Author: luke8
 */

#ifndef INC_LAYER_1_ALGORITHM_ALGORITHM_ADC_CONTROL_H_
#define INC_LAYER_1_ALGORITHM_ALGORITHM_ADC_CONTROL_H_

#include <layer_0_Driver/driver_ADC_Potentiometer.h>
#include <stm32f1xx_hal.h>
#include <stdlib.h>

#define ADC_RAW_MIN      0
#define ADC_RAW_MAX      4095   // 12-bit ADC 기준 (0~4095)

#define OUT_MIN          220
#define OUT_MAX          1400

#define MEDIAN_WINDOW    5      // 스파이크 제거용 중앙값 윈도우 크기 (홀수 권장)
#define EMA_ALPHA_Q8     38     // LPF 강도 (0~256 스케일, 38은 약 0.15 비중 -> 부드러운 필터링)
#define DEADBAND         4      // 미세한 ADC 지터 무시 임계값 (0~4095 기준)

/* ADC 신호 처리 컨텍스트 구조체 */
typedef struct {
    uint16_t buffer[MEDIAN_WINDOW];
    uint8_t  buf_idx;
    uint8_t  is_filled;
    uint32_t ema_filtered_q8;   // Q8 고정소수점 누적값 (실제값 * 256)
    uint16_t last_stable_raw;   // 데드밴드 비교용 이전 값
} RobustADC_t;


void Robust_Static_Init(uint16_t initial_val);
void Polling_Conversion_Target();
uint16_t Get_Filtered_Pot_Value();

#endif /* INC_LAYER_1_ALGORITHM_ALGORITHM_ADC_CONTROL_H_ */
