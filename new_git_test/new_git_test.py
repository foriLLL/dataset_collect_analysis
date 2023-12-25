import random
from collections import defaultdict
import re
from pkg_resources import to_filename
from tqdm import tqdm
import json
from telnetlib import EC
from git import Commit, Head, Repo, Git
import os

from numpy import delete
from util.conflict_util import Conflict
from pathlib import Path

script_path = Path(os.path.dirname(os.path.abspath(__file__)))
repo_path = Path(script_path / '..' / 'git_repo')
repo = Repo(repo_path)
tmpfile_path = Path(repo_path / 'tmp.txt')

new_git_path = '/Users/foril/projects/git/bin-wrappers/git'                  # 编译后的 Git 地址
log_path = script_path / '..' / 'log'
Git.git_exec_name = new_git_path
Git.refresh()
_git = Git(repo_path)

no_parent_commit_generator = Commit.iter_items(
    repo=repo, rev="main",  max_parents=0)  # 找到 reachable 最早的 commit
no_parent_commit = next(no_parent_commit_generator)

file_path = script_path / '..' / 'output' / 'self_collected_most_50.json'
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
        return True  # merge conflict
    return False  # no conflict


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


reset(delete_branch='theirs')
############################# 开始统计 #############################
random.seed(42)
random.shuffle(data)
kind_pseudo = defaultdict(int)
kind_counter = defaultdict(int)
kind_correct = defaultdict(int)
for idx, conflict_dict in enumerate(tqdm(data[:10])):
    if idx % 100 == 99:
        _log(log_path / (file_path.stem + f'_tmp.log'),
             kind_counter, kind_pseudo, kind_correct)
    conflict = Conflict(conflict_dict['ours'], conflict_dict['theirs'],
                        conflict_dict['base'], conflict_dict['resolve'], conflict_dict['resolution_kind'])
    kind_counter[conflict.resolution_kind] += 1
    has_conflict = replay(conflict)
    if has_conflict:
        reset(delete_branch='theirs')
        continue
    kind_pseudo[conflict.resolution_kind] += 1
    with open(tmpfile_path, 'r', encoding='utf-8') as f:
        result = f.read().split('\n')
    result = list(filter(lambda line: not (
        line == '' or line.isspace()), result))
    if result == list(filter(lambda line: not (line == '' or line.isspace()), conflict.resolution)):
        kind_correct[conflict.resolution_kind] += 1
    reset(delete_branch='theirs')

_log(log_path / (file_path.stem + f'.log'),
     kind_counter, kind_pseudo, kind_correct)
