/*
 * gate_driver.c
 *
 *  Created on: Apr 12, 2026
 *      Author: luke8
 */

#include "driver/gate_driver.h"

void Init_GateDriver(){

	// 1. 출력 비활성 상태에서 CCR을 0으로 설정 (로우사이드만 켜지는 상태 준비)
	Change_CCR1(0);
	Change_CCR2(0);
	Change_CCR3(0);

	// 2. 출력 활성화 (CC1E: 하이사이드, CC1NE: 로우사이드)
	// CC1E (bit 0), CC1NE (bit 2) 둘 다 켜야 상보 제어가 됩니다.
	TIM1->CCER |= (1U << 0) | (1U << 2);
	TIM1->CCER |= (1U << 4) | (1U << 6);
	TIM1->CCER |= (1U << 8) | (1U << 10);

	// 3. 마스터 출력 활성화 (Advanced Timer 필수!)
	// BDTR 레지스터의 MOE (bit 15)를 켜야 핀으로 신호가 나갑니다.
	//TIM1->BDTR |= (1U << 15);

	// 4. 타이머 카운터 시작 (CEN bit)
	//TIM1->CR1 |= (1U << 0);

	// 5. 충전 대기 (로우사이드가 켜진 상태로 30ms 유지)
	TIM1->DIER |= (1U << 0); //인터럽트 활성화.
	HAL_Delay(30);

	// 6. 정상 가동 (듀티 50%로 변경)

}


void Change_CCR1(uint16_t new_CCR){

	TIM1->CCER |= (1U << 0) | (1U << 2);
	TIM1->CCR1 = new_CCR;

}

void Change_CCR2(uint16_t new_CCR){

	TIM1->CCER |= (1U << 4) | (1U << 6);
	TIM1->CCR2 = new_CCR;

}

void Change_CCR3(uint16_t new_CCR){

	TIM1->CCER |= (1U << 8) | (1U << 10);
	TIM1->CCR3 = new_CCR;

}

void Change_CCR1_float(){

	TIM1->CCER &= ~((1U << 0) | (1U << 2));
}

void Change_CCR2_float(){

	TIM1->CCER &= ~((1U << 4) | (1U << 6));
}

void Change_CCR3_float(){

	TIM1->CCER &= ~((1U << 8) | (1U << 10));
}

void sixstep(uint8_t step , uint8_t new_CCR){

	switch (step) {

	case 1 :

		//A ( PWM ) B( 0 1 ) C(floating)
		Change_CCR1(new_CCR);
		Change_CCR2(0);
		Change_CCR3_float();
		break;


	case 2 :

		//A (PWM) B(floating) C(0 1)
		Change_CCR1(new_CCR);
		Change_CCR2_float();
		Change_CCR3(0);
		break;

	case 3 :

		//A (floating) B(PWM) C(0 1)
		Change_CCR1_float();
		Change_CCR2(new_CCR);
		Change_CCR3(0);
		break;

	case 4 :

		//A (0 1) B(PWM) C(floating)
		Change_CCR1(0);
		Change_CCR2(new_CCR);
		Change_CCR3_float();
		break;

	case 5 :

		//A (0 1) B(floating) C(PWM)
		Change_CCR1(0);
		Change_CCR2_float();
		Change_CCR3(new_CCR);
		break;

	case 6 :

		//A (floating) B(0 1) C(PWM)
		Change_CCR1_float();
		Change_CCR2(0);
		Change_CCR3(new_CCR);
		break;

	default :

		Change_CCR1_float();
		Change_CCR2_float();
		Change_CCR3_float();
		break;


	}


}
