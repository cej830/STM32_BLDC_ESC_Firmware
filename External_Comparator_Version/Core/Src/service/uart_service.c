/*
 * uart_service.c
 *
 *  Created on: Jul 24, 2026
 *      Author: luke8
 */

#include "service/uart_service.h"
#include <string.h>
#include <stdlib.h>		//// atoi 사용을 위해 추가


#define MAX_BUFF 	128
#define STR_MATCH	0	//파싱함수의 strncmpy에 사용된다.


//혹은 매크로로 지정하는것과 무슨차이지?
typedef enum {
	CMD_ERROR = 0,
	CMD_CCR_CHANGE,
	CMD_PRINT_LOG,
	CMD_MONITOR
}CLI_CMD_e;;

static uint8_t uart_buff[MAX_BUFF];
static CircleQueue uart_que;

static char command_line[MAX_BUFF];
static uint8_t idx = 0;


static void PUSH_UART_Queue(uint8_t byte);
static CLI_CMD_e Parsing(char* cmd_line, uint8_t* target_CCR);
static void CLI_logic(CLI_CMD_e result, uint8_t target_CCR);

//-- include 용 함수들 --

void UART_Service_Initie()
{
	CreateQueue(&uart_que, uart_buff, MAX_BUFF, sizeof(uint8_t));
	Driver_set_Register(PUSH_UART_Queue);
	UART_Driver_Enable_RX_Interrupt();
}


void UART_Service_CLI()
{
	uint8_t byte;
	uint8_t target_CCR = 0; // 파싱된 CCR 값을 받아올 지역 변수

	while(DeQueue(&uart_que, &byte) == 1)
	{
		BLDC_Service_Monitor_OFF();

		// 1. 엔터키 감지 (\r 또는 \n 모두 대응)
		if(byte == '\r' || byte == '\n')
		{
			// 방어 코드: 아무것도 안치고 엔터만 친 경우는 무시
			if(idx == 0) continue;
			command_line[idx] = '\0';

			// 파싱 진행 후 로직 실행
			CLI_CMD_e cmd_result = Parsing(command_line, &target_CCR);
			CLI_logic(cmd_result, target_CCR);

			//명령 처리가 끝났으므로 인덱스를 초기화
			idx = 0;
		}

		// 2. 백스페이스 감지
		else if(byte == '\b' || byte == 127)	//// 터미널에 따라 백스페이스가 127(DEL)로 오기도 함
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
			command_line[idx] = (char)byte;
			idx++;

			Transmit_Byte_Fast(byte); // 타이핑한 글자를 화면에 즉시 보여줌 (에코)

			// 버퍼 오버플로우 방어
			if(idx >= (MAX_BUFF -1) )
			{
				idx = 0;
				Transmit_String_Fast("\r\n ERROR : Over Flow !! \r\n");
			}

		}
	}
}

//---- static 함수들 ----

static void PUSH_UART_Queue(uint8_t byte)
{
	EnQueue(&uart_que, &byte);
}



static CLI_CMD_e Parsing(char* cmd_line, uint8_t* target_CCR)
{
	//cmd_line 배열과 'CCR_' 배열을 4가지 요소에 대해 아스키코드 뺄셈을 시도해 매치하는지 판단한다.
	if(strncmp(cmd_line, "ccr " , 4 ) == STR_MATCH)
	{
		//ccr_"30\0" 공백 이후 포인터부터, \0 까지의 문자열을 uint8_t의 타입으로 자동으로 변환

		//atoi로 숫자 추출
		int temp = atoi((const char*)&cmd_line[4]);

		// 범위 검사 (20 ~ 100)
		if( ( temp > 20 ) && ( temp < 140 ) )
		{
			*target_CCR = (uint8_t)temp;
			return CMD_CCR_CHANGE;
		}
		// 범위를 벗어나면 ERROR로 빠짐
	}

	else if(strncmp(cmd_line, "log" , 3 ) == STR_MATCH)
	{
		return CMD_PRINT_LOG;
	}

	else if(strncmp(cmd_line, "monitor" , 7 ) == STR_MATCH)
	{
		return CMD_MONITOR;
	}

	return CMD_ERROR;

}



void CLI_logic(CLI_CMD_e CLI_CMD, uint8_t target_CCR)
{

	if(CLI_CMD != CMD_ERROR)
	{
		Transmit_String_Fast("\r\n CMD_COMPLETE !! \r\n");
	}

	switch (CLI_CMD)
	{
		case (CMD_CCR_CHANGE) :
				BLDC_Service_Change_CCR(target_CCR);
		break;

		case (CMD_PRINT_LOG) :
				BLDC_Service_ChangePrintFlag();
				break;

		case (CMD_MONITOR) :
				BLDC_Service_Monitor_ON();
				break;

		case (CMD_ERROR):
				Transmit_String_Fast("ERROR : Wrong CMD !! \r\n");
				break;
		default :
			break;

	}

}




