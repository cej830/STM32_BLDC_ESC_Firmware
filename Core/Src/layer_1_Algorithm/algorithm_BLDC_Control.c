/*
 * algorithm_BLDC_Control.c
 *
 *  Created on: 2026. 8. 27.
 *      Author: luke8
 */


#include "layer_1_Algorithm/algorithm_BLDC_Control.h"
#include "layer_1_Algorithm/algorithm_Compartor.h"



#define MAX_TIME_OUT 				5000
#define BLANKING_TIME 				30
#define CONTROL_PATH_LATENCY_US		19

#define DUR_VALID			100
#define DUR_REJECT			500
#define MAX_RISK_CNT	8

#define ERROR_NUM_TIMEOUT			(9999)
#define ERROR_NUM_ZC_REJECTED		(9997)
#define ERROR_NUM_ALREDY			(9996)
#define ERROR_NUM_SAMPLE_AND_ZC		(9995)

#define HALF_ARR 900


/*
#define START_CCR					220
#define START_OPEN_LOOP_DELAY		15000	//15ms
#define LAST_OPEN_LOOP_DELAY		8000	//5ms
*/


// 디버거에서 실시간 수정 가능한 변수들
static volatile uint16_t START_CCR = 220;
static volatile uint16_t START_OPEN_LOOP_DELAY = 10000;
static volatile uint16_t LAST_OPEN_LOOP_DELAY = 6000;

//ZC발생후 전기각 30도 지연 대기 시간.
static volatile uint16_t PAR = 50;


//------------오픈 루프 동작 관련 변수
static volatile OPENLOOP_Mangae_t openloop_manage = {0};

//-----------모터 상 전압 기록--------------

static volatile MotorError_t motor_error = NO_ERROR;


static volatile MotorControl_t motorcontrol = {0};
static volatile ZC_Management_t zc_manage = {0};
static volatile ZC_History zc_history = {0};
static volatile ZC_Over_cnt zc_over_cnt = {0};
static volatile ZC_Valid_Status_t zc_valid_status = ZC_VALID;

typedef struct
{
	uint16_t* dur_step_to_zc;
	uint8_t cnt_risk;
	uint8_t cnt_zc_already;
	ZC_Valid_Status_t zc_valid;
}ZC_Check_t;

static uint16_t last_duration_buff[6] = {0};

static ZC_Check_t zc_check = {
		.dur_step_to_zc = last_duration_buff,
		.cnt_risk = 0,
		.cnt_zc_already = 0,
		.zc_valid = ZC_VALID};


typedef enum
{
	ZC_NOT_YET = 0,
	ZC_DETECTED,
	ZC_ALREADY_OCCUR,
	ZC_PASS,
}ZC_State_t;

#define ZC_ALREADY_MARGIN 10
#define MAX_CNT_ALREADY	3

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

//-----------LOG 작성을 위해 팩킹하는 함수
static inline void Packing_Motor_Log(MotorTelemetry_t* log, Motor_Log_Temp* temp, ADC_snapshot_t* snapshot);
static inline void Return_And_Logging(MotorTelemetry_t* motorlog, Motor_Log_Temp* temp, ADC_snapshot_t* snapshot);
static inline void Motor_Stop_and_LogPush(MotorTelemetry_t* motorlog, Motor_Log_Temp* temp, ADC_snapshot_t* snapshot, MotorError_t errortype, uint16_t special_delay);

//-------------Commutation 에 관련된 함수
static void sixstep(uint8_t step , uint16_t new_CCR);


//----------ADC ISR 에서 계산에 사용되는 함수
static inline int16_t Calculate_BEMF(uint8_t step);
static inline ZC_State_t is_ZeroCrossing_Occur(uint8_t step , int16_t BEMF_curr, int16_t BEMF_prev, uint8_t is_first);
static inline uint16_t Calculate_Linear_ZC_timestamp(uint16_t t_curr, int16_t BEMF_current, uint16_t t_prev, int16_t BEMF_prev);
static inline ZC_Valid_Status_t Check_Valid_ZC(uint16_t prev_duration, uint16_t curr_duration, ADC_snapshot_t* snapshot);
static inline uint16_t Calculate_Edgree_Delay_time(uint16_t current_time, uint16_t last_time, uint16_t step_start,uint8_t is_first );
static inline uint16_t Calculate_limitied_Delaytime(uint16_t current_delay, uint16_t target_delay, uint16_t PAR, ADC_snapshot_t* snapshot);
static inline uint16_t Calculate_Delay_Trigger(uint16_t ts_curr, uint16_t ts_zc, uint16_t delay);


