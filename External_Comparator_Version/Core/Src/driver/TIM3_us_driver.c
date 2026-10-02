/*
 * TIM3_us_driver.c
 *
 *  Created on: Jun 30, 2026
 *      Author: luke8
 */


#include "driver/TIM3_us_driver.h"



uint16_t Time_Get_US(){

	return (uint16_t)TIM3->CNT;
}




void Delay_us(uint16_t time_us){

	uint16_t start_time = Time_Get_US();

	while(1){
		uint16_t current_time = Time_Get_US();
		uint16_t total_time = current_time - start_time;
		if(total_time >= time_us) break;
	}
}



