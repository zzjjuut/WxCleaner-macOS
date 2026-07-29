import os
import hashlib
from pathlib import Path
from collections import defaultdict

def calculate_hash(file_path, block_size=65536, partial=False):
    """
    计算文件哈希值。
    partial=True 时只计算前 1024 字节，用于快速筛选。
    """
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            if partial:
                buf = f.read(1024)
                hasher.update(buf)
            else:
                buf = f.read(block_size)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(block_size)
        return hasher.hexdigest()
    except (OSError, IOError):
        return None

def find_duplicates(scan_path, progress_callback=None):
    """
    扫描目录并找出重复文件。
    返回格式: {hash: [path1, path2, ...]}
    progress_callback: function(current, total, status_text)
    """
    # 0. 预扫描：统计文件总数
    if progress_callback:
        progress_callback(0, 0, "正在统计文件总数...")
    
    total_files = 0
    for root, _, files in os.walk(scan_path):
        total_files += len(files)
    
    if progress_callback:
        progress_callback(0, total_files, f"共找到 {total_files} 个文件，开始分析...")

    # 1. 按大小对文件进行初步分组
    size_groups = defaultdict(list)
    processed_count = 0
    
    for root, _, files in os.walk(scan_path):
        for name in files:
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
                if size > 0: # 忽略空文件
                    size_groups[size].append(path)
            except OSError:
                continue
            
            processed_count += 1
            if progress_callback and processed_count % 100 == 0: # 每100个文件更新一次，避免UI刷新过频
                progress_callback(processed_count, total_files, "正在按大小筛选...")

    # 2. 对大小相同的文件，计算头部哈希 (Partial Hash)
    # 此时进度条可以跳过一部分，或者重新映射。
    # 为了简化，我们假设"筛选"占进度的50%，"哈希"占50%。
    # 或者，我们只在重头戏（计算哈希）时更新剩余的进度。
    
    # 这里我们采用一个简单策略：
    # 第一阶段(Walk)完成后，进度设为 50%
    # 第二阶段(Hash)处理剩下的 50%
    
    potential_duplicates_count = sum(len(paths) for paths in size_groups.values() if len(paths) > 1)
    current_hash_processed = 0
    
    partial_hash_groups = defaultdict(list)
    for size, paths in size_groups.items():
        if len(paths) < 2:
            continue
        for path in paths:
            h = calculate_hash(path, partial=True)
            if h:
                partial_hash_groups[(size, h)].append(path)
            
            current_hash_processed += 1
            if progress_callback and current_hash_processed % 10 == 0:
                 # 映射到 50% - 75% 区间
                 p = 0.5 * total_files + 0.25 * total_files * (current_hash_processed / potential_duplicates_count)
                 progress_callback(p, total_files, "正在计算头部哈希...")

    # 3. 对头部哈希相同的文件，计算全量哈希 (Full Hash)
    potential_full_hash_count = sum(len(paths) for paths in partial_hash_groups.values() if len(paths) > 1)
    current_full_hash_processed = 0
    
    duplicates = defaultdict(list)
    for (size, phash), paths in partial_hash_groups.items():
        if len(paths) < 2:
            continue
        for path in paths:
            h = calculate_hash(path, partial=False)
            if h:
                duplicates[h].append(path)
            
            current_full_hash_processed += 1
            if progress_callback:
                # 映射到 75% - 100% 区间
                p = 0.75 * total_files + 0.25 * total_files * (current_full_hash_processed / potential_full_hash_count)
                progress_callback(p, total_files, "正在进行全量校验...")

    # 4. 过滤掉没有重复的文件
    return {h: paths for h, paths in duplicates.items() if len(paths) > 1}

if __name__ == "__main__":
    # 简单测试逻辑
    test_dir = "./test_folder"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
        # 创建一些重复文件用于测试
        with open(os.path.join(test_dir, "file1.txt"), "w") as f: f.write("hello world")
        with open(os.path.join(test_dir, "file2.txt"), "w") as f: f.write("hello world")
        with open(os.path.join(test_dir, "file3.txt"), "w") as f: f.write("different content")
    
    results = find_duplicates(test_dir)
    print(f"找到 {len(results)} 组重复文件:")
    for h, paths in results.items():
        print(f"Hash {h[:8]}: {paths}")
