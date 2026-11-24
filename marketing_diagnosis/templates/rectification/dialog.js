(() => {
  "use strict";
  const pick = id => document.getElementById("rectification-" + id);
  const data = JSON.parse(pick("data").textContent);
  const rows = pick("rows");
  const filter = pick("filter");
  const search = pick("search");
  const status = pick("status");
  const toast = document.getElementById("plan-toast");
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
  const hasCurrent = row => Boolean(row.facts.length || edits.get(row.id)?.facts?.trim());
  const isHeld = row => ["待业务确认", "暂不实施"].includes(row.status);
  const canFillCurrent = row => !isHeld(row) || row.allow_manual_current;
  const canEditProgress = row => row.status !== "暂不实施";
  const isUnreliable = row => ["数据过期", "口径冲突"].includes(row.status);
  const isDone = row => {
    const prog = valueFor(row, "progress").trim();
    return /已完成|已上线|已开通|已落实|已配置|已生效|已达标/.test(prog);
  };

  function element(tag, value, cls) {
    const el = document.createElement(tag);
    if (value) el.textContent = value;
    if (cls) el.className = cls;
    return el;
  }

  let toastTimer = null;
  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2600);
  }

  const channelButtons = channels.map(name => {
    const count = data.rows.filter(r => r.channel === name).length;
    const button = element("button", `${name} (${count})`);
    button.type = "button";
    button.dataset.name = name;
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
    updateDashboard();
  }

  function valueFor(row, key) {
    const defaults = { goal: row.goal, action: row.review };
    return edits.get(row.id)?.[key] ?? defaults[key] ?? "";
  }

  function evidence(row) {
    const facts = element("div", "", "plan-cell-content");
    if (row.balance_missing) facts.append(element("p", row.balance_missing, "plan-fact"));
    row.facts.forEach((fact, index) => {
      const last = row.facts.length > 1 && index === row.facts.length - 1;
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
    if (key === "facts" && (row.facts.length || row.balance_missing || isUnreliable(row))) {
      td.append(evidence(row));
    }
    if (key === "facts" && row.facts.length) {
      const manual = valueFor(row, key).trim();
      if (manual) td.append(element("p", "已补充 · " + manual, "plan-quiet plan-check"));
      return td;
    }
    const editableHeldCell = (key === "facts" && canFillCurrent(row))
      || (key === "progress" && canEditProgress(row));
    if (isHeld(row) && !editableHeldCell) {
      if (key === "progress") td.append(element("span", row.status, "plan-quiet"));
      if (key === "goal") td.textContent = valueFor(row, key);
      return td;
    }
    td.append(editableValue(row, key, label));
    const previousCheck = edits.get(row.id)?.check?.trim();
    if (key === "progress" && previousCheck) {
      td.append(element("p", "验收 · " + previousCheck, "plan-quiet plan-check"));
    }
    return td;
  }

  function editableValue(row, key, label) {
    const name = row.title + " · " + label;
    const button = element("button", "", "plan-cell-value");
    button.type = "button";

    function refresh() {
      const text = valueFor(row, key).trim();
      button.textContent = text || (key === "facts" ? "填写现状" : "—");
      button.classList.toggle("is-empty", !text);
      button.setAttribute("aria-label", "编辑 " + name + "：" + (text || "未填写"));
      const tr = button.closest("tr");
      if (tr && key === "progress") {
        tr.classList.toggle("is-done-row", isDone(row));
      }
    }
    refresh();

    button.addEventListener("click", () => {
      const isDate = ["start", "due"].includes(key);
      const isShort = isDate || key === "owner";
      const isProgress = key === "progress";

      const container = element("div", "", "plan-editor-box");
      const input = document.createElement(isProgress ? "textarea" : "input");
      if (isDate) {
        input.type = "date";
      } else if (!isProgress) {
        input.type = "text";
      } else {
        input.rows = 2;
      }
      input.className = "plan-cell-editor";
      input.maxLength = isShort ? 60 : 400;
      input.setAttribute("aria-label", name);
      input.value = valueFor(row, key);

      let closing = false;
      function closeEditor() {
        if (closing) return;
        closing = true;
        refresh();
        container.replaceWith(button);
        updateDashboard();
      }

      input.addEventListener("input", () => save(row, key, input.value));
      input.addEventListener("blur", () => {
        setTimeout(closeEditor, 160);
      });

      input.addEventListener("keydown", event => {
        if (event.isComposing) return;
        if (event.key === "Escape" || (event.key === "Enter" && (isShort || event.ctrlKey || event.metaKey))) {
          event.preventDefault();
          closeEditor();
          button.focus();
        }
      });

      container.append(input);

      if (isProgress) {
        const chips = element("div", "", "plan-quick-chips");
        ["已完成", "已上线", "进行中", "待跟进", "未开始"].forEach(label => {
          const chipBtn = element("button", label, "plan-chip-btn");
          chipBtn.type = "button";
          chipBtn.addEventListener("mousedown", e => {
            e.preventDefault();
            input.value = label;
            save(row, key, label);
            closeEditor();
            button.focus();
          });
          chips.append(chipBtn);
        });
        container.append(chips);
      }

      button.replaceWith(container);
      input.focus();
    });

    return button;
  }

  function rowElement(row, startsStage) {
    const tr = element("tr");
    tr.dataset.id = row.id;
    tr.setAttribute("role", "row");
    tr.classList.toggle("plan-stage-start", startsStage);
    tr.classList.toggle("is-done-row", isDone(row));

    const stage = cell("td", "工作阶段");
    stage.append(element("span", row.stage.replace(/\s+/g, "\n"),
      startsStage ? "plan-stage-name" : "plan-stage-name is-repeat"));
    stage.className = "plan-stage";

    const project = cell("th", "核心项目", row.title);
    project.scope = "row";
    project.className = "plan-item";

    tr.append(stage, project, ...fields.map(([key, name]) => inputCell(row, key, name)));
    return tr;
  }

  function updateDashboard() {
    const channelRows = data.rows.filter(row => row.channel === channel);
    const total = channelRows.length;
    const withFacts = channelRows.filter(row => hasCurrent(row)).length;
    const done = channelRows.filter(row => isDone(row)).length;
    const pending = total - done;
    const pct = total ? Math.round((done / total) * 100) : 0;

    const progVal = pick("progress-val");
    const progBar = pick("progress-bar");
    const progTip = pick("progress-tip");
    if (progVal) progVal.textContent = pct + "%";
    if (progBar) progBar.style.width = pct + "%";
    if (progTip) progTip.textContent = `已落实 ${done} 项，共 ${total} 项整改任务`;

    const statTotal = pick("stat-total");
    const statFacts = pick("stat-facts");
    const statPending = pick("stat-pending");
    const statDone = pick("stat-done");
    if (statTotal) statTotal.textContent = String(total);
    if (statFacts) statFacts.textContent = String(withFacts);
    if (statPending) statPending.textContent = String(pending);
    if (statDone) statDone.textContent = String(done);

    document.querySelectorAll(".plan-stat-card").forEach(card => {
      card.classList.toggle("is-active", card.dataset.filter === filter.value);
    });
  }

  document.querySelectorAll(".plan-stat-card").forEach(card => {
    card.addEventListener("click", () => {
      const targetFilter = card.dataset.filter;
      if (filter.value === targetFilter) {
        filter.value = "all";
      } else {
        filter.value = targetFilter;
      }
      render();
    });
    card.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        card.click();
      }
    });
  });

  function render() {
    const query = search.value.trim().toLowerCase();
    const channelRows = data.rows.filter(row => row.channel === channel);

    const list = channelRows.filter(row => {
      let matchesFilter = true;
      if (filter.value === "edited") {
        matchesFilter = hasEdits(row);
      } else if (filter.value === "pending") {
        matchesFilter = canFillCurrent(row) && !hasCurrent(row);
      } else if (filter.value === "done") {
        matchesFilter = isDone(row);
      } else if (filter.value === "todo") {
        matchesFilter = !isDone(row);
      } else if (filter.value === "facts") {
        matchesFilter = hasCurrent(row);
      }

      const matchesQuery = !query || [row.title, ...row.facts, ...Object.values(edits.get(row.id) || {})]
        .join(" ").toLowerCase().includes(query);

      return matchesFilter && matchesQuery;
    });

    channelButtons.forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.name === channel));
    });

    rows.replaceChildren(...list.map((row, index) => rowElement(row, index === 0 || row.stage !== list[index - 1].stage)));
    pick("empty").hidden = Boolean(list.length);
    pick("count").textContent = `显示 ${list.length} / ${channelRows.length} 项 · ${channelRows.filter(row => row.facts.length).length} 项已带入现状`;

    updateDashboard();
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
    const reportFacts = [row.balance_missing, ...row.facts, isUnreliable(row) ? row.status : ""]
      .filter(Boolean).join("\n");
    const current = [reportFacts, manual && (reportFacts ? "人工补充 · " + manual : manual)].filter(Boolean).join("\n");
    const previousCheck = edits.get(row.id)?.check?.trim();
    const progress = canEditProgress(row) ? [
      valueFor(row, "progress"), previousCheck && "验收 · " + previousCheck,
    ].filter(Boolean).join("\n") : row.status;
    return [current, valueFor(row, "goal"), valueFor(row, "action"), progress,
      valueFor(row, "start"), valueFor(row, "due"), valueFor(row, "owner")];
  }

  function refreshSheet(zip, path, channelName) {
    const xml = new DOMParser().parseFromString(fflate.strFromU8(zip[path]), "application/xml");
    const sheetRows = new Map([...xml.getElementsByTagNameNS(sheetNs, "row")].map(row => [row.getAttribute("r"), row]));
    const widths = [24, 20, 22, 18, 10, 16, 16];
    for (const plan of data.rows.filter(row => row.channel === channelName)) {
      const row = sheetRows.get(String(plan.excel_row));
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
      const url = URL.createObjectURL(new Blob([contents], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
      const link = element("a");
      link.href = url;
      link.download = data.hotel.replace(/[\\/:*?"<>|]/g, "_") + "_整改计划草案_" + data.key[1].replace(/[^0-9a-zA-Z_-]/g, "_") + ".xlsx";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = "Excel 已生成，包含当前网页已填写的内容。";
      showToast("Excel 已成功导出！");
    } catch {
      status.textContent = "暂时无法生成 Excel，已补填内容仍保留，请重试。";
    }
  });

  const copyBtn = document.getElementById("rectification-copy");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const channelRows = data.rows.filter(row => row.channel === channel);
      const todoList = channelRows.filter(r => !isDone(r));
      const doneCount = channelRows.length - todoList.length;

      let text = `🏨 【${data.hotel}】OTA 运营整改落地待办清单\n`;
      text += `📌 渠道：${channel} | 周期：${data.period}\n`;
      text += `📊 当前进度：${doneCount}/${channelRows.length} (${Math.round((doneCount / channelRows.length) * 100)}%)\n`;
      text += `----------------------------------------\n`;

      let curStage = "";
      todoList.forEach((r, idx) => {
        if (r.stage && r.stage !== curStage) {
          curStage = r.stage;
          text += `\n【${curStage.replace(/\s+/g, " ")}】\n`;
        }
        const prog = valueFor(r, "progress").trim() || "未开始";
        const owner = valueFor(r, "owner").trim() || "待认领";
        const due = valueFor(r, "due").trim() || "未定";
        text += `${idx + 1}. [${r.title}] 状态: ${prog} | 负责人: ${owner} | 截止: ${due}\n`;
        text += `   - 目标: ${valueFor(r, "goal").trim()}\n`;
        text += `   - 建议: ${valueFor(r, "action").trim()}\n`;
      });

      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(text).then(() => {
          showToast("已复制整改待办清单到剪贴板，可粘贴至工作群！");
        }).catch(() => {
          showToast("复制失败，请手动选取复制");
        });
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.append(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        showToast("已复制整改待办清单到剪贴板！");
      }
    });
  }

  filter.addEventListener("change", render);
  search.addEventListener("input", render);
  render();
})();