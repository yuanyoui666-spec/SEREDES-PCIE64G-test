# serial_utils.py - 串口工具函数
import serial
import time
import threading
from datetime import datetime
import re

# 全局缓冲区
com7_received_data = []
com3_received_data = []
com7_receive_lock = threading.Lock()
com3_receive_lock = threading.Lock()
stop_receiving = False


def setup_serial_port(port_name, baud_rate=115200, timeout=1.0):
    """
    设置并打开串口
    """
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout
        )

        if ser.is_open:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 串口 {port_name} 已成功打开，波特率 {baud_rate}")
            return ser
        else:
            print(f"错误: 无法打开串口 {port_name}")
            return None

    except serial.SerialException as e:
        print(f"串口 {port_name} 错误: {e}")
        print(f"请检查: 1) 串口 {port_name} 是否存在 2) 是否有其他程序占用 3) 驱动程序是否正确安装")
        return None
    except Exception as e:
        print(f"串口 {port_name} 未知错误: {e}")
        return None


def receive_data_thread_com7(ser):
    """
    COM7接收串口数据的线程函数
    """
    global stop_receiving

    while not stop_receiving:
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    try:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    except:
                        decoded_data = str(data)

                    with com7_receive_lock:
                        com7_received_data.append((datetime.now(), decoded_data))

            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM7接收数据时出错: {e}")
            break


def receive_data_thread_com3(ser):
    """
    COM3接收串口数据的线程函数
    """
    global stop_receiving

    while not stop_receiving:
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    try:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    except:
                        decoded_data = str(data)

                    with com3_receive_lock:
                        com3_received_data.append((datetime.now(), decoded_data))

            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COM3接收数据时出错: {e}")
            break


def clean_special_chars(text):
    """
    清理文本中的特殊字符
    """
    if not text:
        return ""

    cleaned = ''.join(char for char in text if ord(char) >= 32 or char == '\n' or char == '\t')

    # 移除其他可能影响Excel的特殊字符
    for i in range(1, 32):
        if i not in (9, 10, 13):  # 保留制表符、换行符、回车符
            cleaned = cleaned.replace(chr(i), '')

    return cleaned.strip()


def extract_hex_value(raw_response):
    """
    从MD命令的原始响应中提取十六进制值
    """
    if not raw_response:
        return ""

    lines = raw_response.strip().split('\n')
    hex_value = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 过滤干扰行
        if line.lower().startswith('md '):
            continue
        if 'display in hex:' in line.lower():
            continue
        if 'jingyu:/' in line.lower() or 'jingyu:/$' in line:
            continue
        if line == '$':
            continue

        # 匹配十六进制值
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                value_part = parts[1].strip()
                hex_pattern = r'[0-9a-fA-F]{8}'
                hex_matches = re.findall(hex_pattern, value_part)

                if hex_matches:
                    hex_value = hex_matches[0]
                    break

    return hex_value