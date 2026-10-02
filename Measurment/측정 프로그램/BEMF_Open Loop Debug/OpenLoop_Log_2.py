import os
import serial
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
            raw_line = ser.readline()
            if not raw_line:
                continue
            line = raw_line.decode('utf-8', errors='ignore').strip()

            if "@START,BLDC_OPENLOOP_LOG" in line:
                print("로그 수신 시작...")
                is_logging = True
                data_rows = []
                continue

            if "@END" in line and is_logging:
                print("로그 수신 완료.")
                break

            if is_logging:
                if line.startswith("step"):
                    headers = [h.strip() for h in line.split(',') if h.strip()]
                else:
                    # 데이터 파싱
                    row = [val.strip() for val in line.split(',') if val.strip()]
                    if len(row) > 0:
                        data_rows.append(row)
                        print(f"수신 중... {len(data_rows)} 샘플", end='\r')

        except KeyboardInterrupt:
            print("\n수신 강제 종료")
            break

    ser.close()

    if headers and data_rows:
        valid_rows = [row[:len(headers)] for row in data_rows if len(row) >= len(headers)]
        df = pd.DataFrame(valid_rows, columns=headers)
        
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
    """BEMF 제로크로싱(ZC) 시간을 감지하여 그래프 및 텍스트로 표시"""
    fig, axes = plt.subplots(2, 1, figsize=(15, 9), sharex=True)
    plt.subplots_adjust(hspace=0.25)

    x_axis = df.index

    # 1. 스텝 전환 인덱스 추출
    step_changes = df[df['step'] != df['step'].shift(1)].index.tolist()
    step_ends = step_changes[1:] + [len(df)]

    # 2. 제로크로싱(ZC) 검출
    zc_list = []  # (step, x_idx, elaptime, zc_type, bemf_val)
    
    print("\n" + "="*50)
    print(f"{'Step':^6} | {'ZC Type':^9} | {'ZC Elaptime (us)':^18} | {'Sample Index':^12}")
    print("="*50)

    for i in range(len(step_changes)):
        start_idx = step_changes[i]
        end_idx = step_ends[i]
        step_df = df.iloc[start_idx:end_idx]
        if len(step_df) < 2:
            continue
        
        step_num = int(step_df['step'].iloc[0])
        zc_detected = False

        for j in range(len(step_df) - 1):
            curr_b = step_df['bemf'].iloc[j]
            next_b = step_df['bemf'].iloc[j + 1]

            # 홀수 스텝: 하강(Falling Edge, +에서 -로 교차)
            if step_num in [1, 3, 5]:
                if curr_b >= 0 and next_b < 0:
                    zc_idx = step_df.index[j + 1]
                    zc_time = step_df['elaptime'].iloc[j + 1]
                    zc_list.append((step_num, zc_idx, zc_time, 'Falling', next_b))
                    print(f"{step_num:^6} | {'Falling':^9} | {zc_time:^18} | {zc_idx:^12}")
                    zc_detected = True
                    break

            # 짝수 스텝: 상승(Rising Edge, -에서 +로 교차)
            else:
                if curr_b <= 0 and next_b > 0:
                    zc_idx = step_df.index[j + 1]
                    zc_time = step_df['elaptime'].iloc[j + 1]
                    zc_list.append((step_num, zc_idx, zc_time, 'Rising', next_b))
                    print(f"{step_num:^6} | {'Rising':^9} | {zc_time:^18} | {zc_idx:^12}")
                    zc_detected = True
                    break

        if not zc_detected:
            print(f"{step_num:^6} | {'None':^9} | {'Not Detected':^18} | {'-':^12}")
            
    print("="*50 + "\n")

    # --- 그래프 1: BEMF 및 ZC 마커 ---
    axes[0].set_title("BEMF & Detected Zero-Crossing Timing", fontsize=12, fontweight='bold')
    axes[0].plot(x_axis, df['bemf'], label='BEMF (ADC)', color='blue', linewidth=1.5)
    axes[0].axhline(0, color='red', linestyle='--', linewidth=1.0, alpha=0.8, label='Zero Line')
    
    # ZC 포인트 빨간 점 및 시간(us) 텍스트 표기
    for step_num, zc_idx, zc_time, zc_type, val in zc_list:
        axes[0].plot(zc_idx, val, 'ro', markersize=7)
        # 텍스트 위치 (위/아래 엇갈려 표시하여 가독성 확보)
        y_offset = 8 if zc_type == 'Rising' else -12
        axes[0].annotate(f"{int(zc_time)} us", 
                         xy=(zc_idx, val), 
                         xytext=(zc_idx, val + y_offset),
                         fontsize=9, fontweight='bold', color='darkred',
                         arrowprops=dict(arrowstyle="->", color='red', lw=1),
                         ha='center')

    axes[0].set_ylabel("BEMF ADC Value")
    axes[0].legend(loc='upper right')
    axes[0].grid(True, linestyle=':', alpha=0.6)

    # --- 그래프 2: 3상 전압 및 SW/HW Vcom ---
    axes[1].set_title("Phase Voltages & Vcom", fontsize=12, fontweight='bold')
    axes[1].plot(x_axis, df['phaseA'], label='Phase A', alpha=0.8)
    axes[1].plot(x_axis, df['phaseB'], label='Phase B', alpha=0.8)
    axes[1].plot(x_axis, df['phaseC'], label='Phase C', alpha=0.8)
    if 'Vcom' in df.columns:
        axes[1].plot(x_axis, df['Vcom'], label='Vcom', color='black', linestyle='--', linewidth=1.8)
    axes[1].set_ylabel("ADC Raw Value")
    axes[1].set_xlabel("Sample Index")
    axes[1].legend(loc='upper right')
    axes[1].grid(True, linestyle=':', alpha=0.6)

    # 스텝 경계선 및 스텝 이름 표시
    for ax in axes:
        for idx in step_changes:
            ax.axvline(x=idx, color='gray', linestyle=':', alpha=0.8)
            if ax == axes[0] and idx < len(df) - 1:
                step_val = df['step'].iloc[idx]
                ax.text(idx + 2, ax.get_ylim()[1] * 0.88, f"Step {int(step_val)}", 
                        color='gray', fontsize=9, fontweight='bold')

    plt.show()

if __name__ == "__main__":
    data = read_and_save_log()
    if data is not None:
        analyze_openloop_data(data)