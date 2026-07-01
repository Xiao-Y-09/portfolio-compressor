"""Configuration constants for classification thresholds and compression defaults."""

HERO_THRESHOLD: float = 2.5
"""Heuristic score threshold above which a page is classified as hero."""

COLOR_ENTROPY_WEIGHT: float = 0.4
"""Weight applied to hue entropy in the hero score calculation."""

EDGE_DENSITY_WEIGHT: float = 30.0
"""Weight applied to edge density in the hero score calculation."""

IMAGE_AREA_RATIO_WEIGHT: float = 0.5
"""Weight applied to non-white image area ratio in the hero score calculation."""

HSV_HIST_BINS: int = 32
"""Number of bins used for the hue histogram when computing entropy."""

ENTROPY_EPSILON: float = 1e-12
"""Lower bound for probability values included in entropy computation."""

CANNY_THRESHOLD_1: int = 50
"""Lower threshold for Canny edge detection."""

CANNY_THRESHOLD_2: int = 150
"""Upper threshold for Canny edge detection."""

NON_WHITE_THRESHOLD: int = 245
"""Grayscale cutoff below which pixels are treated as non-white foreground."""

MORPH_CLOSE_KERNEL_SIZE: int = 5
"""Kernel width and height used for morphology closing on the foreground mask."""

MORPH_CLOSE_ITERATIONS: int = 1
"""Number of morphology closing iterations for the foreground mask."""

TEXT_AREA_RATIO_DEFAULT: float = 0.0
"""Fixed text-area ratio for the MVP until text detection is introduced later."""

CONFIDENCE_SCALE: float = 2.0
"""Score distance scaling factor used in confidence calculation."""

CONFIDENCE_BASELINE: float = 0.5
"""Base confidence assigned to borderline classifications."""
