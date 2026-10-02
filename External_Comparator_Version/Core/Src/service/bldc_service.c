/*
 * bldc_service.c
 *
 *  Created on: Jun 27, 2026
 *      Author: luke8
 */

#include "data_struct/data_struct.h"
#include "driver/uart_driver.h"

#include "service/bldc_service.h"

#include "main.h"
#include <stdio.h> // sprintf를 위해 추가


#define MAX_LOG_BUFF 		128
#define MAX_MONITOR_BUFF 	16


//메인에서 초기화 , 메인과 인터럽트(버튼)에서 갱신됨
static volatile MOTOR_STATE motor_state = MOTOR_IDLE;

static uint8_t print_flag = 0;
static uint8_t monitor_flag = 0;


static motor_idf motor_info[MAX_LOG_BUFF];	//메인에서  초기화되고,인터럽트에서 호출되어 갱신된다.
static CircleQueue log_queue;			//메인에서  초기화되고,인터럽트에서 호출되어 갱신된다.

static motor_idf motor_monitor[MAX_MONITOR_BUFF];	//메인에서  초기화되고,인터럽트에서 호출되어 갱신된다.
static CircleQueue monitor_queue;					//메인에서  초기화되고,인터럽트에서 호출되어 갱신된다.

static void BLDC_Service_LOG_EnQueue();		//드라이버의 TIM6 인터럽트 완료 함수에서 콜백시 호출되는 함수.
static void BLDC_Service_MONITOR_EnQueue();
static void Print_LOG(CircleQueue* CQ);

void Log_Inite()
{
	CreateQueue(&log_queue, motor_info, MAX_LOG_BUFF, sizeof(motor_idf));
	CreateQueue(&monitor_queue, motor_monitor, MAX_MONITOR_BUFF, sizeof(motor_idf));

	Driver_SetRegister_LOG(BLDC_Service_LOG_EnQueue);
	Driver_SetRegister_MONITOR(BLDC_Service_MONITOR_EnQueue);
}


static void BLDC_Service_LOG_EnQueue()	//드라이버에서 콜백시 호출된다.
{
	motor_idf temp;
	Send_Motorlog(&temp);
	EnQueueOverwrite(&log_queue, &temp);
}



static void BLDC_Service_MONITOR_EnQueue()	//드라이버에서 콜백시 호출된다.
{
	motor_idf temp;
	Send_Motorlog(&temp);
	EnQueue(&monitor_queue, &temp);
}


void BLDC_Service_Inite()
{
	Motor_Inite();
	Log_Inite();
	motor_state = MOTOR_IDLE;
}


// 메인 루프 서비스
void BLDC_Service()
{
    switch (motor_state)
    {
    	case MOTOR_IDLE:

    		if(print_flag == 1)
    		{
    			print_flag = 0;
    			Transmit_String_Fast("@START,BLDC_LOG,V1\r\n");
    			Print_LOG(&log_queue);
    			Transmit_String_Fast("@END\r\n");
    		}


    		break;

    	case MOTOR_START_REQUEST:
    		Motor_Start_Request();	//플래그 변수들을 처음으로 초기화.
    		motor_state = MOTOR_OPEN_LOOP;
    		ClearQueue(&log_queue);

    		Transmit_String("MOTOR START ! (Ramping)\r\n");
    		break;

    	case MOTOR_OPEN_LOOP:
    	case MOTOR_CLOSE_LOOP:

    		MOTOR_ERROR ERROR_report = Get_Motor_Error();
    		if(ERROR_report.error_code != NO_ERROR)	//폴링방식으로 지속적으로 error 변수를 감시
    		{
    			Clear_Motor_Error();
    			motor_state = MOTOR_STOP;
    			char print_buf[128];

    			if(ERROR_report.error_code == TIME_OUT_ERROR)
    			{
    				Transmit_String("ERROR: MOTOR STALLED! (TIME OUT ERROR)\r\n");
    				sprintf(print_buf, "CTP: %4u LTP: %4u \r\n", ERROR_report.current_timestamp, ERROR_report.last_timestamp);
    				Transmit_String_Fast(print_buf);
    			}

    			else if(ERROR_report.error_code == ZC_DETECT_ERROR)
    			{
    				Transmit_String("ERROR: MOTOR STALLED! (ZC_DETECT ERROR)\r\n");
    				sprintf(print_buf, "FRONT: %4u LAST_FROUNT_4: %4u \r\n", ERROR_report.current_timestamp, ERROR_report.last_timestamp);
    				Transmit_String_Fast(print_buf);
    			}

    			break;
    		}


    		if(motor_state == MOTOR_OPEN_LOOP)
    		{
    			// 드라이버에게 오픈루프 구동을 지시하고, 완료되었는지 확인
    			if(Motor_Run_First() == 1)
    			{
    			   // 반환값이 1이면 , 오픈루프 종료 -> 클로즈드 루프로 전환 완료된 것
    			   motor_state = MOTOR_CLOSE_LOOP;
    			   Transmit_String("ENTERED CLOSED LOOP !\r\n");
    			}
    		}


    		if(motor_state == MOTOR_CLOSE_LOOP)
    		{
    			//모터가 클로즈 루프에 넘어온 경우 실행되는 영역.
    			if(monitor_flag == 1)
    			{
    				Print_LOG(&monitor_queue);
    			}
    		}

    		break;


    	case MOTOR_STOP:
    		Motor_Stop();	//
    		motor_state = MOTOR_IDLE;

    		Transmit_String("MOTOR STOP !\r\n\n");
    		break;

    	default:
    		motor_state = MOTOR_STOP;
    		break;
    }
}


