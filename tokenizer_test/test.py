# Load model directly
from transformers import AutoTokenizer, AutoModelForMaskedLM

tokenizer = AutoTokenizer.from_pretrained("huggingface/CodeBERTa-small-v1")
# model = AutoModelForMaskedLM.from_pretrained("huggingface/CodeBERTa-small-v1")

output = tokenizer.encode('\t\t\t @Parameters(commandDescription = "Frequency count a structured input instance file.")\n   \t ')
output = tokenizer.encode('\t这是一段临时测试，测试是否能够编码。😂')
print(output)
print(tokenizer.decode(output))