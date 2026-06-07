import cv2
import numpy as np
from config import (
    HAND_CROP_RATIO, DEFECT_DEPTH_MIN,
    DEFECT_MIN, DEFECT_MAX, MIN_HAND_AREA
)


def detect_ok_gesture(frame, person_box, pose_model) -> bool:
    px1, py1, px2, py2 = map(int, person_box)
    px1 = max(0, px1 - 10)
    py1 = max(0, py1 - 10)
    px2 = min(frame.shape[1], px2 + 10)
    py2 = min(frame.shape[0], py2 + 10)

    crop = frame[py1:py2, px1:px2]
    if crop.size == 0:
        return False

    try:
        results = pose_model(crop, verbose=False)[0]
    except Exception:
        return False

    if results.keypoints is None:
        return False

    kpts = results.keypoints.xy.cpu().numpy()
    if len(kpts) == 0 or len(kpts[0]) < 11:
        return False

    kp = kpts[0]

    def valid(pt):
        return pt[0] > 0 and pt[1] > 0

    def is_raised(wrist, elbow, shoulder):
        if not (valid(wrist) and valid(elbow) and valid(shoulder)):
            return False
        return wrist[1] < shoulder[1]

    left_raised  = is_raised(kp[9],  kp[7], kp[5])
    right_raised = is_raised(kp[10], kp[8], kp[6])

    if not (left_raised or right_raised):
        return False

    wrist    = kp[10] if right_raised else kp[9]
    wx, wy   = int(wrist[0]), int(wrist[1])
    size     = int((px2 - px1) * HAND_CROP_RATIO)

    hx1 = max(0, wx - size)
    hy1 = max(0, wy - size)
    hx2 = min(crop.shape[1], wx + size)
    hy2 = min(crop.shape[0], wy + size)

    hand_crop = crop[hy1:hy2, hx1:hx2]
    if hand_crop.size == 0:
        return False

    return _is_ok_by_contour(hand_crop)


def _is_ok_by_contour(hand_img) -> bool:
    gray    = cv2.cvtColor(hand_img, cv2.COLOR_BGR2GRAY)
    blur    = cv2.GaussianBlur(gray, (7, 7), 0)
    thresh  = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < MIN_HAND_AREA:
        return False

    hull = cv2.convexHull(contour, returnPoints=False)
    if hull is None or len(hull) < 3:
        return False

    try:
        defects = cv2.convexityDefects(contour, hull)
    except Exception:
        return False

    if defects is None:
        return False

    count = sum(
        1 for i in range(defects.shape[0])
        if defects[i, 0][3] / 256.0 > DEFECT_DEPTH_MIN
    )
    return DEFECT_MIN <= count <= DEFECT_MAX