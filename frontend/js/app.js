const socketAddress = `ws://${window.location.host}/ws`;

async function getData(path) {
  const response = await fetch(path);
  return response.json();
}

async function sendPost(path) {
  const response = await fetch(path, { method: "POST" });
  return response.json();
}

function getElement(id) {
  return document.getElementById(id);
}

const statusColors = {
  COMPLETED: "#047857",
  SUSPICIOUS: "#c2690a",
  FAILED: "#c0271d",
};

const statusRgbColors = {
  COMPLETED: "4,120,87",
  SUSPICIOUS: "194,105,10",
  FAILED: "192,39,29",
};

const statusNames = {
  COMPLETED: "Completed",
  SUSPICIOUS: "Suspicious",
  FAILED: "Failed",
};

const feedList = getElement("feedList");
const suspiciousList = getElement("suspiciousList");
const failedList = getElement("failedList");
const suspiciousCountText = getElement("suspiciousCount");
const failedCountText = getElement("failedCount");

let suspiciousCount = 0;
let failedCount = 0;
let completedCount = 0;
let transactionIds = {};

const arcTime = 2600;
let cityLocations = {};
let arcs = [];
let rings = [];

const globe = Globe()(getElement("globeViz"))
  .globeImageUrl("https://unpkg.com/three-globe/example/img/earth-day.jpg")
  .bumpImageUrl("https://unpkg.com/three-globe/example/img/earth-topology.png")
  .backgroundColor("rgba(0,0,0,0)")
  .showAtmosphere(true)
  .atmosphereColor("#9cc4ff")
  .atmosphereAltitude(0.15)
  .arcColor((item) => item.color)
  .arcStroke(0.5)
  .arcAltitudeAutoScale(0.45)
  .arcDashLength(0.35)
  .arcDashGap(2)
  .arcDashInitialGap(1)
  .arcDashAnimateTime(arcTime)
  .arcsTransitionDuration(0)
  .arcLabel((item) => item.label)
  .labelLat((city) => city.lat)
  .labelLng((city) => city.lng)
  .labelText((city) => city.city)
  .labelSize(1.05)
  .labelDotRadius(0.42)
  .labelColor(() => "#0b1324")
  .labelAltitude(0.012)
  .labelResolution(2)
  .ringColor((item) => (progress) => `rgba(${item.rgb}, ${1 - progress})`)
  .ringMaxRadius(2.2)
  .ringPropagationSpeed(2.4)
  .ringRepeatPeriod(arcTime);

globe.pointOfView({ lat: 18, lng: 15, altitude: 2.6 });

function resizeGlobe() {
  const globeBox = getElement("globeViz");
  globe.width(globeBox.clientWidth).height(globeBox.clientHeight);
}

window.addEventListener("resize", resizeGlobe);
resizeGlobe();

async function loadLocations() {
  const cities = await getData("/api/locations");
  cityLocations = {};

  cities.forEach((city) => {
    cityLocations[city.city] = { lat: city.lat, lng: city.lng };
  });

  globe.labelsData(cities);
}

function addArc(transaction) {
  const from = cityLocations[transaction.origin.city];
  const to = cityLocations[transaction.destination.city];
  if (!from || !to) return;

  const arc = {
    startLat: from.lat,
    startLng: from.lng,
    endLat: to.lat,
    endLng: to.lng,
    color: statusColors[transaction.status] || "#9aa6b8",
    label:
      `#${transaction.id} · ${transaction.origin.city} → ${transaction.destination.city} · ` +
      `$${transaction.amount.toFixed(2)} · ${statusNames[transaction.status]}`,
  };

  const ring = {
    lat: to.lat,
    lng: to.lng,
    rgb: statusRgbColors[transaction.status] || "154,166,184",
  };

  arcs.push(arc);
  rings.push(ring);
  globe.arcsData(arcs).ringsData(rings);

  setTimeout(() => {
    arcs = arcs.filter((item) => item !== arc);
    rings = rings.filter((item) => item !== ring);
    globe.arcsData(arcs).ringsData(rings);
  }, arcTime);
}

function setText(id, value) {
  const element = getElement(id);
  if (element) element.textContent = value;
}

function setWidth(id, value) {
  const element = getElement(id);
  if (element) element.style.width = value;
}

