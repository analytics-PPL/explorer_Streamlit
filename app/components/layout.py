from __future__ import annotations

from base64 import b64encode
from collections.abc import Callable
from html import escape
from pathlib import Path
import random
import re

import streamlit as st

from app.components.selection import (
    BOROUGH_FILTER_KEY,
    INDICATOR_KEY,
    MAP_MODE_KEY,
    PERIOD_KEY,
    SOURCE_FILTER_KEY,
    TOPIC_KEY,
    init_state,
    set_selected_ids,
)
from neighbourhood_explorer.data_access import available_periods, latest_period


APP_TITLE = "London Neighbourhood Public Data Explorer"
PPL_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logos" / "PPL Logo_RGB.png"
LOADING_CAROUSEL_WORDS = (
    "Accomplishing", "Actioning", "Actualizing", "Architecting", "Baking",
    "Beaming", "Beboppin'", "Befuddling", "Billowing", "Blanching",
    "Bloviating", "Boogieing", "Boondoggling", "Booping", "Bootstrapping",
    "Brewing", "Burrowing", "Calculating", "Canoodling", "Caramelizing",
    "Cascading", "Catapulting", "Cerebrating", "Channelling", "Choreographing",
    "Churning", "Clauding", "Coalescing", "Cogitating", "Combobulating",
    "Composing", "Computing", "Concocting", "Considering", "Contemplating",
    "Cooking", "Crafting", "Creating", "Crystallizing", "Cultivating",
    "Crunching", "Deciphering", "Deliberating", "Determining", "Dilly-dallying",
    "Discombobulating", "Doing", "Doodling", "Drizzling", "Ebbing",
    "Effecting", "Elucidating", "Embellishing", "Enchanting", "Envisioning",
    "Evaporating", "Fermenting", "Fiddle-faddling", "Finagling", "Flambéing",
    "Flibbertigibbeting", "Flowing", "Flummoxing", "Fluttering", "Forging",
    "Forming", "Frosting", "Frolicking", "Gallivanting", "Galloping",
    "Garnishing", "Generating", "Germinating", "Gitifying", "Grooving",
    "Gusting", "Harmonizing", "Hashing", "Hatching", "Herding",
    "Hibernating", "Honking", "Hullaballooing", "Hyperspacing", "Ideating",
    "Imagining", "Improvising", "Incubating", "Inferring", "Infusing",
    "Ionizing", "Jitterbugging", "Julienning", "Kneading", "Leavening",
    "Levitating", "Lollygagging", "Manifesting", "Marinating", "Meandering",
    "Metamorphosing", "Misting", "Moonwalking", "Moseying", "Mulling",
    "Mustering", "Musing", "Nebulizing", "Nesting", "Noodling",
    "Nucleating", "Orbiting", "Orchestrating", "Osmosing", "Perambulating",
    "Percolating", "Perusing", "Philosophising", "Photosynthesizing", "Pollinating",
    "Pontificating", "Pondering", "Pouncing", "Precipitating", "Prestidigitating",
    "Processing", "Proofing", "Propagating", "Puttering", "Puzzling",
    "Quantumizing", "Razzle-dazzling", "Razzmatazzing", "Recombobulating", "Reticulating",
    "Roosting", "Ruminating", "Sautéing", "Scampering", "Scheming",
    "Schlepping", "Scurrying", "Seasoning", "Shenaniganing", "Shimmying",
    "Simmering", "Skedaddling", "Sketching", "Slithering", "Smooshing",
    "Sock-hopping", "Spelunking", "Spinning", "Sprouting", "Stewing",
    "Sublimating", "Sussing", "Swirling", "Swooping", "Symbioting",
    "Synthesizing", "Tempering", "Thinking", "Thundering", "Tinkering",
    "Tomfoolering", "Topsy-turvying", "Transfiguring", "Transmuting", "Twisting",
    "Undulating", "Unfurling", "Unravelling", "Vibing", "Waddling",
    "Wandering", "Warping", "Whatchamacalliting", "Whirlpooling", "Whirring",
    "Whisking", "Wibbling", "Working", "Wrangling", "Zesting", "Zigzagging",
)
POWERPOINT_CAROUSEL_WORDS = LOADING_CAROUSEL_WORDS


