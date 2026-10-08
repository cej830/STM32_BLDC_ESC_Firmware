/*
 * service_BLDC.c
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 */


/*
 * bldc_service.c
 *
 *  Created on: Jun 27, 2026
 *      Author: luke8
 */

#include <layer_0_Driver/driver_GateDriver.h>
#include <layer_0_Driver/driver_UART.h>
#include <layer_2_Service/service_BLDC.h>
#include <layer_1_Algorithm/algorithm_BLDC_Control.h>

#include "main.h"

extern  TIM_HandleTypeDef htim1;
#define MAX_BUFF	200


//메인에서 초기화 , 메인과 인터럽트(버튼)에서 갱신됨
static volatile MOTOR_STATE motor_state = MOTOR_IDLE;
static uint8_t print_flag = 0;

void Service_BLDC_Init()
{
	motor_state = MOTOR_IDLE;
	EXTI->IMR |= (1U<<11);		//USER_BTN1 , PB11 버튼 인터럽트 활성화
}


// 메인 루프 서비스
void Service_BLDC_Run()
{
    switch (motor_state)
    {
    	case MOTOR_IDLE:

    		if(print_flag == 1)
    		{
    		  print_flag = 0;
    		  //print_BLDC_CloseLoop_Log();
    		  //print_BLDC_OpenLoop_Log();
    		 }
    		break;

    	case MOTOR_START_REQUEST:

    		ClearError();
    		HAL_Delay(100);			//정렬후 대기.
    		HAL_TIM_PWM_Start_IT(&htim1, TIM_CHANNEL_4);
			Algo_BLDC_Startup();	//플래그 변수들을 처음으로 초기화. 스텝1으로 정렬.
    		motor_state = MOTOR_RUN_CLOSELOOP;
    		break;
			
    	case MOTOR_RUN_CLOSELOOP:

    		MotorError_t error = Get_ErrorCode();
    		if(error != NO_ERROR)	//폴링방식으로 지속적으로 error 변수를 감시
    		{
    			motor_state = MOTOR_STOP;
    			break;
    		}
    		break;

    	case MOTOR_STOP:
    		print_flag = 1;
    		Driver_BLDC_HW_Stop();
    		HAL_TIM_PWM_Stop_IT(&htim1, TIM_CHANNEL_4);
    		GPIOC->BSRR = (1U << (14+16));

    		motor_state = MOTOR_IDLE;
    		break;

    	default:
    		motor_state = MOTOR_IDLE;
    		break;
    }
}



void Service_BLDC_UserBTN1_Callback()
{
	if(EXTI->PR & (1U << 11))
	{
		EXTI->PR |= (1U << 11);

		if(motor_state == MOTOR_IDLE)
		{
			motor_state = MOTOR_START_REQUEST;
		}

		else if((motor_state == MOTOR_RUN_OPENLOOP) || (motor_state == MOTOR_RUN_CLOSELOOP))
		{
			motor_state = MOTOR_STOP;
		}
	}
}



