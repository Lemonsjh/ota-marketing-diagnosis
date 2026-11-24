(() => {
  "use strict";
  const pick = id => document.getElementById("rectification-" + id);
  const data = JSON.parse(pick("data").textContent);
  const rows = pick("rows");
  const filter = pick("filter");
  const search = pick("search");
  const status = pick("status");
  const namespace = "s14:rectification:v1:" + JSON.stringify(data.key) + ":";
  const edits = new Map();
  const fields = [
    ["facts", "现状"], ["goal", "标准 / 本月目标"], ["action", "建议"],
    ["progress", "完成情况"], ["start", "启动时间"], ["due", "完成时间"], ["owner", "负责人"],
  ];
  const channels = [...new Set(data.rows.map(row => row.channel))];
  const sheetNs = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
  const selected = new URLSearchParams(location.search).get("channel") === "ctrip" ? "携程" : "美团";
  let channel = channels.includes(selected) ? selected : channels[0];

  for (const row of data.rows) {
    try {
      const saved = JSON.parse(localStorage.getItem(namespace + row.id) || "{}");
      const values = {};
      for (const [key] of [...fields, ["check"]]) {
        if (typeof saved?.[key] === "string") values[key] = saved[key].slice(0, 400);
      }
      if (Object.keys(values).length) edits.set(row.id, values);
    } catch {
      status.textContent = "浏览器存储暂不可用，仍可在当前页面补填并下载。";
    }
  }

  const hasEdits = row => Object.values(edits.get(row.id) || {}).some(value => value.trim());
  const hasCurrent = row => row.facts.length || edits.get(row.id)?.facts?.trim();
  const isHeld = row => ["待业务确认", "暂不实施"].includes(row.status);
  const isUnreliable = row => ["数据过期", "口径冲突"].includes(row.status);

  function element(tag, value, cls) {
    const el = document.createElement(tag);
    if (value) el.textContent = value;
    if (cls) el.className = cls;
    return el;
  }

  const channelButtons = channels.map(name => {
    const button = element("button", name);
    button.type = "button";
    button.addEventListener("click", () => {
      channel = name;
      render();
    });
    return button;
  });
  pick("channel").append(...channelButtons);

  function save(row, field, value) {
    const draft = { ...edits.get(row.id), [field]: value };
    edits.set(row.id, draft);
    try {
      localStorage.setItem(namespace + row.id, JSON.stringify(draft));
      status.textContent = "已保存在当前浏览器。";
    } catch {
      status.textContent = "本机保存失败，请先下载 Excel 再关闭页面。";
    }
  }

  function valueFor(row, key) {
    return edits.get(row.id)?.[key] ?? (key === "action" ? row.review || "" : "");
  }

  function evidence(row) {
    const facts = element("div", "", "plan-cell-content");
    row.facts.forEach((fact, index) => {
      const last = index === row.facts.length - 1;
      if (last && fact.startsWith("报告周期 ")) return;
      facts.append(element("p", fact, last ? "plan-fact-date plan-quiet" : "plan-fact"));
    });
    if (isUnreliable(row)) facts.append(element("p", row.status, "plan-quiet"));
    if (row.anchor) {
      const href = new URL(data.report, window.location.href);
      if (channels.length > 1) href.searchParams.set("channel", row.channel === "携程" ? "ctrip" : "meituan");
      href.hash = row.anchor;
      const link = element("a", "查看诊断依据");
      link.title = row.evidence;
      link.href = href.href;
      facts.append(link);
    }
    return facts;
  }

  function cell(elementType, label, content = "") {
    const td = element(elementType, content);
    td.dataset.label = label;
    td.setAttribute("role", elementType === "th" ? "rowheader" : "cell");
    return td;
  }

  function inputCell(row, key, label) {
    const td = cell("td", label);
    if (key === "facts" && (row.facts.length || isUnreliable(row))) td.append(evidence(row));
    if (isHeld(row)) {
      if (key === "progress") td.append(element("span", row.status, "plan-quiet"));
      return td;
    }
    const input = document.createElement("textarea");
    input.rows = key === "action" ? 3 : 2;
    input.maxLength = ["owner", "start", "due"].includes(key) ? 60 : 400;
    input.setAttribute("aria-label", row.title + " · " + label);
    input.value = valueFor(row, key);
    if (key === "facts") input.placeholder = row.facts.length ? "补充现状" : "填写现状";
    input.addEventListener("input", () => save(row, key, input.value));
    td.append(input);
    const previousCheck = edits.get(row.id)?.check?.trim();
    if (key === "progress" && previousCheck) {
      td.append(element("p", "验收 · " + previousCheck, "plan-quiet plan-check"));
    }
    return td;
  }

  function rowElement(row) {
    const tr = element("tr");
    tr.dataset.id = row.id;
    tr.setAttribute("role", "row");
    const stage = cell("td", "工作阶段", row.stage);
    stage.className = "plan-stage";
    const project = cell("th", "核心项目", row.title);
    project.scope = "row";
    project.className = "plan-item";
    tr.append(stage, project, ...fields.map(([key, name]) => inputCell(row, key, name)));
    return tr;
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    const channelRows = data.rows.filter(row => row.channel === channel);
    const list = channelRows.filter(row => (
      (filter.value === "all" || (filter.value === "edited" ? hasEdits(row) : !isHeld(row) && !hasCurrent(row)))
      && (!query || [row.title, ...row.facts, ...Object.values(edits.get(row.id) || {})]
        .join(" ").toLowerCase().includes(query))
    ));
    channelButtons.forEach(button => button.setAttribute("aria-pressed", String(button.textContent === channel)));
    rows.replaceChildren(...list.map(rowElement));
    pick("empty").hidden = Boolean(list.length);
    pick("count").textContent = "显示 " + list.length + " / " + channelRows.length + " 项 · "
      + channelRows.filter(row => row.facts.length).length + " 项已带入现状";
  }

  function setCell(xml, row, column, value) {
    const ref = column + row.getAttribute("r");
    const cells = [...row.children];
    let cell = cells.find(el => el.getAttribute("r") === ref);
    if (!cell) {
      cell = xml.createElementNS(sheetNs, "c");
      cell.setAttribute("r", ref);
      row.insertBefore(cell, cells.find(el => (el.getAttribute("r") || "")[0] > column) || null);
    }
    cell.setAttribute("t", "inlineStr");
    const inline = xml.createElementNS(sheetNs, "is");
    const text = xml.createElementNS(sheetNs, "t");
    text.setAttributeNS("http://www.w3.org/XML/1998/namespace", "xml:space", "preserve");
    text.textContent = String(value).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");
    inline.append(text);
    cell.replaceChildren(inline);
  }

  function exportValues(row) {
    const manual = valueFor(row, "facts").trim();
    const reportFacts = row.facts.length
      ? row.facts.join("\n") + "\n依据 " + row.evidence
      : isUnreliable(row) ? row.status : "";
    const current = [reportFacts, manual && (reportFacts ? "人工补充 · " + manual : manual)].filter(Boolean).join("\n");
    const previousCheck = edits.get(row.id)?.check?.trim();
    const progress = isHeld(row) ? row.status : [
      valueFor(row, "progress"), previousCheck && "验收 · " + previousCheck,
    ].filter(Boolean).join("\n");
    return [current, valueFor(row, "goal"), valueFor(row, "action"), progress,
      valueFor(row, "start"), valueFor(row, "due"), valueFor(row, "owner")];
  }

  function refreshSheet(zip, path, channelName) {
    const xml = new DOMParser().parseFromString(fflate.strFromU8(zip[path]), "application/xml");
    const sheetRows = new Map([...xml.getElementsByTagNameNS(sheetNs, "row")].map(row => [row.getAttribute("r"), row]));
    const widths = [24, 20, 22, 18, 10, 16, 16];
    for (const plan of data.rows.filter(row => row.channel === channelName)) {
      const row = sheetRows.get(plan.id.slice(1));
      if (!row) throw new Error("Plan row missing in template");
      let lines = 1;
      exportValues(plan).forEach((value, index) => {
        setCell(xml, row, "CDEFGHI"[index], value);
        const count = String(value).split("\n").reduce((sum, line) => {
          const len = [...line].reduce((width, char) => width + (char.charCodeAt(0) > 255 ? 2 : 1), 0);
          return sum + Math.max(1, Math.ceil(len / widths[index]));
        }, 0);
        lines = Math.max(lines, count);
      });
      row.setAttribute("ht", Math.min(409, Math.max(Number(row.getAttribute("ht") || 0), lines * 15 + 8)));
      row.setAttribute("customHeight", "1");
    }
    zip[path] = fflate.strToU8(new XMLSerializer().serializeToString(xml));
  }

  pick("download").addEventListener("click", () => {
    try {
      const original = Uint8Array.from(atob(data.workbook), char => char.charCodeAt(0));
      const zip = fflate.unzipSync(original);
      channels.forEach((name, index) => refreshSheet(zip, "xl/worksheets/sheet" + (index + 1) + ".xml", name));
      const contents = fflate.zipSync(zip);
      const url = URL.createObjectURL(new Blob([contents], {type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}));
      const link = element("a");
      link.href = url;
      link.download = data.hotel.replace(/[\\/:*?"<>|]/g, "_") + "_整改计划草案_" + data.key[1].replace(/[^0-9a-zA-Z_-]/g, "_") + ".xlsx";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = "Excel 已生成，包含当前网页已填写的内容。";
    } catch {
      status.textContent = "暂时无法生成 Excel，已补填内容仍保留，请重试。";
    }
  });

  filter.addEventListener("change", render);
  search.addEventListener("input", render);
  render();
})();
