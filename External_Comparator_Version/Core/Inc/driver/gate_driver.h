/*
 * gate_driver.h
 *
 *  Created on: Apr 12, 2026
 *      Author: luke8
 */

#ifndef INC_DRIVER_GATE_DRIVER_H_
#define INC_DRIVER_GATE_DRIVER_H_

#include "stm32f0xx.h"
#include "stm32f0xx_hal.h"

void Init_GateDriver();

void Change_CCR1(uint16_t new_CCR);
void Change_CCR2(uint16_t new_CCR);
void Change_CCR3(uint16_t new_CCR);

void Change_CCR1_float();
void Change_CCR2_float();
void Change_CCR3_float();

void sixstep(uint8_t step , uint8_t new_CCR);
void Motor_ApplyStep(uint8_t step, uint16_t duty);


#endif /* INC_DRIVER_GATE_DRIVER_H_ */
