
import hashlib
import ipaddress
import socket
import urllib.request
from html.parser import HTMLParser
from io import BytesIO
from pypdf import PdfReader
from urllib.parse import urlparse, urljoin

import streamlit as st

from stt import transcribe_audio
from verifier import verify_notice, generate_official_search_links


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="VoiceGuard",
    page_icon=None,
    layout="centered"
)

# --------------------------------------------------
# VOICEGUARD PUBLIC-SERVICE DESIGN
# --------------------------------------------------

st.markdown("""
<style>
    .stApp {
        background-color: #F5F7FA;
    }

    .main .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3 {
        color: #173653 !important;
        font-weight: 700 !important;
    }

    h1 {
        font-size: 2.3rem !important;
    }

    p, label, .stMarkdown {
        color: #273746;
    }

    [data-testid="stTabs"] button {
        font-size: 15px;
        font-weight: 600;
        padding: 12px 10px;
    }

    .stButton > button {
        width: 100%;
        min-height: 48px;
        background-color: #174A70;
        color: white;
        border: none;
        border-radius: 9px;
        font-size: 16px;
        font-weight: 600;
    }

    .stButton > button:hover {
        background-color: #103653;
        color: white;
        border: none;
    }

    .stTextInput input,
    .stTextArea textarea {
        border-radius: 8px;
        border: 1px solid #CBD5E1;
        font-size: 16px;
    }

    [data-testid="stAlert"] {
        border-radius: 10px;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }

    .vg-subtitle {
        color: #536779;
        font-size: 16px;
        line-height: 1.6;
    }

    .vg-notice {
        background: #E8F0F6;
        border-left: 4px solid #174A70;
        border-radius: 8px;
        padding: 14px 16px;
        color: #173653;
        margin: 12px 0 20px 0;
    }

    @media (max-width: 640px) {
        .main .block-container {
            padding: 1rem 0.8rem 2rem 0.8rem;
        }

        h1 {
            font-size: 1.8rem !important;
        }

        [data-testid="stTabs"] button {
            font-size: 12px;
        }
    }
    /* Improve button text visibility */
.stButton > button,
.stButton > button p,
.stButton > button span {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

.stButton > button:disabled {
    background-color: #AAB7C4 !important;
    color: #FFFFFF !important;
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# WEBPAGE TEXT AND LINK EXTRACTION
# --------------------------------------------------

class PageTextParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.skip = 0
        self.link_stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1

        if tag == "a" and attrs.get("href"):
            self.link_stack.append({
                "title": "",
                "url": attrs["href"]
            })

    def handle_endtag(self, tag):

        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

        if tag == "a" and self.link_stack:
            item = self.link_stack.pop()

            if item["title"].strip():
                self.links.append(item)

    def handle_data(self, data):

        if not self.skip and data.strip():
            self.parts.append(data.strip())

            for item in self.link_stack:
                item["title"] += " " + data.strip()



def extract_webpage_text(url):

    parsed = urlparse(url.strip())

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a valid HTTP or HTTPS website link.")

    hostname = parsed.hostname.lower()

    if hostname == "localhost" or hostname.endswith(".local"):
        raise ValueError("This address cannot be analysed.")

    try:
        addresses = socket.getaddrinfo(hostname, None)

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])

            if not ip.is_global:
                raise ValueError(
                    "Private or local network addresses are not allowed."
                )

    except socket.gaierror:
        raise ValueError("The website address could not be reached.")

    request = urllib.request.Request(
        url.strip(),
        headers={"User-Agent": "VoiceGuard/1.0"}
    )

    with urllib.request.urlopen(request, timeout=15) as response:

        content_type = response.headers.get("Content-Type", "").lower()
        final_url = response.geturl()
        data = response.read(2_000_000)

    # PDF notification support
    if "application/pdf" in content_type or data.startswith(b"%PDF"):

        try:
            pdf = PdfReader(BytesIO(data))

            text_parts = []

            for page in pdf.pages[:50]:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)

            text = "\n".join(text_parts).strip()

            if not text:
                raise ValueError(
                    "No readable text found. This may be a scanned PDF."
                )

            return text[:20000], [], final_url

        except Exception as error:
            raise ValueError(f"Could not read this PDF: {error}")

    # HTML webpage support
    if "text/html" not in content_type:
        raise ValueError(
            "This link is not a supported HTML webpage or PDF."
        )

    html = data.decode("utf-8", errors="replace")

    parser = PageTextParser()
    parser.feed(html)

    text = " ".join(parser.parts)

    if not text:
        raise ValueError("No readable text was found.")

    links = []

    for item in parser.links:

        full_url = urljoin(final_url, item["url"])
        link_parsed = urlparse(full_url)

        if link_parsed.scheme in ("http", "https"):
            links.append({
                "title": item["title"].strip(),
                "url": full_url
            })

    return text[:20000], links, final_url


# --------------------------------------------------
# VERIFICATION REPORT
# --------------------------------------------------


def show_report(result):

    REPORT_UI = {
        "hi": {
            "heading": "जाँच रिपोर्ट",
            "analysis": "विश्लेषण",
            "authenticity": "वेबसाइट की प्रामाणिकता",
            "official_domain": "मान्यता प्राप्त आधिकारिक डोमेन:",
            "no_url": "मूल वेबसाइट लिंक नहीं दिया गया। वेबसाइट की प्रामाणिकता जाँची नहीं जा सकी।",
            "unrecognised": "यह मान्यता प्राप्त आधिकारिक डोमेन नहीं है। इसका मतलब यह नहीं कि भर्ती निश्चित रूप से फर्जी है।",
            "application": "आवेदन की स्थिति",
            "confirmed": "आधिकारिक अधिसूचना की पुष्टि हुई।",
            "not_confirmed": "आधिकारिक अधिसूचना की अभी पुष्टि नहीं हुई है।",
            "details": "भर्ती की निकाली गई जानकारी",
            "fields": [
                ("सरकारी स्तर", "government_level"),
                ("भर्ती बोर्ड", "recruitment_board"),
                ("रिक्तियों की जानकारी", "vacancy_numbers"),
                ("विज्ञापन संख्या", "advertisement_numbers"),
                ("तिथियाँ", "dates")
            ],
            "start": "आवेदन शुरू होने की तारीख:",
            "last": "आवेदन की अंतिम तारीख:",
            "not_identified": "पहचान नहीं हुई",
            "not_confirmed_date": "पुष्टि नहीं हुई",
            "risk": "जोखिम संकेत विश्लेषण",
            "no_warning": "भुगतान से संबंधित कोई निर्धारित चेतावनी वाक्यांश नहीं मिला।",
            "sources": "जाँच के लिए आधिकारिक स्रोत",
            "no_links": "कोई संबंधित स्रोत लिंक नहीं बनाया गया।",
            "caution": "यह केवल प्रारंभिक जाँच है। इससे आधिकारिक अधिसूचना की पुष्टि आवश्यक रूप से नहीं होती। खोज लिंक प्रामाणिकता का प्रमाण नहीं हैं। हमेशा मूल आधिकारिक अधिसूचना और आवेदन की तारीखें जाँचें।",
            "default": "विश्लेषण पूरा हुआ।",
            "unknown": "अज्ञात",
            "not_available": "विश्लेषण उपलब्ध नहीं है।"
        },
        "gu": {
            "heading": "ચકાસણી અહેવાલ",
            "analysis": "વિશ્લેષણ",
            "authenticity": "વેબસાઇટની સત્યતા",
            "official_domain": "માન્ય સત્તાવાર ડોમેન:",
            "no_url": "મૂળ વેબસાઇટ લિંક આપવામાં આવી નથી. વેબસાઇટની સત્યતા તપાસી શકાઈ નથી.",
            "unrecognised": "આ માન્ય સત્તાવાર ડોમેન નથી. તેનો અર્થ એ નથી કે ભરતી ચોક્કસપણે નકલી છે.",
            "application": "અરજીની સ્થિતિ",
            "confirmed": "સત્તાવાર સૂચનાની પુષ્ટિ થઈ.",
            "not_confirmed": "સત્તાવાર સૂચનાની હજુ પુષ્ટિ થઈ નથી.",
            "details": "ભરતીની મેળવેલી વિગતો",
            "fields": [
                ("સરકારી સ્તર", "government_level"),
                ("ભરતી બોર્ડ", "recruitment_board"),
                ("ખાલી જગ્યાઓની માહિતી", "vacancy_numbers"),
                ("જાહેરાત નંબર", "advertisement_numbers"),
                ("તારીખો", "dates")
            ],
            "start": "અરજી શરૂ થવાની તારીખ:",
            "last": "અરજી કરવાની છેલ્લી તારીખ:",
            "not_identified": "ઓળખી શકાયું નથી",
            "not_confirmed_date": "પુષ્ટિ થઈ નથી",
            "risk": "જોખમ સૂચક વિશ્લેષણ",
            "no_warning": "ચુકવણી સંબંધિત કોઈ નિર્ધારિત ચેતવણી વાક્ય મળ્યું નથી.",
            "sources": "તપાસવા માટેના સત્તાવાર સ્ત્રોતો",
            "no_links": "કોઈ સંબંધિત સ્ત્રોત લિંક બનાવવામાં આવી નથી.",
            "caution": "આ માત્ર પ્રાથમિક તપાસ છે. સત્તાવાર સૂચનાની પુષ્ટિ થઈ છે એવું જરૂરી નથી. શોધ લિંક્સ સત્યતાનો પુરાવો નથી. હંમેશા મૂળ સત્તાવાર સૂચના અને અરજીની તારીખો તપાસો.",
            "default": "વિશ્લેષણ પૂર્ણ થયું.",
            "unknown": "અજ્ઞાત",
            "not_available": "વિશ્લેષણ ઉપલબ્ધ નથી."
        },
        "en": {
            "heading": "Verification Report",
            "analysis": "Analysis",
            "authenticity": "Website Authenticity",
            "official_domain": "Recognised official domain:",
            "no_url": "No original website URL was provided. Website authenticity could not be checked.",
            "unrecognised": "This is not a recognised official domain. This does not automatically mean the recruitment is fake.",
            "application": "Application Status",
            "confirmed": "Official notification confirmed.",
            "not_confirmed": "Official notification has not yet been confirmed.",
            "details": "Extracted Recruitment Details",
            "fields": [
                ("Government Level", "government_level"),
                ("Recruitment Board", "recruitment_board"),
                ("Vacancy Information", "vacancy_numbers"),
                ("Advertisement Numbers", "advertisement_numbers"),
                ("Dates", "dates")
            ],
            "start": "Application Start Date:",
            "last": "Application Last Date:",
            "not_identified": "Not identified",
            "not_confirmed_date": "Not confirmed",
            "risk": "Risk Indicator Analysis",
            "no_warning": "No configured payment-warning phrases detected.",
            "sources": "Official Sources to Check",
            "no_links": "No relevant source links were generated.",
            "caution": "Preliminary screening only. A matching official notification has not necessarily been found. Search links are not proof of authenticity. Always check the original official notification and application dates.",
            "default": "Analysis completed.",
            "unknown": "Unknown",
            "not_available": "No analysis available."
        }
    }

    ui = REPORT_UI[app_language]

    st.subheader(ui["heading"])

    st.info(result.get("verdict", ui["default"]))

    st.write(f"**{ui['analysis']}**")
    st.write(result.get("status", ui["not_available"]))

    domain = result.get("domain_check", {})

    st.subheader(ui["authenticity"])

    if domain.get("is_official_domain"):
        st.success(
            f"{ui['official_domain']} {domain.get('source_name')}"
        )

    elif domain.get("domain") is None and not result.get("source_url"):
        st.info(ui["no_url"])

    else:
        st.warning(ui["unrecognised"])

    st.subheader(ui["application"])

    st.write(
        result.get("application_status", ui["unknown"])
    )

    if result.get("official_notification_confirmed"):
        st.success(ui["confirmed"])
    else:
        st.info(ui["not_confirmed"])

    st.subheader(ui["details"])

    details = result.get("details", {})

    for label, key in ui["fields"]:
        values = details.get(key, [])

        st.write(f"**{label}:**")
        st.write(
            ", ".join(str(value) for value in values)
            if values else ui["not_identified"]
        )

    st.write(f"**{ui['start']}**")
    st.write(
        details.get("application_start_date")
        or ui["not_confirmed_date"]
    )

    st.write(f"**{ui['last']}**")
    st.write(
        details.get("application_last_date")
        or ui["not_confirmed_date"]
    )

    st.subheader(ui["risk"])

    warnings = result.get("warnings", [])

    if warnings:
        for warning in warnings:
            st.warning(warning)
    else:
        st.write(ui["no_warning"])

    st.subheader(ui["sources"])

    links = generate_official_search_links(details)

    if links:
        for item in links:
            st.markdown(
                f"[{item['name']}]({item['url']})"
            )
    else:
        st.write(ui["no_links"])

    st.caption(ui["caution"])



# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

DEFAULTS = {
    "verification_result": None,
    "transcript": "",
    "page_text": "",
    "page_links": [],
    "page_url": "",
    "selected_notice_text": "",
    "selected_notice_url": "",
    "audio_hash": "",
    "detected_language": ""
}

for key, value in DEFAULTS.items():

    if key not in st.session_state:
        st.session_state[key] = value


# ---------------- GLOBAL LANGUAGE SELECTOR ----------------

LANGUAGES = {
    "हिन्दी": "hi",
    "ગુજરાતી": "gu",
    "English": "en"
}

selected_language = st.selectbox(
    "Select your preferred language / अपनी भाषा चुनें",
    options=list(LANGUAGES.keys()),
    key="app_language"
)

app_language = LANGUAGES[selected_language]
voice_language = {
    "hi": "hi-IN",
    "gu": "gu-IN",
    "en": "en-IN"
}[app_language]
# --------------------------------------------------
# APPLICATION HEADER
# --------------------------------------------------

HEADER_TEXT = {
    "hi": {
        "badge": "भर्ती सुरक्षा सहायक",
        "title": "सरकारी नौकरी की जानकारी अब आसानी से जाँचें।",
        "subtitle": "लिंक, नोटिस या अपनी आवाज़ से शुरुआत करें।"
    },
    "gu": {
        "badge": "ભરતી સુરક્ષા સહાયક",
        "title": "સરકારી નોકરીની માહિતી હવે સરળતાથી તપાસો.",
        "subtitle": "લિંક, સૂચના અથવા તમારા અવાજથી શરૂઆત કરો."
    },
    "en": {
        "badge": "RECRUITMENT SAFETY ASSISTANT",
        "title": "Verify government job information easily.",
        "subtitle": "Start with a link, notice or your voice."
    }
}

header = HEADER_TEXT[app_language]

st.html(f"""
<div style="
    background: linear-gradient(120deg, #102D46, #1D5275);
    padding: 36px;
    border-radius: 20px;
    margin-bottom: 22px;
    box-shadow: 0 8px 24px rgba(16,45,70,0.12);
">
    <div style="
        color: #D8EAF7;
        font-size: 12px;
        font-weight: 600;
    ">{header['badge']}</div>

    <div style="
        color: white;
        font-size: 40px;
        font-weight: 750;
        margin-top: 20px;
    ">VoiceGuard</div>

    <div style="
        color: #E5EEF5;
        font-size: 18px;
        line-height: 1.7;
        margin-top: 12px;
    ">
        {header['title']}<br>
        {header['subtitle']}
    </div>
</div>
""")

# --------------------------------------------------
# INPUT TABS
# --------------------------------------------------

# ---------------- MODERN FEATURE NAVIGATION ----------------

st.markdown("""
<style>
div[role="radiogroup"] {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
}

div[role="radiogroup"] label {
    background: white;
    border: 1px solid #DCE4EC;
    border-radius: 12px;
    padding: 14px 18px;
    min-height: 55px;
    box-shadow: 0 2px 8px rgba(20, 45, 70, 0.04);
}

div[role="radiogroup"] label:has(input:checked) {
    background: #E8F1F8;
    border: 2px solid #174A70;
}

div[role="radiogroup"] label p {
    font-weight: 600;
    color: #173653;
}
</style>
""", unsafe_allow_html=True)


FEATURES = {
    "website": {
        "hi": "वेबसाइट लिंक",
        "gu": "વેબસાઇટ લિંક",
        "en": "Website Link"
    },
    "text": {
        "hi": "लिखा हुआ नोटिस",
        "gu": "લખેલી સૂચના",
        "en": "Pasted Notice"
    },
    "voice": {
        "hi": "आवाज़ से पूछें",
        "gu": "અવાજથી પૂછો",
        "en": "Ask by Voice"
    },
    "compare": {
        "hi": "दो नोटिस की तुलना",
        "gu": "બે સૂચનાઓની સરખામણી",
        "en": "Compare Notices"
    }
}

active_tab = st.radio(
    "Choose verification method",
    options=list(FEATURES.keys()),
    format_func=lambda key: FEATURES[key][app_language],
    horizontal=True,
    label_visibility="collapsed",
    key="active_feature"
)




# --------------------------------------------------
# TAB 1: WEBSITE LINK
# --------------------------------------------------

if active_tab == "website":

    WEBSITE_TEXT = {
        "hi": {
            "label": "भर्ती पोस्ट या वेबसाइट लिंक डालें",
            "button": "लिंक की जाँच करें",
            "empty": "कृपया लिंक डालें।",
            "loading": "वेबसाइट पढ़ी जा रही है...",
            "success": "वेबसाइट से जानकारी सफलतापूर्वक निकाली गई।",
            "error": "इस लिंक की जाँच नहीं हो सकी:"
        },
        "gu": {
            "label": "ભરતી પોસ્ટ અથવા વેબસાઇટ લિંક દાખલ કરો",
            "button": "લિંક તપાસો",
            "empty": "કૃપા કરીને લિંક દાખલ કરો.",
            "loading": "વેબસાઇટ વાંચવામાં આવી રહી છે...",
            "success": "વેબસાઇટમાંથી માહિતી સફળતાપૂર્વક મેળવી.",
            "error": "આ લિંક તપાસી શકાઈ નથી:"
        },
        "en": {
            "label": "Paste a recruitment post or webpage link",
            "button": "Analyse Link",
            "empty": "Please enter a link.",
            "loading": "Reading webpage...",
            "success": "Webpage extracted successfully.",
            "error": "Could not analyse this link:"
        }
    }

    wt = WEBSITE_TEXT[app_language]

    url = st.text_input(
        wt["label"],
        placeholder="https://example.com/recruitment-notice"
    )

    if st.button(wt["button"]):

        if not url.strip():
            st.warning(wt["empty"])

        else:
            with st.spinner(wt["loading"]):
                try:
                    page_text, page_links, final_url = extract_webpage_text(url)

                    st.session_state.page_text = page_text
                    st.session_state.page_links = page_links
                    st.session_state.page_url = final_url
                    st.session_state.verification_result = None
                    st.session_state.selected_notice_text = ""
                    st.session_state.selected_notice_url = ""

                    st.success(wt["success"])

                except Exception as error:
                    st.error(f"{wt['error']} {error}")

    if st.session_state.page_text:

        st.text_area(
            "Extracted webpage text",
            st.session_state.page_text,
            height=150
        )

        if not st.session_state.page_links:

            if st.button("Verify Extracted Document"):
                st.session_state.verification_result = verify_notice(
                    st.session_state.page_text,
                    source_url=st.session_state.page_url
                )

        st.subheader("Discovered Recruitment Notifications")

        recruitment_words = [
            "recruitment", "advertisement", "notification",
            "vacancy", "posts", "post of", "addendum notice",
            "ora", "भर्ती", "જાહેરાત"
        ]

        excluded_words = [
            "final result", "written result", "marks of",
            "interview", "question paper", "examination calendar",
            "answer key", "cut-off"
        ]

        source_host = urlparse(
            st.session_state.page_url
        ).hostname

        relevant_links = []

        for item in st.session_state.page_links:
            title = item["title"].lower()
            link_url = item["url"]
            link_host = urlparse(link_url).hostname

            is_relevant = any(
                word in title or word in link_url.lower()
                for word in recruitment_words
            )

            is_excluded = any(
                word in title for word in excluded_words
            )

            if is_relevant and not is_excluded and link_host == source_host:
                relevant_links.append(item)

        if relevant_links:

            selected_notice = st.selectbox(
                "Available notifications",
                options=relevant_links,
                format_func=lambda item: item["title"]
            )

            st.caption(selected_notice["url"])

            if st.button("Analyse Selected Notification"):
                try:
                    notice_text, notice_links, final_url = extract_webpage_text(
                        selected_notice["url"]
                    )

                    st.session_state.selected_notice_text = notice_text
                    st.session_state.selected_notice_url = final_url

                    st.session_state.verification_result = verify_notice(
                        notice_text,
                        source_url=final_url
                    )

                    st.success("Selected notification analysed.")

                except Exception as error:
                    st.error(f"Could not analyse notification: {error}")

            if st.session_state.selected_notice_text:
                st.text_area(
                    "Selected Notification Text",
                    st.session_state.selected_notice_text,
                    height=180
                )

                st.markdown(
                    f"[Open Original Notification]"
                    f"({st.session_state.selected_notice_url})"
                )

        else:
            st.info(
                "No individual recruitment notifications were discovered. "
                "Try the official Recruitment Advertisements section "
                "or paste the specific notice text."
            )


# --------------------------------------------------
# TAB 2: PASTE TEXT
# --------------------------------------------------


elif active_tab == "text":

    TEXT_UI = {
        "hi": {
            "heading": "भर्ती नोटिस का टेक्स्ट डालें",
            "placeholder": "भर्ती की जानकारी यहाँ पेस्ट करें...",
            "button": "टेक्स्ट की जाँच करें",
            "empty": "कृपया टेक्स्ट डालें।",
            "success": "नोटिस की जाँच पूरी हुई।"
        },
        "gu": {
            "heading": "ભરતી સૂચનાનો ટેક્સ્ટ દાખલ કરો",
            "placeholder": "ભરતીની માહિતી અહીં પેસ્ટ કરો...",
            "button": "ટેક્સ્ટ તપાસો",
            "empty": "કૃપા કરીને ટેક્સ્ટ દાખલ કરો.",
            "success": "સૂચનાની તપાસ પૂર્ણ થઈ."
        },
        "en": {
            "heading": "Paste recruitment notice or social media post",
            "placeholder": "Paste the recruitment announcement here...",
            "button": "Analyse Pasted Text",
            "empty": "Please paste some text.",
            "success": "Notice analysis completed."
        }
    }

    ui = TEXT_UI[app_language]

    pasted_text = st.text_area(
        ui["heading"],
        height=200,
        placeholder=ui["placeholder"]
    )

    if st.button(ui["button"]):

        if not pasted_text.strip():
            st.warning(ui["empty"])

        else:
            st.session_state.verification_result = verify_notice(
                pasted_text
            )
            st.session_state.transcript = ""
            st.success(ui["success"])

# --------------------------------------------------
# TAB 3: VOICE RECORDING
# --------------------------------------------------


elif active_tab == "voice":

    # ---------------- VOICE RECORDING INTERFACE ----------------

    st.html("""
    <div style="
        background: white;
        border: 1px solid #DCE4EC;
        border-radius: 16px;
        padding: 24px;
        margin: 12px 0 20px 0;
    ">
        <div style="
            color: #174A70;
            font-size: 12px;
            font-weight: 700;
        ">VOICE-BASED VERIFICATION</div>

        <h2 style="color:#173653;font-size:25px;">
            आवाज़ से अपनी बात पूछें
        </h2>

        <p style="color:#536779;font-size:16px;line-height:1.7;">
            सरकारी नौकरी के बारे में अपना सवाल बोलें।
            VoiceGuard आपकी आवाज़ को टेक्स्ट में बदलकर
            उसकी जाँच करेगा।
        </p>
    </div>
    """)

    

    VOICE_UI = {
        "hi": {
            "heading": "आवाज़ से अपना सवाल पूछें",
            "description": "सरकारी नौकरी के बारे में अपना सवाल बोलें। VoiceGuard आपकी आवाज़ को टेक्स्ट में बदलकर उसकी जाँच करेगा।",
            "record_heading": "अपना सवाल रिकॉर्ड करें",
            "record_info": "रिकॉर्डिंग शुरू करें, अपना सवाल बोलें और फिर रिकॉर्डिंग रोकें।",
            "record_label": "रिकॉर्ड करने के लिए क्लिक करें",
            "verify": "आवाज़ की जाँच करें",
            "success": "आवाज़ की रिकॉर्डिंग प्राप्त हुई।",
            "loading": "आवाज़ को टेक्स्ट में बदलकर जाँच की जा रही है...",
            "heard": "VoiceGuard ने यह सुना",
            "detected": "पहचानी गई भाषा:",
            "error": "रिकॉर्डिंग समझ नहीं आई। कृपया दोबारा बोलें।"
        },
        "gu": {
            "heading": "અવાજથી તમારો પ્રશ્ન પૂછો",
            "description": "સરકારી નોકરી વિશે તમારો પ્રશ્ન બોલો. VoiceGuard તમારા અવાજને ટેક્સ્ટમાં બદલીને તેની તપાસ કરશે.",
            "record_heading": "તમારો પ્રશ્ન રેકોર્ડ કરો",
            "record_info": "રેકોર્ડિંગ શરૂ કરો, તમારો પ્રશ્ન બોલો અને પછી રેકોર્ડિંગ બંધ કરો.",
            "record_label": "રેકોર્ડ કરવા માટે ક્લિક કરો",
            "verify": "અવાજ તપાસો",
            "success": "અવાજનું રેકોર્ડિંગ પ્રાપ્ત થયું.",
            "loading": "અવાજને ટેક્સ્ટમાં બદલીને તપાસવામાં આવી રહ્યો છે...",
            "heard": "VoiceGuard એ આ સાંભળ્યું",
            "detected": "ઓળખાયેલી ભાષા:",
            "error": "રેકોર્ડિંગ સમજી શકાયું નથી. ફરીથી બોલવાનો પ્રયાસ કરો."
        },
        "en": {
            "heading": "Ask your question by voice",
            "description": "Speak your question about a government job. VoiceGuard will convert your voice into text and analyse it.",
            "record_heading": "Record your question",
            "record_info": "Start recording, speak your question, and then stop recording.",
            "record_label": "Click to record",
            "verify": "Verify Voice Query",
            "success": "Voice recording captured.",
            "loading": "Transcribing and analysing your voice...",
            "heard": "What VoiceGuard heard",
            "detected": "Detected language:",
            "error": "Could not understand the recording. Please try again."
        }
    }

    vu = VOICE_UI[app_language]

    st.subheader(vu["heading"])
    st.write(vu["description"])
    st.markdown(f"### {vu['record_heading']}")
    st.info(vu["record_info"])

    audio_value = st.audio_input(
        vu["record_label"],
        key="live_voice_input"
    )

    if audio_value is not None:
        st.success(vu["success"])

        if st.button(vu["verify"]):
            with st.spinner(vu["loading"]):
                transcript, detected_language = transcribe_audio(
                    audio_value.getvalue(),
                    "voice_query.wav",
                    voice_language
                )

                if transcript.strip():
                    st.subheader(vu["heard"])
                    st.write(transcript)

                    if detected_language:
                        st.caption(
                            f"{vu['detected']} {detected_language}"
                        )

                    result = verify_notice(transcript)
                    st.session_state.verification_result = result

                else:
                    st.warning(vu["error"])

# --------------------------------------------------
# DISPLAY VERIFICATION REPORT
# --------------------------------------------------

# --------------------------------------------------
# TAB 4: COMPARE TWO RECRUITMENT NOTICES
# --------------------------------------------------

elif active_tab == "compare":

    COMPARE_UI = {
        "hi": {
            "heading": "दो भर्ती नोटिस की तुलना करें",
            "one": "नोटिस 1",
            "two": "नोटिस 2",
            "label_one": "पहला भर्ती नोटिस यहाँ डालें",
            "label_two": "दूसरा भर्ती नोटिस यहाँ डालें",
            "button": "नोटिस की तुलना करें",
            "empty": "कृपया दोनों नोटिस डालें।",
            "result_one": "नोटिस 1 की जाँच",
            "result_two": "नोटिस 2 की जाँच"
        },
        "gu": {
            "heading": "બે ભરતી સૂચનાઓની સરખામણી કરો",
            "one": "સૂચના 1",
            "two": "સૂચના 2",
            "label_one": "પ્રથમ ભરતી સૂચના અહીં દાખલ કરો",
            "label_two": "બીજી ભરતી સૂચના અહીં દાખલ કરો",
            "button": "સૂચનાઓની સરખામણી કરો",
            "empty": "કૃપા કરીને બંને સૂચનાઓ દાખલ કરો.",
            "result_one": "સૂચના 1 ની તપાસ",
            "result_two": "સૂચના 2 ની તપાસ"
        },
        "en": {
            "heading": "Compare Two Recruitment Notices",
            "one": "Notice 1",
            "two": "Notice 2",
            "label_one": "Paste the first recruitment notice",
            "label_two": "Paste the second recruitment notice",
            "button": "Compare Notices",
            "empty": "Please enter both recruitment notices.",
            "result_one": "Notice 1 Analysis",
            "result_two": "Notice 2 Analysis"
        }
    }

    cu = COMPARE_UI[app_language]

    st.subheader(cu["heading"])

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### {cu['one']}")
        notice_one = st.text_area(
            cu["label_one"],
            height=220,
            key="compare_notice_one"
        )

    with col2:
        st.markdown(f"### {cu['two']}")
        notice_two = st.text_area(
            cu["label_two"],
            height=220,
            key="compare_notice_two"
        )

    if st.button(cu["button"]):

        if not notice_one.strip() or not notice_two.strip():
            st.warning(cu["empty"])

        else:
            st.session_state.compare_result_one = verify_notice(notice_one)
            st.session_state.compare_result_two = verify_notice(notice_two)

    if st.session_state.get("compare_result_one"):
        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"### {cu['result_one']}")
            show_report(st.session_state.compare_result_one)

        with col2:
            st.markdown(f"### {cu['result_two']}")
            show_report(st.session_state.compare_result_two)


# --------------------------------------------------
# DISPLAY VERIFICATION REPORT
# --------------------------------------------------

if active_tab != "compare" and st.session_state.verification_result:
    st.divider()
    show_report(st.session_state.verification_result)
