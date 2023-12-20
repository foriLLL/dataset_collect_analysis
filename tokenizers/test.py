import os
from pathlib import Path

from tokenizers import Tokenizer
script_path = Path(os.path.abspath(''))
trained_tokenizer_filename = "self_collected_most_50_Whitespace.json"
tokenizer = Tokenizer.from_file(str(script_path / "output" / trained_tokenizer_filename))
output = tokenizer.encode('\t\t\t @Parameters(commandDescription = "Frequency count a structured input instance file.")\n   \t ')
output = tokenizer.encode('\t这是一段临时测试，测试是否能够编码。😂   \t ')
print(output.ids)
print(output.tokens)

print(tokenizer.decode(output.ids))