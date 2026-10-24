# -*- coding: utf-8 -*-
import pyvisa


def read_34470a_voltage(visa_address):
    """
    读取 Keysight 34470A 万用表电压（已修复VISA库找不到问题）
    """
    try:
        # ✅ 关键修复：强制使用 pyvisa-py 纯Python后端，不依赖系统VISA驱动
        rm = pyvisa.ResourceManager('@py')

        # 连接设备
        inst = rm.open_resource(visa_address)
        inst.timeout = 5000

        # 配置并读取直流电压
        inst.write("CONF:VOLT:DC")
        voltage = float(inst.query("READ?"))

        inst.close()
        return voltage

    except Exception as e:
        print(f"读取失败 {visa_address}：{str(e)}")
        return None


# ==================== 主程序 ====================
if __name__ == "__main__":
    # 你的两台设备
    addr1 = "TCPIP0::172.17.17.108::inst0::INSTR"
    addr2 = "TCPIP0::172.17.17.204::inst0::INSTR"

    # 读取设备1
    v1 = read_34470a_voltage(addr1)
    if v1 is not None:
        print(f"设备 187 电压：{v1:.6f} V")

    # 读取设备2
    v2 = read_34470a_voltage(addr2)
    if v2 is not None:
        print(f"设备 108 电压：{v2:.6f} V")