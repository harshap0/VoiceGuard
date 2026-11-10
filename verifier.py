
import re
from datetime import date, datetime
from urllib.parse import quote_plus, urlparse

from sources import OFFICIAL_SOURCES


RECRUITMENT_TERMS = [
    "government job", "government recruitment", "vacancy",
    "vacancies", "recruitment", "notification", "application form",
    "government exam", "सरकारी नौकरी", "भर्ती", "रिक्तियां",
    "नौकरी", "आवेदन", "परीक्षा", "સરકારી નોકરી",
    "સરકારી ભરતી", "ભરતી", "જગ્યાઓ", "નોકરી",
    "ખાલી જગ્યા", "જાહેરાત", "અરજી", "પરીક્ષા",
    "ગ્રામીણ ડાક સેવક"
]

PAYMENT_WARNING_TERMS = [
    "personal upi", "pay to this number", "send money",
    "guaranteed job", "pay for selection", "पैसे भेजें",
    "नौकरी पक्की", "पैसे देकर नौकरी", "પૈસા મોકલો",
    "નોકરી પાક્કી", "પૈસા આપીને નોકરી",
    "વ્યક્તિગત ખાતામાં પૈસા"
]

BOARD_KEYWORDS = {
    "UPSC": ["upsc", "union public service commission",
             "संघ लोक सेवा आयोग"],
    "SSC": [
    "ssc",
    "staff selection commission",
    "कर्मचारी चयन आयोग"
],
    "Railways": ["rrb", "railway recruitment", "रेलवे भर्ती"],
    "IBPS": ["ibps", "institute of banking personnel selection"],
    "SBI Recruitment": ["sbi recruitment", "state bank recruitment"],
    "India Post GDS": [
        "india post", "indian post office", "gramin dak sevak",
        "ग्रामीण डाक सेवक", "ગ્રામીણ ડાક સેવક", "gds"
    ],
    "GPSC": [
        "gpsc", "gujarat public service commission",
        "ગુજરાત જાહેર સેવા આયોગ", "ગુજરાત લોક સેવા આયોગ"
    ],
    "OJAS Gujarat": ["ojas gujarat", "ojas", "ઓજસ"],
    "BPSC": ["bpsc", "bihar public service commission"],
    "RPSC": ["rpsc", "rajasthan public service commission"],
    "UPPSC": ["uppsc", "uttar pradesh public service commission"],
    "MPPSC": ["mppsc", "madhya pradesh public service commission"],
    "TNPSC": ["tnpsc", "tamil nadu public service commission"],
    "KPSC": ["kpsc", "karnataka public service commission"],
    "Kerala PSC": ["kerala psc", "kerala public service commission"],
    "APPSC": ["appsc", "andhra pradesh public service commission"],
    "HPSC": ["hpsc", "haryana public service commission"],
    "Indian Army": ["indian army recruitment", "army bharti"],
    "Indian Navy": ["indian navy recruitment", "navy recruitment"],
    "Indian Air Force": ["indian air force recruitment", "agniveervayu"],
    "Police Recruitment": [
        "police recruitment", "police bharti",
        "પોલીસ ભરતી", "पुलिस भर्ती"
    ]
}


MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}


def detect_boards(text):
    found = []

    for board, keywords in BOARD_KEYWORDS.items():
        for keyword in keywords:
            if keyword.isascii() and keyword.isalnum():
                pattern = r"\b" + re.escape(keyword) + r"\b"
            else:
                pattern = re.escape(keyword)

            if re.search(pattern, text, re.IGNORECASE):
                found.append(board)
                break

    return found


def extract_dates(text):
    """Extract recognizable dates. These are not automatically deadlines."""
    found = []

    numeric_dates = re.findall(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b",
        text
    )
    found.extend(numeric_dates)

    month_pattern = (
        r"\b\d{1,2}\s+"
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
        r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s*,?\s+\d{4}\b"
    )

    found.extend(
        re.findall(month_pattern, text, re.IGNORECASE)
    )

    return list(dict.fromkeys(found))


