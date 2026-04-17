import cv2
import numpy as np
from PIL import Image

def apply_clahe(pil_img):
    img_np = np.array(pil_img)
    if len(img_np.shape) == 3:
        # Convert to LAB space to apply CLAHE only on the L channel
        lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl,a,b))
        out_np = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
        return Image.fromarray(out_np)
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        cl = clahe.apply(img_np)
        return Image.fromarray(cl)
