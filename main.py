#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import subprocess
import requests
from datetime import datetime
from PIL import Image
import re
from tqdm import tqdm
from natsort import natsorted

def preprocess_markdown(content: str) -> str:
    """Preprocess Markdown content to handle line breaks without affecting code blocks or lists."""

    # To store and temporarily replace code blocks and list blocks
    code_blocks = []
    list_blocks = []

    # Save the code block and return a placeholder
    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"CODE_BLOCK_{len(code_blocks)-1}"

    # Save the list block and return a placeholder
    def save_list_block(match):
        list_blocks.append(match.group(0))
        return f"LIST_BLOCK_{len(list_blocks)-1}"

    # 修改这里的正则表达式以正确匹配列表
    # Temporarily replace code blocks and lists with placeholders
    content = re.sub(r'```[\s\S]*?```', save_code_block, content)
    # 修改列表匹配的正则表达式
    content = re.sub(r'(?m)^[ ]*[-*+][ ]+.*?(?=\n\n|\Z)', save_list_block, content)

    # Process the content for paragraph breaks: replace single newlines in non-block content
    def process_paragraphs(match):
        # Process only the paragraphs not in code or list blocks
        return re.sub(r'\n(?!\n)', ' ', match.group(0).strip())

    content = re.sub(r'(?<!CODE_BLOCK_\d+)(?<!LIST_BLOCK_\d+)(?<=\S)[^\n]*\n+[^\n]*(?=\n{2}|\Z)', process_paragraphs, content)

    # Restore the code blocks
    for i, block in enumerate(code_blocks):
        content = content.replace(f"CODE_BLOCK_{i}", block)

    # Restore the list blocks
    for i, block in enumerate(list_blocks):
        content = content.replace(f"LIST_BLOCK_{i}", block)

    return content

def download_image(url, output_dir):
    response = None
    try:
        response = requests.get(url)
        response.raise_for_status()

        # 从 URL 获取文件扩展名
        original_ext = os.path.splitext(url)[1].lower()

        # 获取 Content-Type
        content_type = response.headers.get('content-type', '').lower()

        # 根据 Content-Type 或 URL 确定正确的扩展名
        if 'jpeg' in content_type or 'jpg' in content_type or original_ext in ['.jpg', '.jpeg']:
            final_ext = '.jpg'
        elif 'png' in content_type or original_ext == '.png':
            final_ext = '.png'
        elif 'gif' in content_type or original_ext == '.gif':
            final_ext = '.gif'
        elif 'webp' in content_type or original_ext == '.webp':
            final_ext = '.jpg'  # 将 webp 转换为 jpg
        else:
            final_ext = '.jpg'  # 默认使用 jpg

        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 生成唯一的文件名
        image_name = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}{final_ext}"
        image_path = os.path.join(output_dir, image_name)

        # 先保存原始图片数据
        with open(image_path, 'wb') as f:
            f.write(response.content)

        # 使用 PIL 处理图片
        try:
            with Image.open(image_path) as img:
                # 转换为 RGB 模式
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img = img.convert('RGB')
                # 根据扩展名选择保存格式
                save_format = 'JPEG' if final_ext == '.jpg' else 'PNG'
                img.save(image_path, save_format, quality=85)
        except Exception as e:
            print(f"图片处理失败: {e}")
            if os.path.exists(image_path):
                os.remove(image_path)
            return None

        print(f"已下载并保存图像：{image_path}")
        return image_path

    except Exception as e:
        print(f"图像下载失败:{url}, error:{e}")
        if response:
            print(f"Content-Type: {response.headers.get('content-type')}")
        return None

def compress_image(image_path, output_dir=None, max_size=(200, 200)):
    """压缩图像并保存"""
    try:
        # 获取原始文件大小
        original_size = os.path.getsize(image_path) / 1024  # 转换为 KB

        with Image.open(image_path) as img:
            # 获取原始图片尺寸
            original_dimensions = img.size

            # 压缩图片
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 获取压缩后的尺寸
            compressed_dimensions = img.size

            if output_dir:
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                compressed_path = os.path.join(output_dir, os.path.basename(image_path))
            else:
                compressed_path = image_path

            # 保存压缩后的图片
            img.save(compressed_path, quality=50)

            # 获取压缩后文件大小
            compressed_size = os.path.getsize(compressed_path) / 1024  # 转换为 KB

            print(f"压缩图像: {compressed_path}")
            print(f"原始尺寸: {original_dimensions[0]}x{original_dimensions[1]}px")
            print(f"压缩后尺寸: {compressed_dimensions[0]}x{compressed_dimensions[1]}px")
            print(f"原始大小: {original_size:.2f}KB")
            print(f"压缩后大小: {compressed_size:.2f}KB")
            print(f"压缩率: {(1 - compressed_size/original_size)*100:.2f}%")

            return compressed_path
    except Exception as e:
        print(f"压缩图像失败: {image_path}, 错误: {e}")
        return None

def process_image_urls_in_md(md_file, output_dir):
    """处理 Markdown 文件中的所有图像链接"""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    image_urls = re.findall(r'!\[.*?\]\((http[^\)]+)\)', content)
    compressed_images = []

    # 显示图片处理进度
    with tqdm(image_urls, desc="处理图片", position=2, leave=False) as img_pbar:
        for url in img_pbar:
            img_pbar.set_description(f"下载: {url[:30]}...")
            image_path = download_image(url, output_dir)
            if image_path:
                compressed_image_path = compress_image(image_path, output_dir)
                if compressed_image_path:
                    compressed_images.append(compressed_image_path)
                    content = content.replace(url, os.path.basename(compressed_image_path))

    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return compressed_images

