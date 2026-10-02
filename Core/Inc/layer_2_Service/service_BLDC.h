/*
 * service_BLDC.h
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 */

#ifndef INC_LAYER_2_SERVICE_SERVICE_BLDC_H_
#define INC_LAYER_2_SERVICE_SERVICE_BLDC_H_


#include <layer_0_Driver/driver_BLDC_HW.h>
#include "stm32f103xb.h"

typedef enum
{
	MOTOR_IDLE,
	MOTOR_START_REQUEST,
	MOTOR_RUN_OPENLOOP,
	MOTOR_RUN_CLOSELOOP,
	MOTOR_STOP

}MOTOR_STATE;


void Service_BLDC_Init();
void Service_BLDC_Run();
void Service_BLDC_UserBTN1_Callback();

#endif /* INC_LAYER_2_SERVICE_SERVICE_BLDC_H_ */
