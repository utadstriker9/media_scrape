import streamlit as st

import pandas as pd
import logging
from datetime import datetime, date

from modules.token_pool import get_active_token, run_scrape, render_token_pool

# Configurations
##########################################################################################

ACTOR_ID        = 'GdWCkxBtKWOsKjdch'
DEFAULT_RESULTS = 10

logger = logging.getLogger(__name__)

SCRAPE_TYPE_OPTIONS = {
    "hashtags":      "Hashtags",
    "profiles":      "Profiles",
    "searchQueries": "Search Queries",
    "postURLs":      "Post URLs",
}

PROFILE_SECTIONS_OPTIONS = {
    "videos":    "Videos",
    "liked":     "Liked",
    "reposts":   "Reposts",
    "favorites": "Favorites",
}

SEARCH_SECTION_OPTIONS = {
    "":       "Top / All",
    "/video": "Videos",
    "/user":  "Users",
}

PROFILE_SORTING_OPTIONS = {
    "latest":  "Latest",
    "popular": "Popular",
}

VIDEO_SEARCH_SORTING_OPTIONS = {
    "MOST_RELEVANT": "Most Relevant",
    "MOST_LIKED":    "Most Liked",
    "LATEST":        "Latest",
}

VIDEO_SEARCH_DATE_OPTIONS = {
    "":             "Any time",
    "last_24hours": "Last 24 hours",
    "last_7days":   "Last 7 days",
    "last_30days":  "Last 30 days",
    "last_3months": "Last 3 months",
    "last_6months": "Last 6 months",
    "last_year":    "Last year",
}

COUNTRY_OPTIONS = {
    "Any":                   "",
    "Indonesia (ID)":      "ID",
    "United States (US)":  "US",
    "United Kingdom (GB)": "GB",
    "Singapore (SG)":      "SG",
    "Malaysia (MY)":       "MY",
    "Thailand (TH)":       "TH",
    "Vietnam (VN)":        "VN",
    "Philippines (PH)":    "PH",
    "Brazil (BR)":         "BR",
    "Mexico (MX)":         "MX",
    "India (IN)":          "IN",
    "Japan (JP)":          "JP",
    "South Korea (KR)":    "KR",
    "Australia (AU)":      "AU",
    "Germany (DE)":        "DE",
    "France (FR)":         "FR",
}

# Output helpers
##########################################################################################

def safe_str(v) -> str:
    s = str(v) if v is not None else ''
    return s if s not in ('None', 'nan', '') else None

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

