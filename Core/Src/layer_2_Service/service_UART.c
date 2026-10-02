/*
 * service_UART.c
 *
 *  Created on: 2026. 8. 23.
 *      Author: luke8
 */

#include <layer_2_Service/service_UART.h>

//----------------------------------------------------------
//유아트 , CLI 버퍼 크기
#define MAX_BUFF 64

//유아트 저장 원형버퍼
static uint8_t uart_rx_buffer[MAX_BUFF];
static RingBuffer Uart_RingBuffer;

//CLI 처리용 배열
static char command_line[MAX_BUFF];
static uint8_t idx = 0;

//유아트 RX 인터럽트 콜백함수
static uint8_t Service_Push_UART(uint8_t data);

//---------------------------------------------------------

//유아트 서비스 초기화 함수
void Service_Init_UART()
{
	Driver_UART_Enable_RX_Interrupt();	//RX 인터럽트 활성화

	Driver_Set_Callback_Adress(Service_Push_UART);	//콜백함수 주소 지정
	Create_RingBuffer(&Uart_RingBuffer, uart_rx_buffer, MAX_BUFF);	//원형 버퍼 주소 지정
}

//CLI 서비스 동작 함수
void Service_UART_RunCLI()
{
	uint8_t data;			//RX 인터럽트로 받은 데이터 저장
	uint8_t target_CCR = 0; // 파싱된 CCR 값을 받아올 지역 변수

	while(Pop_RingBuffer(&Uart_RingBuffer, &data) == 1)
	{
		// 1. 엔터키 감지 (\r 또는 \n 모두 대응)
		if(data == '\r' || data == '\n')
		{
			// 방어 코드: 아무것도 안치고 엔터만 친 경우는 무시
			if(idx == 0) continue;
			command_line[idx] = '\0';

			// 파싱 진행 후 로직 실행
			//CLI_CMD_e cmd_result = Parsing(command_line, &target_CCR);
			//CLI_logic(cmd_result, target_CCR);

			//명령 처리가 끝났으므로 인덱스를 초기화
			Transmit_String_Fast("\r\n");
			idx = 0;
		}

		// 2. 백스페이스 감지
		else if(data == '\b' || data == 127)	//// 터미널에 따라 백스페이스가 127(DEL)로 오기도 함
		{
			if(idx >0)
			{
				idx--;
				Transmit_String_Fast("\b \b"); // 터미널 화면에서 글자 지우기 (뒤로가기 -> 공백출력 -> 뒤로가기)
			}
		}


		// 3. 일반 문자 조립
		else
		{
			command_line[idx] = (char)data;
			idx++;

			Transmit_Byte_Fast(data); // 타이핑한 글자를 화면에 즉시 보여줌 (에코)

			// 버퍼 오버플로우 방어
			if(idx >= (MAX_BUFF -1) )
			{
				idx = 0;
				Transmit_String_Fast("\r\n ERROR : Over Flow !! \r\n");
			}

		}
	}
                                           }



//------------------------------------------------
static uint8_t Service_Push_UART(uint8_t data)
{
	return Push_RingBuffer(&Uart_RingBuffer, data);
}


