/*
 * driver_GateDriver.c
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 */

#ifndef INC_MY_DRIVER_DRIVER_GATEDRIVER_C_
#define INC_MY_DRIVER_DRIVER_GATEDRIVER_C_


#include "stm32f103xb.h"


void Driver_Init_GateDriver();

void Change_CCR1(uint16_t new_CCR);
void Change_CCR2(uint16_t new_CCR);
void Change_CCR3(uint16_t new_CCR);

void Change_CCR1_float();
void Change_CCR2_float();
void Change_CCR3_float();

#endif /* INC_MY_DRIVER_DRIVER_GATEDRIVER_C_ */
