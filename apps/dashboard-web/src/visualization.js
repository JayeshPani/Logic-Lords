import { CHART_THRESHOLDS, RISK_COLOR_BY_LEVEL } from "./config.js";

function cssValue(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function renderMicroBars(container, values, color) {
  if (!container) {
    return;
  }
  container.innerHTML = "";

  const maxValue = Math.max(...values, 1);
  values.forEach((value) => {
    const bar = document.createElement("div");
    bar.className = "micro-bar";
    bar.style.height = `${Math.max(14, (value / maxValue) * 48)}px`;
    bar.style.background = `linear-gradient(180deg, ${color}, ${cssValue("--card-bg", "#0f172a")})`;
    container.appendChild(bar);
  });
}

export function renderHealthGauge(score, ringElement) {
  if (!ringElement) {
    return;
  }

  const radius = Number(ringElement.getAttribute("r") || 86);
  const circumference = 2 * Math.PI * radius;
  const normalized = Math.max(0, Math.min(1, Number(score) || 0));

  ringElement.style.strokeDasharray = `${circumference}`;
  const offset = circumference * (1 - normalized);

  ringElement.style.strokeDashoffset = `${offset}`;
  ringElement.style.stroke = "url(#healthGradient)";
}

export function renderRiskBars(container, components) {
  if (!container) {
    return;
  }

  container.innerHTML = "";

  const rows = [
    { key: "mechanical_stress", label: "Mechanical Stress" },
    { key: "thermal_stress", label: "Thermal Stress" },
    { key: "fatigue", label: "Fatigue" },
    { key: "environmental_exposure", label: "Environmental Exposure" },
  ];

  rows.forEach((row) => {
    const value = Number(components?.[row.key] ?? 0);
    const rowEl = document.createElement("div");
    rowEl.className = "risk-row";

    const label = document.createElement("div");
    label.className = "risk-row-label";
    label.textContent = row.label;

    const track = document.createElement("div");
    track.className = "risk-row-track";

    const fill = document.createElement("div");
    fill.className = "risk-row-fill";
    fill.style.width = `${Math.max(4, value * 100)}%`;

    let color = "#00ff88";
    if (value >= CHART_THRESHOLDS.critical) {
      color = "#f43f5e";
    } else if (value >= CHART_THRESHOLDS.warning) {
      color = "#fb923c";
    } else if (value >= CHART_THRESHOLDS.watch) {
      color = "#facc15";
    }

    fill.style.background = `linear-gradient(90deg, ${color} 0%, ${cssValue("--accent-blue", "#00d4ff")} 100%)`;
    track.appendChild(fill);

    const valueLabel = document.createElement("div");
    valueLabel.className = "risk-row-value mono";
    valueLabel.textContent = `${(value * 100).toFixed(0)}%`;

    rowEl.append(label, track, valueLabel);
    container.appendChild(rowEl);
  });
}

export function renderForecastChart(svg, points) {
  if (!svg) {
    return;
  }
  svg.innerHTML = "";

  const width = 780;
  const height = 240;
  const padding = { top: 20, right: 20, bottom: 28, left: 38 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const safePoints = points.length ? points : [{ hour: 0, probability: 0 }, { hour: 72, probability: 0 }];

  const maxX = Math.max(...safePoints.map((point) => point.hour), 72);
  const x = (hour) => padding.left + (hour / maxX) * chartWidth;
  const y = (probability) => padding.top + (1 - probability) * chartHeight;

  const thresholdY = y(CHART_THRESHOLDS.warning);
  const thresholdLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  thresholdLine.setAttribute("x1", String(padding.left));
  thresholdLine.setAttribute("x2", String(width - padding.right));
  thresholdLine.setAttribute("y1", String(thresholdY));
  thresholdLine.setAttribute("y2", String(thresholdY));
  thresholdLine.setAttribute("stroke", "#f43f5e");
  thresholdLine.setAttribute("stroke-dasharray", "6 6");
  thresholdLine.setAttribute("stroke-width", "2");
  thresholdLine.setAttribute("opacity", "0.9");
  svg.appendChild(thresholdLine);

  const pathData = safePoints
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(point.hour)} ${y(point.probability)}`)
    .join(" ");

  const areaPath = `${pathData} L ${x(safePoints[safePoints.length - 1].hour)} ${y(0)} L ${x(safePoints[0].hour)} ${y(0)} Z`;

  const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
  area.setAttribute("d", areaPath);
  area.setAttribute("fill", "rgba(0, 212, 255, 0.16)");
  svg.appendChild(area);

  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("d", pathData);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", "#00d4ff");
  line.setAttribute("stroke-width", "3");
  line.setAttribute("stroke-linecap", "round");
  line.setAttribute("stroke-linejoin", "round");
  svg.appendChild(line);

  safePoints.forEach((point) => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", String(x(point.hour)));
    circle.setAttribute("cy", String(y(point.probability)));
    circle.setAttribute("r", "4");
    circle.setAttribute("fill", "#00ff88");
    circle.setAttribute("opacity", "0.9");
    svg.appendChild(circle);
  });

  for (let step = 0; step <= 72; step += 24) {
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", String(x(step)));
    text.setAttribute("y", String(height - 8));
    text.setAttribute("fill", "#94a3b8");
    text.setAttribute("font-size", "11");
    text.setAttribute("text-anchor", "middle");
    text.textContent = `${step}h`;
    svg.appendChild(text);
  }
}

function severityColor(level) {
  if (level === "Critical") {
    return "#f43f5e";
  }
  if (level === "Warning") {
    return "#fb923c";
  }
  if (level === "Watch") {
    return "#facc15";
  }
  return RISK_COLOR_BY_LEVEL.Low;
}

export function renderRiskMap(container, nodes) {
  if (!container) {
    return;
  }

  container.innerHTML = "";
  if (!nodes.length) {
    container.innerHTML = "<p class='empty-map'>No asset nodes available.</p>";
    return;
  }

  const lats = nodes.map((node) => node.lat);
  const lons = nodes.map((node) => node.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  nodes.forEach((node) => {
    const nodeEl = document.createElement("button");
    nodeEl.type = "button";
    nodeEl.className = "map-node pulse-indicator";

    const xRatio = (node.lon - minLon) / Math.max(0.0001, maxLon - minLon);
    const yRatio = (node.lat - minLat) / Math.max(0.0001, maxLat - minLat);

    nodeEl.style.left = `${8 + xRatio * 84}%`;
    nodeEl.style.top = `${90 - yRatio * 76}%`;
    nodeEl.style.backgroundColor = severityColor(node.severity);
    nodeEl.style.width = `${16 + node.probability * 26}px`;
    nodeEl.style.height = `${16 + node.probability * 26}px`;

    nodeEl.setAttribute(
      "title",
      `${node.name} | ${node.severity} | ${(node.probability * 100).toFixed(0)}% failure risk`,
    );

    const label = document.createElement("span");
    label.className = "map-node-label";
    label.textContent = node.zone.toUpperCase();

    nodeEl.appendChild(label);
    container.appendChild(nodeEl);
  });
}
