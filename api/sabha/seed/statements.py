"""The synthetic seed corpus: one consultation, one contested question.

Platform and gig work regulation was chosen as the default topic in
section 9 of the build instructions because it divides along axes that
are not party-political: how much protection a gig worker is owed, and
by whom, is contested inside every political coalition, not between
them.

Every statement below is synthetic: written for this build to stand in
for a real citizen submission, since no real export was available. Each
carries a `leaning` used only by seed/generator.py to decide how a
synthetic participant votes on it. `leaning` is not persisted anywhere,
because a real statement collected later would have no such label, and
the bridging score, not an author's stated intent, is what determines
whether a statement turns out to be broadly acceptable.
"""

from dataclasses import dataclass
from typing import Literal

Leaning = Literal["bridging", "worker", "platform", "regulator"]


@dataclass(frozen=True)
class SeedStatement:
    text: str
    language: Literal["en", "hi"]
    leaning: Leaning


CONSULTATION_TITLE = "Platform and gig work regulation"
CONSULTATION_QUESTION = (
    "How should platforms, gig workers, and regulators share responsibility for "
    "pay, safety, benefits, and algorithmic transparency in on-demand work?"
)

STATEMENTS: list[SeedStatement] = [
    # Employment classification
    SeedStatement(
        "Gig workers should get a formal classification, whether as employees or a "
        "new third category, so that both platforms and workers know which rules apply.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "Every gig worker who depends on a platform for most of their income should "
        "be classified as an employee with full labour protections.",
        "en",
        "worker",
    ),
    SeedStatement(
        "Forcing platforms to classify gig workers as employees will destroy the "
        "flexibility that drew most of them to this work in the first place.",
        "en",
        "platform",
    ),
    SeedStatement(
        "सरकार को गिग वर्कर्स के लिए एक स्पष्ट कानूनी श्रेणी बनानी चाहिए, ताकि विवाद की "
        "स्थिति में यह तय हो सके कि किसकी जिम्मेदारी है।",
        "hi",
        "regulator",
    ),
    # Social security and provident fund contributions
    SeedStatement(
        "Platforms and gig workers should both contribute a small, fixed percentage "
        "of each transaction to a portable social security fund.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "प्लेटफॉर्म को हर गिग वर्कर के लिए भविष्य निधि में योगदान देना अनिवार्य होना चाहिए, "
        "ठीक वैसे ही जैसे किसी भी नियमित नियोक्ता के लिए होता है।",
        "hi",
        "worker",
    ),
    SeedStatement(
        "Mandatory provident fund contributions calculated on gross transaction "
        "value ignore how thin platform margins already are.",
        "en",
        "platform",
    ),
    SeedStatement(
        "A social security cess collected directly by the labour department, rather "
        "than left to platform self-reporting, is the only way this actually gets paid.",
        "en",
        "regulator",
    ),
    # Minimum earnings and per-task pay floor
    SeedStatement(
        "हर राज्य में गिग वर्कर्स के लिए एक न्यूनतम प्रति-घंटा आय तय होनी चाहिए, जो "
        "स्थानीय जीवन-यापन की लागत के अनुसार तय हो।",
        "hi",
        "bridging",
    ),
    SeedStatement(
        "A per-task pay floor is meaningless if platforms can simply reduce the "
        "number of tasks offered to any worker who complains about it.",
        "en",
        "worker",
    ),
    SeedStatement(
        "A fixed minimum per task removes the very flexibility in pricing that lets "
        "platforms absorb slow periods without laying anyone off.",
        "en",
        "platform",
    ),
    # Algorithmic transparency
    SeedStatement(
        "Platforms should be required to explain, in plain language, why a worker's "
        "account was deactivated.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "Workers deserve to see exactly how the ranking algorithm decides which jobs "
        "they are offered, not a vague summary.",
        "en",
        "worker",
    ),
    SeedStatement(
        "एल्गोरिदम का पूरा विवरण सार्वजनिक करने से प्रतिस्पर्धी कंपनियां उसका दुरुपयोग कर "
        "सकती हैं।",
        "hi",
        "platform",
    ),
    SeedStatement(
        "An independent auditor, not the platform itself, should certify that a "
        "deactivation algorithm does not discriminate.",
        "en",
        "regulator",
    ),
    # Working hours and rest periods
    SeedStatement(
        "Platforms should build a mandatory rest reminder into the app after a "
        "certain number of continuous hours logged in.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "गिग वर्कर्स के लिए भी अधिकतम काम के घंटे तय होने चाहिए, जैसे किसी और मजदूर के लिए "
        "होते हैं।",
        "hi",
        "worker",
    ),
    SeedStatement(
        "Working hour caps assume gig work is someone's only job, when for most "
        "drivers on this platform it is a second income.",
        "en",
        "platform",
    ),
    # Grievance redressal
    SeedStatement(
        "Every platform operating at scale should be required to offer a grievance "
        "officer a worker can actually reach by phone.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "शिकायत दर्ज करने के बाद खाता बंद करने की धमकी नहीं मिलनी चाहिए, यह लिखित नीति में "
        "स्पष्ट होना चाहिए।",
        "hi",
        "worker",
    ),
    SeedStatement(
        "A state-run gig worker grievance portal, independent of any platform, is "
        "the only credible way to handle deactivation disputes.",
        "en",
        "regulator",
    ),
    # Data privacy of location and tracking data
    SeedStatement(
        "Location data collected for a delivery should be deleted once the delivery "
        "is confirmed complete, not retained indefinitely.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "Constant location tracking outside active job hours is surveillance, not safety.",
        "en",
        "worker",
    ),
    SeedStatement(
        "लोकेशन डेटा को सुरक्षित रखना धोखाधड़ी और गलत डिलीवरी दावों को रोकने के लिए जरूरी है।",
        "hi",
        "platform",
    ),
    # Right to unionise
    SeedStatement(
        "Gig workers should be free to form associations that platforms are "
        "required to negotiate with in good faith.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "Without a real right to collective bargaining, every other protection on "
        "paper is optional for the platform to honour.",
        "en",
        "worker",
    ),
    SeedStatement(
        "गिग वर्कर्स स्वतंत्र ठेकेदार हैं, इसलिए पारंपरिक यूनियन मॉडल इस काम की प्रकृति से मेल "
        "नहीं खाता।",
        "hi",
        "platform",
    ),
    # Platform liability for accidents and insurance
    SeedStatement(
        "Every platform should be required to provide baseline accident insurance "
        "for the hours a worker is logged in and available.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "काम के दौरान हुई दुर्घटना का पूरा खर्च प्लेटफॉर्म को उठाना चाहिए, चाहे वर्कर "
        "कर्मचारी हो या न हो।",
        "hi",
        "worker",
    ),
    SeedStatement(
        "Insurance costs are already built into platform commissions; a further "
        "statutory mandate just gets passed back to customers.",
        "en",
        "platform",
    ),
    # Aggregator commission caps and transparency
    SeedStatement(
        "प्लेटफॉर्म कमीशन की दर स्पष्ट रूप से हर बिल में दिखनी चाहिए, ताकि वर्कर और ग्राहक "
        "दोनों जान सकें कि पैसा कहां जा रहा है।",
        "hi",
        "bridging",
    ),
    SeedStatement(
        "Commission rates that quietly rise year over year without notice are the "
        "single biggest reason take-home pay keeps falling.",
        "en",
        "worker",
    ),
    SeedStatement(
        "A hard cap on commission ignores that different cities and service "
        "categories have very different cost structures.",
        "en",
        "platform",
    ),
    # Portability of benefits across platforms
    SeedStatement(
        "Benefit contributions should follow the worker, not the platform, so "
        "someone working across three apps keeps one continuous record.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "एक केंद्रीय, सरकार द्वारा संचालित पंजीकरण प्रणाली के बिना, कोई भी लाभ पोर्टेबिलिटी "
        "योजना व्यवहार में काम नहीं करेगी।",
        "hi",
        "regulator",
    ),
    # Termination and deactivation due process
    SeedStatement(
        "A worker should get a written reason and a chance to respond before, not "
        "after, a permanent deactivation.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "Instant deactivation with no appeal is the platform acting as judge and "
        "jury over someone's entire livelihood.",
        "en",
        "worker",
    ),
    SeedStatement(
        "तुरंत निष्क्रियता धोखाधड़ी और यात्री सुरक्षा के गंभीर मामलों के लिए जरूरी है, हर "
        "मामले में सुनवाई संभव नहीं है।",
        "hi",
        "platform",
    ),
    # Multi-apping rights
    SeedStatement(
        "Platforms should not be allowed to penalise a worker for also accepting "
        "jobs through a competing app.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "कई ऐप पर काम करने पर रैंकिंग गिराना वर्कर्स को एक ही कंपनी पर निर्भर रहने के लिए "
        "मजबूर करता है।",
        "hi",
        "worker",
    ),
    SeedStatement(
        "Exclusivity incentives are a standard, transparent trade: a worker who "
        "commits more hours to one platform earns a better rate.",
        "en",
        "platform",
    ),
    # Customer rating system fairness
    SeedStatement(
        "A single low rating from one customer should never be enough on its own "
        "to trigger a deactivation review.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "ग्राहक की रेटिंग में भाषा, जाति या पहनावे को लेकर पूर्वाग्रह की जांच नहीं होती, फिर "
        "भी यह नौकरी तय करती है।",
        "hi",
        "worker",
    ),
    SeedStatement(
        "Customer ratings remain the most direct signal of service quality a "
        "platform has, and diluting their weight only lowers standards.",
        "en",
        "platform",
    ),
    # Tax treatment of gig income
    SeedStatement(
        "गिग आय पर कर संरचना सरल और स्पष्ट होनी चाहिए, ताकि अनियमित आय वाले वर्कर्स को हर "
        "महीने भ्रम न हो।",
        "hi",
        "bridging",
    ),
    SeedStatement(
        "Every platform should be required to report worker earnings directly to "
        "the tax department, the same way a formal employer does.",
        "en",
        "regulator",
    ),
    SeedStatement(
        "Treating irregular, part time gig income the same as salaried income for "
        "tax purposes penalises exactly the workers this is meant to help.",
        "en",
        "platform",
    ),
    # Verification requirements
    SeedStatement(
        "A single, shared verification system across platforms would save every "
        "new worker from repeating the same background check three times.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "पहचान और पृष्ठभूमि सत्यापन एक सरकारी एजेंसी द्वारा किया जाना चाहिए, न कि हर "
        "प्लेटफॉर्म द्वारा अपने तरीके से।",
        "hi",
        "regulator",
    ),
    # Migrant workers
    SeedStatement(
        "Language support in the worker app, not a residency quota, is the "
        "practical way to help migrant gig workers succeed.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "प्रवासी वर्कर्स को अक्सर सबसे कठिन शिफ्ट और सबसे कम भुगतान वाले काम दिए जाते हैं, "
        "बिना किसी विकल्प के।",
        "hi",
        "worker",
    ),
    # Emergency and insurance fund contributions
    SeedStatement(
        "A small, transparent per-order contribution to a shared emergency fund "
        "could cover medical costs without a full employment mandate.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "A shared emergency fund only works if every platform in a city "
        "contributes proportionally, or it simply favours whichever platform opts out.",
        "en",
        "platform",
    ),
    # Government oversight versus market self-correction
    SeedStatement(
        "गिग इकॉनमी को बिना सरकारी निगरानी के अपने आप ठीक होने देना, अब तक के अनुभव को "
        "देखते हुए, अवास्तविक उम्मीद है।",
        "hi",
        "regulator",
    ),
    SeedStatement(
        "Every past attempt at heavy-handed regulation of this sector has pushed "
        "platforms to cut the exact worker benefits it was meant to protect.",
        "en",
        "platform",
    ),
    # Foreign investment and a level playing field
    SeedStatement(
        "Whatever rules are set should apply equally to every platform operating "
        "in India, regardless of where its investors are based.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "Foreign-funded platforms should not be allowed to operate at a loss for "
        "years specifically to undercut labour standards a domestic company could "
        "not survive undercutting.",
        "en",
        "regulator",
    ),
    # Cost impact on customers
    SeedStatement(
        "Any new worker protection should be phased in gradually so that price "
        "increases do not fall entirely on customers in one step.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "हर नया नियम सीधे ग्राहक की कीमत में जुड़ जाता है, और अंततः मांग घटाकर वर्कर्स की "
        "कमाई को ही नुकसान पहुंचाता है।",
        "hi",
        "platform",
    ),
    # Women's safety and participation
    SeedStatement(
        "Verified emergency contacts and a visible SOS button should be a baseline "
        "requirement for every ride and delivery app, not a premium feature.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "महिला डिलीवरी वर्कर्स के लिए रात की शिफ्ट में सुरक्षा के अतिरिक्त इंतजाम होने चाहिए, "
        "केवल एक बटन काफी नहीं है।",
        "hi",
        "worker",
    ),
    # Dispute resolution timeline
    SeedStatement(
        "A statutory maximum response time for any worker grievance would give "
        "both sides a clear, enforceable clock to work against.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "Labour courts, not platform-run arbitration panels, should have final say "
        "whenever a worker disputes a deactivation.",
        "en",
        "regulator",
    ),
    # Training and onboarding
    SeedStatement(
        "प्लेटफॉर्म को नए वर्कर्स के लिए बुनियादी सुरक्षा और ग्राहक व्यवहार प्रशिक्षण मुफ्त में "
        "उपलब्ध कराना चाहिए।",
        "hi",
        "bridging",
    ),
    SeedStatement(
        "Unpaid onboarding training that takes half a day is effectively unpaid "
        "labour before a worker earns a single rupee.",
        "en",
        "worker",
    ),
    # Cross-border algorithm audits
    SeedStatement(
        "Any algorithm used to manage Indian gig workers should be auditable by an "
        "Indian regulator, regardless of where the platform's parent company is "
        "headquartered.",
        "en",
        "regulator",
    ),
    SeedStatement(
        "एल्गोरिदम का स्रोत कोड सरकार को सौंपना वैश्विक बौद्धिक संपदा समझौतों के विपरीत हो "
        "सकता है।",
        "hi",
        "platform",
    ),
    # Surge pricing and worker share
    SeedStatement(
        "Surge pricing periods should guarantee gig workers a proportionate share "
        "of the higher fare, not just the platform.",
        "en",
        "bridging",
    ),
    SeedStatement(
        "सर्ज के दौरान ग्राहक से ज्यादा पैसा लिया जाता है, लेकिन ड्राइवर तक उसका बहुत छोटा "
        "हिस्सा ही पहुंचता है।",
        "hi",
        "worker",
    ),
    SeedStatement(
        "Surge pricing exists to balance real time supply and demand, and "
        "mandating a fixed worker share removes the tool that gets more drivers on "
        "the road exactly when they're needed.",
        "en",
        "platform",
    ),
]
