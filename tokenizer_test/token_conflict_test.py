import random
from collections import defaultdict
from email.mime import base
import re
from shlex import join
from typing import List
from tqdm import tqdm
import json
from git import Commit, Head, Repo, Git
import os
from util.conflict_util import Conflict, conflict2file
from pathlib import Path
from util.tokenizer_util import encode, decode

script_path = Path(os.path.dirname(os.path.abspath(__file__)))
log_path = Path(script_path / '..' / 'log' / 'ES_unresolvable_self_collected_most_50_token_conflict_test.log')

repo_path = Path(script_path / ".." / "git_repo")
repo = Repo(repo_path)
tmpfile_path = Path(repo_path / 'tmp.txt')

_git = Git(repo_path)

no_parent_commit_generator = Commit.iter_items(
    repo=repo, rev="main",  max_parents=0)  # 找到 reachable 最早的 commit
no_parent_commit = next(no_parent_commit_generator)

file_path = script_path / ".." / 'output' / 'self_collected_most_50_unresolvable.json'
with open(file_path, 'r', encoding='utf-8') as json_file:
    data = json.load(json_file)


def write_content_to_file(content: str | list[str], file_path: Path) -> None:
    # if content is a List, join it with '\n'
    if isinstance(content, list):
        # content = '\n'.join(content)
        if content in [[''], []]:
            content = ""            # ! 非常重要
        else:
            content = '\n'.join(content) + '\n'
    file_path.write_text(content)

def create_branch(branch_name: str) -> Head:
    # 在当前提交的基础上新建分支
    _git.branch(branch_name)
    return repo.heads[branch_name]


def reset(delete_branch: str) -> None:
    _git.restore('.', '--staged')
    _git.restore('.', '--worktree')
    _git.checkout('main')
    # 检查要删除的分支是否存在
    if delete_branch in repo.heads:
        # 删除分支
        _git.branch('-D', delete_branch)
    # main reset 到第一个 commit
    _git.reset('--hard', str(no_parent_commit))


def commit_all(commit_message: str) -> None:
    # track 所有文件
    _git.add('.')
    # 提交
    repo.index.commit(commit_message)


def replay(conflict: Conflict):
    # 写入 base
    write_content_to_file(conflict.base, tmpfile_path)
    # 提交
    commit_all('base')
    # 新建 theirs 分支
    theirs_branch = create_branch('theirs')
    _git.checkout(theirs_branch)
    # 写入 theirs
    write_content_to_file(conflict.theirs, tmpfile_path)
    # 提交
    commit_all('theirs')
    # 切换回 main
    _git.checkout('main')
    # 写入 ours
    write_content_to_file(conflict.ours, tmpfile_path)
    # 提交
    commit_all('ours')
    # merge theirs
    try:
        _git.merge('theirs')
    except Exception as e:
        return True # merge conflict
    return False # no conflict

def debug_view(conflict: Conflict):
    '''将冲突写入本地文件，用于 diffviewer 查看'''
    conflict2file(conflict, Path('/Users/foril/projects/conflict_resolve/test_with_vscode/tmp'))


os.environ["TOKENIZERS_PARALLELISM"] = "false"  # 禁用 tokenizers 的并行，避免 warning
############################# 开始统计 token 级别冲突 #############################
random.seed(42)
random.shuffle(data)
kind_counter = defaultdict(int)
token_resolvable_counter = defaultdict(int)
correct_counter = defaultdict(int)


for conflict_dict in tqdm(data[:], dynamic_ncols=True):
    reset(delete_branch='theirs')
    # 1. 拿到 conflict
    conflict = Conflict(conflict_dict['ours'], conflict_dict['theirs'],
                        conflict_dict['base'], conflict_dict['resolution'], conflict_dict['resolution_kind'])
    kind_counter[conflict.resolution_kind] += 1
    
    debug_view(conflict)

    def content_preprocess(content_list: List[str]):
        # !important
        if content_list in [[''], []]:
            return ""
        return '\n'.join(content_list) + '\n'   # todo 检查是否正确
    
    base_content = content_preprocess(conflict.base)
    ours_content = content_preprocess(conflict.ours)
    theirs_content = content_preprocess(conflict.theirs)
    resolution_content = content_preprocess(conflict.resolution)
    # 2. 对 ours, theirs, base, resolution 都分词
    def tokenize_to_str_list(content: str) -> List[str]:
        encoded_list = encode(content)
        decoded_strs = decode(encoded_list)
        return decoded_strs # type: ignore
    
    # 3. 每个 token 为一行
    base_tokens = tokenize_to_str_list(base_content)
    ours_tokens = tokenize_to_str_list(ours_content)
    theirs_tokens = tokenize_to_str_list(theirs_content)
    resolution_tokens = tokenize_to_str_list(resolution_content)

    # 4. replay，看是否有冲突
    tokenized_conflict = Conflict(ours_tokens, theirs_tokens, base_tokens, resolution_tokens, conflict.resolution_kind)
    debug_view(tokenized_conflict)
    has_conflict = replay(tokenized_conflict)
    if has_conflict:
        continue
    token_resolvable_counter[conflict.resolution_kind] += 1

    # 5. 比较没有冲突的合成结果是否一致
    merged_content = tmpfile_path.read_text()
    joint_merged = ''.join(merged_content.split('\n'))
    joint_resolution = ''.join(resolution_tokens)
    # todo：比较时去除空行  在上面 preprocess 时已经去除了
    if joint_merged == joint_resolution:
        correct_counter[conflict.resolution_kind] += 1

def _log(save_name, kind_counter, kind_pseudo, kind_correct):
    with open(save_name, 'w') as f:
        correct = sum(kind_correct.values())
        total = sum(kind_counter.values())
        print(f"总数 = {total}", file=f)
        print(f"伪冲突 = {sum(kind_pseudo.values())}", file=f)
        print(f"正确数 = {correct}", file=f)
        print(f"伪冲突正确率 = {correct/sum(kind_pseudo.values())*100}%", file=f)
        print(f"总正确率 = {correct/total*100}%", file=f)
        print('各类型的数量：', file=f)
        print(kind_counter, file=f)
        print('各类型伪冲突数量：', file=f)
        print(kind_pseudo, file=f)
        print('各类型正确数量：', file=f)
        print(kind_correct, file=f)

        print('-' * 30, file=f)

        total_correct_ratio = {
            kind: kind_correct[kind]/kind_counter[kind]*100 for kind in kind_counter.keys()}
        pseudo_correct_ratio = {
            kind: kind_correct[kind]/kind_pseudo[kind]*100 if kind_pseudo[kind] != 0 else 0 for kind in kind_counter.keys()}
        print('各种类型的伪冲突占比：', file=f)
        print({kind: kind_pseudo[kind]/kind_counter[kind]
              * 100 for kind in kind_counter.keys()}, file=f)
        print('各类型伪冲突正确率：', file=f)
        print(pseudo_correct_ratio, file=f)
        print('各种类型的总正确率：', file=f)
        print(total_correct_ratio, file=f)

_log(log_path, kind_counter, token_resolvable_counter, correct_counter)
