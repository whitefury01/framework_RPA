import logging
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Union, Dict, List, Generator

import pytesseract
from pytesseract import TesseractNotFoundError
from PIL import Image

from RPA.core.geometry import Region
from RPA.recognition.utils import to_image, clamp

LOGGER = logging.getLogger(__name__)

# TODO: refer to conda package when created?
INSTALL_PROMPT = (
    "tesseract is not installed or not in PATH, "
    "see library documentation for installation instructions"
)

DEFAULT_CONFIDENCE = 80.0


def find(
    image: Union[Image.Image, Path], text: str, confidence: float = DEFAULT_CONFIDENCE
):
    """Scan image for text and return a list of regions
    that contain it (or something close to it).

    :param image: Path to image or Image object
    :param text: Text to find in image
    :param confidence: Minimum confidence for text similarity
    """
    text = str(text)
    confidence = clamp(1, float(confidence), 100)

    data = _scan_image(image)

    lines = defaultdict(list)
    for word in _iter_rows(data):
        if word["level"] != 5:
            continue

        key = "{:d}-{:d}-{:d}".format(
            word["block_num"], word["par_num"], word["line_num"]
        )
        region = Region.from_size(
            word["left"], word["top"], word["width"], word["height"]
        )

        # NOTE: Currently ignoring confidence in tesseract results
        lines[key].append({"text": word["text"], "region": region})
        assert len(lines[key]) == word["word_num"]

    matches = _match_lines(lines.values(), text, confidence)
    matches = sorted(matches, key=lambda match: match["confidence"], reverse=True)

    return matches


def _scan_image(image: Union[Image.Image, Path]) -> Dict:
    """Use tesseract to scan image for text."""
    image = to_image(image)
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        return data
    except TesseractNotFoundError as err:
        raise EnvironmentError(INSTALL_PROMPT) from err


def _iter_rows(data: Dict) -> Generator:
    """Convert dictionary of columns to iterable rows."""
    return (dict(zip(data.keys(), values)) for values in zip(*data.values()))


def _match_lines(lines: List[Dict], text: str, confidence: float) -> List[Dict]:
    """Find best matches between lines of text and target text,
    and return resulting bounding boxes and confidences.
    """
    matches = []
    for line in lines:
        match = {}

        for window in range(1, len(line) + 1):
            for index in range(len(line) - window + 1):
                words = line[index : index + window]
                regions = [word["region"] for word in words]

                sentence = " ".join(word["text"] for word in words)
                ratio = SequenceMatcher(None, sentence, text).ratio() * 100.0

                if ratio < confidence:
                    continue

                if match and match["confidence"] >= ratio:
                    continue

                match = {
                    "text": sentence,
                    "region": Region.merge(*regions),
                    "confidence": ratio,
                }

        if match:
            matches.append(match)

    return matches
