# 寻找 md 文档在转换成 EPUB 时出现的错误

import os

def split_markdown_file(input_file, lines_per_file=2):
    # 读取输入文件
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 计算需要创建的文件数
    total_lines = len(lines)

    # 按每50行进行分割
    for i in range(0, total_lines, lines_per_file):
        # 计算当前批次的结束行号
        end_index = min(i + lines_per_file, total_lines)

        # 创建文件夹名称 (例如: "1-50")
        folder_name = f"{i+1}-{end_index}"

        # 创建文件夹
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        # 创建文件名 (与文件夹名相同)
        file_name = f"{folder_name}.md"
        file_path = os.path.join(folder_name, file_name)

        # 写入内容到新文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines[i:end_index])

        print(f"创建文件: {file_path}")

def main():
    # 获取用户输入
    input_file = './t3/i.md'
    # 检查文件是否存在
    if not os.path.exists(input_file):
        print("文件不存在!")
        return

    # 检查是否为Markdown文件
    if not input_file.endswith('.md'):
        print("不是Markdown文件!")
        return

    # 执行分割
    split_markdown_file(input_file)
    print("分割完成!")

if __name__ == "__main__":
    main()
