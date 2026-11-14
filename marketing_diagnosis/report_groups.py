"""Organize existing HTML modules by topic without rebuilding their contents."""
from html.parser import HTMLParser
import re


TITLES = (
    "经营结果与房型收益", "流量转化与市场竞争", "页面信息与产品展示", "价格政策与预订条件",
    "口碑与服务", "活动权益与渠道合作", "推广与扫码执行", "平台质量与接单履约",
)

# IDs here are the generated page anchors, which differ from displayed numbers.
RULES = {
    "meituan": ((1, 2), (3, 4, 5, 12), (8, 10, 11, 21), (), (13,), (14, 22), (7, 9), (6,)),
    "ctrip": ((1, 2), (3, 4, 5), (8, 10, 11, 19, 20), (), (12,), (13, 14, 15, 16, 17, 18, 21), (7, 9), (6,)),
}
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
STYLE = """<style id="REPORT_GROUPS_STYLE">
.report-topic-title{display:flex;align-items:baseline;gap:.7em;margin:28px 0 14px;padding:11px 14px;border-left:4px solid #16845b;background:#eaf5f0;color:#153a32;font-size:clamp(18px,2vw,24px);line-height:1.4;scroll-margin-top:95px}
.report-topic-title small{font-size:.65em;color:#24664f;font-variant-numeric:tabular-nums}
.report-topic-title~.diagnosis-card .rule-no{font-size:13px;white-space:nowrap}
.report-topic-note{margin:0 0 16px;color:#526877;font-size:14px}
@media print{.report-topic-title{margin:12px 0 6px;padding:5px 8px;font-size:15px;break-after:avoid;page-break-after:avoid}}
</style>"""


class Blocks(HTMLParser):
    """Find direct HTML children while retaining their original source spans."""

    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.nodes = []
        self.lines = [0, *(m.end() for m in re.finditer("\n", source))]
        self.source = source
        self.feed(source)
        self.close()

    def source_offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            self.handle_startendtag(tag, attrs)
        else:
            self.stack.append((tag, dict(attrs), self.source_offset()))

    def handle_startendtag(self, tag, attrs):
        if not self.stack:
            start = self.source_offset()
            self.nodes.append((tag, dict(attrs), start, start + len(self.get_starttag_text())))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            node = self.stack.pop()
            if not self.stack:
                self.nodes.append((*node, self.source.index(">", self.source_offset()) + 1))


MEITUAN_CONFIG_GROUPS = {2: (19,), 3: (20,), 5: (15, 16, 17, 18), 7: (23,)}


def _split_meituan_config(markup):
    table = re.search(
        r"(<table\b[^>]*>\s*<thead\b[^>]*>.*?</thead>\s*<tbody\b[^>]*>)(.*?)(</tbody>\s*</table>)",
        markup, re.S,
    )
    if not table:
        return {}
    body = table[2]
    parsed = Blocks(body)
    if parsed.stack or any(tag != "tr" or not attrs.get("id") for tag, attrs, _, _ in parsed.nodes):
        return {}
    rows = {attrs["id"]: body[start:end] for _, attrs, start, end in parsed.nodes}
    expected = {f"rule-{number}" for numbers in MEITUAN_CONFIG_GROUPS.values() for number in numbers}
    if len(parsed.nodes) != len(expected) or rows.keys() != expected:
        return {}

    return {
        group: (
            "<article class='diagnosis-card config-status-group'>"
            "<div class='result-area config-status-result'><div class='viz-card config-status-card'>"
            "<div class='table-scroll'>" + table[1]
            + "".join(rows[f"rule-{number}"] for number in numbers)
            + table[3] + "</div></div></div></article>"
        )
        for group, numbers in MEITUAN_CONFIG_GROUPS.items()
    }


RULE_ANCHOR = re.compile(r"(?:ctrip-)?(?:rule|module)-(\d+)$")
ITEM_BADGE = re.compile(r"(<div\b[^>]*class=['\"]rule-no['\"][^>]*>)[^<]*(</div>)")
CONFIG_NUMBER = re.compile(r"(<td\b[^>]*class=['\"]config-rule-number['\"][^>]*>)[^<]*(</td>)")
CONFIG_ROW = re.compile(r"<tr\b[^>]*id=['\"](rule-\d+)['\"][^>]*>.*?</tr>", re.S)


def _number_items(cards, topic, labels):
    index = 0
    numbered = []
    for card in cards:
        def next_label(node_id):
            nonlocal index
            index += 1
            label = f"{topic:02d}.{index}"
            if match := RULE_ANCHOR.fullmatch(node_id):
                labels[int(match[1])] = label
            return label

        def number_row(match):
            label = next_label(match[1])
            return CONFIG_NUMBER.sub(lambda cell: cell[1] + label + cell[2], match[0], count=1)

        if CONFIG_ROW.search(card):
            card = CONFIG_ROW.sub(number_row, card)
        else:
            node_id = re.search(r"\bid=['\"]([^'\"]+)['\"]", card.split(">", 1)[0])
            label = next_label(node_id[1] if node_id else "")
            card = ITEM_BADGE.sub(lambda badge: badge[1] + label + badge[2], card, count=1)
        numbered.append(card)
    return numbered


