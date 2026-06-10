import os
import time
import logging
import requests as req
import streamlit as st

APIFY_BASE      = 'https://api.apify.com/v2'
EXHAUSTED_CODES = {401, 402, 429}

logger = logging.getLogger(__name__)

# Token management
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

def fetch_token_usage(token: str, default_limit_usd: float = 5.0) -> dict:
    try:
        resp = req.get(f'{APIFY_BASE}/users/me', params={'token': token}, timeout=10)
        if resp.status_code != 200:
            return {}
        data    = resp.json().get('data', {})
        monthly = data.get('monthlyUsage') or {}
        plan    = data.get('plan') or {}
        used    = monthly.get('totalCreditCostUsd') or 0
        limit = (
            plan.get('maxMonthlyUsageCreditUsd')
            or monthly.get('monthlyUsageLimitUsd')
            or plan.get('monthlyUsageCreditsUsd')
            or default_limit_usd
        )
        pct = round(min(100.0, used / limit * 100), 1) if limit > 0 else None
        return {'used': used, 'limit': limit, 'pct': pct}
    except Exception:
        return {}

def start_actor_run(actor_id: str, actor_input: dict, token: str):
    url = f'{APIFY_BASE}/acts/{actor_id}/runs'
    try:
        resp = req.post(
            url,
            params={'token': token, 'maxTotalChargeUsd': 1.0},
            json=actor_input,
            timeout=60,
        )
        if resp.status_code in EXHAUSTED_CODES:
            return None, 'TOKEN_EXHAUSTED'
        if resp.status_code == 400:
            try:
                msg = resp.json().get('error', {}).get('message', resp.text)
            except Exception:
                msg = resp.text
            return None, f"Invalid actor input: {msg}"
        if resp.status_code == 404:
            return None, f"Actor '{actor_id}' not found — check your access."
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
            data       = resp.json().get('data', {})
            status     = data.get('status', '')
            status_msg = data.get('statusMessage', '')
            if status == 'SUCCEEDED':
                return status, data.get('defaultDatasetId'), None
            if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                detail = f": {status_msg}" if status_msg else ""
                return status, None, f"Actor run **{status}**{detail}"
            time.sleep(interval)
        except Exception as e:
            return None, None, str(e)
    return None, None, (
        f"Polling timed out after {timeout}s — run {run_id} may still be running on Apify."
    )

def fetch_dataset(dataset_id: str, token: str):
    url = f'{APIFY_BASE}/datasets/{dataset_id}/items'
    try:
        resp = req.get(url, params={'token': token, 'format': 'json'}, timeout=30)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as e:
        return None, str(e)

def run_scrape(actor_id: str, actor_input: dict, no_results_hint: str = '') -> tuple:
    """Run an Apify actor with automatic token rotation on 401/402/429."""
    pool     = st.session_state.get('token_pool', [])
    attempts = max(len(pool), 1)

    for attempt in range(attempts):
        token = get_active_token()
        if not token:
            return None, "No Apify token available. Load a token file in the panel above."

        run_id, err = start_actor_run(actor_id, actor_input, token)

        if err == 'TOKEN_EXHAUSTED':
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

        _, dataset_id, err = poll_run(run_id, token)
        poll_placeholder.empty()

        if err:
            return None, err

        items, err = fetch_dataset(dataset_id, token)
        if err:
            return None, err
        if not items:
            base = "Actor succeeded but returned 0 items."
            hint = f" {no_results_hint}" if no_results_hint else ""
            return None, base + hint

        return items, None

    return None, "All Apify tokens failed."

# User Interface

def render_token_pool(prefix: str):
    pool  = st.session_state.get('token_pool', [])
    index = st.session_state.get('token_index', 0)

    with st.expander("Apify Token Pool", expanded=not get_active_token()):
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'credentials', 'apify_token.txt',
        )
        token_file = st.text_input(
            "Path to token file (one token per line)",
            value=st.session_state.get('token_file', default_path),
            key=f'{prefix}_token_file_input',
        )

        col_load, col_reset, col_check = st.columns(3)
        with col_load:
            if st.button("Load / Reload Tokens", key=f'{prefix}_btn_load'):
                if token_file:
                    init_token_pool(token_file)
                    st.session_state.pop('token_usage', None)
                    st.rerun()
        with col_reset:
            if pool and st.button("Reset to Token #1", key=f'{prefix}_btn_reset'):
                st.session_state['token_index'] = 0
                st.rerun()
        with col_check:
            if pool and st.button("Check Usage", key=f'{prefix}_btn_check_usage'):
                with st.spinner("Checking..."):
                    usage = {}
                    for i, t in enumerate(pool):
                        usage[i] = fetch_token_usage(t)
                st.session_state['token_usage'] = usage

        if token_file and st.session_state.get('token_file') != token_file:
            init_token_pool(token_file)
            st.session_state.pop('token_usage', None)

        pool  = st.session_state.get('token_pool', [])
        index = st.session_state.get('token_index', 0)

        if pool:
            usage_data = st.session_state.get('token_usage')  # None = never checked
            if usage_data is None:
                # Default: show only the active token summary
                remaining = len(pool) - index - 1
                st.success(
                    f"Active: **Token #{index + 1}** of {len(pool)}"
                    + (f" ({remaining} more available)" if remaining > 0 else "")
                )
            else:
                # After "Check Usage": full list with font color by percentage
                for i, t in enumerate(pool):
                    u         = usage_data.get(i)
                    is_active = (i == index)

                    if not u:
                        color    = "#9ca3af"
                        pct_text = "—"
                    else:
                        pct = u.get('pct')
                        if pct is None:
                            color    = "#22c55e"
                            pct_text = "unlimited"
                        elif pct >= 80:
                            color    = "#ef4444"
                            pct_text = f"{pct:.0f}%"
                        elif pct >= 50:
                            color    = "#f97316"
                            pct_text = f"{pct:.0f}%"
                        else:
                            color    = "#22c55e"
                            pct_text = f"{pct:.0f}%"

                    weight       = "bold" if is_active else "normal"
                    active_label = " ← active" if is_active else ""
                    st.markdown(
                        f'<span style="color:{color}; font-weight:{weight}">'
                        f'Token #{i + 1} — {pct_text}{active_label}</span>',
                        unsafe_allow_html=True,
                    )
        else:
            st.warning(
                "No tokens loaded. Add a `.txt` file with tokens (one per line) then click Load."
            )
