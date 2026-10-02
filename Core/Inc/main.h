/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f1xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

void HAL_TIM_MspPostInit(TIM_HandleTypeDef *htim);

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define DEBUG_PC13_Pin GPIO_PIN_13
#define DEBUG_PC13_GPIO_Port GPIOC
#define DEBUG_PC14_Pin GPIO_PIN_14
#define DEBUG_PC14_GPIO_Port GPIOC
#define USB_DP_PullUp_Pin GPIO_PIN_15
#define USB_DP_PullUp_GPIO_Port GPIOC
#define ADC_PhaseA_Pin GPIO_PIN_0
#define ADC_PhaseA_GPIO_Port GPIOA
#define ADC_PhaseB_Pin GPIO_PIN_1
#define ADC_PhaseB_GPIO_Port GPIOA
#define ADC_PhaseC_Pin GPIO_PIN_2
#define ADC_PhaseC_GPIO_Port GPIOA
#define ADC_Vcom_Pin GPIO_PIN_3
#define ADC_Vcom_GPIO_Port GPIOA
#define ADC_Poten1_Pin GPIO_PIN_4
#define ADC_Poten1_GPIO_Port GPIOA
#define ADC_Poten2_Pin GPIO_PIN_5
#define ADC_Poten2_GPIO_Port GPIOA
#define ADC_ShuntA_Pin GPIO_PIN_6
#define ADC_ShuntA_GPIO_Port GPIOA
#define ADC_ShuntB_Pin GPIO_PIN_7
#define ADC_ShuntB_GPIO_Port GPIOA
#define ADC_ShuntC_Pin GPIO_PIN_0
#define ADC_ShuntC_GPIO_Port GPIOB
#define LED_YELLOW_Pin GPIO_PIN_1
#define LED_YELLOW_GPIO_Port GPIOB
#define LED_ORANGE_Pin GPIO_PIN_2
#define LED_ORANGE_GPIO_Port GPIOB
#define TIM2_IC_COMPC_Pin GPIO_PIN_10
#define TIM2_IC_COMPC_GPIO_Port GPIOB
#define USER_BTN_1_Pin GPIO_PIN_11
#define USER_BTN_1_GPIO_Port GPIOB
#define USER_BTN_1_EXTI_IRQn EXTI15_10_IRQn
#define USER_BTN_2_Pin GPIO_PIN_12
#define USER_BTN_2_GPIO_Port GPIOB
#define PWM_CH1N_Pin GPIO_PIN_13
#define PWM_CH1N_GPIO_Port GPIOB
#define PWM_CH2N_Pin GPIO_PIN_14
#define PWM_CH2N_GPIO_Port GPIOB
#define PWM_CH3N_Pin GPIO_PIN_15
#define PWM_CH3N_GPIO_Port GPIOB
#define PWM_CH1_Pin GPIO_PIN_8
#define PWM_CH1_GPIO_Port GPIOA
#define PWM_CH2_Pin GPIO_PIN_9
#define PWM_CH2_GPIO_Port GPIOA
#define PWM_CH3_Pin GPIO_PIN_10
#define PWM_CH3_GPIO_Port GPIOA
#define TIM2_IC_COMPA_Pin GPIO_PIN_15
#define TIM2_IC_COMPA_GPIO_Port GPIOA
#define TIM2_IC_COMPB_Pin GPIO_PIN_3
#define TIM2_IC_COMPB_GPIO_Port GPIOB
#define DEBUG_PB4_Pin GPIO_PIN_4
#define DEBUG_PB4_GPIO_Port GPIOB
#define DEBUG_PB5_Pin GPIO_PIN_5
#define DEBUG_PB5_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
