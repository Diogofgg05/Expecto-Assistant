"""Optional, explicitly approved local LoRA SFT/DPO experiment.

Never run by normal Expecto service. Offline model only; CUDA required. This is
NOT an online reinforcement-learning loop. Evaluate adapters before activation.

Usage: python scripts/train_local_lora.py --mode sft --dataset data/training_exports/x
       --model /path/to/local/hf_checkpoint --output data/local_adapters/sft1 --approve-training
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path


def validate_paths(args):
    if not args.approve_training:
        raise PermissionError('O treino precisa de consentimento explícito --approve-training')
    root = Path(args.dataset).expanduser().resolve(strict=True)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != args.mode or manifest.get('training_executed') is not False:
        raise ValueError('O manifesto não corresponde a um conjunto curado por prepare-tuning')
    local_model = Path(args.model).expanduser().resolve(strict=True)
    if not local_model.is_dir() or not (local_model/'config.json').is_file():
        raise ValueError('É exigido um checkpoint Hugging Face local com config.json')
    output = Path(args.output).expanduser()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Destino já existente: não substituímos adapters')
    train = root/'train.jsonl'
    if not train.is_file() or train.stat().st_size == 0:
        raise ValueError('Treino vazio')
    return local_model, train, output


def main():
    parser=argparse.ArgumentParser(description='Experiência isolada LoRA SFT/DPO, nunca executada automaticamente')
    parser.add_argument('--mode',required=True,choices=['sft','dpo'])
    parser.add_argument('--dataset',required=True)
    parser.add_argument('--model',required=True,help='Checkpoint Hugging Face já presente no disco')
    parser.add_argument('--output',required=True)
    parser.add_argument('--approve-training',action='store_true')
    args=parser.parse_args()
    model_path, train, output=validate_paths(args)
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('Necessária GPU CUDA; não iniciar treino CPU acidentalmente')
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig
    from trl import SFTConfig,SFTTrainer,DPOConfig,DPOTrainer
    model=AutoModelForCausalLM.from_pretrained(str(model_path),local_files_only=True,trust_remote_code=False)
    tokenizer=AutoTokenizer.from_pretrained(str(model_path),local_files_only=True,trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    config=LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,bias='none',task_type='CAUSAL_LM')
    dataset=load_dataset('json',data_files=str(train),split='train')
    common=dict(output_dir=str(output),per_device_train_batch_size=1,
                gradient_accumulation_steps=4,learning_rate=1e-4,
                num_train_epochs=1,save_strategy='epoch',report_to='none')
    if args.mode=='sft':
        trainer=SFTTrainer(model=model,args=SFTConfig(**common,max_length=1024),
                           train_dataset=dataset,peft_config=config,processing_class=tokenizer)
    else:
        trainer=DPOTrainer(model=model,args=DPOConfig(**common,max_length=1024),
                           train_dataset=dataset,peft_config=config,processing_class=tokenizer)
    trainer.train()
    trainer.save_model(str(output))
    print('Adapter experimental criado. NÃO foi ativado na Expecto; avalia-o no holdout antes de usar.')


if __name__=='__main__':
    main()
