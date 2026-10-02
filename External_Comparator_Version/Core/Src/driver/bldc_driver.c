/*
 * bldc_driver.c
 *
 *  Created on: Jul 26, 2026
 *      Author: luke8
 */

#include "driver/motor_driver.h"
#include "driver/gate_driver.h"
#include "driver/TIM3_us_driver.h"
#include "driver/bldc_driver.h"

#include "main.h"

#define POLE_PAIRS 7U
#define TIME_OUT 10000
#define BLOCK_COUNTER	1


//전체 공유 전역 변수 (메인에서 초기화, 인터럽트에서 갱신)
static volatile uint8_t step = 1;		//TIM1 인터럽트에서 업데이트 된다.
static volatile uint8_t current_duty;	//메인에서 초기화, TIM6 ISR에서 업데이트
static volatile uint8_t	target_duty;	//메인/UART에서 기록, TIM6 ISR에서 읽음


//motor_Run_First 에서 사용하는 변수들 (메인 함수에서 한번만 실행 된다)
static uint16_t delay_time = 10000;  //10ms  메인함수에서만 업데이트 된다.
static uint8_t ramp_count = 0;		//메인 함수에서만 업데이트 된다.
static uint8_t first_flag = 1;		//메인 함수에서만 업데이트 된다.


//첫 클로즈 루프임을 알리는데에 사용되는 플래그 와 변수
static volatile uint8_t isFirstzcCOM = 1;	//메인에서 초기화 되고, TIM1 인터럽트에서 갱신된다.
static volatile uint16_t startTime = 0;				//메인에서 초기화 따로 없다. TIM6 ISR에서 기록, TIM1 ISR에서 읽음


//TIM1에서 사용하는 변수	(TIM1에서만 사용되면, 함수 탈출후에도 값이 유지되어야 함)
static uint16_t last_ZC_time = 0;			//전역 변수, TIM1에서 전기각 계산에 사용 (us 단위)
static uint16_t previous_zc_diff = 0;	    //TIM1 인터럽트 함수에서만 사용되는 zc_diff, 전기각 60도에 해당하는 시간(us 단위)
static uint16_t zc_diff_30 = 0;

//TIM1와 TIM6에서 공유할 변수 (메인에서 초기화 ,인터럽트에서 사용)
static volatile uint8_t readpinstate_request = 0;	//플래그, 	TIM6 인터럽트에서 갱신, TIM1 인터럽트에서 확인
static volatile uint8_t block_counter = 1;			//관찰용 변수, TIM6 인터럽트에서 초기화, TIM1 인터럽트에서 갱신

// 드라이버 내부에사 에러 상태를 저장할 static 변수 추가, 서비스 레이어가 관찰한다.
//static volatile uint8_t motor_stall_error = NO_ERROR; //메인에서 초기화, 인터럽트에서 갱신
static uint8_t skip_counter	= 0;
static uint16_t last_front_us;
static volatile MOTOR_ERROR motor_stall_error;

// 6스텝 평균을 위한 배열과 카운터 (메인에서 초기화, 인터럽트에서 사용)
static inline uint16_t Get_Average_ZC_diff(uint16_t zc_diff);
static uint16_t zc_history[6] = {0};
static uint8_t zc_index = 0;
static uint8_t zc_count = 0;


static uint8_t last_pinstate;					//Check_ZC()와 TIM1 ISR 안에서만 접근
static volatile uint8_t is_first_ZCsample = 0;	//TIM6 ISR 에서 기록, TIM1 ISR에서 읽고 변경


#define SKIP_TARGET 97 // 6의 배수(96) + 1 -> 스텝 순서를 유지하며 딜레이 생성
#define GUARD_COUNT	240

static uint16_t Adt_delay_us = 30;
static uint8_t zc_guard_count = 0;


#define HYSTERESIS	80				//윈도우 필터 범위 +-
#define MAX_ERROR	5				//motor stall 기준 에러 개수 조건
static volatile uint8_t err_cnt = 0;
static volatile uint16_t list_last_front_us[6];
static volatile uint16_t list_last_zc_diff_30[6];


//서비스 레이어에서 사용하는 함수
MOTOR_ERROR Get_Motor_Error()
{
	return motor_stall_error;
}

void Clear_Motor_Error()
{
	motor_stall_error.error_code = NO_ERROR;
	motor_stall_error.current_timestamp = 0;
	motor_stall_error.last_timestamp = 0;
}