function formatMoney(number) {
  return number.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function updateStats() {
  const total = completedCount + suspiciousCount + failedCount;
  setText("statTotal", total.toLocaleString("en-US"));
  setText("statCompleted", completedCount);
  setText("statSuspicious", suspiciousCount);
  setText("statFailed", failedCount);

  const alertRate = total ? ((suspiciousCount / total) * 100).toFixed(1) : "0.0";
  setText("statFraudRate", `${alertRate}%`);

  setWidth("segCompleted", total ? `${(completedCount / total) * 100}%` : "0%");
  setWidth("segSuspicious", total ? `${(suspiciousCount / total) * 100}%` : "0%");
  setWidth("segFailed", total ? `${(failedCount / total) * 100}%` : "0%");
}

function transactionCardHtml(transaction) {
  const reason = transaction.rule_reason
    ? `<div class="reason">${transaction.rule_reason}</div>`
    : "";

  return `
    <div class="txn-card row-${transaction.status}" data-id="${transaction.id}">
      <div class="txn-head">
        <span class="txn-id">${transaction.id}</span>
        <span class="txn-parties">${transaction.sender} → ${transaction.receiver}</span>
        <span class="status-tag status-${transaction.status}">
          ${statusNames[transaction.status] || transaction.status}
        </span>
      </div>
      <div class="txn-meta">
        <span class="route">${transaction.origin.city} → ${transaction.destination.city}</span>
        <span class="amount">$${formatMoney(transaction.amount)}</span>
      </div>
      ${reason}
    </div>`;
}

function makeCard(transaction, clickAction) {
  const wrapper = document.createElement("div");
  wrapper.innerHTML = transactionCardHtml(transaction);
  const card = wrapper.firstElementChild;

  card.addEventListener("click", () => {
    if (clickAction) {
      clickAction();
    } else {
      openFromPanel(() => openTransaction(transaction));
    }
  });

  return card;
}

function addCard(container, transaction, maximumCards = 60) {
  container.prepend(makeCard(transaction));

  while (container.children.length > maximumCards) {
    container.removeChild(container.lastChild);
  }
}

function handleTransaction(transaction, drawLine = true) {
  if (transactionIds[transaction.id]) return;

  transactionIds[transaction.id] = transaction;
  addCard(feedList, transaction);

  if (transaction.status === "SUSPICIOUS") {
    addCard(suspiciousList, transaction);
    suspiciousCount++;
    suspiciousCountText.textContent = suspiciousCount;
  } else if (transaction.status === "FAILED") {
    addCard(failedList, transaction);
    failedCount++;
    failedCountText.textContent = failedCount;
  } else {
    completedCount++;
  }

  updateStats();
  if (drawLine) addArc(transaction);
}

const accountsView = getElement("accountsView");

async function showAccountsList() {
  const bots = await getData("/api/bots");

  accountsView.innerHTML = `
    <div class="account-list">
      ${bots.map((bot) => `
        <div class="account-row" data-bot="${bot.id}">
          <div class="acc-main">
            <span class="acc-name">${bot.display_name}</span>
            <span class="acc-sub">${bot.account_id} · ${bot.city}, ${bot.country}</span>
          </div>
          <div class="acc-right">
            <span class="acc-balance">$${formatMoney(bot.balance)}</span>
            <span class="profile-tag profile-${bot.profile}">
              ${bot.profile.replace("_", " ")}
            </span>
          </div>
        </div>`).join("")}
    </div>`;

  accountsView.querySelectorAll(".account-row").forEach((row) => {
    row.addEventListener("click", () => {
      openFromPanel(() => openAccount(row.dataset.bot));
    });
  });
}

const modal = getElement("modal");
const modalBody = getElement("modalBody");
const modalBack = getElement("modalBack");
let modalHistory = [];

function showModal(html) {
  modalBody.innerHTML = html;
  modalBody.scrollTop = 0;
  modal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  modalBack.classList.toggle("hidden", modalHistory.length === 0);
}

function closeModal() {
  modal.classList.add("hidden");
  document.body.classList.remove("modal-open");
  modalHistory = [];
}

function openFromPanel(showView) {
  modalHistory = [];
  showView();
}

function openNextView(previousView, nextView) {
  modalHistory.push(previousView);
  nextView();
}

modalBack.addEventListener("click", () => {
  const previousView = modalHistory.pop();
  if (previousView) previousView();
  else closeModal();
});

getElement("modalClose").addEventListener("click", closeModal);

modal.addEventListener("click", (event) => {
  if (event.target === modal) closeModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !modal.classList.contains("hidden")) {
    closeModal();
  }
});

