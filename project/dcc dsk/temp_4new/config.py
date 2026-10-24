# config.py - 配置文件（适配新固件）
import warnings
warnings.filterwarnings('ignore')

# ========== 串口配置 ==========
SERIAL_PORT_COM7 = 'COM4'   # 串口号 - jingyu (主控制)
SERIAL_PORT_COM3 = 'COM29'  # 串口号 - shell (辅助)
BAUD_RATE = 115200          # 波特率
READ_TIMEOUT = 1.0          # 串口读取超时（秒）

# ========== 通道配置 ==========
LANE_CONFIGS = [
    {'name': 'lane0', 'mm_param': '0x00000000', 'com3_param': '0'},
    {'name': 'lane1', 'mm_param': '0x00000001', 'com3_param': '1'},
    {'name': 'lane2', 'mm_param': '0x00000002', 'com3_param': '2'},
    {'name': 'lane3', 'mm_param': '0x00000003', 'com3_param': '3'},
]

# ========== 新固件完整初始化命令（一次性初始化） ==========
# 注意：这里放在 BATCH_1_COMMANDS 中，会在逐个lane测试前执行
INIT_COMMANDS_NEW = [
    "phy_init_only",
    "m3_run",
    "phy_macro_reset",                     # 新固件必需
    "serdes_set_cca_skip 0 0 0 0xffffffff",
    "serdes_set_cca_skip 0 0 1 0xffffffff",
    "serdes_start_cm 0 0 3",               # 新固件参数
    "serdes_pstate_chg 0 0 0xf 0",
    "serdes_rate_chg 0 0 0xf 5",
    "echo 基础初始化完成，准备通道测试..."
]

# ========== 批次配置 ==========
BATCH_1_COMMANDS = INIT_COMMANDS_NEW   # 使用新初始化命令
BATCH_1_DELAY = 0.5
BATCH_1_RESPONSE_TIMEOUT = 3.0
BATCH_1_SHOW_TX_RX = True

BATCH_2_DELAY = 0.2
BATCH_2_RESPONSE_TIMEOUT = 2.5
BATCH_2_SHOW_TX_RX = False
BATCH_2_RETRY_COUNT = 1

COM3_DELAY = 1.0
COM3_RESPONSE_TIMEOUT = 10.0
COM3_SHOW_TX_RX = True

# ========== lane启用命令（保持逐个启用，但新固件可一次性，这里保留原逻辑） ==========
# 无需额外配置