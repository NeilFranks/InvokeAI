import numpy as np
import cv2
from mss import mss
from PIL import Image

bounding_box = {'top': 168, 'left': 24, 'width': 834, 'height': 448}

sct = mss()

while True:
    sct_img = sct.grab(bounding_box)
    cv2.imshow('screen', np.array(sct_img))

    if (cv2.waitKey(1) & 0xFF) == ord('q'):
        cv2.destroyAllWindows()
        break