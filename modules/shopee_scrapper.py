import streamlit as st

import pandas as pd
import logging
from datetime import datetime

from modules.token_pool import get_active_token, run_scrape, render_token_pool

# Configurations
##########################################################################################

ACTOR_ID    = 'cZrxaxPbcqHwGwSlm'
DEFAULT_MAX = 20

logger = logging.getLogger(__name__)

MODE_OPTIONS = {
    "keyword":  "Search by Keyword",
    "url":      "Product / Shop URL",
    "shopId":   "Shop ID",
    "itemId":   "Item ID",
    "category": "Category URL",
    "shop":     "Shop Username",
}

SORT_OPTIONS = {
    "relevancy":  "Relevance",
    "sales":      "Top Sales",
    "newest":     "Newest",
    "price_asc":  "Price (Low → High)",
    "price_desc": "Price (High → Low)",
}

COUNTRY_OPTIONS = {
    "Indonesia (ID)":   "id",
    "Singapore (SG)":   "sg",
    "Malaysia (MY)":    "my",
    "Thailand (TH)":    "th",
    "Vietnam (VN)":     "vn",
    "Philippines (PH)": "ph",
    "Taiwan (TW)":      "tw",
    "Brazil (BR)":      "br",
    "Mexico (MX)":      "mx",
    "Colombia (CO)":    "co",
    "Chile (CL)":       "cl",
}

LABEL_MAP = {
    "keyword":  "Keyword",
    "url":      "Product or Shop URL",
    "shopId":   "Shop ID",
    "itemId":   "Item ID",
    "category": "Category URL",
    "shop":     "Shop Username / Slug",
}

