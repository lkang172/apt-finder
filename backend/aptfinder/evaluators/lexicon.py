from dataclasses import dataclass

NEGATIVE = "negative"
POSITIVE = "positive"
NEUTRAL = "neutral"

TEXT_CATEGORIES = ("noise", "management", "pests", "building_safety", "neighborhood_safety", "other_issues")


@dataclass(frozen=True)
class ThemeSpec:
    category: str
    theme: str
    polarity: str
    label: str
    phrase: str
    # A negator just before one of these phrases flips the mention to negated_theme, or drops it when
    # negated_theme is None ("no roaches" is an explicit positive statement, not a roach complaint).
    patterns: tuple[str, ...] = ()
    # These phrases already carry their own negation or absence ("no hot water", "never fixed"),
    # so a preceding negator must not flip them.
    fixed_patterns: tuple[str, ...] = ()
    negated_theme: str | None = None
    suppressed_by: tuple[str, ...] = ()


_INT = (
    r"(?:(?:so|very|really|super|extremely|incredibly|pretty|quite|too|always|often|constantly|"
    r"unbearably|ridiculously|insanely|way too|kind of|a bit|a little|somewhat) )?"
)
_BE = r"(?:is|are|was|were|has been|have been|had been|can be|could be|gets|get|got|seems|seem|seemed|felt|feels|feel)"
_W2 = r"(?:[^\s,;]+ ){0,2}?"
_W3 = r"(?:[^\s,;]+ ){0,3}?"
_W4 = r"(?:[^\s,;]+ ){0,4}?"
_FREEWAYS = r"(?:(?:hwy |highway |interstate |i-)?(?:101|280|880|680|85|87|237|92))"
_STAFF = (
    r"(?:staff|management|managers?|office staff|office team|front desk|front office|concierge|"
    r"leasing (?:office|agents?|staff|team|consultants?|managers?|specialists?)|property managers?|"
    r"landlords?|team|employees|personnel|agents?)"
)
_GOOD = (
    r"(?:friendly|helpful|kind|courteous|professional|attentive|accommodating|nice|pleasant|welcoming|caring|"
    r"wonderful|amazing|great|awesome|fantastic|excellent|knowledgeable|lovely|polite|respectful|understanding|the best)"
)
_BAD = (
    r"(?:rude|unprofessional|disrespectful|condescending|hostile|nasty|mean|arrogant|dismissive|belligerent|"
    r"incompetent|useless|terrible|horrible|awful|unhelpful|lazy|dishonest|clueless|unfriendly|worst|the worst|"
    r"horrendous|atrocious)"
)
_FAST = (
    r"(?:very |super |really |always |so |extremely )?(?:quickly|promptly|right away|immediately|fast|"
    r"same day|the same day|the next day|within (?:a day|24 hours|hours|the day|a few hours|an hour))"
)
_AREA = (
    r"(?:neighborhood|neighbourhood|area|streets?|surroundings|part of town|vicinity|surrounding area|block)"
)
_AC = r"(?:ac|a/c|air conditioning|air conditioner|air conditioners|central air|hvac)"
_SPECIFIC_PESTS = ("cockroaches", "ants", "bed_bugs", "rodents", "spiders", "termites", "silverfish")
_AREA_THEMES = ("area_crime", "area_safe")


