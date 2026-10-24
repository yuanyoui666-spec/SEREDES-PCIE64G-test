import serial
import time
import threading
from datetime import datetime
import sys

# 串口配置
SERIAL_PORT = 'COM7'  # 串口号
BAUD_RATE = 115200  # 波特率
READ_TIMEOUT = 1.0  # 读取超时（秒）
COMMAND_DELAY = 0.2  # 命令间延迟（秒）
RESPONSE_TIMEOUT = 2.0  # 等待响应的最大时间（秒）

# 接收缓冲区
received_data = []
receive_lock = threading.Lock()
stop_receiving = False


def setup_serial_port():
    """
    设置并打开串口
    """
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=READ_TIMEOUT
        )

        if ser.is_open:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 串口 {SERIAL_PORT} 已成功打开，波特率 {BAUD_RATE}")
            return ser
        else:
            print(f"错误: 无法打开串口 {SERIAL_PORT}")
            return None

    except serial.SerialException as e:
        print(f"串口错误: {e}")
        print(f"请检查: 1) 串口 {SERIAL_PORT} 是否存在 2) 是否有其他程序占用 3) 驱动程序是否正确安装")
        return None
    except Exception as e:
        print(f"未知错误: {e}")
        return None


def receive_data_thread(ser):
    """
    接收串口数据的线程函数
    """
    global stop_receiving

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动数据接收线程")

    while not stop_receiving:
        try:
            if ser.in_waiting > 0:
                # 读取所有可用数据
                data = ser.read(ser.in_waiting)
                if data:
                    # 尝试以UTF-8解码，失败则显示原始字节
                    try:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    except:
                        decoded_data = str(data)

                    # 存储接收到的数据
                    with receive_lock:
                        received_data.append((datetime.now(), decoded_data))

                    # 实时显示接收到的数据
                    display_received_data(decoded_data)

            # 短暂休眠避免过高CPU占用
            time.sleep(0.01)

        except Exception as e:
            if not stop_receiving:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 接收数据时出错: {e}")
            break

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 数据接收线程已停止")


def display_received_data(data, prefix="接收"):
    """
    显示接收到的数据
    """
    if not data or data.isspace():
        return

    lines = data.strip().split('\n')
    for line in lines:
        if line.strip():  # 只显示非空行
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f"[{timestamp}] {prefix}: {line.strip()}")


def wait_for_response(ser, timeout=RESPONSE_TIMEOUT, expect_pattern=None):
    """
    等待并收集指定时间内的响应
    """
    responses = []
    start_time = time.time()

    while time.time() - start_time < timeout:
        with receive_lock:
            if received_data:
                # 收集新接收的数据
                for timestamp, data in received_data:
                    responses.append((timestamp, data))
                received_data.clear()

        if responses and expect_pattern:
            # 检查是否包含预期的模式
            for timestamp, data in responses:
                if expect_pattern in data:
                    return responses

        time.sleep(0.05)

    return responses


def send_command(ser, command, wait_for_resp=True):
    """
    发送单个命令并等待响应
    """
    if not command or command.isspace():
        return

    # 确保命令以换行符结束
    if not command.endswith('\n'):
        command = command + '\n'

    # 发送命令
    try:
        ser.write(command.encode('utf-8'))
        ser.flush()  # 确保数据发送完成

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f"[{timestamp}] 发送: {command.strip()}")

        if wait_for_resp:
            # 等待响应
            time.sleep(COMMAND_DELAY)
            collected_responses = wait_for_response(ser, RESPONSE_TIMEOUT)

            if not collected_responses:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 警告: 命令 '{command.strip()}' 未收到响应")
            else:
                # 显示收集到的响应
                for resp_time, resp_data in collected_responses:
                    display_received_data(resp_data, prefix=f"响应")

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 发送命令时出错: {e}")


