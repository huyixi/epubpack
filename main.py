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
import concurrent.futures
import json
import logging
import hashlib

def load_config(config_path="./config/config.json"):
    config={}

    try:
        with open(config_path,'r',encoding='utf-8') as f:
            config = json.load(f) or {}
            logging.info(f"Load config file success: {config_path}")
    except FileNotFoundError:
        logging.error(f"配置文件 {config_path} 未找到")
    except json.JSONDecodeError as e:
        logging.error(f"配置文件解析失败: {str(e)}")
    except Exception as e:
        logging.error(f"加载配置文件失败: {str(e)}")

    return config

def preprocess_markdown(content):
    # 部分 <img> 标签会导致 EPUB 报错
    # 给 <img> 标签添加转义字符
    # 避免匹配 `<img>` 标签
    def escape_img_tags(text):
        return re.sub(
            r'(?<!`)(<img)(\s*>)(?!`)',
            lambda m: f"&lt;{m.group(1)[1:]}{m.group(2)}",  # 此处仅为示例转换
            text,
            flags=re.IGNORECASE
        )

    # 在图片内容后面添加 \ 符号以避免 pandoc 生成 EPUB 时在下方附带图片标题
    def add_backslash_to_md_images(text):
        pattern = r'(!\[[^\]]*\]\([^)]+\))'
        replacement = r'\1\\'
        return re.sub(pattern, replacement, text)

    _LINK_PATTERN = re.compile(r'(?<!!)\[(.*?)\]\((.*?)\)')
    def convert_links_to_readable(text, url_limit=60):
        def replacement(match):
            link_text, url = match.groups()
            # Shorten URL if needed
            if len(url) > url_limit:
                shortened_url = url[:30] + '...' + url[-7:]
            else:
                shortened_url = url
            return f'`[{link_text}]({shortened_url})`'

        return _LINK_PATTERN.sub(replacement, text)

    content = add_backslash_to_md_images(content)
    content = convert_links_to_readable(content)
    content = escape_img_tags(content)

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
            original_ext = os.path.splitext(url)[1].lower()
            if original_ext in ['.jpg', '.jpeg']:
                final_ext = '.jpg'
            elif original_ext == '.png':
                final_ext = '.png'
            elif original_ext == '.gif':
                final_ext = '.gif'
            else:
                final_ext = '.jpg'  # 默认用 jpg

        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 生成唯一的文件名
        hash_value = hashlib.md5(url.encode()).hexdigest()[:8]
        image_name = f"image_{datetime.now().strftime('%H%M%S')}_{hash_value}{final_ext}"
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
                img.save(image_path, save_format, quality=70)

        except Exception as e:
            print(f"图片处理失败: {e}")
            if os.path.exists(image_path):
                os.remove(image_path)
            return None

        return image_path

    except Exception as e:
        print(f"图像下载失败:{url}, error:{e}")
        if response:
            print(f"Content-Type: {response.headers.get('content-type')}")
        return None

def compress_image(image_path, output_dir=None, max_size=(600, 600)):
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
            img.save(compressed_path, quality=90)

            # 获取压缩后文件大小
            compressed_size = os.path.getsize(compressed_path) / 1024  # 转换为 KB

            # print(f"压缩图像: {compressed_path}")
            # print(f"原始尺寸: {original_dimensions[0]}x{original_dimensions[1]}px")
            # print(f"压缩后尺寸: {compressed_dimensions[0]}x{compressed_dimensions[1]}px")
            # print(f"原始大小: {original_size:.2f}KB")
            # print(f"压缩后大小: {compressed_size:.2f}KB")
            # print(f"压缩率: {(1 - compressed_size/original_size)*100:.2f}%")

            return compressed_path
    except Exception as e:
        print(f"压缩图像失败: {image_path}, 错误: {e}")
        return None

