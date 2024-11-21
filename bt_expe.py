# 这个文件是把 script.ipynb 中的代码转化成一个 python 文件，以便多个进程同时运行

from IPython import get_ipython
import os
from pathlib import Path
from collections import defaultdict
import json
from util.conflict_util import Conflict, conflict2file
from tqdm import tqdm
from typing import List, Dict, Any, Tuple
import re
work_dir = Path('/root/projects/dataset_collect_analysis')
print(work_dir)

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



from util.edit_script import compute, SequenceDiff

class EditScriptLabel:
    def __init__(self, sd: SequenceDiff, _from: str, accept: bool):
        self.edit_script = sd
        self._from = _from
        self.accept = accept

def analyze_edit_script(dir2analyze):
    dataset_name = os.path.basename(dir2analyze)
    print(f'在 {dataset_name} 下统计')
    accept_mark_cnt = defaultdict(int)
    es_cnt = defaultdict(int)
    cc_with_es_intersects = 0
    resolvable_cc_cnt = 0
    all_cc_cnt = 0
    too_many_lines_cnt = 0
    label_cnt = defaultdict(int)
    label_resolvable_cnt = defaultdict(int)

    def cc_check(chunk: ConflictChunk) -> None:
        '''
        统计可以用编辑脚本解决的冲突，统计接受和拒绝的数量
        统计编辑脚本的数量，如果太多则跳
        最后比较时我希望转化成 token
        生成编辑脚本时，去除空行影响，缩进。。。去掉？
        '''
        nonlocal accept_mark_cnt
        nonlocal es_cnt
        nonlocal resolvable_cc_cnt
        nonlocal too_many_lines_cnt
        nonlocal label_resolvable_cnt

        def es_gen_str2list(content: str) -> List[str]:
            '''
            生成编辑脚本时的处理
            '''
            return [line.strip() for line in content.split('\n') if line.strip() != '']

        if len(chunk.a_content) > 5000 or len(chunk.b_content) > 5000 or len(chunk.o_content) > 5000 or len(chunk.r_content) > 5000:
            too_many_lines_cnt += 1
            return
            
        a_contents = es_gen_str2list(chunk.a_content)
        b_contents = es_gen_str2list(chunk.b_content)
        o_contents = es_gen_str2list(chunk.o_content)
        r_contents = es_gen_str2list(chunk.r_content)

        def compareInToken(a_ls: List[str], b_ls: List[str]) -> bool:
            '''
            最后比较的预处理，忽略空白符的影响
            '''
            def toUnifiedStr(ls: List[str]) -> str:
                return '' if ls == [] or ls == [''] else re.sub(r'\s+', ' ', '\n'.join(ls).strip() + '\n')
            a_processed = toUnifiedStr(a_ls)
            b_processed = toUnifiedStr(b_ls)
            # print(a_processed)
            # print(b_processed)
            # print(a_processed == b_processed)
            # print('-' * 20)
            return a_processed == b_processed

        def bt(generated, i, last_end, all_edit_scripts: List[EditScriptLabel]) -> bool:
            '''
            回溯法生成所有可能的解决方案，如果和 resolution 相同则加入结果集
            '''
            nonlocal cc_with_es_intersects
            # exit
            if i == len(all_edit_scripts):
                whole_generated = generated + o_contents[last_end:]
                # 过滤 whole_generated 和 resolution 中的空行
                if compareInToken(whole_generated, r_contents):
                    # 可以使用组合 ES 的方式解决的冲突
                    return True
                return False

            # 不接受这个脚本
            all_edit_scripts[i].accept = False
            if bt(generated, i + 1, last_end, all_edit_scripts):
                return True

            # 如果当前脚本的起始位置比 last_end 还小，说明这个脚本和上一个脚本有冲突
            # 不能接受这个脚本，直接跳过
            if all_edit_scripts[i].edit_script.seq1Range.start < last_end:
                cc_with_es_intersects += 1
                return False     # 因为是小于号，所以可以解决伪冲突

            # 接受这个脚本
            start = all_edit_scripts[i].edit_script.seq2Range.start
            end = all_edit_scripts[i].edit_script.seq2Range.end
            if all_edit_scripts[i]._from == 'ours':
                curr_content = a_contents[start:end]
            else:
                curr_content = b_contents[start:end]
            all_edit_scripts[i].accept = True
            if bt(generated
                    + o_contents[last_end:all_edit_scripts[i].edit_script.seq1Range.start]
                    + curr_content,
                    i + 1,
                    all_edit_scripts[i].edit_script.seq1Range.end,
                    all_edit_scripts
                ):
                return True


            # 有下一个脚本，且两者对应 base 的位置相同
            if (
                i + 1 < len(all_edit_scripts) and
                all_edit_scripts[i].edit_script.seq1Range == all_edit_scripts[i + 1].edit_script.seq1Range
            ):
                start = all_edit_scripts[i + 1].edit_script.seq2Range.start
                end = all_edit_scripts[i + 1].edit_script.seq2Range.end
                if all_edit_scripts[i + 1]._from == 'ours':
                    next_content = a_contents[start:end]
                else:
                    next_content = b_contents[start:end]

                # base 长度为 0 的情况，只需要加入另一种 concat（seq1Range 的长度为 0，代表双方在同一位置的插入）
                all_edit_scripts[i + 1].accept = True
                if bt(generated
                        + o_contents[last_end:all_edit_scripts[i].edit_script.seq1Range.start]
                        + next_content
                        + curr_content,
                    i + 2,
                    all_edit_scripts[i].edit_script.seq1Range.end,
                    all_edit_scripts
                ):
                    return True
                # base 长度不为 0 的情况，需要考虑两种 concat
                if len(all_edit_scripts[i].edit_script.seq1Range) > 0: 
                    all_edit_scripts[i + 1].accept = True
                    if bt(generated
                            + o_contents[last_end:all_edit_scripts[i].edit_script.seq1Range.start]
                            + curr_content
                            + next_content,
                            i + 2,
                            all_edit_scripts[i].edit_script.seq1Range.end,
                            all_edit_scripts
                    ):
                        return True



        # 开始收集数据集
        kind = chunk.label
        
        # 如果是 newline 的冲突，直接跳过
        if kind == 'newline':
            return
            
        # 如果行数过大，直接跳过
        if any([len(content) > 1000 for content in [a_contents, b_contents, o_contents, r_contents]]):
            too_many_lines_cnt += 1
            return
        from_ours = compute(o_contents, a_contents)
        from_theirs = compute(o_contents, b_contents)
        # 加入 _from 标记
        from_ours = [EditScriptLabel(sd, 'ours', False) for sd in from_ours]
        from_theirs = [EditScriptLabel(sd, 'theirs', False) for sd in from_theirs]
        all_edit_scripts = from_ours + from_theirs
        es_cnt[len(all_edit_scripts)] += 1
        
        
        # 限制脚本数量，避免计算量过大
        if len(all_edit_scripts) > 20:
            return

        all_edit_scripts.sort(key=lambda editScriptLabel: editScriptLabel.edit_script.seq1Range)

        if bt([], 0, 0, all_edit_scripts):  # 这个冲突能解决
            resolvable_cc_cnt += 1
            label_resolvable_cnt[kind] += 1
            # 统计 accept_mark
            for i, es in enumerate(all_edit_scripts):
                accept_mark_cnt[es.accept] += 1



    # 开始统计数据集结果
    jsonPaths = [path for path in ConflictFileCollector.getAllJsonsUnder(dir2analyze)]
    if len(jsonPaths) == 0:
        raise FileNotFoundError("No metadata json files found in the dataset path")
    for jsonPath in tqdm(jsonPaths, desc="Processing files", position=0, leave=True, dynamic_ncols=True):
        # jsonData
        try:
            with open(jsonPath, 'r') as f:
                cfs = json.load(f)
        except Exception as e:
            print(f"Error reading {jsonPath}: {e} (type: {type(e).__name__})")
            import traceback
            traceback.print_exc()
        for cf in tqdm(cfs, desc=f"Process items", position=1, leave=False, dynamic_ncols=True):
            for cc in cf['conflict_chunks']:
                all_cc_cnt += 1
                label_cnt[cc['label']] += 1
                cc = ConflictChunk(cc['m_start'], cc['m_end'], cc['a_content'], cc['b_content'], cc['o_content'], cc['r_content'], cc['label'], cc['chunk_idx'])
                cc_check(cc)
    
    def print_res_to_file(file=os.sys.stdout):
        print(f'在 {dataset_name} 下统计结果:', file=file) 
        print(f'共有 {all_cc_cnt} 个冲突块，其中 {resolvable_cc_cnt} 个可以用编辑脚本解决，占比 {resolvable_cc_cnt / all_cc_cnt * 100:.2f}%', file=file)
        print(f'有 {cc_with_es_intersects} 个冲突块的编辑脚本有交集', file=file)
        print(f'有 {too_many_lines_cnt} 个冲突块的行数过大，无法处理', file=file)
        print(f'编辑脚本数量分布: {es_cnt}', file=file)
        print(f'接受标记分布: {accept_mark_cnt}', file=file)
        print(f'类型分布: {label_cnt}', file=file)
        print(f'可解决类型分布: {label_resolvable_cnt}', file=file)
        for k, v in label_cnt.items():
            print(f'{k}: {v}, 可解决: {label_resolvable_cnt[k]}，占比: {label_resolvable_cnt[k] / v * 100:.2f}%', file=file)

    # 新建文件夹
    os.makedirs(work_dir / 'data_collect_analysis' / 'bt_log', exist_ok=True)
    print_res_to_file(file=open(work_dir / 'data_collect_analysis' / 'bt_log' / f'{dataset_name}.log', 'w'))



# dir2analyze = work_dir / "data_collect_analysis" / "output" / "100+stars_4GB-_multidev_org_lang"
# dir2analyze = work_dir / "data_collect_analysis" / "output" / "2000repos"
dir2analyze = work_dir / "data_collect_analysis" / "output" / "top50"
# dir2analyze = work_dir / "data_collect_analysis" / "output" / "mergebert_ts"
# dir2analyze = work_dir / "data_collect_analysis" / "output" / "mergebert_all_lang"
analyze_edit_script(dir2analyze)
