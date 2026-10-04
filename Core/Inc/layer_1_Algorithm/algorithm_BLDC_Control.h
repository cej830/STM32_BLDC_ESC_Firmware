/*
 * algorithm_BLDC_Control.h
 *
 *  Created on: 2026. 8. 27.
 *      Author: luke8
 */

#ifndef INC_LAYER_1_ALGORITHM_ALGORITHM_BLDC_CONTROL_H_
#define INC_LAYER_1_ALGORITHM_ALGORITHM_BLDC_CONTROL_H_


#include <layer_0_Driver/driver_BLDC_HW.h>
#include <layer_0_Driver/driver_GateDriver.h>
#include <my_Utility/utility_Log_BLDC.h>

	/* @BLDC six_step table
	 *
	 * step 1 : A (PWM) 	  B (GND)       C (floating)
	 * step 2 : A (PWM) 	  B (floating)  C (GND)
	 * step 3 : A (floating)  B (PWM)       C (GND)
	 *
	 * step 4 : A (GND) 	  B (PWM) 	   C (floating)
	 * step 5 : A (GND) 	  B (floating) C (PWM)
	 * step 6 : A (floating)  B (GND) 	   C (PWM)
	 *
	 * R_Edge : step2, step4, setp6
	 * F_Edge : setp1, step3, setp5
	 *
	 */


typedef enum
{
	NO_ERROR = 0,
	TIME_OUT,
	ZC_RISK_LIMIT,
	ZC_REJECTED,
}MotorError_t;

typedef enum
{
	OPEN_LOOP = 0,
	CLOSE_LOOP,
	CLOSE_LOCKIN
}MotorStatus_t;


typedef enum
{
	ZC_VALID=0,
	ZC_RISK,
	ZC_REJECT
}ZC_Valid_Status_t;


//모터 관리 변수 구조체, TIM3 ISR
typedef struct
{
	MotorStatus_t motorstate;		//motorstate, 0: OPENLOOP, 1: CLOSELOOP
	uint16_t step;					//current step
	uint16_t target_CCR;
	uint16_t CCR;					//current CCR
	uint8_t motor_first_closeloop;	//falg, 첫번째 클로즈루프인지, 0: NO, 1: YES
	uint8_t cnt_cycle;
}MotorControl;

typedef struct
{
	uint16_t timestamp_start;		//인버터 동작시, 타임스탬프
	uint8_t	zc_searching;			//ZC 탐지 플래그, 0: 탐지 OFF, 1: 탐지 ON
	uint8_t zc_first_sample;		//스텝전환후 첫번째 샘플인지, 0: NO, 1: YES

	uint8_t CNT;

}ZC_Management;

typedef struct
{
	uint16_t timestamp_prev;		//이전 샘플의 ISR 진입 타임스탬프
	uint16_t timestamp_last_zc;		//이전 스텝의 zc 발생 타임스탬프
	int16_t  BEMF_prev;				//이전 샘플의 BEMF
	uint16_t current_delay;			//이전 샘플의 30도 지연 시간.
}ZC_History;


typedef struct
{
	int16_t log_BEMF_curr;

	uint16_t log_timestamp_curr;
	uint16_t log_timestamp_zc;

	uint16_t log_delay_target;
	uint16_t log_delay_limited;
	uint16_t log_delay_trigger;

	uint8_t log_zc_event;

}Motorlog_Temporary;

typedef struct
{
	uint16_t cnt_delay_over;
	uint16_t cnt_elapsed_over;
	uint16_t cnt_predict_over;
}ZC_Over_cnt;


typedef enum
{
	LOWSIDE_SAMPLE,
	HIGHSIDE_SAMPLE
}SAMPLE_MODE;


void ClearError();
MotorError_t Get_ErrorCode();

void Algo_BLDC_Init();

void Algo_BLDC_Startup();
uint8_t Algo_BLDC_RunOpenloop();

#endif /* INC_LAYER_1_ALGORITHM_ALGORITHM_BLDC_CONTROL_H_ */
