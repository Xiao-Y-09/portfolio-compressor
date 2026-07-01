"""OpenCV-based heuristic page classification for portfolio pages."""

import cv2
import numpy as np

from compressor.config import (
    CANNY_THRESHOLD_1,
    CANNY_THRESHOLD_2,
    COLOR_ENTROPY_WEIGHT,
    CONFIDENCE_BASELINE,
    CONFIDENCE_SCALE,
    EDGE_DENSITY_WEIGHT,
    ENTROPY_EPSILON,
    HERO_THRESHOLD,
    HSV_HIST_BINS,
    IMAGE_AREA_RATIO_WEIGHT,
    MORPH_CLOSE_ITERATIONS,
    MORPH_CLOSE_KERNEL_SIZE,
    NON_WHITE_THRESHOLD,
    TEXT_AREA_RATIO_DEFAULT,
)
from compressor.exceptions import ClassificationError
from compressor.schemas import PageClassification, PageFeatures, PageType


def extract_features(image: np.ndarray) -> PageFeatures:
    """Extract heuristic visual features from one RGB page image.

    Args:
        image: Rendered page image as an RGB numpy array.

    Returns:
        A structured set of heuristic features for the page.

    Raises:
        ClassificationError: If the input image is invalid or features cannot
            be computed.
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise ClassificationError("Expected an RGB image with shape (H, W, 3).")
    if image.dtype != np.uint8:
        raise ClassificationError("Expected image dtype uint8.")

    try:
        hsv_image = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        hue_channel = hsv_image[:, :, 0]
        histogram = cv2.calcHist([hue_channel], [0], None, [HSV_HIST_BINS], [0, 180])
        histogram = histogram.flatten().astype(np.float64)
        probability = histogram / histogram.sum()
        probability = probability[probability > ENTROPY_EPSILON]
        color_entropy = float(-np.sum(probability * np.log2(probability)))

        gray_image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray_image, CANNY_THRESHOLD_1, CANNY_THRESHOLD_2)
        edge_density = float(np.count_nonzero(edges) / edges.size)

        _, foreground_mask = cv2.threshold(
            gray_image,
            NON_WHITE_THRESHOLD,
            255,
            cv2.THRESH_BINARY_INV,
        )
        kernel = np.ones(
            (MORPH_CLOSE_KERNEL_SIZE, MORPH_CLOSE_KERNEL_SIZE),
            dtype=np.uint8,
        )
        closed_mask = cv2.morphologyEx(
            foreground_mask,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=MORPH_CLOSE_ITERATIONS,
        )
        image_area_ratio = float(np.count_nonzero(closed_mask) / closed_mask.size)

        # TODO(Phase 4): Replace the fixed placeholder with a real text detector.
        text_area_ratio = TEXT_AREA_RATIO_DEFAULT
    except (cv2.error, ValueError, ZeroDivisionError) as exc:
        raise ClassificationError("Failed to extract page features.") from exc

    return PageFeatures(
        color_entropy=color_entropy,
        edge_density=edge_density,
        image_area_ratio=image_area_ratio,
        text_area_ratio=text_area_ratio,
    )


def classify_page(features: PageFeatures) -> tuple[PageType, float]:
    """Classify one page from extracted features and return type plus confidence.

    Args:
        features: Heuristic features extracted from a page image.

    Returns:
        The page type and its confidence score.
    """
    hero_score = (
        features.color_entropy * COLOR_ENTROPY_WEIGHT
        + features.edge_density * EDGE_DENSITY_WEIGHT
        + features.image_area_ratio * IMAGE_AREA_RATIO_WEIGHT
    )

    if hero_score > HERO_THRESHOLD:
        page_type = PageType.HERO
        raw_confidence = (
            (hero_score - HERO_THRESHOLD) / CONFIDENCE_SCALE + CONFIDENCE_BASELINE
        )
    else:
        page_type = PageType.PROCESS
        raw_confidence = (
            (HERO_THRESHOLD - hero_score) / CONFIDENCE_SCALE + CONFIDENCE_BASELINE
        )

    confidence = float(np.clip(raw_confidence, 0.0, 1.0))
    return page_type, confidence


def classify_pages(images: list[np.ndarray]) -> list[PageClassification]:
    """Classify a list of RGB page images into numbered page results.

    Args:
        images: Rendered page images in document order.

    Returns:
        A list of per-page classification results.

    Raises:
        ClassificationError: If feature extraction fails for any image.
    """
    results: list[PageClassification] = []

    for index, image in enumerate(images, start=1):
        features = extract_features(image)
        page_type, confidence = classify_page(features)
        results.append(
            PageClassification(
                page_num=index,
                page_type=page_type,
                confidence=confidence,
                features=features,
            )
        )

    return results