def parse_date(value):
    value = value.strip().replace(",", "")

    formats = [
        "%d/%m/%Y", "%d-%m-%Y",
        "%d %b %Y", "%d %B %Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None



def extract_application_dates(text):
    """Extract application start and closing dates from labelled notice text."""

    result = {
        "application_start_date": None,
        "application_last_date": None
    }

    date_regex = (
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b"
        r"|\b\d{1,2}\s+"
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
        r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s*,?\s+\d{4}\b"
    )

    normalized_text = re.sub(r"\s+", " ", text)

    start_patterns = [
        r"online applications are invited.{0,300}?between\s+date\s*[:\-]?\s*(" + date_regex + r")",
        r"online recruitment applications.{0,300}?\bfrom\s+(" + date_regex + r")",
        r"application\s+(?:start|starting|begin)\s+date\s*[:\-]?\s*(" + date_regex + r")",
        r"registration\s+(?:start|starting)\s+date\s*[:\-]?\s*(" + date_regex + r")",
        r"आवेदन\s+प्रारंभ\s+तिथि\s*[:\-]?\s*(" + date_regex + r")",
        r"અરજી\s+શરૂ\s+થવાની\s+તારીખ\s*[:\-]?\s*(" + date_regex + r")",
        r"between\s+date\s*[:\-]?\s*" + date_regex + r".{0,100}?\bto\s+date\s*[:\-]?\s*(" + date_regex + r")",
    ]


    end_patterns = [
        r"\bto\s+date\s*[:\-]?\s*(" + date_regex + r")",
        r"closing\s+date\s+for\s+submission.{0,300}?\b(?:on\s+)?(" + date_regex + r")",
        r"last\s+date\s+(?:to\s+)?(?:apply|submit|register)\s*[:\-]?\s*(" + date_regex + r")",
        r"closing\s+date\s+of\s+application\s*[:\-]?\s*(" + date_regex + r")",
        r"application\s+(?:closing|end)\s+date\s*[:\-]?\s*(" + date_regex + r")",
        r"last\s+date\s+for\s+application\s*[:\-]?\s*(" + date_regex + r")",
        r"आवेदन\s+की\s+अंतिम\s+तिथि\s*[:\-]?\s*(" + date_regex + r")",
        r"અરજી\s+કરવાની\s+છેલ્લી\s+તારીખ\s*[:\-]?\s*(" + date_regex + r")"
    ]

    for pattern in start_patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                result["application_start_date"] = parsed.isoformat()
                break

    for pattern in end_patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                result["application_last_date"] = parsed.isoformat()
                break

    return result


def extract_recruitment_details(transcript):
    text = transcript.lower()

    details = {
        "recruitment_board": detect_boards(text),
        "government_level": [],
        "vacancy_numbers": [],
        "advertisement_numbers": [],
        "dates": [],
        "application_start_date": None,
        "application_last_date": None
    }

    central_keywords = [
        "central government", "government of india",
        "भारत सरकार", "केंद्र सरकार"
    ]

    delhi_keywords = [
        "government of nct of delhi",
        "gnctd"
    ]

    state_keywords = [
        "ગુજરાત સરકાર",
        "રાજ્ય સરકાર",
        "राज्य सरकार"
    ]

    if any(word in text for word in delhi_keywords):
        details["government_level"].append("Delhi Government")

    if any(word in text for word in state_keywords):
        details["government_level"].append("State Government")

    if any(word in text for word in central_keywords):
        details["government_level"].append("Central Government")

    if any(board in details["recruitment_board"] for board in ["GPSC", "OJAS Gujarat"]):
        details["government_level"].append("State Government")
    vacancy_pattern = (
    r"\b(?:[\d,]+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+vacanc(?:y|ies)\s+for\s+the\s+post\b"
)


    details["vacancy_numbers"] = re.findall(
        vacancy_pattern, text, re.IGNORECASE
    )
    numeric_vacancy_pattern = (
    r"class-i\s+0*(\d{1,3})\s+0*\d{1,3}\s+0*\d{1,3}\b"
)

    numeric_vacancies = re.findall(
        numeric_vacancy_pattern, text, re.IGNORECASE
    )

    for count in numeric_vacancies:
        vacancy = f"{int(count)} vacancy" if int(count) == 1 else f"{int(count)} vacancies"
        if vacancy not in details["vacancy_numbers"]:
            details["vacancy_numbers"].append(vacancy)

    large_claim_patterns = [
        (r"\b1\s*,?\s*00\s*,?\s*000\b", "1,00,000"),
        (r"\bone\s+lakh\b", "1 lakh"),
        (r"એક\s+લાખ", "1 lakh"),
        (r"एक\s+लाख", "1 lakh")
    ]

    for pattern, label in large_claim_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            claim = label + " (spoken claim)"
            if claim not in details["vacancy_numbers"]:
                details["vacancy_numbers"].append(claim)

    ad_pattern = (
        r"\b(?:advertisement|advt\.?|notification)"
        r"\s*(?:no\.?|number)\s*[:#-]?\s*"
        r"([a-z0-9]+(?:[-/][a-z0-9]+)*)"
    )

    details["advertisement_numbers"] = re.findall(
        ad_pattern, text, re.IGNORECASE
    )

    details["dates"] = extract_dates(text)

    application_dates = extract_application_dates(text)
    details.update(application_dates)

    return details


def check_official_domain(source_url):
    """Check whether a URL belongs to a configured official source."""
    if not source_url:
        return {
            "is_official_domain": False,
            "source_name": None,
            "domain": None
        }

    try:
        hostname = urlparse(source_url).hostname

        if not hostname:
            raise ValueError("Missing hostname")

        hostname = hostname.lower().rstrip(".")

        for source in OFFICIAL_SOURCES.values():
            official_domain = source["domain"].lower()

            if (
                hostname == official_domain
                or hostname.endswith("." + official_domain)
            ):
                return {
                    "is_official_domain": True,
                    "source_name": source["name"],
                    "domain": official_domain
                }

    except (ValueError, AttributeError):
        pass

    return {
        "is_official_domain": False,
        "source_name": None,
        "domain": None
    }


def get_application_status(details):
    start = details.get("application_start_date")
    end = details.get("application_last_date")

    today = date.today()

    if not start and not end:
        return "Unknown"

    start_date = date.fromisoformat(start) if start else None
    end_date = date.fromisoformat(end) if end else None

    if start_date and today < start_date:
        return "Upcoming"

    if end_date and today > end_date:
        return "Closed"

    if start_date and end_date:
        if start_date <= today <= end_date:
            return "Open"

    return "Unknown"


def verify_notice(transcript, source_url=None):
    text = transcript.lower()

    warnings = [
        "Potential warning sign: " + term
        for term in PAYMENT_WARNING_TERMS
        if term in text
    ]

    recruitment_found = [
        term for term in RECRUITMENT_TERMS
        if term in text
    ]

    details = extract_recruitment_details(transcript)
    domain_check = check_official_domain(source_url)
    application_status = get_application_status(details)

    if warnings:
        verdict = "Potential risk detected"
        status = "Payment-related warning language found."

    elif not recruitment_found:
        verdict = "Insufficient evidence to verify"
        status = "No clear recruitment-related language detected."

    else:
        verdict = "Recruitment claim detected - verification required"
        status = (
            "Recruitment information extracted. "
            "A matching official notification has not yet been confirmed."
        )

    return {
        "verdict": verdict,
        "status": status,
        "warnings": warnings,
        "evidence": [],
        "recruitment_terms": recruitment_found,
        "details": details,
        "domain_check": domain_check,
        "application_status": application_status,
        "official_notification_confirmed": False
    }


def get_official_sources():
    return OFFICIAL_SOURCES


def generate_official_search_links(details):
    board_source_mapping = {
        "UPSC": ["UPSC"],
        "SSC": ["SSC"],
        "Railways": ["Railways"],
        "IBPS": ["IBPS"],
        "SBI Recruitment": [],
        "India Post GDS": ["India Post GDS"],
        "GPSC": ["GPSC"],
        "OJAS Gujarat": ["OJAS Gujarat"],
        "BPSC": ["BPSC"],
        "RPSC": ["RPSC"],
        "UPPSC": ["UPPSC"],
        "MPPSC": ["MPPSC"],
        "TNPSC": ["TNPSC"],
        "KPSC": ["KPSC"],
        "Kerala PSC": ["Kerala PSC"],
        "APPSC": ["APPSC"],
        "HPSC": ["HPSC"]
    }

    boards = details.get("recruitment_board", [])

    selected_sources = []

    for board in boards:
        selected_sources.extend(
            board_source_mapping.get(board, [])
        )

    selected_sources = list(dict.fromkeys(selected_sources))

    if not selected_sources:
        selected_sources = ["UPSC", "SSC", "Employment News"]

    keywords = []
    keywords.extend(boards)
    keywords.extend(details.get("vacancy_numbers", []))
    keywords.extend(details.get("advertisement_numbers", []))

    search_text = " ".join(keywords).strip()

    if not search_text:
        search_text = "government recruitment notification"

    links = []

    for source_key in selected_sources:
        source = OFFICIAL_SOURCES.get(source_key)

        if not source:
            continue

        query = (
            f'site:{source["domain"]} '
            f'{search_text} recruitment notification'
        )

        links.append({
            "name": source["name"],
            "url": (
                "https://www.google.com/search?q="
                + quote_plus(query)
            )
        })

    return links


def compare_claim_with_official_notice(
    claim_text,
    official_notice_text,
    official_notice_url
):
    """
    Compare a recruitment claim with an official notification.
    A full match requires an official domain, matching board,
    matching advertisement number, matching vacancy count,
    and no detected mismatches.
    """

    claim = extract_recruitment_details(claim_text)
    notice = extract_recruitment_details(official_notice_text)

    domain = check_official_domain(official_notice_url)

    comparison = {
        "official_domain": domain["is_official_domain"],
        "source_name": domain["source_name"],
        "board_match": False,
        "advertisement_match": False,
        "vacancy_match": False,
        "matched_fields": [],
        "mismatched_fields": [],
        "status": "Insufficient evidence",
        "official_notification_confirmed": False
    }

    if not domain["is_official_domain"]:
        comparison["status"] = "Official source not established"
        return comparison

    # Compare recruitment boards
    claim_boards = set(claim["recruitment_board"])
    notice_boards = set(notice["recruitment_board"])

    if claim_boards and notice_boards:
        if claim_boards.intersection(notice_boards):
            comparison["board_match"] = True
            comparison["matched_fields"].append("Recruitment board")
        else:
            comparison["mismatched_fields"].append("Recruitment board")

    # Compare advertisement numbers
    claim_ads = set(claim["advertisement_numbers"])
    notice_ads = set(notice["advertisement_numbers"])

    if claim_ads and notice_ads:
        if claim_ads.intersection(notice_ads):
            comparison["advertisement_match"] = True
            comparison["matched_fields"].append("Advertisement number")
        else:
            comparison["mismatched_fields"].append("Advertisement number")

    # Extract vacancy counts using contextual patterns
    def extract_vacancy_counts(text, existing_values):
        counts = set()

        # Include values already extracted by the existing function
        for value in existing_values:
            digits = re.sub(r"[^\d]", "", str(value))
            if digits:
                counts.add(str(int(digits)))

        patterns = [
            r"\b([\d,]+)\s*(?:vacancies|vacancy|posts|post)\b",
            r"\b(?:vacancies|vacancy|posts|post)\s*"
            r"(?:available|are|of|:|-)?\s*([\d,]+)\b",
            r"\btotal\s+(?:number\s+of\s+)?(?:vacancies|posts)"
            r"\s*[:\-]?\s*([\d,]+)\b",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)

            for value in matches:
                digits = value.replace(",", "")
                if digits:
                    counts.add(str(int(digits)))

        return counts

    claim_vacancies = extract_vacancy_counts(
        claim_text,
        claim["vacancy_numbers"]
    )

    notice_vacancies = extract_vacancy_counts(
        official_notice_text,
        notice["vacancy_numbers"]
    )

    if claim_vacancies and notice_vacancies:
        if claim_vacancies.intersection(notice_vacancies):
            comparison["vacancy_match"] = True
            comparison["matched_fields"].append("Vacancy information")
        else:
            comparison["mismatched_fields"].append("Vacancy information")

    # Determine final comparison status
    if comparison["mismatched_fields"]:
        comparison["status"] = "Mismatch found - manual review required"

    elif (
        comparison["board_match"]
        and comparison["advertisement_match"]
        and comparison["vacancy_match"]
    ):
        comparison["status"] = "All checked fields matched"
        comparison["official_notification_confirmed"] = True

    elif comparison["board_match"]:
        comparison["status"] = "Partial match - more evidence required"

    else:
        comparison["status"] = "Insufficient evidence to confirm a match"

    return comparison
