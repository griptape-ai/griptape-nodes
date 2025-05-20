import psutil

def get_memory_usage():
    process = psutil.Process()
    memory_info = process.memory_info()
    return memory_info.rss

def get_total_memory_usage():
    parent = psutil.Process()
    memory = parent.memory_info().rss
    for child in parent.children(recursive=True):
        try:
            memory += child.memory_info().rss
        except psutil.NoSuchProcess:
            continue
    return memory

def convert_bytes_to_readable(bytes):
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    index = 0
    while bytes >= 1024 and index < len(units) - 1:
        bytes /= 1024
        index += 1
    return f"{bytes:.2f} {units[index]}"

def print_current_memory_usage():
    print(f"\nCurrent memory usage: {convert_bytes_to_readable(get_total_memory_usage())}\n")
