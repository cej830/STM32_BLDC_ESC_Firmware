/*
 * data_struct.h
 *
 *  Created on: Jul 24, 2026
 *      Author: luke8
 */

#ifndef INC_DATA_STRUCT_DATA_STRUCT_H_
#define INC_DATA_STRUCT_DATA_STRUCT_H_

#include <stdint.h>
#include <string.h>		//memcpy를 쓰기 위해 include


typedef struct {

	uint8_t step;
	uint8_t duty;

	// ISR에서 기록하는 원시 시간 데이터
	uint16_t zc_diff_30;	//원본 속도 추정값, ZC->ZC 까지 걸리는 시간/2 , 전기각 30도
	uint16_t front_us;		//ZC가 일찍/늦게 잡히는지, 상전환->ZC
	uint16_t back_us;		//실제 30° 대기시간, ZC->상전환
	uint16_t step_us;		//실제 상전환 균일성, 전체 스텝 시간

	// 메인 루프에서 계산할 연산 결과
	//int16_t center_error_us;   //ZC 중앙 오차 방향 (음수: front < back → ZC가 스텝 앞쪽)  양수: front > back → ZC가 스텝 뒤쪽
	//uint16_t zc_pos_permille;  //ZC의 스텝 내 상대 위치

}motor_idf;



typedef struct {

	void* buff; 		//모든 데이터 타입의 포인터를 받을수 있는 변수 선언.
	uint8_t element_size;	//저장할 데이터의 크기 (byte)

    volatile uint8_t front; 	// 쓰기 인덱스 (ISR/main 공유)
    volatile uint8_t rear;  	// 읽기 인덱스 (ISR/main 공유)
    uint16_t SIZE;			// 반드시 2의 거듭제곱 크기(최대 256)

} CircleQueue;


void CreateQueue(CircleQueue* CQ, void* data, uint16_t buffer_size, uint8_t datatype_size);
uint8_t isQueFull(CircleQueue* CQ);
uint8_t isQueEmpty(CircleQueue * CQ);
uint8_t EnQueue(CircleQueue* CQ, void* byte);
uint8_t DeQueue(CircleQueue* CQ, void* out_byte);
uint8_t GetQueueLength(CircleQueue* CQ);
void ClearQueue(CircleQueue* CQ);

uint8_t EnQueueOverwrite(CircleQueue *CQ, void *data);


#endif /* INC_DATA_STRUCT_DATA_STRUCT_H_ */