//------------TIM3 ISR 에 사용되는 함수.
static inline void OpenLoop_Update_Rampdelay();
static inline void CloseLoop_Update_State();
static inline void CloseLockIn_Update_SamplePosition();
static inline void CloseLockIn_Control_CCR(uint16_t min_ccr);
static inline void Sixstep_and_Set_ZC_manage_Flag();

// #region [원하는 제목 명칭]
void ClearError() 
{ 
	motor_error = NO_ERROR;
}

MotorError_t Get_ErrorCode()
{ 
	return motor_error; 
}


void Algo_BLDC_Init()
{
	Driver_BLDC_HW_SetFuncAdress(Algo_BLDC_AdcISRCallback, Algo_BLDC_TimISRCallback);
}


void Algo_BLDC_Startup()
{
	Driver_BLDC_HW_Startup();
	Driver_BLDC_HW_SetLowSide_Flat();

	Driver_BLDC_HW_SetTim3OFF();

	motorcontrol.is_cl_first = 0;
	motorcontrol.motorstate = OPEN_LOOP;
	motorcontrol.cnt_cycle = 0;
	motorcontrol.ccr_state = IDLE;
	motorcontrol.step = 1;
	motorcontrol.ccr_curr = START_CCR;
	motorcontrol.ccr_target = START_CCR;
	motorcontrol.samplemode = LOWSIDE_SAMPLE;

	zc_manage.is_searching = 0;			//ZC계산분기 ADC 플래그 RESET
	zc_manage.is_sample_first = 0;
	zc_manage.cnt = 0;

	openloop_manage.delay_us = START_OPEN_LOOP_DELAY;
	openloop_manage.cnt_openloop = 0;
	openloop_manage.flag_openloop = 1;

	zc_over_cnt.cnt_delay_over = 0;
	zc_over_cnt.cnt_elapsed_over = 0;

	for(uint8_t i=0; i<6; i++)
	{
		zc_check.dur_step_to_zc[i] = 0;
	}

	zc_check.cnt_risk = 0;
	zc_check.cnt_zc_already = 0;
	zc_check.zc_valid = ZC_VALID;

	Reset_Comp_t();
	Setting_Comparator_Off(1);
	Setting_Comparator_Off(2);
	Setting_Comparator_Off(3);

	Clear_LogRingBuffer();
	sixstep(motorcontrol.step, motorcontrol.ccr_curr);
	Driver_BLDC_HW_SetTimTrig(openloop_manage.delay_us);
}