def generate_ebook(root_dir, output_format="epub", output_name=None):
    """生成电子书的主要函数"""
    temp_dir = os.path.join(root_dir, "_booktemp")
    os.makedirs(temp_dir, exist_ok=True)

    # 为图片创建专门的目录
    images_dir = os.path.join(temp_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    metadata = generate_metadata(root_dir)
    main_md = os.path.join(temp_dir, "main.md")

    with open(main_md, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"title: {metadata['title']}\n")
        f.write(f"author: {metadata['author']}\n")
        f.write(f"date: {metadata['date']}\n")
        f.write("lang: zh-CN\n")
        f.write("---\n\n")

        process_directory(root_dir, f, root_dir, 0)

    # 处理Markdown中的在线图片
    process_image_urls_in_md(main_md, images_dir)

    # 最后处理一遍主文件的换行
    with open(main_md, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(main_md, 'w', encoding='utf-8') as f:
        f.write(content)

    output_file = os.path.join(root_dir, f"{output_name or metadata['title'] or 'book'}.{output_format}")
    generate_with_pandoc(main_md, output_file, output_format)
    return True

def generate_metadata(root_dir):
    """生成电子书元数据"""
    return {
        "title": os.path.basename(os.path.abspath(root_dir)),
        "author": os.path.basename(os.path.abspath(root_dir)),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

def process_directory(current_dir, file_handler, root_dir, level=0):
    """递归处理目录结构，同时跳过临时目录和隐藏文件，并按名称顺序排序"""
    for item in natsorted(os.listdir(current_dir), key=lambda x: x.lower()):
        if item.startswith(('_', '.')):
            continue

        path = os.path.join(current_dir, item)
        if os.path.isdir(path):
            header = "#" * (level + 1)
            file_handler.write(f"{header} {item}\n\n")
            process_directory(path, file_handler, root_dir, level + 1)
        else:
            if item.lower().endswith((".html", ".md")):
                # 为文件内容创建一个新的标题层级
                file_header = "#" * (level + 1)
                file_handler.write(f"{file_header} {os.path.splitext(item)[0]}\n\n")
                include_content(path, file_handler, level + 1)
                file_handler.write("\n\n")

def remove_yaml_front_matter(content):
    """检测内容是否以 YAML front matter 开头"""
    content = content.lstrip()
    if content.startswith("---"):
        lines = content.splitlines()
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i+1:]).lstrip()
    return content

def include_content(file_path, file_handler, base_level):
    """将文件内容插入主文档，处理 Markdown 文件时剔除 YAML front matter 并调整标题层级"""
    try:
        content = ""
        if file_path.lower().endswith(".html"):
            content = subprocess.check_output(
                ["pandoc", "-f", "html", "-t", "markdown", file_path],
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
        elif file_path.lower().endswith(".md"):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = remove_yaml_front_matter(content)

        # 调整内容中的标题层级
        lines = content.split('\n')
        adjusted_lines = []
        for line in lines:
            # 检查行是否是标题
            if line.strip().startswith('#'):
                # 计算当前标题的层级
                current_level = len(line) - len(line.lstrip('#'))
                # 调整标题层级
                new_level = base_level + current_level
                # 确保不超过6级标题
                new_level = min(new_level, 6)
                # 替换原有的#号
                adjusted_line = '#' * new_level + line[current_level:]
                adjusted_lines.append(adjusted_line)
            else:
                adjusted_lines.append(line)

        file_handler.write('\n'.join(adjusted_lines))

    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        file_handler.write(f"*[Error processing file: {file_path}]*\n")

def generate_with_pandoc(input_md, output_file, output_format):
    """使用 Pandoc 生成最终电子书"""
    cmd = [
        "pandoc",
        input_md,
        "-o",
        output_file,
        "--toc",
        "--toc-depth=3",
        "--standalone"
    ]

    if output_format == "epub":
        cmd.extend([
            "-f", "markdown+smart"
        ])
        cover_image = os.path.join(os.path.dirname(input_md), "assets", "cover.jpg")
        if os.path.exists(cover_image):
            cmd.extend(["--epub-cover-image=" + cover_image])

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"成功生成电子书: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"生成电子书失败: {e}")
        print(f"错误输出: {e.stderr}")

if __name__ == "__main__":
    base_dir = './test'
    dirs_to_process = [
        item for item in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, item))
        and not item.startswith(("_", "."))
    ]

    successful = 0
    failed = 0

    print("开始处理电子书...")
    with tqdm(dirs_to_process, desc="总进度", position=0) as pbar:
        for item in pbar:
            pbar.set_description(f"处理目录: {item}")
            full_path = os.path.join(base_dir, item)

            # 子进度条显示当前处理的具体步骤
            steps = ["检查目录", "处理图片", "生成元数据", "转换格式"]
            with tqdm(total=len(steps), desc="当前任务", position=1, leave=False) as sub_pbar:
                try:
                    # 更新子进度条并显示当前步骤
                    sub_pbar.set_description("检查目录结构")
                    sub_pbar.update(1)

                    sub_pbar.set_description("处理和压缩图片")
                    # 处理图片相关代码
                    sub_pbar.update(1)

                    sub_pbar.set_description("生成元数据")
                    # 生成元数据相关代码
                    sub_pbar.update(1)

                    sub_pbar.set_description("转换为电子书格式")
                    if generate_ebook(full_path, "epub", output_name=item):
                        successful += 1
                        sub_pbar.update(1)
                    else:
                        failed += 1
                        tqdm.write(f"警告: {item} 转换可能不完整")

                except Exception as e:
                    failed += 1
                    tqdm.write(f"错误 - {item}: {str(e)}")
                    continue

            # 在每个目录处理完成后显示结果
            tqdm.write(f"完成: {item}")

    print(f"\n完成! 成功: {successful}, 失败: {failed}")
