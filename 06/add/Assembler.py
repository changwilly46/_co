import sys
import os

# --- 預定義符號表 (Symbol Table) ---
symbols = {
    "SP": 0, "LCL": 1, "ARG": 2, "THIS": 3, "THAT": 4,
    "R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5, "R6": 6, "R7": 7,
    "R8": 8, "R9": 9, "R10": 10, "R11": 11, "R12": 12, "R13": 13, "R14": 14, "R15": 15,
    "SCREEN": 16384, "KBD": 24576
}

# --- C-指令轉換字典 ---
comp_dict = {
    "0": "0101010", "1": "0111111", "-1": "0111010", "D": "0001100",
    "A": "0110000", "!D": "0001101", "!A": "0110001", "-D": "0001111",
    "-A": "0110011", "D+1": "0011111", "A+1": "0110111", "D-1": "0001110",
    "A-1": "0110010", "D+A": "0000010", "D-A": "0010011", "A-D": "0000111",
    "D&A": "0000000", "D|A": "0010101",
    "M": "1110000", "!M": "1110001", "-M": "1110011", "M+1": "1110111",
    "M-1": "1110010", "D+M": "1000010", "D-M": "1010011", "M-D": "1000111",
    "D&M": "1000000", "D|M": "1010101"
}

dest_dict = {
    "null": "000", "M": "001", "D": "010", "MD": "011",
    "A": "100", "AM": "101", "AD": "110", "AMD": "111"
}

jump_dict = {
    "null": "000", "JGT": "001", "JEQ": "010", "JGE": "011",
    "JLT": "100", "JNE": "101", "JLE": "110", "JMP": "111"
}


def clean_code(lines):
    """移除註解與空白"""
    cleaned = []
    for line in lines:
        line = line.split('//')[0].strip()
        if line:
            cleaned.append(line)
    return cleaned


def parse_c_instruction(instruction):
    """解析 C-指令為 dest, comp, jump"""
    dest = "null"
    jump = "null"

    if "=" in instruction:
        dest, comp_part = instruction.split("=")
    else:
        comp_part = instruction

    if ";" in comp_part:
        comp, jump = comp_part.split(";")
    else:
        comp = comp_part

    return dest, comp, jump


def assemble(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    instructions = clean_code(lines)

    # 第一階段 (Pass 1)：建立標籤 (Labels)
    # 掃描 (XXX) 並記錄其對應的 ROM 位址
    rom_address = 0
    code_without_labels = []
    for inst in instructions:
        if inst.startswith('(') and inst.endswith(')'):
            label = inst[1:-1]
            symbols[label] = rom_address
        else:
            code_without_labels.append(inst)
            rom_address += 1

    # 第二階段 (Pass 2)：翻譯指令與處理變數
    # 將組譯碼轉為 16-bit 二進位字串
    next_variable_address = 16
    binary_output = []

    for inst in code_without_labels:
        # 處理 A-指令 (@value 或 @symbol)
        if inst.startswith('@'):
            symbol = inst[1:]
            if symbol.isdigit():
                address = int(symbol)
            else:
                if symbol not in symbols:
                    symbols[symbol] = next_variable_address
                    next_variable_address += 1
                address = symbols[symbol]
            # 轉為 16 位元二進位字串
            binary_output.append(f"{address:016b}")

        # 處理 C-指令 (dest=comp;jump)
        else:
            dest, comp, jump = parse_c_instruction(inst)
            c_binary = "111" + comp_dict[comp] + dest_dict[dest] + jump_dict[jump]
            binary_output.append(c_binary)

    # 輸出成 .hack 檔案
    output_filepath = os.path.splitext(filepath)[0] + ".hack"
    with open(output_filepath, 'w') as f:
        for binary_line in binary_output:
            f.write(binary_line + '\n')

    print(f"組譯完成！輸出檔案: {output_filepath}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python assembler.py <file.asm>")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"錯誤: 找不到檔案 '{input_file}'")
        sys.exit(1)

    assemble(input_file)
