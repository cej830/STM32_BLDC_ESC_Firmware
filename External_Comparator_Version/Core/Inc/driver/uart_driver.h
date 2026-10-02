/*
 * uart_driver.h
 *
 *  Created on: Jul 24, 2026
 *      Author: luke8
 */

#ifndef INC_DRIVER_UART_DRIVER_H_
#define INC_DRIVER_UART_DRIVER_H_


#include "stm32f0xx.h"
#include "stm32f0xx_hal.h"

#include <string.h>


void Driver_set_Register( void(*callback_func)(uint8_t byte));
void UART_Driver_Enable_RX_Interrupt(void);


uint8_t Transmit_Byte(uint8_t byte);
uint8_t Transmit_String(char* string);

void Transmit_Byte_Fast(uint8_t byte);
void Transmit_String_Fast(char* str);


void UART_Driver_IRQ_Callback(void);

#endif /* INC_DRIVER_UART_DRIVER_H_ */
