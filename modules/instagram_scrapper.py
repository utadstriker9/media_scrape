import streamlit as st

import os
import requests as req
import pandas as pd
import time
import logging
from datetime import datetime

# Configurations
##########################################################################################

ACTOR_ID        = 'shu8hvrXbJbY3Eb9W'
APIFY_BASE      = 'https://api.apify.com/v2'
DEFAULT_LIMIT   = 20
EXHAUSTED_CODES = {401, 402, 429}

logger = logging.getLogger(__name__)

RESULTS_TYPE_OPTIONS = {
    "posts":    "Posts",
    "reels":    "Reels",
    "comments": "Comments",
    "details":  "Profile Details",
    "mentions": "Mentions",
    "stories":  "Stories",
}

SEARCH_TYPE_OPTIONS = {
    "hashtag": "Hashtag",
    "user":    "User / Profile",
    "place":   "Place / Location",
}

INPUT_MODE_OPTIONS = {
    "directUrls": "Direct URLs",
    "search":     "Search",
}

# Helpers
##########################################################################################

def load_tokens(filepath: str) -> list:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error("Failed to load tokens from %s: %s", filepath, e)
        return []

def init_token_pool(filepath: str):
    tokens = load_tokens(filepath)
    st.session_state['token_pool']  = tokens
    st.session_state['token_index'] = 0
    st.session_state['token_file']  = filepath

def get_active_token() -> str:
    pool  = st.session_state.get('token_pool', [])
    index = st.session_state.get('token_index', 0)
    if not pool or index >= len(pool):
        return os.environ.get('APIFY_TOKEN', '')
    return pool[index]

def rotate_token() -> bool:
    next_index = st.session_state.get('token_index', 0) + 1
    st.session_state['token_index'] = next_index
    pool = st.session_state.get('token_pool', [])
    return next_index < len(pool)

# API
##########################################################################################

def start_actor_run(actor_input: dict, token: str):
    url = f'{APIFY_BASE}/acts/{ACTOR_ID}/runs'
    try:
        resp = req.post(
            url,
            params={'token': token, 'maxTotalChargeUsd': 1.0},
            json=actor_input,
            timeout=60,
        )
        if resp.status_code in EXHAUSTED_CODES:
            return None, '__EXHAUSTED__'
        if resp.status_code == 400:
            try:
                msg = resp.json().get('error', {}).get('message', resp.text)
            except Exception:
                msg = resp.text
            return None, f"Invalid actor input: {msg}"
        if resp.status_code == 404:
            return None, f"Actor '{ACTOR_ID}' not found — check your access."
        resp.raise_for_status()
        run_id = resp.json().get('data', {}).get('id')
        return run_id, None
    except req.exceptions.ConnectionError:
        return None, "Cannot reach Apify API — check your internet connection."
    except req.exceptions.Timeout:
        return None, "Apify start-run request timed out."
    except Exception as e:
        return None, str(e)

def poll_run(run_id: str, token: str, timeout: int = 360, interval: int = 3):
    url      = f'{APIFY_BASE}/actor-runs/{run_id}'
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = req.get(url, params={'token': token}, timeout=15)
            resp.raise_for_status()
            data   = resp.json().get('data', {})
            status = data.get('status', '')
            if status in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'):
                return status, data.get('defaultDatasetId'), None
            time.sleep(interval)
        except Exception as e:
            return None, None, str(e)
    return None, None, f"Polling timed out after {timeout}s — run {run_id} may still be running on Apify."

def fetch_dataset(dataset_id: str, token: str):
    url = f'{APIFY_BASE}/datasets/{dataset_id}/items'
    try:
        resp = req.get(url, params={'token': token, 'format': 'json'}, timeout=30)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as e:
        return None, str(e)

