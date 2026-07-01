"""Tests for heuristic page feature extraction and classification."""

import cv2
import numpy as np

from compressor.classifier import classify_page, classify_pages, extract_features
from compressor.schemas import PageType


def test_extract_features_white_page_classifies_as_process() -> None:
    """A blank white page should classify as process with strong confidence."""
    image = np.full((240, 180, 3), 255, dtype=np.uint8)

    features = extract_features(image)
    page_type, confidence = classify_page(features)

    assert features.edge_density == 0.0
    assert features.image_area_ratio == 0.0
    assert features.text_area_ratio == 0.0
    assert page_type == PageType.PROCESS
    assert confidence >= 0.7


def test_extract_features_noise_page_classifies_as_hero() -> None:
    """A colorful noisy page should classify as hero with strong confidence."""
    rng = np.random.default_rng(42)
    image = rng.integers(0, 256, size=(240, 180, 3), dtype=np.uint8)

    features = extract_features(image)
    page_type, confidence = classify_page(features)

    assert features.color_entropy > 1.0
    assert features.edge_density > 0.05
    assert features.image_area_ratio > 0.5
    assert page_type == PageType.HERO
    assert confidence >= 0.7


def test_extract_features_solid_red_page_classifies_as_process() -> None:
    """A solid red page should still classify as process with high confidence."""
    image = np.zeros((240, 180, 3), dtype=np.uint8)
    image[:, :, 0] = 255

    features = extract_features(image)
    page_type, confidence = classify_page(features)

    assert features.color_entropy == 0.0
    assert features.edge_density == 0.0
    assert features.image_area_ratio > 0.9
    assert page_type == PageType.PROCESS
    assert confidence >= 0.7


def test_classify_pages_mixed_layout_classifies_as_hero() -> None:
    """A mixed image-and-text-like page should classify as hero."""
    image = np.full((240, 180, 3), 255, dtype=np.uint8)
    image[20:170, 20:160] = (0, 180, 255)
    image[35:95, 35:85] = (255, 80, 40)
    image[50:145, 100:150] = (40, 80, 255)

    for offset in range(0, 140, 14):
        cv2.line(image, (20 + offset, 20), (20, 20 + offset), (255, 255, 255), 2)

    for y in range(185, 230, 12):
        cv2.line(image, (25, y), (155, y), (0, 0, 0), 2)

    classifications = classify_pages([image])

    assert len(classifications) == 1
    classification = classifications[0]
    assert classification.page_num == 1
    assert classification.page_type == PageType.HERO
    assert classification.confidence >= 0.5
    assert classification.features.text_area_ratio == 0.0