static void (*Motor_log_Callback)(void) = NULL; 	//함수 포인터 변수 선언. 주소 = NULL , TIM6 인터럽트 완료시점에 콜백한다.
static void (*Motor_monitor_Callback)(void) = NULL; //함수 포인터 변수 선언. 주소 = NULL , TIM6 인터럽트 완료시점에 콜백한다.

void Driver_SetRegister_LOG(void (*callback_func)(void)) //서비스레이어에서 드라이버의 함수 포인터주소를 callback_func로 지정
{
	Motor_log_Callback = callback_func;
}

void Driver_SetRegister_MONITOR(void (*callback_func)(void))
{
	Motor_monitor_Callback = callback_func;
}


//로그로 사용되는 데이터 변수
static uint16_t log_step_us = 0;	//스텝 지속 시간
static uint16_t log_front_us = 0;	//스텝 변경부터 ZC검출까지 걸린 시간
static volatile uint16_t log_back_us = 0;	//ZC 검출부터 다음 스텝 갱신 까지 걸린 시간, TIM1 ISR에서 기록, TIM6 ISR에서 읽고 변경
static volatile uint16_t log_zc_30 = 0;		//전기각 30도에 해당하는 시간, IM1 ISR에서 기록, TIM6 ISR의 로그 콜백에서 읽음


void Set_TIM14_ON(uint16_t preiod);
void Set_TIM14_OFF();

void Packing_LOG(motor_idf* templog)
{
	templog->duty = current_duty;		//현재 PWM TIM1의 CCR값, x/240 비율
	templog->step = step;				//현재 step
	templog->zc_diff_30 = log_zc_30;
	templog->front_us = log_front_us;
	templog->back_us = log_back_us;
	templog->step_us = log_step_us;
}

//드라이버의 전역변수 정보를, 서비스 레이어에서 사용할수 있게 한다.
void Send_Motorlog(motor_idf* motor_log)
{
	motor_idf temp_log;
	Packing_LOG(&temp_log);
	*motor_log = temp_log;
}


// RPM 계산 함수
uint32_t RPM_From_ZcDiff(uint16_t zc_diff_us)
{
    if(zc_diff_us == 0) return 0;

    /*
     * zc_diff_us = electrical 60 degree time.
     * electrical period = zc_diff_us * 6.
     * mechanical RPM = 60,000,000 / (electrical_period_us * pole_pairs)
     */
    return 60000000UL / ((uint32_t)zc_diff_us * 6UL * POLE_PAIRS);
}


// 모터 초기화
void Motor_Inite(){	//메인에서 최초에 한번 실횅, 게이트 드라이버 초기화, 및 각종 변수 초기화.

	Init_GateDriver();

	step = 1;
	current_duty = 22;
	//motor_stall_error = 0;

	Set_TIM6_OFF();
	Set_TIM14_OFF();

	Clear_Motor_Error();
}

// 시작 요청
void Motor_Start_Request(){ //버튼 인터럽트시. 모터 서비스 실행전 한번 실행됨. 타이머 키기. 변수 초기화?

	step = 1;
	current_duty = 30;
	target_duty = current_duty;

	first_flag = 1;
	delay_time = 10000;
	ramp_count = 0;

	// 각종 변수 초기화
	isFirstzcCOM = 1;
	readpinstate_request = 0;
	block_counter = BLOCK_COUNTER;

	previous_zc_diff = 0;
	zc_diff_30 = 0;

	zc_index = 0;
	zc_count = 0;

	last_front_us = 0;
	zc_guard_count = 0;

	Clear_Motor_Error();

	err_cnt = 0;
	for(uint8_t i = 0; i<6; i++)
	{
		list_last_front_us[i] = 0;
		list_last_zc_diff_30[i] = 0;
	}


	Motor_TIM1_Set(current_duty);
	HAL_Delay(50);
}

// 정지
void Motor_Stop(){	//버튼 인터럽트시, 타임아웃시 실행됨. 타이머 끄기, 변수 초기화?

	Motor_TIM1_Reset();
	Set_TIM6_OFF();
	Set_TIM14_OFF();

}

void BLDC_Driver_Change_Duty(uint8_t target_CCR)
{
	target_duty = target_CCR;
}


