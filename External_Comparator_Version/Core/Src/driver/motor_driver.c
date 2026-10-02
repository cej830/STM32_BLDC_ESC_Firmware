#include "driver/motor_driver.h"
#include "driver/gate_driver.h"
#include "main.h"
#include "stm32f0xx_it.h"


void Motor_TIM1_Set(uint8_t duty){

	TIM1->CNT = 0U;
	TIM1->CR1 |= (1U << 0);

	sixstep(1, duty);
	TIM1->BDTR |= (1U << 15);
	HAL_Delay(30);
}

void Motor_TIM1_Reset(){

	/* Disable main output */
	TIM1->BDTR &= ~TIM_BDTR_MOE;
	//타이머 끄기.
	TIM1->CR1 &= ~(1U << 0);

}


void Set_TIM6_OFF(){

	TIM6->CR1 &= ~(1U << 0);
	TIM6->SR = ~(1U << 0);
	TIM6->CNT = 0;
}


void Set_TIM6_ON(){

	TIM6->SR = ~(1U << 0);
	TIM6->CNT = 0;
	TIM6->CR1 |= (1U << 0);
}

void Set_TIM6_newARR(uint16_t new_ARR){

	//TIM3 (30도 지연 타이머) 세팅 및 시작
	TIM6->ARR = new_ARR;
	//EGR를 쓰면 즉시 인터럽트가 터지므로, 조용히 카운터만 초기화
	TIM6->CNT = 0;
	// 이전에 발생했을지 모를 인터럽트 찌꺼기 플래그 확실히 제거 (0을 써서 클리어)
	TIM6->SR = ~(1U << 0);
	// TIM3 시작 (CEN 비트 활성화)
	TIM6->CR1 |= (1U << 0);
}


/*
 * 스텝 1, 스텝 4 : floating C -> PB5
 * 스텝 2, 스텝 5 : floating B -> PB4
 * 스텝 3, 스텝 6 : floating A -> PB3
 */

uint8_t ReadPinState(uint8_t current_step){

	uint8_t pinstate = 0;

	switch (current_step)
	{

	case 1: case 4:
		pinstate = (GPIOB->IDR >> 5) & 0x01;
		break;
	case 2: case 5:
		pinstate = (GPIOB->IDR >> 4) & 0x01;
		break;
	case 3: case 6:
		pinstate = (GPIOB->IDR >> 3) & 0x01;
		break;
	default :
		pinstate = 0;
		break;
	}

	return pinstate;
}

/*
ZC가 발생한 순간 Interrupt를 통해 읽을수 있도록 한다.

floating C -> PB5
floating B -> PB4
floating A -> PB3

PB3 인터럽트 라인을 활성화
인터럽트 마스크를 씌워두고 해제하기

step 1 일때, 플로팅 C를 검출 -> PB5 라인의 인터럽트 마스크를 해제하여, 인터럽트를 활성화 하기.

인터럽트 IRQ에서 타이머6의 ARR만 설정해주고 빠져나오기

타미어6의 완료 인터럽트에서 step을 변경해주고, 인터럽트를 마스트를 해제해주고 빠져나오기


ex step1) 인터럽트로 ZC 감지했을시의 흐름

1. PB5라인 인터럽트 다시 차단
2. 타이머6 의 ARR을 전기각 30도에 해당하도록 설정
3. 타이머 완료 인터럽트 대기
4. 타이머 완료 인터럽트 완료
4-1. step2에 해당하는 PB4라인을 라이징 엣지 검출로 모드 변경
4-2. PB4 라인의 인터럽트 마스크 해제
4-2. 다음 스텝인 step2로 변경

타이머 6의 ARR을 설정후 타이머6 ON


필요한 드라이버 함수는
1. 라인별 인터럽트 마스크 해제
2. 모든 라인 인터럽트 마스크 설정
3. 라인별 라이징 엣지 , 폴링 엣지 설정

*/


//타이머 인터럽트 완료시 핸들러 함수,
//다음 스텝에 대하여
/*
* 스텝 1, 스텝 4 : floating C -> PB5
* 스텝 2, 스텝 5 : floating B -> PB4
* 스텝 3, 스텝 6 : floating A -> PB3
*
* 1,3,5 -> 폴링 엣지
* 2,4,6 -> 라이징 엣지
*
*
* ZC 감지 -> 인터럽트 함수 내용
*
* 비교기 인터럽트 모두 마스크
*
* 타미어 6의 CNT에서 감지 시간 추출
* 이전 감지 시간과 CNT로 부터 전기각 30도 계산.
*
* 타이머 3의 ARR에 전기각 30도 입력
* 타이머 3 처음부터 타이머 시작.
*
* 345 라인 모두에 해당하는 내용.
*
*/



