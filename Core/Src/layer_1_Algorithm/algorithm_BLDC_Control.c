/*
 * algorithm_BLDC_Control.c
 *
 *  Created on: 2026. 8. 27.
 *      Author: luke8
 */


#include "layer_1_Algorithm/algorithm_BLDC_Control.h"


#define MAX_TIME_OUT 				5000
#define BLANKING_TIME 				50
#define ISR_LATENCY					19


/*
#define START_CCR					220
#define START_OPEN_LOOP_DELAY		15000	//15ms
#define LAST_OPEN_LOOP_DELAY		8000	//5ms
*/


// 디버거에서 실시간 수정 가능한 변수들
static volatile uint16_t START_CCR = 220;
static volatile uint16_t START_OPEN_LOOP_DELAY = 10000;
static volatile uint16_t LAST_OPEN_LOOP_DELAY = 6000;


static volatile int16_t THRESHOLD_UP = 	5;
static volatile int16_t THRESHOLD_DOWN = -5;


#define HALF_ARR 900


//스텝 시작후 현재 까지 걸린 시간 측정 변수

//ZC발생후 전기각 30도 지연 대기 시간.
static volatile uint16_t PAR = 50;
static volatile MotorStatus_t motorstate = OPEN_LOOP;

//------------오픈 루프 동작 관련 변수
static uint16_t OpenLoop_delay_us = 0;
static uint8_t OpenLoop_count = 0;

//-----------모터 상 전압 기록--------------
static volatile uint16_t PhaseA;
static volatile uint16_t PhaseB;
static volatile uint16_t PhaseC;
static volatile uint16_t VCOM;
static volatile uint16_t sw_VCOM;


static volatile MotorError_t motor_error = NO_ERROR;


static volatile MotorControl motorcontrol = {0};
static volatile ZC_Management zc_manage = {0};
static volatile ZC_History zc_history = {0};
static volatile ZC_Over_cnt zc_over_cnt = {0};

//---------------에러 관리 함수------------------------
void ClearError();
MotorError_t Get_ErrorCode();


//----------동작 관련 함수------------------
void Algo_BLDC_Init();
void Algo_BLDC_Startup();
uint8_t Algo_BLDC_RunOpenloop();

//------------BLDC 관련 ISR 에서 콜백할 함수-----------------
static void Algo_BLDC_AdcISRCallback();
static void Algo_BLDC_TimISRCallback();

//-------------BEMF를 ADC로 받아서 ZC를 알아내는 함수
static int16_t Read_BEMF(uint8_t step, uint16_t Vcom);
static inline uint8_t is_ZeroCrossing_Occur(uint8_t step , int16_t BEMF_curr, int16_t BEMF_prev, uint8_t is_first);

//-----------LOG 작성을 위해 팩킹하는 함수
static inline void Packing_Motor_Log(MotorTelemetry_t* log, Motorlog_Temporary* tempor);

//-------------Commutation 에 관련된 함수
static void sixstep(uint8_t step , uint16_t new_CCR);
static inline uint16_t cal_Edgree_Delay_time(uint16_t current_time, uint16_t last_time, uint16_t step_start,uint8_t is_first );
static uint16_t Get_Actual_Delaytime(uint16_t current_delay, uint16_t target_delay, uint16_t PAR, uint8_t is_First);

void ClearError() { motor_error = NO_ERROR; }
MotorError_t Get_ErrorCode() { return motor_error; }


void Algo_BLDC_Init()
{
	Driver_BLDC_HW_SetFuncAdress(Algo_BLDC_AdcISRCallback, Algo_BLDC_TimISRCallback);
}


void Algo_BLDC_Startup()
{
	Driver_BLDC_HW_Startup();

	zc_manage.zc_searching = 0;			//ZC계산분기 ADC 플래그 RESET
	zc_manage.zc_first_sample = 0;

	motorcontrol.motor_first_closeloop = 0;
	motorcontrol.motorstate = OPEN_LOOP;
	OpenLoop_count = 0;
	OpenLoop_delay_us = START_OPEN_LOOP_DELAY;

	motorcontrol.step = 1;
	motorcontrol.CCR = START_CCR;
	motorcontrol.target_CCR = START_CCR;

	zc_over_cnt.cnt_delay_over = 0;
	zc_over_cnt.cnt_elapsed_over = 0;

	Clear_LogRingBuffer();
	sixstep(motorcontrol.step, motorcontrol.CCR);
}


/* 오픈루프 동작을 수행하는 함수 @return | uint8_t
 * 오픈루프를 돌면서 전기각 1바퀴마다, 카운트 증가
 * 오픈루프 상태일때 return 0, 클로즈 루프로 상태전환시 return 1
 */