//초기 강제 구동 (오픈 루프). //50ms -> 10ms
uint8_t Motor_Run_First(){


	/*

	if(step == 2)  { GPIOB->BSRR = (1U << 12); }

	else { GPIOB->BSRR = (1U << (12+16)); }

	sixstep(step, current_duty); //초기값 22 -> 22/124 ;
	Delay_us(delay_time); // 50000

	ramp_count++;
	if(ramp_count >= 6){
		ramp_count = 0;
		if(delay_time > 5000){ delay_time -= 300; }
		else if (delay_time > 1000){ delay_time -= 100; }

	}

	// 클로즈드 루프(인터럽트 기반)로 전환
	if(delay_time <= 1000) {
		first_flag = 0;

		//TIM6가 바통을 이어받을 수 있도록 초기값 세팅
		TIM6_Complete_Callback();
		return 1;
	}

	else {
		step++;
		if(step > 6) step = 1;
		return 0;
	}

	*/


	first_flag = 0;
	current_duty = 30;
	TIM6_Complete_Callback();
	return 1;

}


//---------------------------
// 인터럽트 기반 상태머신
//----------------------------

//20kHz 핀 검사
uint8_t Check_ZC(uint8_t step)
{
	uint8_t result = 0;
	uint8_t current_pinstate = 0;
	current_pinstate = ReadPinState(step);



	//TIM1 ZC 검출요청 최초로 받을시 현재 스텝에서의 첫번째 상태 확인.
	if(is_first_ZCsample == 1)
	{
		is_first_ZCsample = 0;
		last_pinstate = current_pinstate;
		result = 0;
	}



	switch (step)
	{
		case 1: case 3: case 5:		//스텝 1, 3, 5 는 폴링 엣지가 발생, -> 레벨 0를 검출해야 한다
			if( last_pinstate == 1 && current_pinstate == 0) result = 1;
			else result = 0;
			break;

		case 2: case 4: case 6:		//스텝 2, 4, 6 는 라이징 엣지가 발생, -> 레벨 0를 검출해야 한다
			if( last_pinstate == 0 && current_pinstate == 1) result = 1;
			else result = 0;
			break;

		default:
			return result = 0;
			break;
	}

	last_pinstate = current_pinstate;

	return result;
}


// TIM1 콜백 (20kHz 폴링 동기화 샘플링)
void TIM1_Complete_Callback()
{

	//스위칭 엣지무시 조건을 만족하지 않을시 리턴.
	if(TIM1->CNT < 120) return;

	//zc_pinstate를 읽으라는 요청이 들어오면 동작 수행
	if(readpinstate_request == 1)
	{

		//블록 카운터가 남아있으면, 노이즈인식을 방지하기우해, 바로 리턴
		if(block_counter > 0)
		{
		   block_counter--;
		   return;
		}


		uint16_t current_Time = Time_Get_US();
	    uint16_t elapsed = (uint16_t)(current_Time - startTime);

		if(elapsed >= TIME_OUT)
		{
			readpinstate_request = 0;
			// 1. 하드웨어 보호가 최우선! 서비스 레이어를 기다리지 않고 드라이버가 직접 모터를 끈다
			Motor_Stop();
			// 2. 상위 레이어가 알 수 있도록 에러 플래그만 세팅한다.
			motor_stall_error.error_code = TIME_OUT_ERROR;

			//3. ZC검출 진행하지 않고 빠져나온다.
			return;
		}


		//ZC검출이 완료되었는지 체크한다.
		if(Check_ZC(step) == 1)
		{

			readpinstate_request = 0;

			uint16_t current_ZC_time = Time_Get_US();

			log_front_us = current_ZC_time - startTime;  //스텝 시작부터 ZC 검출까지의 시간을 기록
			log_back_us = current_ZC_time;

			uint16_t newARR;

			if(isFirstzcCOM == 1)	//클로즈 루프에 처음들어와 ZC 검출 완료가 처음이여서, 전기각 30도를 계산 기준이 없는경우
			{
				newARR = (uint16_t)(current_ZC_time - startTime);
				zc_diff_30 = newARR;
				isFirstzcCOM = 0;
			}

			else	//클로즈 루프에 들어온게 처음이 아닌경우, 전기각 30도 계산은 (현재스텝 ZC 발생시간 - 이전스텝 ZC 발생시간)/2
			{
				uint16_t zc_diff = (uint16_t)(current_ZC_time - last_ZC_time);	//60도 전기각을 구한다.

				uint16_t average_ARR = 0;

				average_ARR = Get_Average_ZC_diff(zc_diff);	//평균을 통해 구한 전기각 30도의 시간(us)

				zc_diff_30 = average_ARR;
				log_zc_30 = zc_diff_30;		//전기각 30도를 기록.
			}





			last_ZC_time = current_ZC_time;
			Set_TIM6_newARR(zc_diff_30); // TIM6에게 다음 스텝 타격 명령

		}
	}
}




