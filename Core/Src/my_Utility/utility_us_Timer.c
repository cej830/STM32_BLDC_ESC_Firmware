/*
 * driver_Us_Timer.c
 *
 *  Created on: 2026. 8. 25.
 *      Author: luke8
 */


#include "my_Utility/utility_us_Timer.h"


void Driver_Init_Us_Timer()
{
	TIM2->CR1 |= (1U << 0);
}


uint16_t Driver_Time_Get_Us()
{
	return (uint16_t)(TIM2->CNT);
}


void Driver_Delay_Us(uint16_t delay_time)
{
	uint16_t start_time = Driver_Time_Get_Us();

	while(1)
	{
		uint16_t current_time = Driver_Time_Get_Us();
		uint16_t laptime = current_time - start_time;
		if( laptime >= delay_time ) return;
		else __NOP();
	}
}
