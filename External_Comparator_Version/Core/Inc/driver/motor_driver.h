/*
 * motor_driver.h
 *
 *  Created on: Jun 24, 2026
 *      Author: luke8
 */

#ifndef INC_DRIVER_MOTOR_DRIVER_H_
#define INC_DRIVER_MOTOR_DRIVER_H_

#include "stm32f0xx.h"
#include "stm32f0xx_hal.h"


void Motor_TIM1_Set(uint8_t duty);
void Motor_TIM1_Reset();

uint8_t ReadPinState(uint8_t current_step);

void Set_TIM6_OFF();
void Set_TIM6_ON();
void Set_TIM6_newARR(uint16_t);

#endif /* INC_DRIVER_MOTOR_DRIVER_H_ */