def set_page(title: str) -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="collapsed")


def _logo_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    suffix = path.suffix.lower().lstrip(".") or "png"
    payload = b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{suffix};base64,{payload}"


def _load_theme_css() -> str:
    css_path = Path(__file__).resolve().parents[2] / "assets" / "css" / "theme.css"
    return css_path.read_text(encoding="utf-8")


def inject_theme() -> None:
    st.markdown(f"<style>{_load_theme_css()}</style>", unsafe_allow_html=True)


def render_empty_state(message: str, icon: str = "📊") -> None:
    st.markdown(
        (
            "<div class='empty-state-card'>"
            f"<div class='empty-state-icon'>{escape(str(icon))}</div>"
            f"<div class='empty-state-text'>{escape(str(message))}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _safe_dom_token(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value).strip()).strip("-") or "default"


def _loading_overlay_dom_id(overlay_key: str) -> str:
    return f"app-loading-overlay-{_safe_dom_token(overlay_key)}"


def _loading_button_dom_id(button_key: str) -> str:
    return f"app-loading-button-{_safe_dom_token(button_key)}"


def _loading_word_sequence(words: tuple[str, ...] = LOADING_CAROUSEL_WORDS, count: int = 10) -> list[str]:
    cleaned_words = [word.strip() for word in words if str(word).strip()]
    unique_words = list(dict.fromkeys(cleaned_words))
    if not unique_words or count <= 0:
        return []
    if len(unique_words) == 1:
        return unique_words * count

    chooser = random.SystemRandom()
    sequence: list[str] = []
    while len(sequence) < count:
        options = [word for word in unique_words if not sequence or word != sequence[-1]]
        sequence.append(chooser.choice(options))
    return sequence


def _loading_word_animation_css(overlay_id: str, word_count: int, total_duration: float) -> str:
    if word_count <= 0 or total_duration <= 0:
        return ""

    safe_overlay = _safe_dom_token(overlay_id)
    keyframes: list[str] = []
    rules: list[str] = []
    segment = 100 / word_count

    for index in range(word_count):
        name = f"appLoadingWordCarousel-{safe_overlay}-{index}"
        segment_start = segment * index
        fade_in_end = segment_start + segment * 0.28
        visible_end = segment_start + segment * 0.56
        fade_out_end = segment_start + segment * 0.76
        keyframes.append(
            "\n".join(
                [
                    f"@keyframes {name} {{",
                    f"  0%, {segment_start:.4f}% {{ opacity: 0; transform: translateY(16px) scale(0.98); }}",
                    f"  {fade_in_end:.4f}% {{ opacity: 1; transform: translateY(0) scale(1); }}",
                    f"  {visible_end:.4f}% {{ opacity: 1; transform: translateY(0) scale(1); }}",
                    f"  {fade_out_end:.4f}%, 100% {{ opacity: 0; transform: translateY(-14px) scale(1.02); }}",
                    "}",
                ]
            )
        )
        rules.append(
            (
                f"#{overlay_id} .app-loading-word--{index} {{ "
                f"animation-name: {name}; animation-duration: {total_duration:.2f}s; }}"
            )
        )

    return "<style>" + "".join(keyframes + rules) + "</style>"


def render_loading_overlay(
    *,
    overlay_key: str,
    title: str,
    caption: str = "",
    words: tuple[str, ...] = LOADING_CAROUSEL_WORDS,
) -> None:
    overlay_id = _loading_overlay_dom_id(overlay_key)
    carousel_words = _loading_word_sequence(words=words, count=min(max(len(words), 8), 14))
    if not carousel_words:
        carousel_words = ["loading"]
    step_seconds = 1.2
    total_duration = step_seconds * len(carousel_words)
    animation_css = _loading_word_animation_css(overlay_id, len(carousel_words), total_duration)
    word_markup = "".join(
        (
            f"<span class='app-loading-word app-loading-word--{index}'>"
            f"{escape(word)}</span>"
        )
        for index, word in enumerate(carousel_words)
    )
    caption_markup = (
        f"<div class='app-loading-caption'>{escape(caption)}</div>"
        if caption.strip()
        else ""
    )
    st.markdown(
        (
            f"{animation_css}"
            f"<div id='{overlay_id}' class='app-loading-overlay' aria-live='polite' aria-busy='true'>"
            "<div class='app-loading-shell'>"
            "<div class='app-loading-mark' aria-hidden='true'></div>"
            f"<div class='app-loading-title'>{escape(title)}</div>"
            f"{caption_markup}"
            f"<div class='app-loading-carousel'>{word_markup}</div>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_loading_button(
    *,
    button_key: str,
    prefix: str = "Preparing",
    words: tuple[str, ...] = POWERPOINT_CAROUSEL_WORDS,
) -> None:
    button_id = _loading_button_dom_id(button_key)
    carousel_words = _loading_word_sequence(words=words, count=min(max(len(words), 6), 10))
    if not carousel_words:
        carousel_words = ["loading"]
    step_seconds = 1.05
    total_duration = step_seconds * len(carousel_words)
    animation_css = _loading_word_animation_css(button_id, len(carousel_words), total_duration)
    word_markup = "".join(
        f"<span class='app-loading-word app-loading-word--{index}'>{escape(word)}</span>"
        for index, word in enumerate(carousel_words)
    )
    st.markdown(
        (
            f"{animation_css}"
            f"<div id='{button_id}' class='app-loading-button-shell' aria-live='polite' aria-busy='true'>"
            f"<span class='app-loading-button-prefix'>{escape(prefix)}</span>"
            "<span aria-hidden='true'>&middot;</span>"
            f"<span class='app-loading-button-word-wrap'>{word_markup}</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def dismiss_loading_overlay(*, overlay_key: str) -> None:
    overlay_id = _loading_overlay_dom_id(overlay_key)
    st.markdown(
        (
            "<style>"
            f"#{overlay_id} {{"
            "opacity: 0 !important;"
            "visibility: hidden !important;"
            "pointer-events: none !important;"
            "transition: opacity 260ms ease, visibility 0s linear 260ms !important;"
            "}"
            "</style>"
        ),
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str, action_renderer: Callable[[], None] | None = None) -> None:
    if action_renderer is None:
        logo_col, spacer_col = st.columns([0.22, 0.78], gap="medium")
        action_col = None
    else:
        logo_col, spacer_col, action_col = st.columns([0.2, 0.52, 0.28], gap="medium")
    logo_uri = _logo_data_uri(PPL_LOGO_PATH)
    with logo_col:
        if logo_uri:
            st.markdown(
                (
                    "<div class='app-logo-wrap'>"
                    f"<a class='app-logo-link' href='https://ppl.org.uk' target='_blank' rel='noopener noreferrer'>"
                    f"<img class='app-logo' src='{logo_uri}' alt='PPL logo' />"
                    "</a>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
    with spacer_col:
        st.markdown("&nbsp;", unsafe_allow_html=True)
    if action_col is not None:
        with action_col:
            with st.container(border=True):
                action_renderer()
    st.markdown("<div class='app-header-wrap'>", unsafe_allow_html=True)
    st.title(APP_TITLE)
    if title and title != APP_TITLE:
        st.subheader(title)
    if subtitle:
        st.markdown(f"<div class='app-subtitle'>{subtitle}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def sidebar_controls(reference_df, catalog_df, page_default_topic: str | None = None) -> dict[str, object]:
    topic_options = ["All"] + sorted(catalog_df["topic"].dropna().unique().tolist())
    default_indicator_id = catalog_df.iloc[0]["indicator_id"]
    default_period = latest_period(str(default_indicator_id))
    init_state(
        default_indicator_id=str(default_indicator_id),
        default_period=str(default_period) if default_period else None,
        default_topic=page_default_topic or "All",
    )

    with st.sidebar:
        st.header("Explorer controls")
        st.radio("Map mode", ["Real map", "Hex map", "Both maps"], key=MAP_MODE_KEY, horizontal=True)

        boroughs = sorted(
            {
                item.strip()
                for raw_value in reference_df["borough_name"].dropna().astype(str)
                for item in raw_value.split(";")
                if item.strip()
            }
        )
        st.multiselect("Borough filter", boroughs, key=BOROUGH_FILTER_KEY)

        source_options = ["All"] + sorted(catalog_df["source_name"].dropna().unique().tolist())
        st.selectbox("Source filter", source_options, key=SOURCE_FILTER_KEY)

        topic_index = topic_options.index(page_default_topic) if page_default_topic in topic_options else 0
        st.selectbox("Topic filter", topic_options, key=TOPIC_KEY, index=topic_index)

        filtered_catalog = catalog_df.copy()
        if st.session_state[TOPIC_KEY] != "All":
            filtered_catalog = filtered_catalog[filtered_catalog["topic"] == st.session_state[TOPIC_KEY]].copy()
        if st.session_state[SOURCE_FILTER_KEY] != "All":
            filtered_catalog = filtered_catalog[filtered_catalog["source_name"] == st.session_state[SOURCE_FILTER_KEY]].copy()
        filtered_catalog = filtered_catalog.sort_values("title")
        if filtered_catalog.empty:
            filtered_catalog = catalog_df.sort_values("title")

        indicator_options = filtered_catalog["indicator_id"].tolist()
        indicator_titles = {row["indicator_id"]: row["title"] for _, row in filtered_catalog.iterrows()}
        current_indicator = st.session_state.get(INDICATOR_KEY, indicator_options[0])
        if current_indicator not in indicator_options:
            current_indicator = indicator_options[0]
            st.session_state[INDICATOR_KEY] = current_indicator
        chosen_indicator = st.selectbox(
            "Indicator",
            indicator_options,
            index=indicator_options.index(current_indicator),
            format_func=lambda value: indicator_titles.get(value, value),
            key=INDICATOR_KEY,
        )

        period_options = available_periods(str(chosen_indicator))
        if not period_options:
            period_options = [""]
        current_period = st.session_state.get(PERIOD_KEY, period_options[-1])
        if current_period not in period_options:
            current_period = period_options[-1]
            st.session_state[PERIOD_KEY] = current_period
        st.selectbox("Year / period", period_options, index=period_options.index(current_period), key=PERIOD_KEY)

        selection_options = reference_df.sort_values(["borough_name", "neighbourhood_name"]).copy()
        option_lookup = {
            f"{row.neighbourhood_name} ({row.borough_name})": str(row.neighbourhood_id) for row in selection_options.itertuples(index=False)
        }
        current_ids = {str(value) for value in st.session_state.get("selected_neighbourhood_ids", [])}
        current_labels = [label for label, value in option_lookup.items() if value in current_ids]
        chosen_labels = st.multiselect(
            "Neighbourhood search",
            options=list(option_lookup.keys()),
            default=current_labels,
            help="Search and select one or more neighbourhoods.",
        )
        set_selected_ids([option_lookup[label] for label in chosen_labels])

    return {
        "indicator_id": st.session_state[INDICATOR_KEY],
        "period": st.session_state[PERIOD_KEY],
        "map_mode": st.session_state[MAP_MODE_KEY],
        "topic_filter": st.session_state[TOPIC_KEY],
        "borough_filter": st.session_state[BOROUGH_FILTER_KEY],
        "source_filter": st.session_state[SOURCE_FILTER_KEY],
    }
