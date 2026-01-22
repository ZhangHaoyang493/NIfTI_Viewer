import os
import shutil
import argparse
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable):
        return iterable

def process_data(img_dir, out_dir, pred_dir=None, gt_dir=None):
    """
    Organize NIfTI files into a structured directory format.
    
    Structure:
    out_dir/
      {case_name}/
        {case_name}_0000.nii.gz  (Original Image)
        {case_name}_pred.nii.gz  (Prediction, optional)
        {case_name}_gt.nii.gz    (Ground Truth, optional)
    """
    img_path = Path(img_dir)
    out_path = Path(out_dir)
    
    if not img_path.exists():
        raise FileNotFoundError(f"Image directory not found: {img_dir}")
    
    # Create output directory if it doesn't exist
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Find all images ending with _0000.nii.gz
    # Using glob to find files in the top level of img_dir
    nii_files = list(img_path.glob("*_0000.nii.gz"))
    
    if not nii_files:
        print(f"No files ending with _0000.nii.gz found in {img_dir}")
        return

    print(f"Found {len(nii_files)} images to process.")

    # Iterate over files with a progress bar
    for file_path in tqdm(nii_files):
        file_name = file_path.name
        # Extract case name: {name}_0000.nii.gz -> {name}
        # We split by '_0000.nii.gz' to safely handle the suffix
        if not file_name.endswith("_0000.nii.gz"):
            continue
            
        case_name = file_name[:-12] # remove _0000.nii.gz (12 chars)
        
        # Create a folder for this case
        case_folder = out_path / case_name
        case_folder.mkdir(exist_ok=True)
        
        # 1. Copy Image
        # Destination: {out_dir}/{case_name}/{case_name}_0000.nii.gz
        dst_img_path = case_folder / file_name
        shutil.copy(file_path, dst_img_path)
        
        # 2. Process Prediction (Optional)
        if pred_dir:
            pred_path_src = Path(pred_dir) / f"{case_name}.nii.gz"
            if pred_path_src.exists():
                dst_pred_path = case_folder / f"{case_name}_pred.nii.gz"
                shutil.copy(pred_path_src, dst_pred_path)
            else:
                # Optional: print warning if expected but missing (verbose mode?)
                # print(f"Warning: Prediction file not found: {pred_path_src}")
                pass

        # 3. Process Ground Truth (Optional)
        if gt_dir:
            gt_path_src = Path(gt_dir) / f"{case_name}.nii.gz"
            if gt_path_src.exists():
                dst_gt_path = case_folder / f"{case_name}_gt.nii.gz"
                shutil.copy(gt_path_src, dst_gt_path)
            else:
                # print(f"Warning: GT file not found: {gt_path_src}")
                pass

    print("Processing complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Organize NIfTI images, predictions, and ground labels into case-specific folders.")
    
    parser.add_argument("-i", "--img_dir", type=str, required=True, help="Path to the directory containing images (ending in _0000.nii.gz)")
    parser.add_argument("-o", "--out_dir", type=str, required=True, help="Path to the output directory where folders will be created")
    parser.add_argument("-p", "--pred_dir", type=str, help="Path to the directory containing model predictions (named {name}.nii.gz)", default=None)
    parser.add_argument("-g", "--gt_dir", type=str, help="Path to the directory containing ground truth labels (named {name}.nii.gz)", default=None)
    
    args = parser.parse_args()
    
    process_data(args.img_dir, args.out_dir, args.pred_dir, args.gt_dir)
