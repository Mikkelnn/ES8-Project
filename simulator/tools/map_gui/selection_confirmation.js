export let confirmedRoadPathObjects = [];
export let confirmedRoadIds = [];
export let confirmedCommonIntersectionPoints = [];
export let confirmedGatewayPoints = [];

const OUTPUT_FILE_NAME = 'selected_roads.json';
const SAVE_ENDPOINT = '/save-selected-roads';

const PATH_COMMAND_RE = /([ML])\s*(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g;
const POINT_TOLERANCE = 0.35;

function parsePathSegments(pathData) {
  const segments = [];
  let previousPoint = null;
  let match;

  PATH_COMMAND_RE.lastIndex = 0;
  while ((match = PATH_COMMAND_RE.exec(pathData)) !== null) {
    const command = match[1];
    const point = {
      x: Number(match[2]),
      y: Number(match[3]),
    };

    if (command === 'M') {
      previousPoint = point;
      continue;
    }

    if (command === 'L' && previousPoint) {
      segments.push([previousPoint, point]);
      previousPoint = point;
    }
  }

  return segments;
}

function pointLiesOnSegment(point, start, end, tolerance = POINT_TOLERANCE) {
  const minX = Math.min(start.x, end.x) - tolerance;
  const maxX = Math.max(start.x, end.x) + tolerance;
  const minY = Math.min(start.y, end.y) - tolerance;
  const maxY = Math.max(start.y, end.y) + tolerance;

  if (point.x < minX || point.x > maxX || point.y < minY || point.y > maxY) {
    return false;
  }

  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;

  if (lengthSquared === 0) {
    const distanceSquared = (point.x - start.x) ** 2 + (point.y - start.y) ** 2;
    return distanceSquared <= tolerance * tolerance;
  }

  const projection = ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared;
  const clamped = Math.max(0, Math.min(1, projection));
  const projectedX = start.x + clamped * dx;
  const projectedY = start.y + clamped * dy;
  const distanceSquared = (point.x - projectedX) ** 2 + (point.y - projectedY) ** 2;

  return distanceSquared <= tolerance * tolerance;
}

function findIntersectionIdsForPath(pathData, intersectionLookup) {
  const segments = parsePathSegments(pathData);
  if (!segments.length) {
    return [];
  }

  const matchedIntersectionIds = [];

  for (const [intersectionId, coords] of Object.entries(intersectionLookup)) {
    if (!Array.isArray(coords) || coords.length < 2) {
      continue;
    }

    const point = { x: Number(coords[0]), y: Number(coords[1]) };
    const isOnRoad = segments.some(([start, end]) => pointLiesOnSegment(point, start, end));
    if (isOnRoad) {
      matchedIntersectionIds.push(intersectionId);
    }
  }

  return matchedIntersectionIds;
}

function buildCommonIntersectionPoints(roadPathObjects, intersectionLookup) {
  const intersectionToRoads = new Map();

  for (const { roadId, path } of roadPathObjects) {
    const intersectionIds = findIntersectionIdsForPath(path, intersectionLookup);
    for (const intersectionId of intersectionIds) {
      if (!intersectionToRoads.has(intersectionId)) {
        intersectionToRoads.set(intersectionId, []);
      }
      intersectionToRoads.get(intersectionId).push(roadId);
    }
  }

  return [...intersectionToRoads.entries()]
    .filter(([, roadIds]) => roadIds.length > 1)
    .map(([intersectionId, roadIds]) => ({
      intersectionId,
      point: intersectionLookup[intersectionId],
      roadIds,
    }))
    .sort((left, right) => Number(left.intersectionId) - Number(right.intersectionId));
}

export function getConfirmedRoadPathObjects() {
  return [...confirmedRoadPathObjects];
}

export function getConfirmedRoadIds() {
  return [...confirmedRoadIds];
}

export function getConfirmedCommonIntersectionPoints() {
  return confirmedCommonIntersectionPoints.map((item) => ({
    ...item,
    roadIds: [...item.roadIds],
    point: Array.isArray(item.point) ? [...item.point] : item.point,
  }));
}

export function getConfirmedGatewayPoints() {
  return confirmedGatewayPoints.map((item) => ({
    id: item.id,
    point: Array.isArray(item.point) ? [...item.point] : item.point,
  }));
}

function buildSelectedRoadsJsonPayload() {
  const payload = {
    Road_ID: {},
    intersection_ID: {},
    gateway_points: [],
  };

  for (const item of confirmedRoadPathObjects) {
    payload.Road_ID[item.roadId] = {
      path: item.path,
    };
  }

  for (const item of confirmedCommonIntersectionPoints) {
    payload.intersection_ID[item.intersectionId] = {
      point: Array.isArray(item.point) ? [...item.point] : item.point,
    };
  }

  payload.gateway_points = confirmedGatewayPoints.map((item) => ({
    id: item.id,
    point: Array.isArray(item.point) ? [...item.point] : item.point,
  }));

  return payload;
}

async function saveSelectedRoadsJsonInPwd(payload, context = {}) {
  const endpoint = context.saveEndpoint || SAVE_ENDPOINT;
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fileName: OUTPUT_FILE_NAME,
      data: payload,
    }),
  });

  let result = {};
  try {
    result = await response.json();
  } catch {
    result = {};
  }

  if (!response.ok) {
    throw new Error(typeof result.error === 'string' ? result.error : `Save failed (${response.status})`);
  }

  return result;
}

export async function onSelectionConfirmed(ids, context = {}) {
  const safeIds = Array.isArray(ids) ? ids.map(String) : [];
  const roads = context.roadPaths || {};
  const intersections = context.intersectionPoints || {};

  confirmedGatewayPoints = Array.isArray(context.gatewayPoints)
    ? context.gatewayPoints
        .map((item) => ({
          id: Number(item?.id),
          point: Array.isArray(item?.point)
            ? [Number(item.point[0]), Number(item.point[1])]
            : [Number(item?.x), Number(item?.y)],
        }))
        .filter((item) => Number.isFinite(item.id) && item.point.every(Number.isFinite))
    : [];

  confirmedRoadIds = [...safeIds];
  confirmedRoadPathObjects = safeIds
    .map((roadId) => ({
      roadId,
      path: roads[roadId] ?? null,
    }))
    .filter((item) => item.path !== null);
  confirmedCommonIntersectionPoints = buildCommonIntersectionPoints(
    confirmedRoadPathObjects,
    intersections,
  );

  console.log('Confirmed road IDs:', confirmedRoadIds);
  console.log('Confirmed road path objects:', confirmedRoadPathObjects);
  console.log('Confirmed common intersection points:', confirmedCommonIntersectionPoints);
  console.log('Confirmed gateway points:', confirmedGatewayPoints);

  const payload = buildSelectedRoadsJsonPayload();

  try {
    const saveResult = await saveSelectedRoadsJsonInPwd(payload, context);
    if (typeof context.showToast === 'function') {
      if (typeof saveResult.savedTo === 'string' && saveResult.savedTo) {
        context.showToast(`Saved ${OUTPUT_FILE_NAME} to ${saveResult.savedTo}`);
      } else {
        context.showToast(`Saved ${OUTPUT_FILE_NAME}`);
      }
    }
  } catch (error) {
    console.error('Failed to save selected_roads.json:', error);
    if (typeof context.showToast === 'function') {
      context.showToast('Failed to save selected_roads.json. Run via displayed_gui.py server.');
    }
  }
}
