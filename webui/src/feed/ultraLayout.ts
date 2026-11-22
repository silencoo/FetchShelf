interface Arrangement {
  spanning: boolean;
  rows: number[];
  count: number;
}

interface LayoutLimits {
  columns: number;
  rows: number;
  aspect: number;
}

interface BatchPlan extends Arrangement {
  start: number;
}

const SEARCH_POSTS = 8;

function rowAspect(aspects: readonly number[], start: number, count: number) {
  let aspect = 0;
  for (let i = start; i < start + count; i++) aspect += aspects[i];
  return aspect;
}

function greedyRows(aspects: readonly number[], start: number, limits: LayoutLimits): Arrangement {
  const rows: number[] = [];
  const target = limits.aspect * limits.rows;
  let index = start;
  while (index < aspects.length && rows.length < limits.rows) {
    let count = 1;
    let aspect = aspects[index++];
    while (count < limits.columns && index < aspects.length) {
      const next = aspect + aspects[index];
      if (aspect >= target || aspect * next > target ** 2) break;
      aspect = next;
      index++;
      count++;
    }
    rows.push(count);
  }
  return { spanning: false, rows, count: index - start };
}

function bestArrangement(
  aspects: readonly number[], start: number, limits: LayoutLimits, fallback: Arrangement, exact = false,
): Arrangement {
  const { aspect, columns, rows } = limits;
  const end = Math.min(aspects.length, start + (exact ? fallback.count : SEARCH_POSTS));
  if (exact && fallback.count > SEARCH_POSTS) return fallback;

  let best = fallback;
  const score = (width: number, count: number) => Math.min(width / aspect, aspect / width) + 0.03 * Math.log2(count);

  let index = start + Number(fallback.spanning);
  let height = 0;
  for (const count of fallback.rows) {
    height += 1 / rowAspect(aspects, index, count);
    index += count;
  }
  const minimum = exact ? fallback.count : Math.min(2, columns * rows, aspects.length - start);
  let bestScore = fallback.count >= minimum
    ? score(1 / height + (fallback.spanning ? aspects[start] : 0), fallback.count)
    : 0;

  function search(index: number, height: number, path: number[], spanning: boolean) {
    const count = index - start;
    if (path.length && count >= minimum && (!exact || index === end) && (!spanning || path.length >= 2)) {
      const candidate = score(1 / height + (spanning ? aspects[start] : 0), count);
      if (candidate > bestScore) {
        best = { spanning, rows: path, count };
        bestScore = candidate;
      }
    }
    if (path.length === rows) return;
    let width = 0;
    const rowEnd = Math.min(end, index + columns - Number(spanning));
    for (let next = index; next < rowEnd; next++) {
      width += aspects[next];
      search(next + 1, height + 1 / width, [...path, next + 1 - index], spanning);
    }
  }

  // Try ordered row breaks, plus a tall leading tile spanning the rows to its right.
  // The greedy fallback still handles batches larger than the lookahead.
  search(start, 0, [], false);
  if (columns >= 2 && rows >= 2 && end - start >= 3 && aspects[start] < 1) search(start + 1, 0, [], true);
  return best;
}

export function packUltraBatches(aspects: readonly number[], limits: LayoutLimits): BatchPlan[] {
  const batches: BatchPlan[] = [];
  let start = 0;
  while (start < aspects.length) {
    const plan = bestArrangement(aspects, start, limits, greedyRows(aspects, start, limits));
    batches.push({ ...plan, start });
    start += plan.count;
  }
  return batches;
}

export function fitUltraBatch(
  aspects: readonly number[], plan: Arrangement, limits: LayoutLimits, width: number, height: number,
) {
  const arrangement = bestArrangement(aspects, 0, limits, plan, true);
  const rowHeights: number[] = [];
  let index = Number(arrangement.spanning);
  for (const count of arrangement.rows) {
    rowHeights.push(1 / rowAspect(aspects, index, count));
    index += count;
  }
  const rowsHeight = rowHeights.reduce((sum, value) => sum + value, 0);
  const leadWidth = arrangement.spanning ? rowsHeight * aspects[0] : 0;
  const scale = Math.min(width / (1 + leadWidth), height / rowsHeight);
  const left = (width - (1 + leadWidth) * scale) / 2;
  let top = (height - rowsHeight * scale) / 2;
  const tiles = arrangement.spanning
    ? [{ left, top, width: leadWidth * scale, height: rowsHeight * scale }]
    : [];

  index = Number(arrangement.spanning);
  for (let row = 0; row < arrangement.rows.length; row++) {
    const rowHeight = rowHeights[row] * scale;
    let x = left + leadWidth * scale;
    for (let column = 0; column < arrangement.rows[row]; column++) {
      const tileWidth = rowHeight * aspects[index++];
      tiles.push({ left: x, top, width: tileWidth, height: rowHeight });
      x += tileWidth;
    }
    top += rowHeight;
  }
  return { tiles, spanning: arrangement.spanning };
}
