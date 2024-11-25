'''
这个脚本是针对之前 gitMergeScenario 获取的结果，读取其中的 json，重演整个文件的 merge 并重新收集冲突块的脚本
'''
# 类型提示放在这里，方便查看
class ConflictChunk:
    def __init__(self, m_start, m_end, a_content, b_content, 
                 o_content, r_content, label: str | None, chunk_idx):
        self.m_start = m_start
        self.m_end = m_end
        self.a_content: 'str' = a_content
        self.b_content: 'str' = b_content
        self.o_content: 'str' = o_content
        self.r_content: 'str' = r_content
        self.label = label
        self.chunk_idx = chunk_idx

    def to_dict(self):
        return {
            "m_start": self.m_start,
            "m_end": self.m_end,
            "a_content": self.a_content,
            "b_content": self.b_content,
            "o_content": self.o_content,
            "r_content": self.r_content,
            "label": self.label,
        }
    
    def getJSONstr(self):
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)


class ConflictFile:
    def __init__(self, path, repo_url, file_a_content, file_b_content, file_o_content, file_r_content, file_m_content, commit_hash):
        self.path = path
        self.repo_url = repo_url
        self.file_a_content = file_a_content
        self.file_b_content = file_b_content
        self.file_o_content = file_o_content
        self.file_r_content = file_r_content
        self.file_m_content = file_m_content
        self.commit_hash = commit_hash
        self.conflict_chunks = []

    def add_conflict_chunk(self, conflict_chunk_obj):
        self.conflict_chunks.append(conflict_chunk_obj)

    def to_dict(self):
        return {
            "path": self.path,
            "repo_url": self.repo_url,
            "file_a_content": self.file_a_content,
            "file_b_content": self.file_b_content,
            "file_o_content": self.file_o_content,
            "file_r_content": self.file_r_content,
            "file_m_content": self.file_m_content,
            "conflict_chunks": [chunk.to_dict() for chunk in self.conflict_chunks],
        }
    
    def getJSONstr(self):
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)

class ConflictFileCollector:
    def __init__(self, dataset_path):
        self.dataset_path = dataset_path
    
    @staticmethod
    def sample(output_dir, n, random_seed=0, label=None):
        cnt = 0
        # 从所有冲突文件中随机抽取 n 个 label 类型的 Conflict chunk
        # 读取 output_dir 中的所有 JSON 文件
        jsons = list(ConflictFileCollector.getAllJsonsUnder(output_dir))
        print(f"Found {len(jsons)} JSON files in {output_dir}")
        # 读取所有 JSON 文件中的 Conflict chunk
        for json_file in jsons:
            with open(json_file) as f:
                data = json.load(f)
            for conflict_file in data:
                for chunk in conflict_file['conflict_chunks']:
                    if label == None or chunk['label'] == label:
                        if cnt >= n:
                            return
                        cnt += 1
                        yield chunk


    def collect(self):
        '''
        返回一个迭代器，每次迭代返回一个ConflictFile对象
        '''
        raise NotImplementedError
        
    def collect_in_batches(self, batch_size=10000):
        batch = []
        for conflict_file in self.collect():
            batch.append(conflict_file)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def collect_and_save(self, output_dir, batch_size=10000):
        output_dir = Path(output_dir)  # 确保 output_dir 是 Path 对象
        output_dir.mkdir(parents=True, exist_ok=True)  # 自动创建目录及其父目录
        for i, batch in enumerate(self.collect_in_batches(batch_size)):
            with open(output_dir / f"{i}.json", 'w') as f:
                print(f"Saving batch {i} to {output_dir / f'{i}.json'}")
                json.dump([json.loads(x.getJSONstr()) for x in batch], f)
    
    @staticmethod
    def preprocessContent(content: str):
        return '' if content.strip() == '' else re.sub(r'\s+', ' ', content.strip() + '\n')
    
    @staticmethod
    def getLabel(a, b, o, r):
        r_processed = ConflictFileCollector.preprocessContent(r)
        a_processed = ConflictFileCollector.preprocessContent(a)
        b_processed = ConflictFileCollector.preprocessContent(b)
        o_processed = ConflictFileCollector.preprocessContent(o)
        if a_processed == b_processed:
            return "same modification, formatting maybe different"
        if r_processed == a_processed:
            return "A"
        if r_processed == b_processed:
            return "B"
        if r_processed == o_processed:
            return "O"
        if r_processed == a_processed + b_processed:
            return "AB"
        if r_processed == b_processed + a_processed:
            return "BA"

        r_lines = set(r.split('\n'))
        a_lines = set(a.split('\n'))
        b_lines = set(b.split('\n'))
        o_lines = set(o.split('\n'))
        for rl in r_lines:
            if (rl not in a_lines) and (rl not in b_lines) and (rl not in o_lines) and not rl.isspace():
                return 'newline'
        return 'mixline'

    @staticmethod
    def getAllJsonsUnder(dirPath: str):
        for root, _, files in os.walk(dirPath):
            for file in files:
                if(file.endswith(".json")):
                    yield os.path.join(root, file)
    
    @staticmethod
    def list2str(l):
        if l == [] or l == ['']:
            return ''
        return '\n'.join(l) + '\n'