function verdictHtml(flagged) {
  return `
    <span class="verdict ${flagged ? "verdict-flag" : "verdict-clear"}">
      ${flagged ? "Flagged" : "Clear"}
    </span>`;
}

function openTransaction(transaction) {
  showModal(`
    <div class="m-header">
      <div>
        <span class="m-eyebrow">Transaction</span>
        <h2 class="m-title mono">#${transaction.id}</h2>
      </div>
      <span class="status-tag status-${transaction.status}">
        ${statusNames[transaction.status] || transaction.status}
      </span>
    </div>

    <div class="m-hero">
      <span class="m-amount">$${formatMoney(transaction.amount)}</span>
      <span class="m-currency">${transaction.currency}</span>
    </div>

    <div class="m-route">
      <div class="m-place">
        <span class="m-city">${transaction.origin.city}</span>
        <span class="m-country">${transaction.origin.country}</span>
      </div>
      <div class="m-place m-place-end">
        <span class="m-city">${transaction.destination.city}</span>
        <span class="m-country">${transaction.destination.country}</span>
      </div>
    </div>

    <div class="m-rows">
      ${linkRow("Sender", transaction.sender, transaction.sender_account, transaction.sender_id)}
      ${linkRow("Receiver", transaction.receiver, transaction.receiver_account, transaction.receiver_id)}
      <div class="m-row">
        <span class="m-label">Time</span>
        <span class="m-value">${new Date(transaction.timestamp).toLocaleString()}</span>
      </div>
    </div>

    <div class="m-section">
      <span class="m-section-title">Detection results</span>
      <div class="m-verdicts">
        <div class="verdict-box">
          <span class="verdict-title">Traditional rules</span>
          ${verdictHtml(transaction.rule_flagged)}
          <p>${transaction.rule_reason || "No rule was triggered."}</p>
        </div>
        <div class="verdict-box">
          <span class="verdict-title">
            Machine learning${transaction.model_name ? ` · ${transaction.model_name}` : ""}
          </span>
          ${transaction.model_name
            ? verdictHtml(transaction.model_flagged)
            : '<span class="verdict verdict-na">Not scored</span>'}
          <p>${transaction.model_name
            ? `Fraud probability: <b>${transaction.model_probability}</b>.`
            : "Seeded history without a model result."}</p>
        </div>
      </div>
    </div>`);

  modalBody.querySelectorAll("[data-open-bot]").forEach((element) => {
    element.addEventListener("click", () => {
      openNextView(
        () => openTransaction(transaction),
        () => openAccount(element.dataset.openBot)
      );
    });
  });
}

function linkRow(label, name, account, botId) {
  return `
    <div class="m-row">
      <span class="m-label">${label}</span>
      <span class="m-value m-link" data-open-bot="${botId}">
        ${name} <span class="m-acc">${account}</span>
      </span>
    </div>`;
}

async function openAccount(botId) {
  showModal('<div class="loading">Loading account…</div>');
  const bot = await getData(`/api/bots/${botId}?limit=40`);

  if (bot.error) {
    showModal(`<div class="loading">${bot.error}</div>`);
    return;
  }

  showModal(`
    <div class="m-header">
      <div>
        <span class="m-eyebrow">Account holder</span>
        <h2 class="m-title">${bot.display_name}</h2>
        <p class="m-sub">
          <span class="mono">${bot.account_id}</span> · ${bot.city}, ${bot.country}
        </p>
      </div>
      <span class="profile-tag profile-${bot.profile}">
        ${bot.profile.replace("_", " ")}
      </span>
    </div>

    <div class="m-hero">
      <span class="m-amount">$${formatMoney(bot.balance)}</span>
      <span class="m-currency">available balance</span>
    </div>

    <div class="m-stats">
      ${statBlock(bot.stats.sent, "Sent")}
      ${statBlock(bot.stats.received, "Received")}
      ${statBlock(bot.stats.flagged, "Rule alerts")}
    </div>

    <div class="m-section">
      <span class="m-section-title">Transaction history</span>
      <div class="txn-list m-history" id="botTxnList"></div>
    </div>`);

  const list = modalBody.querySelector("#botTxnList");
  bot.transactions.forEach((transaction) => {
    list.appendChild(makeCard(
      transaction,
      () => openNextView(
        () => openAccount(botId),
        () => openTransaction(transaction)
      )
    ));
  });
}

