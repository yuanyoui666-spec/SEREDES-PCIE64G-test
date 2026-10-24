# config.py - 配置文件
import warnings
warnings.filterwarnings('ignore')

# ========== 串口配置 ==========
SERIAL_PORT_COM7 = 'COM4'  # 串口号 - jingyu
SERIAL_PORT_COM3 = 'COM26'  # 串口号 - shell
BAUD_RATE = 115200  # 波特率
READ_TIMEOUT = 1.0  # 串口读取超时（秒）

# ========== 通道配置 ==========
# 只有4个通道（lane0-lane3），每个通道有特定的参数
LANE_CONFIGS = [
    {
        'name': 'lane0',
        'mm_param': '0x00000000',  # 第一个字节为0x01
        'com3_param': '0'  # COM3函数参数
    },
    {
        'name': 'lane1',
        'mm_param': '0x00000001',  # 第一个字节为0x02
        'com3_param': '1'  # COM3函数参数
    },
    {
        'name': 'lane2',
        'mm_param': '0x00000002',  # 第一个字节为0x03
        'com3_param': '2'  # COM3函数参数
    },
    {
        'name': 'lane3',
        'mm_param': '0x00000003',  # 第一个字节为0x04
        'com3_param': '3'  # COM3函数参数
    }
]

# ========== 批次配置 ==========
# 批次1：初始化阶段 - 较长的延迟和超时
BATCH_1_COMMANDS = [
    "phy_init_only",
    "m3_run",
    "",
    "serdes_start_cm 0 3",
    "",
    "echo 基础初始化完成，准备通道测试...",  # 调试信息
]

# 批次1的配置
BATCH_1_DELAY = 0.5  # 初始化阶段命令间延迟
BATCH_1_RESPONSE_TIMEOUT = 3.0  # 初始化阶段响应超时
BATCH_1_SHOW_TX_RX = True  # 批次1显示发送和接收消息

# 批次2的配置
BATCH_2_DELAY = 0.2  # 快速执行阶段命令间延迟
BATCH_2_RESPONSE_TIMEOUT = 2.5  # 快速执行阶段响应超时
BATCH_2_SHOW_TX_RX = False  # 批次2不显示发送和接收消息（除了md命令）
BATCH_2_RETRY_COUNT = 1  # 对MD命令失败时重试次数

# COM3配置
COM3_DELAY = 1.0  # COM3命令间延迟
COM3_RESPONSE_TIMEOUT = 3.0  # COM3响应超时
COM3_SHOW_TX_RX = True  # COM3显示发送和接收消息