# 1. 读取 json 文件，每一个都是 conflictFile[]
# 2. 读取每一个 conflictFile，获取其中的 a_file_content, b_file_content, o_file_content, r_file_content
# 3. 写入文件，使用 Pythongit merge-file
# 4. 读取冲突块，提取对应的 resolution
# 5. 覆盖写入文件

import os
import re
import json
from pathlib import Path

def merge_file(a_content, b_content, o_content):
    """
    开一个新的进程，执行 merge_file，返回合并后的内容
    params will be string
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdirname:
        # 写入文件
        with open(os.path.join(tmpdirname, "a.txt"), "w") as f:
            f.write(a_content)
        with open(os.path.join(tmpdirname, "b.txt"), "w") as f:
            f.write(b_content)
        with open(os.path.join(tmpdirname, "o.txt"), "w") as f:
            f.write(o_content)
        # 执行 merge-file
        os.system(f"git merge-file --diff3 {tmpdirname}/a.txt {tmpdirname}/o.txt {tmpdirname}/b.txt")
        # 读取合并后的文件
        with open(os.path.join(tmpdirname, "a.txt"), "r") as f:
            return f.readlines()
        

def process_conflict_file(conflict_file):
    """
    处理单个 ConflictFile，提取冲突块，返回更新后的数据
    """
    a_content: str = conflict_file["file_a_content"]
    b_content: str = conflict_file["file_b_content"]
    o_content: str = conflict_file["file_o_content"]
    r_content: str = conflict_file["file_r_content"]

    # 执行 merge
    merged_lines_withEnding = merge_file(a_content, b_content, o_content)   # 每行末尾都有换行符
    conflict_file['file_m_content'] = ''.join(merged_lines_withEnding)

    # 提取冲突块
    conflict_chunks = []
    in_conflict = False
    chunk = None
    current_content = ""  # 用于临时存储当前块内容
    chunk_idx = 0
    for i in range(len(merged_lines_withEnding)):
        line = merged_lines_withEnding[i]
        if line.startswith("<<<<<<<"):
            if in_conflict:
                # 如果当前已经在冲突块中，说明文件有问题，直接返回
                conflict_file["conflict_chunks"] = []
                return conflict_file
            in_conflict = True
            chunk = {
                "a_content": "",
                "b_content": "",
                "o_content": "",
                'm_start': i,
            }
            current_content = ""  # 初始化临时变量
        elif line.startswith("|||||||"):
            if chunk is None:
                # 先看到 |||，说明文件有问题，直接返回
                conflict_file["conflict_chunks"] = []
                return conflict_file
            chunk["a_content"] = current_content  # 保存当前块为 a_content
            current_content = ""
        elif line.startswith("======="):
            if chunk is None:
                # 先看到 ===，说明文件有问题，直接返回
                conflict_file["conflict_chunks"] = []
                return conflict_file
            chunk["o_content"] = current_content
            current_content = ""  # 清空临时变量准备存储 b_content
        elif line.startswith(">>>>>>>"):
            if chunk is None:
                # 先看到 >>>，说明文件有问题，直接返回
                conflict_file["conflict_chunks"] = []
                return conflict_file
            chunk["b_content"] = current_content  # 保存 b_content
            chunk['chunk_idx'] = chunk_idx
            chunk_idx += 1
            chunk['m_end'] = i + 1
            in_conflict = False
            conflict_chunks.append(chunk)
            chunk = None
        elif in_conflict:
            current_content += line  # 累加当前冲突块内容

    ###### 以下是提取解决方案的代码 ######

    # 定义 minimal_unique_prefix 函数（已在前面提供）
    def minimal_unique_prefix(x, y):
        """
        Parameters
        ----------
        x : List[str]
            用于查找前缀的列表。
        y : List[str]
            truth。
        找到 x 在 y 中唯一出现的最小前缀。
        返回前缀在 y 中的起始索引，如果未找到则返回 -1。
        """
        if not x:
            return -1
        # 初始化候选索引集合，x[0] 在 y 中的位置
        candidates = {i for i, val in enumerate(y) if val == x[0]}
        offset = 0
        while len(candidates) > 1:
            offset += 1
            if offset == len(x):  # 如果偏移量达到 x 的长度，说明找不到唯一前缀
                return -1
            to_remove = set()
            for idx in candidates:
                # 如果越界或当前偏移量的值不匹配，则移出候选
                if idx + offset >= len(y) or y[idx + offset] != x[offset]:
                    to_remove.add(idx)
            candidates -= to_remove
        return candidates.pop() if candidates else -1
    
    # 准备 resolved_content，即解决后的文件内容
    resolved_content_lines = list(map(lambda x: x + '\n', conflict_file["file_r_content"].splitlines()))        # 每行末尾都有换行符，和上面统一

    len_after = len(resolved_content_lines) + 2  # 添加 2 个填充标记的长度

    # 在 resolved_content 前后添加填充标记
    truth_padded = ['<Begin Marker Here>'] + resolved_content_lines + ['<End Marker Here>']

    # 为前缀匹配创建反转的 truth_padded
    reversed_truth_padded = truth_padded[::-1]

    for i in range(len(conflict_chunks) - 1, -1, -1):  # 反向遍历，以便删除元素
        cc = conflict_chunks[i]
        if 'm_start' not in cc:
            # 说明这个原本的文本中含有冲突块，这个文件不要
            conflict_file["conflict_chunks"] = []
            return conflict_file
        # 创建用于后缀匹配的 subArr_eos
        subArr_eos = merged_lines_withEnding[cc['m_end']:] + ['<End Marker Here>']
        sffxIdx = minimal_unique_prefix(subArr_eos, truth_padded)  # 查找后缀起始位置
        if sffxIdx == -1:
            # 如果没有找到唯一后缀，删去当前冲突块
            del conflict_chunks[i]
            continue

        # 创建用于前缀匹配的 subArr_bos
        subArr_bos = merged_lines_withEnding[:cc['m_start']][::-1] + ['<Begin Marker Here>']
        prfxIdx = minimal_unique_prefix(subArr_bos, reversed_truth_padded)  # 查找前缀起始位置
        if prfxIdx == -1:
            del conflict_chunks[i]
            continue

        # 如果条件满足，则提取解决方案
        if len_after - prfxIdx <= sffxIdx:
            start = len_after - prfxIdx
            end = sffxIdx
            cc['r_content'] = ''.join(truth_padded[start:end])
            cc['label'] = ConflictFileCollector.getLabel(cc['a_content'], cc['b_content'], cc['o_content'], cc['r_content'])
        else:
            del conflict_chunks[i]

    # 更新 conflict_file 的冲突块
    conflict_file["conflict_chunks"] = conflict_chunks
    return conflict_file



from tqdm import tqdm
from multiprocessing import Pool
import signal

def initializer():
    """Ignore CTRL+C in the worker process."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # 子进程忽略中断信号
    
