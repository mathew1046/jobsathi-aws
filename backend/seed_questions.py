"""
seed_questions.py
=================
Populates the `onboarding_questions` and `question_translations` tables.

Run once (safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING):

    python seed_questions.py

Requirements:
    pip install asyncpg python-dotenv
    DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD must be set
    (via environment variables or a .env file in the same directory)

What this does:
    1. Inserts 20 rows into `onboarding_questions`
    2. For each question, inserts one row per supported language into
       `question_translations` (10 languages × 20 questions = 200 rows)

Supported languages:
    hi  Hindi       ta  Tamil       te  Telugu
    mr  Marathi     bn  Bengali     gu  Gujarati
    kn  Kannada     pa  Punjabi     ml  Malayalam
    en  English (Indian)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


# ─── 20 Onboarding Questions ──────────────────────────────────────────────────
#
# Each question is designed around what the article describes as the core data
# JobSathi must collect from a blue-collar worker through *conversation*, not forms.
#
# Fields:
#   index           0-based position in the conversation flow
#   field_key       the column in worker_profiles this answer populates
#   extraction_hint instruction to Bedrock on how to parse the free-form answer
#   translations    dict of language_code → question text

QUESTIONS = [
    {
        "index": 0,
        "field_key": "primary_skill",
        "extraction_hint": (
            "Extract the primary skill/trade as a short lowercase English string. "
            "Examples: tile_work, painting, electrical, plumbing, driving, masonry, "
            "carpentry, welding, domestic_work, security, factory_work, whitewash, "
            "waterproofing. Return a single string."
        ),
        "translations": {
            "hi": "आप कौन सा काम करते हैं? जैसे टाइल का काम, पेंटिंग, बिजली का काम, प्लंबिंग, ड्राइविंग?",
            "ta": "நீங்கள் என்ன வேலை செய்கிறீர்கள்? உதாரணமாக: டைல் வேலை, பெயிண்டிங், மின் வேலை, பம்பிங், ஓட்டுனர்?",
            "te": "మీరు ఏ పని చేస్తారు? ఉదాహరణకు: టైల్ పని, పెయింటింగ్, విద్యుత్ పని, ప్లంబింగ్, డ్రైవింగ్?",
            "mr": "तुम्ही कोणत्या प्रकारचे काम करता? उदा. टाईल काम, पेंटिंग, वीज काम, प्लंबिंग, ड्रायव्हिंग?",
            "bn": "আপনি কী ধরনের কাজ করেন? যেমন টাইলস কাজ, রং করা, বিদ্যুৎ কাজ, প্লাম্বিং, ড্রাইভিং?",
            "gu": "તમે કયા પ્રકારનું કામ કરો છો? જેમ કે ટાઇલ કામ, પેઇન્ટિંગ, ઇલેક્ટ્રિક કામ, પ્લમ્બિંગ, ડ્રાઇવિંગ?",
            "kn": "ನೀವು ಯಾವ ರೀತಿಯ ಕೆಲಸ ಮಾಡುತ್ತೀರಿ? ಉದಾ: ಟೈಲ್ ಕೆಲಸ, ಪೇಂಟಿಂಗ್, ವಿದ್ಯುತ್ ಕೆಲಸ, ಪ್ಲಂಬಿಂಗ್, ಚಾಲನೆ?",
            "pa": "ਤੁਸੀਂ ਕਿਹੋ ਜਿਹਾ ਕੰਮ ਕਰਦੇ ਹੋ? ਜਿਵੇਂ ਟਾਈਲ ਦਾ ਕੰਮ, ਪੇਂਟਿੰਗ, ਬਿਜਲੀ ਦਾ ਕੰਮ, ਪਲੰਬਿੰਗ, ਡਰਾਈਵਿੰਗ?",
            "ml": "നിങ്ങൾ എന്ത് ജോലി ചെയ്യുന്നു? ഉദാഹരണം: ടൈൽ പണി, പെയിന്റിംഗ്, ഇലക്ട്രിക്കൽ, പ്ലംബിംഗ്, ഡ്രൈവിംഗ്?",
            "en": "What kind of work do you do? For example: tile work, painting, electrical, plumbing, driving?",
        },
    },
    {
        "index": 1,
        "field_key": "secondary_skills",
        "extraction_hint": (
            "Extract a list of additional skills beyond the primary skill. "
            "Return as a JSON array of short lowercase strings. "
            'Example: ["whitewash", "waterproofing"]. Return [] if none mentioned.'
        ),
        "translations": {
            "hi": "क्या आप कोई और काम भी करते हैं? जैसे व्हाइटवाश, वाटरप्रूफिंग, या कोई और?",
            "ta": "நீங்கள் வேறு ஏதாவது வேலை செய்கிறீர்களா? உதாரணமாக வெள்ளை பூச்சு, வாட்டர்ப்ரூஃபிங்?",
            "te": "మీరు ఇంకా ఏదైనా పని చేస్తారా? ఉదాహరణకు వైట్‌వాష్, వాటర్‌ప్రూఫింగ్?",
            "mr": "तुम्ही आणखी काही काम करता का? जसे व्हाइटवॉश, वॉटरप्रूफिंग?",
            "bn": "আপনি কি আরো কোনো কাজ করেন? যেমন হোয়াইটওয়াশ, ওয়াটারপ্রুফিং?",
            "gu": "શું તમે બીજું કોઈ કામ પણ કરો છો? જેમ કે વ્હાઇટવૉશ, વૉટરપ્રૂફિંગ?",
            "kn": "ನೀವು ಬೇರೆ ಯಾವುದಾದರೂ ಕೆಲಸ ಮಾಡುತ್ತೀರಾ? ಉದಾ: ವೈಟ್‌ವಾಶ್, ವಾಟರ್‌ಪ್ರೂಫಿಂಗ್?",
            "pa": "ਕੀ ਤੁਸੀਂ ਹੋਰ ਕੋਈ ਕੰਮ ਵੀ ਕਰਦੇ ਹੋ? ਜਿਵੇਂ ਵ੍ਹਾਈਟਵਾਸ਼, ਵਾਟਰਪਰੂਫਿੰਗ?",
            "ml": "നിങ്ങൾ മറ്റ് എന്തെങ്കിലും ജോലി ചെയ്യുന്നുണ്ടോ? ഉദാഹരണം: വൈറ്റ്‌വാഷ്, വാട്ടർപ്രൂഫിംഗ്?",
            "en": "Do you do any other type of work as well? For example whitewash, waterproofing, or anything else?",
        },
    },
    {
        "index": 2,
        "field_key": "years_experience",
        "extraction_hint": (
            "Extract the total years of experience as an integer. "
            "If the person says 'around 5' or '3-4 years', use the midpoint. "
            "If they say 'many years' without a number, return 5 as a default."
        ),
        "translations": {
            "hi": "आप कितने सालों से यह काम कर रहे हैं?",
            "ta": "நீங்கள் எத்தனை ஆண்டுகளாக இந்த வேலை செய்கிறீர்கள்?",
            "te": "మీరు ఎన్ని సంవత్సరాలుగా ఈ పని చేస్తున్నారు?",
            "mr": "तुम्ही किती वर्षांपासून हे काम करत आहात?",
            "bn": "আপনি কত বছর ধরে এই কাজ করছেন?",
            "gu": "તમે કેટલા વર્ષોથી આ કામ કરો છો?",
            "kn": "ನೀವು ಎಷ್ಟು ವರ್ಷಗಳಿಂದ ಈ ಕೆಲಸ ಮಾಡುತ್ತಿದ್ದೀರಿ?",
            "pa": "ਤੁਸੀਂ ਕਿੰਨੇ ਸਾਲਾਂ ਤੋਂ ਇਹ ਕੰਮ ਕਰ ਰਹੇ ਹੋ?",
            "ml": "നിങ്ങൾ എത്ര വർഷമായി ഈ ജോലി ചെയ്യുന്നു?",
            "en": "How many years have you been doing this work?",
        },
    },
    {
        "index": 3,
        "field_key": "city",
        "extraction_hint": (
            "Extract the city name in English, properly capitalized. "
            "Examples: Pune, Nagpur, Mumbai, Delhi, Bengaluru, Chennai, Hyderabad."
        ),
        "translations": {
            "hi": "आप अभी किस शहर में रहते हैं?",
            "ta": "நீங்கள் இப்போது எந்த நகரத்தில் வசிக்கிறீர்கள்?",
            "te": "మీరు ప్రస్తుతం ఏ నగరంలో నివసిస్తున్నారు?",
            "mr": "तुम्ही सध्या कोणत्या शहरात राहता?",
            "bn": "আপনি এখন কোন শহরে থাকেন?",
            "gu": "તમે અત્યારે કયા શહેરમાં રહો છો?",
            "kn": "ನೀವು ಈಗ ಯಾವ ನಗರದಲ್ಲಿ ವಾಸಿಸುತ್ತಿದ್ದೀರಿ?",
            "pa": "ਤੁਸੀਂ ਹੁਣ ਕਿਸ ਸ਼ਹਿਰ ਵਿੱਚ ਰਹਿੰਦੇ ਹੋ?",
            "ml": "നിങ്ങൾ ഇപ്പോൾ ഏത് നഗരത്തിലാണ് താമസിക്കുന്നത്?",
            "en": "Which city do you currently live in?",
        },
    },
    {
        "index": 4,
        "field_key": "district",
        "extraction_hint": (
            "Extract the area, neighborhood, locality, or district name as a string. "
            "Keep it as the person said it — do not translate or normalize."
        ),
        "translations": {
            "hi": "शहर का कौन सा इलाका या मोहल्ला?",
            "ta": "நகரத்தின் எந்த பகுதி அல்லது தெரு?",
            "te": "నగరంలో ఏ ప్రాంతం లేదా కాలనీ?",
            "mr": "शहरातील कोणता भाग किंवा मोहल्ला?",
            "bn": "শহরের কোন এলাকা বা মহল্লা?",
            "gu": "શહેરનો કયો વિસ્તાર અથવા મહોલ્લો?",
            "kn": "ನಗರದ ಯಾವ ಪ್ರದೇಶ ಅಥವಾ ಬಡಾವಣೆ?",
            "pa": "ਸ਼ਹਿਰ ਦਾ ਕਿਹੜਾ ਇਲਾਕਾ ਜਾਂ ਮੁਹੱਲਾ?",
            "ml": "നഗരത്തിലെ ഏത് ഏരിയ അല്ലെങ്കിൽ കോളനി?",
            "en": "Which area or neighborhood of the city do you live in?",
        },
    },
    {
        "index": 5,
        "field_key": "state",
        "extraction_hint": (
            "Extract the Indian state name in English, properly capitalized. "
            "Examples: Maharashtra, Karnataka, Bihar, Uttar Pradesh, Tamil Nadu."
        ),
        "translations": {
            "hi": "आप किस राज्य में हैं? जैसे महाराष्ट्र, बिहार, उत्तर प्रदेश?",
            "ta": "நீங்கள் எந்த மாநிலத்தில் இருக்கிறீர்கள்? உதாரணமாக தமிழ்நாடு, மகாராஷ்டிரா?",
            "te": "మీరు ఏ రాష్ట్రంలో ఉన్నారు? ఉదాహరణకు తెలంగాణ, మహారాష్ట్ర, కర్ణాటక?",
            "mr": "तुम्ही कोणत्या राज्यात आहात? जसे महाराष्ट्र, कर्नाटक?",
            "bn": "আপনি কোন রাজ্যে আছেন? যেমন পশ্চিমবঙ্গ, বিহার?",
            "gu": "તમે કયા રાજ્યમાં છો? જેમ કે ગુજરાત, મહારાષ્ટ્ર?",
            "kn": "ನೀವು ಯಾವ ರಾಜ್ಯದಲ್ಲಿದ್ದೀರಿ? ಉದಾ: ಕರ್ನಾಟಕ, ಮಹಾರಾಷ್ಟ್ರ?",
            "pa": "ਤੁਸੀਂ ਕਿਸ ਰਾਜ ਵਿੱਚ ਹੋ? ਜਿਵੇਂ ਪੰਜਾਬ, ਮਹਾਰਾਸ਼ਟਰ?",
            "ml": "നിങ്ങൾ ഏത് സംസ്ഥാനത്താണ്? ഉദാഹരണം: കേരളം, മഹാരാഷ്ട്ര?",
            "en": "Which state are you in? For example Maharashtra, Bihar, Uttar Pradesh?",
        },
    },
    {
        "index": 6,
        "field_key": "willing_to_relocate",
        "extraction_hint": (
            "Return true if the person is willing to travel to or work in another city. "
            "Return false if they want to stay local only."
        ),
        "translations": {
            "hi": "क्या आप दूसरे शहर में जाकर भी काम कर सकते हैं?",
            "ta": "நீங்கள் வேறு நகரத்திற்கு சென்று வேலை செய்ய தயாரா?",
            "te": "మీరు వేరే నగరానికి వెళ్ళి పని చేయగలరా?",
            "mr": "तुम्ही दुसऱ्या शहरात जाऊन काम करण्यास तयार आहात का?",
            "bn": "আপনি কি অন্য শহরে গিয়ে কাজ করতে পারবেন?",
            "gu": "શું તમે બીજા શહેરમાં જઈને કામ કરી શકો?",
            "kn": "ನೀವು ಬೇರೆ ನಗರಕ್ಕೆ ಹೋಗಿ ಕೆಲಸ ಮಾಡಲು ತಯಾರಿದ್ದೀರಾ?",
            "pa": "ਕੀ ਤੁਸੀਂ ਦੂਜੇ ਸ਼ਹਿਰ ਵਿੱਚ ਜਾ ਕੇ ਕੰਮ ਕਰ ਸਕਦੇ ਹੋ?",
            "ml": "മറ്റൊരു നഗരത്തിൽ പോയി ജോലി ചെയ്യാൻ നിങ്ങൾ തയ്യാറാണോ?",
            "en": "Are you willing to travel to or work in another city?",
        },
    },
    {
        "index": 7,
        "field_key": "max_travel_km",
        "extraction_hint": (
            "Extract the maximum distance the person is willing to travel, as an integer in kilometers. "
            "If they say 'nearby' or 'local area', return 20. "
            "If they say 'within the city', return 50. "
            "If they say 'same state', return 300. "
            "If they say 'anywhere in India' or similar, return 2000."
        ),
        "translations": {
            "hi": "आप कितने किलोमीटर तक जाने के लिए तैयार हैं?",
            "ta": "நீங்கள் எவ்வளவு கிலோமீட்டர் தூரம் பயணிக்க தயாரா?",
            "te": "మీరు ఎంత కిలోమీటర్ల వరకు వెళ్ళగలరు?",
            "mr": "तुम्ही किती किलोमीटर प्रवास करण्यास तयार आहात?",
            "bn": "আপনি কত কিলোমিটার পর্যন্ত যেতে পারবেন?",
            "gu": "તમે કેટલા કિલોમીટર સુધી જઈ શકો?",
            "kn": "ನೀವು ಎಷ್ಟು ಕಿಲೋಮೀಟರ್ ಪ್ರಯಾಣಿಸಲು ತಯಾರಿದ್ದೀರಿ?",
            "pa": "ਤੁਸੀਂ ਕਿੰਨੇ ਕਿਲੋਮੀਟਰ ਤੱਕ ਜਾਣ ਲਈ ਤਿਆਰ ਹੋ?",
            "ml": "നിങ്ങൾ എത്ര കിലോമീറ്റർ വരെ സഞ്ചരിക്കാൻ തയ്യാറാണ്?",
            "en": "How far are you willing to travel for work? You can say in kilometers or describe it.",
        },
    },
    {
        "index": 8,
        "field_key": "availability",
        "extraction_hint": (
            "Return one of these exact values based on their answer: "
            "'immediate' if they are available now or looking for work now, "
            "'employed' if they are currently working, "
            "'1_week' if they can start within a week, "
            "'1_month' if they can start within a month."
        ),
        "translations": {
            "hi": "आप अभी काम कर रहे हैं, या काम की तलाश में हैं?",
            "ta": "நீங்கள் இப்போது வேலை செய்கிறீர்களா, இல்லை வேலை தேடுகிறீர்களா?",
            "te": "మీరు ఇప్పుడు పని చేస్తున్నారా, లేదా పని వెతుకుతున్నారా?",
            "mr": "तुम्ही सध्या काम करत आहात का, की नोकरी शोधत आहात?",
            "bn": "আপনি কি এখন কাজ করছেন, নাকি কাজ খুঁজছেন?",
            "gu": "શું તમે અત્યારે કામ કરી રહ્યા છો, કે નોકરી શોધી રહ્યા છો?",
            "kn": "ನೀವು ಈಗ ಕೆಲಸ ಮಾಡುತ್ತಿದ್ದೀರಾ, ಅಥವಾ ಕೆಲಸ ಹುಡುಕುತ್ತಿದ್ದೀರಾ?",
            "pa": "ਕੀ ਤੁਸੀਂ ਹੁਣ ਕੰਮ ਕਰ ਰਹੇ ਹੋ, ਜਾਂ ਕੰਮ ਲੱਭ ਰਹੇ ਹੋ?",
            "ml": "നിങ്ങൾ ഇപ്പോൾ ജോലി ചെയ്യുകയാണോ, അതോ ജോലി തിരയുകയാണോ?",
            "en": "Are you currently working somewhere, or are you looking for work right now?",
        },
    },
    {
        "index": 9,
        "field_key": "expected_daily_wage",
        "extraction_hint": (
            "Extract the expected daily wage as an integer in Indian Rupees. "
            "If they give a monthly figure, divide by 25 to get daily. "
            "If they say 'market rate' or are unsure, return 500 as a reasonable default."
        ),
        "translations": {
            "hi": "आप एक दिन के काम के लिए कितने रुपये की उम्मीद करते हैं?",
            "ta": "ஒரு நாள் வேலைக்கு எவ்வளவு ரூபாய் எதிர்பார்க்கிறீர்கள்?",
            "te": "మీరు ఒక రోజు పనికి ఎంత రూపాయలు ఆశిస్తున్నారు?",
            "mr": "तुम्हाला एका दिवसाच्या कामासाठी किती रुपये हवे आहेत?",
            "bn": "আপনি একদিনের কাজের জন্য কত টাকা আশা করেন?",
            "gu": "તમે એક દિવસના કામ માટે કેટલા રૂપિયા અપેક્ષા રાખો છો?",
            "kn": "ನೀವು ಒಂದು ದಿನದ ಕೆಲಸಕ್ಕೆ ಎಷ್ಟು ರೂಪಾಯಿ ನಿರೀಕ್ಷಿಸುತ್ತಿದ್ದೀರಿ?",
            "pa": "ਤੁਸੀਂ ਇੱਕ ਦਿਨ ਦੇ ਕੰਮ ਲਈ ਕਿੰਨੇ ਰੁਪਏ ਦੀ ਉਮੀਦ ਕਰਦੇ ਹੋ?",
            "ml": "ഒരു ദിവസത്തെ ജോലിക്ക് നിങ്ങൾ എത്ര രൂപ പ്രതീക്ഷിക്കുന്നു?",
            "en": "How much do you expect to earn per day, in rupees?",
        },
    },
    {
        "index": 10,
        "field_key": "work_type",
        "extraction_hint": (
            "Return exactly one of: 'daily_wage', 'contract', 'permanent', or 'any'. "
            "Map their answer: daily/rozana → daily_wage, contract/theka → contract, "
            "permanent/pakki naukri → permanent, no preference/any → any."
        ),
        "translations": {
            "hi": "आप किस तरह का काम पसंद करते हैं — रोज़ का काम (दिहाड़ी), कॉन्ट्रैक्ट, या पक्की नौकरी?",
            "ta": "நீங்கள் எந்த வகை வேலையை விரும்புகிறீர்கள் — தினக்கூலி, ஒப்பந்தம், அல்லது நிரந்தர வேலை?",
            "te": "మీకు ఏ రకమైన పని ఇష్టం — రోజువారీ వేతనం, కాంట్రాక్ట్, లేదా శాశ్వత ఉద్యోగం?",
            "mr": "तुम्हाला कोणत्या प्रकारचे काम आवडते — रोजंदारी, कंत्राट, की कायमची नोकरी?",
            "bn": "আপনি কোন ধরনের কাজ পছন্দ করেন — দৈনিক মজুরি, চুক্তি, নাকি স্থায়ী চাকরি?",
            "gu": "તમને કયા પ્રકારનું કામ ગમે છે — રોજિંદું, કોન્ટ્રેક્ટ, કે કાયમી નોકરી?",
            "kn": "ನಿಮಗೆ ಯಾವ ರೀತಿಯ ಕೆಲಸ ಇಷ್ಟ — ದಿನಗೂಲಿ, ಕಾಂಟ್ರ್ಯಾಕ್ಟ್, ಅಥವಾ ಶಾಶ್ವತ ಉದ್ಯೋಗ?",
            "pa": "ਤੁਸੀਂ ਕਿਸ ਤਰ੍ਹਾਂ ਦਾ ਕੰਮ ਪਸੰਦ ਕਰਦੇ ਹੋ — ਰੋਜ਼ਾਨਾ ਮਜ਼ਦੂਰੀ, ਕੰਟਰੈਕਟ, ਜਾਂ ਪੱਕੀ ਨੌਕਰੀ?",
            "ml": "നിങ്ങൾക്ക് ഏത് തരം ജോലി ഇഷ്ടമാണ് — ദൈനംദിന കൂലി, കരാർ, അതോ സ്ഥിര ജോലി?",
            "en": "Do you prefer daily wage work, contract work, or a permanent job?",
        },
    },
    {
        "index": 11,
        "field_key": "preferred_hours",
        "extraction_hint": (
            "Extract preferred working hours as a short string. "
            "Examples: '8am-5pm', 'morning shift', 'flexible', 'full_day', '6am-2pm'. "
            "If no preference, return 'flexible'."
        ),
        "translations": {
            "hi": "आप कितने घंटे काम करना पसंद करते हैं और कौन सा समय?",
            "ta": "நீங்கள் எத்தனை மணி நேரம் வேலை செய்ய விரும்புகிறீர்கள், எந்த நேரத்தில்?",
            "te": "మీరు ఎన్ని గంటలు పని చేయాలని ఇష్టపడతారు, ఏ సమయంలో?",
            "mr": "तुम्हाला किती तास काम करणे आवडते आणि कोणत्या वेळी?",
            "bn": "আপনি কত ঘন্টা কাজ করতে পছন্দ করেন এবং কোন সময়ে?",
            "gu": "તમે કેટલા કલાક કામ કરવાનું પસંદ કરો છો અને કયા સમયે?",
            "kn": "ನೀವು ಎಷ್ಟು ಗಂಟೆ ಕೆಲಸ ಮಾಡಲು ಇಷ್ಟಪಡುತ್ತೀರಿ ಮತ್ತು ಯಾವ ಸಮಯದಲ್ಲಿ?",
            "pa": "ਤੁਸੀਂ ਕਿੰਨੇ ਘੰਟੇ ਕੰਮ ਕਰਨਾ ਪਸੰਦ ਕਰਦੇ ਹੋ ਅਤੇ ਕਿਸ ਸਮੇਂ?",
            "ml": "നിങ്ങൾ എത്ര മണിക്കൂർ ജോലി ചെയ്യാൻ ഇഷ്ടപ്പെടുന്നു, ഏത് സമയത്ത്?",
            "en": "How many hours do you prefer to work, and at what time of day?",
        },
    },
    {
        "index": 12,
        "field_key": "name",
        "extraction_hint": (
            "Extract the person's name as a string. "
            "If they say they don't want to share, or give a refusal, return null."
        ),
        "translations": {
            "hi": "आपका नाम क्या है? यह बताना ज़रूरी नहीं है, आप चाहें तो छोड़ सकते हैं।",
            "ta": "உங்கள் பெயர் என்ன? இது விருப்பமானது — விரும்பவில்லை என்றால் தவிர்க்கலாம்.",
            "te": "మీ పేరు ఏమిటి? ఇది ఐచ్ఛికం — చెప్పాలని అనిపించకపోతే వదిలేయవచ్చు.",
            "mr": "तुमचे नाव काय आहे? हे सांगणे आवश्यक नाही — इच्छा नसल्यास सोडू शकता.",
            "bn": "আপনার নাম কী? এটি ঐচ্ছিক — না বলতে চাইলে এড়িয়ে যেতে পারেন।",
            "gu": "તમારું નામ શું છે? આ વૈકલ્પિક છે — ન કહેવું હોય તો છોડી શકો.",
            "kn": "ನಿಮ್ಮ ಹೆಸರು ಏನು? ಇದು ಐಚ್ಛಿಕ — ಹೇಳಲು ಇಷ್ಟವಿಲ್ಲದಿದ್ದರೆ ಬಿಡಬಹುದು.",
            "pa": "ਤੁਹਾਡਾ ਨਾਮ ਕੀ ਹੈ? ਇਹ ਵਿਕਲਪਿਕ ਹੈ — ਦੱਸਣਾ ਨਹੀਂ ਚਾਹੁੰਦੇ ਤਾਂ ਛੱਡ ਸਕਦੇ ਹੋ।",
            "ml": "നിങ്ങളുടെ പേര് എന്താണ്? ഇത് ഐച്ഛികമാണ് — പറയണമെന്നില്ലെങ്കിൽ ഒഴിവാക്കാം.",
            "en": "What is your name? This is optional — you don't have to share if you prefer not to.",
        },
    },
    {
        "index": 13,
        "field_key": "biggest_project",
        "extraction_hint": (
            "Extract a brief description of the biggest or most significant project "
            "they have worked on. Return as a string. This goes into the resume work history."
        ),
        "translations": {
            "hi": "आपने अब तक का सबसे बड़ा काम या सबसे बड़ी साइट कौन सी थी?",
            "ta": "இதுவரை நீங்கள் செய்த மிகப் பெரிய திட்டம் அல்லது தளம் எது?",
            "te": "మీరు ఇప్పటి వరకు చేసిన అతి పెద్ద ప్రాజెక్ట్ లేదా సైట్ ఏది?",
            "mr": "आतापर्यंत तुम्ही केलेली सर्वात मोठी साइट किंवा काम कोणते होते?",
            "bn": "এখন পর্যন্ত আপনি যে সবচেয়ে বড় কাজ বা সাইটে কাজ করেছেন সেটা কী?",
            "gu": "અત્યાર સુધી તમે સૌથી મોટી સાઇટ અથવા કામ ક્યું કર્યું?",
            "kn": "ಇದುವರೆಗೆ ನೀವು ಕೆಲಸ ಮಾಡಿದ ಅತ್ಯಂತ ದೊಡ್ಡ ಪ್ರಾಜೆಕ್ಟ್ ಅಥವಾ ಸೈಟ್ ಯಾವುದು?",
            "pa": "ਹੁਣ ਤੱਕ ਤੁਸੀਂ ਸਭ ਤੋਂ ਵੱਡਾ ਕੰਮ ਜਾਂ ਸਾਈਟ ਕਿਹੜੀ ਕੀਤੀ ਹੈ?",
            "ml": "ഇതുവരെ നിങ്ങൾ ജോലി ചെയ്ത ഏറ്റവും വലിയ പ്രോജക്ട് അല്ലെങ്കിൽ സൈറ്റ് ഏതാണ്?",
            "en": "What is the biggest project or construction site you have worked on so far?",
        },
    },
    {
        "index": 14,
        "field_key": "previous_employer",
        "extraction_hint": (
            "Extract the name of any company, contractor, or employer they have worked for. "
            "Return as a string. Return null if they have only worked informally or cannot name one."
        ),
        "translations": {
            "hi": "क्या आपने किसी कंपनी या बड़े ठेकेदार के साथ काम किया है? कोई नाम याद है?",
            "ta": "நீங்கள் ஏதாவது நிறுவனம் அல்லது பெரிய ஒப்பந்தக்காரருடன் வேலை செய்தீர்களா?",
            "te": "మీరు ఏదైనా కంపెనీ లేదా పెద్ద కాంట్రాక్టర్‌తో పని చేశారా?",
            "mr": "तुम्ही एखाद्या कंपनी किंवा मोठ्या कंत्राटदारासोबत काम केले आहे का?",
            "bn": "আপনি কি কোনো কোম্পানি বা বড় ঠিকাদারের সাথে কাজ করেছেন?",
            "gu": "શું તમે કોઈ કંપની અથવા મોટા ઠેકેદાર સાથે કામ કર્યું છે?",
            "kn": "ನೀವು ಯಾವಾದರೂ ಕಂಪನಿ ಅಥವಾ ದೊಡ್ಡ ಗುತ್ತಿಗೆದಾರರ ಜೊತೆ ಕೆಲಸ ಮಾಡಿದ್ದೀರಾ?",
            "pa": "ਕੀ ਤੁਸੀਂ ਕਿਸੇ ਕੰਪਨੀ ਜਾਂ ਵੱਡੇ ਠੇਕੇਦਾਰ ਨਾਲ ਕੰਮ ਕੀਤਾ ਹੈ?",
            "ml": "നിങ്ങൾ ഏതെങ്കിലും കമ്പനി അല്ലെങ്കിൽ വലിയ കോൺട്രാക്ടറുടെ കീഴിൽ ജോലി ചെയ്തിട്ടുണ്ടോ?",
            "en": "Have you worked with any company or well-known contractor? Do you remember the name?",
        },
    },
    {
        "index": 15,
        "field_key": "certifications",
        "extraction_hint": (
            "Extract any certificates or formal training programs as a JSON array of strings. "
            'Examples: ["ITI", "Skill India", "NSDC"]. Return [] if none.'
        ),
        "translations": {
            "hi": "क्या आपके पास कोई सर्टिफिकेट या ट्रेनिंग है? जैसे आईटीआई, स्किल इंडिया?",
            "ta": "உங்களிடம் ஏதாவது சான்றிதழ் அல்லது பயிற்சி உள்ளதா? உதாரணமாக ITI, Skill India?",
            "te": "మీకు ఏదైనా సర్టిఫికేట్ లేదా శిక్షణ ఉందా? ఉదాహరణకు ITI, స్కిల్ ఇండియా?",
            "mr": "तुमच्याकडे काही प्रमाणपत्र किंवा प्रशिक्षण आहे का? जसे ITI, Skill India?",
            "bn": "আপনার কি কোনো সার্টিফিকেট বা প্রশিক্ষণ আছে? যেমন ITI, স্কিল ইন্ডিয়া?",
            "gu": "શું તમારી પાસે કોઈ પ્રમાણપત્ર અથવા તાલીમ છે? જેમ કે ITI, Skill India?",
            "kn": "ನಿಮ್ಮ ಬಳಿ ಯಾವುದಾದರೂ ಪ್ರಮಾಣಪತ್ರ ಅಥವಾ ತರಬೇತಿ ಇದೆಯಾ? ಉದಾ: ITI, Skill India?",
            "pa": "ਕੀ ਤੁਹਾਡੇ ਕੋਲ ਕੋਈ ਸਰਟੀਫਿਕੇਟ ਜਾਂ ਟਰੇਨਿੰਗ ਹੈ? ਜਿਵੇਂ ITI, Skill India?",
            "ml": "നിങ്ങൾക്ക് ഏതെങ്കിലും സർട്ടിഫിക്കറ്റ് അല്ലെങ്കിൽ പരിശീലനം ഉണ്ടോ? ഉദാഹരണം: ITI, Skill India?",
            "en": "Do you have any certificates or training? For example ITI, Skill India, NSDC courses?",
        },
    },
    {
        "index": 16,
        "field_key": "tools_equipment",
        "extraction_hint": (
            "Extract a list of tools or equipment the person knows how to use. "
            "Return as a JSON array of strings. "
            'Examples: ["drill machine", "angle grinder", "welding machine"]. Return [] if none.'
        ),
        "translations": {
            "hi": "आप कौन से औज़ार या मशीन चलाना जानते हैं?",
            "ta": "நீங்கள் எந்த கருவிகள் அல்லது இயந்திரங்களை இயக்க தெரியும்?",
            "te": "మీకు ఏ పనిముట్లు లేదా యంత్రాలు ఉపయోగించడం తెలుసు?",
            "mr": "तुम्हाला कोणती हत्यारे किंवा यंत्रे चालवता येतात?",
            "bn": "আপনি কোন যন্ত্রপাতি বা সরঞ্জাম চালাতে জানেন?",
            "gu": "તમે કઈ ઓજારો અથવા મશીનો ચલાવી શકો છો?",
            "kn": "ನೀವು ಯಾವ ಉಪಕರಣಗಳು ಅಥವಾ ಯಂತ್ರಗಳನ್ನು ಚಲಾಯಿಸಬಲ್ಲಿರಿ?",
            "pa": "ਤੁਸੀਂ ਕਿਹੜੇ ਔਜ਼ਾਰ ਜਾਂ ਮਸ਼ੀਨ ਚਲਾਉਣਾ ਜਾਣਦੇ ਹੋ?",
            "ml": "നിങ്ങൾക്ക് ഏതെല്ലാം ഉപകരണങ്ങൾ അല്ലെങ്കിൽ യന്ത്രങ്ങൾ ഉപയോഗിക്കാൻ അറിയാം?",
            "en": "What tools or equipment do you know how to use?",
        },
    },
    {
        "index": 17,
        "field_key": "special_skills",
        "extraction_hint": (
            "Extract any special or unique skills, strengths, or qualities that would "
            "make this worker stand out to an employer. Return as a short descriptive string. "
            "Return null if they say nothing notable."
        ),
        "translations": {
            "hi": "आपके काम में कोई ऐसी खास बात है जो नियोक्ता को पता होनी चाहिए?",
            "ta": "உங்கள் வேலையில் முதலாளிக்கு தெரிந்திருக்க வேண்டிய சிறப்பு தகவல் ஏதாவது உண்டா?",
            "te": "మీ పనిలో యజమానికి తెలియవలసిన ప్రత్యేకత ఏమైనా ఉందా?",
            "mr": "तुमच्या कामात असे काही खास आहे का जे नियोक्त्याला माहित असणे आवश्यक आहे?",
            "bn": "আপনার কাজে এমন কিছু বিশেষ বিষয় আছে কি যা নিয়োগকর্তার জানা দরকার?",
            "gu": "તમારા કામમાં એવી કોઈ ખાસ વાત છે જે નોકરી આપનારને ખબર હોવી જોઈએ?",
            "kn": "ನಿಮ್ಮ ಕೆಲಸದಲ್ಲಿ ಉದ್ಯೋಗದಾತರಿಗೆ ತಿಳಿದಿರಬೇಕಾದ ಯಾವುದಾದರೂ ವಿಶೇಷ ಸಂಗತಿ ಇದೆಯಾ?",
            "pa": "ਤੁਹਾਡੇ ਕੰਮ ਵਿੱਚ ਕੋਈ ਅਜਿਹੀ ਖਾਸ ਗੱਲ ਹੈ ਜੋ ਨੌਕਰੀ ਦੇਣ ਵਾਲੇ ਨੂੰ ਪਤਾ ਹੋਣੀ ਚਾਹੀਦੀ ਹੈ?",
            "ml": "നിങ്ങളുടെ ജോലിയിൽ നിയോഗദാതാവ് അറിഞ്ഞിരിക്കേണ്ട പ്രത്യേകമായ എന്തെങ്കിലും ഉണ്ടോ?",
            "en": "Is there anything special about your work that employers should know?",
        },
    },
    {
        "index": 18,
        "field_key": "skill_description",
        "extraction_hint": (
            "Extract 2-3 sentences the worker said describing their work, preserving their "
            "own words and style as much as possible. This goes directly into the resume. "
            "Return as a single string."
        ),
        "translations": {
            "hi": "अपने काम के बारे में दो-तीन वाक्य बोलें जो हम आपके रेज़्यूमे में लिखेंगे।",
            "ta": "உங்கள் வேலையைப் பற்றி இரண்டு-மூன்று வாக்கியங்கள் சொல்லுங்கள், அதை நாங்கள் உங்கள் விண்ணப்பத்தில் எழுதுவோம்.",
            "te": "మీ పని గురించి రెండు మూడు వాక్యాలు చెప్పండి, వాటిని మీ రెజ్యూమ్‌లో రాస్తాం.",
            "mr": "तुमच्या कामाबद्दल दोन-तीन वाक्ये सांगा, ती आम्ही तुमच्या रेझ्युमेमध्ये लिहू.",
            "bn": "আপনার কাজ সম্পর্কে দুই-তিনটি বাক্য বলুন, সেগুলো আমরা আপনার রেজুমেতে লিখব।",
            "gu": "તમારા કામ વિશે બે-ત્રણ વાક્ય કહો, અમે તે તમારા રેઝ્યૂમેમાં લખીશું.",
            "kn": "ನಿಮ್ಮ ಕೆಲಸದ ಬಗ್ಗೆ ಎರಡು-ಮೂರು ವಾಕ್ಯ ಹೇಳಿ, ಅದನ್ನು ನಾವು ನಿಮ್ಮ ರೆಸ್ಯೂಮ್‌ನಲ್ಲಿ ಬರೆಯುತ್ತೇವೆ.",
            "pa": "ਆਪਣੇ ਕੰਮ ਬਾਰੇ ਦੋ-ਤਿੰਨ ਵਾਕ ਦੱਸੋ, ਅਸੀਂ ਉਹ ਤੁਹਾਡੇ ਰੈਜ਼ਿਊਮੇ ਵਿੱਚ ਲਿਖਾਂਗੇ।",
            "ml": "നിങ്ങളുടെ ജോലിയെ കുറിച്ച് രണ്ടോ മൂന്നോ വാക്യം പറയൂ, അത് ഞങ്ങൾ നിങ്ങളുടെ റെസ്യൂമേയിൽ എഴുതും.",
            "en": "Tell us two or three sentences about your work that we can include in your resume.",
        },
    },
    {
        "index": 19,
        "field_key": "resume_consent",
        "extraction_hint": (
            "Return true if the person agrees to create a profile/resume and start job matching. "
            "Return false if they decline or want to wait."
        ),
        "translations": {
            "hi": "क्या आप चाहते हैं कि हम अभी आपका प्रोफाइल बनाएं और आपके लिए नौकरियां ढूंढें?",
            "ta": "நாங்கள் இப்போது உங்கள் சுயவிவரத்தை உருவாக்கி வேலைகளை தேட விரும்புகிறீர்களா?",
            "te": "మేము ఇప్పుడే మీ ప్రొఫైల్ తయారు చేసి ఉద్యోగాలు వెతకాలని మీకు ఇష్టమా?",
            "mr": "आम्ही आत्ता तुमचे प्रोफाइल बनवून नोकऱ्या शोधाव्यात असे तुम्हाला वाटते का?",
            "bn": "আমরা কি এখনই আপনার প্রোফাইল তৈরি করে চাকরি খুঁজব?",
            "gu": "શું તમે ઇચ્છો છો કે અમે હવે તમારો પ્રોફાઇલ બનાવી નોકરીઓ શોધીએ?",
            "kn": "ನಾವು ಈಗಲೇ ನಿಮ್ಮ ಪ್ರೊಫೈಲ್ ತಯಾರಿಸಿ ಉದ್ಯೋಗ ಹುಡುಕಲು ಇಷ್ಟವಿದೆಯಾ?",
            "pa": "ਕੀ ਤੁਸੀਂ ਚਾਹੁੰਦੇ ਹੋ ਕਿ ਅਸੀਂ ਹੁਣੇ ਤੁਹਾਡਾ ਪ੍ਰੋਫਾਈਲ ਬਣਾਈਏ ਅਤੇ ਨੌਕਰੀਆਂ ਲੱਭੀਏ?",
            "ml": "ഞങ്ങൾ ഇപ്പോൾ തന്നെ നിങ്ങളുടെ പ്രൊഫൈൽ ഉണ്ടാക്കി ജോലി തിരയട്ടെ?",
            "en": "Would you like us to create your profile and start finding jobs for you right now?",
        },
    },
]

# Language metadata
LANGUAGES = [
    ("hi", "Hindi"),
    ("ta", "Tamil"),
    ("te", "Telugu"),
    ("mr", "Marathi"),
    ("bn", "Bengali"),
    ("gu", "Gujarati"),
    ("kn", "Kannada"),
    ("pa", "Punjabi"),
    ("ml", "Malayalam"),
    ("en", "English"),
]


# ─── Seed Logic ───────────────────────────────────────────────────────────────


async def seed(conn: asyncpg.Connection):
    total_questions = 0
    total_translations = 0

    for q in QUESTIONS:
        # Upsert into onboarding_questions
        row = await conn.fetchrow(
            """
            INSERT INTO onboarding_questions (question_index, field_key, extraction_hint)
            VALUES ($1, $2, $3)
            ON CONFLICT (question_index) DO UPDATE
                SET field_key = EXCLUDED.field_key,
                    extraction_hint = EXCLUDED.extraction_hint
            RETURNING id
            """,
            q["index"],
            q["field_key"],
            q["extraction_hint"],
        )
        question_id = row["id"]
        total_questions += 1

        for lang_code, lang_name in LANGUAGES:
            text = q["translations"].get(lang_code)
            if not text:
                print(
                    f"  WARNING: No translation for question {q['index']} in {lang_code}"
                )
                continue

            await conn.execute(
                """
                INSERT INTO question_translations (question_id, language_code, language_name, question_text)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (question_id, language_code) DO UPDATE
                    SET question_text  = EXCLUDED.question_text,
                        language_name  = EXCLUDED.language_name
                """,
                question_id,
                lang_code,
                lang_name,
                text,
            )
            total_translations += 1

    print(f"\n✓ Seeded {total_questions} questions")
    print(
        f"✓ Seeded {total_translations} translations ({len(LANGUAGES)} languages × {len(QUESTIONS)} questions)"
    )


async def main():
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "jobsathi")
    db_user = os.getenv("DB_USER", "jobsathi_admin")
    db_pass = os.getenv("DB_PASSWORD", "")

    print(f"Connecting to PostgreSQL: {db_user}@{db_host}:{db_port}/{db_name} ...")

    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_pass,
    )

    try:
        await seed(conn)
    finally:
        await conn.close()

    print("\nDone. Run `python seed_questions.py` again anytime — it is idempotent.")


if __name__ == "__main__":
    asyncio.run(main())