void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    if (GPIO_Pin == BTN_INPUT_Pin)
    {
        if (motor_state == MOTOR_IDLE)
        {
        	motor_state = MOTOR_START_REQUEST;
        }
        else if (motor_state == MOTOR_OPEN_LOOP || motor_state == MOTOR_CLOSE_LOOP)
        {
        	motor_state = MOTOR_STOP;
        }
    }
}


void Print_LOG(CircleQueue* CQ)
{
	motor_idf temp;

	while( DeQueue(CQ, &temp) == 1)	//큐가 차있으면,
	{

		// 중앙 오차 계산 (front - back)
		int16_t center_error_us = (int16_t)(temp.front_us - temp.back_us);


		uint32_t RPM = RPM_From_ZcDiff(temp.zc_diff_30*2);

		// ZC 위치 퍼밀(1/1000) 계산 (0 나누기 방지)
		uint16_t total_time = temp.front_us + temp.back_us;
		uint16_t zc_pos_permille = 0;

		if(total_time > 0)
		{
			// 32비트 캐스팅 필수: front_us * 1000 은 16비트를 넘어감
			zc_pos_permille = (uint16_t)(((uint32_t)temp.front_us * 1000) / total_time);
		}
		else
		{
		    zc_pos_permille = 0;
		}



		// 2. UART 문자열 조립 및 전송
		char print_buf[128];
		sprintf(print_buf, "ST:%d|R:%4lu|D:%2d| F:%4u B:%4u S:%4u |Err:%4d Pos:%3u\r\n",
		            temp.step, RPM, temp.duty,
		            temp.front_us, temp.back_us, temp.step_us,
		            center_error_us, zc_pos_permille);

	    // 2. 조립된 문자열을 UART로 전송합니다.
		Transmit_String_Fast(print_buf);

	}
}


void BLDC_Service_Change_CCR(uint8_t target_CCR)
{
	//서비스 함수 동작 예상
	char temp[128];
	sprintf(temp,"\r\n Change CCR to %d !! \r\n", target_CCR);
	Transmit_String_Fast(temp);
	BLDC_Driver_Change_Duty(target_CCR);
}


void BLDC_Service_ChangePrintFlag()
{
	if(motor_state == MOTOR_IDLE)
	{
		Transmit_String_Fast("\r\n Print Motor LOG !! \r\n");
		print_flag = 1;
	}

	else
	{
		Transmit_String_Fast("\r\n ERROR: Change MotorState IDLE !! \r\n");
	}
}

void BLDC_Service_Monitor_ON()
{
	if(monitor_flag == 0) monitor_flag = 1;
	Transmit_String_Fast("\r\n Monitor ON  !! \r\n");
}

void BLDC_Service_Monitor_OFF()
{
	 monitor_flag= 0;
	//Transmit_String_Fast("\r\n Monitor OFF  !! \r\n");
}



