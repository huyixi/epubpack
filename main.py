#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import subprocess
import requests
from datetime import datetime
from PIL import Image
import re
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
    """Download an image from URL, process it, and save to the output directory."""
    try:
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Download image
        response = requests.get(url)
        response.raise_for_status()

        # Generate file path with appropriate extension
        image_path = _generate_image_path(url, response, output_dir)

        # Save the original image
        with open(image_path, 'wb') as f:
            f.write(response.content)

        # Process the image
        if not _process_image(image_path):
            return None

        return image_path

    except Exception as e:
        print(f"图像下载失败:{url}, error:{e}")
        return None

def _get_extension(url, content_type):
    """Determine file extension based on content type and URL."""
    original_ext = os.path.splitext(url)[1].lower()

    # Determine extension based on content type
    if 'jpeg' in content_type or 'jpg' in content_type or original_ext in ['.jpg', '.jpeg']:
        return '.jpg'
    elif 'png' in content_type or original_ext == '.png':
        return '.png'
    elif 'gif' in content_type or original_ext == '.gif':
        return '.gif'
    elif 'webp' in content_type or original_ext == '.webp':
        return '.jpg'  # Convert webp to jpg

    # Fallback to URL extension
    if original_ext in ['.jpg', '.jpeg', '.png', '.gif']:
        return original_ext

    # Default extension
    return '.jpg'

def _generate_image_path(url, response, output_dir):
    """Generate a unique filename for the image."""
    content_type = response.headers.get('content-type', '').lower()
    final_ext = _get_extension(url, content_type)

    # Create unique filename
    hash_value = hashlib.md5(url.encode()).hexdigest()[:8]
    image_name = f"image_{datetime.now().strftime('%H%M%S')}_{hash_value}{final_ext}"

    return os.path.join(output_dir, image_name)

def _process_image(image_path):
    """Process the image with PIL."""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB mode if needed
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGB')

            # Determine save format based on file extension
            file_ext = os.path.splitext(image_path)[1].lower()
            save_format = 'JPEG' if file_ext == '.jpg' else 'PNG'

            # Save processed image
            img.save(image_path, save_format, quality=70)
        return True

    except Exception as e:
        print(f"图片处理失败: {e}")
        if os.path.exists(image_path):
            os.remove(image_path)
        return False

def compress_image(image_path, output_dir=None, max_size=(500, 500)):
    try:
        with Image.open(image_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            if output_dir:
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                compressed_path = os.path.join(output_dir, os.path.basename(image_path))
            else:
                compressed_path = image_path

            img.save(compressed_path, quality=80)

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

        for future in concurrent.futures.as_completed(futures):
            original_url, new_filename = future.result()
            if new_filename:
                replacements.append((original_url, new_filename))
                compressed_images.append(os.path.join(output_dir, new_filename))

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

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def process_directory(current_dir, file_handler, root_dir, level=0):
    """递归处理目录结构，同时跳过临时目录和隐藏文件，并按名称顺序排序"""
    for item in sorted(os.listdir(current_dir), key=natural_sort_key):
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
                current_level = len(line) - len(line.lstrip('#'))
                new_level = base_level + current_level
                new_level = min(new_level, 6)
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
            print(f"已经生成电子书: {output_file}")
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
        f.write(
            "---\n"
            f"title: {metadata['title']}\n"
            f"author: {metadata['author']}\n"
            f"date: {metadata['date']}\n"
            "lang: zh-CN\n"
            "---\n"
        )

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

    for item in dirs_to_process:
        full_path = os.path.join(base_dir, item)

        try:
            if generate_ebook(full_path, "epub", output_name=item,output_dir=output_dir):
                successful += 1
            else:
                failed += 1

        except Exception as exc:
            failed += 1
            failed_dirs.append(item)
            print(f"处理 {item} 时出现错误: {exc}")
            continue

    print(f"\n完成! 成功: {successful}, 失败: {failed}")
    # 打印出生成失败的目录
    if failed_dirs:
        print(f"生成失败的目录: {failed_dirs}")

if __name__ == "__main__":
    main()
