/*
 * uart_service.c
 *
 *  Created on: Jul 24, 2026
 *      Author: luke8
 */


#include "data_struct/data_struct.h"


// 1. 큐 초기화
void CreateQueue(CircleQueue* CQ, void* data, uint16_t buffer_size, uint8_t datatype_size)
{
    CQ->buff = data;
    CQ->element_size = datatype_size;
    CQ->front = 0;
    CQ->rear = 0;
    CQ->SIZE = buffer_size;
}

// 2. 큐가 꽉 찼는지 확인
uint8_t isQueFull(CircleQueue* CQ)
{
    uint8_t next_front = (CQ->front + 1) & (CQ->SIZE-1);
    if(next_front == CQ->rear) return 1;
    else return 0;
}

// 3. 큐가 비어있는지 확인
uint8_t isQueEmpty(CircleQueue * CQ)
{
    if(CQ->front == CQ->rear) return 1;
    else return 0;
}

// 4. 데이터 넣기 (모든 타입을 받기 위해 void* 사용)
uint8_t EnQueue(CircleQueue* CQ, void* data)
{
    if(isQueFull(CQ)) return 0;

    // 1바이트 단위 포인터(uint8_t*)로 캐스팅 후, 정확한 목적지 주소 계산
    uint8_t* target_addr = (uint8_t*)CQ->buff + (CQ->front * CQ->element_size);

    // 계산된 주소에 외부 데이터(data)를 element_size만큼 복사
    memcpy(target_addr, data, CQ->element_size);

    CQ->front = (CQ->front + 1) & (CQ->SIZE-1);

    return 1;
}


uint8_t EnQueueOverwrite(CircleQueue *CQ, void *data)
{
    uint8_t next_front = (CQ->front + 1) & (CQ->SIZE-1);

    if(next_front == CQ->rear)
    {
        // 가장 오래된 데이터 폐기
        CQ->rear = (CQ->rear + 1U) & (CQ->SIZE-1);
    }

    uint8_t *target =
        (uint8_t *)CQ->buff +
        (CQ->front * CQ->element_size);

    memcpy(target, data, CQ->element_size);
    CQ->front = next_front;

    return 1;
}


// 5. 데이터 빼기 (모든 타입을 내보내기 위해 void* 사용)
uint8_t DeQueue(CircleQueue* CQ, void* out_data)
{
    if(isQueEmpty(CQ)) return 0;

    // 데이터를 빼낼 출발지 주소 계산
    uint8_t* source_addr = (uint8_t*)CQ->buff + (CQ->rear * CQ->element_size);

    // 출발지 주소의 데이터를 외부 변수(out_data)에 복사
    memcpy(out_data, source_addr, CQ->element_size);

    CQ->rear = (CQ->rear + 1) & (CQ->SIZE-1);

    return 1;
}

// 6. 데이터 빼지 않고 읽기만 하기 (Peek 역할)
uint8_t ReadQueue(CircleQueue* CQ, void* out_data)
{
    if(isQueEmpty(CQ)) return 0;

    uint8_t* source_addr = (uint8_t*)CQ->buff + (CQ->rear * CQ->element_size);
    memcpy(out_data, source_addr, CQ->element_size);

    return 1;
}

// 7. 현재 큐에 들어있는 데이터 개수 확인
uint8_t GetQueueLength(CircleQueue* CQ)
{
    if(isQueEmpty(CQ)) return 0;

    uint8_t count = (CQ->front - CQ->rear + CQ->SIZE) & (CQ->SIZE-1);
    return count;
}

// 8. 큐 초기화 (비우기)
void ClearQueue(CircleQueue* CQ)
{
    CQ->front = 0;
    CQ->rear = 0;
}


