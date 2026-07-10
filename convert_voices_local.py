import os
import shutil
from pathlib import Path
import numpy as np

def main():
    import torch
    from huggingface_hub import hf_hub_download
    
    repo_id = 'contextboxai/Kokoro-Vietnamese'
    voices = [
        'diem_trinh', 'hung_thinh', 'mai_linh', 'mai_loan',
        'manh_dung', 'my_yen', 'ngoc_huyen', 'phat_tai',
        'thanh_dat', 'thuc_trinh', 'tuan_ngoc', 'storyvert',
        'duc_an', 'duc_duy'
    ]
    
    # Create target directories
    models_dir = Path('models')
    voicepacks_dir = models_dir / 'voicepacks'
    voicepacks_dir.mkdir(parents=True, exist_ok=True)
    
    print("Downloading base ONNX model...")
    onnx_src = hf_hub_download(repo_id=repo_id, filename='kokoro_vi.onnx')
    shutil.copy(onnx_src, models_dir / 'kokoro_vi.onnx')
    print("Saved kokoro_vi.onnx")
    
    print("Downloading config.json...")
    config_src = hf_hub_download(repo_id=repo_id, filename='config.json')
    shutil.copy(config_src, models_dir / 'config.json')
    print("Saved config.json")
    
    for voice in voices:
        filename = f"voicepacks/{voice}.pt"
        print(f"Downloading voicepack: {filename}")
        pt_src = hf_hub_download(repo_id=repo_id, filename=filename)
        
        print(f"Converting {voice} to numpy...")
        tensor = torch.load(pt_src, map_location='cpu', weights_only=True)
        arr = tensor.numpy() if hasattr(tensor, 'numpy') else np.asarray(tensor)
        
        npy_dest = voicepacks_dir / f"{voice}.npy"
        np.save(npy_dest, arr)
        print(f"Saved: {npy_dest}")
        
    print("All models and voicepacks converted and saved locally in 'models/' directory!")

if __name__ == '__main__':
    main()
