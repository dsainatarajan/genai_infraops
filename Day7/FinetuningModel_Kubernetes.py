# Install required libraries and set up environment
!pip install -q accelerate peft bitsandbytes transformers trl datasets

import torch
from datasets import load_dataset, DatasetDict
from peft import LoraConfig
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer, 
    BitsAndBytesConfig, 
    TrainingArguments,
    GenerationConfig
)
from trl import SFTTrainer

# 1. Configuration
MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
OUTPUT_DIR = "tinyllama-kubectl-lora"
DATA_PATH = "/mnt/data/kubectl_dataset.json"  # Path to your JSON dataset

# 2. Helper to format prompts
def format_example(example):
    prompt = f"<|user|>\n{example['input']}</s>\n<|assistant|>\n{example['output']}</s>"
    return {"text": prompt}

# 3. Load and preprocess dataset
raw_ds = load_dataset("json", data_files={"train": DATA_PATH})
# Map to single text field
ds = raw_ds["train"].map(format_example, remove_columns=raw_ds["train"].column_names)
# Optionally split train/validation
dataset = DatasetDict({
    "train": ds.train_test_split(test_size=0.05, seed=42)["train"],
    "validation": ds.train_test_split(test_size=0.05, seed=42)["test"]
})

# 4. Load model & tokenizer with 4-bit quantization
def get_model_tokenizer(model_id):
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenizer.pad_token = tokenizer.eos_token
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype="float16",
        bnb_4bit_use_double_quant=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto"
    )
    model.config.use_cache = False
    return model, tokenizer

model, tokenizer = get_model_tokenizer(MODEL_ID)

# 5. PEFT LoRA configuration
peft_config = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

# 6. Training arguments
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=16,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    num_train_epochs=3,
    logging_steps=50,
    save_strategy="epoch",
    evaluation_strategy="epoch",
    fp16=True,
    optim="paged_adamw_32bit",
    lr_scheduler_type="cosine"
)

# 7. Initialize SFTTrainer for LoRA fine-tuning
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    peft_config=peft_config,
    tokenizer=tokenizer,
    args=training_args,
    max_seq_length=512  # adjust based on typical prompt length
)

# 8. Fine-tune
trainer.train()

# 9. Generation function to test model after fine-tuning
def generate_kubectl_command(prompt: str, max_new_tokens: int = 64):
    formatted = f"<|user|>\n{prompt}</s>\n<|assistant|>"
    inputs = tokenizer(formatted, return_tensors="pt").to(model.device)
    generation_config = GenerationConfig(
        do_sample=False,
        temperature=0.0,
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.eos_token_id
    )
    output_ids = model.generate(**inputs, generation_config=generation_config)
    decoded = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    # Extract assistant response
    return decoded.split("<|assistant|>")[-1].strip()

# Example usage:
print(generate_kubectl_command("create a deployment named dep1 with httpd image and 2 replicas"))