uint8_t Algo_BLDC_RunOpenloop()
{

	//2. 현재 스텝 인가 및 시간 기록
	zc_manage.timestamp_start = Driver_Time_Get_Us();
	sixstep(motorcontrol.step, motorcontrol.CCR);

	//3. 지연 대기
	Driver_Delay_Us(OpenLoop_delay_us);

	//4. 스텝 진행 및 바퀴 수 카운트
	motorcontrol.step++;
	if(motorcontrol.step > 6 )
	{
		motorcontrol.step = 1;
		OpenLoop_count++;	//전기각 1바퀴 완료.
	}

	//5. LAST 속도 도달전 감속 로직
	if(OpenLoop_delay_us > LAST_OPEN_LOOP_DELAY)
	{
		// 구간 1: 극초반 탈출 (15000us ~ 10000us) -> 관성이 붙기 시작하는 구간, 굵게 감소
		if(OpenLoop_delay_us > 10000)
		{
			if(OpenLoop_count >= 2)
			{
				OpenLoop_count = 0;
				OpenLoop_delay_us -= 500; //250us씩 큼직하게 감소
			}
		}

		// 구간 2: 중속 영역 (10000us ~ 7000us) -> 속도가 붙은 상태
		else if(OpenLoop_delay_us > 7000)
		{
			if(OpenLoop_count >= 3)
			{
				OpenLoop_count = 0;
				OpenLoop_delay_us -= 250; //100us씩 감소
			}
		}

		// 구간 3: 목표 도달 직전 (7000us ~ LASTus) -> 급가속 방지 및 부드러운 접근
		else
		{
			if(OpenLoop_count >= 4)
			{
				OpenLoop_count = 0;
				OpenLoop_delay_us -= 100; //30us씩 감소
			}
		}

		if(OpenLoop_delay_us < LAST_OPEN_LOOP_DELAY)
		{
			OpenLoop_delay_us = LAST_OPEN_LOOP_DELAY;
		}
	}

	//6. 오픈루프에서 로그 모두 채우고나서 클로즈 루프로 전환시작.
	if(OpenLoop_delay_us <= LAST_OPEN_LOOP_DELAY && OpenLoop_count >= 10)
	{
		motorcontrol.motor_first_closeloop = 1;
		sixstep(motorcontrol.step, motorcontrol.CCR);
		Driver_BLDC_HW_SetTimTrig(OpenLoop_delay_us);
		return 1;
	}


	zc_history.current_delay = OpenLoop_delay_us;
	return 0;
}


static inline void Packing_Motor_Log(MotorTelemetry_t* log, Motorlog_Temporary* tempor)
{

	uint8_t info = (uint8_t)(motorcontrol.step & 0x0F);

	if(motorcontrol.motorstate != OPEN_LOOP)
	{
		info |= (1U << 4);
	}

	if(tempor->log_zc_event)
	{
		info |= (1U << 5);
	}

	log->info = info;

	log->header = HEADER;

	//log->phase_A = PhaseA;
	//log->phase_B = PhaseB;
	//log->phase_C = PhaseC;
	//log->vcom_adc =VCOM;

	//log->ccr_target  = motorcontrol.target_CCR;
	log->ccr_current = motorcontrol.CCR;

	//log->BEMF_prev = zc_history.BEMF_prev;
	log->BEMF_curr = tempor->log_BEMF_curr;

	log->timestamp_start = zc_manage.timestamp_start;
	//log->timestamp_prev = zc_history.timestamp_prev;
	log->timestamp_curr = tempor->log_timestamp_curr;
	log->timestamp_zc =	tempor->log_timestamp_zc;

	//log->delay_target  = tempor->log_delay_target;
	log->delay_limited = zc_history.current_delay;
	log->delay_trigger = tempor->log_delay_trigger;
	log->delay_PAR = zc_manage.CNT;

	log->tail = TAIL;
}


/*
ZC_Status_t Validate_ZC_Duration(uint16_t duration, uint16_t last_duration, uint8_t is_first)
{
	if(is_first)
	{
		return ZC_VALID;
	}

	uint16_t diff;

	if(duration >= last_duration)
	{
		diff = duration - last_duration;
	}

	else
	{
		diff = last_duration - duration;
	}

	//step_duration과 last_duration이 X 이내로 차이날때, valid
	if( diff <= ZC_VALID_RANGE)
	{
		return ZC_VALID;
	}

	//step_duration과 last_duration이 X 이내 X2 이내로 차이날때, Risk
	if( diff <= ZC_RISK_RANGE)
	{
		return ZC_RISK;
	}

	//step_duration과 last_duration이 X2 보다 더 차이날때, Rejected
	return ZC_REJECT;
}
*/


