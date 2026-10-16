import numpy as np


def get_mask(W, H, ratio_w=0.9, ratio_h=0.9):
    w = int(W * ratio_w)
    h = int(H * ratio_h)

    x1 = (W - w) // 2
    x2 = x1 + w

    y1 = (H - h) // 2
    y2 = y1 + h

    mask = np.ones((H, W), dtype=np.float32)

   
    row = np.linspace(0, 0, w)[None, :] 
    col = np.linspace(0, 1, y1)[:, None] 
    grad_t = np.sqrt(row**2 + col**2).astype(np.float32) 
    mask[0:y1, x1:x2] = grad_t

   
    row = np.linspace(0, 0, w)[None, :] 
    col = np.linspace(1, 0, H - y2)[:, None] 
    grad_b = np.sqrt(row**2 + col**2).astype(np.float32) 
    mask[y2:H, x1:x2] = grad_b

   
    row = np.linspace(0, 1, x1)[None, :] 
    col = np.linspace(0, 0, h)[:, None] 
    grad_l = np.sqrt(row**2 + col**2).astype(np.float32) 
    mask[y1:y2, 0:x1] = grad_l

   
    row = np.linspace(1, 0, W - x2)[None, :] 
    col = np.linspace(0, 0, h)[:, None] 
    grad_r = np.sqrt(row**2 + col**2).astype(np.float32) 
    mask[y1:y2, x2:W] = grad_r

   
    row = np.linspace(1, 0, x1)[None, :] 
    col = np.linspace(1, 0, y1)[:, None] 
    grad_tl = np.sqrt(row**2 + col**2).astype(np.float32) 
    grad_tl = 1 - np.clip(grad_tl, 0, 1)
    mask[0:y1, 0:x1] = grad_tl

   
    row = np.linspace(0, 1, W - x2)[None, :] 
    col = np.linspace(1, 0, y1)[:, None] 
    grad_tr = np.sqrt(row**2 + col**2).astype(np.float32) 
    grad_tr = 1 - np.clip(grad_tr, 0, 1)
    mask[0:y1, x2:W] = grad_tr

   
    row = np.linspace(1, 0, x1)[None, :] 
    col = np.linspace(0, 1, H - y2)[:, None] 
    grad_bl = np.sqrt(row**2 + col**2).astype(np.float32) 
    grad_bl = 1 - np.clip(grad_bl, 0, 1)
    mask[y2:H, 0:x1] = grad_bl

   
    row = np.linspace(0, 1, W - x2)[None, :] 
    col = np.linspace(0, 1, H - y2)[:, None] 
    grad_br = np.sqrt(row**2 + col**2).astype(np.float32) 
    grad_br = 1 - np.clip(grad_br, 0, 1)
    mask[y2:H, x2:W] = grad_br
    return mask[:, :, None]
