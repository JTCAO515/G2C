"""Offline imports, upstream argument compatibility, and tensor smoke; no model."""
from dataclasses import fields
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform

os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', MODELSCOPE_OFFLINE='1',
                  HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')

import torch
from swift.arguments import SftArguments
from swift.dataset import OpenAIMessagesPreprocessor
from swift.model import get_model_processor
from swift.template import get_template


def main():
    expected = {'ms-swift': '4.6.0', 'torch': '2.8.0', 'transformers': '4.57.6',
                'datasets': '4.8.4', 'peft': '0.18.1', 'trl': '0.29.1',
                'accelerate': '1.12.0', 'jsonschema': '4.26.0'}
    versions = {name: version(name) for name in expected}
    errors = ['VERSION_MISMATCH:' + name for name in expected
              if versions[name].split('+')[0] != expected[name]]
    if platform.python_version() != '3.12.14':
        errors.append('PYTHON_VERSION_MISMATCH')
    config = json.loads(Path(__file__).with_name('sft.example.json').read_text())
    unknown = sorted(set(config) - {field.name for field in fields(SftArguments)})
    errors.extend('UNKNOWN_SFT_ARGUMENT:' + key for key in unknown)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    value = torch.tensor([2.0], device=device, requires_grad=True)
    (value * value).sum().backward()
    gradient = value.grad.cpu().tolist()
    if gradient != [4.0]:
        errors.append('TENSOR_BACKWARD_FAILED')
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'scope': 'environment-only',
                      'python': platform.python_version(), 'platform': platform.system(),
                      'architecture': platform.machine(), 'versions': versions,
                      'tensor_device': device, 'gradient': gradient,
                      'cuda_available': torch.cuda.is_available(), 'errors': errors,
                      'real_model_template': 'UNRUN', 'training': 'UNRUN'}))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
