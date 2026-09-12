"""Offline description matching. A match is a notice, never a diagnosis."""
import re
import unicodedata

RULE_VERSION = 'offline-danger-v1'
DANGER_REMINDER = '原始记录中出现需要及时人工或急救专业人员判断的描述，请联系当地急救服务或专业人员，不要自行改药。'

# Keep the earlier rules as well as the requested synonyms. Deliberately
# conservative: negation, history and hypothetical mentions may still match.
RULES = (
    ('chest', r'胸痛|胸口(?:疼|痛)|胸(?:部)?疼痛|胸闷'),
    ('breathing', r'呼吸(?:困难|.*困难)|喘不(?:上|过)(?:来)?气|喘不过来|呼吸不上来|喘不上来|呼吸费力'),
    ('consciousness', r'昏迷|叫不醒|喊不醒|唤不醒|意识不清|失去意识|不省人事'),
    ('convulsion', r'抽搐|全身抽动'),
    ('bleeding', r'大量出血|严重出血|止不住血|出血不止|血流不止'),
    ('neurologic_description', r'突然[^，。！？；\n]{0,6}(?:不能说话|说不出话|不会说话)|口角歪|嘴角歪|一侧(?:肢体)?无力|半边(?:身体)?(?:无力|没劲)|说话含糊|突发.*无力'),
    ('injury', r'严重摔倒|摔倒|头部受伤|头部外伤|摔伤头部|撞到头|磕到头'),
    ('persistent_vomiting', r'呕吐.*停'),
    ('extreme_pressure_description', r'血压(?:极高|极低|非常高|非常低|高得吓人|低得吓人)'),
)
PRESSURE_PAIR = re.compile(r'血压\s*(?:高达|达到|超过|是|为|降至|升至)?\s*(\d{2,3})\s*(?:/|比|[，,])\s*(\d{2,3})')
PRESSURE_SINGLE = re.compile(r'(收缩压|高压|舒张压|低压)\s*(?:高达|达到|超过|是|为|降至|升至)?\s*(\d{2,3})')


def scan_danger(raw_text):
    text = unicodedata.normalize('NFKC', str(raw_text or ''))
    matched = [name for name, pattern in RULES if re.search(pattern, text)]
    # MVP matching cutoffs, retaining the old 180/110 rule. No diagnosis,
    # severity estimate, medication decision, or assurance from a non-match.
    for match in PRESSURE_PAIR.finditer(text):
        systolic, diastolic = map(int, match.groups())
        if systolic >= 180 or diastolic >= 110 or systolic < 80 or diastolic < 50:
            matched.append('extreme_pressure_number')
    for label, value in PRESSURE_SINGLE.findall(text):
        value = int(value)
        if (label in ('收缩压', '高压') and (value >= 180 or value < 80)) or (label in ('舒张压', '低压') and (value >= 110 or value < 50)):
            matched.append('extreme_pressure_number')
    matched = list(dict.fromkeys(matched))
    return {
        'danger_detected': bool(matched),
        'escalation_level': 'emergency' if matched else 'none',
        'review_role': 'emergency_services' if matched else 'none',
        'danger_reminder': DANGER_REMINDER if matched else None,
        'matched_rules': matched,
        'safety_rule_version': RULE_VERSION,
    }
