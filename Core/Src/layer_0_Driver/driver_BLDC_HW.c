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

void Driver_BLDC_HW_GetPhaseV(volatile uint16_t* A, volatile uint16_t* B, volatile uint16_t* C , volatile uint16_t* VCOM);

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

void Driver_BLDC_HW_GetPhaseV(volatile uint16_t* A, volatile uint16_t* B, volatile uint16_t* C , volatile uint16_t* VCOM)
{
	*A = ADC1->JDR1;
	*B = ADC1->JDR2;
	*C = ADC1->JDR3;
	*VCOM = ADC1->JDR4;
}


void ADC_IRQ_Handler()
{
	if( !(ADC1->SR & ADC_SR_JEOS) ) return;		//ADC_SR 레지스터 injectedADC 변환 완료 인터럽트 마스크 확인

	ADC1->SR &= ~ADC_SR_JEOS;						//ADC_SR 레지스터 injectedADC 변환 완료 인터럽트 마스크 해제
	GPIOB->BSRR = (1U << 16);

	if(ADC_ISR_Callback != NULL) ADC_ISR_Callback();
}


void Driver_BLDC_HW_Set_InputCapture_Disable()
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


/* 라이징 엣지 설정 edge = 0, 폴링 엣지 설정 edge = 1
 *
 */
void Driver_BLDC_HW_SetTIM2_InputCapture_Direction(uint8_t channel, uint8_t edge)
{

	Driver_BLDC_HW_Set_InputCapture_Disable();

	switch (channel)
	{
	case 1 :
		if(edge == R_edge) TIM2->CCER &= ~TIM_CCER_CC1P;		//라이징 엣지로 설정
		else 		  	   TIM2->CCER |= TIM_CCER_CC1P;		//폴링 엣지로 설정
		break;

	case 2 :
		if(edge == R_edge) TIM2->CCER &= ~TIM_CCER_CC2P;		//라이징 엣지로 설정
		else 		  	   TIM2->CCER |= TIM_CCER_CC2P;		//폴링 엣지로 설정
		break;

	case 3 :
		if(edge == R_edge) TIM2->CCER &= ~TIM_CCER_CC3P;		//라이징 엣지로 설정
		else 		  	   TIM2->CCER |= TIM_CCER_CC3P;		//폴링 엣지로 설정
		break;

	default :
		break;
	}

}

void Driver_BLDC_HW_Set_InputCapture_Enable(uint8_t channel)
{

	switch (channel)
	{
	case 1 :
		TIM2->SR &= ~TIM_SR_CC1OF;						//오버캡쳐 인터럽트 팬딩 비트 클리어
		TIM2->SR &= ~TIM_SR_CC1IF;						//인터럽트 팬딩 비트 클리어
		TIM2->DIER |= TIM_DIER_CC1IE;					//CH1 에 대해 인터럽트 활성화.

		TIM2->CCER |= TIM_CCER_CC1E;					//CH1 인풋 캡쳐 활성화.
		break;

	case 2 :
		TIM2->SR &= ~TIM_SR_CC2OF;						//오버캡쳐 인터럽트 팬딩 비트 클리어
		TIM2->SR &= ~TIM_SR_CC2IF;						//인터럽트 팬딩 비트 클리어
		TIM2->DIER |= TIM_DIER_CC2IE;					//CH2 에 대해 인터럽트 활성화.

		TIM2->CCER |= TIM_CCER_CC2E;					//CH2 인풋 캡쳐 활성화.
		break;

	case 3 :
		TIM2->SR &= ~TIM_SR_CC3OF;						//오버캡쳐 인터럽트 팬딩 비트 클리어
		TIM2->SR &= ~TIM_SR_CC3IF;						//인터럽트 팬딩 비트 클리어
		TIM2->DIER |= TIM_DIER_CC3IE;					//CH3 에 대해 인터럽트 활성화.

		TIM2->CCER |= TIM_CCER_CC3E;					//CH3 인풋 캡쳐 활성화.
		break;

	default :
		break;
	}
}



void Driver_BLDC_HW_TIM2_IRQ_Handler()
{
	if( TIM2->SR & TIM_SR_CC1IF )
	{
		TIM2->SR &= ~TIM_SR_CC1IF;
		//TIM2->CCR1 값을 알고리즘 레이어나 다른 레이어의 static 변수에 넘겨주기
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


void TIM3_IRQ_Handler()
{
	if( TIM3->SR & TIM_SR_UIF )
	{
		TIM3->SR &= ~TIM_SR_UIF;
		if(TIM3_ISR_Callback != NULL) TIM3_ISR_Callback();
	}
}