void Algo_BLDC_AdcISRCallback()
{
	
	ADC_snapshot_t adc_snapshot;

	adc_snapshot.step            = motorcontrol.step;
	adc_snapshot.motor_state     = motorcontrol.motorstate;
	adc_snapshot.is_cl_first     = motorcontrol.is_cl_first;
	adc_snapshot.is_sample_first = zc_manage.is_sample_first;
	adc_snapshot.ts_step         = zc_manage.ts_start;
	adc_snapshot.is_searching    = zc_manage.is_searching;
		
	//Get timestamp and Duration.
	uint16_t ts_curr = Driver_Time_Get_Us();
	uint16_t dur_now = (uint16_t)(ts_curr - adc_snapshot.ts_step);

	
	
	//Block ADC value until step_duration is less than BLANKINGTIME
	if(dur_now < BLANKING_TIME)
	{
		return;
	}

	GPIOC->BSRR = (1U << (14));
	int16_t bemf_curr = Calculate_BEMF(adc_snapshot.step);	//sw bemf 계산.
	MotorTelemetry_t motor_log = {0};
	Motor_Log_Temp temp = {0};

	temp.ts_curr   = ts_curr;
	temp.bemf_curr = bemf_curr;
	GPIOC->BSRR = (1U << (14+16));

	if(adc_snapshot.motor_state == OPEN_LOOP)
	{
		ZC_State_t is_zc_detect = is_ZeroCrossing_Occur(adc_snapshot.step, bemf_curr, zc_history.bemf_prev, adc_snapshot.is_sample_first);
		temp.is_zc_detect = is_zc_detect;
		zc_history.bemf_prev = bemf_curr;
		zc_history.ts_prev   = ts_curr;
		Return_And_Logging(&motor_log, &temp, &adc_snapshot);
		return;
	}

	if(adc_snapshot.is_searching == 0)
	{
		//히스토리를 업데이트 하는것은 계속 되어야 하는가. 끊김없이.
		Return_And_Logging(&motor_log, &temp, &adc_snapshot);
		return;
	}

	//ZC 감지를 TIMEOUT 이내에 못하면 에러발생.
	if(dur_now > MAX_TIME_OUT)
	{
		Motor_Stop_and_LogPush(&motor_log, &temp, &adc_snapshot, ERROR_TIME_OUT, ERROR_NUM_TIMEOUT);
		return;
	}

	// searching == 1 일때, BEMF기반 ZC 계산 시작.

	uint8_t idx = adc_snapshot.step-1;
	uint16_t ts_zc;							//zc가 발생함 타임스탬프
	uint16_t dur_step_to_zc;				//스텝 시작부터 zc 발생 까지의 시간 기록
	uint16_t dur_step_to_zc_last;
	ZC_State_t is_zc_detect;

	is_zc_detect = is_ZeroCrossing_Occur(adc_snapshot.step, bemf_curr, zc_history.bemf_prev, adc_snapshot.is_sample_first);
	temp.is_zc_detect = is_zc_detect;

	switch (is_zc_detect)
	{
		case ZC_NOT_YET :
			zc_manage.is_sample_first = 0;
			zc_history.bemf_prev = bemf_curr;			
			zc_history.ts_prev = ts_curr;
			Return_And_Logging(&motor_log, &temp, &adc_snapshot);
			return;

		case ZC_PASS :
			Return_And_Logging(&motor_log, &temp, &adc_snapshot);
			return;

		
		case ZC_DETECTED :
			{
				zc_check.cnt_zc_already = 0;
				ts_zc = Calculate_Linear_ZC_timestamp(ts_curr, bemf_curr, zc_history.ts_prev, zc_history.bemf_prev);  //선형 보간 계산 을 통해 zc 구하기
				temp.ts_zc = ts_zc;

				dur_step_to_zc = (uint16_t)(ts_zc - adc_snapshot.ts_step);	//step_to_zc duration 계산
				dur_step_to_zc_last = zc_check.dur_step_to_zc[idx];			//last step_to_zc duration 꺼내서, 비교
				zc_check.zc_valid = Check_Valid_ZC(dur_step_to_zc_last, dur_step_to_zc, &adc_snapshot);
			
				if(zc_check.zc_valid == ZC_REJECT)
				{
					Motor_Stop_and_LogPush(&motor_log, &temp, &adc_snapshot, ERROR_ZC_REJECTED, ERROR_NUM_ZC_REJECTED);
					return;
				}
				zc_check.dur_step_to_zc[idx] = dur_step_to_zc;	//버퍼의 값을 업데이트
				break;
			}
			
			
		case ZC_ALREADY_OCCUR :
			{
				zc_manage.is_sample_first = 0;
				zc_check.cnt_zc_already++;
				if(zc_check.cnt_zc_already >= MAX_CNT_ALREADY)
				{
					Motor_Stop_and_LogPush(&motor_log, &temp, &adc_snapshot, ERROR_ALREADY, ERROR_NUM_ALREDY);
					return;
				}

				//첫번째 샘플에서 ZC가 이미 지나갔다, step 시작부터 현재 첫번째 샘플 검출까지 걸린시간은 dur_now.
				dur_step_to_zc_last = zc_check.dur_step_to_zc[idx];	
				if(dur_step_to_zc_last > dur_now)	//이전 스텝에서 기록된 step_to_ZC duration이, dur_now 보다 길면.
				{
					zc_over_cnt.cnt_predict_over++;		//ZC의 발생 시간을 비교하면 < step - ZC - now - last_step_zc > 
					dur_step_to_zc = dur_now;			//step-ZC의 시간은 보수적으로 가장 긴값인 step-now 를 사용한다.
				}										//첫샘플에서 이미 ZC가 지난것은, ADC의 해상도가 한계라는 의미
				else
				{											//ZC의 발생 시간을 비교하면 < step - ZC - last_step_zc - now >
					dur_step_to_zc = dur_step_to_zc_last;	//step-ZC 의 시간은 step-last_step_zc 를 사용한다.
				}

				ts_zc = (uint16_t)(adc_snapshot.ts_step + dur_step_to_zc);	//duration에서 timestamp으로 변환한다.
				temp.ts_zc = ts_zc;
				break;
			}

		default :
			Driver_BLDC_HW_Stop();
			return;
	}


	//ZC-to-ZC 로부터 30도 target delay 계산, 레이트 리미터(PAR) 적용, zc 이후 지금까지 흘러간 시간 duration 계산  
	uint16_t delay_target  = Calculate_Edgree_Delay_time(ts_zc, zc_history.ts_last_zc, dur_step_to_zc, adc_snapshot.is_cl_first);
	uint16_t delay_limited = Calculate_limitied_Delaytime(zc_history.delay_prev, delay_target, PAR, &adc_snapshot);
	uint16_t delay_trigger = Calculate_Delay_Trigger(ts_curr,ts_zc, delay_limited);

	//로그 기록, 지역변수 값들
	temp.delay_target  = delay_target;
	temp.delay_limited = delay_limited;
	temp.delay_trigger = delay_trigger;

	//상태(플래그) 업데이트, prev 값 업데이트
	zc_history.ts_last_zc = ts_zc;
	zc_history.ts_prev    = ts_curr;
	zc_history.bemf_prev  = bemf_curr;
	zc_history.delay_prev = delay_limited;

	zc_manage.is_searching = 0;
	motorcontrol.is_cl_first = 0;
	
	//TIM3로 전기각 30도 대기시간 트리거
	Driver_BLDC_HW_SetTimTrig(delay_trigger);
	Return_And_Logging(&motor_log, &temp, &adc_snapshot);
}


