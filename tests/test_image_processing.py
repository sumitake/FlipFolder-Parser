"""Unit tests for computer vision and image processing routines."""
import numpy as np

from flip_folder_tool import calculate_deskew_angle, deskew_image


def test_deskew_horizontal_lines():
    # Synthetic image with horizontal lines (0 deg skew)
    img = np.full((300, 500), 255, dtype=np.uint8)
    for y in [50, 70, 90, 110, 130]:
        img[y:y+2, 50:450] = 0

    angle = calculate_deskew_angle(img)
    # Deskew angle on perfectly horizontal lines should be very close to 0
    assert abs(angle) < 1.0


def test_deskew_blank_image():
    # On a blank image with no edges, angle should default to 0.0
    img = np.full((200, 200), 255, dtype=np.uint8)
    angle = calculate_deskew_angle(img)
    assert angle == 0.0


def test_deskew_image_shape_preserved():
    img = np.full((300, 500, 3), 255, dtype=np.uint8)
    deskewed = deskew_image(img, 1.5)
    assert deskewed.shape == img.shape
