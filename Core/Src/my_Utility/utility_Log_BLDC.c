/*
 * Utility_LOG_bldc.c
 *
 *  Created on: 2026. 8. 27.
 *      Author: luke8
 */

#include <my_Utility/utility_Log_BLDC.h>
#include <layer_0_Driver/driver_UART.h>

#define BUFFER_SIZE		64
#define MAX_BATCH_PACKETS   16

static uint8_t is_LogRingBuffer_Full();
static uint8_t is_LogRingBuffer_Empty();

static MotorTelemetry_t motor_log[BUFFER_SIZE] = {0};
static MotorTelemetry_t tx_staging_buf[MAX_BATCH_PACKETS] = {0};

typedef struct
{
	MotorTelemetry_t* logbuffer;
	volatile uint8_t front;
	volatile uint8_t rear;
	uint8_t lenth;
}MotorTelemetryQueue_t;

static MotorTelemetryQueue_t log_queue = {
	.logbuffer = motor_log,
	.front = 0,
	.rear = 0,
	.lenth = BUFFER_SIZE
};



void Create_LogRingBuffer()
{
	log_queue.logbuffer = motor_log;
	log_queue.front = 0;
	log_queue.rear = 0;
	log_queue.lenth = BUFFER_SIZE;
}

void Clear_LogRingBuffer()
{
	log_queue.front = 0;
	log_queue.rear = 0;
}


uint8_t Push_LogRingBuffer(MotorTelemetry_t *push_data)
{
	if( is_LogRingBuffer_Full() == 1)
	{
		return 0;
	}

	else
	{
		log_queue.logbuffer[log_queue.front] = *push_data;
		log_queue.front = (log_queue.front + 1) % (log_queue.lenth);
		return 1;
	}
}

uint8_t Pop_LogRingBuffer(MotorTelemetry_t *pop_data)
{
	if( is_LogRingBuffer_Empty() == 1)
	{
		return 0;
	}

	else
	{
		*pop_data = log_queue.logbuffer[log_queue.rear];
		log_queue.rear = (log_queue.rear + 1) % (log_queue.lenth);
		return 1;
	}
}


void Service_Telemetry_Run(void)
{
    extern USBD_HandleTypeDef hUsbDeviceFS;
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef*)hUsbDeviceFS.pClassData;

    // 1. USB 하드웨어가 이전 패킷을 PC로 다 보냈는지 확인 (BUSY 상태면 리턴)
    if (hcdc == NULL || hcdc->TxState != 0)
    {
        return;
    }

    // 2. 링버퍼에 데이터가 전혀 없으면 리턴
    if (is_LogRingBuffer_Empty())
    {
        return;
    }

    // 3. 링버퍼에서 최대 MAX_BATCH_PACKETS개만큼 팝하여 전송 버퍼에 모음
    uint16_t pop_count = 0;
    while (pop_count < MAX_BATCH_PACKETS)
    {
        if (Pop_LogRingBuffer(&tx_staging_buf[pop_count]) == 1)
        {
            pop_count++;
        }
        else
        {
            break; // 링버퍼가 비었으면 반복 종료
        }
    }

    // 4. 모인 패킷 일괄 전송
    if (pop_count > 0)
    {
        uint16_t total_tx_bytes = pop_count * sizeof(MotorTelemetry_t);
        CDC_Transmit_FS((uint8_t*)tx_staging_buf, total_tx_bytes);
    }
}


//FULL -> next write position reaches the read position (one slot reserved)
static uint8_t is_LogRingBuffer_Full()
{
	if(((log_queue.front + 1) % (log_queue.lenth)) == log_queue.rear )
	{
		return 1;
	}
	else
	{
		return 0;
	}
}


//Empty -> front == rear
static uint8_t is_LogRingBuffer_Empty()
{
	if(log_queue.front == log_queue.rear)
	{
		return 1;
	}
	else
	{
		return 0;
	}
}
