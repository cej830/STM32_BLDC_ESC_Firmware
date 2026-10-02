import serial
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# --- 설정 ---
COM_PORT = 'COM3'
BAUD_RATE = 115200
BASE_FILENAME = 'OpenLoop_Log_Exp'

def get_next_filename():
    idx = 1
    while os.path.exists(f"{BASE_FILENAME}_{idx}.csv"):
        idx += 1
    return f"{BASE_FILENAME}_{idx}.csv"

def read_and_save_log():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"[{COM_PORT}] 연결 성공. 오픈루프 데이터 수신 대기 중...")
    except Exception as e:
        print(f"포트 연결 에러: {e}")
        return None

    is_logging = False
    headers = []
    data_rows = []

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            if "@START,BLDC_OPENLOOP_LOG" in line:
                print("로그 수신 시작...")
                is_logging = True
                data_rows = []
                continue

            if "@END" in line and is_logging:
                print("로그 수신 완료.")
                break

            if is_logging:
                # 헤더 라인 파싱
                if line.startswith("step"):
                    # 마지막 빈 콤마 제거
                    headers = [h.strip() for h in line.split(',') if h.strip()]
                else:
                    # 데이터 라인 파싱 (C코드 sprintf 마지막의 '. ' 와 콤마 제거)
                    clean_line = line.replace('.', '').replace(' ', '')
                    row = [val.strip() for val in clean_line.split(',') if val.strip()]
                    if len(row) > 0:
                        data_rows.append(row)
                        print(f"수신 중... {len(data_rows)} 샘플", end='\r')

        except KeyboardInterrupt:
            print("\n수신 강제 종료")
            break

    ser.close()

    if headers and data_rows:
        # 데이터 길이 맞추기
        valid_rows = [row[:len(headers)] for row in data_rows if len(row) >= len(headers)]
        df = pd.DataFrame(valid_rows, columns=headers)
        
        # 전체 숫자형 변환
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        filename = get_next_filename()
        df.to_csv(filename, index=False)
        print(f"\n저장 완료: {filename}")
        return df
    else:
        print("\n저장할 데이터가 없습니다.")
        return None

def analyze_openloop_data(df):
    """수신된 데이터를 스텝 기반으로 시각화하여 분석"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    plt.subplots_adjust(hspace=0.3)

    x_axis = df.index # 샘플 순서를 X축으로 사용 (elaptime은 리셋될 수 있으므로)

    # 스텝이 변경되는 인덱스 찾기 (그래프에 세로선 긋기 용도)
    step_changes = df[df['step'] != df['step'].shift(1)].index

    # 1. BEMF 파형 (Zero Crossing 관찰)
    axes[0].set_title("BEMF vs 0V (Does it cross zero within the step?)")
    axes[0].plot(x_axis, df['bemf'], label='BEMF (ADC)', color='blue', linewidth=1.5)
    axes[0].axhline(0, color='red', linestyle='--', linewidth=1.2, label='Zero Line')
    axes[0].set_ylabel("ADC Value")
    axes[0].legend(loc='upper right')
    axes[0].grid(True)

    # 2. 3상 전압 및 Vcom (플로팅 상의 교차점 관찰)
    axes[1].set_title("Phase Voltages & HW Vcom (Floating phase should cross Vcom)")
    axes[1].plot(x_axis, df['phaseA'], label='Phase A', alpha=0.8)
    axes[1].plot(x_axis, df['phaseB'], label='Phase B', alpha=0.8)
    axes[1].plot(x_axis, df['phaseC'], label='Phase C', alpha=0.8)
    axes[1].plot(x_axis, df['Vcom'], label='Hardware Vcom', color='black', linestyle='--', linewidth=2)
    axes[1].set_ylabel("ADC Value")
    axes[1].legend(loc='upper right')
    axes[1].grid(True)

    # 3. Vcom 오차 분석 (하드웨어 Vcom vs 계산된 가상 Vcom)
    axes[2].set_title("Vcom Error (HW Vcom - Calculated Virtual Vcom)")
    axes[2].plot(x_axis, df['V_com_error'], label='Vcom Error', color='purple')
    axes[2].axhline(0, color='black', linestyle='--', linewidth=1)
    axes[2].set_ylabel("Error Value")
    axes[2].set_xlabel("Sample Index")
    axes[2].legend(loc='upper right')
    axes[2].grid(True)

    # 모든 그래프에 스텝 변경 구간 표시 (세로선 및 스텝 번호 텍스트)
    for ax in axes:
        for idx in step_changes:
            ax.axvline(x=idx, color='gray', linestyle=':', alpha=0.7)
            # 스텝 번호를 맨 위쪽 그래프에만 표시
            if ax == axes[0] and idx < len(df) - 1:
                step_num = df['step'].iloc[idx]
                ax.text(idx + 1, ax.get_ylim()[1]*0.9, f"Step {int(step_num)}", color='gray', fontsize=9)

    plt.show()

if __name__ == "__main__":
    data = read_and_save_log()
    if data is not None:
        analyze_openloop_data(data)