def run_scrape(actor_input: dict):
    pool     = st.session_state.get('token_pool', [])
    attempts = max(len(pool), 1)

    for attempt in range(attempts):
        token = get_active_token()
        if not token:
            return None, "No Apify token available. Load a token file in the panel above."

        run_id, err = start_actor_run(actor_input, token)

        if err == '__EXHAUSTED__':
            has_next = rotate_token()
            st.warning(
                f"Token #{attempt + 1} rate-limited (401/402/429) — "
                + ("switching to next token..." if has_next else "no more tokens available.")
            )
            if not has_next:
                return None, "All Apify tokens are exhausted."
            continue

        if err:
            return None, err

        poll_placeholder = st.empty()
        poll_placeholder.info(f"Actor run started (ID: `{run_id}`) — waiting for results...")

        status, dataset_id, err = poll_run(run_id, token)
        poll_placeholder.empty()

        if err:
            return None, err
        if status != 'SUCCEEDED':
            return None, f"Actor run finished with status: **{status}**. Check your Apify console for details."

        items, err = fetch_dataset(dataset_id, token)
        if err:
            return None, err
        if not items:
            return None, (
                "Actor succeeded but returned 0 items. "
                "Check your input URL/search term, or ensure the account/hashtag is public."
            )

        return items, None

    return None, "All Apify tokens failed."

# Output
##########################################################################################

def _flatten_item(item: dict) -> dict:
    """Flatten one JSON item into a plain dict, handling nested lists and dicts."""
    row = {}
    for k, v in item.items():
        if isinstance(v, list):
            if not v:
                row[k] = None
            elif all(isinstance(x, (str, int, float, bool)) for x in v):
                row[k] = ', '.join(str(x) for x in v)
            else:
                # list of dicts (e.g. latestComments, taggedUsers) — store count
                row[k] = f"[{len(v)} items]"
        elif isinstance(v, dict):
            # flatten one level: musicInfo_song_name, owner_username, etc.
            for dk, dv in v.items():
                if not isinstance(dv, (dict, list)):
                    row[f"{k}_{dk}"] = dv
        elif isinstance(v, str) and len(v) > 500:
            row[k] = v[:500] + '...'
        else:
            row[k] = v
    return row


def items_to_dataframe(items: list) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    return pd.DataFrame([_flatten_item(item) for item in items])

# User Interfaces
##########################################################################################

