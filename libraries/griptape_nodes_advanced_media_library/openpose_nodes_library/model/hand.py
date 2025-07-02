from typing import Any

import cv2  # type: ignore[reportMissingImports]
import numpy as np
import torch  # type: ignore[reportMissingImports]
from scipy.ndimage.filters import gaussian_filter  # type: ignore[reportMissingImports]
from skimage.measure import label  # type: ignore[reportMissingImports]

from openpose_nodes_library.model import util
from openpose_nodes_library.model.model import HandPoseModel


class Hand:
    def __init__(self, state_dict: dict[str, Any]) -> None:
        self.model = HandPoseModel()

        # Use MPS if available (Apple Silicon), otherwise CUDA, otherwise CPU
        if torch.backends.mps.is_available():
            self.device = torch.device("mps")
            self.model = self.model.to(self.device)
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
            self.model = self.model.cuda()
        else:
            self.device = torch.device("cpu")

        model_dict = util.transfer(self.model, state_dict)
        self.model.load_state_dict(model_dict)
        self.model.eval()

    def __call__(self, ori_img: Any) -> Any:
        scale_search = [0.5, 1.0, 1.5, 2.0]
        boxsize = 368
        stride = 8
        pad_value = 128
        threshold = 0.05
        multiplier = [x * boxsize / ori_img.shape[0] for x in scale_search]
        heatmap_avg = np.zeros((ori_img.shape[0], ori_img.shape[1], 22))

        for m in range(len(multiplier)):
            scale = multiplier[m]
            image_to_test = cv2.resize(ori_img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            image_to_test_padded, pad = util.padRightDownCorner(image_to_test, stride, pad_value)
            im = np.transpose(np.float32(image_to_test_padded[:, :, :, np.newaxis]), (3, 2, 0, 1)) / 256 - 0.5
            im = np.ascontiguousarray(im)

            data = torch.from_numpy(im).float()
            data = data.to(self.device)
            with torch.no_grad():
                output = self.model(data).cpu().numpy()

            # extract outputs, resize, and remove padding
            heatmap = np.transpose(np.squeeze(output), (1, 2, 0))  # output 1 is heatmaps
            heatmap = cv2.resize(heatmap, (0, 0), fx=stride, fy=stride, interpolation=cv2.INTER_CUBIC)
            heatmap = heatmap[: image_to_test_padded.shape[0] - pad[2], : image_to_test_padded.shape[1] - pad[3], :]
            heatmap = cv2.resize(heatmap, (ori_img.shape[1], ori_img.shape[0]), interpolation=cv2.INTER_CUBIC)

            heatmap_avg += heatmap / len(multiplier)

        all_peaks = []
        for part in range(21):
            map_ori = heatmap_avg[:, :, part]
            one_heatmap = gaussian_filter(map_ori, sigma=3)
            binary = np.ascontiguousarray(one_heatmap > threshold, dtype=np.uint8)
            # All below threshold
            if np.sum(binary) == 0:
                all_peaks.append([0, 0])
                continue
            label_img, label_numbers = label(binary, return_num=True, connectivity=binary.ndim)
            max_index = np.argmax([np.sum(map_ori[label_img == i]) for i in range(1, label_numbers + 1)]) + 1
            label_img[label_img != max_index] = 0
            map_ori[label_img == 0] = 0

            y, x = util.npmax(map_ori)
            all_peaks.append([x, y])
        return np.array(all_peaks)


if __name__ == "__main__":
    state_dict = torch.load("../model/hand_pose_model.pth")
    hand_estimation = Hand(state_dict)

    test_image = "../images/hand.jpg"
    ori_img = cv2.imread(test_image)  # B,G,R order
    peaks = hand_estimation(ori_img)
    canvas = util.draw_handpose(ori_img, [peaks], show_number=True)
    cv2.imshow("", canvas)
    cv2.waitKey(0)
