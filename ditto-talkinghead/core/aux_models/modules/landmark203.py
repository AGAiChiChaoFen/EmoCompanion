import onnxruntime
import numpy as np


def _transform_pts(pts, M):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    return pts @ M[:2, :2].T + M[:2, 2]

    
class Landmark203:
    def __init__(self, model_file, device="cuda"):
        if device == "cuda":
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]
        self.session = onnxruntime.InferenceSession(model_file, providers=providers)

        self.dsize = 224

    def _run(self, inp):
        out = self.session.run(None, {'input': inp})
        return out
    
    def run(self, img_crop_rgb, M_c2o=None):
       

        inp = (img_crop_rgb.astype(np.float32) / 255.).transpose(2, 0, 1)[None, ...] 

        out_lst = self._run(inp)
        out_pts = out_lst[2]

       
        lmk = out_pts[0].reshape(-1, 2) * self.dsize 
        if M_c2o is not None:
            lmk = _transform_pts(lmk, M=M_c2o)

        return lmk
    