def process_json_file(json_file_path):
    """
    处理单个 JSON 文件，将 conflictFiles 并行处理，并添加 tqdm 进度条。
    """
    with open(json_file_path, "r") as f:
        conflict_files = json.load(f)

    # 多进程处理 conflictFiles
    cpus = os.cpu_count() - 8
    # cpus = 1
    print(f"Using {cpus} CPUs")


    # 创建一个共享的进度条
    with tqdm(total=len(conflict_files), desc="Processing files", unit="file", dynamic_ncols=True) as pbar:
        def update(*args):
            """更新进度条"""
            pbar.update()

        with Pool(cpus, initializer=initializer) as pool:
            try:
                # 使用 `imap_unordered` 逐步处理并更新进度
                results = []
                for result in pool.imap_unordered(process_conflict_file, conflict_files):
                    results.append(result)
                    update()
            except KeyboardInterrupt:
                print('manually stop, exiting all processes')
                pool.terminate()

    return results

def process_directory(input_dir, output_dir):
    """
    处理整个目录的 JSON 文件，重演合并并提取冲突块
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_file_paths = list(input_dir.glob("*.json"))
    with tqdm(total=len(json_file_paths), desc="Processing JSON files", dynamic_ncols=True, unit="file") as outer_pbar:
        for json_file in json_file_paths:
            print(f"Processing {json_file}")
            updated_conflict_files = process_json_file(json_file)

            # 保存更新后的 JSON 文件
            output_path = output_dir / json_file.name
            with open(output_path, "w") as f:
                json.dump(updated_conflict_files, f, indent=4)
            outer_pbar.update()

if __name__ == "__main__":
    input_dir = "/root/projects/dataset_collect_analysis/data_collect_analysis/output/100+stars_4GB-_multidev_org_lang"  # 替换为实际输入目录
    output_dir = "/root/projects/dataset_collect_analysis/data_collect_analysis/output/100+stars_4GB-_multidev_org_lang"  # 替换为实际输出目录

    process_directory(input_dir, output_dir)

    # test case，测试 merge_file 函数
    # baseContent = "a\nb\nc\nd\ne\nf\ng\nh\ni\n"
    # oursContent = "a\nb\n1\n2\n3\n6\nc\nd\ne\naaa\nf\nj\nk\nl\nm\n9\nxxx\ng\nh\nhhh\ni\n"
    # theirsContent = "a\nb\n4\n5\n6\nc\nd\ne\nf\n7\n8\n9\nxxx\ng\nh\ni\n"
    # merge_result = merge_file(oursContent, theirsContent, baseContent)
    # print(list(merge_result))