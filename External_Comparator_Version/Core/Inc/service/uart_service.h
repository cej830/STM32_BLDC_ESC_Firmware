/*
 * uart_service.h
 *
 *  Created on: Jul 31, 2026
 *      Author: luke8
 */

#ifndef INC_SERVICE_UART_SERVICE_H_
#define INC_SERVICE_UART_SERVICE_H_


#include "data_struct/data_struct.h"
#include "driver/uart_driver.h"
#include "service/bldc_service.h"



void UART_Service_Initie();

void UART_Service_CLI();

#endif /* INC_SERVICE_UART_SERVICE_H_ */
