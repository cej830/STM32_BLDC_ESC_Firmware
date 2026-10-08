/*
 * Utility_LOG_bldc.h
 *
 *  Created on: 2026. 8. 27.
 *      Author: luke8
 */

#ifndef INC_MY_UTILITY_UTILITY_LOG_BLDC_H_
#define INC_MY_UTILITY_UTILITY_LOG_BLDC_H_

#include "stm32f1xx.h"
#include "usbd_cdc_if.h"

#define HEADER 	0xAA
#define TAIL	0xBB

#pragma pack(push, 1)
typedef struct
{
	uint8_t  header;			//0xAA 패킷 동기화용

	//uint16_t phase_A;			//ADC Phase A
	//uint16_t phase_B;			//ADC Phase B
	//uint16_t phase_C;			//ADC Phase C
	//uint16_t vcom_adc;			//ADC Vcom (비교용)

	//uint16_t ccr_target;		//타이머 타겟 CCR
	uint16_t ccr_current;		//타이머 현재 CCR

	uint8_t  info;				// step/ OL-CL/ ZC_event

	//int16_t BEMF_prev;			//이전샘플의 BEMF 값
	int16_t BEMF_curr;			//현재 샘플의 BEMF값 (* tempor)

	uint16_t timestamp_start;	//스텝 시작 직후 CNT값
	//uint16_t timestamp_prev;	//이전 샘플에서 ADC ISR 진입시 CNT값
	uint16_t timestamp_curr;	//현재 샘플에서 ADC ISR 진입시 CNT값  (* tempor)
	uint16_t timestamp_zc;		//선형보간으로 계산된 ZC 발생시의 CNT값 (* tempor)

	//uint16_t delay_target;		//이전 스텝의 ZC 발생값에 의해 결정된 30도 전기각 시간 (* tempor)
	uint16_t delay_limited;		//리미터를 적용한 30도 전기각 시간				  (* tempor)
	uint16_t delay_trigger;		//30도 전기각 시간을 맞추기 위해 현재 샘플에서 트리거할 대기시간 (* tempor)

	uint8_t  delay_PAR;			//딜레이 제어 증감 파라미터

	uint8_t  tail;				//0xBB 패킷 종료 검증용

}MotorTelemetry_t; 
#pragma pack(pop)


void Create_LogRingBuffer();
void Clear_LogRingBuffer();
uint8_t Push_LogRingBuffer(MotorTelemetry_t *push_data);
uint8_t Pop_LogRingBuffer(MotorTelemetry_t *pop_data);

void Service_Telemetry_Run(void);



#endif /* INC_MY_UTILITY_UTILITY_LOG_BLDC_H_ */