static inline uint16_t Get_Average_ZC_diff(uint16_t zc_diff)
{
	// 1. 히스토리 배열에 현재 스텝의 ZC_diff 시간 저장 및 인덱스 증가
	zc_history[zc_index] = zc_diff;
	zc_index++;

	// 인덱스가 배열 크기(6)를 넘어가면 다시 0으로 돌림 (원형 버퍼)
	if(zc_index >= 6) { zc_index = 0; }

	// 6개가 꽉 찰 때까지만 카운트 증가
	// 2. 데이터 누적 상태에 따른 newARR 계산 , 데이터가 6개 미만일 때는 기존처럼 현재 zc_diff 절반 사용
	if(zc_count < 6)
	{
		zc_count++;
		return  (uint16_t)(zc_diff / 2);
	}

	else
	{
		// 6개가 다 모이면 6스텝(전기각 360도) 합산 구하기
		uint32_t zc_sum = 0;
		for(uint8_t i = 0; i < 6; i++) { zc_sum += zc_history[i]; }

		// 총합(360도)을 12로 나누면 정확히 30도 지연 시간이 됨
		return  (uint16_t)(zc_sum / 12);
	}

}



// TIM6 콜백 (지연 완료 후 상전환 타격)
void TIM6_Complete_Callback()
{

	uint16_t current_time = Time_Get_US();

	log_step_us = (uint16_t)(current_time - startTime);  //스텝 종료 시간을 기록후 스텝 지속시간을 기록,
	log_back_us = (uint16_t)(current_time - log_back_us);

	//서비스 레이어를 콜백한다.
	skip_counter++;

	Motor_log_Callback();	//스텝 종료시점에 로깅

	if(skip_counter >= SKIP_TARGET)
	{
		skip_counter = 0;
		Motor_monitor_Callback();	//모니터링용 정보를 쏴주기.
	}

	Set_TIM6_OFF();
	step++;
	if(step > 6) step = 1;


	if(step == 1) { GPIOB->BSRR = (1U << 12); }
	else { GPIOB->BSRR = (1U << (12+16)); }


	if(step == 1)	//모든 스텝 진행후 전기각 360도를 넘었으면, 타켓 CCR에 맞추어 현재 CCR에서 1 증가
	{
		if(current_duty < target_duty) current_duty++;
		else if(current_duty > target_duty) current_duty--;
	}

	if(zc_guard_count < GUARD_COUNT) zc_guard_count++;


	//변경된 스텝에 해당하는 last_pinstate의 상태를 미리 설정.
	sixstep(step, current_duty);

	startTime = Time_Get_US();	//상전환 한 직후 startTime을 갱신해준다. 스텝 시작 시간을 기록

	//readpinstate_request = 1;	//TIM1 의 핀상태읽기 플래기를 활서화.
	//is_first_ZCsample = 1;		//TIM1 에게 클로즈 루프의 첫번째 샘플임을 알리는 플래그

	block_counter = BLOCK_COUNTER;			//상전환 직후 ZC감지 공백시간 적용.


	is_first_ZCsample = 1;	//TIM14에게 클로즈 루프의 첫번째 샘플임을 알리는 플래그
	Set_TIM14_ON(Adt_delay_us);	//TIM14_ON, Adt_delay_us 만큼 TIM14의 ARR을 설정하여 딜레이

}


uint8_t Check_ZC_Edge(uint8_t current_step, uint8_t last_pinstate, uint8_t current_pinstate)
{
	uint8_t result = 0;

	switch (current_step)
	{
		case 1 : case 3 : case 5 :
			if(last_pinstate == 1 && current_pinstate == 0) { result = 1; }
			else{ result = 0; }
			break;

		case 2 : case 4 : case 6 :
			if(last_pinstate == 0 && current_pinstate == 1) { result = 1; }
			else{ result = 0; }
			break;

		default :
			break;
	}

	return result;
}



void Set_TIM14_ON(uint16_t preiod)
{
	//TIM14 비활성화, 인터럽트 찌꺼기 제거,
	TIM14->CR1 &= ~(1U << 0);
	TIM14->SR = ~(1U << 0);

	//CNT 0로 설정, ARR 설정
	TIM14->ARR = preiod;
	TIM14->CNT = 0;

	// TIM14 시작 (CEN 비트 활성화)
	TIM14->CR1 |= (1U << 0);
}


