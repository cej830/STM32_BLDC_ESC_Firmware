/*
 * algorithm_ADC_Control.c
 *
 *  Created on: 2026. 10. 5.
 *      Author: luke8
 */


#include <layer_1_Algorithm/algorithm_ADC_Control.h>



static volatile uint16_t target_value = 0;
volatile uint8_t g_adc_ready_flag = 0;

RobustADC_t robust_adc = {0};

void RobustADC_Init(RobustADC_t *inst, uint16_t initial_val);
static uint16_t GetMedian(uint16_t *buf, uint8_t size);
uint16_t RobustADC_Update(RobustADC_t *inst, int32_t raw_adc);


void Robust_Static_Init(uint16_t initial_val)
{
	RobustADC_Init(&robust_adc, initial_val);
	target_value = OUT_MIN;
}


void Polling_Conversion_Target()
{
	if(!g_adc_ready_flag) return;

	g_adc_ready_flag = 0;
	uint16_t pot_1, pot_2;
	Driver_Get_rawPot(&pot_1, &pot_2); //pot1, pot2는 ADC DMA와 SysTick ISR 에의해 일정주기로 변환됨.

	target_value = RobustADC_Update(&robust_adc, (int32_t)pot_1);
}

uint16_t Get_Target_Value()
{
	return target_value;
}


void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef* hadc)
{
	if(hadc->Instance == ADC1)
	{
		g_adc_ready_flag = 1;
	}
}

/* 컨텍스트 초기화 함수 */
void RobustADC_Init(RobustADC_t *inst, uint16_t initial_val) {
    if (initial_val > ADC_RAW_MAX) initial_val = ADC_RAW_MAX;

    for (int i = 0; i < MEDIAN_WINDOW; i++) {
        inst->buffer[i] = initial_val;
    }
    inst->buf_idx = 0;
    inst->is_filled = 1;
    inst->ema_filtered_q8 = (uint32_t)initial_val << 8;
    inst->last_stable_raw = initial_val;
}


/* 중앙값(Median) 계산을 위한 정렬 헬퍼 */
static uint16_t GetMedian(uint16_t *buf, uint8_t size) {
    uint16_t temp[MEDIAN_WINDOW];
    for (uint8_t i = 0; i < size; i++) temp[i] = buf[i];

    // 단순 삽입 정렬 (크기가 작으므로 가장 빠름)
    for (uint8_t i = 1; i < size; i++) {
        uint16_t key = temp[i];
        int8_t j = i - 1;
        while (j >= 0 && temp[j] > key) {
            temp[j + 1] = temp[j];
            j--;
        }
        temp[j + 1] = key;
    }
    return temp[size / 2];
}

/* 강인한 ADC 신호 변환 메인 함수 */
uint16_t RobustADC_Update(RobustADC_t *inst, int32_t raw_adc) {
    // 1. 하드웨어 이상값 클램핑 (0 ~ 4095)
    if (raw_adc < ADC_RAW_MIN) raw_adc = ADC_RAW_MIN;
    if (raw_adc > ADC_RAW_MAX) raw_adc = ADC_RAW_MAX;

    // 2. 미세 지터 제거 (Deadband)
    if (abs((int32_t)raw_adc - (int32_t)inst->last_stable_raw) <= DEADBAND) {
        raw_adc = inst->last_stable_raw;
    } else {
        inst->last_stable_raw = (uint16_t)raw_adc;
    }

    // 3. 스파이크 노이즈 제거 (Median Filter 버퍼 갱신)
    inst->buffer[inst->buf_idx] = (uint16_t)raw_adc;
    inst->buf_idx = (inst->buf_idx + 1) % MEDIAN_WINDOW;
    uint16_t median_val = GetMedian(inst->buffer, MEDIAN_WINDOW);

    // 4. 고주파 노이즈 제거 (EMA 필터: Y[n] = alpha * X[n] + (1 - alpha) * Y[n-1])
    // Q8 연산: (EMA * (256 - ALPHA) + Median * ALPHA) / 256
    inst->ema_filtered_q8 = (inst->ema_filtered_q8 * (256 - EMA_ALPHA_Q8) +
                            ((uint32_t)median_val << 8) * EMA_ALPHA_Q8) >> 8;

    uint32_t final_adc_raw = inst->ema_filtered_q8 >> 8;

    // 5. 스케일 변환 (Linear Mapping: 0~4095 -> 220~1400)
    // 수식: OUT_MIN + (final_adc_raw * (OUT_MAX - OUT_MIN)) / ADC_RAW_MAX
    // 오버플로우 방지를 위해 uint32_t 사용
    uint32_t range_in  = ADC_RAW_MAX - ADC_RAW_MIN;       // 4095
    uint32_t range_out = OUT_MAX - OUT_MIN;               // 1180

    // 반올림을 위해 분모의 절반(range_in / 2)을 더해줌
    uint32_t scaled_val = OUT_MIN + ((final_adc_raw * range_out) + (range_in / 2)) / range_in;

    // 6. 최종 출력 안전 클램핑
    if (scaled_val < OUT_MIN) scaled_val = OUT_MIN;
    if (scaled_val > OUT_MAX) scaled_val = OUT_MAX;

    return (uint16_t)scaled_val;
}



