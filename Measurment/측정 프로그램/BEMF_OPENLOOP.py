import serial
import csv
import time

# --- 설정 부분 ---
COM_PORT = 'COM3'       # 사용하는 COM 포트 번호에 맞게 수정하세요
BAUD_RATE = 115200      # 통신 속도
OUTPUT_FILE = 'bldc_openloop_log.csv' # 저장될 파일 이름

def main():
    try:
        # 시리얼 포트 열기
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"{COM_PORT} 포트에 {BAUD_RATE} 속도로 연결되었습니다.")
        print("데이터 수신 대기 중... (@START 태그를 기다립니다)")
        
        is_logging = False
        data_list = []
        
        while True:
            # 수신된 데이터가 있는지 확인
            if ser.in_waiting > 0:
                # 데이터를 한 줄씩 읽고 문자열로 변환 (공백 및 줄바꿈 제거)
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                # 시작 태그 확인
                if "@START" in line:
                    is_logging = True
                    data_list = [] # 새 로그를 위해 데이터 초기화
                    print("로깅 시작 태그 감지. 데이터를 수집합니다...")
                    continue
                
                # 종료 태그 확인
                if "@END" in line:
                    is_logging = False
                    print("로깅 종료 태그 감지. 수집을 멈추고 파일로 저장합니다.")
                    break
                
                # 로깅 상태일 때만 데이터 리스트에 추가
                if is_logging:
                    if not line: # 빈 줄은 건너뜀
                        continue
                    
                    # 쉼표를 기준으로 데이터를 나누어 리스트로 만듦
                    row = line.split(',')
                    data_list.append(row)
                    
                    # 수신 상황을 화면에 간단히 표시
                    print(f"수신 중: {line}")
                    
        # 수집된 데이터를 CSV 파일로 저장
        if len(data_list) > 0:
            with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                # 데이터 전체를 한 번에 저장 (첫 줄은 step, elapsed_us, bemf 헤더)
                writer.writerows(data_list)
            print(f"\n데이터가 성공적으로 저장되었습니다: {OUTPUT_FILE}")
        else:
            print("\n저장할 데이터가 수집되지 않았습니다.")
            
    except serial.SerialException as e:
        print(f"\n시리얼 포트 연결 오류: {e}")
        print("포트 번호가 맞는지, 혹은 다른 프로그램에서 COM3를 사용 중인지 확인하세요.")
    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 종료되었습니다.")
    finally:
        # 프로그램 종료 시 안전하게 시리얼 포트 닫기
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("시리얼 포트를 닫았습니다.")

if __name__ == "__main__":
    main()