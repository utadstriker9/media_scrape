import streamlit as st
from modules.shopee_scrapper import scrapper_shopee
# from modules.tiktok_scrapper import scrapper_tiktok

# Toggle Maintenance
UNDER_MAINTENANCE = False

# Page Config
st.set_page_config(page_title='Media Scrapper',layout="centered")

with st.container():
    col1, col2 = st.columns((4.1,1))
    with col1:
        st.empty()
        st.caption('Production Version 1')
    with col2:
        st.image('https://gemini.google.com/share/c22135563774',width=230)

if UNDER_MAINTENANCE == False:
    # Title
    st.markdown("""
    <style>
    .big-font {
        font-size:40px !important;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<p class="big-font">Media Scrapper</p>', unsafe_allow_html=True)

    # Tab
    tab1,tab2 = st.tabs(['TikTok Scrapper','Shopee Scrapper'])

    try:    
        with tab1:
            # scrapper_tiktok()
            st.write('UNDER MAINTENANCE')
    except ModuleNotFoundError as err1:
        st.error(err1)
    except Exception as err1:
        st.error(err1)

    try:
        with tab2:
            scrapper_shopee()
    except ModuleNotFoundError as err2:
        st.error(err2)
    except Exception as err2:
        st.error(err2)


else:
    #st.header('')
    st.markdown("<h1 style='text-align: center; color: black;'>Tools is under Maintenance</h1>", unsafe_allow_html=True)
    st.markdown("<p><center>We'll be back as soon as possible</center></p>", unsafe_allow_html=True)
    st.image('https://data-public-internal.s3.ap-southeast-1.amazonaws.com/maintenance-page_01.gif', caption='Under Maintenance')
    
    
