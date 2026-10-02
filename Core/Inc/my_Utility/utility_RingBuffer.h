/*
 * driver_RingBuffer.h
 *
 *  Created on: 2026. 8. 22.
 *      Author: luke8
 */

#ifndef INC_DRIVER_RINGBUFFER_H_
#define INC_DRIVER_RINGBUFFER_H_

#include <stdint.h>


typedef struct
{
	uint8_t* buffer;
	uint8_t front;
	uint8_t rear;
	uint8_t buff_len;

}RingBuffer;


void Create_RingBuffer(RingBuffer* ringbuffer, uint8_t* adress, uint16_t buff_len);
void Clear_RingBuffer(RingBuffer* ringbuffer);

uint8_t is_RingBuffer_Full(RingBuffer* ringbuffer);
uint8_t is_RingBuffer_Empty(RingBuffer* ringbuffer);

uint8_t Push_RingBuffer(RingBuffer* ringbuffer, uint8_t input_data);
uint8_t Pop_RingBuffer(RingBuffer* ringbuffer, uint8_t* output_data);


#endif /* INC_DRIVER_RINGBUFFER_H_ */