uint16_t Get_Linear_ZC(uint16_t t_curr, uint16_t t_prev, int16_t BEMF_current, int16_t BEMF_prev )
{
	// t_zc = t_prev + (t_curr - t_prev) * {|Bprev|/(|Bprev| + |Bcurr|)}

	// 1. 절대값 변환 (음수 부호 제거)
	int16_t b_prev = (BEMF_prev < 0) ? -BEMF_prev : BEMF_prev;
	int16_t b_curr = (BEMF_current < 0) ? -BEMF_current : BEMF_current;

	// 2. 분모 계산, 분모가 0인 경우 예외 처리 (보간 불가능하므로 현재 sample timestamp 사용)
	uint32_t den = (uint32_t)(b_prev + b_curr);
	if (den == 0)
	{
		return t_curr;
	}

	// 3. 실제 두 샘플 사이의 시간 차이 (타이머 롤오버 안전)
	uint16_t dt = (uint16_t)(t_curr - t_prev);
	// 비정상적인 dt 발생시 t_curr로 리턴
	if(dt == 0 || dt > 100)
	{
		return t_curr;
	}

	//4. 정수 보간 계산, 반올림 포함
	uint32_t num = (uint32_t)b_prev * dt;
	uint16_t zc_offset = (uint16_t)((num + (den / 2U)) / den);
	if(zc_offset > dt)
	{
		zc_offset = (uint16_t)dt;
	}

	return (uint16_t)(t_prev + zc_offset);
}




void Algo_BLDC_AdcISRCallback()
{
	//Get timestamp and Duration.
	uint16_t timestamp_curr = Driver_Time_Get_Us();
	uint16_t duration = (uint16_t)(timestamp_curr - zc_manage.timestamp_start);

	//Block ADC value until step_duration is less than BLANKINGTIME
	if(duration < BLANKING_TIME)
	{
		return;
	}

	MotorTelemetry_t motor_log = {0};
	Motorlog_Temporary tempor = {0};

	//From ADC , Get Phase Voltage, sw_VCOM, BEMF
	Driver_BLDC_HW_GetPhaseV(&PhaseA, &PhaseB, &PhaseC, &VCOM);
	sw_VCOM = (uint16_t)(((uint32_t)PhaseA + (uint32_t)PhaseB + (uint32_t)PhaseC)/3);

	int16_t BEMF_curr = Read_BEMF(motorcontrol.step, sw_VCOM);

	tempor.log_timestamp_curr = timestamp_curr;
	tempor.log_BEMF_curr = BEMF_curr;

	//ZC 감지 플래그가 true 일때
	if(zc_manage.zc_searching == 1)
	{
		if(duration > 60000)
		{
			// 디버깅 동안만 남길 수 있음
			tempor.log_delay_trigger = 9998;
			Packing_Motor_Log(&motor_log, &tempor);
			motor_log.delay_PAR = zc_manage.CNT++;
			Push_LogRingBuffer(&motor_log);
			return;
		}
		//ZC 감지를 TIMEOUT 이내에 못하면 에러발생.
		if(duration > MAX_TIME_OUT)
		{
			tempor.log_delay_trigger = 9999;
			Packing_Motor_Log(&motor_log, &tempor);
			motor_log.delay_PAR = zc_manage.CNT++;
			Push_LogRingBuffer(&motor_log);

			Driver_BLDC_HW_Stop();
			motor_error = TIME_OUT;
			return;
		}

		uint8_t zc_event = 0;
		zc_event = is_ZeroCrossing_Occur(motorcontrol.step,
										 BEMF_curr,
										 zc_history.BEMF_prev,
										 zc_manage.zc_first_sample);

		if(zc_event == 1)//ZC가 발생한 경우
		{
			//션형근사를 통한 ZC 발생 timestamp를 구하기.

			//1. 선형보간을 통해 두 ADC sample 사이의 실제 ZC timestamp 추정

			uint16_t timestamp_zc = Get_Linear_ZC(timestamp_curr,
										 	 	 	zc_history.timestamp_prev,
													BEMF_curr,
													zc_history.BEMF_prev);

			tempor.log_timestamp_zc = timestamp_zc;
			//timestamp_zc = timestamp_curr;


			//2. 스텝 시작 -> 보간 ZC 까지의 시간 계산
			uint16_t zc_duration = (uint16_t)(timestamp_zc - zc_manage.timestamp_start);


			//3. ZC-to-ZC 60도 로부터 30도 target delay 계산
			uint16_t target_delay = cal_Edgree_Delay_time(timestamp_zc,
															zc_history.timestamp_last_zc,
															zc_duration,
															motorcontrol.motor_first_closeloop);

			//4. 레이트 리미터(PAR) 적용하여 급격한 delay 변화 안정화
			zc_history.current_delay = Get_Actual_Delaytime(zc_history.current_delay,
															target_delay,
															PAR,
															motorcontrol.motor_first_closeloop);

			//5. zc 이후 지금까지 흘러간 시간 duration 계산
			uint16_t elapsed_since_zc = (uint16_t)(timestamp_curr - timestamp_zc);
			if(elapsed_since_zc > 100)
			{
				elapsed_since_zc = 0;
				zc_over_cnt.cnt_elapsed_over++;
			}

			//6. 타이머에 트리거할 30도 딜레이 시간을 계산.
			uint16_t delay_time = 1;
			//uint16_t delay_time = zc_history.current_delay - elapsed_since_zc;

			uint16_t total_elapsed = elapsed_since_zc + ISR_LATENCY;
			if(zc_history.current_delay > total_elapsed)
			{
				delay_time = zc_history.current_delay - total_elapsed;
			}

			else
			{
				delay_time = 1;
				zc_over_cnt.cnt_delay_over++;
			}

			//로그 기록, 지역변수 값들
			tempor.log_zc_event = zc_event;
			tempor.log_delay_target = target_delay;
			tempor.log_delay_limited = zc_history.current_delay;
			tempor.log_delay_trigger = delay_time;

			//상태(플래그) 명시적 업데이트
			motorcontrol.motor_first_closeloop = 0;
			zc_history.timestamp_last_zc = timestamp_zc;
			zc_manage.zc_searching = 0;

			//TIM3로 전기각 30도 대기시간 트리거
			Driver_BLDC_HW_SetTimTrig(delay_time);
		}
	}

	Packing_Motor_Log(&motor_log, &tempor);
	motor_log.delay_PAR = zc_manage.CNT++;
	Push_LogRingBuffer(&motor_log);

	//플래그 명시적 업데이트 & last값 갱신.
	zc_manage.zc_first_sample = 0;
	zc_history.BEMF_prev = BEMF_curr;
	zc_history.timestamp_prev = timestamp_curr;
}



