/*
 * bldc_driver.h
 *
 *  Created on: Jul 26, 2026
 *      Author: luke8
 */

#ifndef INC_DRIVER_BLDC_DRIVER_H_
#define INC_DRIVER_BLDC_DRIVER_H_

#include "stm32f0xx.h"
#include "stm32f0xx_hal.h"
#include "data_struct/data_struct.h"


//에러코드 정리
typedef enum
{
	NO_ERROR,
	TIME_OUT_ERROR,
	ZC_DETECT_ERROR

}MOTOR_ERROR_CODE;

typedef struct
{
	MOTOR_ERROR_CODE error_code;
	uint16_t current_timestamp;
	uint16_t last_timestamp;

}MOTOR_ERROR;


//서비스 레이어에서 동작에 사용하는 함수
void Motor_Inite();
void Motor_Start_Request();
void Motor_Stop();
uint8_t Motor_Run_First();
void BLDC_Driver_Change_Duty(uint8_t target_CCR);

//서비스 레이어에서 디버깅에 사용하는 함수
MOTOR_ERROR Get_Motor_Error();
void Clear_Motor_Error();
void Send_Motorlog(motor_idf* motor_log);

void Driver_SetRegister_LOG(void (*callback_func)(void));
void Driver_SetRegister_MONITOR(void (*callback_func)(void));

uint32_t RPM_From_ZcDiff(uint16_t zc_diff_us);


//인터럽트.c 에서 사용하는 함수
void TIM1_Complete_Callback();
void TIM6_Complete_Callback();
void TIM14_Complete_Callback();




#endif /* INC_DRIVER_BLDC_DRIVER_H_ */
