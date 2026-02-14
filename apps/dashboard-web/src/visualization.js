import { CHART_THRESHOLDS, MAP_CONFIG, RISK_COLOR_BY_LEVEL, SEVERITY_COLOR } from "./config.js";

const lstmAnimationRegistry = new WeakMap();

function cssValue(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function severityColorByValue(value) {
  if (value >= CHART_THRESHOLDS.critical) {
    return SEVERITY_COLOR.critical;
  }
  if (value >= CHART_THRESHOLDS.warning) {
    return SEVERITY_COLOR.warning;
  }
  if (value >= CHART_THRESHOLDS.watch) {
    return SEVERITY_COLOR.watch;
  }
  return SEVERITY_COLOR.healthy;
}

export function renderMicroBars(container, values, color) {
  if (!container) {
    return;
  }
  container.innerHTML = "";

  const source = Array.isArray(values) && values.length > 0 ? values : [0, 0, 0, 0, 0, 0, 0, 0];
  const maxValue = Math.max(...source, 1);

  source.forEach((value) => {
    const bar = document.createElement("div");
    bar.className = "micro-bar";
    bar.style.height = `${Math.max(12, (Number(value) / maxValue) * 42)}px`;
    bar.style.background = `linear-gradient(180deg, ${color}, ${cssValue("--surface-3", "#0b1222")})`;
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
  ringElement.style.strokeDashoffset = `${circumference * (1 - normalized)}`;
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
  ]
    .map((row) => ({ ...row, value: Math.max(0, Math.min(1, Number(components?.[row.key] ?? 0))) }))
    .sort((left, right) => right.value - left.value);

  rows.forEach((row) => {
    const rowEl = document.createElement("div");
    rowEl.className = "risk-row";

    const label = document.createElement("div");
    label.className = "risk-row-label";
    label.textContent = row.label;

    const track = document.createElement("div");
    track.className = "risk-row-track";

    const fill = document.createElement("div");
    fill.className = "risk-row-fill";
    fill.style.width = `${Math.max(4, row.value * 100)}%`;
    fill.style.background = `linear-gradient(90deg, ${severityColorByValue(row.value)} 0%, ${cssValue("--accent-blue", "#00d4ff")} 100%)`;

    const value = document.createElement("div");
    value.className = "risk-row-value mono";
    value.textContent = `${(row.value * 100).toFixed(0)}%`;

    track.appendChild(fill);
    rowEl.append(label, track, value);
    container.appendChild(rowEl);
  });
}

export function renderForecastChart(svg, points) {
  if (!svg) {
    return;
  }
  svg.innerHTML = "";

  const width = 760;
  const height = 240;
  const padding = { top: 16, right: 18, bottom: 30, left: 42 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const safePoints = Array.isArray(points) && points.length > 1 ? points : [{ hour: 0, probability: 0 }, { hour: 72, probability: 0 }];
  const sorted = [...safePoints].sort((left, right) => left.hour - right.hour);

  const maxX = Math.max(...sorted.map((point) => Number(point.hour)), 72);
  const x = (hour) => padding.left + (Number(hour) / maxX) * chartWidth;
  const y = (probability) => padding.top + (1 - Math.max(0, Math.min(1, Number(probability)))) * chartHeight;

  const bands = [
    { from: CHART_THRESHOLDS.critical, to: 1, color: "rgba(244, 63, 94, 0.16)", label: "Critical" },
    { from: CHART_THRESHOLDS.warning, to: CHART_THRESHOLDS.critical, color: "rgba(251, 146, 60, 0.15)", label: "Warning" },
    { from: CHART_THRESHOLDS.watch, to: CHART_THRESHOLDS.warning, color: "rgba(250, 204, 21, 0.12)", label: "Watch" },
  ];

  bands.forEach((band) => {
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", String(padding.left));
    rect.setAttribute("y", String(y(band.to)));
    rect.setAttribute("width", String(chartWidth));
    rect.setAttribute("height", String(Math.max(0, y(band.from) - y(band.to))));
    rect.setAttribute("fill", band.color);
    svg.appendChild(rect);
  });

  [0.2, 0.4, 0.6, 0.8, 1].forEach((tick) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(padding.left));
    line.setAttribute("x2", String(width - padding.right));
    line.setAttribute("y1", String(y(tick)));
    line.setAttribute("y2", String(y(tick)));
    line.setAttribute("stroke", "rgba(148, 163, 184, 0.24)");
    line.setAttribute("stroke-width", "1");
    svg.appendChild(line);
  });

  const pathData = sorted
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(point.hour)} ${y(point.probability)}`)
    .join(" ");

  const areaPath = `${pathData} L ${x(sorted[sorted.length - 1].hour)} ${y(0)} L ${x(sorted[0].hour)} ${y(0)} Z`;

  const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
  area.setAttribute("d", areaPath);
  area.setAttribute("fill", "rgba(0, 212, 255, 0.16)");
  svg.appendChild(area);

  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("d", pathData);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", cssValue("--accent-blue", "#00d4ff"));
  line.setAttribute("stroke-width", "3");
  line.setAttribute("stroke-linecap", "round");
  line.setAttribute("stroke-linejoin", "round");
  svg.appendChild(line);

  const currentPoint = sorted[0];
  const peakPoint = sorted.reduce((peak, point) => (point.probability > peak.probability ? point : peak), sorted[0]);

  const markers = [
    { point: currentPoint, color: cssValue("--accent-green", "#00ff88"), radius: 4.5, label: "Now" },
    { point: peakPoint, color: cssValue("--risk-critical", "#f43f5e"), radius: 5.5, label: `Peak ${(peakPoint.probability * 100).toFixed(0)}%` },
  ];

  markers.forEach((marker) => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", String(x(marker.point.hour)));
    circle.setAttribute("cy", String(y(marker.point.probability)));
    circle.setAttribute("r", String(marker.radius));
    circle.setAttribute("fill", marker.color);
    svg.appendChild(circle);

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", String(x(marker.point.hour) + 8));
    text.setAttribute("y", String(y(marker.point.probability) - 8));
    text.setAttribute("fill", marker.color);
    text.setAttribute("font-size", "11");
    text.setAttribute("font-weight", "700");
    text.textContent = marker.label;
    svg.appendChild(text);
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

  // Hover interaction: show nearest point values at cursor without changing chart data.
  const hoverGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
  hoverGroup.setAttribute("visibility", "hidden");

  const hoverLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  hoverLine.setAttribute("y1", String(padding.top));
  hoverLine.setAttribute("y2", String(height - padding.bottom));
  hoverLine.setAttribute("stroke", "rgba(148, 163, 184, 0.55)");
  hoverLine.setAttribute("stroke-width", "1.5");
  hoverLine.setAttribute("stroke-dasharray", "4 4");

  const hoverPoint = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  hoverPoint.setAttribute("r", "5");
  hoverPoint.setAttribute("fill", cssValue("--accent-blue", "#00d4ff"));
  hoverPoint.setAttribute("stroke", "#0b1222");
  hoverPoint.setAttribute("stroke-width", "2");

  const tooltipGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const tooltipBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  tooltipBg.setAttribute("rx", "7");
  tooltipBg.setAttribute("ry", "7");
  tooltipBg.setAttribute("fill", "rgba(2, 6, 23, 0.92)");
  tooltipBg.setAttribute("stroke", "rgba(0, 212, 255, 0.45)");
  tooltipBg.setAttribute("stroke-width", "1");

  const tooltipText = document.createElementNS("http://www.w3.org/2000/svg", "text");
  tooltipText.setAttribute("fill", "#e2e8f0");
  tooltipText.setAttribute("font-size", "11");
  tooltipText.setAttribute("font-weight", "700");
  tooltipText.setAttribute("dominant-baseline", "middle");

  tooltipGroup.appendChild(tooltipBg);
  tooltipGroup.appendChild(tooltipText);
  hoverGroup.appendChild(hoverLine);
  hoverGroup.appendChild(hoverPoint);
  hoverGroup.appendChild(tooltipGroup);
  svg.appendChild(hoverGroup);

  const hideHover = () => {
    hoverGroup.setAttribute("visibility", "hidden");
  };

  const updateHover = (clientX) => {
    const rect = svg.getBoundingClientRect();
    if (!rect.width) {
      hideHover();
      return;
    }

    const localX = ((clientX - rect.left) / rect.width) * width;
    const clampedX = Math.max(padding.left, Math.min(width - padding.right, localX));
    const hourValue = ((clampedX - padding.left) / chartWidth) * maxX;
    const clampedHour = Math.max(0, Math.min(maxX, hourValue));

    let leftPoint = sorted[0];
    let rightPoint = sorted[sorted.length - 1];
    for (let index = 0; index < sorted.length - 1; index += 1) {
      const current = sorted[index];
      const next = sorted[index + 1];
      if (clampedHour >= current.hour && clampedHour <= next.hour) {
        leftPoint = current;
        rightPoint = next;
        break;
      }
    }

    const span = Math.max(1e-6, Number(rightPoint.hour) - Number(leftPoint.hour));
    const ratio = Math.max(0, Math.min(1, (clampedHour - Number(leftPoint.hour)) / span));
    const interpolatedProbability =
      Number(leftPoint.probability) + (Number(rightPoint.probability) - Number(leftPoint.probability)) * ratio;

    const px = clampedX;
    const py = y(interpolatedProbability);

    hoverLine.setAttribute("x1", String(px));
    hoverLine.setAttribute("x2", String(px));
    hoverPoint.setAttribute("cx", String(px));
    hoverPoint.setAttribute("cy", String(py));

    const label = `${clampedHour.toFixed(1)}h  |  ${(interpolatedProbability * 100).toFixed(1)}%`;
    tooltipText.textContent = label;
    const textWidth = Math.max(68, tooltipText.getComputedTextLength() + 12);
    const textHeight = 24;

    const tooltipX = Math.min(
      width - padding.right - textWidth,
      Math.max(padding.left, px + 10),
    );
    const tooltipY = Math.max(padding.top, py - 30);

    tooltipBg.setAttribute("x", String(tooltipX));
    tooltipBg.setAttribute("y", String(tooltipY));
    tooltipBg.setAttribute("width", String(textWidth));
    tooltipBg.setAttribute("height", String(textHeight));

    tooltipText.setAttribute("x", String(tooltipX + 6));
    tooltipText.setAttribute("y", String(tooltipY + textHeight / 2));

    hoverGroup.setAttribute("visibility", "visible");
  };

  svg.style.cursor = "crosshair";
  svg.onmousemove = (event) => updateHover(event.clientX);
  svg.onmouseleave = hideHover;
}

let leafletLoaderPromise = null;
const leafletRegistry = new WeakMap();

function createMapError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function normalizeSeverityKey(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical" || normalized === "warning" || normalized === "watch" || normalized === "healthy") {
    return normalized;
  }
  if (normalized === "high" || normalized === "severe") {
    return "critical";
  }
  if (normalized === "moderate") {
    return "watch";
  }
  return "healthy";
}

function severityColor(level) {
  const severityKey = normalizeSeverityKey(level);
  return SEVERITY_COLOR[severityKey] || RISK_COLOR_BY_LEVEL.Low;
}

function markerRadius(probability) {
  const ratio = Math.max(0, Math.min(1, Number(probability ?? 0)));
  const span = MAP_CONFIG.markerMaxRadius - MAP_CONFIG.markerMinRadius;
  return MAP_CONFIG.markerMinRadius + span * ratio;
}

function isValidCoordinate(lat, lon) {
  const safeLat = Number(lat);
  const safeLon = Number(lon);
  return Number.isFinite(safeLat) && Number.isFinite(safeLon) && Math.abs(safeLat) <= 90 && Math.abs(safeLon) <= 180;
}

function setMapStatus(element, variant, text) {
  if (!element) {
    return;
  }

  element.className = `map-status map-status-${variant}`;
  element.textContent = text;
}

function clearLeafletInstance(container) {
  const existing = leafletRegistry.get(container);
  if (!existing) {
    return;
  }

  try {
    existing.map.remove();
  } catch (_error) {
    // Ignore teardown errors while switching to fallback renderer.
  }

  leafletRegistry.delete(container);
}

function ensureLeafletLoaded() {
  if (typeof window === "undefined") {
    return Promise.reject(createMapError("NO_WINDOW", "Leaflet requires browser environment."));
  }

  if (window.L?.map) {
    return Promise.resolve(window.L);
  }

  if (leafletLoaderPromise) {
    return leafletLoaderPromise;
  }

  leafletLoaderPromise = new Promise((resolve, reject) => {
    const cssId = "infraguard-leaflet-css";
    const scriptId = "infraguard-leaflet-js";

    if (!document.getElementById(cssId)) {
      const link = document.createElement("link");
      link.id = cssId;
      link.rel = "stylesheet";
      link.href = MAP_CONFIG.leafletCssUrl;
      document.head.appendChild(link);
    }

    const existingScript = document.getElementById(scriptId);
    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(window.L), { once: true });
      existingScript.addEventListener(
        "error",
        () => reject(createMapError("LEAFLET_SCRIPT_ERROR", "Leaflet script failed to load.")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = MAP_CONFIG.leafletJsUrl;
    script.async = true;
    script.defer = true;

    const timeoutHandle = window.setTimeout(() => {
      reject(createMapError("LEAFLET_TIMEOUT", "Leaflet loading timed out."));
    }, MAP_CONFIG.leafletLoadTimeoutMs);

    script.onload = () => {
      window.clearTimeout(timeoutHandle);
      if (window.L?.map) {
        resolve(window.L);
        return;
      }
      reject(createMapError("LEAFLET_MISSING_GLOBAL", "Leaflet loaded but global L was not found."));
    };

    script.onerror = () => {
      window.clearTimeout(timeoutHandle);
      reject(createMapError("LEAFLET_SCRIPT_ERROR", "Leaflet script failed to load."));
    };

    document.head.appendChild(script);
  }).catch((error) => {
    leafletLoaderPromise = null;
    throw error;
  });

  return leafletLoaderPromise;
}

function renderRiskMapFallback(container, nodes, options = {}) {
  if (!container) {
    return;
  }

  container.classList.remove("risk-map-leaflet");
  container.innerHTML = "";
  if (!Array.isArray(nodes) || !nodes.length) {
    container.innerHTML = "<p class='empty-map'>No asset nodes available.</p>";
    return;
  }

  const validNodes = nodes.filter((node) => isValidCoordinate(node.lat, node.lon));
  if (!validNodes.length) {
    container.innerHTML = "<p class='empty-map'>No valid coordinates available.</p>";
    return;
  }

  const lats = validNodes.map((node) => Number(node.lat));
  const lons = validNodes.map((node) => Number(node.lon));
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  validNodes.forEach((node) => {
    const nodeEl = document.createElement("button");
    nodeEl.type = "button";
    const isSelected = options.selectedAssetId
      ? node.assetId === options.selectedAssetId
      : Boolean(node.selected);
    nodeEl.className = `map-node ${isSelected ? "map-node-selected" : ""}`;

    const xRatio = (node.lon - minLon) / Math.max(0.0001, maxLon - minLon);
    const yRatio = (node.lat - minLat) / Math.max(0.0001, maxLat - minLat);

    nodeEl.style.left = `${8 + xRatio * 84}%`;
    nodeEl.style.top = `${90 - yRatio * 76}%`;
    nodeEl.style.backgroundColor = severityColor(node.severityKey || node.severity);
    nodeEl.style.width = `${markerRadius(node.probability) * 2}px`;
    nodeEl.style.height = `${markerRadius(node.probability) * 2}px`;

    nodeEl.setAttribute("title", `${node.name} | ${node.severity} | ${(node.probability * 100).toFixed(0)}% failure risk`);

    const label = document.createElement("span");
    label.className = "map-node-label";
    label.textContent = node.zone.toUpperCase();

    nodeEl.addEventListener("click", () => {
      if (typeof options.onSelectAsset === "function") {
        options.onSelectAsset(node.assetId);
      }
    });

    nodeEl.appendChild(label);
    container.appendChild(nodeEl);
  });
}

function getLeafletState(container, L) {
  const existing = leafletRegistry.get(container);
  if (existing) {
    return existing;
  }

  container.innerHTML = "";
  container.classList.add("risk-map-leaflet");
  const map = L.map(container, {
    zoomControl: true,
    attributionControl: true,
    minZoom: MAP_CONFIG.minZoom,
    maxZoom: MAP_CONFIG.maxZoom,
  });

  const tileLayer = L.tileLayer(MAP_CONFIG.osmTileUrl, {
    attribution: MAP_CONFIG.osmAttribution,
    minZoom: MAP_CONFIG.minZoom,
    maxZoom: MAP_CONFIG.maxZoom,
  }).addTo(map);

  const markerLayer = L.layerGroup().addTo(map);
  const state = {
    map,
    tileLayer,
    markerLayer,
    fitted: false,
    onSelectAsset: null,
    lastNodes: [],
    lastOptions: {},
    tileErrored: false,
  };

  tileLayer.on("tileerror", () => {
    if (state.tileErrored) {
      return;
    }
    state.tileErrored = true;
    const latestNodes = Array.isArray(state.lastNodes) ? state.lastNodes : [];
    const latestOptions = state.lastOptions || {};
    clearLeafletInstance(container);
    setMapStatus(latestOptions.statusElement, "warn", "Basemap unavailable, fallback view active.");
    renderRiskMapFallback(container, latestNodes, latestOptions);
  });

  leafletRegistry.set(container, state);
  return state;
}

function renderRiskMapLeaflet(container, nodes, options = {}) {
  const L = window.L;
  if (!L?.map) {
    throw createMapError("LEAFLET_UNAVAILABLE", "Leaflet runtime is unavailable.");
  }

  const state = getLeafletState(container, L);
  state.onSelectAsset = typeof options.onSelectAsset === "function" ? options.onSelectAsset : null;
  state.lastNodes = nodes;
  state.lastOptions = options;
  state.markerLayer.clearLayers();
  state.map.invalidateSize();

  const validNodes = nodes.filter((node) => isValidCoordinate(node.lat, node.lon));
  if (!validNodes.length) {
    state.map.setView(MAP_CONFIG.defaultCenter, MAP_CONFIG.defaultZoom);
    setMapStatus(options.statusElement, "warn", "No valid coordinates available for map rendering.");
    return;
  }

  const latLngs = [];

  validNodes.forEach((node) => {
    const latLng = [Number(node.lat), Number(node.lon)];
    latLngs.push(latLng);

    const isSelected = options.selectedAssetId
      ? node.assetId === options.selectedAssetId
      : Boolean(node.selected);
    const color = severityColor(node.severityKey || node.severity);

    const marker = L.circleMarker(latLng, {
      radius: markerRadius(node.probability),
      color,
      fillColor: color,
      fillOpacity: isSelected ? 0.95 : 0.72,
      weight: isSelected ? 3 : 1.5,
      opacity: 1,
      className: isSelected ? "leaflet-risk-marker-selected" : "leaflet-risk-marker",
    });

    marker.bindTooltip(
      `${node.name}<br>${node.zone.toUpperCase()} | ${node.severity}<br>72h Risk ${(Number(node.probability) * 100).toFixed(0)}%`,
      { direction: "top", sticky: true, opacity: 0.94 },
    );

    marker.on("click", () => {
      if (typeof state.onSelectAsset === "function") {
        state.onSelectAsset(node.assetId);
      }
    });

    marker.addTo(state.markerLayer);
  });

  if (!state.fitted) {
    if (latLngs.length === 1) {
      state.map.setView(latLngs[0], MAP_CONFIG.defaultZoom);
    } else {
      state.map.fitBounds(L.latLngBounds(latLngs), {
        padding: [24, 24],
        maxZoom: MAP_CONFIG.defaultZoom + 2,
      });
    }
    state.fitted = true;
  }

  if (state.tileErrored) {
    clearLeafletInstance(container);
    setMapStatus(options.statusElement, "warn", "Basemap unavailable, fallback view active.");
    renderRiskMapFallback(container, nodes, options);
    return;
  }

  setMapStatus(options.statusElement, "ok", "Live basemap active (OpenStreetMap).");
}

export function renderRiskMap(container, nodes, options = {}) {
  if (!container) {
    return;
  }

  if (!options.active) {
    setMapStatus(options.statusElement, "quiet", "Open the City Map tab to load live basemap tiles.");
    return;
  }

  const safeNodes = Array.isArray(nodes) ? nodes : [];
  if (!safeNodes.length) {
    clearLeafletInstance(container);
    renderRiskMapFallback(container, [], options);
    setMapStatus(options.statusElement, "warn", "No asset nodes available.");
    return;
  }

  setMapStatus(options.statusElement, "quiet", "Loading basemap...");

  const renderVersion = Number(container.dataset.mapRenderVersion || "0") + 1;
  container.dataset.mapRenderVersion = String(renderVersion);

  ensureLeafletLoaded()
    .then(() => {
      if (Number(container.dataset.mapRenderVersion || "0") !== renderVersion) {
        return;
      }
      renderRiskMapLeaflet(container, safeNodes, options);
    })
    .catch(() => {
      if (Number(container.dataset.mapRenderVersion || "0") !== renderVersion) {
        return;
      }
      clearLeafletInstance(container);
      setMapStatus(options.statusElement, "warn", "Map library unavailable, using fallback city renderer.");
      renderRiskMapFallback(container, safeNodes, options);
    });
}

export function renderMapLegend(container) {
  if (!container) {
    return;
  }

  container.innerHTML = "";
  const levels = [
    { label: "Low", color: RISK_COLOR_BY_LEVEL.Low, size: "Small" },
    { label: "Watch", color: "#facc15", size: "Medium" },
    { label: "Warning", color: "#fb923c", size: "Large" },
    { label: "Critical", color: RISK_COLOR_BY_LEVEL.Critical, size: "Largest" },
  ];

  levels.forEach((level) => {
    const row = document.createElement("div");
    row.className = "map-legend-row";

    const dot = document.createElement("span");
    dot.className = "map-legend-dot";
    dot.style.backgroundColor = level.color;

    const label = document.createElement("span");
    label.textContent = `${level.label} (${level.size})`;

    row.append(dot, label);
    container.appendChild(row);
  });
}

export function renderLstmOverviewChart(
  svg,
  lstmModel,
  nodesModel = null,
  selection = { selectedNodeId: null, selectedAssetId: null },
) {
  if (!svg) {
    return;
  }
  const existingAnimation = lstmAnimationRegistry.get(svg);
  if (existingAnimation?.frameId) {
    cancelAnimationFrame(existingAnimation.frameId);
  }
  lstmAnimationRegistry.delete(svg);
  svg.innerHTML = "";

  const width = 980;
  const height = 260;
  const padding = { top: 18, right: 24, bottom: 34, left: 44 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const clamp01 = (value) => Math.max(0, Math.min(1, Number(value ?? 0)));

  const pickFirebaseNode = () => {
    const nodes = Array.isArray(nodesModel?.nodes) ? nodesModel.nodes : [];
    if (!nodes.length || !nodesModel?.connected) {
      return null;
    }
    const selectedNodeId = selection?.selectedNodeId || null;
    const selectedAssetId = selection?.selectedAssetId || null;
    if (selectedNodeId) {
      const byNodeId = nodes.find((node) => node?.nodeId === selectedNodeId);
      if (byNodeId) {
        return byNodeId;
      }
    }
    if (selectedAssetId) {
      const byAsset = nodes.find((node) => node?.assetId === selectedAssetId);
      if (byAsset) {
        return byAsset;
      }
    }
    const withTelemetry = nodes.filter((node) => {
      const telemetry = node?.telemetry || {};
      return ["strain", "vibration", "temperature"].every((key) => Number.isFinite(Number(telemetry?.[key]?.value)));
    });
    return withTelemetry[0] || nodes[0] || null;
  };

  const firebaseNode = pickFirebaseNode();
  const firebaseHistorySeries = (() => {
    if (!firebaseNode) {
      return [];
    }
    const strainSamples = Array.isArray(firebaseNode?.telemetry?.strain?.samples)
      ? firebaseNode.telemetry.strain.samples
      : [firebaseNode?.telemetry?.strain?.value];
    const vibrationSamples = Array.isArray(firebaseNode?.telemetry?.vibration?.samples)
      ? firebaseNode.telemetry.vibration.samples
      : [firebaseNode?.telemetry?.vibration?.value];
    const temperatureSamples = Array.isArray(firebaseNode?.telemetry?.temperature?.samples)
      ? firebaseNode.telemetry.temperature.samples
      : [firebaseNode?.telemetry?.temperature?.value];

    const total = Math.max(strainSamples.length, vibrationSamples.length, temperatureSamples.length);
    if (total < 2) {
      return [];
    }
    const normalizeSample = (samples, index) => Number(samples[Math.min(samples.length - 1, index)] ?? 0);
    return Array.from({ length: total }, (_, index) => {
      const strain = normalizeSample(strainSamples, index);
      const vibration = normalizeSample(vibrationSamples, index);
      const temperature = normalizeSample(temperatureSamples, index);
      const stress = 0.45 * strain + 0.35 * vibration + 0.2 * ((temperature - 20) / 20);
      return {
        x: -48 + (48 * index) / Math.max(1, total - 1),
        y: clamp01(stress / 12),
      };
    });
  })();

  const firebaseForecastSeries = (() => {
    if (!firebaseNode || !firebaseHistorySeries.length) {
      return [];
    }
    const base = clamp01(firebaseNode.failureProbability72h ?? firebaseHistorySeries[firebaseHistorySeries.length - 1].y);
    return Array.from({ length: 13 }, (_, idx) => {
      const hour = idx * 6;
      const progress = hour / 72;
      const wave = 0.06 * Math.sin((2 * Math.PI * progress) + 0.8);
      const trend = 0.11 * progress;
      return { x: hour, y: clamp01(base - 0.06 + wave + trend) };
    });
  })();

  const history = Array.isArray(lstmModel.history) ? lstmModel.history : [];
  const forecast = Array.isArray(lstmModel.forecastPoints) ? lstmModel.forecastPoints : [];

  const recentHistory = history.slice(-192);
  const pythonHistorySeries = recentHistory.map((point, index) => {
    const stress = 0.45 * point.strain + 0.35 * point.vibration + 0.2 * ((point.temperature - 20) / 20);
    return {
      x: -48 + (48 * index) / Math.max(1, recentHistory.length - 1),
      y: clamp01(stress / 12),
    };
  });
  const pythonForecastSeries = forecast.map((point) => ({
    x: point.hour,
    y: clamp01(Number(point.probability)),
  }));

  const historySeries = firebaseHistorySeries.length ? firebaseHistorySeries : pythonHistorySeries;
  const forecastSeries = firebaseForecastSeries.length ? firebaseForecastSeries : pythonForecastSeries;

  if (!historySeries.length && !forecastSeries.length) {
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", String(width / 2));
    text.setAttribute("y", String(height / 2));
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#94a3b8");
    text.textContent = "LSTM/Firebase data unavailable";
    svg.appendChild(text);
    return;
  }

  const x = (value) => padding.left + ((value + 48) / 120) * chartWidth;
  const y = (value) => padding.top + (1 - value) * chartHeight;

  [0.2, 0.4, 0.6, 0.8, 1].forEach((tick) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(padding.left));
    line.setAttribute("x2", String(width - padding.right));
    line.setAttribute("y1", String(y(tick)));
    line.setAttribute("y2", String(y(tick)));
    line.setAttribute("stroke", "rgba(148,163,184,0.2)");
    line.setAttribute("stroke-width", "1");
    svg.appendChild(line);
  });

  const divider = document.createElementNS("http://www.w3.org/2000/svg", "line");
  divider.setAttribute("x1", String(x(0)));
  divider.setAttribute("x2", String(x(0)));
  divider.setAttribute("y1", String(padding.top));
  divider.setAttribute("y2", String(height - padding.bottom));
  divider.setAttribute("stroke", "rgba(250,204,21,0.55)");
  divider.setAttribute("stroke-width", "1.5");
  divider.setAttribute("stroke-dasharray", "5 4");
  svg.appendChild(divider);

  const drawPath = (series, color, widthPx, dashArray = null) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    if (series.length) {
      const d = series
        .map((point, idx) => `${idx === 0 ? "M" : "L"}${x(point.x)} ${y(point.y)}`)
        .join(" ");
      path.setAttribute("d", d);
    }
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", String(widthPx));
    path.setAttribute("stroke-linecap", "round");
    if (dashArray) {
      path.setAttribute("stroke-dasharray", dashArray);
    }
    svg.appendChild(path);
    return path;
  };

  const historyPath = drawPath(historySeries, "rgba(34,211,238,0.95)", 2.6);
  const forecastPath = drawPath(forecastSeries, "rgba(244,63,94,0.9)", 2.8, "7 5");

  const nowCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  nowCircle.setAttribute("r", "5");
  nowCircle.setAttribute("fill", "#22d3ee");
  nowCircle.setAttribute("stroke", "#0b1222");
  nowCircle.setAttribute("stroke-width", "2");
  svg.appendChild(nowCircle);

  const nowValueText = document.createElementNS("http://www.w3.org/2000/svg", "text");
  nowValueText.setAttribute("fill", "#22d3ee");
  nowValueText.setAttribute("font-size", "11");
  nowValueText.setAttribute("font-weight", "700");
  svg.appendChild(nowValueText);

  const labels = [
    { value: -48, text: "-48h" },
    { value: -24, text: "-24h" },
    { value: 0, text: "Now" },
    { value: 24, text: "+24h" },
    { value: 48, text: "+48h" },
    { value: 72, text: "+72h" },
  ];
  labels.forEach((label) => {
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", String(x(label.value)));
    text.setAttribute("y", String(height - 8));
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#94a3b8");
    text.setAttribute("font-size", "11");
    text.textContent = label.text;
    svg.appendChild(text);
  });

  const buildPathData = (series) => series
    .map((point, idx) => `${idx === 0 ? "M" : "L"}${x(point.x)} ${y(point.y)}`)
    .join(" ");

  const toAnimatedSeries = (series, phase, magnitude) => series.map((point, index) => ({
    x: point.x,
    y: clamp01(point.y + (magnitude * Math.sin(phase + (index * 0.16) + (point.x * 0.025)))),
  }));
  const interpolateSeries = (series, xValue) => {
    if (!series.length) {
      return null;
    }
    if (xValue <= series[0].x) {
      return series[0].y;
    }
    if (xValue >= series[series.length - 1].x) {
      return series[series.length - 1].y;
    }
    for (let i = 0; i < series.length - 1; i += 1) {
      const left = series[i];
      const right = series[i + 1];
      if (xValue >= left.x && xValue <= right.x) {
        const span = Math.max(1e-6, right.x - left.x);
        const ratio = (xValue - left.x) / span;
        return left.y + ((right.y - left.y) * ratio);
      }
    }
    return series[series.length - 1].y;
  };
  const xToDomain = (pixelX) => -48 + (((pixelX - padding.left) / chartWidth) * 120);

  const hoverGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
  hoverGroup.setAttribute("visibility", "hidden");
  const hoverLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  hoverLine.setAttribute("y1", String(padding.top));
  hoverLine.setAttribute("y2", String(height - padding.bottom));
  hoverLine.setAttribute("stroke", "rgba(148,163,184,0.6)");
  hoverLine.setAttribute("stroke-width", "1.5");
  hoverLine.setAttribute("stroke-dasharray", "4 4");
  const hoverPoint = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  hoverPoint.setAttribute("r", "4.5");
  hoverPoint.setAttribute("fill", "#22d3ee");
  hoverPoint.setAttribute("stroke", "#0b1222");
  hoverPoint.setAttribute("stroke-width", "2");
  const hoverBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  hoverBg.setAttribute("rx", "6");
  hoverBg.setAttribute("ry", "6");
  hoverBg.setAttribute("fill", "rgba(2,6,23,0.93)");
  hoverBg.setAttribute("stroke", "rgba(34,211,238,0.45)");
  hoverBg.setAttribute("stroke-width", "1");
  const hoverText = document.createElementNS("http://www.w3.org/2000/svg", "text");
  hoverText.setAttribute("fill", "#e2e8f0");
  hoverText.setAttribute("font-size", "11");
  hoverText.setAttribute("font-weight", "700");
  hoverText.setAttribute("dominant-baseline", "middle");
  hoverGroup.appendChild(hoverLine);
  hoverGroup.appendChild(hoverPoint);
  hoverGroup.appendChild(hoverBg);
  hoverGroup.appendChild(hoverText);
  svg.appendChild(hoverGroup);

  let animatedHistory = historySeries;
  let animatedForecast = forecastSeries;
  let hoverClientX = null;
  let frameId = null;

  const updateHover = () => {
    if (hoverClientX == null) {
      hoverGroup.setAttribute("visibility", "hidden");
      return;
    }
    const rect = svg.getBoundingClientRect();
    if (!rect.width) {
      hoverGroup.setAttribute("visibility", "hidden");
      return;
    }

    const localX = ((hoverClientX - rect.left) / rect.width) * width;
    const clampedX = Math.max(padding.left, Math.min(width - padding.right, localX));
    const domainX = xToDomain(clampedX);
    const activeSeries = domainX <= 0
      ? animatedHistory
      : [{ x: 0, y: animatedHistory[animatedHistory.length - 1]?.y ?? 0 }, ...animatedForecast];
    const value = interpolateSeries(activeSeries, domainX);
    if (value == null) {
      hoverGroup.setAttribute("visibility", "hidden");
      return;
    }

    const valueY = y(value);
    hoverLine.setAttribute("x1", String(clampedX));
    hoverLine.setAttribute("x2", String(clampedX));
    hoverPoint.setAttribute("cx", String(clampedX));
    hoverPoint.setAttribute("cy", String(valueY));

    const label = `${domainX >= 0 ? `+${domainX.toFixed(1)}` : domainX.toFixed(1)}h  |  ${(value * 100).toFixed(1)}%`;
    hoverText.textContent = label;
    const tooltipWidth = Math.max(76, hoverText.getComputedTextLength() + 12);
    const tooltipHeight = 24;
    const tooltipX = Math.min(width - padding.right - tooltipWidth, Math.max(padding.left, clampedX + 10));
    const tooltipY = Math.max(padding.top, valueY - 30);
    hoverBg.setAttribute("x", String(tooltipX));
    hoverBg.setAttribute("y", String(tooltipY));
    hoverBg.setAttribute("width", String(tooltipWidth));
    hoverBg.setAttribute("height", String(tooltipHeight));
    hoverText.setAttribute("x", String(tooltipX + 6));
    hoverText.setAttribute("y", String(tooltipY + (tooltipHeight / 2)));
    hoverGroup.setAttribute("visibility", "visible");
  };

  const animate = (nowMs) => {
    const phase = nowMs * 0.0022;
    animatedHistory = toAnimatedSeries(historySeries, phase, 0.012);
    animatedForecast = toAnimatedSeries(forecastSeries, phase + 0.9, 0.009);

    if (historyPath) {
      historyPath.setAttribute("d", buildPathData(animatedHistory));
    }
    if (forecastPath && animatedForecast.length) {
      forecastPath.setAttribute("d", buildPathData(animatedForecast));
    }

    const nowValue = animatedHistory[animatedHistory.length - 1]?.y ?? 0;
    const nowX = x(0);
    const nowY = y(nowValue);
    nowCircle.setAttribute("cx", String(nowX));
    nowCircle.setAttribute("cy", String(nowY));
    nowCircle.setAttribute("r", String(4.2 + (0.9 * (1 + Math.sin(phase * 1.6)))));

    nowValueText.textContent = `${(nowValue * 100).toFixed(1)}% live`;
    nowValueText.setAttribute("x", String(nowX + 10));
    nowValueText.setAttribute("y", String(nowY - 10));

    updateHover();
    frameId = requestAnimationFrame(animate);
    lstmAnimationRegistry.set(svg, { frameId });
  };

  svg.style.cursor = "crosshair";
  svg.onmousemove = (event) => {
    hoverClientX = event.clientX;
    updateHover();
  };
  svg.onmouseleave = () => {
    hoverClientX = null;
    hoverGroup.setAttribute("visibility", "hidden");
  };

  frameId = requestAnimationFrame(animate);
  lstmAnimationRegistry.set(svg, { frameId });
}