void Algo_BLDC_TimISRCallback()
{
	Driver_BLDC_HW_SetTim3OFF();
	
	motorcontrol.step++;
	if(motorcontrol.step > 6)
	{
		motorcontrol.step = 1;
	}

	if(motorcontrol.step == 1)
	{
		GPIOC->BSRR = (1U << 13);
	}

	else
	{
		GPIOC->BSRR = (1U << (13+16));
	}
	
	MotorStatus_t motor_state = motorcontrol.motorstate;

	switch (motor_state)
	{
		case OPEN_LOOP :
		OpenLoop_Update_Rampdelay();
		
		if(openloop_manage.delay_us <= LAST_OPEN_LOOP_DELAY)
		{
			motorcontrol.motorstate = CLOSE_LOOP;
			motorcontrol.is_cl_first = 1;
		}

		zc_manage.ts_start = Driver_Time_Get_Us();
		sixstep(motorcontrol.step, motorcontrol.ccr_curr);
		Driver_BLDC_HW_SetTimTrig(openloop_manage.delay_us);
		return;

		case CLOSE_LOOP :
		CloseLoop_Update_State();
		Sixstep_and_Set_ZC_manage_Flag();
		return;

		case CLOSE_LOCKIN :
		CloseLockIn_Update_SamplePosition();
		CloseLockIn_Control_CCR(225);
		Sixstep_and_Set_ZC_manage_Flag();
		return;

		default :
		return;
	}
}


static inline void Packing_Motor_Log(MotorTelemetry_t* log, Motor_Log_Temp* temp, ADC_snapshot_t* snapshot)
{
	uint8_t info = 0;

	info |= (uint8_t)((snapshot->step) & 0x0F);				//Bit [3:0] : step
	info |= (uint8_t)(((snapshot->motor_state) & 0x03) << 4);	//Bit [5:4] : motor_state
	info |= (uint8_t)((temp->is_zc_detect & 0x03) << 6);		//Bit [7:6] : zc_event

	log->info = info;

	log->header = HEADER;
	log->ccr_current = motorcontrol.ccr_curr;
	log->BEMF_curr = temp->bemf_curr;

	log->timestamp_start = zc_manage.ts_start;
	log->timestamp_curr = temp->ts_curr;
	log->timestamp_zc =	temp->ts_zc;

	log->delay_limited = zc_history.delay_prev;
	log->delay_trigger = temp->delay_trigger;
	log->delay_PAR = zc_manage.cnt;

	log->tail = TAIL;
}

