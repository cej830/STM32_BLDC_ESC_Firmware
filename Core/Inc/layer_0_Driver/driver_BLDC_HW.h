/*
 * driver_BLDC.h
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 */

#ifndef INC_LAYER_0_DRIVER_DRIVER_BLDC_HW_H_
#define INC_LAYER_0_DRIVER_DRIVER_BLDC_HW_H_

#define R_edge	0
#define F_edge	1

#define CompA	1
#define CompB	2
#define CompC	3


#include "stm32f103xb.h"
#include <my_Utility/utility_us_Timer.h>

//ADC1, TIM3 , TIM2 ISR 에서 콜백할 함수포인터 선언.
typedef void (*Callbackfunc)(void);
typedef void (*Callbackfunc2)(uint16_t);

void Driver_BLDC_HW_SetFuncAdress(Callbackfunc ADC_func, Callbackfunc TIM_func);
void Driver_BLDC_HW_SetFuncAdress2(Callbackfunc2 TIM2_func1, Callbackfunc2 TIM2_func2, Callbackfunc2 TIM2_func3);

//BLDC 모터 제어 관련 HW 레지스터 조작
void Driver_BLDC_HW_Init();
void Driver_BLDC_HW_Startup();
void Driver_BLDC_HW_Stop();

//BLDC 내부 ADC 활용 센서리스 제어 알고리즘 관련 HW 레지스터 조작
void Driver_BLDC_HW_SetTimTrig(uint16_t time_us);
void Driver_BLDC_HW_SetTim3OFF();
void Driver_BLDC_HW_GetPhaseV(volatile uint16_t* A, volatile uint16_t* B, volatile uint16_t* C , volatile uint16_t* VCOM);

//BLDC 외부 비교기 활용 센서리스 제어 알고리즘 관련 HW 레지스터 조작
void Driver_BLDC_HW_SetTIM2_InputCapture_Direction(uint8_t channel, uint8_t edge);
void Driver_BLDC_HW_Set_InputCapture_Enable(uint8_t channel);
void Driver_BLDC_HW_Set_InputCapture_Disable();

//인터럽트 핸들러 함수
void ADC_IRQ_Handler();
void TIM3_IRQ_Handler();
void Driver_BLDC_HW_TIM2_IRQ_Handler();




#endif /* INC_LAYER_0_DRIVER_DRIVER_BLDC_HW_H_ */