function statBlock(value, label) {
  return `
    <div class="m-stat">
      <span class="m-stat-value">${value}</span>
      <span class="m-stat-label">${label}</span>
    </div>`;
}

document.querySelectorAll(".tab-btn").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((item) => item.classList.remove("active"));

    button.classList.add("active");
    getElement(`tab-${button.dataset.tab}`).classList.add("active");

    if (button.dataset.tab === "metrics") loadMetrics();
    if (button.dataset.tab === "accounts") showAccountsList();
  });
});

const statusPill = getElement("statusPill");

function showRunningState(running) {
  statusPill.innerHTML = `<i class="pulse"></i>${running ? "Running" : "Idle"}`;
  statusPill.className = `status-pill ${running ? "status-running" : "status-idle"}`;
}

function clearDashboard() {
  feedList.innerHTML = "";
  suspiciousList.innerHTML = "";
  failedList.innerHTML = "";
  suspiciousCount = 0;
  failedCount = 0;
  completedCount = 0;
  suspiciousCountText.textContent = "0";
  failedCountText.textContent = "0";
  transactionIds = {};
  updateStats();

  arcs = [];
  rings = [];
  globe.arcsData([]).ringsData([]);
}

getElement("runBtn").addEventListener("click", async () => {
  const speed = parseFloat(getElement("tpsInput").value) || 3;
  await sendPost(`/api/simulator/run?tps=${speed}`);
  showRunningState(true);
});

getElement("pauseBtn").addEventListener("click", async () => {
  await sendPost("/api/simulator/pause");
  statusPill.innerHTML = '<i class="pulse"></i>Paused';
  statusPill.className = "status-pill status-paused";
});

getElement("resetBtn").addEventListener("click", async () => {
  const result = await sendPost("/api/simulator/reset");
  clearDashboard();
  await loadRecentTransactions();
  showRunningState(result.running);
});

async function loadMetrics() {
  const box = getElement("metricsContent");
  const data = await getData("/api/model-metrics");

  if (data.error) {
    box.textContent = data.error;
    return;
  }

  const modelNames = {
    logistic_regression: "Logistic Regression",
    decision_tree: "Decision Tree",
    mlp_ann: "Neural Network (MLP)",
  };

  box.innerHTML = Object.entries(data).map(([modelName, metrics]) => {
    const [[trueNormal, falseFraud], [falseNormal, trueFraud]] =
      metrics.confusion_matrix;

    return `
      <h4>${modelNames[modelName] || modelName}</h4>
      <table>
        <tr><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th></tr>
        <tr>
          <td>${metrics.accuracy.toFixed(3)}</td>
          <td>${metrics.precision.toFixed(3)}</td>
          <td>${metrics.recall.toFixed(3)}</td>
          <td>${metrics.f1_score.toFixed(3)}</td>
        </tr>
      </table>
      <div class="cm">
        TN ${trueNormal} · FP ${falseFraud} · FN ${falseNormal} · TP ${trueFraud}
      </div>`;
  }).join("");
}

async function loadRecentTransactions() {
  const transactions = await getData("/api/transactions?limit=40");
  transactions.reverse().forEach((transaction) => {
    handleTransaction(transaction, false);
  });
}

function connectWebSocket() {
  const socket = new WebSocket(socketAddress);

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "transaction") {
      handleTransaction(data.transaction, true);
    }
  };

  socket.onclose = () => setTimeout(connectWebSocket, 2000);
  socket.onerror = () => socket.close();
}

function pollForNewTransactions() {
  getData("/api/transactions?limit=25")
    .then((transactions) => {
      transactions.reverse().forEach((transaction) => {
        handleTransaction(transaction, true);
      });
    })
    .catch(() => {});
}

(async function start() {
  await loadLocations();
  await loadRecentTransactions();
  connectWebSocket();
  setInterval(pollForNewTransactions, 2000);

  const status = await getData("/api/simulator/status");
  getElement("tpsInput").value = status.tps;
  showRunningState(status.running);
})();