void Set_TIM14_OFF(){

	TIM14->CR1 &= ~(1U << 0);
	TIM14->SR = ~(1U << 0);
	TIM14->CNT = 0;
}


uint8_t isNOTwithinWindow(uint16_t front_us, uint16_t reference);

void TIM14_Complete_Callback()
{

	//TIM14 IRQ 처음 진입인지 확인, 처음진입일 경우 lsat_pinstate 결정하고, 샘플링 주파수 설정
	if(is_first_ZCsample == 1)
	{
		is_first_ZCsample = 0;
		last_pinstate = ReadPinState(step);
		Set_TIM14_ON(20);	//20us 주기는 50kHz
		return;
	}


	//TIM14 IRQ 처음 이후 진입, 타임 아웃 조건 확인
	uint16_t current_time = Time_Get_US();
	uint16_t elapsed = (uint16_t)(current_time - startTime);

	//타임 아웃일시 모터 정지
	if(elapsed >= TIME_OUT)
	{
		Motor_Stop();	//TIM1 리셋, TIM6 리셋, TIM14 리셋

		motor_stall_error.error_code = TIME_OUT_ERROR;
		motor_stall_error.current_timestamp = current_time;
		motor_stall_error.last_timestamp = startTime;

		return;
	}

	//current_pinstate 를 읽고 , ZC검출 엣지 판별
	uint8_t current_pinstate = ReadPinState(step);
	uint8_t is_Edge_Detect = Check_ZC_Edge(step, last_pinstate, current_pinstate);

	//엣지 검출 실패시, last_pinstate의 상태를 업데이트 후 IRQ 리턴
	if(is_Edge_Detect == 0)
	{
		last_pinstate = current_pinstate;
		return;
	}

	//엣지 검출 성공시, 엣지 검출시간 기록
	uint16_t current_ZC_time = Time_Get_US();
	uint16_t front_us = (uint16_t)(current_ZC_time - startTime);


	//front_us , ZC감지시간이 이전 시간 대비 비정상으로 길면 에러
	uint8_t err_detect = isNOTwithinWindow(front_us, list_last_front_us[step-1]);

	if( err_detect == 1)
	{
		uint16_t raw_front_us = front_us;
		front_us = list_last_front_us[step-1];
		err_cnt++;

		if(err_cnt >= MAX_ERROR)
			{
				Motor_Stop();
				motor_stall_error.error_code = ZC_DETECT_ERROR;
				motor_stall_error.current_timestamp = raw_front_us;
				motor_stall_error.last_timestamp = list_last_front_us[step-1];
				return;
			}
	}



	//60도 전기각 시간 구하기.
	uint16_t zc_diff;
	if(isFirstzcCOM)
	{
		zc_diff = 2*front_us;
		isFirstzcCOM = 0;
	}

	else
	{
		zc_diff = current_ZC_time - last_ZC_time;
	}


	//60도 전기각 시간의 평균을 구하고, 30도 전기각 시간 정하기.
	if(err_detect == 1) zc_diff_30 = list_last_zc_diff_30[step-1];	//에러 검출시, zc_diff_30은 이전 사이클의 것을 사
	else zc_diff_30 = Get_Average_ZC_diff(zc_diff);

	//로그변수들 업데이트, front_us(전체 기록) , back_us(back 시작시간 기록)
	log_front_us = front_us;
	log_back_us = current_ZC_time;
	log_zc_30 = zc_diff_30;

	//다음 루프에 사용되는 값들 업데이트
	last_ZC_time = current_ZC_time;
	list_last_front_us[step-1] = front_us;
	list_last_zc_diff_30[step-1] = zc_diff_30;

	//TIM14를 끄고, TIM6 트리거 하기
	Set_TIM14_OFF();
	Set_TIM6_newARR(zc_diff_30);

}


uint8_t isNOTwithinWindow(uint16_t front_us, uint16_t reference)
{

	if(current_duty <= 100) return 0;

	if(zc_guard_count < GUARD_COUNT) return 0;

	uint16_t MAX = reference + HYSTERESIS;
	uint16_t MIN;

	if (front_us >= reference) { MIN = front_us - reference; }
	else { MIN = reference - front_us; }

	if( front_us >= MIN && front_us <= MAX) return 0;

	else return 1;
}
