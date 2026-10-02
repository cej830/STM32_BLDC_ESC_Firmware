/*
 * driver_UART.h
 *
 *  Created on: 2026. 8. 23.
 *      Author: luke8
 */

#ifndef INC_LAYER_0_DRIVER_DRIVER_UART_H_
#define INC_LAYER_0_DRIVER_DRIVER_UART_H_


#include "stm32f103xb.h"
#include <stddef.h>


void Driver_UART_Enable_RX_Interrupt(void);
void Driver_Set_Callback_Adress( uint8_t(*callback_func)(uint8_t data));

void Transmit_Byte_Fast(uint8_t byte);
void Transmit_String_Fast(char *str);


void Driver_USART1_IRQ_Callback();



#endif /* INC_LAYER_0_DRIVER_DRIVER_UART_H_ */
