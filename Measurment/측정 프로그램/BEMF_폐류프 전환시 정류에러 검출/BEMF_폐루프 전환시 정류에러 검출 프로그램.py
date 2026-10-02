import serial
import csv
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

COM_PORT = 'COM3'       
BAUD_RATE = 115200      

def analyze_and_plot(filename):
    print("\n데이터 분석 및 그래프 생성을 시작합니다...")
    df = pd.read_csv(filename)

    # 문자열 등에 포함된 공백 제거 및 숫자로 변환
    cols_to_convert = ['step', 'laptime', 'bemf', 'is_ZC_Occur', 'Trigger_delay']
    for col in cols_to_convert:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna().copy()
    
    # 20kHz 샘플링 주기 적용: 1 샘플 = 50us = 0.05ms
    df['time_ms'] = df.index * 0.05

    # 스텝이 변경되는 시점 찾기 (수직선으로 표시하기 위함)
    step_changes = df[df['step'] != df['step'].shift(1)]

    # ZC가 검출된 시점 찾기
    zc_events = df[df['is_ZC_Occur'] > 0]

    # 그래프 2단 구성
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # --- [상단 그래프] BEMF 파형 및 제어 이벤트 분석 ---
    ax1.plot(df['time_ms'], df['bemf'], label='BEMF (ADC)', color='blue', alpha=0.7)
    
    # 스텝 변경 지점을 회색 점선 수직선으로 표시
    for _, row in step_changes.iterrows():
        ax1.axvline(x=row['time_ms'], color='gray', linestyle='--', alpha=0.5)
        # 스텝 번호 텍스트 표시
        ax1.text(row['time_ms'], df['bemf'].max() * 0.9, f"S{int(row['step'])}", color='black', fontsize=9)
        
    # ZC 검출 지점을 빨간색 'X' 마커로 겹쳐서 표시
    ax1.scatter(zc_events['time_ms'], zc_events['bemf'], color='red', marker='x', s=100, label='ZC Detected', zorder=5)

    ax1.set_title('BEMF Waveform, Step Changes & ZC Detection (20kHz Sampling)')
    ax1.set_ylabel('BEMF Value')
    ax1.grid(True)
    ax1.legend(loc='upper right')

    # --- [하단 그래프] 타이밍 (Laptime & Trigger Delay) 분석 ---
    ax2.plot(df['time_ms'], df['laptime'], label='Laptime', color='green', linewidth=1.5)
    ax2.plot(df['time_ms'], df['Trigger_delay'], label='Trigger Delay (30 deg wait)', color='purple', linewidth=1.5)
    
    # ZC 검출 시점의 Trigger delay 값을 명확히 점으로 표시
    ax2.scatter(zc_events['time_ms'], zc_events['Trigger_delay'], color='purple', s=30)

    ax2.set_title('Timing Analysis: Commutation Period vs Calculated 30° Delay')
    ax2.set_xlabel('Time (ms)')
    ax2.set_ylabel('Timer Value (Ticks/us)')
    ax2.grid(True)
    ax2.legend(loc='upper right')

    plt.tight_layout()
    plt.show()

def main():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"{COM_PORT} 포트에 연결되었습니다. 배열 로그 데이터를 기다립니다...")
        
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
                    # 전체 데이터를 터미널에 다 찍으면 느려질 수 있으므로 점(.)으로 진행상황 대체 가능
                    # print(f"수신 중: {line}") 
                    
        if len(data_list) > 0:
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f'bldc_debug_{now}.csv'
            
            with open(output_file, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerows(data_list)
            print(f"저장 완료: {output_file}")
            
            ser.close() 
            analyze_and_plot(output_file)
            
    except serial.SerialException as e:
        print(f"포트 오류: {e}")
    except KeyboardInterrupt:
        print("종료되었습니다.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()