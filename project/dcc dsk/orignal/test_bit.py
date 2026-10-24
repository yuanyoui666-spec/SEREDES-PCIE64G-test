# 在你的主程序中
from Bit import RegisterExtractor

# 初始化提取器
extractor = RegisterExtractor(use_safe_method=True)

# 假设这是你从硬件读取的数据流
raw_registers = [
    0x3e35f90e, 0x3e38040e, 0x3e36d82e,
    0x3e35f84e, 0x3e37388e, 0x3e36010e
]

# 批量处理
results = extractor.process_batch(raw_registers, verbose=True)

# 提取转换后的值
converted_values = [result['data_safe'] for result in results]
print(f"转换后的数据值: {converted_values}")
'''
# 或者直接获取地址和数据
for reg in raw_registers:
    addr, data = extract_register_data(reg, use_safe_method=True)
    print(f"寄存器 0x{reg:08x} -> 地址: {addr}, 数据: {data}")
'''