void Algo_BLDC_TimISRCallback()
{
	Driver_BLDC_HW_SetTim3OFF();

	if(motorcontrol.motorstate == OPEN_LOOP)
	{
		motorcontrol.motorstate = CLOSE_LOOP;
	}

	motorcontrol.step++;
	if(motorcontrol.step > 6) motorcontrol.step = 1;

	if(motorcontrol.step == 1)
	{
		//target_CCR = Get_Target_CCR();		//포텐셔미터의 서비스 함수
		if(motorcontrol.CCR < motorcontrol.target_CCR)
		{
			motorcontrol.CCR++;
		}
		else if (motorcontrol.CCR > motorcontrol.target_CCR)
		{
			motorcontrol.CCR--;
		}
	}

	sixstep(motorcontrol.step, motorcontrol.CCR);

	zc_manage.timestamp_start = Driver_Time_Get_Us();
	zc_manage.zc_searching = 1;
	zc_manage.zc_first_sample = 1;
}


/* 레이트 리미터: 목표 딜레이로 점진적 수렴 */
uint16_t Get_Actual_Delaytime(uint16_t current_delay, uint16_t target_delay, uint16_t PAR, uint8_t is_First)
{
	// 첫번째 CL에 진입한 경우, 30도 전기각 딜레이 시간은 target_dealy 을 동일하게 적용한다.
	if(is_First == 1)
	{
		return target_delay;
	}

	// 1. target_delay 가 더 긴 경우, actual_delay는 PAR만큼 점진적으로 증가한다.
	//-> 급감속을 방지하고 PAR 만큼 점진적으로 감속한다.
	if(target_delay > current_delay)
	{
		//뺄셈으로 먼저 차이를 계산하여 오버슈트 방지
		if((uint16_t)(target_delay - current_delay) > PAR)
		{
			return (current_delay + PAR);
		}

		else
		{
			return target_delay;	// 잔여 차이가 PAR 이하이면 목표치에 정확히 안착
		}
	}

	// 2. target_delay 가 더 짧은 경우, actual_delay는 PAR만큼 점진적으로 감소 한다.
	//-> 급가속을 방지하고 PAR 만큼 점진적으로 가속한다.
	if(target_delay < current_delay)
	{
		// 뺄셈으로 차이를 먼저 비교
		if((uint16_t)(current_delay - target_delay) > PAR)
		{
			// 안전 가드: 언더플로우 원천 차단
			if(current_delay > PAR)
			{
				return (current_delay - PAR);
			}

			else
			{
				return target_delay;
			}
		}

		else
		{
			return target_delay;	// 잔여 차이가 PAR 이하이면 목표치에 정확히 안착
		}

	}

	//3. 타겟 딜레이 시간과 현재 딜레이시간이 같을때,
	return current_delay;

}

