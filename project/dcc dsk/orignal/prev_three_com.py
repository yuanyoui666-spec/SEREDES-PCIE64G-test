##仅发送，没有消息回传

import serial
import time

# 串口配置
SERIAL_PORT = 'COM7'  # 串口号
BAUD_RATE = 115200  # 波特率
TIMEOUT = 1  # 超时时间（秒）

# 从文档中提取的指令列表
# 注意：文档中的"phy_init_only"、"m3_run"等可能是控制台命令
# 我们将其转换为字符串格式，每个命令后添加换行符
INSTRUCTIONS = [
    "phy_init_only\n",
    "m3_run\n",
    "\n",  # 空行
    "serdes_start_cm 0 3\n",
    "\n",  # 空行
    "serdes_start_tx 0 0x1 5\n",
    "\n",  # 空行
    "serdes_start_rx 0 0x1 5\n",
    "\n",  # 空行
    "1.\n",  # 步骤标记
    "mm 0xb0303434 0x00000000\n",
    "mm 0xb0303438 0x02000000\n",
    "mm 0xb030341c 0x00000008\n",
    "mm 0xb030204c 0x0000019e\n",
    "mm 0xb0302028 0x000009c0\n",
    "mm 0xb0302010 0x00000040\n",
    "mm 0xb0302028 0x00000840\n",
    "mm 0xb0302010 0x00000040\n",
    "\n",  # 空行
    "2.\n",  # 步骤标记
    "mm 0xb0303434 0x00000000\n",
    "mm 0xb0303438 0x29000000\n",
    "mm 0xb030341c 0x00000008\n",
    "mm 0xb030204c 0x0000019e\n",
    "mm 0xb0302028 0x000009c0\n",
    "mm 0xb0302010 0x00000040\n",
    "mm 0xb0302028 0x00000840\n",
    "mm 0xb0302010 0x00000040\n",
    "md 0xb0302078\n",
    "mm 0xb0303434 0x00000000\n",
    "mm 0xb0303438 0x2a000000\n",
    "mm 0xb030341c 0x00000008\n",
    "mm 0xb030204c 0x0000019e\n",
    "mm 0xb0302028 0x000009c0\n",
    "mm 0xb0302010 0x00000040\n",
    "mm 0xb0302028 0x00000840\n",
    "mm 0xb0302010 0x00000040\n",
    "md 0xb0302078\n",
    "3.\n",  # 步骤标记
    "mm 0xb0303434 0x00000000\n",
    "mm 0xb0303438 0x34000000\n",
    "mm 0xb030341c 0x00000008\n",
    "mm 0xb030204c 0x0000019e\n",
    "mm 0xb0302028 0x000009c0\n",
    "mm 0xb0302010 0x00000040\n",
    "mm 0xb0302028 0x00000840\n",
    "mm 0xb0302010 0x00000040\n",
    "md 0xb0302078\n",
    "\n",  # 空行
    "mm 0xb0303434 0x00000000\n",
    "mm 0xb0303438 0x35000000\n",
    "mm 0xb030341c 0x00000008\n",
    "mm 0xb030204c 0x0000019e\n",
    "mm 0xb0302028 0x000009c0\n",
    "mm 0xb0302010 0x00000040\n",
    "mm 0xb0302028 0x00000840\n",
    "mm 0xb0302010 0x00000040\n",
    "md 0xb0302078\n",
    "\n",  # 空行
    "mm 0xb0303434 0x00000000\n",
    "mm 0xb0303438 0x36000000\n",
    "mm 0xb030341c 0x00000008\n",
    "mm 0xb030204c 0x0000019e\n",
    "mm 0xb0302028 0x000009c0\n",
    "mm 0xb0302010 0x00000040\n",
    "mm 0xb0302028 0x00000840\n",
    "mm 0xb0302010 0x00000040\n",
    "md 0xb0302078\n",
    "\n",  # 空行
    "mm 0xb0303434 0x00000000\n",
    "mm 0xb0303438 0x37000000\n",
    "mm 0xb030341c 0x00000008\n",
    "mm 0xb030204c 0x0000019e\n",
    "mm 0xb0302028 0x000009c0\n",
    "mm 0xb0302010 0x00000040\n",
    "mm 0xb0302028 0x00000840\n",
    "mm 0xb0302010 0x00000040\n",
    "md 0xb0302078\n"
]


def send_serial_commands():
    """
    通过串口发送指令列表
    """
    try:
        # 打开串口
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT
        )

        print(f"串口 {SERIAL_PORT} 已打开，波特率 {BAUD_RATE}")

        # 发送所有指令
        for i, cmd in enumerate(INSTRUCTIONS, 1):
            ser.write(cmd.encode('utf-8'))
            print(f"发送指令 {i}/{len(INSTRUCTIONS)}: {cmd.strip()}")

            # 可选的延迟，某些设备需要时间处理指令
            time.sleep(0.1)

            # 可选：读取并打印响应
            if ser.in_waiting:
                response = ser.read(ser.in_waiting)
                if response:
                    print(f"接收响应: {response.decode('utf-8', errors='ignore')}")

        print("所有指令发送完成")

        # 关闭串口
        ser.close()
        print("串口已关闭")

    except serial.SerialException as e:
        print(f"串口错误: {e}")
    except Exception as e:
        print(f"其他错误: {e}")


def read_from_file_and_send(file_path):
    """
    从文件读取指令并通过串口发送
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            instructions = f.readlines()

        # 打开串口
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT
        )

        print(f"从文件 {file_path} 读取指令并通过串口 {SERIAL_PORT} 发送")

        for i, cmd in enumerate(instructions, 1):
            # 确保每条指令以换行符结束
            if not cmd.endswith('\n'):
                cmd = cmd + '\n'

            ser.write(cmd.encode('utf-8'))
            print(f"发送指令 {i}/{len(instructions)}: {cmd.strip()}")

            # 可选的延迟
            time.sleep(0.1)

            # 可选：读取响应
            if ser.in_waiting:
                response = ser.read(ser.in_waiting)
                if response:
                    print(f"接收响应: {response.decode('utf-8', errors='ignore')}")

        print("文件指令发送完成")
        ser.close()

    except FileNotFoundError:
        print(f"文件 {file_path} 未找到")
    except Exception as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    # 使用方法1：使用内置的指令列表
    send_serial_commands()

    # 使用方法2：从文件读取指令（如果需要）
    # file_path = "前3步.txt"  # 您的文件名
    # read_from_file_and_send(file_path)