# Load model directly
from transformers import AutoTokenizer, AutoModelForMaskedLM

tokenizer = AutoTokenizer.from_pretrained("huggingface/CodeBERTa-small-v1")

def encode(text: str):
    return tokenizer.encode(text)

def decode(token_ids: list[int]):
    return tokenizer.convert_ids_to_tokens(token_ids)

if __name__ == '__main__':
    output = encode('\t\t\t @Parameters(commandDescription = "Frequency count a structured input instance file.")\n   \t ')
    output = encode('\t这是一段临时测试，测试是否能够编码。😂')
    output = encode('')
    print(output)
    print(tokenizer.convert_ids_to_tokens(output))