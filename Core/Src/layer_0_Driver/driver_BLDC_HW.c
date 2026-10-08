/*
 * driver_BLDC.c
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 */


#include <layer_0_Driver/driver_BLDC_HW.h>
#include <stddef.h>

void Driver_BLDC_HW_Init();
void Driver_BLDC_HW_Startup();
void Driver_BLDC_HW_Stop();

void Driver_BLDC_HW_SetTimTrig(uint16_t time_us);
void Driver_BLDC_HW_SetTim3OFF();

void ADC_Handler();
void TIM3_IRQ_Handler();

void Driver_BLDC_HW_GetPhaseV(uint16_t* A,  uint16_t* B, uint16_t* C );

//------ADC ISR, TIM3 ISR 에서 사용
static Callbackfunc ADC_ISR_Callback = NULL;
static Callbackfunc TIM3_ISR_Callback = NULL;

static Callbackfunc2 TIM2_ISR_Callback_A =NULL;
static Callbackfunc2 TIM2_ISR_Callback_B =NULL;
static Callbackfunc2 TIM2_ISR_Callback_C =NULL;

void Driver_BLDC_HW_SetFuncAdress(Callbackfunc ADC_func, Callbackfunc TIM_func)
{
	ADC_ISR_Callback = ADC_func;
	TIM3_ISR_Callback = TIM_func;
}

void Driver_BLDC_HW_SetFuncAdress2(Callbackfunc2 TIM2_func1, Callbackfunc2 TIM2_func2, Callbackfunc2 TIM2_func3)
{
	TIM2_ISR_Callback_A = TIM2_func1;
	TIM2_ISR_Callback_B = TIM2_func2;
	TIM2_ISR_Callback_C = TIM2_func3;
}


void Driver_BLDC_HW_Init()
{
	TIM1->CCER |=  (1U << 12);		//TIM 채널4 출력 활성화
	TIM3->DIER |= (1U << 0);		//TIM3 업데이트 인터럽트 활성화.
	TIM2->CR1  |= TIM_CR1_CEN;
}


void Driver_BLDC_HW_Startup()
{
	TIM1->CCR4 = (TIM1->ARR)- 1;				//타이머1 채널4 CCR 에 로우듀티케이스 적용

	TIM1->BDTR 	|= 	TIM_BDTR_MOE;				//TIM1  Master Output Enable
	TIM1->CR1 	|= 	TIM_CR1_CEN;				//CEN(0) ON

	TIM3->ARR = 0xFF;
	TIM3->SR &= ~TIM_SR_UIF;		//타이머3 인터럽트 팬딩 클리어
}

void Driver_BLDC_HW_SetLowSide_Flat()
{
	TIM1->CCR4 = (TIM1->ARR)-1;
}

void Driver_BLDC_HW_SetHighSide_Flat()
{
	TIM1->CCR4 = 1;
}

void Driver_BLDC_HW_Stop()
{
	/* Disable main output */
	TIM1->BDTR &= ~(1U << 15);	//MOE 레지스터에서 main output 끄기.
	TIM1->CR1 &= ~(1U << 0);	//타이머 끄기.

	TIM3->CR1 &= ~(1U << 0);
	TIM3->SR &= ~(1U << 0);
	TIM3->CNT = 0;
}

/* TIM3로 time_us 지연후 UI 발생하는 함수. @ return | void
*  @ time_us : 지연할 시간 us 단위
*/
void Driver_BLDC_HW_SetTimTrig(uint16_t time_us)
{
	TIM3->CR1 &= ~TIM_CR1_CEN;			//타이머3 enable RESET
	TIM3->SR &= ~TIM_SR_UIF;			//업데이트 인터럽트 RESET

	TIM3->CNT = 0;						//CNT값 초기화
	TIM3->ARR =  time_us;		//16비트 us초 입력
	TIM3->CR1 |= TIM_CR1_CEN;			//타이머3 enable SET
}


void Driver_BLDC_HW_SetTim3OFF()
{
	TIM3->CR1 &= ~TIM_CR1_CEN;	//CEN (0) 비활성화.
	TIM3->CNT = 0;				//CNT값 초기화
}

void Driver_BLDC_HW_GetPhaseV(uint16_t* A, uint16_t* B, uint16_t* C )
{
	*A = ADC1->JDR1;
	*B = ADC1->JDR2;
	*C = ADC1->JDR3;
}


void ADC_IRQ_Handler()
{
	if( !(ADC1->SR & ADC_SR_JEOS) ) return;		//ADC_SR 레지스터 injectedADC 변환 완료 인터럽트 마스크 확인

	ADC1->SR &= ~ADC_SR_JEOS;						//ADC_SR 레지스터 injectedADC 변환 완료 인터럽트 마스크 해제
	GPIOB->BSRR = (1U << 16);

	if(ADC_ISR_Callback != NULL) ADC_ISR_Callback();
}


void TIM3_IRQ_Handler()
{
	if( TIM3->SR & TIM_SR_UIF )
	{
		TIM3->SR &= ~TIM_SR_UIF;
		if(TIM3_ISR_Callback != NULL) TIM3_ISR_Callback();
	}
}

