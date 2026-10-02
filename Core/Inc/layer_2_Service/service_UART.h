/*
 * service_UART.h
 *
 *  Created on: 2026. 8. 23.
 *      Author: luke8
 */

#ifndef INC_LAYER_2_SERVICE_SERVICE_UART_H_
#define INC_LAYER_2_SERVICE_SERVICE_UART_H_


#include <my_Utility/utility_RingBuffer.h>
#include <layer_0_Driver/driver_UART.h>

void Service_Init_UART();
void Service_UART_RunCLI();


#endif /* INC_LAYER_2_SERVICE_SERVICE_UART_H_ */