def process_image_urls_in_md(md_file, output_dir):
    """处理 Markdown 文件中的所有图像链接"""
    """图像链接分为 Markdown 和 HTML 两种格式"""
    with open(md_file, 'r', encoding='utf-8') as f:
        original_content = f.read()

    # 1) 提取出三重反引号的代码块
    code_block_pattern = re.compile(r'```.*?```', re.DOTALL)
    code_blocks = code_block_pattern.findall(original_content)

    # 创建用来存放代码块的占位符
    content = original_content
    for i, block in enumerate(code_blocks):
        placeholder = f"__CODE_BLOCK_{i}__"
        # 使用 replace(block, placeholder, 1) 保证只替换一次，否则如果某个代码块内容重复，会出问题
        content = content.replace(block, placeholder, 1)

    # 匹配 Markdown 语法的图像链接
    markdown_image_urls = re.findall(r'!\[.*?\]\((http[^\)]+)\)', content)
    # 匹配 HTML 语法的图像链接
    html_image_urls = re.findall(r'<img[^>]+src="([^"]+)"', content)
    image_urls = []
    for url in markdown_image_urls + html_image_urls:
            if url.startswith("http"):
                image_urls.append(url)
    compressed_images = []
    replacements = []

    def process_single_url(url):
        try:
            image_path = download_image(url,output_dir)
            if image_path:
                compressed_image_path = compress_image(image_path,output_dir)
                if compressed_image_path:
                    return (url, os.path.basename(compressed_image_path))
        except Exception as e:
            print(f"Error processing {url[:30]}...: {str(e)}")
        return (None, None)

    # 创建线程池执行并行下载
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_single_url, url) for url in image_urls]

        # 使用tqdm显示并行处理进度
        with tqdm(total=len(image_urls), desc="并行处理图片") as pbar:
            for future in concurrent.futures.as_completed(futures):
                original_url, new_filename = future.result()
                if new_filename:
                    replacements.append((original_url, new_filename))
                    compressed_images.append(os.path.join(output_dir, new_filename))
                pbar.update(1)

    for original_url, new_filename in replacements:
        content = content.replace(original_url, f"images/{new_filename}")

    # 还原代码块
    for i, block in enumerate(code_blocks):
        placeholder = f"__CODE_BLOCK_{i}__"
        content = content.replace(placeholder, block,1)

    with open(md_file, 'w', encoding='utf-8') as f:
            f.write(content)

    return compressed_images

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
    temp_dir = os.path.dirname(input_md)
    cmd = [
        "pandoc",
        input_md,
        "-o",
        output_file,
        "--toc",
        "--standalone",
        "--no-highlight",
        "--resource-path=" + os.path.dirname(input_md),
        "--resource-path=" + os.path.join(temp_dir,"images"),
    ]

    # lua_filter_path = os.path.join(os.path.dirname(__file__), "removeAlt.lua")
    # cmd.append(f"--lua-filter={lua_filter_path}")

    if output_format == "epub":
        cmd.extend([
            "-f", "markdown+smart"
        ])
        cover_image = os.path.join(os.path.dirname(input_md), "assets", "cover.jpg")
        if os.path.exists(cover_image):
            cmd.extend(["--epub-cover-image=" + cover_image])

    try:
        result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        if result.returncode == 0:
            print(f"成功生成电子书: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"生成电子书失败: {e}")
        print(f"错误输出: {e.stderr}")

def generate_ebook(root_dir, output_format="epub", output_name=None, output_dir=None):
    temp_dir = os.path.join(root_dir, "_booktemp")
    os.makedirs(temp_dir, exist_ok=True)

    # 为图片创建目录
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
    with open(main_md, 'r', encoding='utf-8') as f:
            content = f.read()
    content = preprocess_markdown(content)
    with open(main_md, 'w', encoding='utf-8') as f:
            f.write(content)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{output_name or metadata['title'] or 'book'}.{output_format}")
    else:
        output_file = os.path.join(root_dir, f"{output_name or metadata['title'] or 'book'}.{output_format}")

    generate_with_pandoc(main_md, output_file, output_format)
    return True

def main():
    CONFIG = load_config()
    base_dir = CONFIG["paths"]["base_dir"]
    output_dir =  CONFIG["paths"]["output_dir"]
    dirs_to_process = [
        item for item in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, item))
        and not item.startswith(("_", "."))
    ]

    successful = 0
    failed = 0
    failed_dirs = []

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
                    if generate_ebook(full_path, "epub", output_name=item,output_dir=output_dir):
                        successful += 1
                        sub_pbar.update(1)
                    else:
                        failed += 1
                        tqdm.write(f"警告: {item} 转换可能不完整")

                except Exception as e:
                    failed += 1
                    failed_dirs.append(item)
                    tqdm.write(f"错误 - {item}: {str(e)}")
                    continue

            # 在每个目录处理完成后显示结果
            tqdm.write(f"完成: {item}")

    print(f"\n完成! 成功: {successful}, 失败: {failed}")
    # 打印出生成失败的目录
    if failed_dirs:
        print(f"生成失败的目录: {failed_dirs}")

if __name__ == "__main__":
    main()