static inline void Return_And_Logging(MotorTelemetry_t* motorlog, Motor_Log_Temp* temp, ADC_snapshot_t* snapshot)
{
	Packing_Motor_Log(motorlog, temp, snapshot);
	motorlog->delay_PAR = zc_manage.cnt++;
	Push_LogRingBuffer(motorlog);
}


static inline void Motor_Stop_and_LogPush(MotorTelemetry_t* motorlog, Motor_Log_Temp* temp, ADC_snapshot_t* snapshot, MotorError_t errortype, uint16_t special_delay)
{
	Driver_BLDC_HW_Stop();
	Disable_TIM_IC(1);
	Disable_TIM_IC(2);
	Disable_TIM_IC(3);
	
	temp->delay_trigger = special_delay;
	motor_error = errortype;

	Return_And_Logging(motorlog, temp, snapshot);
}


//타이머 ISR 에서 호출.
static inline void OpenLoopCommutate()
{
	// 구간 1: 극초반 탈출 (15000us ~ 10000us) -> 관성이 붙기 시작하는 구간, 굵게 감소
	if(openloop_manage.delay_us > 10000)
	{
		if(openloop_manage.cnt_openloop >= 2)
		{
			openloop_manage.cnt_openloop = 0;
			openloop_manage.delay_us -= 500; //큼직하게 감소
		}
	}
		
	// 구간 2: 중속 영역 (10000us ~ 7000us) -> 속도가 붙은 상태
	else if(openloop_manage.delay_us > 7000)
	{
		if(openloop_manage.cnt_openloop >= 3)
		{
			openloop_manage.cnt_openloop = 0;
			openloop_manage.delay_us -= 250; //중간강도씩 감소
		}
	}

	// 구간 3: 목표 도달 직전 (7000us ~ LASTus) -> 급가속 방지 및 부드러운 접근
	else
	{
		if(openloop_manage.cnt_openloop >= 4)
		{
			openloop_manage.cnt_openloop = 0;
			openloop_manage.delay_us -= 100; //약한강도씩 감소
		}
	}

	if(openloop_manage.delay_us < LAST_OPEN_LOOP_DELAY)
	{
		openloop_manage.delay_us = LAST_OPEN_LOOP_DELAY;
	}	
}

#pragma region ZC_ADC_ISR_Prossing_Functions
//ADC ISR 에서 호출, 선형보간으로 zc 발생 타임스탬프 구하기
static inline uint16_t Calculate_Linear_ZC_timestamp(uint16_t t_curr, int16_t BEMF_current, uint16_t t_prev, int16_t BEMF_prev )
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

// #region ADC ISR 함수
static inline uint16_t Calculate_Delay_Trigger(uint16_t ts_curr, uint16_t ts_zc, uint16_t delay)
{
	//ZC발생 - now 까지의 duration을 구하기
	//sample ---- ZC -------sample(now)  => sample(now ->get ts_curr)을 기준으로 ZC - nextstep 시간을 계산 
	//ADC_ISR_start_---get_ts_curr --------control_path_time--------TIM3trigger--ADC_ISR__end
	//control_path_time을 고려해야한다.

	uint16_t dur_zc_to_now = (uint16_t)(ts_curr - ts_zc);	//ts_curr을 얻을때까지의 시간.
	if(dur_zc_to_now > 100)		//sample - sample 간격임으로 50us 을 넘어 큰 값인 경우 오류이다.
	{							
		zc_over_cnt.cnt_elapsed_over++;	
		return 1;		//sample - sample(now) ---- ZC or sample - ZC ----- sample(now) 둘다 오류, 
	}

	uint16_t dur_zc_to_isrend = dur_zc_to_now + CONTROL_PATH_LATENCY_US;

	uint16_t delay_trigger = 1;
	if(delay > dur_zc_to_isrend)		//정상적인 경우.
	{
		delay_trigger = (uint16_t)(delay - dur_zc_to_isrend);
		return delay_trigger;
	}

	else					//ZC 발생후 30도 전기각 대기시간을, 현재샘플을 기다리다가 지나간 경우,
	{
		delay_trigger = 1; 	//빠르게 정류 시점으로 이동한다.
		zc_over_cnt.cnt_delay_over++;
		return delay_trigger;
	}
}