PLACEHOLDER_MAP = {
    "keyword":  "samsung galaxy s24\nnike air max",
    "url":      "https://shopee.sg/product-name-i.123456.789012",
    "shopId":   "123456",
    "itemId":   "789012",
    "category": "https://shopee.sg/Handphone-Tablet-cat.11013548",
    "shop":     "samsung_official",
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

def scrapper_shopee():
    if 'pg_step' not in st.session_state:
        st.session_state['pg_step'] = 1

    render_token_pool('shopee')

    col1, col2, col3 = st.columns(3)
    with col1:
        mode = st.selectbox(
            "Scrape Mode",
            list(MODE_OPTIONS.keys()),
            format_func=lambda k: MODE_OPTIONS[k],
            key='sp_sel_mode',
        )
    with col2:
        country_label = st.selectbox(
            "Country",
            list(COUNTRY_OPTIONS.keys()),
            key='sp_sel_country',
        )
    with col3:
        sort = st.selectbox(
            "Sort By",
            list(SORT_OPTIONS.keys()),
            format_func=lambda k: SORT_OPTIONS[k],
            key='sp_sel_sort',
        )

    # Optional Filters
    min_price = 0
    max_price = 0

    with st.expander("Optional Filters", expanded=False):
        col_min, col_max = st.columns(2)
        with col_min:
            min_price = st.number_input(
                "Min Price",
                min_value=0,
                value=0,
                step=1000,
                help="Minimum product price. 0 = no minimum.",
                key='sp_opt_min_price',
            )
        with col_max:
            max_price = st.number_input(
                "Max Price",
                min_value=0,
                value=0,
                step=1000,
                help="Maximum product price. 0 = no maximum.",
                key='sp_opt_max_price',
            )

    # Form
    with st.form(key='shopee_form'):
        search_input = st.text_area(
            LABEL_MAP[mode],
            height=100,
            placeholder=PLACEHOLDER_MAP[mode],
        )

        max_products = st.number_input(
            "Max Products",
            min_value=1,
            max_value=500,
            value=DEFAULT_MAX,
            step=10,
        )

        c1, c2 = st.columns([1, 1])
        with c1: search_but  = st.form_submit_button("Scrape Data", width='stretch')
        with c2: example_but = st.form_submit_button("Show Example", width='stretch')

        if search_but:
            st.session_state.update({
                'pg_step':           2,
                'scrape_pending':    True,
                'scrape_results':    None,
                'scrape_error':      None,
                'sp_mode':           mode,
                'sp_search_input':   search_input.strip(),
                'sp_country':        COUNTRY_OPTIONS[country_label],
                'sp_country_label':  country_label,
                'sp_sort':           sort,
                'sp_min_price':      int(min_price),
                'sp_max_price':      int(max_price),
                'sp_max_products':   int(max_products),
            })
        if example_but:
            st.session_state['pg_step'] = 4

    # Results
    if st.session_state['pg_step'] == 2:
        if st.session_state.get('scrape_pending', False):
            st.session_state['scrape_pending'] = False
            search_input = st.session_state.get('sp_search_input', '').strip()

            if not search_input:
                st.warning("Input is empty. Please enter a value.")
            elif not get_active_token():
                st.session_state.update({
                    'scrape_results': None,
                    'scrape_error':   "No Apify token available. Load a token file in the panel above.",
                })
            else:
                sp_mode      = st.session_state.get('sp_mode', 'keyword')
                country      = st.session_state.get('sp_country', 'sg')
                sort         = st.session_state.get('sp_sort', 'relevancy')
                min_price    = st.session_state.get('sp_min_price', 0)
                max_price    = st.session_state.get('sp_max_price', 0)
                max_products = st.session_state.get('sp_max_products', DEFAULT_MAX)

                actor_input = {
                    'mode':        sp_mode,
                    'country':     country,
                    'sort':        sort,
                    'maxProducts': max_products,
                    sp_mode:       search_input,
                }
                if min_price:
                    actor_input['minPrice'] = min_price
                if max_price:
                    actor_input['maxPrice'] = max_price

                hint = "Try different keywords, check the country setting, or verify your Apify plan."
                with st.spinner("Running Apify Shopee scrape... (typically 30 – 120 s)"):
                    items, err = run_scrape(ACTOR_ID, actor_input, hint)
                st.session_state.update({'scrape_results': items, 'scrape_error': err})

        items         = st.session_state.get('scrape_results')
        err           = st.session_state.get('scrape_error')
        sp_mode       = st.session_state.get('sp_mode', 'keyword')
        country_label = st.session_state.get('sp_country_label', '')
        sort          = st.session_state.get('sp_sort', 'relevancy')
        country       = st.session_state.get('sp_country', 'sg')

        if err:
            st.error(f"Error: {err}")
            return
        if items is None:
            return

        st.write(
            f"**{MODE_OPTIONS[sp_mode]}** in **{country_label}** "
            f"sorted by **{SORT_OPTIONS.get(sort, sort)}** — **{len(items)}** items"
        )
        st.divider()

        st.success(f"Scraped **{len(items)}** item(s) successfully!")

        df = items_to_dataframe(items)

        image_cols   = [c for c in df.columns if 'image' in c.lower() or 'img' in c.lower() or 'photo' in c.lower()]
        display_cols = [c for c in df.columns if c not in image_cols]
        st.dataframe(df[display_cols], width='stretch')

        if image_cols:
            with st.expander(f"Images ({len(df)} products, columns: {', '.join(image_cols)})"):
                for i, row in df.iterrows():
                    name = str(row.get('name') or row.get('title') or f"Item {i + 1}")
                    st.caption(f"**{name[:80]}**")
                    for col in image_cols:
                        val = row.get(col)
                        if val and str(val) not in ('None', 'nan', ''):
                            st.write(f"`{col}`: {str(val).strip()}")
                    st.divider()

        with st.expander("JSON Response"):
            st.json(items)

        csv = df.to_csv(index=False, sep=';')
        st.download_button(
            label=f"Download CSV ({len(df)} rows)",
            data=csv,
            file_name=f"shopee_{sp_mode}_{country}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            width='stretch',
        )

    # Example
    if st.session_state['pg_step'] == 4:
        st.subheader("Example Inputs per Mode")
        st.dataframe(pd.DataFrame({
            "Mode":          list(MODE_OPTIONS.values()),
            "Payload Key":   list(MODE_OPTIONS.keys()),
            "Example Input": [
                "samsung galaxy s24",
                "https://shopee.sg/product-i.123456.789012",
                "123456",
                "789012",
                "https://shopee.sg/Handphone-Tablet-cat.11013548",
                "samsung_official",
            ],
        }), width='stretch')
