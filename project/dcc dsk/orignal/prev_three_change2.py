import serial
import time
import threading
from datetime import datetime
import sys

# 串口配置
SERIAL_PORT = 'COM7'  # 串口号
BAUD_RATE = 115200  # 波特率
READ_TIMEOUT = 1.0  # 串口读取超时（秒）

# 批次配置
# 批次1：初始化阶段 - 较长的延迟和超时
BATCH_1_COMMANDS = [
    "phy_init_only",
    "m3_run",
    "",
    "serdes_start_cm 0 3",
    "",
    "serdes_start_tx 0 0x1 5",
    "",
    "serdes_start_rx 0 0x1 5"
]

# 批次1的配置
BATCH_1_DELAY = 0.3  # 初始化阶段命令间延迟
BATCH_1_RESPONSE_TIMEOUT = 2.0  # 初始化阶段响应超时

# 批次2：快速执行阶段 - 较短的延迟
BATCH_2_COMMANDS = [
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

# 批次2的配置
BATCH_2_DELAY = 0.05  # 快速执行阶段命令间延迟
BATCH_2_RESPONSE_TIMEOUT = 0.3  # 快速执行阶段响应超时

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


def wait_for_response(ser, timeout):
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

        time.sleep(0.05)

    return responses


def send_command_with_params(ser, command, command_delay, response_timeout, batch_name="", cmd_index=0, total_cmds=0):
    """
    发送单个命令并等待响应，使用指定的延迟和超时参数
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
        batch_info = f"[{batch_name}] " if batch_name else ""
        cmd_info = f"({cmd_index}/{total_cmds}) " if total_cmds > 0 else ""
        print(f"[{timestamp}] {batch_info}发送{cmd_info}: {command.strip()}")

        # 等待响应
        time.sleep(command_delay)
        collected_responses = wait_for_response(ser, response_timeout)

        if not collected_responses:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] 警告: 命令 '{command.strip()}' 未收到响应 (超时: {response_timeout}s)")
        else:
            # 显示收集到的响应
            for resp_time, resp_data in collected_responses:
                display_received_data(resp_data, prefix=f"响应")

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 发送命令时出错: {e}")


def send_command_batch(ser, batch_commands, batch_name, command_delay, response_timeout):
    """
    发送一批命令
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始发送批次: {batch_name}")
    print(f"批次配置: 命令间延迟={command_delay}s, 响应超时={response_timeout}s")
    print(f"命令总数: {len([cmd for cmd in batch_commands if cmd.strip()])} 条")

    valid_commands = 0
    for i, cmd in enumerate(batch_commands, 1):
        # 空行只做延迟，不发送
        if not cmd.strip():
            time.sleep(command_delay)
            continue

        # 发送有效命令
        send_command_with_params(
            ser=ser,
            command=cmd,
            command_delay=command_delay,
            response_timeout=response_timeout,
            batch_name=batch_name,
            cmd_index=valid_commands + 1,
            total_cmds=len([c for c in batch_commands if c.strip()])
        )
        valid_commands += 1

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 批次 {batch_name} 发送完成，共发送 {valid_commands} 条有效命令")


def main():
    """
    主函数
    """
    global stop_receiving

    print("=" * 60)
    print("串口通信程序 - 分批次配置延迟参数")
    print(f"目标串口: {SERIAL_PORT}, 波特率: {BAUD_RATE}")
    print("=" * 60)
    print("批次配置详情:")
    print(
        f"1. 初始化阶段: 命令数={len([c for c in BATCH_1_COMMANDS if c.strip()])}条, 延迟={BATCH_1_DELAY}s, 超时={BATCH_1_RESPONSE_TIMEOUT}s")
    print(
        f"2. 快速执行阶段: 命令数={len([c for c in BATCH_2_COMMANDS if c.strip()])}条, 延迟={BATCH_2_DELAY}s, 超时={BATCH_2_RESPONSE_TIMEOUT}s")
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

        # 3. 发送批次1：初始化阶段（较长延迟）
        send_command_batch(
            ser=ser,
            batch_commands=BATCH_1_COMMANDS,
            batch_name="初始化阶段",
            command_delay=BATCH_1_DELAY,
            response_timeout=BATCH_1_RESPONSE_TIMEOUT
        )

        # 批次间额外等待
        batch_interval = 1.0
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 批次间等待 {batch_interval} 秒...")
        time.sleep(batch_interval)

        # 4. 发送批次2：快速执行阶段（较短延迟）
        send_command_batch(
            ser=ser,
            batch_commands=BATCH_2_COMMANDS,
            batch_name="快速执行阶段",
            command_delay=BATCH_2_DELAY,
            response_timeout=BATCH_2_RESPONSE_TIMEOUT
        )

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 所有批次指令发送完成")

        # 5. 等待最终响应
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
        # 6. 清理资源
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