// #endrigion

//오픈루프에 사용되는 딜레이시간의 조절
static inline void OpenLoop_Update_Rampdelay()
{
	if(motorcontrol.step == 1)
	{
		openloop_manage.cnt_openloop++;
		OpenLoopCommutate();
	}

	openloop_manage.flag_openloop = 1;
	zc_history.delay_prev = openloop_manage.delay_us;
}


//클로즈 루프 상태가 100번 지속될시 클로즈 락인으로 상태 변경
static inline void CloseLoop_Update_State()
{
	if(motorcontrol.step == 1)
	{
		motorcontrol.cnt_cycle++;
		if(motorcontrol.cnt_cycle >= 100)
		{
			motorcontrol.motorstate = CLOSE_LOCKIN;
		}
	}
}


//CCR값이 PAR 의 중간을 넘을시 ADC 샘플링 타이밍을 하이사이드 플랫으로 변경
static inline void CloseLockIn_Update_SamplePosition()
{
	if(motorcontrol.ccr_curr >= 900)
	{
		if(motorcontrol.samplemode != HIGHSIDE_SAMPLE)
		{
			motorcontrol.samplemode = HIGHSIDE_SAMPLE;
			Driver_BLDC_HW_SetHighSide_Flat();
		}
	}

	else
	{
		if(motorcontrol.samplemode != LOWSIDE_SAMPLE)
		{
			motorcontrol.samplemode = LOWSIDE_SAMPLE;
			Driver_BLDC_HW_SetLowSide_Flat();
		}
	}
}


//포텐시오미터 값이 충분히 낮으면 ccr_state 를 추적상태로 변경
static inline void CloseLockIn_Control_CCR(uint16_t min_ccr)
{
	uint16_t pot_value = Get_Filtered_Pot_Value();

	if(motorcontrol.ccr_state == IDLE)
	{
		if(pot_value <= min_ccr)
		{
			motorcontrol.ccr_state = FOLLOWER;
		}
	}

	else if(motorcontrol.ccr_state == FOLLOWER)
	{
		if(motorcontrol.step == 1)
		{
			motorcontrol.ccr_target = pot_value;

			if(zc_check.zc_valid == ZC_VALID)
			{
				if(motorcontrol.ccr_target > motorcontrol.ccr_curr)
				{
					motorcontrol.ccr_curr++;
				}

				else if(motorcontrol.ccr_target < motorcontrol.ccr_curr)
				{
					motorcontrol.ccr_curr--;
				}
			}
		}
	}
}





// 식스스텝 정류후 zc 플래그 set
static inline void Sixstep_and_Set_ZC_manage_Flag()
{
	sixstep(motorcontrol.step, motorcontrol.ccr_curr);
	zc_manage.ts_start = Driver_Time_Get_Us();
	zc_manage.is_searching = 1;
	zc_manage.is_sample_first = 1;
}




