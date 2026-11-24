(() => {
  "use strict";
  const pick = id => document.getElementById("rectification-" + id);
  const data = JSON.parse(pick("data").textContent);
  const dialog = pick("dialog");
  const rows = pick("rows");
  const filter = pick("filter");
  const search = pick("search");
  const status = pick("status");
  const namespace = "s14:rectification:v1:" + JSON.stringify(data.key) + ":";
  const edits = new Map();
  const fields = [
    ["facts", "人工补充现状"], ["goal", "目标"], ["action", "整改措施"],
    ["owner", "负责人"], ["start", "启动时间"], ["due", "完成时间"], ["check", "验收方式"],
  ];
  const channels = [...new Set(data.rows.map(row => row.channel))];
  const sheetNs = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
  const selected = new URLSearchParams(location.search).get("channel") === "ctrip" ? "携程" : "美团";
  let channel = channels.includes(selected) ? selected : channels[0];
  let editingId = null;

  for (const row of data.rows) {
    try {
      const saved = JSON.parse(localStorage.getItem(namespace + row.id) || "{}");
      const values = {};
      for (const [key] of fields) {
        if (typeof saved?.[key] === "string") values[key] = saved[key].slice(0, 400);
      }
      if (Object.keys(values).length) edits.set(row.id, values);
    } catch {
      status.textContent = "浏览器存储暂不可用，仍可在当前页面补填并下载。";
    }
  }

  const hasEdits = row => fields.some(([key]) => edits.get(row.id)?.[key]?.trim());
  const isHeld = row => ["待业务确认", "暂不实施"].includes(row.status);
  const isReady = row => !isHeld(row) && (row.facts.length || edits.get(row.id)?.facts?.trim())
    && fields.slice(1).every(([key]) => edits.get(row.id)?.[key]?.trim());
  function label(row) {
    if (isHeld(row)) return row.status;
    if (isReady(row)) return "待复核";
    if (!row.facts.length && !edits.get(row.id)?.facts?.trim()) return row.status;
    return "待酒店确认";
  }

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

  function line(container, title, value) {
    const paragraph = element("p");
    paragraph.append(element("span", title, "plan-field"), document.createTextNode(value));
    container.append(paragraph);
  }

  function evidence(row, showManual) {
    const facts = element("div", "", "plan-cell-content");
    row.facts.forEach((fact, index) => facts.append(element(
      "p", fact, index === row.facts.length - 1 ? "plan-fact-date plan-quiet" : "plan-fact"
    )));
    if (!row.facts.length) facts.append(element("p", row.status, "plan-quiet"));
    if (row.anchor) {
      const href = new URL(data.report, window.location.href);
      if (channels.length > 1) href.searchParams.set("channel", row.channel === "携程" ? "ctrip" : "meituan");
      href.hash = row.anchor;
      const link = element("a", "诊断依据 · " + row.evidence);
      link.href = href.href;
      facts.append(link);
    }
    const additional = edits.get(row.id)?.facts?.trim();
    if (showManual && additional) line(facts, "人工补充", additional);
    return facts;
  }

  function editRow(row) {
    editingId = row.id;
    pick("title").textContent = "补填 · " + row.title;
    const form = element("div");
    for (const [key, name] of fields) {
      const caption = element("label", name);
      const control = document.createElement(["owner", "start", "due"].includes(key) ? "input" : "textarea");
      control.maxLength = control.tagName === "INPUT" ? 60 : 400;
      control.value = edits.get(row.id)?.[key] || "";
      if (key === "start" || key === "due") control.placeholder = "日期或相对时间";
      control.addEventListener("input", () => save(row, key, control.value));
      caption.append(control);
      form.append(caption);
    }
    pick("editor").replaceChildren(evidence(row, false), form);
    dialog.showModal();
  }

  function planDetails(row) {
    const details = element("div", "", "plan-cell-content");
    const draft = edits.get(row.id) || {};
    const recorded = fields.slice(1).filter(([key]) => draft[key]?.trim());
    if (recorded.length) {
      recorded.forEach(([key, name]) => line(details, name, draft[key].trim()));
    } else {
      const next = {
        "暂不实施": "当前不安排实施。",
        "待业务确认": "先确认项目定义和适用范围。",
        "数据过期": "先更新本项数据，再确认措施。",
        "口径冲突": "先复核数据口径，再确认措施。",
        "待补资料": "先补齐资料，再填写目标和措施。",
      };
      const review = (row.status === "待补资料" || row.facts.length) && row.review;
      if (review) {
        line(details, "建议下一步", review);
      } else {
        details.append(element("p", next[row.status] || "根据诊断依据复核现状后，填写目标和措施。", "plan-note"));
      }
    }
    return details;
  }

  function rowElement(row) {
    const tr = element("tr");
    const project = element("td");
    project.append(element("strong", row.title, "plan-item"), element("span", row.stage, "plan-stage"));
    const current = element("td");
    current.dataset.label = "现状与依据";
    current.append(evidence(row, true));
    const plan = element("td");
    plan.dataset.label = "整改计划";
    plan.append(planDetails(row));
    const actions = element("td");
    const badge = element("span", label(row), "plan-state");
    badge.dataset.tone = isReady(row) || row.status === "暂不实施" ? "neutral" : "pending";
    actions.append(badge);
    if (!isHeld(row)) {
      const button = element("button", hasEdits(row) ? "编辑" : "补填", "plan-edit");
      button.type = "button";
      button.dataset.row = row.id;
      button.setAttribute("aria-label", "编辑 " + row.title);
      button.addEventListener("click", () => editRow(row));
      const control = element("div");
      control.append(button);
      actions.append(control);
    }
    tr.append(project, current, plan, actions);
    return tr;
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    const channelRows = data.rows.filter(row => row.channel === channel);
    const list = channelRows.filter(row => (
      (filter.value === "all" || (filter.value === "edited" ? hasEdits(row) : !isHeld(row) && !isReady(row)))
      && (!query || [row.title, ...row.facts, ...Object.values(edits.get(row.id) || {})]
        .join(" ").toLowerCase().includes(query))
    ));
    channelButtons.forEach(button => button.setAttribute("aria-pressed", String(button.textContent === channel)));
    rows.replaceChildren(...list.map(rowElement));
    pick("empty").hidden = Boolean(list.length);
    pick("count").textContent = "显示 " + list.length + " / " + channelRows.length + " 项 · "
      + channelRows.filter(hasEdits).length + " 项已补填";
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
    const edit = isHeld(row) ? {} : edits.get(row.id) || {};
    const facts = row.facts.length
      ? "诊断现状\n" + row.facts.join("\n") + "\n依据 " + row.evidence
      : "诊断现状 · " + row.status;
    return [
      facts + (edit.facts?.trim() ? "\n人工补充 · " + edit.facts.trim() : ""),
      edit.goal || "", edit.action || "", label(row) + (edit.check?.trim() ? "\n验收 · " + edit.check.trim() : ""),
      edit.start || "", edit.due || "", edit.owner || "",
    ];
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
      status.textContent = "Excel 已生成，表内保留未补齐项目的状态。";
    } catch {
      status.textContent = "暂时无法生成 Excel，已补填内容仍保留，请重试。";
    }
  });

  filter.addEventListener("change", render);
  search.addEventListener("input", render);
  dialog.addEventListener("close", () => {
    render();
    (rows.querySelector('[data-row="' + editingId + '"]') || search).focus();
    editingId = null;
  });
  render();
})();
