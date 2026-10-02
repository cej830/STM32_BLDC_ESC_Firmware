import serial
import csv
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

COM_PORT = 'COM3'       
BAUD_RATE = 115200      

def draw_graph(filename):
    print("\n그래프를 그립니다...")
    df = pd.read_csv(filename)

    cols_to_convert = ['step', 'elapsed_us', 'bemf', 'floating_phase', 'Vcom', 'err']
    for col in cols_to_convert:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna()
    steps = df['step'].unique()

    for step in steps:
        step_data = df[df['step'] == step]
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        
        ax1.plot(step_data['elapsed_us'], step_data['bemf'], label='BEMF', color='blue', linewidth=2)
        ax1.plot(step_data['elapsed_us'], step_data['Vcom'], label='Vcom', color='orange', linestyle='--')
        ax1.set_title(f'BLDC Openloop Log - Step {int(step)}')
        ax1.set_ylabel('Voltage / Value')
        ax1.grid(True)
        ax1.legend()
        
        ax2.plot(step_data['elapsed_us'], step_data['err'], label='Error (err)', color='red')
        ax2.set_xlabel('Elapsed Time (us)')
        ax2.set_ylabel('Error Value')
        ax2.grid(True)
        ax2.legend()
        
        plt.tight_layout()
        plt.show()

def main():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"{COM_PORT} 포트에 연결되었습니다. 데이터를 기다립니다...")
        
        is_logging = False
        data_list = []
        
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if "@START" in line:
                    is_logging = True
                    data_list = [] 
                    print("로깅 시작...")
                    continue
                
                if "@END" in line:
                    is_logging = False
                    print("로깅 종료. 파일로 저장합니다.")
                    break
                
                if is_logging and line:
                    row = line.split(',')
                    data_list.append(row)
                    print(f"수신 중: {line}")
                    
        if len(data_list) > 0:
            # 현재 시간을 가져와서 고유한 파일명 생성
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f'bldc_openloop_{now}.csv'
            
            with open(output_file, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerows(data_list)
            print(f"저장 완료: {output_file}")
            
            # 파일 저장이 끝나면 시리얼 포트를 닫고 그래프 함수 실행
            ser.close() 
            draw_graph(output_file)
            
    except serial.SerialException as e:
        print(f"포트 오류: {e}")
    except KeyboardInterrupt:
        print("종료되었습니다.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()