static inline ZC_Valid_Status_t Check_Valid_ZC(uint16_t prev_duration, uint16_t curr_duration, ADC_snapshot_t* snapshot)
{
	if(snapshot->motor_state != CLOSE_LOCKIN)
	{
		zc_check.cnt_risk = 0;
		return ZC_VALID;
	}
	
	
	uint16_t diff = 0;

	/* 해당 Step의 첫 데이터 */
	if(prev_duration == 0)
	{
		zc_check.cnt_risk = 0;
		return ZC_VALID;
	}

	if(prev_duration >= curr_duration)
	{
		diff = (uint16_t)(prev_duration - curr_duration);
	}
	else
	{
		diff = (uint16_t)(curr_duration - prev_duration);
	}

	/* 정상 */
	if(diff <= DUR_VALID)
	{
		zc_check.cnt_risk = 0;
		return ZC_VALID;
	}

	else if(diff <= DUR_REJECT)
	{
		zc_check.cnt_risk++;
		if(zc_check.cnt_risk >= MAX_RISK_CNT)
		{
			return ZC_REJECT;
		}
		else
		{
			return ZC_RISK;
		}
	}

	else
	{
		return ZC_REJECT;
	}
}
/* 레이트 리미터: 목표 딜레이로 점진적 수렴 */
static inline uint16_t Calculate_limitied_Delaytime(uint16_t current_delay, uint16_t target_delay, uint16_t PAR, ADC_snapshot_t* snapshot)
{	
	// 첫번째 CL에 진입한 경우, 30도 전기각 딜레이 시간은 target_dealy 을 동일하게 적용한다.
	if(snapshot->is_cl_first == 1)
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


// 현재 스텝에 해당하는 BEMF 값을 계산 하는 함수
static inline int16_t Calculate_BEMF(uint8_t step)
{
	uint16_t PhaseA, PhaseB, PhaseC, Vcom = 0;
	Driver_BLDC_HW_GetPhaseV(&PhaseA, &PhaseB, &PhaseC);
	Vcom = (uint16_t)(((uint32_t)PhaseA + (uint32_t)PhaseB + (uint32_t)PhaseC)/3);
	
	uint16_t floating_phase;

	switch (step)
	{
	case 1: case 4: floating_phase = PhaseC; break;
	case 2: case 5: floating_phase = PhaseB; break;
	case 3: case 6: floating_phase = PhaseA; break;
	default : return 0;
		break;
	}

	int16_t BEMF = (int16_t)floating_phase - (int16_t)Vcom;
	return BEMF;
}


static inline ZC_State_t is_ZeroCrossing_Occur(uint8_t step , int16_t BEMF_curr, int16_t BEMF_prev, uint8_t is_first)
{
	//현재 step 에서 six_step 처음 발생시 ZC 발생 X 처리.
	if(is_first)
	{
		if(motorcontrol.motorstate != CLOSE_LOCKIN)
		{
			return ZC_NOT_YET;
		}

		// 첫 샘플에서 라이징 엣지 검출전에 먼저 + 가 검출 되면, ZC는 이미 발생했다고 본다.
		if( step == 2 || step == 4 || step == 6)
		{
			if(BEMF_curr > ZC_ALREADY_MARGIN)
			{
				return ZC_ALREADY_OCCUR;
			}

			if(BEMF_curr > 0)
			{
				return ZC_PASS;		//+1 ~ +MARGIN
			}

			return ZC_NOT_YET;
		}

		// 첫 샘플에서 폴링 엣지 검출전에 먼저 - 가 검출 되면, ZC는 이미 발생했다고 본다.
		if( step == 1 || step == 3 || step == 5 )
		{
			if(BEMF_curr < -ZC_ALREADY_MARGIN)
			{
				return ZC_ALREADY_OCCUR;
			}

			if(BEMF_curr < 0)
			{
				return ZC_PASS;
			}

			return ZC_NOT_YET;
		}
	}

	switch (step)
	{
	//스텝 1, 3, 5 는 폴링 엣지, BEMF + 에서 - , 발생시 ZC 발생
	case 1: case 3: case 5:
			if( (BEMF_prev >=0) && (BEMF_curr < 0)) return ZC_DETECTED;
			else return ZC_NOT_YET;
			break;

	//스텝 2, 4, 6 는 라이징 엣지, BEMF - 에서 + , 발생시 ZC 발생
	case 2: case 4: case 6:
			if( (BEMF_prev <=0) && (BEMF_curr > 0)) return ZC_DETECTED;
			else return ZC_NOT_YET;
			break;

		default:
			return ZC_NOT_YET;
			break;
	}
}

/* 전기각 30도의 대기시간(us)를 계산하는 함수. @ return | uint16_t
 * @ current_time 	: 현재 ZC 감지시간
 * @ last_time		: 이전 ZC 감지시간
 * @ laptime		: 스텝 시작부터 ZC검출 까지의 시간	(첫 진입시 사용)
 * @ is_first		: Close-Loop 처음진입인지 아닌지
 */
static inline uint16_t Calculate_Edgree_Delay_time(uint16_t current_time, uint16_t last_time, uint16_t laptime,uint8_t is_first )
{
	//처음 Close-Loop 들어왔을시. 전기각 30도 대기시간은 오픈루프주기에 맞추게됨.
	if(is_first == 1)
	{
		return laptime;
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
