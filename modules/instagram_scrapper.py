import streamlit as st

import pandas as pd
import logging
from datetime import datetime

from modules.token_pool import get_active_token, run_scrape, render_token_pool

# Configurations
##########################################################################################

ACTOR_ID      = 'shu8hvrXbJbY3Eb9W'
DEFAULT_LIMIT = 20

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

# Output helpers
##########################################################################################

def flatten_item(item: dict) -> dict:
    row = {}
    for k, v in item.items():
        if isinstance(v, list):
            if not v:
                row[k] = None
            elif all(isinstance(x, (str, int, float, bool)) for x in v):
                row[k] = ', '.join(str(x) for x in v)
            else:
                row[k] = f"[{len(v)} items]"
        elif isinstance(v, dict):
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
    return pd.DataFrame([flatten_item(item) for item in items])

# User Interface
##########################################################################################

def scrapper_instagram():
    if 'ig_pg_step' not in st.session_state:
        st.session_state['ig_pg_step'] = 1

    render_token_pool('instagram')

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

    # Optional Filters
    newer_than = ''

    with st.expander("Optional Filters", expanded=False):
        newer_than = st.text_input(
            "Only posts after (optional)",
            placeholder="2024-01-01  or  7 days  or  2 months",
            help="Accepted: YYYY-MM-DD, ISO 8601, or relative like '7 days', '3 months'",
            key='ig_opt_newer_than',
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
                    'hashtag': "#travel  or  travel",
                    'user':    "natgeo",
                    'place':   "Bali",
                }.get(search_type, ""),
            )

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
        if st.session_state.get('ig_scrape_pending', False):
            st.session_state['ig_scrape_pending'] = False
            search_input = st.session_state.get('ig_search_input', '').strip()

            if not search_input:
                st.warning("Input is empty. Please enter a URL or search query.")
            elif not get_active_token():
                st.session_state.update({
                    'ig_scrape_results': None,
                    'ig_scrape_error':   "No Apify token available. Load a token file in the panel above.",
                })
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

                hint = "Check your input URL/search term, or ensure the account/hashtag is public."
                with st.spinner("Running Apify scrape... (typically 30 – 120 s)"):
                    items, err = run_scrape(ACTOR_ID, actor_input, hint)
                st.session_state.update({'ig_scrape_results': items, 'ig_scrape_error': err})

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

        media_cols   = [c for c in df.columns if c in ('displayUrl', 'videoUrl', 'images', 'thumbnailUrl', 'previewUrl')]
        display_cols = [c for c in df.columns if c not in media_cols]
        st.dataframe(df[display_cols], width='stretch')

        if media_cols:
            with st.expander(f"Media URLs ({len(df)} items, columns: {', '.join(media_cols)})"):
                for i, row in df.iterrows():
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

        with st.expander("JSON Response"):
            st.json(items)

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
