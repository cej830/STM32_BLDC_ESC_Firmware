/*
 * driver_GateDriver.c
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 *
 *
 *      TIM1 20kHz PWM 발생 -> APB Clock : 72MHz , TIM1 PSC = 0, ARR = 1800 , Center-Aligened Mode 1
 *      채널 1, 2, 3 :  Center-Aligened PWM mode1 상보 output
 *      채널 4		: PWM No Output -> External Trigger Source 로 사용하여 ADC와 연결.
 *
 *      데드타임, 2us -> 72MHz 기준 144
 *
 */

#include <layer_0_Driver/driver_GateDriver.h>

void Driver_Init_GateDriver()
{
	// 1. 출력 비활성 상태에서 채널 1,2,3 의 CCR을 0으로 설정 (로우사이드만 켜지는 상태 준비)
	TIM1->CCR1 = 0;
	TIM1->CCR2 = 0;
	TIM1->CCR3 = 0;

	// 2. 출력 활성화 (CC1E: 하이사이드, CC1NE: 로우사이드)
	// CC1E (bit 0), CC1NE (bit 2) 둘 다 켜야 상보 제어가 됩니다.
	TIM1->CCER |= (1U << 0) | (1U << 2);	//채널 1 , CC1E(0) CC1NE(2)
	TIM1->CCER |= (1U << 4) | (1U << 6);	//채널 2 , CC1E(4) CC1NE(6)
	TIM1->CCER |= (1U << 8) | (1U << 10);	//채널 3 , CC1E(8) CC1NE(10)
}


void Change_CCR1(uint16_t new_CCR)
{
	TIM1->CCER |= (1U << 0) | (1U << 2);	//채널의 P, N 출력을 활성화.
	TIM1->CCR1 = new_CCR;					//새로운 CCR 값 적용
}

void Change_CCR2(uint16_t new_CCR)
{
	TIM1->CCER |= (1U << 4) | (1U << 6);
	TIM1->CCR2 = new_CCR;
}

void Change_CCR3(uint16_t new_CCR)
{
	TIM1->CCER |= (1U << 8) | (1U << 10);
	TIM1->CCR3 = new_CCR;
}

void Change_CCR1_float()
{
	TIM1->CCER &= ~((1U << 0) | (1U << 2));	//PWM 채널 출력을 끊어버림.
}

void Change_CCR2_float()
{
	TIM1->CCER &= ~((1U << 4) | (1U << 6));
}

void Change_CCR3_float()
{
	TIM1->CCER &= ~((1U << 8) | (1U << 10));
}

