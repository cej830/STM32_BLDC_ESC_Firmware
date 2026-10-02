/*
 * driver_UART.c
 *
 *  Created on: 2026. 8. 21.
 *      Author: luke8
 */

#include <layer_0_Driver/driver_UART.h>

static uint8_t error_cnt;
static uint8_t (*Callback_Service_func)(uint8_t data) = NULL;


void Driver_Set_Callback_Adress( uint8_t(*callback_func)(uint8_t data) )
{
	Callback_Service_func = callback_func;
}


void Driver_UART_Enable_RX_Interrupt(void)
{
	USART1->CR1 |= USART_CR1_RXNEIE;	// (5) RXNEIE: Receive Interrupt Enable
}


// HAL 함수 사용하지 않는 경우
void Transmit_Byte_Fast(uint8_t byte)
{
        // TXE(Transmit Data Register Empty) 플래그가 1이 될 때까지 대기
        while (!(USART1->SR & (1 << 7))) {}; // USART_SR_TXE 비트 0인경우 계속 대기
        // 플래그가 비면 TDR(Transmit Data Register)에 1바이트 꽂아넣기
        USART1->DR = byte;
        //shift register 에서 data 가 모두 전송이 되었다는 플래그가 있을때까지 대기
        while (!(USART1->SR & (1 << 6))) {};
}



void Transmit_String_Fast(char *str) {
    while (*str) {

    	Transmit_Byte_Fast((uint8_t)(*str++));
    }
}




void Driver_USART1_IRQ_Callback(){


	uint32_t sr = USART1->SR; //SR이 에러가 있을수 있으니 저장해놓는다.

	if(sr & (1U << 5)) {  //SR의 RXNE가 1일경우 진짜 인터럽트

		//DR에 있는 수신된 정보를 저장.
		uint8_t received_byte = (uint8_t)USART1->DR;
		//DR에 있는 정보를 읽으면 RXNE 플래그는 자동으로 0으로 꺼진다.

		if(Callback_Service_func != NULL)
		{
			uint8_t result = Callback_Service_func(received_byte);
			if(result == 0) error_cnt++;
		}
	}


	// Overrun error (bit3) , Noise error (bit2) , Framing error (bit1)
	// 수신 레지스터를 읽기 전에 , 다음데이터가 또 들어온 경우 -> Overrun
	if( sr & ((1U<<3) | (1U<<2) | (1U<<1)) ){

		//error 발생기 처리, DR을 한번 더 읽어서 버퍼를 비우기.
		volatile uint32_t dummy = USART1->DR;
		(void)dummy; //더미를 읽어서 에러 처리.
		error_cnt ++; //에러 카운트++
	}


}