void TIM2_IRQ_Handler()
{
	if( TIM2->SR & TIM_SR_CC1IF )
	{
		TIM2->SR &= ~TIM_SR_CC1IF;
		//TIM2->CCR1 값을 알고리즘 레이어나 다른 레이어에서 쓸수 있도록 매개변수로 넘겨주기.
		//알고리즘 레이어의 static 변수를 update 하는 함수를 콜백하기.
		TIM2_ISR_Callback_A((uint16_t)TIM2->CCR1);

	}

	else if (TIM2->SR & TIM_SR_CC2IF)
	{
		TIM2->SR &= ~TIM_SR_CC2IF;
		// TIM2->CCR2 값을 알고리즘 레이어나 다른 레이어에 넘겨주기
		TIM2_ISR_Callback_B((uint16_t)TIM2->CCR2);
	}

	else if (TIM2->SR & TIM_SR_CC3IF)
	{
		TIM2->SR &= ~TIM_SR_CC3IF;
		// TIM2->CCR3 값을 알고리즘 레이어나 다른 레이어에 넘겨주기
		TIM2_ISR_Callback_C((uint16_t)TIM2->CCR3);
	}
}


void Disable_TIM_IC_ALL()
{
	//인터럽트 비활성화.
	TIM2->DIER &= ~TIM_DIER_CC1IE;
	TIM2->DIER &= ~TIM_DIER_CC2IE;
	TIM2->DIER &= ~TIM_DIER_CC3IE;

	//인풋 캡쳐 비활성화.
	TIM2->CCER &= ~TIM_CCER_CC1E;	//CH1 인풋캡쳐 모드 끄기
	TIM2->CCER &= ~TIM_CCER_CC2E;	//CH2 인풋캡쳐 모드 끄기
	TIM2->CCER &= ~TIM_CCER_CC3E;	//CH3 인풋캡쳐 모드 끄기
}


void Enable_TIM_IC(uint8_t channel,  TIM_IC_EDGE_MODE mode)
{

	switch (channel)
	{
	case 1 :
		TIM2->DIER &= ~TIM_DIER_CC1IE_Msk;		//인터럽트 비활성화
		TIM2->CCER &= ~TIM_CCER_CC1E_Msk;		//IC 비활성화

		TIM2->CCER &= ~TIM_CCER_CC1P_Msk;		//CCxP 비트 reset, (Rising이 기본)
		if(mode == FALLING_EDGE)
		{
			TIM2->CCER |= TIM_CCER_CC1P;
		}

		TIM2->DIER |= TIM_DIER_CC1IE;					//인터럽트 켜기
		TIM2->CCER |= TIM_CCER_CC1E;					//인풋캡쳐 키기.
		return;

	case 2 :
		TIM2->DIER &= ~TIM_DIER_CC2IE_Msk;		//인터럽트 비활성화
		TIM2->CCER &= ~TIM_CCER_CC2E_Msk;		//IC 비활성화

		TIM2->CCER &= ~TIM_CCER_CC2P_Msk;		//CCxP 비트 reset, (Rising이 기본)
		if(mode == FALLING_EDGE)
		{
			TIM2->CCER |= TIM_CCER_CC2P;
		}

		TIM2->DIER |= TIM_DIER_CC2IE;					//인터럽트 켜기
		TIM2->CCER |= TIM_CCER_CC2E;					//인풋캡쳐 키기.
		return;

	case 3 :
		TIM2->DIER &= ~TIM_DIER_CC3IE_Msk;		//인터럽트 비활성화
		TIM2->CCER &= ~TIM_CCER_CC3E_Msk;		//IC 비활성화

		TIM2->CCER &= ~TIM_CCER_CC3P_Msk;		//CCxP 비트 reset, (Rising이 기본)
		if(mode == FALLING_EDGE)
		{
			TIM2->CCER |= TIM_CCER_CC3P;
		}

		TIM2->DIER |= TIM_DIER_CC3IE;					//인터럽트 켜기
		TIM2->CCER |= TIM_CCER_CC3E;					//인풋캡쳐 키기.
		return;

	default :
		Disable_TIM_IC_ALL();
		return;
	}


}


void Disable_TIM_IC(uint8_t channel)
{
	switch (channel)
	{
	case 1 :
		TIM2->DIER &= ~TIM_DIER_CC1IE_Msk;					//인터럽트 비활성화.
		TIM2->CCER &= ~TIM_CCER_CC1E_Msk;					//인풋캡쳐 모드 끄기
		TIM2->SR &= ~TIM_SR_CC1OF_Msk;						//오버캡쳐 인터럽트 팬딩 비트 클리어
		TIM2->SR &= ~TIM_SR_CC1IF_Msk;						//인터럽트 팬딩 비트 클리어
		return;

	case 2 :
		TIM2->DIER &= ~TIM_DIER_CC2IE_Msk;
		TIM2->CCER &= ~TIM_CCER_CC2E_Msk;
		TIM2->SR &= ~TIM_SR_CC2OF_Msk;
		TIM2->SR &= ~TIM_SR_CC2IF_Msk;
		return;

	case 3 :
		TIM2->DIER &= ~TIM_DIER_CC3IE_Msk;
		TIM2->CCER &= ~TIM_CCER_CC3E_Msk;
		TIM2->SR &= ~TIM_SR_CC3OF_Msk;
		TIM2->SR &= ~TIM_SR_CC3IF_Msk;
		return;

	default :
		Disable_TIM_IC_ALL();
		return;
	}
}
