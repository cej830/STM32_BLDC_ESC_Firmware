/*
 * driver_ADC_Potentiometer.c
 *
 *  Created on: 2026. 8. 23.
 *      Author: luke8
 */


#include <layer_0_Driver/driver_ADC_Potentiometer.h>
#include "stm32f1xx_hal.h"

extern ADC_HandleTypeDef hadc1;

volatile uint16_t adc_DMA_buffer[2];

void Driver_Init_Potentiometer()
{
	HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_DMA_buffer, 2);
}


void Driver_Get_rawPot(uint16_t *pot_1, uint16_t *pot_2)
{
	*pot_1 = adc_DMA_buffer[0];
	*pot_2 = adc_DMA_buffer[1];
}


void Driver_Pot_SysTick_callback()
{
	ADC1->CR2 |=  ADC_CR2_SWSTART;	//DMA 변환 시작, SW트리거.
}
