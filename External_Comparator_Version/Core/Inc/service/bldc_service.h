/*
 * bldc_service.h
 *
 *  Created on: Jun 27, 2026
 *      Author: luke8
 */

#ifndef INC_SERVICE_BLDC_SERVICE_H_
#define INC_SERVICE_BLDC_SERVICE_H_

#include "driver/bldc_driver.h"

typedef enum {

	MOTOR_IDLE = 1,
	MOTOR_START_REQUEST,
	MOTOR_OPEN_LOOP,
	MOTOR_CLOSE_LOOP,
	MOTOR_STOP,

}MOTOR_STATE;


void BLDC_Service_Inite();
void BLDC_Service();

void BLDC_Service_Change_CCR(uint8_t target_CCR);
void BLDC_Service_ChangePrintFlag();
void BLDC_Service_Monitor_ON();
void BLDC_Service_Monitor_OFF();




#endif /* INC_SERVICE_BLDC_SERVICE_H_ */