/* 현재 스텝에 맞추어 BEMF 값을 Get 하는 함수 @ return | int16_t
 * @ uint8_t  | step : 현재 스텝
 */
static inline int16_t Read_BEMF(uint8_t step, uint16_t Vcom)
{
	uint16_t floating_phase;

	switch (step)
	{
	case 1: case 4: floating_phase = PhaseC; break;
	case 2: case 5: floating_phase = PhaseB; break;
	case 3: case 6: floating_phase = PhaseA; break;
	default :
		break;
	}

	int16_t BEMF =  (int16_t)floating_phase - (int16_t)Vcom;
	return BEMF;
}


static inline uint8_t is_ZeroCrossing_Occur(uint8_t step , int16_t BEMF_curr, int16_t BEMF_prev, uint8_t is_first)
{
	//현재 step 에서 six_step 처음 발생시 ZC 발생 X 처리.
	if(is_first)
	{
		return 0;
	}

	switch (step)
	{
	//스텝 1, 3, 5 는 폴링 엣지, BEMF + 에서 - , 발생시 ZC 발생
	case 1: case 3: case 5:
			if( (BEMF_prev >=0) && (BEMF_curr < 0)) return 1;
			else return 0;
			break;

	//스텝 2, 4, 6 는 라이징 엣지, BEMF - 에서 + , 발생시 ZC 발생
	case 2: case 4: case 6:
			if( (BEMF_prev <=0) && (BEMF_curr > 0)) return 1;
			else return 0;
			break;

		default:
			return 0;
			break;
	}
}

/* 전기각 30도의 대기시간(us)를 계산하는 함수. @ return | uint16_t
 * @ current_time 	: 현재 ZC 감지시간
 * @ last_time		: 이전 ZC 감지시간
 * @ laptime		: 스텝 시작부터 ZC검출 까지의 시간	(첫 진입시 사용)
 * @ is_first		: Close-Loop 처음진입인지 아닌지
 */
static inline uint16_t cal_Edgree_Delay_time(uint16_t current_time, uint16_t last_time, uint16_t laptime,uint8_t is_first )
{
	//처음 Close-Loop 들어왔을시. 전기각 30도 대기시간은 오픈루프주기에 맞추게됨.
	if(is_first == 1)
	{
		return (uint16_t)laptime;
	}

	//이후 Close-Loop 들어왔을시. 전기각 30도 대기시간은 이전 ZC 감지시간 부터 현재 ZC 감지시간 과 동일.
	else
	{
		uint16_t edgree_60 =  (uint16_t)(current_time - last_time);
		return (uint16_t)(edgree_60/2U);
	}
}


static void sixstep(uint8_t step , uint16_t new_CCR)
{
	switch (step) {

	case 1 :
		//A ( PWM ) B( 0 1 ) C(floating)
		Change_CCR1(new_CCR);
		Change_CCR2(0);
		Change_CCR3_float();
		break;
	case 2 :
		//A (PWM) B(floating) C(0 1)
		Change_CCR1(new_CCR);
		Change_CCR2_float();
		Change_CCR3(0);
		break;

	case 3 :
		//A (floating) B(PWM) C(0 1)
		Change_CCR1_float();
		Change_CCR2(new_CCR);
		Change_CCR3(0);
		break;

	case 4 :
		//A (0 1) B(PWM) C(floating)
		Change_CCR1(0);
		Change_CCR2(new_CCR);
		Change_CCR3_float();
		break;

	case 5 :
		//A (0 1) B(floating) C(PWM)
		Change_CCR1(0);
		Change_CCR2_float();
		Change_CCR3(new_CCR);
		break;

	case 6 :
		//A (floating) B(0 1) C(PWM)
		Change_CCR1_float();
		Change_CCR2(0);
		Change_CCR3(new_CCR);
		break;

	default :
		Change_CCR1_float();
		Change_CCR2_float();
		Change_CCR3_float();
		break;
	}
}