def scrapper_instagram():

    if 'ig_pg_step' not in st.session_state:
        st.session_state['ig_pg_step'] = 1

    # Token pool panel
    pool  = st.session_state.get('token_pool', [])
    index = st.session_state.get('token_index', 0)

    with st.expander("Apify Token Pool", expanded=not get_active_token()):
        if os.environ.get('APIFY_TOKEN'):
            st.success("Token loaded from environment variable `APIFY_TOKEN`.")
        else:
            default_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'credentials', 'apify_token.txt',
            )
            token_file = st.text_input(
                "Path to token file (one token per line)",
                value=st.session_state.get('token_file', default_path),
                key='ig_token_file_input',
            )
            col_load, col_reset = st.columns(2)
            with col_load:
                if st.button("Load / Reload Tokens", key='ig_btn_load'):
                    if token_file:
                        init_token_pool(token_file)
                        st.rerun()
            with col_reset:
                if pool and st.button("Reset to Token #1", key='ig_btn_reset'):
                    st.session_state['token_index'] = 0
                    st.rerun()

            if token_file and st.session_state.get('token_file') != token_file:
                init_token_pool(token_file)

            pool  = st.session_state.get('token_pool', [])
            index = st.session_state.get('token_index', 0)
            if pool:
                remaining = len(pool) - index
                st.success(
                    f"{len(pool)} token(s) loaded "
                    f"— Active: **#{index + 1}** of {len(pool)} "
                    f"({remaining} remaining)"
                )
            else:
                st.warning("No tokens loaded. Add a `.txt` file with tokens (one per line) then click Load.")

    # Selectors outside form (rerender on change)
    col1, col2, col3 = st.columns(3)
    with col1:
        input_mode = st.selectbox(
            "Input Mode",
            list(INPUT_MODE_OPTIONS.keys()),
            format_func=lambda k: INPUT_MODE_OPTIONS[k],
            key='ig_sel_input_mode',
        )
    with col2:
        results_type = st.selectbox(
            "Results Type",
            list(RESULTS_TYPE_OPTIONS.keys()),
            format_func=lambda k: RESULTS_TYPE_OPTIONS[k],
            key='ig_sel_results_type',
            disabled=(input_mode == 'search'),
        )
    with col3:
        if input_mode == 'search':
            search_type = st.selectbox(
                "Search Type",
                list(SEARCH_TYPE_OPTIONS.keys()),
                format_func=lambda k: SEARCH_TYPE_OPTIONS[k],
                key='ig_sel_search_type',
            )
        else:
            search_type = 'hashtag'
            st.selectbox(
                "Search Type",
                list(SEARCH_TYPE_OPTIONS.keys()),
                format_func=lambda k: SEARCH_TYPE_OPTIONS[k],
                key='ig_sel_search_type_disabled',
                disabled=True,
            )

    # Form
    with st.form(key='instagram_form'):
        if input_mode == 'directUrls':
            search_input = st.text_area(
                "Direct URLs (one per line)",
                height=120,
                placeholder=(
                    "https://www.instagram.com/natgeo/\n"
                    "https://www.instagram.com/p/ABC123xyz/\n"
                    "https://www.instagram.com/reel/DEF456uvw/"
                ),
            )
        else:
            search_input = st.text_area(
                "Search Query",
                height=80,
                placeholder={
                    'hashtag': "#travel  or  travel  (# is optional)",
                    'user':    "natgeo",
                    'place':   "Bali",
                }.get(search_type, ""),
            )

        col_date, col_limit = st.columns(2)
        with col_date:
            newer_than = st.text_input(
                "Only posts after (optional)",
                placeholder="2024-01-01  or  7 days  or  2 months",
                help="Accepted: YYYY-MM-DD, ISO 8601, or relative like '7 days', '3 months'",
            )
        with col_limit:
            results_limit = st.number_input(
                "Max results",
                min_value=1,
                max_value=500,
                value=DEFAULT_LIMIT,
                step=10,
            )

        c1, c2 = st.columns([1, 1])
        with c1: search_but  = st.form_submit_button("Scrape Data", width='stretch')
        with c2: example_but = st.form_submit_button("Show Example", width='stretch')

        if search_but:
            st.session_state.update({
                'ig_pg_step':        2,
                'ig_scrape_pending': True,
                'ig_scrape_results': None,
                'ig_scrape_error':   None,
                'ig_input_mode':     input_mode,
                'ig_results_type':   results_type,
                'ig_search_type':    search_type,
                'ig_search_input':   search_input.strip(),
                'ig_newer_than':     newer_than.strip(),
                'ig_limit':          int(results_limit),
            })
        if example_but:
            st.session_state['ig_pg_step'] = 4

    # Results
    if st.session_state['ig_pg_step'] == 2:
        # Only call the API when the button was just clicked
        if st.session_state.get('ig_scrape_pending', False):
            st.session_state['ig_scrape_pending'] = False
            search_input = st.session_state.get('ig_search_input', '').strip()

            if not search_input:
                st.warning("Input is empty. Please enter a URL or search query.")
            elif not get_active_token():
                st.session_state.update({'ig_scrape_results': None, 'ig_scrape_error': "No Apify token available. Load a token file in the panel above."})
            else:
                input_mode   = st.session_state.get('ig_input_mode', 'directUrls')
                results_type = st.session_state.get('ig_results_type', 'posts')
                search_type  = st.session_state.get('ig_search_type', 'hashtag')
                newer_than   = st.session_state.get('ig_newer_than', '').strip()
                limit        = st.session_state.get('ig_limit', DEFAULT_LIMIT)

                actor_input = {'resultsType': results_type, 'resultsLimit': limit}
                if input_mode == 'directUrls':
                    actor_input['directUrls'] = [u.strip() for u in search_input.splitlines() if u.strip()]
                else:
                    query = search_input.lstrip('#') if search_type == 'hashtag' else search_input
                    actor_input['search']      = query
                    actor_input['searchType']  = search_type
                    actor_input['searchLimit'] = limit
                if newer_than:
                    actor_input['onlyPostsNewerThan'] = newer_than

                with st.spinner("Running Apify scrape... (typically 30 – 120 s)"):
                    items, err = run_scrape(actor_input)
                st.session_state.update({'ig_scrape_results': items, 'ig_scrape_error': err})

        # Display stored results (no API call on rerender)
        items        = st.session_state.get('ig_scrape_results')
        err          = st.session_state.get('ig_scrape_error')
        input_mode   = st.session_state.get('ig_input_mode', 'directUrls')
        results_type = st.session_state.get('ig_results_type', 'posts')
        search_type  = st.session_state.get('ig_search_type', 'hashtag')
        newer_than   = st.session_state.get('ig_newer_than', '').strip()
        limit        = st.session_state.get('ig_limit', DEFAULT_LIMIT)

        if err:
            st.error(f"Error: {err}")
            return
        if items is None:
            return

        st.write(
            f"Scraped **{RESULTS_TYPE_OPTIONS[results_type]}** "
            f"via **{INPUT_MODE_OPTIONS[input_mode]}** "
            + (f"({SEARCH_TYPE_OPTIONS[search_type]})" if input_mode == 'search' else "")
            + f" — **{len(items)}** results"
        )
        if newer_than:
            st.caption(f"Filter: only posts after **{newer_than}**")
        st.divider()

        st.success(f"Scraped **{len(items)}** item(s) successfully!")

        df = items_to_dataframe(items)

        # Columns that contain media URLs — collect for the expander
        media_cols = [c for c in df.columns if c in ('displayUrl', 'videoUrl', 'images', 'thumbnailUrl', 'previewUrl')]
        # Hide media URL columns from main table (they are long and clutter the view)
        display_cols = [c for c in df.columns if c not in media_cols]
        st.dataframe(df[display_cols], width='stretch')

        # Media expander
        if media_cols:
            with st.expander(f"Media URLs ({len(df)} items, columns: {', '.join(media_cols)})"):
                for i, row in df.iterrows():
                    # Best available label: url > shortCode > index
                    def check_str(v):
                        return str(v) if v and str(v) not in ('None', 'nan', '') else None
                    label = check_str(row.get('url')) or check_str(row.get('shortCode')) or f"Item {i + 1}"
                    owner = check_str(row.get('ownerUsername'))
                    st.caption(f"**{f'@{owner}' if owner else label}** — {label}")
                    for col in media_cols:
                        val = row.get(col)
                        if val and str(val) not in ('None', 'nan', ''):
                            for url in str(val).split('\n'):
                                if url.strip():
                                    st.write(f"`{col}`: {url.strip()}")
                    st.divider()

        # Raw JSON
        with st.expander("Raw Apify JSON Response"):
            st.json(items)

        # CSV download
        csv = df.to_csv(index=False, sep=';')
        st.download_button(
            label=f"Download CSV ({len(df)} rows)",
            data=csv,
            file_name=f"instagram_{results_type}_{input_mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            width='stretch',
        )

    # Example
    if st.session_state['ig_pg_step'] == 4:
        st.subheader("Example Inputs")
        st.dataframe(pd.DataFrame({
            "Input Mode":   ["Direct URLs", "Direct URLs", "Direct URLs", "Search", "Search", "Search"],
            "Results Type": ["posts",        "comments",    "reels",       "posts",  "posts",  "posts"],
            "Example":      [
                "https://www.instagram.com/natgeo/",
                "https://www.instagram.com/p/ABC123xyz/",
                "https://www.instagram.com/reel/DEF456uvw/",
                "#travel  (hashtag search)",
                "natgeo  (user search)",
                "Bali  (place search)",
            ],
        }), width='stretch')