def scrapper_tiktok():
    if 'tk_pg_step' not in st.session_state:
        st.session_state['tk_pg_step'] = 1

    # APIFY token pool
    render_token_pool('tiktok')

    scrape_type = st.selectbox(
        "Scrape Type",
        list(SCRAPE_TYPE_OPTIONS.keys()),
        format_func=lambda k: SCRAPE_TYPE_OPTIONS[k],
        key='tk_sel_scrape_type',
    )

    profile_sections   = ['videos']
    profile_sorting    = 'latest'
    search_section     = ''
    search_sorting     = 'MOST_RELEVANT'
    search_date_filter = ''

    if scrape_type == 'profiles':
        col_ps, col_psort = st.columns(2)
        with col_ps:
            profile_sections = st.multiselect(
                "Profile Sections",
                list(PROFILE_SECTIONS_OPTIONS.keys()),
                default=['videos'],
                format_func=lambda k: PROFILE_SECTIONS_OPTIONS[k],
                key='tk_sel_profile_sections',
            )
        with col_psort:
            profile_sorting = st.selectbox(
                "Profile Sorting",
                list(PROFILE_SORTING_OPTIONS.keys()),
                format_func=lambda k: PROFILE_SORTING_OPTIONS[k],
                key='tk_sel_profile_sorting',
            )

    elif scrape_type == 'searchQueries':
        col_sec, col_vsort, col_vdate = st.columns(3)
        with col_sec:
            search_section = st.selectbox(
                "Search Section",
                list(SEARCH_SECTION_OPTIONS.keys()),
                format_func=lambda k: SEARCH_SECTION_OPTIONS[k],
                key='tk_sel_search_section',
            )
        with col_vsort:
            search_sorting = st.selectbox(
                "Video Sorting",
                list(VIDEO_SEARCH_SORTING_OPTIONS.keys()),
                format_func=lambda k: VIDEO_SEARCH_SORTING_OPTIONS[k],
                key='tk_sel_search_sorting',
            )
        with col_vdate:
            search_date_filter = st.selectbox(
                "Search Date",
                list(VIDEO_SEARCH_DATE_OPTIONS.keys()),
                format_func=lambda k: VIDEO_SEARCH_DATE_OPTIONS[k],
                key='tk_sel_search_date',
            )

    # Optional Filters
    oldest_date    = None
    newest_date    = None
    least_diggs    = 0
    most_diggs     = 0
    exclude_pinned = False
    filter_mode    = 'None'
    country_label  = 'Any'
    comments_pp    = 0
    top_comments   = 0
    max_replies    = 0

    with st.expander("Optional Filters", expanded=False):
        filter_mode = st.radio(
            "Date / Likes filter",
            ["None", "Date Range", "Likes Range"],
            horizontal=True,
            key='tk_opt_filter_mode',
            help="TikTok doesn't allow date and likes filters simultaneously — select one.",
        )

        if filter_mode == "Date Range":
            if scrape_type != 'postURLs':
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    oldest_date = st.date_input(
                        "Oldest Post Date",
                        value=None,
                        min_value=date(2016, 9, 1),
                        max_value=date.today(),
                        format="YYYY-MM-DD",
                        key='tk_opt_oldest_date',
                    )
                with col_d2:
                    newest_date = st.date_input(
                        "Newest Post Date",
                        value=None,
                        min_value=date(2016, 9, 1),
                        max_value=date.today(),
                        format="YYYY-MM-DD",
                        key='tk_opt_newest_date',
                    )
            else:
                st.caption("Date filters are not applicable for Post URLs.")

        elif filter_mode == "Likes Range":
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                least_diggs = st.number_input(
                    "Min Likes",
                    min_value=0,
                    value=0,
                    step=1000,
                    help="Only posts with at least this many likes. 0 = no minimum.",
                    key='tk_opt_least_diggs',
                )
            with col_l2:
                most_diggs = st.number_input(
                    "Max Likes",
                    min_value=0,
                    value=0,
                    step=1000,
                    help="Only posts with at most this many likes. 0 = no maximum.",
                    key='tk_opt_most_diggs',
                )

        col_cnt, col_pin = st.columns(2)
        with col_cnt:
            country_label = st.selectbox(
                "Country",
                list(COUNTRY_OPTIONS.keys()),
                key='tk_opt_country_label',
            )
        with col_pin:
            if scrape_type == 'profiles':
                exclude_pinned = st.checkbox(
                    "Exclude Pinned Posts",
                    value=False,
                    key='tk_opt_exclude_pinned',
                )

        with st.expander("Comments (default 0 = disabled)", expanded=False):
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                comments_pp = st.number_input(
                    "Per Post",
                    min_value=0,
                    value=0,
                    step=10,
                    key='tk_opt_comments_per_post',
                )
            with col_c2:
                top_comments = st.number_input(
                    "Top-Level",
                    min_value=0,
                    value=0,
                    step=10,
                    key='tk_opt_top_comments',
                )
            with col_c3:
                max_replies = st.number_input(
                    "Max Replies",
                    min_value=0,
                    value=0,
                    step=5,
                    key='tk_opt_max_replies',
                )

    # Form 
    label_map = {
        'hashtags':      "Hashtags (one per line)",
        'profiles':      "Profiles (username or URL, one per line)",
        'searchQueries': "Search Queries (one per line)",
        'postURLs':      "Post URLs (one per line)",
    }
    placeholder_map = {
        'hashtags':      "#dance\n#foodie\ntravel",
        'profiles':      "charlidamelio\nhttps://www.tiktok.com/@bellapoarch",
        'searchQueries': "funny cats\npython tutorial",
        'postURLs':      "https://www.tiktok.com/@user/video/1234567890",
    }

    with st.form(key='tiktok_form'):
        search_input = st.text_area(
            label_map[scrape_type],
            height=120,
            placeholder=placeholder_map[scrape_type],
        )

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            results_per_page = st.number_input(
                "Results Per Page",
                min_value=1,
                max_value=500,
                value=DEFAULT_RESULTS,
                step=10,
                help="Max results per hashtag / query / profile section",
            )
        with col_r2:
            if scrape_type in ('profiles', 'searchQueries'):
                max_profiles = st.number_input(
                    "Max Profiles Per Query",
                    min_value=1,
                    max_value=200,
                    value=DEFAULT_RESULTS,
                    step=5,
                )
            else:
                max_profiles = DEFAULT_RESULTS
                st.number_input(
                    "Max Profiles Per Query",
                    min_value=1,
                    max_value=200,
                    value=DEFAULT_RESULTS,
                    step=5,
                    disabled=True,
                )

        c1, c2 = st.columns([1, 1])
        with c1: search_but  = st.form_submit_button("Scrape Data", width='stretch')
        with c2: example_but = st.form_submit_button("Show Example", width='stretch')

        if search_but:
            st.session_state.update({
                'tk_pg_step':           2,
                'tk_scrape_pending':    True,
                'tk_scrape_results':    None,
                'tk_scrape_error':      None,
                'tk_scrape_type':       scrape_type,
                'tk_search_input':      search_input.strip(),
                'tk_profile_sections':  profile_sections,
                'tk_profile_sorting':   profile_sorting,
                'tk_search_section':    search_section,
                'tk_search_sorting':    search_sorting,
                'tk_search_date':       search_date_filter,
                'tk_filter_mode':       filter_mode,
                'tk_oldest_date':       str(oldest_date) if oldest_date else '',
                'tk_newest_date':       str(newest_date) if newest_date else '',
                'tk_exclude_pinned':    bool(exclude_pinned),
                'tk_country':           COUNTRY_OPTIONS.get(country_label, ''),
                'tk_country_label':     country_label,
                'tk_least_diggs':       int(least_diggs),
                'tk_most_diggs':        int(most_diggs),
                'tk_results_per_page':  int(results_per_page),
                'tk_max_profiles':      int(max_profiles),
                'tk_comments_per_post': int(comments_pp),
                'tk_top_comments':      int(top_comments),
                'tk_max_replies':       int(max_replies),
            })
        if example_but:
            st.session_state['tk_pg_step'] = 4

    # Results
    if st.session_state['tk_pg_step'] == 2:
        if st.session_state.get('tk_scrape_pending', False):
            st.session_state['tk_scrape_pending'] = False
            search_input = st.session_state.get('tk_search_input', '').strip()

            if not search_input:
                st.warning("Input is empty.")
            elif not get_active_token():
                st.session_state.update({
                    'tk_scrape_results': None,
                    'tk_scrape_error':   "No Apify token available. Load a token file in the panel above.",
                })
            else:
                scrape_type      = st.session_state.get('tk_scrape_type', 'hashtags')
                profile_sections = st.session_state.get('tk_profile_sections', ['videos'])
                profile_sorting  = st.session_state.get('tk_profile_sorting', 'latest')
                search_section   = st.session_state.get('tk_search_section', '')
                search_sorting   = st.session_state.get('tk_search_sorting', 'MOST_RELEVANT')
                search_date      = st.session_state.get('tk_search_date', '')
                oldest_date_str  = st.session_state.get('tk_oldest_date', '')
                newest_date_str  = st.session_state.get('tk_newest_date', '')
                exclude_pinned   = st.session_state.get('tk_exclude_pinned', False)
                country          = st.session_state.get('tk_country', '')
                least_diggs      = st.session_state.get('tk_least_diggs', 0)
                most_diggs       = st.session_state.get('tk_most_diggs', 0)
                results_per_page = st.session_state.get('tk_results_per_page', DEFAULT_RESULTS)
                max_profiles     = st.session_state.get('tk_max_profiles', DEFAULT_RESULTS)
                comments_pp      = st.session_state.get('tk_comments_per_post', 0)
                top_comments     = st.session_state.get('tk_top_comments', 0)
                max_replies      = st.session_state.get('tk_max_replies', 0)

                lines = [ln.strip() for ln in search_input.splitlines() if ln.strip()]
                actor_input = {'resultsPerPage': results_per_page}

                if scrape_type == 'hashtags':
                    actor_input['hashtags'] = [h.lstrip('#') for h in lines]
                elif scrape_type == 'profiles':
                    actor_input['profiles']              = lines
                    actor_input['profileScrapeSections'] = profile_sections or ['videos']
                    actor_input['profileSorting']        = profile_sorting
                    actor_input['maxProfilesPerQuery']   = max_profiles
                    actor_input['excludePinnedPosts']    = exclude_pinned
                elif scrape_type == 'searchQueries':
                    actor_input['searchQueries']      = lines
                    actor_input['searchSection']       = search_section
                    actor_input['videoSearchSorting']  = search_sorting
                    actor_input['maxProfilesPerQuery'] = max_profiles
                    if search_date:
                        actor_input['videoSearchDateFilter'] = search_date
                elif scrape_type == 'postURLs':
                    actor_input['postURLs'] = lines

                if oldest_date_str:
                    actor_input['oldestPostDateUnified'] = oldest_date_str
                if newest_date_str:
                    actor_input['newestPostDate'] = newest_date_str
                if least_diggs:
                    actor_input['leastDiggs'] = least_diggs
                if most_diggs:
                    actor_input['mostDiggs'] = most_diggs
                if country:
                    actor_input['proxyCountryCode'] = country
                if comments_pp:
                    actor_input['commentsPerPost'] = comments_pp
                if top_comments:
                    actor_input['topLevelCommentsPerPost'] = top_comments
                if max_replies:
                    actor_input['maxRepliesPerComment'] = max_replies

                with st.spinner("Running Apify TikTok scrape... (typically 30 – 180 s)"):
                    items, err = run_scrape(ACTOR_ID, actor_input)
                st.session_state.update({'tk_scrape_results': items, 'tk_scrape_error': err})

        items         = st.session_state.get('tk_scrape_results')
        err           = st.session_state.get('tk_scrape_error')
        scrape_type   = st.session_state.get('tk_scrape_type', 'hashtags')
        country_label = st.session_state.get('tk_country_label', 'Any')

        if err:
            st.error(f"Error: {err}")
            return
        if items is None:
            return

        st.write(
            f"Scraped **{SCRAPE_TYPE_OPTIONS[scrape_type]}**"
            + (f" via **{country_label}** proxy" if st.session_state.get('tk_country') else "")
            + f" — **{len(items)}** items"
        )
        st.divider()

        st.success(f"Scraped **{len(items)}** item(s) successfully!")

        df = items_to_dataframe(items)

        media_cols   = [c for c in df.columns if c in (
            'videoUrl', 'webVideoUrl', 'cover', 'dynamicCover', 'originCover',
        )]
        display_cols = [c for c in df.columns if c not in media_cols]
        st.dataframe(df[display_cols], width='stretch')

        if media_cols:
            with st.expander(f"Media URLs ({len(df)} items, columns: {', '.join(media_cols)})"):
                for i, row in df.iterrows():
                    label  = (
                        safe_str(row.get('webVideoUrl'))
                        or safe_str(row.get('id'))
                        or f"Item {i + 1}"
                    )
                    author = (
                        safe_str(row.get('authorMeta_name'))
                        or safe_str(row.get('author'))
                    )
                    st.caption(f"**{f'@{author}' if author else label}** — {label}")
                    for col in media_cols:
                        val = safe_str(row.get(col))
                        if val:
                            st.write(f"`{col}`: {val}")
                    st.divider()

        with st.expander("JSON Response"):
            st.json(items)

        csv = df.to_csv(index=False, sep=';')
        st.download_button(
            label=f"Download CSV ({len(df)} rows)",
            data=csv,
            file_name=f"tiktok_{scrape_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            width='stretch',
        )

    # Example
    if st.session_state['tk_pg_step'] == 4:
        st.subheader("Example Inputs per Scrape Type")
        st.dataframe(pd.DataFrame({
            "Scrape Type":   list(SCRAPE_TYPE_OPTIONS.values()),
            "Payload Key":   list(SCRAPE_TYPE_OPTIONS.keys()),
            "Example Input": [
                "#dance  (one hashtag per line, # optional)",
                "charlidamelio  (username or full profile URL)",
                "funny cats  (one search query per line)",
                "https://www.tiktok.com/@user/video/123  (full post URL)",
            ],
        }), width='stretch')
