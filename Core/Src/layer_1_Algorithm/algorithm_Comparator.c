
#include "layer_1_Algorithm/algorithm_Compartor.h"


void Init_Comparator();
void Reset_Comp_t();


void Comparator_A_ZC_detect(uint16_t cnt_tim2);
void Comparator_B_ZC_detect(uint16_t cnt_tim2);
void Comparator_C_ZC_detect(uint16_t cnt_tim2);


static Comparator_t comp_t = {0};

#define BUFF_SIZE	10

static uint16_t buff_ic_st_A[10];
static uint16_t buff_ic_st_B[10];
static uint16_t buff_ic_st_C[10];


void Init_Comparator()
{
    Driver_BLDC_HW_SetFuncAdress2(Comparator_A_ZC_detect, Comparator_B_ZC_detect, Comparator_C_ZC_detect);

    comp_t.buff_compA = buff_ic_st_A;
    comp_t.buff_compB = buff_ic_st_B;
    comp_t.buff_compC = buff_ic_st_C;

    Reset_Comp_t();
}


// Capture Compare 발생시 인터럽트 에서 호출하는 함수. 
void Comparator_A_ZC_detect(uint16_t cnt_value)
{
	if(comp_t.cnt_edge >= BUFF_SIZE)
    {
    	return;
    }

	uint8_t idx = comp_t.cnt_edge;

    comp_t.buff_compA[idx] = cnt_value;
	comp_t.buff_compB[idx] = 0;
	comp_t.buff_compC[idx] = 0;

    comp_t.ts_compA = cnt_value;
    comp_t.ts_compB = 0;
    comp_t.ts_compC = 0;

    comp_t.is_edge_occur = 1;
    comp_t.cnt_edge++;
}

void Comparator_B_ZC_detect(uint16_t cnt_value)
{
	uint8_t idx = comp_t.cnt_edge;

	if(idx >= BUFF_SIZE)
    {
    	return;
    }


    comp_t.buff_compA[idx] = 0;
	comp_t.buff_compB[idx] = cnt_value;
	comp_t.buff_compC[idx] = 0;

	comp_t.ts_compA = 0;
    comp_t.ts_compB = cnt_value;
    comp_t.ts_compC = 0;

    comp_t.is_edge_occur = 1;
    comp_t.cnt_edge++;
}

void Comparator_C_ZC_detect(uint16_t cnt_value)
{
	uint8_t idx = comp_t.cnt_edge;

	if(idx >= BUFF_SIZE)
    {
    	return;
    }

    comp_t.buff_compA[idx] = 0;
	comp_t.buff_compB[idx] = 0;
	comp_t.buff_compC[idx] = cnt_value;

	comp_t.ts_compA = 0;
    comp_t.ts_compB = 0;
    comp_t.ts_compC = cnt_value;

    comp_t.is_edge_occur = 1;
    comp_t.cnt_edge++;
}


// 구조체 변수 초기화.
void Reset_Comp_t()
{
    comp_t.ts_compA = 0;
    comp_t.ts_compB = 0;
    comp_t.ts_compC = 0;

    comp_t.is_edge_occur = 0;
    comp_t.cnt_edge = 0;
}



void Get_Curr_CompStatus(Comparator_t *temp)
{
    *temp = comp_t;
}


void Setting_Comparator_State(uint8_t step)
{
    Disable_TIM_IC(1);
    Disable_TIM_IC(2);
    Disable_TIM_IC(3);

    switch (step)
    {
        case 1:
            Enable_TIM_IC(3, FALLING_EDGE);
            return;
        case 2 :
            Enable_TIM_IC(2, RISING_EDGE);
            return;
        case 3 :
            Enable_TIM_IC(1, FALLING_EDGE);
            return;

        case 4:
            Enable_TIM_IC(3, RISING_EDGE);
            return;
        case 5 :
            Enable_TIM_IC(2, FALLING_EDGE);
            return;
        case 6 :
            Enable_TIM_IC(1, RISING_EDGE);
            return;
    }
}

void Setting_Comparator_Off()
{
    Disable_TIM_IC(1);
    Disable_TIM_IC(2);
    Disable_TIM_IC(3);
}

