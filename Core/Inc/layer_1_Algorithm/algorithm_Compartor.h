#ifndef INC_LAYER_1_ALGORITHM_COMPARATOR_H_
#define INC_LAYER_1_ALGORITHM_COMPARATOR_H_


#include "layer_0_Driver/driver_BLDC_HW.h"


#define MAX_CNT_BUFFER

typedef struct
{
    volatile uint16_t ts_compA;
    volatile uint16_t ts_compB;
    volatile uint16_t ts_compC;

    volatile uint8_t is_edge_occur;
    volatile uint8_t cnt_edge;

}Comparator_t;


void Init_Comparator();
void Reset_Comp_t();
void Get_Curr_CompStatus(Comparator_t* temp);


void Setting_Comparator_State(uint8_t step);
void Setting_Comparator_Off();

//함수를 호출한 시점에서 제공할 정보: 스텝에 맞추어서 알맞은 비교기에서 비교기 엣지가 발생 했는지 안했는지.
//발생 했다면, 그때 찍힌 가장 최신의 timestamp값이 몇인지. 비교기가 켜지고 몇번이나 엣지가 발생했는지.

/*
sixstep 알고리즘에서 동작한다고 했을시

/--- step 시작 /
COMPARATOR_T 리셋.
step과 관련없는 comparator off
step 에 맞는 COMPARATOR ON

step 시작. ts_start 기록

/---- ZC 대기 /
ts_comp 발생. ts_start 와, ts_comp 비교, 
브로킹 조건에 걸리면, 리턴

/---- 30도 대기 시간 트리거
블로킹 조건 모두 통과시, ts_comp를 최종 t_zc로 결정,
t_zc와 last_t_zc로 부터 30도 딜레이 시간 계산
comparator OFF
TIM로 30도 딜레이 시간 트리거.

*/


//ADC 인터럽트에서 관찰한다고 하면
/*
ADC 계산에 의한 t_zc가 발생했을때.
t_zc 했을때,  comp에 기록된 값을 참조. 
엣지 발생 했는지. 몇번 발생 했는지 확인
comparator_off, 

로그에 포함

*/

#endif

