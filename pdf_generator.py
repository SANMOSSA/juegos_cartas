"""Utilities for generating card deck PDFs on A4 sheets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageOps


PAGE_WIDTH = 3111
PAGE_HEIGHT = 4404
CARD_WIDTH = 796
CARD_HEIGHT = 1244
CARD_SPACING = 0
CARD_CORNER_RADIUS = 36
COLUMN_COUNT = 3
ROW_COUNT = 3
CARDS_PER_PAGE = COLUMN_COUNT * ROW_COUNT

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


try:  # Pillow >= 10
    RESAMPLE = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # Pillow < 10
    RESAMPLE = Image.LANCZOS  # type: ignore[attr-defined]


def _create_card_mask() -> Image.Image:
    mask = Image.new("L", (CARD_WIDTH, CARD_HEIGHT), 0)
    draw = ImageDraw.Draw(mask)
    radius = min(CARD_CORNER_RADIUS, CARD_WIDTH // 2, CARD_HEIGHT // 2)
    draw.rounded_rectangle((0, 0, CARD_WIDTH, CARD_HEIGHT), radius=radius, fill=255)
    return mask


_CARD_ALPHA_MASK = _create_card_mask()


@dataclass(frozen=True)
class CardAsset:
    name: str
    path: Path


@dataclass(frozen=True)
class GameAssets:
    name: str
    front_cards: Sequence[CardAsset]
    back_card: CardAsset


def list_games(base_dir: Path | str) -> Dict[str, GameAssets]:
    """Return all games found under the provided base directory."""

    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    games: Dict[str, GameAssets] = {}
    for folder in sorted(p for p in base_path.iterdir() if p.is_dir()):
        try:
            assets = _load_game_assets(folder)
        except ValueError:
            continue
        if assets.front_cards:
            games[assets.name] = assets

    return games


def generate_pdf(
    game: GameAssets,
    card_counts: Dict[str, int],
    output_dir: Path | str,
) -> Path:
    """Create the PDF document for the requested game configuration."""

    normalized_counts = {
        card: int(max(0, value)) for card, value in card_counts.items()
    }

    total_front_cards = sum(normalized_counts.values())
    if total_front_cards <= 0:
        raise ValueError("Selecciona al menos una carta para generar el documento.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%d-%m-%Y")
    document_name = f"{game.name.upper()}_{timestamp}.pdf"
    document_path = output_path / document_name

    front_sequence = _iter_front_sequence(game.front_cards, normalized_counts)
    layout_positions = _compute_layout_positions()

    front_pages = _render_pages(front_sequence, layout_positions)

    back_count = total_front_cards
    back_sequence = _iter_back_sequence(game.back_card.path, back_count)
    back_pages = _render_pages(back_sequence, layout_positions)

    pages = front_pages + back_pages
    if not pages:
        raise RuntimeError("No fue posible generar el PDF solicitado.")

    first_page, *other_pages = pages
    first_page.save(  # type: ignore[attr-defined]
        document_path,
        "PDF",
        resolution=300,
        save_all=True,
        append_images=other_pages,
    )

    return document_path


def _load_game_assets(folder: Path) -> GameAssets:
    images = [
        path
        for path in sorted(folder.iterdir())
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    ]

    back_card_path = None
    front_cards: List[CardAsset] = []

    for image_path in images:
        card_name = image_path.stem
        if card_name.lower() == "parte_atras":
            back_card_path = image_path
            continue
        front_cards.append(CardAsset(name=card_name, path=image_path))

    if back_card_path is None:
        raise ValueError(
            f"La carpeta '{folder.name}' no contiene una carta 'parte_atras'."
        )

    return GameAssets(
        name=folder.name,
        front_cards=tuple(front_cards),
        back_card=CardAsset(name="parte_atras", path=back_card_path),
    )


def _iter_front_sequence(
    cards: Sequence[CardAsset],
    counts: Dict[str, int],
) -> Iterator[Image.Image]:
    for card in cards:
        count = counts.get(card.name, 0)
        if count <= 0:
            continue
        image = _load_card_image(card.path)
        try:
            for _ in range(count):
                yield image.copy()
        finally:
            image.close()


def _iter_back_sequence(path: Path, count: int) -> Iterator[Image.Image]:
    if count <= 0:
        return
    image = _load_card_image(path)
    try:
        for _ in range(count):
            yield image.copy()
    finally:
        image.close()


def _render_pages(
    card_sequence: Iterable[Image.Image],
    positions: Sequence[Tuple[int, int]],
) -> List[Image.Image]:
    pages: List[Image.Image] = []

    position_total = len(positions)
    assert position_total == CARDS_PER_PAGE

    new_page = _blank_page
    current_page = None
    slot_index = 0

    for card_image in card_sequence:
        if current_page is None:
            current_page = new_page()
        x, y = positions[slot_index]
        if card_image.mode == "RGBA":
            alpha = card_image.getchannel("A")
            current_page.paste(card_image, (x, y), alpha)
            alpha.close()
        else:
            current_page.paste(card_image, (x, y))
        card_image.close()
        slot_index += 1

        if slot_index == position_total:
            rgb_page = current_page.convert("RGB")
            current_page.close()
            pages.append(rgb_page)
            current_page = None
            slot_index = 0

    if current_page is not None and slot_index > 0:
        rgb_page = current_page.convert("RGB")
        current_page.close()
        pages.append(rgb_page)

    return pages


def _blank_page() -> Image.Image:
    return Image.new("RGBA", (PAGE_WIDTH, PAGE_HEIGHT), (255, 255, 255, 255))


def _load_card_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA") if source.mode not in {"RGB", "RGBA"} else source.copy()
    image = ImageOps.fit(image, (CARD_WIDTH, CARD_HEIGHT), RESAMPLE)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    image.putalpha(_CARD_ALPHA_MASK)
    return image


def _compute_layout_positions() -> List[Tuple[int, int]]:
    effective_width = COLUMN_COUNT * CARD_WIDTH + (COLUMN_COUNT - 1) * CARD_SPACING
    effective_height = ROW_COUNT * CARD_HEIGHT + (ROW_COUNT - 1) * CARD_SPACING

    margin_x = (PAGE_WIDTH - effective_width) / 2
    margin_y = (PAGE_HEIGHT - effective_height) / 2

    x_positions = [
        int(round(margin_x + col * (CARD_WIDTH + CARD_SPACING)))
        for col in range(COLUMN_COUNT)
    ]
    y_positions = [
        int(round(margin_y + row * (CARD_HEIGHT + CARD_SPACING)))
        for row in range(ROW_COUNT)
    ]

    positions: List[Tuple[int, int]] = []
    for y in y_positions:
        for x in x_positions:
            positions.append((x, y))

    return positions
