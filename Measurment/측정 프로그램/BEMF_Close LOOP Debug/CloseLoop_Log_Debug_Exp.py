import serial
import os
import pandas as pd
import matplotlib.pyplot as plt

# 설정
COM_PORT = 'COM3'
BAUD_RATE = 115200
BASE_FILENAME = 'CloseLoop_Log_Debug_Exp'

def get_next_filename():
    """폴더 내 파일을 검색하여 다음 실험 번호를 자동 부여"""
    idx = 1
    while os.path.exists(f"{BASE_FILENAME}_{idx}.csv"):
        idx += 1
    return f"{BASE_FILENAME}_{idx}.csv"

def read_and_save_log():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"[{COM_PORT}] 연결 성공. 수신 대기 중...")
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

            if "@START" in line:
                print("로그 수신 시작...")
                is_logging = True
                data_rows = []
                continue

            if "@END" in line and is_logging:
                print("로그 수신 완료.")
                break

            if is_logging:
                # 헤더 라인 파싱 (step,CCR,laptime,...)
                if line.startswith("step"):
                    headers = [h.strip() for h in line.split(',') if h.strip()]
                else:
                    # 데이터 라인 파싱
                    row = [val.strip() for val in line.split(',') if val.strip()]
                    if len(row) > 0:
                        data_rows.append(row)
                        print(f"수신 중... {len(data_rows)}개", end='\r')

        except KeyboardInterrupt:
            print("\n수신 강제 종료")
            break

    ser.close()

    # CSV 저장
    if headers and data_rows:
        # 데이터 길이가 헤더보다 길면 잘라내기 (sprintf 끝의 빈 콤마 처리용)
        valid_rows = [row[:len(headers)] for row in data_rows if len(row) >= len(headers)]
        df = pd.DataFrame(valid_rows, columns=headers)
        
        # 숫자형 데이터로 변환
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        filename = get_next_filename()
        df.to_csv(filename, index=False)
        print(f"\n저장 완료: {filename}")
        return df
    else:
        print("\n저장할 데이터가 없습니다.")
        return None

def analyze_data(df):
    """수신된 데이터를 시각화하여 분석"""
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    plt.subplots_adjust(hspace=0.3)

    # x축을 인덱스 또는 누적 시간으로 설정 가능. 여기서는 샘플 순서(index) 사용
    x_axis = df.index

    # 1. 툭툭 끊기는 현상(Stuttering) 분석: BEMF 파형과 ZC 발생 시점
    axes[0].set_title("BEMF vs ZC Detection (Check for Noise & Chattering)")
    axes[0].plot(x_axis, df['bemf'], label='BEMF', color='blue')
    # ZC가 1인 지점에 빨간 점 찍기
    zc_points = df[df['is_ZC_Occur'] == 1]
    axes[0].scatter(zc_points.index, zc_points['bemf'], color='red', label='ZC Occurred', zorder=5)
    axes[0].axhline(0, color='black', linestyle='--', linewidth=0.8)
    axes[0].legend(loc='upper right')
    axes[0].grid(True)

    # 2. Phase 전압 노이즈 및 플로팅 구간 확인
    axes[1].set_title("Phase Voltages & Vcom (Check for Floating Phase Stability)")
    axes[1].plot(x_axis, df['phaseA'], label='Phase A', alpha=0.7)
    axes[1].plot(x_axis, df['phaseB'], label='Phase B', alpha=0.7)
    axes[1].plot(x_axis, df['phaseC'], label='Phase C', alpha=0.7)
    axes[1].plot(x_axis, df['Vcom'], label='Vcom', color='black', linestyle='--')
    axes[1].legend(loc='upper right')
    axes[1].grid(True)

    """
    # 3. ADC vs Timer IC 지연 시간 분석 (laptime - time_IC_ZC)
    axes[2].set_title("Time Difference: ADC laptime vs Timer IC ZC (us)")
    # time_IC_ZC가 0이 아닐 때만 차이 계산 (IC가 갱신된 시점)
    ic_valid = df[df['time_IC_ZC'] > 0].copy()
    ic_valid['delay'] = ic_valid['laptime'] - ic_valid['time_IC_ZC']
    axes[2].plot(ic_valid.index, ic_valid['delay'], label='Delay (ADC - IC)', color='purple', marker='o', markersize=3)
    axes[2].legend(loc='upper right')
    axes[2].grid(True)
    axes[2].set_xlabel("Sample Index")
    """

    plt.show()

if __name__ == "__main__":
    data = read_and_save_log()
    if data is not None:
        analyze_data(data)