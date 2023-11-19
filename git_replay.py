from collections import defaultdict
from tqdm import tqdm
from typing import List, Union
import json
from pathlib import Path
import subprocess
from util import Conflict

# 数据文件路径
file_path = 'output/all_lang_emptyreserved.json'
new_git = '/root/projects/git/git'                  # 编译后的 Git 地址
tmp_file = Path('git_repo/tmp.txt')                 # 用于 replay 冲突的文件


# 打开并读取文件中的数据
with open(file_path, 'r', encoding='utf-8') as json_file:
    data = json.load(json_file)


def run_command(args: List[str], **kwargs):
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)

def writeNcommit(file: Path, content: Union[List[str], str], commit_message = "commit"):
    # if content is a List, join it with '\n'
    if isinstance(content, list):
        # content = '\n'.join(content)
        if content == ['']: content = ""
        else: content = '\n'.join(content) + '\n'
    file.write_text(content)
    
    # 添加所有修改的文件
    run_command([new_git, "add", "-A"], cwd = file.parent)
    # 提交更改
    run_command([new_git, "commit", "-m", commit_message], cwd = file.parent)


def new_branch_and_checkout(repo_dir: Path, branch_name: str):
    run_command([new_git, "checkout", "-b", branch_name], cwd = repo_dir)


def switch_branch(repo_dir: Path, branch_name: str):
    run_command([new_git, "switch", branch_name], cwd = repo_dir)

def merge_branch(repo_dir: Path, branch_name: str):
    run_command([new_git, "merge", branch_name], cwd = repo_dir)


def replay(file: Path, conflict: Conflict):
    # 写入 base
    writeNcommit(file, conflict['base'], 'base')
    # 新建 theirs 分支
    new_branch_and_checkout(file.parent, 'theirs')
    # 写入 theirs
    writeNcommit(file, conflict['theirs'], 'theirs')
    # 切换到 main 分支
    switch_branch(file.parent, 'main')
    # 写入 ours
    writeNcommit(file, conflict['ours'], 'ours')
    # 合并 theirs 分支
    merge_branch(file.parent, 'theirs')


def reset_all(repo_dir, init_hash, delete_branch_name):
    switch_branch(repo_dir, 'main')
    run_command([new_git, "reset", "--hard", init_hash], cwd = repo_dir)
    run_command([new_git, "branch", "-D", delete_branch_name], cwd = repo_dir)

correct, total = 0, 0
wierd = 0
kind_pseudo = defaultdict(int)
kind_counter = defaultdict(int)
kind_correct = defaultdict(int)
for idx, conflict in enumerate(tqdm(data[:])):
    if conflict['base'] == conflict['theirs'] or conflict['base'] == conflict['ours']:
        wierd += 1          # 往往是多一个换行符导致的问题，是 mergebert 收集的数据集的问题
        continue
    kind_counter[conflict['resolution_kind']] += 1
    try:
        replay(tmp_file, conflict)
        # 读取合并后的内容
        with open(tmp_file, 'r', encoding='utf-8') as f:
            result = f.read().split('\n')
            # 在这里过滤合并后的内容和 resolution，去掉空行
        result = list(filter(lambda line: not(line == '' or line.isspace()), result))
        total += 1
        if '<<<<<<< HEAD' not in result:
            kind_pseudo[conflict['resolution_kind']] += 1
            if result == list(filter(lambda line: not(line == '' or line.isspace()), conflict['resolve'])):
                correct += 1
                kind_correct[conflict['resolution_kind']] += 1
        reset_all(tmp_file.parent, '37b4a54d9cdf619c9e6ffb9aaff885c3ef0dc592', 'theirs')
    except subprocess.CalledProcessError as e:
        print(f"索引 = {idx}，发生错误:", e) 
        # 打印标准错误输出（即命令的错误信息）
        break
    if idx % 100 == 99:
        with open('tmp_output.txt', 'w') as f:
            print(f"总数 = {total}", file=f)
            print(f"伪冲突 = {sum(kind_pseudo.values())}", file=f)
            print(f"正确数 = {correct}", file=f)
            print(f"伪冲突正确率 = {correct/sum(kind_pseudo.values())*100}%", file=f)
            print(f"总正确率 = {correct/total*100}%", file=f)
            print(f"奇怪的数据 = {wierd}", file=f)
            print('-' * 30, file=f)
            ratio = {kind: kind_correct[kind]/kind_counter[kind]*100 for kind in kind_counter.keys()}
            print('各种类型的正确率：', file=f)
            print(ratio, file=f)
            print('各种类型的伪冲突占比：', file=f)
            print({kind: kind_pseudo[kind]/kind_counter[kind]*100 for kind in kind_counter.keys()}, file=f)


save_name = './output/result_' + file_path[file_path.rfind('/')+1:file_path.rfind('.')] + '.txt'
with open(save_name, 'w') as f:
    print(f"总数 = {total}", file=f)
    print(f"伪冲突 = {sum(kind_pseudo.values())}", file=f)
    print(f"正确数 = {correct}", file=f)
    print(f"伪冲突正确率 = {correct/sum(kind_pseudo.values())*100}%", file=f)
    print(f"总正确率 = {correct/total*100}%", file=f)
    print(f"奇怪的数据 = {wierd}", file=f)
    print('-' * 30, file=f)
    ratio = {kind: kind_correct[kind]/kind_counter[kind]*100 for kind in kind_counter.keys()}
    print('各种类型的正确率：', file=f)
    print(ratio, file=f)
    print('各种类型的伪冲突占比：', file=f)
    print({kind: kind_pseudo[kind]/kind_counter[kind]*100 for kind in kind_counter.keys()}, file=f)
