import os
from tokenizers import Tokenizer
from tokenizers.models import BPE
from pathlib import Path
from tokenizers.trainers import BpeTrainer
from tokenizers.pre_tokenizers import Whitespace, ByteLevel, Metaspace, Punctuation, PreTokenizer
from custom_pre_tokenizer import CustomPreTokenizer

# 获取当前文件的路径
script_path = Path(os.path.dirname(os.path.abspath(__file__)))
tokenizer_dataset_filename = "self_collected_most_50.raw"
tokenizer_output_filename = "self_collected_most_50_Whitespace.json"


tokenizer = Tokenizer(BPE(unk_token="[UNK]"))
tokenizer.pre_tokenizer = Whitespace()
# tokenizer.pre_tokenizer = ByteLevel()
# tokenizer.pre_tokenizer = Metaspace(replacement='Ġ')
# tokenizer.pre_tokenizer = Punctuation()
# tokenizer.pre_tokenizer = PreTokenizer.custom(CustomPreTokenizer())

trainer = BpeTrainer(special_tokens=["[UNK]", "[CLS]", "[SEP]", "[PAD]", "[MASK]",])

files = [str(script_path / "data" / tokenizer_dataset_filename)]
tokenizer.train(files, trainer)

if not os.path.exists(str(script_path / "output" )):
    os.makedirs(str(script_path / "output" ))
tokenizer.save(str(script_path / "output" / tokenizer_output_filename))