def _number_summary(markup, labels):
    def number_row(match):
        row = match[0]
        anchor = re.search(r"href=['\"]#([^'\"]+)['\"]", row)
        key = RULE_ANCHOR.fullmatch(anchor[1]) if anchor else None
        label = labels.get(int(key[1])) if key else None
        if label is None:
            return row
        return re.sub(r"(<td\b[^>]*>)\s*\d+\s*(</td>)",
                      lambda cell: cell[1] + label + cell[2], row, count=1)
    return re.sub(r"<tr\b[^>]*>.*?</tr>", number_row, markup, flags=re.S)


def _partition(body, channel, dual):
    groups = [[] for _ in TITLES]
    appendix, prefix, scripts = [], [], []
    mapping = {f"rule-{number}": group for group, numbers in enumerate(RULES[channel]) for number in numbers}
    mapping["mt-price" if channel == "meituan" else "ct-price"] = 3
    parsed = Blocks(body)
    if not parsed.nodes or parsed.stack:
        return None
    for tag, attrs, start, end in parsed.nodes:
        markup = body[start:end]
        node_id = (attrs.get("id") or "").removeprefix("ctrip-")
        classes = (attrs.get("class") or "").split()
        if tag == "script":
            scripts.append(markup)
        elif node_id in ("overview", "summary") or "report-opening" in classes:
            prefix.append(markup)
        elif "diagnosis-pair-v17" in classes:
            inner = markup[markup.index(">") + 1:markup.rfind("</div>")]
            pair = Blocks(inner)
            card_nodes = [(a, s, e) for tag, a, s, e in pair.nodes if tag != "script"]
            card_ids = {(a.get("id") or "").removeprefix("ctrip-") for a, _, _ in card_nodes}
            if not pair.stack and len(card_nodes) == 2 and card_ids == {"rule-7", "rule-8"}:
                for attrs, start, end in card_nodes:
                    key = attrs["id"].removeprefix("ctrip-")
                    groups[mapping[key]].append(inner[start:end])
                scripts.extend(inner[s:e] for tag, _, s, e in pair.nodes if tag == "script")
            else:
                appendix.append(markup)
        elif channel == "meituan" and node_id == "config-status-group":
            tables = _split_meituan_config(markup)
            if not tables:
                appendix.append(markup)
            for group, config_table in tables.items():
                groups[group].append(config_table)
        elif node_id in mapping:
            groups[mapping[node_id]].append(markup)
        else:
            appendix.append(markup)
    if not any(groups):
        return None

    nav = []
    labels = {}
    overview_count = len(prefix)
    for number, (title, cards) in enumerate(zip(TITLES, groups), 1):
        anchor = f"topic-{number}"
        node_id = f"ctrip-{anchor}" if dual and channel == "ctrip" else anchor
        nav.append(f"<a href='#{anchor}'><span>{number:02d}</span>{title}</a>")
        prefix.append(f"<h2 class='report-topic-title' id='{node_id}' data-channel-anchor='{anchor}'><small>{number:02d}</small>{title}</h2>")
        prefix.extend(_number_items(cards, number, labels) or ["<p class='report-topic-note'>当前报告暂无此板块的独立模块。</p>"])
    if appendix:
        node_id = "ctrip-topic-original" if dual and channel == "ctrip" else "topic-original"
        nav.append("<a href='#topic-original'><span>附</span>原报告附录</a>")
        prefix.append(f"<h2 class='report-topic-title' id='{node_id}' data-channel-anchor='topic-original'>原报告附录</h2>")
        prefix.append("<p class='report-topic-note'>保留跨板块汇总及未归类的原报告模块。</p>")
        prefix.extend(appendix)
    prefix[:overview_count] = [_number_summary(part, labels) if re.match(
        r"<(?:details|section)\b[^>]*id=['\"](?:ctrip-)?summary['\"]", part
    ) else part for part in prefix[:overview_count]]
    return "\n".join(prefix + scripts), "".join(nav)


def organize_report_html(document, channel=None):
    main = re.compile(r"(<main\b[^>]*>)(.*?)(</main>)", re.S)
    sidebar = re.compile(r"(<nav\b[^>]*\bclass=(['\"])side\2[^>]*>)(.*?)(</nav>)", re.S)
    mains, sidebars = list(main.finditer(document)), list(sidebar.finditer(document))
    if len(mains) != len(sidebars) or not mains or (channel is None and len(mains) != 2):
        return document
    for i, (section, side) in reversed(list(enumerate(zip(mains, sidebars)))):
        active = channel or ("meituan", "ctrip")[i]
        partition = _partition(section[2], active, channel is None)
        if not partition:
            continue
        body, links = partition
        existing = re.sub(
            r"<a\b[^>]*\bhref=(['\"])#(?:(?:ctrip-)?rule|module)-\d+\1[^>]*>.*?</a>",
            "", side[3], flags=re.S,
        )
        document = document[:section.start(2)] + body + document[section.end(2):]
        document = document[:side.start(3)] + existing + links + document[side.end(3):]
    return document.replace("</head>", STYLE + "</head>", 1)

