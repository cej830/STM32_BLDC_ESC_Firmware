/*
 * driver_ADC_Potentiometer.h
 *
 *  Created on: 2026. 8. 23.
 *      Author: luke8
 */

#ifndef INC_LAYER_0_DRIVER_DRIVER_ADC_POTENTIOMETER_H_
#define INC_LAYER_0_DRIVER_DRIVER_ADC_POTENTIOMETER_H_

#include "stm32f103xb.h"


void Driver_Init_Potentiometer();
void Driver_Get_rawPot(uint16_t *pot_1, uint16_t *pot_2);


void Driver_Pot_SysTick_callback();



#endif /* INC_LAYER_0_DRIVER_DRIVER_ADC_POTENTIOMETER_H_ */
