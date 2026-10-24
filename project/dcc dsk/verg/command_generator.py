# command_generator.py - 命令生成器
def generate_batch_commands_for_lane(mm_param, com3_param, lane_index=0):
    """
    为指定通道生成批次命令
    """
    # 计算通道掩码
    lane_masks = [0x1, 0x2, 0x4, 0x8]  # lane0-lane3的掩码
    lane_mask = lane_masks[lane_index]

    # 根据lane_index计算地址偏移 (每个lane增加0x400)
    addr_offset = lane_index * 0x400

    # 计算每个受影响的寄存器地址
    addr_204c = 0xb030204c + addr_offset
    addr_2028 = 0xb0302028 + addr_offset
    addr_2010 = 0xb0302010 + addr_offset
    addr_2078 = 0xb0302078 + addr_offset

    # COM3命令保持不变
    com3_commands = [
        f"dump_ssm_cal_result {com3_param}",
        f"dump_rx_dll_Deskew_v2 {com3_param}"
    ]

    # 基础命令模板
    base_template = [
        f"0. 启用通道lane{lane_index}",
        f"serdes_start_tx 0 0x{lane_mask:x} 5",
        f"serdes_start_rx 0 0x{lane_mask:x} 5",
        "等待通道启用...",
        "",
        "1.",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x02000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        "serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 2 4 1200",
        f"READ_VOLTAGE_34470A",  # 电压读取标记
        "",
        "2.",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x29000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址
        "serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 2 4 1200",
        f"READ_VOLTAGE_34470A",  # 电压读取标记
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x2a000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址
        "serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 2 4 1200",
        f"READ_VOLTAGE_34470A",  # 电压读取标记
        "3.",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x34000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址
        "serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 2 4 1200",
        f"READ_VOLTAGE_34470A",  # 电压读取标记
        "",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x35000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址
        "serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 2 4 1200",
        f"READ_VOLTAGE_34470A",  # 电压读取标记
        "",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x36000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}",  # 动态地址
        "serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 2 4 1200",
        f"READ_VOLTAGE_34470A",  # 电压读取标记
        "",
        f"mm 0xb0303434 {mm_param}",
        "mm 0xb0303438 0x37000000",
        "mm 0xb030341c 0x00000008",
        f"mm 0x{addr_204c:08x} 0x0000019e",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x000009c0",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"mm 0x{addr_2028:08x} 0x00000840",  # 动态地址
        f"mm 0x{addr_2010:08x} 0x00000040",  # 动态地址
        f"md 0x{addr_2078:08x}"  # 动态地址
        "serdes_ATB_DUMP_BY_SIGNAL_ID 0 0 2 4 1200",
        f"READ_VOLTAGE_34470A",  # 电压读取标记
    ]

    print(f"DEBUG: lane{lane_index} - addr_offset=0x{addr_offset:08x}, addr_2078=0x{addr_2078:08x}")
    return base_template, com3_commands