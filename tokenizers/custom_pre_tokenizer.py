from tokenizers.pre_tokenizers import PreTokenizer
from tokenizers import PreTokenizedString
import re

# 自定义预分词器函数
class CustomPreTokenizer:
    def pre_tokenize(self, text: PreTokenizedString):
        # 分割连续的空白符和非空白字符
        tokens = re.findall(r'\s+|[^\s]+', text)
        print(tokens)

        # 处理结果，确保空白符作为单独的符号
        processed_tokens = []
        for token in tokens:
            if token.isspace():
                processed_tokens.extend([char for char in token])
            elif token.isdigit():
                processed_tokens.extend([char for char in token])
            else:
                processed_tokens.append(token)
