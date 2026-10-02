/*
 * driver_RingBuffer.c
 *
 *  Created on: 2026. 8. 22.
 *      Author: luke8
 */

#include "my_Utility/utility_RingBuffer.h"
#define true 1
#define false 0


void Create_RingBuffer(RingBuffer* ringbuffer, uint8_t* adress, uint16_t buff_len)
{
	ringbuffer->buffer = adress;
	ringbuffer->front = 0;
	ringbuffer->rear = 0;
	ringbuffer->buff_len = buff_len;
}

void Clear_RingBuffer(RingBuffer* ringbuffer)
{
	ringbuffer->front = 0;
	ringbuffer->rear = 0;
}


//Full check -> (rear + 1) % M == front
uint8_t is_RingBuffer_Full(RingBuffer* ringbuffer)
{
	uint8_t result = ( ringbuffer->rear + 1 ) % ringbuffer->buff_len;

	if(result == ringbuffer->front) return true;
	else return false;
}

//Empty check -> front == rear
uint8_t is_RingBuffer_Empty(RingBuffer* ringbuffer)
{

	if(ringbuffer->front == ringbuffer->rear) return true;
	else return false;
}

uint8_t Push_RingBuffer(RingBuffer* ringbuffer, uint8_t input_data)
{
	if(is_RingBuffer_Full(ringbuffer) == true) return false;

	ringbuffer->buffer[ringbuffer->rear] = input_data;
	ringbuffer->rear = ( ringbuffer->rear + 1 ) % ringbuffer->buff_len;

	return true;

}

uint8_t Pop_RingBuffer(RingBuffer* ringbuffer, uint8_t* output_data)
{
	if(is_RingBuffer_Empty(ringbuffer) == true) return false;

	*output_data = ringbuffer->buffer[ringbuffer->front];
	ringbuffer->front = ( ringbuffer->front + 1 ) % ringbuffer->buff_len;
	return true;

}
