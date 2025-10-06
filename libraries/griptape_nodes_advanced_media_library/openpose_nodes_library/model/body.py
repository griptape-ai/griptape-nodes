import math
from typing import Any

import cv2  # type: ignore[reportMissingImports]
import numpy as np
import torch  # type: ignore[reportMissingImports]
from scipy.ndimage.filters import gaussian_filter  # type: ignore[reportMissingImports]

from openpose_nodes_library.model import util
from openpose_nodes_library.model.model import BodyPose25Model, BodyPoseModel

# Constants for magic numbers
FOUND_TWO_CONNECTIONS = 2
MIN_PARTS_THRESHOLD = 4
MIN_SCORE_RATIO = 0.4


class Body:
    def __init__(self, state_dict: dict[str, Any], model_type: str = "coco") -> None:
        if model_type == "coco":
            self.model = BodyPoseModel()
            self.njoint = 19
            self.npaf = 38
        elif model_type == "body25":
            self.model = BodyPose25Model()
            self.njoint = 26
            self.npaf = 52
        else:
            self.model = BodyPoseModel()
            self.njoint = 19
            self.npaf = 38
        self.model_type = model_type

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

    def __call__(self, ori_img: Any) -> tuple[Any, Any]:  # noqa: C901, PLR0912, PLR0915
        scale_search = [0.5]
        boxsize = 368
        stride = 8
        pad_value = 128
        threshold1 = 0.1
        threshold2 = 0.05
        multiplier = [x * boxsize / ori_img.shape[0] for x in scale_search]
        heatmap_avg = np.zeros((ori_img.shape[0], ori_img.shape[1], self.njoint))
        paf_avg = np.zeros((ori_img.shape[0], ori_img.shape[1], self.npaf))

        for m in range(len(multiplier)):
            scale = multiplier[m]
            image_to_test = cv2.resize(ori_img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            image_to_test_padded, pad = util.padRightDownCorner(image_to_test, stride, pad_value)
            im = np.transpose(np.float32(image_to_test_padded[:, :, :, np.newaxis]), (3, 2, 0, 1)) / 256 - 0.5
            im = np.ascontiguousarray(im)

            data = torch.from_numpy(im).float()
            data = data.to(self.device)
            with torch.no_grad():
                mconv7_stage6_l1, mconv7_stage6_l2 = self.model(data)
            mconv7_stage6_l1 = mconv7_stage6_l1.cpu().numpy()
            mconv7_stage6_l2 = mconv7_stage6_l2.cpu().numpy()

            # extract outputs, resize, and remove padding
            heatmap = np.transpose(np.squeeze(mconv7_stage6_l2), (1, 2, 0))  # output 1 is heatmaps
            heatmap = cv2.resize(heatmap, (0, 0), fx=stride, fy=stride, interpolation=cv2.INTER_CUBIC)
            heatmap = heatmap[: image_to_test_padded.shape[0] - pad[2], : image_to_test_padded.shape[1] - pad[3], :]
            heatmap = cv2.resize(heatmap, (ori_img.shape[1], ori_img.shape[0]), interpolation=cv2.INTER_CUBIC)

            paf = np.transpose(np.squeeze(mconv7_stage6_l1), (1, 2, 0))  # output 0 is PAFs
            paf = cv2.resize(paf, (0, 0), fx=stride, fy=stride, interpolation=cv2.INTER_CUBIC)
            paf = paf[: image_to_test_padded.shape[0] - pad[2], : image_to_test_padded.shape[1] - pad[3], :]
            paf = cv2.resize(paf, (ori_img.shape[1], ori_img.shape[0]), interpolation=cv2.INTER_CUBIC)

            heatmap_avg += heatmap_avg + heatmap / len(multiplier)
            paf_avg += +paf / len(multiplier)

        all_peaks = []
        peak_counter = 0

        for part in range(self.njoint - 1):
            map_ori = heatmap_avg[:, :, part]
            one_heatmap = gaussian_filter(map_ori, sigma=3)

            map_left = np.zeros(one_heatmap.shape)
            map_left[1:, :] = one_heatmap[:-1, :]
            map_right = np.zeros(one_heatmap.shape)
            map_right[:-1, :] = one_heatmap[1:, :]
            map_up = np.zeros(one_heatmap.shape)
            map_up[:, 1:] = one_heatmap[:, :-1]
            map_down = np.zeros(one_heatmap.shape)
            map_down[:, :-1] = one_heatmap[:, 1:]

            peaks_binary = np.logical_and.reduce(
                (
                    one_heatmap >= map_left,
                    one_heatmap >= map_right,
                    one_heatmap >= map_up,
                    one_heatmap >= map_down,
                    one_heatmap > threshold1,
                )
            )
            peaks = list(zip(np.nonzero(peaks_binary)[1], np.nonzero(peaks_binary)[0], strict=False))  # note reverse
            peaks_with_score = [(*x, map_ori[x[1], x[0]]) for x in peaks]
            peak_id = range(peak_counter, peak_counter + len(peaks))
            peaks_with_score_and_id = [peaks_with_score[i] + (peak_id[i],) for i in range(len(peak_id))]

            all_peaks.append(peaks_with_score_and_id)
            peak_counter += len(peaks)

        if self.model_type == "body25":
            # find connection in the specified sequence, center 29 is in the position 15
            limb_seq = [
                [1, 0],
                [1, 2],
                [2, 3],
                [3, 4],
                [1, 5],
                [5, 6],
                [6, 7],
                [1, 8],
                [8, 9],
                [9, 10],
                [10, 11],
                [8, 12],
                [12, 13],
                [13, 14],
                [0, 15],
                [0, 16],
                [15, 17],
                [16, 18],
                [11, 24],
                [11, 22],
                [14, 21],
                [14, 19],
                [22, 23],
                [19, 20],
            ]
            # the middle joints heatmap correspondence
            map_idx = [
                [30, 31],
                [14, 15],
                [16, 17],
                [18, 19],
                [22, 23],
                [24, 25],
                [26, 27],
                [0, 1],
                [6, 7],
                [2, 3],
                [4, 5],
                [8, 9],
                [10, 11],
                [12, 13],
                [32, 33],
                [34, 35],
                [36, 37],
                [38, 39],
                [50, 51],
                [46, 47],
                [44, 45],
                [40, 41],
                [48, 49],
                [42, 43],
            ]
        else:
            # find connection in the specified sequence, center 29 is in the position 15
            limb_seq = [
                [1, 2],
                [1, 5],
                [2, 3],
                [3, 4],
                [5, 6],
                [6, 7],
                [1, 8],
                [8, 9],
                [9, 10],
                [1, 11],
                [11, 12],
                [12, 13],
                [1, 0],
                [0, 14],
                [14, 16],
                [0, 15],
                [15, 17],
                [2, 16],
                [5, 17],
            ]
            # the middle joints heatmap correspondence
            map_idx = [
                [12, 13],
                [20, 21],
                [14, 15],
                [16, 17],
                [22, 23],
                [24, 25],
                [0, 1],
                [2, 3],
                [4, 5],
                [6, 7],
                [8, 9],
                [10, 11],
                [28, 29],
                [30, 31],
                [34, 35],
                [32, 33],
                [36, 37],
                [18, 19],
                [26, 27],
            ]

        connection_all = []
        special_k = []
        mid_num = 10

        for k in range(len(map_idx)):
            score_mid = paf_avg[:, :, map_idx[k]]
            cand_a = all_peaks[limb_seq[k][0]]
            cand_b = all_peaks[limb_seq[k][1]]

            n_a = len(cand_a)
            n_b = len(cand_b)
            index_a, index_b = limb_seq[k]
            if n_a != 0 and n_b != 0:
                connection_candidate = []
                for i in range(n_a):
                    for j in range(n_b):
                        vec = np.subtract(cand_b[j][:2], cand_a[i][:2])
                        norm = math.sqrt(vec[0] * vec[0] + vec[1] * vec[1])
                        norm = max(0.001, norm)
                        vec = np.divide(vec, norm)

                        startend = list(
                            zip(
                                np.linspace(cand_a[i][0], cand_b[j][0], num=mid_num),
                                np.linspace(cand_a[i][1], cand_b[j][1], num=mid_num),
                                strict=False,
                            )
                        )

                        vec_x = np.array(
                            [
                                score_mid[round(startend[idx][1]), round(startend[idx][0]), 0]
                                for idx in range(len(startend))
                            ]
                        )
                        vec_y = np.array(
                            [
                                score_mid[round(startend[idx][1]), round(startend[idx][0]), 1]
                                for idx in range(len(startend))
                            ]
                        )

                        score_midpts = np.multiply(vec_x, vec[0]) + np.multiply(vec_y, vec[1])
                        score_with_dist_prior = sum(score_midpts) / len(score_midpts) + min(
                            0.5 * ori_img.shape[0] / norm - 1, 0
                        )
                        criterion1 = len(np.nonzero(score_midpts > threshold2)[0]) > 0.8 * len(score_midpts)
                        criterion2 = score_with_dist_prior > 0
                        if criterion1 and criterion2:
                            connection_candidate.append(
                                [i, j, score_with_dist_prior, score_with_dist_prior + cand_a[i][2] + cand_b[j][2]]
                            )

                connection_candidate = sorted(connection_candidate, key=lambda x: x[2], reverse=True)
                connection = np.zeros((0, 5))
                for c in range(len(connection_candidate)):
                    i, j, s = connection_candidate[c][0:3]
                    if i not in connection[:, 3] and j not in connection[:, 4]:
                        connection = np.vstack([connection, [cand_a[i][3], cand_b[j][3], s, i, j]])
                        if len(connection) >= min(n_a, n_b):
                            break

                connection_all.append(connection)
            else:
                special_k.append(k)
                connection_all.append([])

        # last number in each row is the total parts number of that person
        # the second last number in each row is the score of the overall configuration
        subset = -1 * np.ones((0, self.njoint + 1))
        candidate = np.array([item for sublist in all_peaks for item in sublist])

        for k in range(len(map_idx)):
            if k not in special_k:
                part_as = connection_all[k][:, 0]
                part_bs = connection_all[k][:, 1]
                index_a, index_b = np.array(limb_seq[k])

                for i in range(len(connection_all[k])):  # = 1:size(temp,1)
                    found = 0
                    subset_idx = [-1, -1]
                    for j in range(len(subset)):  # 1:size(subset,1):
                        if subset[j][index_a] == part_as[i] or subset[j][index_b] == part_bs[i]:
                            subset_idx[found] = j
                            found += 1

                    if found == 1:
                        j = subset_idx[0]
                        if subset[j][index_b] != part_bs[i]:
                            subset[j][index_b] = part_bs[i]
                            subset[j][-1] += 1
                            subset[j][-2] += candidate[part_bs[i].astype(int), 2] + connection_all[k][i][2]
                    elif found == FOUND_TWO_CONNECTIONS:  # if found 2 and disjoint, merge them
                        j1, j2 = subset_idx
                        membership = ((subset[j1] >= 0).astype(int) + (subset[j2] >= 0).astype(int))[:-2]
                        if len(np.nonzero(membership == FOUND_TWO_CONNECTIONS)[0]) == 0:  # merge
                            subset[j1][:-2] += subset[j2][:-2] + 1
                            subset[j1][-2:] += subset[j2][-2:]
                            subset[j1][-2] += connection_all[k][i][2]
                            subset = np.delete(subset, j2, 0)
                        else:  # as like found == 1
                            subset[j1][index_b] = part_bs[i]
                            subset[j1][-1] += 1
                            subset[j1][-2] += candidate[part_bs[i].astype(int), 2] + connection_all[k][i][2]

                    # if find no partA in the subset, create a new subset
                    elif not found and k < self.njoint - 2:
                        row = -1 * np.ones(self.njoint + 1)
                        row[index_a] = part_as[i]
                        row[index_b] = part_bs[i]
                        row[-1] = 2
                        row[-2] = sum(candidate[connection_all[k][i, :2].astype(int), 2]) + connection_all[k][i][2]
                        subset = np.vstack([subset, row])
        # delete some rows of subset which has few parts occur
        delete_idx = [
            i
            for i in range(len(subset))
            if subset[i][-1] < MIN_PARTS_THRESHOLD or subset[i][-2] / subset[i][-1] < MIN_SCORE_RATIO
        ]
        subset = np.delete(subset, delete_idx, axis=0)

        # subset: n*20 array, 0-17 is the index in candidate, 18 is the total score, 19 is the total parts
        # candidate: x, y, score, id
        return candidate, subset


if __name__ == "__main__":
    model_type = "body25"  # 'coco'
    if model_type == "body25":
        model_path = "./model/pose_iter_584000.caffemodel.pt"
    else:
        model_path = "./model/body_pose_model.pth"

    # Load state dict from checkpoint file
    state_dict = torch.load(model_path, map_location="cpu")
    body_estimation = Body(state_dict, model_type)

    test_image = "./images/ski.jpg"
    ori_img = cv2.imread(test_image)  # B,G,R order
    candidate, subset = body_estimation(ori_img)
    canvas = util.draw_bodypose(ori_img, candidate, subset, model_type)
    cv2.imwrite("body_result2.png", canvas)
