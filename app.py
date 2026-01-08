"""Gradio app for generating custom card PDFs."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import gradio as gr

from pdf_generator import GameAssets, generate_pdf, list_games


BASE_DIR = Path("Juegos")
OUTPUT_DIR = Path("documentos")

BASE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def _initial_games() -> Dict[str, GameAssets]:
    return list_games(BASE_DIR)


def _game_metadata() -> List[Tuple[str, GameAssets]]:
    games = _initial_games()
    sorted_names = sorted(games.keys())
    return [(name, games[name]) for name in sorted_names]


def generate_document(game_name: str, *counts: float):
    games = list_games(BASE_DIR)
    if game_name not in games:
        raise gr.Error(
            "Selecciona un juego válido antes de generar el documento.")

    game = games[game_name]

    cards_order = [card.name for card in game.front_cards]
    count_mapping = {name: 0 for name in cards_order}

    relevant_counts = counts[: len(cards_order)]
    for card_name, value in zip(cards_order, relevant_counts):
        count_mapping[card_name] = int(value)

    pdf_path = generate_pdf(game, count_mapping, OUTPUT_DIR)
    return str(pdf_path)


metadata = _game_metadata()
game_names = [name for name, _ in metadata]


with gr.Blocks(title="Generador de Cartas") as demo:
    gr.Markdown("# Generador de cartas personalizadas")

    game_dropdown = gr.Dropdown(
        label="Selecciona un juego",
        choices=game_names,
        value=game_names[0] if game_names else None,
        interactive=bool(game_names),
    )

    reload_button = gr.Button("Recargar juegos", variant="secondary")
    bulk_number = gr.Number(
        label="Cantidad global",
        value=0,
        precision=0,
        minimum=0,
        maximum=10,
        interactive=True,
    )

    form_host = gr.Column()
    generate_button = gr.Button("Generar documento", interactive=False)
    output_file = gr.File(label="Documento generado")

    number_inputs: List[gr.Number] = []
    form_columns: Dict[str, gr.Column] = {}

    with form_host:
        for game_name, assets in metadata:
            visible = game_name == game_names[0] if game_names else False
            with gr.Column(visible=visible) as card_form:
                form_columns[game_name] = card_form
                for card in assets.front_cards:
                    gr.Markdown(f"### {card.name}")
                    with gr.Row():
                        gr.Image(
                            value=str(card.path),
                            height=160,
                            interactive=False,
                            show_label=False,
                        )
                        number = gr.Number(
                            label="Cantidad",
                            value=0,
                            precision=0,
                            minimum=0,
                            maximum=10,
                            interactive=True,
                        )
                        number_inputs.append(number)

    if game_names:
        generate_button.interactive = True

    def _on_game_change(selected: str):
        updates = []
        for name in form_columns:
            updates.append(gr.update(visible=(name == selected)))

        button_update = gr.Button.update(interactive=selected in form_columns)
        file_update = gr.File.update(value=None)
        return (*updates, button_update, file_update)

    game_dropdown.change(
        _on_game_change,
        inputs=game_dropdown,
        outputs=[*form_columns.values(), generate_button, output_file],
    )

    def _refresh_games():
        _initial_games.cache_clear()
        games = list_games(BASE_DIR)
        options = sorted(games.keys())
        if not options:
            return gr.update(choices=[], value=None, interactive=False)
        return gr.update(choices=options, value=options[0], interactive=True)

    reload_button.click(_refresh_games, outputs=game_dropdown)

    generate_button.click(
        generate_document,
        inputs=[game_dropdown, *number_inputs],
        outputs=output_file,
    )

    if number_inputs:
        def _apply_global_quantity(value: float):
            clamped = max(0, min(10, int(value)))
            return tuple(gr.update(value=clamped) for _ in number_inputs)

        bulk_number.change(
            _apply_global_quantity,
            inputs=bulk_number,
            outputs=number_inputs,
        )


if __name__ == "__main__":
    demo.launch(server_port=8005, server_name="0.0.0.0")
