#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

def split_markdown_file(input_file, lines_per_file):
    # 获取输入文件所在的文件夹（输入文件的父目录）
    input_dir = os.path.dirname(os.path.abspath(input_file))

    # 读取输入文件内容
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total_lines = len(lines)
    # 根据指定的行数分割文件
    for i in range(0, total_lines, lines_per_file):
        end_index = min(i + lines_per_file, total_lines)

        # 定义输出文件夹名称（例如 "1-800", "801-1600"）
        folder_name = f"{i+1}-{end_index}"
        # 输出文件夹绝对路径，位于输入文件同一目录下
        output_folder = os.path.join(input_dir, folder_name)

        # 如果输出文件夹不存在则创建
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # 定义新生成的 Markdown 文件名称及其路径
        file_name = f"{folder_name}.md"
        file_path = os.path.join(output_folder, file_name)

        # 将对应区间的内容写入新文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines[i:end_index])

        print(f"创建文件: {file_path}")

def main():
    # 输入 Markdown 文件的路径
    input_file = './test/m2.md'

    # 设置每个分割部分的行数，可在此处修改参数
    lines_per_file = 8

    # 检查文件是否存在
    if not os.path.exists(input_file):
        print("文件不存在!")
        return

    # 检查是否为 Markdown 文件
    if not input_file.endswith('.md'):
        print("不是 Markdown 文件!")
        return

    # 执行分割操作
    split_markdown_file(input_file, lines_per_file)
    print("分割完成!")

if __name__ == "__main__":
    main()
