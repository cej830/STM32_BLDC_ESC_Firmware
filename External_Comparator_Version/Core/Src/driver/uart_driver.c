/*
 * uart_driver.c
 *
 *  Created on: Jul 24, 2026
 *      Author: luke8
 */

#include "driver/uart_driver.h"

extern UART_HandleTypeDef huart2;

static uint8_t error_cnt = 0;

/*
레지스터로 구현시, 송신 영역
TXE 비트가 클리어 되어있는지를 확인하고,
UART->TDR 레지스터에 값을 쓰면, 알아서 하드웨어가 Tx 핀으로 보내준다.
TR 완료 비트를 확인한다.
*/

static void (*UART_Callback_func)(uint8_t byte) = NULL;


void Driver_set_Register( void(*callback_func)(uint8_t byte))
{
	UART_Callback_func = callback_func;
}

void UART_Driver_Enable_RX_Interrupt(void)
{
	/* HAL_UART_Init 이후에 USART 수신 및 오류 인터럽트를 활성화한다. */
	USART2->ICR = USART_ICR_ORECF | USART_ICR_NCF |
				 USART_ICR_FECF | USART_ICR_PECF;
	USART2->CR3 |= USART_CR3_EIE;

	USART2->CR1 |= USART_CR1_RXNEIE;
}

uint8_t Transmit_Byte(uint8_t byte)
{

	if( HAL_UART_Transmit(&huart2, &byte, 1, 10) == HAL_OK ) return 1;
	else return 0;
}


uint8_t Transmit_String(char* string)
{
	if( HAL_UART_Transmit(&huart2, (uint8_t*)string, strlen(string), 10) == HAL_OK ) return 1;
	else return 0;
}


// HAL 함수 사용하지 않는 경우
void Transmit_Byte_Fast(uint8_t byte)
{
        // TXE(Transmit Data Register Empty) 플래그가 1이 될 때까지 대기
        while (!(USART2->ISR & (1 << 7))) {}; // USART_ISR_TXE 비트 0인경우 계속 대기
        // 플래그가 비면 TDR(Transmit Data Register)에 1바이트 꽂아넣기
        USART2->TDR = byte;
        //shift register에서 data가 모두 전송이 되었다는 플래그가 있을때까지 대기
        while (!(USART2->ISR & (1 << 6))) {};

}



void Transmit_String_Fast(char *str) {
    while (*str) {

    	Transmit_Byte_Fast((uint8_t)(*str++));
    }
}


//유아트 수신 인터럽트 받은경우, 수신 인터럽트 핸들러 -> 수신받은 바이트를 알아내고 큐에 집어넣는다.
void UART_Driver_IRQ_Callback(void)
{
	uint32_t sr = USART2->ISR; //SR이 에러가 있을수 있으니 저장해놓는다. ISR레지스터는 인터럽트오 수신상태 정보 알려줌

	if(sr & USART_ISR_RXNE)
	{
		//DR에 있는 수신된 정보를 저장.
		uint8_t received_byte = (uint8_t)USART2->RDR;
		//DR에 있는 정보를 읽으면 RXNE 플래그는 자동으로 0으로 꺼진다.

		if(UART_Callback_func != NULL)
		{
			UART_Callback_func(received_byte);
		}
	}

	if(sr & (USART_ISR_ORE | USART_ISR_NE | USART_ISR_FE | USART_ISR_PE))
	{
		/* 구형 MCU의 에러비트 처리 방식.
		//error 발생기 처리, DR을 한번 더 읽어서 버퍼를 비우기.
		volatile uint32_t dummy = USART2->RDR;
		(void)dummy; //더미를 읽어서 에러 처리.
		*/

		USART2->ICR = USART_ICR_ORECF | USART_ICR_NCF |
					 USART_ICR_FECF | USART_ICR_PECF;

		error_cnt ++; //에러 카운트++
	}

}