def get_instructions():
    """
    返回要发送的指令列表
    """
    return [
        "phy_init_only",
        "m3_run",
        "",
        "serdes_start_cm 0 3",
        "",
        "serdes_start_tx 0 0x1 5",
        "",
        "serdes_start_rx 0 0x1 5",
        "",
        "1.",
        "mm 0xb0303434 0x00000000",
        "mm 0xb0303438 0x02000000",
        "mm 0xb030341c 0x00000008",
        "mm 0xb030204c 0x0000019e",
        "mm 0xb0302028 0x000009c0",
        "mm 0xb0302010 0x00000040",
        "mm 0xb0302028 0x00000840",
        "mm 0xb0302010 0x00000040",
        "",
        "2.",
        "mm 0xb0303434 0x00000000",
        "mm 0xb0303438 0x29000000",
        "mm 0xb030341c 0x00000008",
        "mm 0xb030204c 0x0000019e",
        "mm 0xb0302028 0x000009c0",
        "mm 0xb0302010 0x00000040",
        "mm 0xb0302028 0x00000840",
        "mm 0xb0302010 0x00000040",
        "md 0xb0302078",
        "mm 0xb0303434 0x00000000",
        "mm 0xb0303438 0x2a000000",
        "mm 0xb030341c 0x00000008",
        "mm 0xb030204c 0x0000019e",
        "mm 0xb0302028 0x000009c0",
        "mm 0xb0302010 0x00000040",
        "mm 0xb0302028 0x00000840",
        "mm 0xb0302010 0x00000040",
        "md 0xb0302078",
        "3.",
        "mm 0xb0303434 0x00000000",
        "mm 0xb0303438 0x34000000",
        "mm 0xb030341c 0x00000008",
        "mm 0xb030204c 0x0000019e",
        "mm 0xb0302028 0x000009c0",
        "mm 0xb0302010 0x00000040",
        "mm 0xb0302028 0x00000840",
        "mm 0xb0302010 0x00000040",
        "md 0xb0302078",
        "",
        "mm 0xb0303434 0x00000000",
        "mm 0xb0303438 0x35000000",
        "mm 0xb030341c 0x00000008",
        "mm 0xb030204c 0x0000019e",
        "mm 0xb0302028 0x000009c0",
        "mm 0xb0302010 0x00000040",
        "mm 0xb0302028 0x00000840",
        "mm 0xb0302010 0x00000040",
        "md 0xb0302078",
        "",
        "mm 0xb0303434 0x00000000",
        "mm 0xb0303438 0x36000000",
        "mm 0xb030341c 0x00000008",
        "mm 0xb030204c 0x0000019e",
        "mm 0xb0302028 0x000009c0",
        "mm 0xb0302010 0x00000040",
        "mm 0xb0302028 0x00000840",
        "mm 0xb0302010 0x00000040",
        "md 0xb0302078",
        "",
        "mm 0xb0303434 0x00000000",
        "mm 0xb0303438 0x37000000",
        "mm 0xb030341c 0x00000008",
        "mm 0xb030204c 0x0000019e",
        "mm 0xb0302028 0x000009c0",
        "mm 0xb0302010 0x00000040",
        "mm 0xb0302028 0x00000840",
        "mm 0xb0302010 0x00000040",
        "md 0xb0302078"
    ]


def main():
    """
    主函数
    """
    global stop_receiving

    print("=" * 60)
    print("串口通信程序 - 支持发送和接收")
    print(f"目标串口: {SERIAL_PORT}, 波特率: {BAUD_RATE}")
    print("=" * 60)

    # 1. 打开串口
    ser = setup_serial_port()
    if not ser:
        print("程序退出")
        return

    receiver_thread = None

    try:
        # 2. 启动接收线程
        stop_receiving = False
        receiver_thread = threading.Thread(target=receive_data_thread, args=(ser,), daemon=True)
        receiver_thread.start()

        # 等待接收线程启动
        time.sleep(0.5)

        # 3. 发送指令
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始发送指令...")
        instructions = get_instructions()

        for i, cmd in enumerate(instructions, 1):
            # 空行只做延迟，不发送
            if not cmd.strip():
                time.sleep(COMMAND_DELAY)
                continue

            send_command(ser, cmd, wait_for_resp=True)

            # 显示进度
            progress = (i / len(instructions)) * 100
            print(f"进度: {i}/{len(instructions)} ({progress:.1f}%)")

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 所有指令发送完成")

        # 4. 等待最终响应
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待额外响应...")
        time.sleep(1.0)

        # 检查是否有未显示的响应
        with receive_lock:
            if received_data:
                print("\n最终接收到的数据:")
                for timestamp, data in received_data:
                    display_received_data(data, prefix=f"[{timestamp.strftime('%H:%M:%S')}]")

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行完成")

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断程序")
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 程序执行出错: {e}")
    finally:
        # 5. 清理资源
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在清理资源...")
        stop_receiving = True

        if receiver_thread and receiver_thread.is_alive():
            receiver_thread.join(timeout=1.0)

        if ser and ser.is_open:
            ser.close()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 串口已关闭")

        print("程序结束")


if __name__ == "__main__":
    main()