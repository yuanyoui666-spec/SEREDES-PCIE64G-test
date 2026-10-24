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

# 调试标志
DEBUG_SERIAL = False


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

                    if DEBUG_SERIAL:
                        # 打印接收到的数据（调试用）
                        print(f"[DEBUG-COM7] 接收到 {len(data)} 字节: {repr(decoded_data[:100])}")

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
    增强版本 - 支持多种格式
    """
    if not raw_response:
        return ""

    # 首先尝试匹配标准的8位十六进制数
    hex_pattern = r'[0-9a-fA-F]{8}'

    print(f"[DEBUG-EXTRACT] 原始响应: {repr(raw_response)}")

    # 方法1: 查找冒号后面的值
    lines = raw_response.strip().split('\n')
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

        print(f"[DEBUG-EXTRACT] 处理行: {repr(line)}")

        # 查找冒号后的值
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                value_part = parts[1].strip()
                # 移除可能的空格和前缀
                value_part = value_part.replace('0x', '').replace('0X', '').strip()
                matches = re.findall(hex_pattern, value_part)
                if matches:
                    print(f"[DEBUG-EXTRACT] 从冒号后提取: {matches[0]}")
                    return matches[0]

        # 直接匹配整行中的十六进制数
        matches = re.findall(hex_pattern, line)
        if matches:
            print(f"[DEBUG-EXTRACT] 从行中提取: {matches[0]}")
            return matches[0]

    # 方法2: 在整个响应中查找
    # 先移除干扰前缀
    cleaned = raw_response
    # 移除 md 命令本身
    cleaned = re.sub(r'^md\s+0x[0-9a-fA-F]+\s*', '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
    # 移除 shell 提示符
    cleaned = re.sub(r'jingyu:/[^ ]*\s*', '', cleaned)
    cleaned = re.sub(r'\$\s*', '', cleaned)

    matches = re.findall(hex_pattern, cleaned)
    if matches:
        print(f"[DEBUG-EXTRACT] 从清理后提取: {matches[0]}")
        return matches[0]

    print(f"[DEBUG-EXTRACT] 未提取到十六进制值")
    return ""