NOISE_THEMES = (
    ThemeSpec(
        "noise", "thin_walls", NEGATIVE, "Thin walls", "mention thin walls",
        patterns=(
            r"thin walls?",
            r"paper[- ]?thin(?: walls?)?",
            rf"walls {_BE} {_INT}(?:paper[- ]?)?thin",
            r"(?:can|could) (?:literally |actually |easily |clearly |even |still |totally |definitely )?hear "
            r"(?:everything|every ?thing|every word|every sound|every conversation|conversations|"
            r"(?:my|the|our) neighbors?|neighbors?|next door|(?:the )?people (?:next door|above|below|upstairs|downstairs)|"
            r"people talking|them talking|their (?:tv|music|conversations?|phone calls?|alarms?))",
            r"sounds? (?:really |easily )?(?:travels?|carries|carry)",
        ),
        fixed_patterns=(
            r"(?:poor|bad|terrible|no|zero|little|lack of|minimal|cheap) sound ?proofing",
            r"(?:not|isn't|wasn't|aren't|weren't) (?:very |at all )?sound ?proof(?:ed)?",
            r"poorly sound ?proofed",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "neighbor_noise", NEGATIVE, "Neighbor noise and footsteps", "mention noisy neighbors or footsteps",
        patterns=(
            r"foot ?steps",
            r"stomp(?:ing|s|ed)?",
            r"(?:noisy|loud|inconsiderate) (?:upstairs |downstairs )?(?:neighbors?|tenants?|residents?)",
            rf"(?:neighbors?|tenants?|residents?|kids) {_W2}{_BE} {_INT}(?:loud|noisy)",
            rf"(?:upstairs|downstairs|above|below) (?:neighbors?|tenants?|units?|residents?) {_W3}"
            r"(?:noise|noisy|loud|stomp\w*|walking|running|jumping|banging|thumping|pounding)",
            rf"(?:noise|noisy|loud|stomp\w*|banging|thumping|pounding|footsteps) {_W3}(?:from|of) (?:the |my |our )?"
            r"(?:upstairs|downstairs|unit above|unit below|apartment above|neighbors?|next door)",
            r"(?:hear|heard|hearing) (?:my |the |our )?(?:upstairs |downstairs )?neighbors?",
            r"banging|thumping|pounding",
            r"dogs? bark(?:ing|s)?|barking dogs?",
        ),
        fixed_patterns=(
            r"(?:nobody|no one) (?:respects?|follows?|observes?|cares about) (?:the )?quiet hours",
            r"(?:don't|doesn't|do not|does not|never) (?:respect|follow|observe|care about|enforce) (?:the )?quiet hours",
            r"quiet hours (?:are|is|were|was) (?:not|never|rarely) (?:enforced|respected|followed)",
            r"quiet hours (?:aren't|isn't|weren't|wasn't) (?:enforced|respected|followed)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "street_traffic", NEGATIVE, "Street and traffic noise", "mention street or traffic noise",
        patterns=(
            r"(?:street|traffic|road|car|vehicle) noise",
            rf"(?:noise|noisy|loud) {_W2}(?:from|of) (?:the )?(?:street|traffic|cars|road|intersection|el camino)",
            r"(?:loud|noisy) (?:street|road|intersection|traffic)",
            r"sirens?|honking|car alarms?|motorcycles?|revving|loud cars|loud mufflers?",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "highway", NEGATIVE, "Highway noise", "mention highway or freeway noise",
        patterns=(
            r"(?:highway|freeway|interstate|expressway) (?:noise|traffic noise|hum|roar)",
            rf"(?:noise|noisy|loud|hum|roar) {_W2}(?:from|of) (?:the )?(?:highway|freeway|interstate|expressway|{_FREEWAYS})",
            r"(?:hear|heard|hearing) (?:the )?(?:highway|freeway|expressway|101|280|880|237)",
            r"(?:loud|noisy) (?:highway|freeway)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "train", NEGATIVE, "Train noise", "mention train noise",
        patterns=(
            r"train (?:noise|horns?|whistles?|bells?)",
            r"(?:caltrain|bart|vta|light rail|freight trains?|trains?) (?:noise|horns?|whistles?|"
            r"(?:is|are|was|were|can be|gets) (?:\w+ )?(?:loud|noisy)|rumbl\w*|all night|at night|"
            r"every \d+ minutes|every few minutes|shak\w+)",
            r"(?:hear|heard|hearing) (?:the )?(?:trains?|caltrain|bart|light rail|vta|train horns?|horns?)",
            rf"(?:noise|horns?|rumbl\w*) {_W2}(?:from|of) (?:the )?(?:trains?|caltrain|bart|light rail|vta|tracks|rail ?road|railway)",
            r"(?:loud|noisy) (?:trains?|caltrain|light rail)",
            rf"(?:train|railroad) tracks? {_W2}(?:noise|noisy|loud)",
            r"horns? (?:blaring|blowing|all night|at night|in the middle of the night)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "airplane", NEGATIVE, "Airplane noise", "mention airplane noise",
        patterns=(
            r"(?:airplane|aircraft|plane|jet|flight|helicopter|airport)s? (?:noise|overhead|flying (?:over|low|overhead)|"
            r"fly(?:ing)? over|taking off|landing)",
            r"(?:planes?|airplanes?|jets?|helicopters?) (?:are|were|is|was|can be|get) (?:\w+ )?(?:loud|noisy)",
            rf"(?:noise|noisy|loud) {_W2}(?:from|of) (?:the )?(?:airport|planes?|airplanes?|jets?|flights?|moffett|sjc|helicopters?)",
            r"(?:under|below|in) (?:the |a )?flight ?path",
            r"(?:hear|heard|hearing) (?:the )?(?:planes?|airplanes?|jets?|helicopters?)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "construction_noise", NEGATIVE, "Construction noise", "mention construction noise",
        patterns=(
            r"construction noises?",
            rf"(?:noise|noisy|loud) {_W2}(?:from|of) (?:the )?(?:construction|renovations?|remodel\w*|demolition)",
            r"jack ?hammer\w*",
            r"drilling|hammering|power tools",
            rf"construction {_W2}(?:starts?|started|begins?|began|starting) (?:at )?(?:\d|early|dawn|the crack of dawn)",
            r"(?:loud|noisy) (?:construction|renovations?)",
            rf"construction (?:crews?|workers?) {_W3}(?:early|loud|noisy|\d ?am)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "nightlife", NEGATIVE, "Nightlife and parties", "mention parties or nightlife noise",
        patterns=(
            r"(?:loud|late[- ]night|noisy|wild|frequent|constant|weekend|all[- ]night) part(?:y|ies)",
            r"partying",
            r"part(?:y|ies) (?:noise|neighbors?|animals?|goers|until|till|every|all night|on weekends|next door|upstairs)",
            rf"(?:noise|noisy|loud) {_W2}(?:from|of) (?:the )?(?:bars?|clubs?|nightclubs?|nightlife|restaurants?|patrons)",
            r"(?:loud|blasting|blaring|booming) (?:music|bass)",
            r"music (?:blasting|blaring|booming|until|till|late at night|all night)",
            r"(?:loud|noisy|late[- ]night) (?:bars?|clubs?|nightlife|crowds?)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "commercial", NEGATIVE, "Commercial and delivery noise", "mention commercial or delivery noise",
        patterns=(
            rf"(?:garbage|trash|recycling|delivery|commercial) trucks? {_W3}(?:at \d|early|every morning|in the morning|"
            r"wake|woke|waking|noise|noisy|loud|beeping)",
            r"(?:loud|noisy|beeping) (?:garbage|trash|recycling|delivery) trucks?",
            r"loading docks?",
            rf"(?:noise|noisy|loud) {_W2}(?:from|of) (?:the )?(?:businesses|stores?|shops?|grocery|retail|commercial|deliveries)",
            rf"(?:deliveries|delivery trucks?) {_W3}(?:at \d|early|all night|every morning)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "landscaping", NEGATIVE, "Landscaping noise", "mention landscaping noise",
        patterns=(
            r"leaf ?blowers?",
            rf"(?:landscap\w+|gardeners?|lawn ?mowers?|mowing|groundskeep\w+) {_W3}(?:noise|noisy|loud|at \d|early|"
            r"every (?:morning|week)|crews?)",
            r"(?:noisy|loud) (?:landscap\w+|gardeners?|lawn ?mowers?)",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "other_noise", NEGATIVE, "General noise", "describe general noise problems",
        patterns=(
            r"nois(?:y|ier|iest)",
            r"(?<!out )loud(?:er|est)?",
            r"(?<!white )noises?",
        ),
        negated_theme="quiet",
    ),
    ThemeSpec(
        "noise", "quiet", POSITIVE, "Quiet", "describe the property as quiet",
        patterns=(
            r"quiet(?:er|est)?(?!\s+hours?)",
            r"peaceful(?:ly)?",
            r"tranquil",
            r"serene",
            r"calm (?:and quiet|neighborhood|building|community|area|environment|place)",
            r"(?:well|good|great|excellent|solid|decent) (?:sound ?proof(?:ed|ing)|sound insulation)",
            r"sound ?proofing (?:is|was) (?:good|great|excellent|solid|decent)",
            r"(?:thick|solid|concrete) walls",
        ),
        fixed_patterns=(
            r"(?:can't|cannot|can not|couldn't|could not|never|don't|do not|didn't|did not|rarely|barely|hardly|seldom) "
            r"(?:ever )?hear (?:my |the |any |our |a )?(?:neighbors?|anything|anyone|a thing|noise|people|sounds?|"
            r"footsteps|trains?|traffic|cars)",
            r"(?:little|minimal|barely any|hardly any|very little|almost no|no) (?:outside |street |traffic )?noise",
            r"(?:couldn't|could not|can't|cannot) (?:be|have been|ask for) (?:any )?quieter",
        ),
        negated_theme="other_noise",
    ),
)

MANAGEMENT_THEMES = (
    ThemeSpec(
        "management", "responsiveness", NEGATIVE, "Unresponsive management", "describe management as unresponsive",
        fixed_patterns=(
            r"unresponsive",
            r"never (?:\w+ )?(?:respond(?:s|ed)?|answer(?:s|ed)?|repl(?:y|ies|ied)|"
            r"return(?:s|ed)? (?:my |our |any )?(?:calls?|emails?|messages?)|calls? (?:me |us )?back|"
            r"called (?:me |us )?back|got back|gets back|get back|picks? up)",
            r"(?:didn't|don't|doesn't|did not|do not|does not|won't|wouldn't|will not|would not|rarely|seldom) "
            r"(?:even |ever )?(?:respond|answer|reply|return (?:my |our |any )?(?:calls?|emails?|messages?)|"
            r"call (?:me |us )?back|get back to|pick up)",
            r"no (?:response|reply|replies|answer|call ?back|follow[- ]up)",
            r"ignor(?:e|es|ed|ing) (?:my |our |all |the |tenant |resident |multiple |several |repeated )?(?:\w+ )?"
            r"(?:emails?|calls?|requests?|messages?|complaints?|concerns?|tickets?)",
            r"(?:hard|impossible|difficult|tough) to (?:reach|get a hold of|get ahold of|contact|get in touch with)",
            r"(?:no one|nobody) (?:ever )?(?:answers?|responds?|picks up|calls? back|gets? back|replies)",
            r"(?:slow|took (?:days|weeks|forever|ages)|takes (?:days|weeks|forever|ages)) to (?:respond|reply|answer|get back)",
            r"slow (?:to respond|responses?|replies)",
        ),
    ),
    ThemeSpec(
        "management", "responsive", POSITIVE, "Responsive management", "describe management as responsive",
        patterns=(
            r"responsive",
            r"(?:respond(?:s|ed)?|repl(?:y|ies|ied)|got back|gets back|get back|answer(?:s|ed)?) "
            r"(?:to (?:me|us|my \w+|our \w+|emails|requests) )?(?:very |super |really |always )?"
            r"(?:quickly|promptly|right away|immediately|fast|within (?:a day|an hour|hours|the hour|minutes|24 hours|the same day))",
            r"quick to (?:respond|reply|answer|address)",
            r"(?:quick|fast|prompt|timely|speedy) (?:responses?|replies|reply)",
        ),
        negated_theme="responsiveness",
    ),
    ThemeSpec(
        "management", "maintenance", NEGATIVE, "Slow or poor maintenance", "report slow or poor maintenance",
        fixed_patterns=(
            rf"(?:maintenance|repairs?|work orders?|service requests?|requests?|tickets?|fixes) {_W3}(?:took|takes|take|taking) "
            r"(?:weeks|months|forever|ages|days|a long time|so long|too long|over a (?:week|month)|\d+ (?:days|weeks|months))",
            r"(?:never|still (?:not|hasn't|haven't|hadn't|isn't|aren't|wasn't)|wasn't|weren't|isn't|aren't|not|didn't|"
            r"did not|wouldn't|won't) (?:been |get |got |gotten |getting )?(?:fixed|repaired|addressed|resolved|taken care of)",
            rf"(?:never|didn't|did not|wouldn't|won't|refused to|refuse to|refuses to) (?:come|came|bother|show up|"
            rf"send (?:anyone|someone)) {_W2}(?:to )?(?:fix|repair|look at|check)",
            r"(?:never|didn't|did not|wouldn't|won't|refused to|refuses to) (?:fix|fixed|repair|repaired|address|addressed)",
            rf"(?:waited|waiting|wait) (?:for )?(?:weeks|months|days|over a week|over a month|\d+ (?:days|weeks|months)) "
            rf"(?:for|on|to get) {_W2}(?:maintenance|repairs?|a repair|someone|them|it|the \w+|fix\w*)",
            r"(?:slow|terrible|horrible|awful|poor|bad|lousy|incompetent|non-?existent|nonexistent|subpar|shoddy|sloppy|"
            r"lazy|useless) (?:maintenance|repairs?|repair work|work orders?)",
            rf"maintenance (?:team |staff |crew |guys? |men |workers? |department |requests? |response )?"
            rf"(?:is|was|are|were|has been|have been|can be) {_INT}(?:slow|terrible|horrible|awful|poor|bad|lousy|incompetent|"
            r"non-?existent|nonexistent|a joke|useless|lacking|sloppy|lazy|unreliable)",
            rf"maintenance (?:team |staff |crew )?(?:is|was|are|were|has been|have been) (?:not|never) {_INT}"
            r"(?:great|good|quick|fast|prompt|responsive|helpful|reliable)",
            rf"maintenance (?:team |staff |crew )?(?:isn't|wasn't|aren't|weren't) {_INT}(?:great|good|quick|fast|prompt|"
            r"responsive|helpful|reliable)",
            rf"work orders? {_W2}(?:ignored|unanswered|never (?:completed|done|addressed|fixed)|go unanswered|sit for)",
            rf"(?:broken|leaking|leaky|not working) {_W2}for (?:weeks|months|over a (?:week|month)|\d+ (?:weeks|months))",
            r"(?:half[- ]assed|band[- ]aid) (?:repairs?|fix(?:es)?|job)",
            r"(?:took|takes|take|taking) (?:them |him |her |maintenance |management |the office )?(?:weeks|months|forever|ages|"
            r"a long time|so long|over a (?:week|month)|\d+ (?:days|weeks|months)) to (?:fix|repair|address|replace|come out)",
            r"(?:no one|nobody) (?:ever )?(?:fixes|fixed|repairs|repaired|comes|came|shows up|showed up)",
        ),
    ),
    ThemeSpec(
        "management", "quick_repairs", POSITIVE, "Quick, reliable repairs", "praise quick or reliable repairs",
        patterns=(
            rf"(?:maintenance|repairs?|work orders?|requests?|issues?|problems?|everything|it|things) {_W3}"
            rf"(?:fixed|addressed|resolved|handled|taken care of|completed|done|repaired|came|comes|come|responded|responds) {_FAST}",
            rf"(?:fix|fixed|fixes|repair|repaired|address|addressed|resolve|resolved|handled) "
            rf"(?:(?:it|them|everything|things|the problem|the issue|issues|problems) )?{_FAST}",
            r"(?:great|excellent|amazing|awesome|fantastic|good|quick|fast|prompt|efficient|reliable|wonderful|responsive|"
            r"attentive|helpful|top[- ]notch) maintenance",
            rf"maintenance (?:team |staff |crew |guys? |men |workers? |department |person |guy |man )?"
            rf"(?:is|was|are|were|has been|have been) {_INT}(?:great|excellent|amazing|awesome|fantastic|good|quick|fast|"
            r"prompt|efficient|reliable|wonderful|responsive|helpful|on top of it|top[- ]notch|the best)",
            r"(?:quick|fast|prompt|speedy|timely|same[- ]day) (?:repairs?|fixes|service|maintenance)",
        ),
        negated_theme="maintenance",
    ),
    ThemeSpec(
        "management", "professionalism", NEGATIVE, "Rude or unprofessional staff", "describe staff as rude or unprofessional",
        patterns=(
            r"rude(?:ly|ness)?",
            r"unprofessional",
            r"disrespectful",
            r"condescending",
            r"unhelpful",
            r"unfriendly",
            r"dishonest",
            r"belligerent",
            rf"{_BAD} {_STAFF}",
            rf"{_STAFF} {_W2}(?:is|are|was|were|has been|have been|can be|seems?|seemed) {_INT}{_BAD}",
            r"bad attitudes?",
            r"slum ?lords?",
            r"(?:lied|lying|lies) (?:to )?(?:me|us|residents|tenants|people)",
            r"(?:predatory|greedy) (?:management|landlords?|company|owners?|corporation)",
        ),
        fixed_patterns=(
            rf"(?:not|isn't|wasn't|aren't|weren't|never) {_INT}(?:at all |very |particularly )?"
            r"(?:helpful|friendly|professional|courteous|accommodating|polite|respectful|kind)",
        ),
    ),
    ThemeSpec(
        "management", "helpful_staff", POSITIVE, "Friendly, helpful staff", "describe staff as friendly or helpful",
        patterns=(
            rf"{_GOOD} (?:and {_GOOD} )?{_STAFF}",
            rf"{_STAFF} {_W2}(?:is|are|was|were|has been|have been|always|seems?) {_INT}{_GOOD}",
            r"went (?:above and beyond|out of (?:their|her|his|the) way)",
            r"above and beyond",
        ),
        negated_theme="professionalism",
    ),
    ThemeSpec(
        "management", "communication", NEGATIVE, "Poor communication", "report poor communication",
        fixed_patterns=(
            r"(?:poor|bad|terrible|horrible|awful|lack of|no|zero|little|non-?existent|nonexistent|inconsistent) communication",
            r"(?:never|didn't|did not|don't|do not|doesn't|does not|won't) (?:\w+ )?(?:inform|informed|notify|notified|tell|told|"
            r"warn|warned|update|updated|communicate|communicated|let (?:us|me|residents|tenants) know)",
            r"(?:without|no|zero|little|short) (?:any |prior |advance )?(?:notice|warning|heads[- ]up)",
            rf"communication (?:is|was|has been|can be) {_INT}(?:poor|bad|terrible|horrible|awful|lacking|non-?existent|"
            r"nonexistent|inconsistent|a problem|an issue)",
            r"(?:mixed|conflicting) (?:messages|information|answers)",
            r"(?:left|leave|leaves) (?:us|me|residents|tenants) in the dark",
        ),
    ),
    ThemeSpec(
        "management", "good_communication", POSITIVE, "Good communication", "praise management communication",
        patterns=(
            r"(?:great|good|excellent|clear|timely|open|consistent|frequent) communication",
            r"communicat(?:e|es|ed) (?:very |really )?(?:well|clearly|promptly|regularly)",
            r"(?:keeps?|kept) (?:us|me|residents|tenants|everyone) (?:informed|updated|in the loop)",
            r"communicative",
        ),
        negated_theme="communication",
    ),
    ThemeSpec(
        "management", "renewals", NEGATIVE, "Rent increases at renewal", "complain about renewals or rent increases",
        patterns=(
            r"rent (?:increases?|hikes?|went up|goes up|go up|raised|jumped|skyrocketed)",
            r"(?:raised|raise|raises|raising|increased|increase|increases|hiked|hike|jacked up|jack up) (?:the |my |our )?rent",
            r"renewal (?:offer|rate|price|increase|quote)s?",
            r"(?:huge|massive|steep|big|large|crazy|ridiculous|outrageous|insane|absurd|unreasonable|significant) "
            r"(?:rent )?(?:increases?|hikes?|jumps?)",
            r"price gouging",
            r"(?:lease )?renewals? (?:is|was|are|were) (?:a nightmare|terrible|horrible|ridiculous|expensive|outrageous)",
        ),
        negated_theme="fair_renewals",
    ),
    ThemeSpec(
        "management", "fair_renewals", POSITIVE, "Fair renewals", "describe renewals as fair",
        fixed_patterns=(
            r"(?:reasonable|fair|small|modest|minimal|minor|tiny|low) (?:rent )?(?:increases?|renewals?|renewal (?:rates?|offers?))",
            r"(?:didn't|did not|don't|do not|never|haven't|have not|hasn't|won't) (?:\w+ )?(?:raise|raised|increase|increased|"
            r"hike|hiked) (?:the |my |our )?rent",
            r"(?:rent|renewal) (?:increases? )?(?:is|was|were|are|has been|have been) (?:very |pretty |quite )?(?:reasonable|fair|modest)",
        ),
    ),
    ThemeSpec(
        "management", "deposit_disputes", NEGATIVE, "Security deposit disputes", "report security deposit disputes",
        fixed_patterns=(
            r"(?:kept|keep|keeps|withheld|withhold|stole|took) (?:my |our |the |all of (?:my|our|the) |most of (?:my|our|the) |"
            r"part of (?:my|our|the) |half (?:of )?(?:my|our|the) )?(?:entire |whole |full )?(?:security )?deposit",
            r"(?:never|didn't|did not|haven't|have not|still haven't|hasn't) (?:\w+ )?(?:got|get|gotten|received|receive|"
            r"return(?:ed)?|refund(?:ed)?|give|gave)(?: \w+)? (?:back )?(?:my |our |the )?(?:full |entire |whole )?"
            r"(?:security )?deposit(?: back)?",
            r"deposit (?:disputes?|deductions?|was withheld|never returned|not returned)",
            rf"(?:charged|deducted) {_W4}from (?:my |our |the )?(?:security )?deposit",
        ),
    ),
    ThemeSpec(
        "management", "deposit_returned", POSITIVE, "Deposit returned", "report getting their deposit back",
        patterns=(
            r"(?:got|get|received|returned|refunded|gave (?:me|us)) (?:back )?(?:my |our |the )?(?:full |entire |whole )?"
            r"(?:security )?deposit(?: back)?(?: in full)?",
        ),
        negated_theme="deposit_disputes",
    ),
    ThemeSpec(
        "management", "unexplained_charges", NEGATIVE, "Unexplained charges", "report unexplained charges or billing errors",
        patterns=(
            r"(?:hidden|unexpected|unexplained|random|mysterious|bogus|ridiculous|surprise|excessive|outrageous|unauthorized) "
            r"(?:fees?|charges?|bills?|costs?)",
            r"(?:billing|bill) (?:errors?|mistakes?|issues?|problems?)",
            r"(?:charged|billed) (?:me|us) (?:for|twice|double|an extra|extra|a fee)",
            r"overcharged|overcharging|double[- ]charged",
        ),
    ),
    ThemeSpec(
        "management", "package_handling", NEGATIVE, "Package handling", "report package handling problems",
        patterns=(
            r"(?:lost|misplaced|missing|misdelivered) (?:my |our |a |the )?packages?",
            r"packages? (?:were |was |get |got |go |are |keep )?(?:lost|misplaced|missing|misdelivered|returned to sender|sent back)",
            r"package (?:room|locker|lockers|system|area|center) (?:is|was|are|were) (?:a mess|a nightmare|always full|full|"
            r"broken|terrible|chaotic|overflowing|unreliable)",
        ),
        fixed_patterns=(
            r"(?:never|didn't|did not) (?:receive|received|get|got) (?:my |our |a |the )?packages?",
            r"(?:office|staff|management|front desk|leasing office) (?:won't|wouldn't|doesn't|didn't|refuses? to|refused to) "
            r"(?:accept|hold|sign for|take) packages?",
        ),
    ),
    ThemeSpec(
        "management", "move_in", NEGATIVE, "Move-in problems", "report move-in problems",
        fixed_patterns=(
            r"move[- ]in (?:day |process |experience )?(?:was |is )?(?:a nightmare|terrible|horrible|awful|stressful|chaotic|"
            r"a disaster|rough|delayed)",
            r"(?:unit|apartment|place) (?:wasn't|was not) (?:ready|clean|cleaned)",
            r"(?:dirty|filthy|not clean|unclean) (?:at|on|upon) move[- ]in",
            rf"(?:when|after|upon) (?:i|we) moved in,? {_W4}(?:dirty|filthy|broken|not clean|wasn't clean|was not clean|not ready)",
        ),
    ),
    ThemeSpec(
        "management", "smooth_move_in", POSITIVE, "Smooth move-in", "describe a smooth move-in",
        patterns=(
            r"(?:smooth|easy|seamless|great|painless|quick|simple|pleasant) move[- ]in",
            r"move[- ]in (?:process |experience |day )?(?:was|went) (?:very |super |really |so )?(?:smooth|easy|seamless|great|"
            r"painless|quick|simple|pleasant)",
        ),
        negated_theme="move_in",
    ),
    ThemeSpec(
        "management", "move_out", NEGATIVE, "Move-out problems", "report move-out problems",
        fixed_patterns=(
            r"move[- ]out (?:process |experience |inspection )?(?:was |is )?(?:a nightmare|terrible|horrible|awful|stressful|"
            r"a disaster|unfair)",
            rf"(?:charged|billed) (?:me |us )?{_W3}(?:after|when|upon) (?:i |we )?(?:moved|moving|move) out",
            rf"(?:after|when|upon) (?:i|we) moved out,? {_W4}(?:charged|billed|bill|fees?|kept)",
        ),
    ),
    ThemeSpec(
        "management", "smooth_move_out", POSITIVE, "Smooth move-out", "describe a smooth move-out",
        patterns=(
            r"(?:smooth|easy|seamless|painless|fair) move[- ]out",
            r"move[- ]out (?:process |experience |inspection )?(?:was|went) (?:very |super |really |so )?(?:smooth|easy|seamless|"
            r"painless|fair)",
        ),
        negated_theme="move_out",
    ),
    ThemeSpec(
        "management", "management_change", NEUTRAL, "Management change", "mention a management change",
        fixed_patterns=(
            r"(?:under )?new management",
            r"new (?:owners?|ownership|property management|management company|management team|managers?|property managers?)",
            r"(?:management|ownership|management company|property management) (?:has |have |had )?(?:changed|switched|"
            r"was replaced|were replaced|took over|transitioned)",
            r"(?:changed|switched|changing) (?:management|management companies|owners|ownership)",
            r"(?:bought|purchased|acquired) by (?:a |an |the )?(?:new )?(?:\w+ )?(?:company|owners?|group|management|investors?|reit)",
        ),
    ),
)

PEST_THEMES = (
    ThemeSpec("pests", "cockroaches", NEGATIVE, "Cockroaches", "mention cockroaches",
              patterns=(r"(?:cock)?roach(?:es)?",), negated_theme="no_pests"),
    ThemeSpec("pests", "ants", NEGATIVE, "Ants", "mention ants",
              patterns=(r"ants", r"ant (?:problems?|issues?|infestations?|trails?|invasions?|colon(?:y|ies))", r"sugar ants"),
              negated_theme="no_pests"),
    ThemeSpec("pests", "bed_bugs", NEGATIVE, "Bed bugs", "mention bed bugs",
              patterns=(r"bed ?bugs?",), negated_theme="no_pests"),
    ThemeSpec("pests", "rodents", NEGATIVE, "Rodents", "mention mice or rats",
              patterns=(r"mice", r"mouse", r"rats?", r"rodents?", r"vermin", r"(?:mouse|rat|rodent) droppings"),
              negated_theme="no_pests"),
    ThemeSpec("pests", "spiders", NEGATIVE, "Spiders", "mention spiders",
              patterns=(r"spiders?", r"black widows?"), negated_theme="no_pests"),
    ThemeSpec("pests", "termites", NEGATIVE, "Termites", "mention termites",
              patterns=(r"termites?",), negated_theme="no_pests"),
    ThemeSpec("pests", "silverfish", NEGATIVE, "Silverfish", "mention silverfish",
              patterns=(r"silver ?fish",), negated_theme="no_pests"),
    ThemeSpec(
        "pests", "other_pests", NEGATIVE, "Other pests", "mention other pests or bugs",
        patterns=(
            r"pests?(?! control)",
            r"bugs?",
            r"insects?",
            r"fleas?",
            r"fruit flies",
            r"gnats?",
            r"infest(?:ed|ation|ations)",
            r"critters?",
        ),
        negated_theme="no_pests",
        suppressed_by=_SPECIFIC_PESTS,
    ),
    ThemeSpec(
        "pests", "no_pests", POSITIVE, "No pest problems", "report no pest problems",
        fixed_patterns=(
            r"(?:pest|bug|roach|insect|rodent)[- ]free",
            r"free (?:of|from) (?:any )?(?:pests|bugs|roaches|insects|rodents|mice)",
        ),
    ),
)

BUILDING_SAFETY_THEMES = (
    ThemeSpec(
        "building_safety", "package_theft", NEGATIVE, "Package theft", "report package theft",
        patterns=(
            rf"packages? {_W2}(?:stolen|theft|thefts|thieves|swiped|disappear(?:ed|s|ing)?|keep disappearing)",
            r"package (?:theft|thefts|thieves|thief)",
            r"stolen (?:packages?|parcels?|deliveries|mail)",
            r"(?:stole|steal|steals|stealing) (?:\w+ )?(?:packages?|deliveries|parcels?|mail)",
            r"porch pirates?",
            rf"mail {_W2}(?:stolen|theft)",
        ),
        negated_theme="secure_building",
    ),
    ThemeSpec(
        "building_safety", "car_break_ins", NEGATIVE, "Car break-ins", "report car break-ins or vehicle theft",
        patterns=(
            r"car (?:break[- ]?ins?|thefts?|vandalism|prowl\w*)",
            rf"(?:breaking|broke|broken|break) into {_W2}(?:cars?|vehicles?|trucks?)",
            rf"(?:cars?|vehicles?|trucks?|car windows?) {_W2}(?:broken into|vandalized|stolen|smashed|keyed|burglarized)",
            r"smashed (?:car |the |my )?windows?",
            rf"catalytic converters? {_W2}(?:stolen|theft|thefts|taken|cut off)",
            r"(?:stole|stolen|steal) (?:\w+ )?(?:car|cars|catalytic converters?|tires|wheels|vehicles?)",
            r"break[- ]?ins? (?:in|at) (?:the )?(?:garage|parking (?:lot|garage|structure)|car ?port)",
        ),
        negated_theme="secure_building",
    ),
    ThemeSpec(
        "building_safety", "burglary", NEGATIVE, "Break-ins and burglary", "report break-ins or burglary",
        patterns=(
            r"(?:apartments?|units?|homes?|places?|doors?|storage units?|storage) (?:\w+ )?(?:was |got |were |been )?"
            r"(?:broken into|burglarized|robbed)",
            r"burglar(?:y|ies|ized|s)?",
            r"break[- ]?ins?",
        ),
        negated_theme="secure_building",
    ),
    ThemeSpec(
        "building_safety", "garage_security", NEGATIVE, "Garage security", "report garage security problems",
        fixed_patterns=(
            r"garage (?:gate|door)s? (?:is |was |are |were )?(?:always |often |constantly |frequently |usually )?(?:broken|open|"
            r"left open|stuck open|not working|doesn't close|won't close|never closes)",
            r"(?:unsecured|unsecure|insecure|open) (?:parking )?garage",
            r"garage (?:is not|was not|isn't|wasn't) (?:secure|secured|safe)",
            r"(?:anyone|anybody|people|strangers) can (?:just )?(?:walk|get|come|drive) into the garage",
            r"tailgat(?:e|ing|ed|ers?) (?:into|in) (?:the )?garage",
        ),
    ),
    ThemeSpec(
        "building_safety", "bike_theft", NEGATIVE, "Bike theft", "report bike theft",
        patterns=(
            rf"(?:bikes?|bicycles?|e-?bikes?|scooters?) {_W2}(?:stolen|theft|thefts)",
            r"(?:stole|stolen|steal|steals|stealing) (?:\w+ )?(?:bikes?|bicycles?|e-?bikes?|scooters?)",
            rf"bike (?:room|storage|cage|locker)s? {_W3}(?:broken into|break[- ]?ins?|stolen|theft)",
        ),
        negated_theme="secure_building",
    ),
    ThemeSpec(
        "building_safety", "broken_gates", NEGATIVE, "Broken gates", "report broken or open gates",
        fixed_patterns=(
            r"gates? (?:is |are |was |were )?(?:always |often |constantly |frequently |usually )?(?:broken|left open|propped open|"
            r"stuck open|not working|never closes?|doesn't close|don't close|won't close|out of order)",
            r"broken gates?",
        ),
    ),
    ThemeSpec(
        "building_safety", "access_control", NEGATIVE, "Access-control failures", "report access-control failures",
        fixed_patterns=(
            rf"(?:fobs?|key ?cards?|access (?:cards?|system|control)|buzzers?|call ?box|intercom|entry system) {_W2}"
            r"(?:broken|not working|don't work|doesn't work|never works?|stopped working|failed|fails|unreliable)",
            r"(?:doors?|entrances?|lobby doors?|front doors?) (?:is |are |was |were )?(?:always |often |constantly |frequently )?"
            r"(?:propped open|left open|left unlocked|unlocked|don't lock|doesn't lock|won't lock)",
            r"(?:anyone|anybody|strangers|non-?residents) can (?:just )?(?:walk|get|come|wander) (?:in|into)",
        ),
    ),
    ThemeSpec(
        "building_safety", "trespassing", NEGATIVE, "Trespassing", "report trespassing",
        patterns=(
            r"trespass(?:ers?|ing|ed)?",
            rf"(?:strangers|non-?residents|people who don't live here|unauthorized (?:people|persons|individuals|visitors)|"
            rf"outsiders) {_W3}(?:in|inside|into|entering|getting into|wandering) (?:the )?(?:building|halls?|hallways?|"
            r"garage|stairwells?|stairs|lobby|property|complex|gym|pool)",
            r"unauthorized (?:entry|access)",
        ),
        negated_theme="secure_building",
    ),
    ThemeSpec(
        "building_safety", "broken_locks", NEGATIVE, "Broken locks", "report broken locks",
        fixed_patterns=(
            r"(?:broken|busted|faulty|flimsy) (?:door )?locks?",
            rf"locks? {_W2}(?:broken|don't work|doesn't work|didn't work|not working|never fixed|jammed)",
            r"(?:door|deadbolt) (?:won't|doesn't|didn't|wouldn't|does not|did not) lock",
        ),
    ),
    ThemeSpec(
        "building_safety", "security_response", NEGATIVE, "Poor security response", "report poor security response",
        fixed_patterns=(
            rf"(?:security|security guards?|courtesy patrol|patrol) {_W2}(?:never|didn't|did not|doesn't|does not|won't|"
            r"failed to) (?:respond|show|come|do anything|help)",
            r"(?:no|zero|lack of|nonexistent|non-existent|useless|poor|inadequate) security",
            r"security (?:is|was) (?:a joke|useless|nonexistent|non-existent|lacking|poor|terrible|bad|inadequate)",
        ),
    ),
    ThemeSpec(
        "building_safety", "feels_unsafe", NEGATIVE, "Feels unsafe in the building", "say the building feels unsafe",
        patterns=(
            rf"(?:feel|feels|felt|feeling) {_INT}(?:unsafe|insecure|uneasy)",
            r"(?:unsafe|insecure|unsecure) (?:building|complex|property|garage|parking|entry|entrance)",
            rf"(?:building|complex|property|garage|parking (?:lot|garage)) {_W2}(?:is|feels|seems|was) {_INT}(?:unsafe|insecure|dangerous)",
        ),
        negated_theme="secure_building",
        suppressed_by=_AREA_THEMES,
    ),
    ThemeSpec(
        "building_safety", "secure_building", POSITIVE, "Secure building", "describe the building as safe or secure",
        patterns=(
            rf"(?:feel|feels|felt|feeling) {_INT}(?:very |totally |completely )?(?:safe|secure)",
            r"(?:safe|secure|secured|gated) (?:building|complex|community|property|place to live|garage|parking(?: garage| lot)?|"
            r"entry|entrance)",
            r"(?:good|great|excellent|tight|strong|solid|24/7|24-hour|24 hour|on-?site) security",
            rf"security (?:is|was|has been|seems) {_INT}(?:good|great|excellent|tight|solid|top[- ]notch|strong|reliable)",
            rf"(?:gates?|fobs?|key ?cards?|access control|controlled access|access system) {_W2}(?:works?|working) "
            r"(?:well|great|fine|reliably|properly)",
            r"(?:controlled|secure|restricted|fob|key ?card) (?:access|entry)",
            rf"(?:building|complex|property|place|apartment|community) {_W2}(?:is|feels|seems|was) {_INT}(?:safe|secure)",
        ),
        negated_theme="feels_unsafe",
        suppressed_by=_AREA_THEMES,
    ),
)

NEIGHBORHOOD_SAFETY_THEMES = (
    ThemeSpec(
        "neighborhood_safety", "area_crime", NEGATIVE, "Area crime or feeling unsafe in the area",
        "describe the surrounding area as unsafe or mention crime nearby",
        patterns=(
            rf"(?:unsafe|dangerous|high[- ]crime|crime[- ]ridden|scary) {_AREA}",
            rf"{_AREA} {_W2}(?:is|are|was|were|feels|felt|seems|can be|gets) {_INT}(?:unsafe|dangerous|scary)",
            rf"crimes? (?:\w+ )?(?:in|around|near) (?:the |this |our )?{_AREA}",
            r"(?:lots of|a lot of|high|rising|increasing|frequent|constant|so much) crime",
            r"crime (?:rates? )?(?:is|are|has been|have been|has gone|went) (?:\w+ )?(?:high|bad|terrible|increasing|rising|up|worse)",
            rf"(?:shootings?|gunshots?|gun ?fire|stabbings?|muggings?|robber(?:y|ies)|carjackings?|assaults?) {_W3}"
            r"(?:nearby|in the area|around here|in the neighborhood|down the street|near(?:by)?|outside|across the street|"
            r"around the corner|on the block|close by)",
            r"(?:hear|heard|hearing) (?:gun ?shots|gun ?fire)",
            r"(?:afraid|scared|nervous|uncomfortable|unsafe) (?:to )?(?:walk|walking|be out|go out|going out|be outside)"
            r"(?: \w+){0,3}? (?:at night|after dark|alone)",
        ),
        fixed_patterns=(
            rf"{_AREA} {_W2}(?:isn't|is not|wasn't|was not|aren't|are not|doesn't feel|does not feel|didn't feel|did not feel|"
            rf"don't feel) {_INT}safe",
        ),
        negated_theme="area_safe",
    ),
    ThemeSpec(
        "neighborhood_safety", "area_safe", POSITIVE, "Feels safe in the area", "describe the surrounding area as safe",
        patterns=(
            rf"safe {_AREA}",
            rf"safe(?: and|,) (?:\w+ )?{_AREA}",
            rf"{_AREA} {_W2}(?:is|are|was|were|feels|felt|seems) {_INT}(?:very |totally |completely )?safe",
            rf"(?:feel|feels|felt|feeling) {_INT}(?:very |totally |completely )?safe (?:walking|to walk|going (?:out|for (?:a )?walks?|"
            r"on walks?)|jogging|running|biking|walking around|walking alone|at night|after dark|outside|"
            r"in the (?:area|neighborhood)|around (?:the )?(?:area|neighborhood|here))",
            r"safe (?:to walk|walking|for walks|to go (?:out|for (?:a )?walks?|running|jogging))(?: \w+){0,3}?"
            r"(?: at night| after dark| alone)?",
            r"low[- ]crime(?: area| neighborhood| rate)?",
        ),
        fixed_patterns=(
            r"(?:little|very little|hardly any|barely any|no) crime",
        ),
        negated_theme="area_crime",
    ),
)

OTHER_ISSUE_THEMES = (
    ThemeSpec(
        "other_issues", "parking", NEGATIVE, "Parking problems", "mention parking problems",
        patterns=(
            rf"parking (?:is|was|can be|has been|gets) {_INT}(?:a )?(?:nightmare|terrible|horrible|awful|difficult|hard|tough|"
            r"limited|tight|scarce|a pain|a hassle|an issue|a problem|impossible|bad|insufficient|competitive|a struggle|expensive)",
            r"(?:hard|difficult|impossible|tough|a nightmare|a pain) to (?:find|get) (?:a )?parking",
            r"parking (?:situation|issues?|problems?|nightmare)",
            r"(?:limited|terrible|horrible|awful|bad|difficult|tight|insufficient|expensive|overpriced|pricey) parking",
            r"(?:got|get|gets|getting) towed|towed (?:my|our) cars?",
            r"parking (?:fees?|costs?) (?:are|is) (?:high|expensive|ridiculous|outrageous)",
        ),
        fixed_patterns=(
            r"(?:not enough|lack of|no guest|no visitor|no assigned|no covered) parking",
        ),
    ),
    ThemeSpec(
        "other_issues", "ev_charging", NEGATIVE, "EV charging", "mention EV charging problems",
        fixed_patterns=(
            rf"ev charg(?:ers?|ing)(?: stations?| spots?)? {_W2}(?:broken|always taken|always occupied|not working|"
            r"never available|limited|expensive|full)",
            r"(?:no|not enough|limited|lack of|insufficient|broken|only (?:a few|two|2|one|1)) (?:ev|electric vehicle) "
            r"(?:charg\w+|stations?|spots?)",
            r"(?:hard|difficult|impossible) to (?:find|get) (?:an )?(?:ev |electric )?charg(?:er|ing)",
        ),
    ),
    ThemeSpec(
        "other_issues", "packages", NEGATIVE, "Package delivery issues", "mention package delivery issues",
        fixed_patterns=(
            rf"(?:package|amazon|luxer|parcel) (?:room|lockers?|area|system)s? {_W2}(?:full|overflowing|broken|a mess|always full|"
            r"too small|unreliable|down|not working)",
            rf"packages? {_W2}(?:left (?:outside|in the lobby|on the ground|at the door)|piled up|piling up|delayed)",
        ),
        suppressed_by=("package_handling", "package_theft"),
    ),
    ThemeSpec(
        "other_issues", "elevators", NEGATIVE, "Elevator problems", "mention elevator problems",
        fixed_patterns=(
            rf"elevators? {_W2}(?:broken|out of service|out of order|down|not working|doesn't work|don't work|stops working|"
            r"keeps breaking|always breaking|breaks down|broke down|stuck|slow)",
            r"(?:broken|slow|unreliable) elevators?",
            r"(?:stuck in|trapped in) (?:the |an )?elevator",
        ),
    ),
    ThemeSpec(
        "other_issues", "air_conditioning", NEGATIVE, "Air conditioning problems", "mention air conditioning problems",
        fixed_patterns=(
            rf"(?:no|without|lack of|didn't have|doesn't have|does not have|no central) {_AC}",
            rf"{_AC} {_W2}(?:broken|broke|not working|doesn't work|didn't work|don't work|stopped working|went out|is out|"
            r"was out|died|failed|barely works|weak|leaking|leaks)",
            rf"(?:broken|weak|faulty) {_AC}",
            rf"(?:never|didn't|did not|won't|wouldn't) (?:fix|fixed|repair|repaired) (?:the |our |my )?{_AC}",
            r"(?:apartment|unit|place|bedroom) (?:gets|is|was|got) (?:unbearably |extremely |super |so |very |really )?"
            r"(?:hot|stuffy|an oven)(?: in (?:the )?summer)?",
        ),
    ),
    ThemeSpec(
        "other_issues", "heating", NEGATIVE, "Heating problems", "mention heating problems",
        fixed_patterns=(
            r"(?:no|without|lack of) (?:heat|heating|heater)",
            rf"(?:heat|heating|heater|heaters|furnace|radiators?) {_W2}(?:broken|broke|not working|doesn't work|didn't work|"
            r"don't work|stopped working|went out|died|failed|barely works|weak|inadequate)",
            r"(?:broken|faulty|inadequate|weak) (?:heater|heating|heat|furnace)",
            r"(?:apartment|unit|place) (?:gets|is|was|got) (?:freezing|so cold|very cold|really cold|extremely cold|ice cold)",
            r"freezing in (?:the )?winter",
        ),
    ),
    ThemeSpec(
        "other_issues", "plumbing", NEGATIVE, "Plumbing and leaks", "mention plumbing problems or leaks",
        patterns=(
            r"leak(?:s|ing|y|ed)?",
            rf"(?:pipes?|faucets?|sinks?|toilets?|showers?|water heater|dishwasher|drains?) {_W2}(?:clogged|clogs|backed up|"
            r"backing up|overflow(?:ed|ing)?|burst)",
            r"(?:clogged|backed[- ]up|overflowing) (?:drains?|toilets?|sinks?|pipes?)",
            r"(?:low|weak|poor|terrible) water pressure",
            r"water pressure (?:is|was) (?:low|weak|poor|terrible|bad)",
            r"plumbing (?:issues?|problems?|is old|is terrible|was terrible|nightmare)",
            r"water damage|flood(?:ed|ing)",
        ),
        fixed_patterns=(
            r"(?:no|lack of|inconsistent|lukewarm|not enough|never any) hot water",
            rf"hot water {_W2}(?:goes out|went out|runs out|ran out|is inconsistent|takes forever|never works|not working|"
            r"was out|is out)",
        ),
    ),
    ThemeSpec(
        "other_issues", "water_shutdowns", NEGATIVE, "Water shutoffs", "mention water shutoffs",
        patterns=(
            rf"water {_W2}(?:shut ?offs?|shut off|turned off|outages?|cut off)",
            r"(?:frequent|constant|random|unannounced|unexpected) water (?:shut ?offs?|outages?)",
            r"(?:shut|shutting|turned|turning|cut|cutting) (?:off )?(?:the )?water(?: off)?",
        ),
        fixed_patterns=(
            r"no (?:running )?water (?:for|all|again)",
        ),
    ),
    ThemeSpec(
        "other_issues", "mold", NEGATIVE, "Mold", "mention mold",
        patterns=(r"mou?ldy?", r"mildew"),
    ),
    ThemeSpec(
        "other_issues", "trash", NEGATIVE, "Trash problems", "mention trash problems",
        patterns=(
            rf"(?:trash|garbage|dumpsters?|recycling|trash chutes?|garbage chutes?|trash rooms?|trash areas?) {_W3}"
            r"(?:overflowing|overflows|piled up|piles up|piling up|always full|smells?|smelly|stinks?|disgusting|dirty|"
            r"everywhere|not picked up|never picked up|broken|clogged)",
            r"(?:overflowing|smelly|disgusting|dirty) (?:trash|garbage|dumpsters?|recycling|bins)",
            rf"valet trash {_W2}(?:fees?|expensive|unreliable|missed|never)",
        ),
    ),
    ThemeSpec(
        "other_issues", "smells", NEGATIVE, "Odors", "mention persistent odors",
        patterns=(
            rf"(?:smells?|smelled|smelling|stinks?|stank|stunk|odors?|stench|reeks?) (?:like|of) {_W2}(?:smoke|weed|marijuana|"
            r"cigarettes?|sewage|sewer|garbage|trash|mold|mildew|urine|pee|gas|dogs?|cats?|pets?|feces|rotten \w+)",
            r"(?:weed|marijuana|cigarette|cigar|pot|smoke|sewage|sewer|gas|garbage|trash|urine|pet|musty|moldy|foul|bad|"
            r"weird|strange|terrible|horrible|awful|unpleasant) (?:smells?|odors?|stench)",
            r"smelly|stinky|musty",
            r"second[- ]?hand smoke",
            rf"smoke {_W3}(?:comes in|coming in|seeps|seeping|enters|through the vents|from (?:the )?neighbors?)",
        ),
    ),
    ThemeSpec(
        "other_issues", "laundry", NEGATIVE, "Laundry problems", "mention laundry problems",
        patterns=(
            rf"(?:laundry|washers?|dryers?|washing machines?|laundry machines?|laundry rooms?) {_W3}(?:broken|out of order|"
            r"not working|don't work|doesn't work|always taken|always full|always in use|never available|eats? (?:my )?"
            r"(?:money|quarters)|expensive|overpriced|dirty|filthy|unreliable)",
            r"(?:broken|expensive|dirty|unreliable) (?:laundry|washers?|dryers?|washing machines?)",
        ),
        fixed_patterns=(
            r"(?:not enough|only (?:one|two|a few|1|2|3)) (?:laundry machines|washers|dryers|washing machines)",
            r"(?:no|without) (?:in[- ]unit )?(?:laundry|washer|dryer|w/d|washer/dryer)",
        ),
    ),
    ThemeSpec(
        "other_issues", "internet", NEGATIVE, "Internet problems", "mention internet problems",
        patterns=(
            rf"(?:internet|wi-?fi|comcast|xfinity|broadband|isp|internet service) {_W3}(?:slow|spotty|unreliable|terrible|"
            r"horrible|awful|bad|goes out|went out|drops|dropping|keeps dropping|outages?|sucks|is a joke|not working|poor|"
            r"expensive|overpriced)",
            r"(?:slow|spotty|unreliable|terrible|horrible|awful|bad|poor|limited) (?:internet|wi-?fi|connection|broadband)",
            rf"(?:forced|required|mandatory|have to use) {_W2}(?:internet|comcast|xfinity|isp|bulk internet)",
        ),
        fixed_patterns=(
            r"no (?:internet|wi-?fi)",
            r"only (?:one|1) (?:internet )?(?:provider|isp|option)",
        ),
    ),
    ThemeSpec(
        "other_issues", "construction", NEGATIVE, "Ongoing construction", "mention ongoing construction",
        patterns=(
            r"(?:ongoing|constant|endless|never-?ending|nonstop|non-stop|current|major|lots of|so much|heavy) "
            r"(?:construction|renovations?|remodeling)",
            rf"(?:construction|renovations?|remodeling|scaffolding) {_W3}(?:going on|ongoing|for (?:months|years|over a year)|"
            r"everywhere|all the time|never ends|has been going|is going|blocking)",
            r"(?:under|during) (?:construction|renovations?)",
            r"scaffolding",
        ),
        suppressed_by=("construction_noise",),
    ),
    ThemeSpec(
        "other_issues", "insulation", NEGATIVE, "Poor insulation", "mention poor insulation or drafts",
        fixed_patterns=(
            r"(?:poor|bad|no|terrible|lack of|zero|little|inadequate) insulation",
            r"(?:poorly|badly|not) insulated",
            r"insulation (?:is|was) (?:poor|bad|terrible|nonexistent|non-existent|lacking|inadequate)",
            r"drafty",
            rf"drafts? {_W2}(?:windows?|doors?)",
            r"(?:single[- ]pane|leaky|drafty) windows",
        ),
    ),
    ThemeSpec(
        "other_issues", "utility_costs", NEGATIVE, "High utility costs", "mention high utility costs",
        patterns=(
            r"(?:high|expensive|outrageous|crazy|insane|ridiculous|huge|steep|excessive|exorbitant|sky[- ]high|astronomical) "
            r"(?:\w+ )?(?:utility|utilities|electric(?:ity)?|pg&e|pge|gas|water|energy|power) (?:bills?|costs?|fees?|charges?|rates?)",
            rf"(?:utility|utilities|electric(?:ity)?|pg&e|pge|gas|water|energy|power) (?:bills?|costs?|fees?|charges?) {_W2}"
            r"(?:high|expensive|outrageous|crazy|insane|ridiculous|huge|steep|excessive|through the roof|add up)",
            r"rubs|ratio utility billing",
            rf"(?:utilities|utility) (?:are|is) {_INT}(?:expensive|high|pricey)",
        ),
    ),
    ThemeSpec(
        "other_issues", "cell_reception", NEGATIVE, "Poor cell reception", "mention poor cell reception",
        patterns=(
            rf"(?:cell|cellular|phone|mobile|cell phone|verizon|at&t|t-mobile|tmobile) (?:\w+ )?(?:reception|signal|service|coverage) "
            rf"{_W2}(?:bad|terrible|horrible|awful|poor|weak|spotty|nonexistent|non-existent|sucks|is a joke|limited|drops)",
            r"(?:bad|terrible|horrible|awful|poor|weak|spotty|limited) (?:cell(?:ular)?|phone|mobile|lte|5g|4g) "
            r"(?:reception|signal|service|coverage)",
            r"(?:bad|terrible|poor|weak|spotty) (?:cell )?signal",
            r"dead zones?",
        ),
        fixed_patterns=(
            r"(?:no|zero|little) (?:cell(?:ular)?|phone|mobile|lte|5g|4g) (?:reception|signal|service|coverage)",
        ),
    ),
    ThemeSpec(
        "other_issues", "fire_alarms", NEGATIVE, "Fire alarm disruptions", "mention fire alarm disruptions",
        patterns=(
            rf"fire alarms? {_W3}(?:go(?:es)? off|went off|going off|constantly|all the time|at (?:\d|night|midnight)|false|"
            r"keeps? going off|middle of the night)",
            r"(?:false|frequent|constant|random) (?:fire )?alarms?",
            rf"smoke (?:detectors?|alarms?) {_W2}(?:go(?:es)? off|went off|beeping|chirping|keeps? going off)",
            r"fire alarms? (?:testing|tests)",
        ),
    ),
    ThemeSpec(
        "other_issues", "amenity_closures", NEGATIVE, "Amenity closures", "mention closed or broken amenities",
        patterns=(
            rf"(?:pool|gym|fitness (?:center|room)|hot tub|jacuzzi|spa|clubhouse|amenities|rooftop|roof deck|sauna|bbq|lounge|"
            rf"business center|tennis courts?)(?: area)? {_W3}(?:closed|shut down|out of order|broken|unavailable|never open|"
            r"not open|under repair)",
            r"(?:closed|broken|unusable|unavailable) (?:pool|gym|hot tub|jacuzzi|amenities|fitness center)",
        ),
    ),
    ThemeSpec(
        "other_issues", "move_out_fees", NEGATIVE, "Move-out fees", "mention move-out fees",
        patterns=(
            r"move[- ]out (?:fees?|charges?|costs?|bills?|cleaning (?:fee|charge)s?)",
            rf"(?:charged|billed) (?:me |us )?{_W4}(?:cleaning|carpet|paint(?:ing)?|repainting|repairs?|damages?|wear and tear)"
            r"(?: fees?| charges?| costs?)?",
            r"(?:cleaning|carpet cleaning|painting|repainting|carpet replacement) (?:fees?|charges?)",
            r"normal wear and tear",
        ),
    ),
)

THEMES = NOISE_THEMES + MANAGEMENT_THEMES + PEST_THEMES + BUILDING_SAFETY_THEMES + NEIGHBORHOOD_SAFETY_THEMES + OTHER_ISSUE_THEMES
THEMES_BY_NAME = {spec.theme: spec for spec in THEMES}

NEGATORS = frozenset({
    "no", "not", "never", "without", "zero", "nor", "neither", "none", "nothing", "hardly", "barely", "rarely", "seldom",
    "cannot", "dont", "didnt", "doesnt", "isnt", "wasnt", "arent", "werent", "havent", "hasnt", "hadnt", "cant", "couldnt",
    "wont", "wouldnt", "shouldnt", "aint",
})
NEGATION_EXCEPTIONS = (
    "no one", "no idea", "no matter", "no doubt", "no wonder", "no joke", "no exaggeration", "no surprise", "no end",
    "no way", "no longer care", "not only", "not just", "not sure", "not to mention", "without a doubt", "never mind",
    "nothing but",
)
NEGATION_FILLER = frozenset({
    "a", "an", "the", "any", "of", "with", "about", "regarding", "had", "have", "has", "having", "been", "be", "ever",
    "even", "seen", "saw", "see", "noticed", "notice", "found", "find", "experienced", "experience", "encountered",
    "dealt", "spotted", "heard", "hear", "single", "real", "major", "serious", "big", "much", "many", "really", "very",
    "too", "that", "so", "overly", "particularly", "super", "terribly", "especially", "exactly", "always", "at", "all",
    "problems", "problem", "issues", "issue", "sign", "signs", "trouble", "complaints", "complaint", "is", "are", "was",
    "were", "it", "it's", "its", "personally", "once", "longer", "more", "any", "kind", "sort", "type",
})
NEGATION_WINDOW = 6
LIST_CONNECTORS = frozenset({"or", "nor", "and", ",", "any", "even", "a", "an", "the", "/"})
POST_NEGATION = (
    r"^\s*(?:(?:is|are|was|were|has|have|had|been|be|ever|really|honestly|personally|truly|definitely|here|so far)\s+){0,3}"
    r"(?:not|never|no longer|isn't|wasn't|aren't|weren't|hasn't|haven't|hadn't|ain't|isnt|wasnt|arent|werent|hasnt|havent)\s+"
    r"(?:(?:been|ever|really|an?|any|much|of|too|that|very|big|real|major|serious|at all|even)\s+){0,3}"
    r"(?:problems?|issues?|concerns?|bad|noticeable|loud|annoying|bothersome|a bother|disruptive|a factor|a thing)\b"
    r"|^\s*(?:is|are|was|were|has been|have been|seems?|seemed)\s+(?:(?:very|pretty|quite|really|basically|virtually|almost|"
    r"practically)\s+)?(?:minimal|non-?existent|nonexistent|rare|negligible|unnoticeable)\b"
)
CLAUSE_END = r"[.,;:!?]|\bbut\b|\bthough\b|\balthough\b|\bhowever\b|\bexcept\b"
RECURRENCE = (
    r"\b(?:constant(?:ly)?|always|infest(?:ed|ation|ations)?|every (?:summer|winter|spring|fall|year|month|week|night|day|time)|"
    r"keeps? coming back|kept coming back|keeps? (?:showing up|returning|reappearing)|recurring|ongoing|all the time|"
    r"again and again|over and over|repeatedly|never (?:goes|go|went) away|chronic|everywhere|multiple times|several times|"
    r"numerous times|still (?:have|had|has|there|seeing|see))\b"
)
ANAPHORA_START = r"^(?:they|it|these|those|this|the (?:problem|issue|infestation))\b"
