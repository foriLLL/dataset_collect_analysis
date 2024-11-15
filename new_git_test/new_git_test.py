import random
from collections import defaultdict
import re
from tqdm import tqdm
import json
from git import Commit, Head, Repo, Git
import os

from numpy import delete
from pathlib import Path

script_path = Path(os.path.dirname(os.path.abspath(__file__)))

# data_dir = script_path / '..' / 'data_collect_analysis' / 'output' / '2000repos'
data_dir = script_path / '..' / 'data_collect_analysis' / 'output' / 'mergebert_ts'
# 最后的 dataset_name
dataset_name = data_dir.stem
print(f"开始统计 {dataset_name} 数据集")


repo_path = Path(script_path / 'git_repo' / dataset_name)


def write_content_to_file(content: str | list[str], file_path: Path) -> None:
    # if content is a List, join it with '\n'
    if isinstance(content, list):
        # content = '\n'.join(content)
        if content in [[''], []]:
            content = ""            # ! 非常重要
        else:
            content = '\n'.join(content) + '\n'
    file_path.write_text(content)


# 如果存在，先删除
def remove_dir(dir_path: Path) -> None:
    if dir_path.exists():
        for item in dir_path.iterdir():
            if item.is_dir():
                remove_dir(item)
            else:
                item.unlink()
        dir_path.rmdir()

# 删除已有的仓库
if repo_path.exists():
    remove_dir(repo_path)

# 初始化 Git 仓库
repo = Repo.init(repo_path)
print(f"Initialized empty Git repository in {repo.git_dir}")

# 创建 .gitignore 文件
gitignore_path = repo_path / '.gitignore'
write_content_to_file(['.DS_Store', '.vscode/', '.idea/'], gitignore_path)

# 添加并提交 .gitignore 文件
repo.index.add([str(gitignore_path)])
repo.index.commit("Add .gitignore")
print(f"Added and committed .gitignore file.")

# 将 master 分支重命名为 main
if 'master' in repo.heads:
    repo.heads.master.rename('main')

tmpfile_path = Path(repo_path / 'tmp.txt')

new_git_path = '/root/projects/git/bin-wrappers/git'                  # 编译后的 Git 地址
log_path = script_path / 'log'
Git.git_exec_name = new_git_path
Git.refresh()
_git = Git(repo_path)


no_parent_commit_generator = Commit.iter_items(
    repo=repo, rev="main",  max_parents=0)  # 找到 reachable 最早的 commit
no_parent_commit = next(no_parent_commit_generator)


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


def replay(base_content, a_content, b_content):
    # 写入 base
    write_content_to_file(base_content, tmpfile_path)
    # 提交
    commit_all('base')
    # 新建 theirs 分支
    theirs_branch = create_branch('theirs')
    _git.checkout(theirs_branch)
    # 写入 theirs
    write_content_to_file(b_content, tmpfile_path)
    # 提交
    commit_all('theirs')
    # 切换回 main
    _git.checkout('main')
    # 写入 ours
    write_content_to_file(a_content, tmpfile_path)
    # 提交
    commit_all('ours')
    # merge theirs
    try:
        _git.merge('theirs')
    except Exception as e:
        return True  # merge conflict
    return False  # no conflict


def _log(save_name, kind_counter, kind_pseudo, kind_correct):
    def print_res(f):
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

    if save_name is None:
        import sys
        print_res(sys.stdout)
        return
    with open(save_name, 'w') as f:
        print_res(f)

def preprocess(content: str) -> str:
    return '' if content.strip() == '' else re.sub(r'\s+', ' ', content.strip() + '\n')

reset(delete_branch='theirs')
############################# 开始统计 #############################
kind_pseudo = defaultdict(int)
kind_counter = defaultdict(int)
kind_correct = defaultdict(int)

# 获取 data_dir 下所有的 json 文件
data_files = list(data_dir.glob('*.json'))
# 遍历所有文件，读取数据
for file_path in tqdm(data_files):
    with open(file_path, 'r', encoding='utf-8') as f:
        cfs = json.load(f)
    # 遍历所有的 chunk，重演 chunk 记录结果
    for cf in tqdm(cfs):
        for chunk in cf['conflict_chunks']:
            a_content = chunk['a_content']
            b_content = chunk['b_content']
            base_content = chunk['o_content']

            kind_counter[chunk['label']] += 1
            has_conflict = replay(base_content, a_content, b_content)
            if has_conflict:
                reset(delete_branch='theirs')
                continue
            kind_pseudo[chunk['label']] += 1

            # 没有冲突的情况下，读取 tmp.txt 文件
            with open(tmpfile_path, 'r', encoding='utf-8') as f:
                result = f.read()
            if (preprocess(result) == preprocess(chunk['r_content'])):
                kind_correct[chunk['label']] += 1
            reset(delete_branch='theirs')

    _log(None, kind_counter, kind_pseudo, kind_correct)



_log(log_path / (f'{dataset_name}.log'), kind_counter, kind_pseudo, kind_correct)
# 绘图表示并存储
def paint_new_git_result(kind_counter, kind_pseudo, kind_correct):
    import plotly.graph_objects as go
    fig = go.Figure()
    labels = list(kind_counter.keys())
    correct_pseudo = [kind_correct[label] for label in labels]
    wrong_pseudo = [kind_pseudo[label] - kind_correct[label] for label in labels]
    non_pseudo = [kind_counter[label] - kind_pseudo[label] for label in labels]

    fig.add_trace(go.Bar(
        x=labels,
        y=correct_pseudo,
        name='正确伪冲突'
    ))

    fig.add_trace(go.Bar(
        x=labels,
        y=wrong_pseudo,
        name='错误伪冲突',
        base=correct_pseudo
    ))

    fig.add_trace(go.Bar(
        x=labels,
        y=non_pseudo,
        name='非伪冲突',
        base=[correct_pseudo[i] + wrong_pseudo[i] for i in range(len(labels))]
    ))

    fig.update_layout(
        barmode='stack',
        title=f'{dataset_name} 伪冲突统计',
        xaxis_title='冲突类型',
        yaxis_title='数量',
        font=dict(
        family="Microsoft YaHei, SimHei, Arial",  # 指定多个字体，按顺序匹配
        size=14
    )
    )

    # 保存为 html 文件
    fig.write_html(log_path / f'{dataset_name}_new_git_result.html')

paint_new_git_result(kind_counter, kind_pseudo, kind_correct)
