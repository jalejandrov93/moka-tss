// SPDX-License-Identifier: GPL-3.0-or-later
//
// turing-smart-screen-python - a Python system monitor and library for USB-C displays
// Mascota fork - client script for the local web configuration panel (D13)
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version. See LICENSE for the full text.
//
// Plain vanilla JS, no framework, no build step: this has to survive being
// served straight out of a frozen .exe (T12). Talks only to same-origin
// /api/* endpoints served by library/mascota/webconfig.py.

(function () {
  "use strict";

  var PROVIDERS = [
    { id: "claude", label: "Claude" },
    { id: "codex", label: "Codex" },
    { id: "antigravity", label: "Antigravity" },
    { id: "opencodego", label: "OpenCode Go" },
    { id: "copilot", label: "GitHub Copilot" },
  ];

  var configForm = document.getElementById("config-form");
  var providersList = document.getElementById("providers-list");
  var brightnessInput = document.getElementById("brightness");
  var brightnessValue = document.getElementById("brightness-value");
  var globalMessage = document.getElementById("global-message");
  var rulesBody = document.getElementById("rules-body");
  var defaultMoodSelect = document.getElementById("default-mood");
  var moodsListInput = document.getElementById("moods-list");
  var rulesMessage = document.getElementById("rules-message");

  var currentRules = { moods: [], default_mood: null, rules: [] };

  function showMessage(el, text, kind) {
    el.textContent = text;
    el.setAttribute("data-kind", kind || "");
  }

  function fetchJson(url, options) {
    return fetch(url, options).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) {
          var error = new Error((body && body.error) || ("HTTP " + response.status));
          error.body = body;
          throw error;
        }
        return body;
      });
    });
  }

  function postJson(url, data) {
    return fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  }

  function renderProviders(hidden) {
    hidden = hidden || [];
    providersList.innerHTML = "";
    PROVIDERS.forEach(function (provider) {
      var wrapper = document.createElement("label");
      var checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = "provider_" + provider.id;
      checkbox.checked = hidden.indexOf(provider.id) === -1;
      wrapper.appendChild(checkbox);
      wrapper.appendChild(document.createTextNode(provider.label));
      providersList.appendChild(wrapper);
    });
  }

  function collectHiddenProviders() {
    var hidden = [];
    PROVIDERS.forEach(function (provider) {
      var checkbox = configForm.querySelector('[name="provider_' + provider.id + '"]');
      if (checkbox && !checkbox.checked) {
        hidden.push(provider.id);
      }
    });
    return hidden;
  }

  function fillConfigForm(config) {
    configForm.elements.codexbar_url.value = config.codexbar_url || "";
    configForm.elements.agenthub_url.value = config.agenthub_url || "";
    configForm.elements.orientation.value = config.orientation || "landscape";
    configForm.elements.refresh_interval_seconds.value = config.refresh_interval_seconds || 2;
    var brightness = typeof config.brightness === "number" ? config.brightness : 85;
    brightnessInput.value = String(brightness);
    brightnessValue.textContent = String(brightness);
    renderProviders(config.hidden_providers);
  }

  function loadConfig() {
    return fetchJson("/api/config").then(fillConfigForm);
  }

  function loadStatus() {
    return fetchJson("/api/status").then(function (status) {
      var dot = document.getElementById("status-dot");
      var connectedLabel = document.getElementById("status-connected");
      var moodLabel = document.getElementById("status-mood");
      var refreshLabel = document.getElementById("status-refresh");
      dot.classList.toggle("is-connected", !!status.connected);
      connectedLabel.textContent = status.connected ? "Conectado" : "Sin conexión";
      moodLabel.textContent = status.mood || "—";
      refreshLabel.textContent = status.last_refresh ? String(status.last_refresh) : "—";
    });
  }

  brightnessInput.addEventListener("input", function () {
    brightnessValue.textContent = brightnessInput.value;
  });

  configForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var payload = {
      codexbar_url: configForm.elements.codexbar_url.value.trim(),
      agenthub_url: configForm.elements.agenthub_url.value.trim(),
      hidden_providers: collectHiddenProviders(),
      brightness: Number(brightnessInput.value),
      orientation: configForm.elements.orientation.value,
      refresh_interval_seconds: Number(configForm.elements.refresh_interval_seconds.value),
    };
    postJson("/api/config", payload)
      .then(function () {
        showMessage(globalMessage, "Configuración guardada.", "ok");
      })
      .catch(function (error) {
        showMessage(globalMessage, "No se pudo guardar: " + error.message, "error");
      });
  });

  loadConfig().catch(function (error) {
    showMessage(globalMessage, "No se pudo cargar la configuración: " + error.message, "error");
  });
  loadStatus().catch(function () {
    // The panel must stay usable even if the app has not wired live
    // status yet; the fields already show their placeholder dashes.
  });

  // -- Rules editor ---------------------------------------------------

  var RULE_FIELDS = [
    "id", "metric", "op", "value", "for", "mood", "priority", "release", "release_for",
  ];
  var OPERATORS = [">=", ">", "<=", "<", "==", "!="];

  function makeCell(tag) {
    var cell = document.createElement("td");
    var el = document.createElement(tag);
    cell.appendChild(el);
    return { cell: cell, el: el };
  }

  function renderMoodOptions(select, moods, selected) {
    select.innerHTML = "";
    moods.forEach(function (mood) {
      var option = document.createElement("option");
      option.value = mood;
      option.textContent = mood;
      if (mood === selected) {
        option.selected = true;
      }
      select.appendChild(option);
    });
  }

  function renderRuleRow(rule) {
    var row = document.createElement("tr");
    var inputs = {};

    ["id", "metric"].forEach(function (field) {
      var built = makeCell("input");
      built.el.type = "text";
      built.el.value = rule[field] != null ? rule[field] : "";
      built.el.setAttribute("aria-label", field);
      inputs[field] = built.el;
      row.appendChild(built.cell);
    });

    var opCell = makeCell("select");
    OPERATORS.forEach(function (op) {
      var option = document.createElement("option");
      option.value = op;
      option.textContent = op;
      if (rule.op === op) {
        option.selected = true;
      }
      opCell.el.appendChild(option);
    });
    inputs.op = opCell.el;
    row.appendChild(opCell.cell);

    ["value", "for", "mood-placeholder", "priority", "release", "release_for"].forEach(
      function (field) {
        if (field === "mood-placeholder") {
          var moodCell = makeCell("select");
          renderMoodOptions(moodCell.el, currentRules.moods || [], rule.mood);
          inputs.mood = moodCell.el;
          row.appendChild(moodCell.cell);
          return;
        }
        var built = makeCell("input");
        built.el.type = "number";
        built.el.step = "any";
        if (rule[field] !== undefined && rule[field] !== null) {
          built.el.value = rule[field];
        }
        built.el.setAttribute("aria-label", field);
        inputs[field] = built.el;
        row.appendChild(built.cell);
      }
    );

    var actionCell = document.createElement("td");
    var removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "danger";
    removeButton.textContent = "Quitar";
    removeButton.addEventListener("click", function () {
      row.remove();
    });
    actionCell.appendChild(removeButton);
    row.appendChild(actionCell);

    row._inputs = inputs;
    return row;
  }

  function renderRulesTable() {
    rulesBody.innerHTML = "";
    (currentRules.rules || []).forEach(function (rule) {
      rulesBody.appendChild(renderRuleRow(rule));
    });
    renderMoodOptions(defaultMoodSelect, currentRules.moods || [], currentRules.default_mood);
    moodsListInput.value = (currentRules.moods || []).join(", ");
  }

  function collectRulesFromTable() {
    var moods = moodsListInput.value
      .split(",")
      .map(function (mood) { return mood.trim(); })
      .filter(function (mood) { return mood.length > 0; });

    var rules = Array.prototype.map.call(rulesBody.children, function (row) {
      var inputs = row._inputs;
      var rule = {
        id: inputs.id.value.trim(),
        metric: inputs.metric.value.trim(),
        op: inputs.op.value,
        value: Number(inputs.value.value),
        mood: inputs.mood.value,
      };
      if (inputs["for"].value !== "") rule["for"] = Number(inputs["for"].value);
      if (inputs.priority.value !== "") rule.priority = Number(inputs.priority.value);
      if (inputs.release.value !== "") rule.release = Number(inputs.release.value);
      if (inputs.release_for.value !== "") rule.release_for = Number(inputs.release_for.value);
      return rule;
    });

    return {
      moods: moods,
      default_mood: defaultMoodSelect.value,
      rules: rules,
    };
  }

  document.getElementById("add-rule-button").addEventListener("click", function () {
    rulesBody.appendChild(
      renderRuleRow({ id: "", metric: "", op: ">=", value: 0, mood: currentRules.default_mood })
    );
  });

  document.getElementById("save-rules-button").addEventListener("click", function () {
    var payload = collectRulesFromTable();
    postJson("/api/rules", payload)
      .then(function (saved) {
        currentRules = saved;
        renderRulesTable();
        showMessage(rulesMessage, "Reglas guardadas.", "ok");
      })
      .catch(function (error) {
        showMessage(rulesMessage, "No se pudo guardar: " + error.message, "error");
      });
  });

  fetchJson("/api/rules")
    .then(function (rules) {
      currentRules = rules;
      renderRulesTable();
    })
    .catch(function (error) {
      showMessage(rulesMessage, "No se pudieron cargar las reglas: " + error.message, "error");
    });
})();
