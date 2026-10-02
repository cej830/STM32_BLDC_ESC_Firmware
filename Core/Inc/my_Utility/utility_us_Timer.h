/*
 * driver_Us_Timer.h
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 */

#ifndef INC_LAYER_0_DRIVER_DRIVER_US_TIMER_H_
#define INC_LAYER_0_DRIVER_DRIVER_US_TIMER_H_

#include "stm32f103xb.h"

void Driver_Init_Us_Timer();
uint16_t Driver_Time_Get_Us();
void Driver_Delay_Us(uint16_t delay_time);

#endif /* INC_LAYER_0_DRIVER_DRIVER_US_TIMER_H_ */
